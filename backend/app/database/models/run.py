"""Analysis runs and their per-stage records.

**Run metadata (not an epistemic layer).** A run explains *how* every derived row in Layers 2–4
came to exist: which topic, which configuration, which versions, and which stages succeeded.

`RunStage` is an addition to the core table list: resumability (FR-18/FR-20) and per-stage
reporting (FR-19) need a structured record, and modelling that as JSONB would forfeit the
`(run, stage)` uniqueness that makes resume logic safe. See docs/database.md.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.models.enums import RunStatus, Stage, StageStatus, sql_in
from app.database.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class AnalysisRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One execution of the analysis pipeline for a topic."""

    __tablename__ = "analysis_runs"

    topic_id: Mapped[UUID] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
    )
    triggered_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'pending'"))

    # The window actually analysed, which may be narrower than the topic's default window.
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Genuinely flexible metadata: model names/versions, clustering parameters and prompt
    # versions differ per stage and evolve between runs, so the exact shape is not fixed.
    config: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    # An observation of the run (how many discussions it covered), nullable until computed.
    corpus_size: Mapped[int | None] = mapped_column(Integer)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)

    stages: Mapped[list["RunStage"]] = relationship(
        back_populates="analysis_run", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # "Runs for a topic" (the topic page) and the topic-delete cascade. Foreign keys are not
        # indexed by PostgreSQL, so without this, deleting a topic scans every run.
        Index("ix_analysis_runs_topic_id", "topic_id"),
        CheckConstraint(sql_in("status", RunStatus), name="status_valid"),
        CheckConstraint(
            "window_start IS NULL OR window_end IS NULL OR window_end >= window_start",
            name="window_order",
        ),
        CheckConstraint("corpus_size IS NULL OR corpus_size >= 0", name="corpus_size_non_negative"),
        CheckConstraint(
            "finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at",
            name="finish_after_start",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"AnalysisRun(id={self.id!r}, status={self.status!r})"


class RunStage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One stage of one run: status, counts, and timing."""

    __tablename__ = "run_stages"

    analysis_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False
    )
    stage: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'pending'"))

    items_in: Mapped[int | None] = mapped_column(Integer)
    items_out: Mapped[int | None] = mapped_column(Integer)
    items_dropped: Mapped[int | None] = mapped_column(Integer)

    # Per-stage counters evolve as instrumentation improves; the shape is intentionally open.
    metrics: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    analysis_run: Mapped["AnalysisRun"] = relationship(back_populates="stages")

    __table_args__ = (
        UniqueConstraint("analysis_run_id", "stage", name="uq_run_stages_run_stage"),
        CheckConstraint(sql_in("status", StageStatus), name="status_valid"),
        CheckConstraint(sql_in("stage", Stage), name="stage_valid"),
        CheckConstraint("length(btrim(stage)) > 0", name="stage_not_blank"),
        CheckConstraint(
            "items_in IS NULL OR items_out IS NULL OR items_dropped IS NULL "
            "OR items_in >= items_out + items_dropped",
            name="counts_are_consistent",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"RunStage(stage={self.stage!r}, status={self.status!r})"
