"""Layer 4 — temporal observations.

A `NarrativeSnapshot` records what a narrative looked like **at one point in time**: how many
discussions and citations it had, its share of the corpus, and the direction of travel. These
are observations about change, kept separate from the interpretation itself so a trend can be
recomputed without touching Layer 3.

Design note (documented in docs/database.md): a snapshot references the narrative it observed
and the run that produced the observation, and the pair is unique. At MVP scale one snapshot is
written per narrative per run, because each run currently produces its own narrative rows.
Cross-run narrative identity — which would give one narrative many snapshots over time — is
Phase 6 work; the table is already shaped for it, and first/last-seen are derived by
aggregating `as_of` rather than being stored redundantly.
"""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKeyConstraint,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.models.enums import TrendDirection, sql_in
from app.database.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.database.models.narrative import Narrative


class NarrativeSnapshot(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A narrative's observed state at one point in time."""

    __tablename__ = "narrative_snapshots"

    narrative_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    analysis_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)

    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Counts are the observation itself (not a cache of a live table), so they are stored.
    member_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    # Share of the run's corpus, in [0, 1]. Relative share is stored next to absolute counts so
    # small-sample effects are visible (FR-11.4).
    share: Mapped[float | None] = mapped_column(Float)
    direction: Mapped[str | None] = mapped_column(Text)

    narrative: Mapped["Narrative"] = relationship(back_populates="snapshots")

    __table_args__ = (
        UniqueConstraint("narrative_id", "analysis_run_id", name="uq_narrative_snapshots_pair"),
        # Composite FK: the snapshot's run must be the narrative's own run.
        ForeignKeyConstraint(
            ["narrative_id", "analysis_run_id"],
            ["narratives.id", "narratives.analysis_run_id"],
            ondelete="CASCADE",
            name="fk_narrative_snapshots_narrative_run",
        ),
        CheckConstraint("member_count >= 0", name="member_count_non_negative"),
        CheckConstraint("evidence_count >= 0", name="evidence_count_non_negative"),
        CheckConstraint("share IS NULL OR (share >= 0 AND share <= 1)", name="share_range"),
        CheckConstraint(
            f"direction IS NULL OR {sql_in('direction', TrendDirection)}", name="direction_valid"
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"NarrativeSnapshot(narrative={self.narrative_id!r}, as_of={self.as_of!r})"
