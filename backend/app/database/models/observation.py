"""Layer 2 — ML observations.

Deterministic, model-derived facts, each recorded with the model/method version that produced
it so results stay attributable and re-runnable.

Tables
------
* `discussion_analysis` — a discussion's analysis record **within one run**. This row is also
  the run's corpus record: it exists as soon as the discussion is selected for the run, and its
  observation columns are filled in as stages complete. That is why sentiment/stance are
  nullable while the run/discussion pair is unique.
* `embeddings`          — one vector per (discussion, model, model version). Not scoped to a
  run: an embedding is a property of the text and the model, so re-running reuses it instead of
  duplicating vectors. `created_by_run_id` records who computed it first.
* `clusters`            — an opinion group produced by one run.
* `cluster_members`     — a discussion's assignment within a run, including explicit noise.

Noise is modelled as `cluster_members.is_noise = true` with a NULL `cluster_id` rather than as
a synthetic "noise cluster", so clusters always mean real groups and the two fields cannot
disagree (enforced by a CHECK).
"""

from datetime import datetime
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config.constants import EMBEDDING_DIMENSIONS
from app.database.base import Base
from app.database.models.enums import SentimentLabel, StanceLabel, sql_in
from app.database.models.mixins import CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin


class DiscussionAnalysis(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A discussion's analysis record within one run (and the run's corpus membership)."""

    __tablename__ = "discussion_analysis"

    analysis_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False
    )
    discussion_id: Mapped[UUID] = mapped_column(
        ForeignKey("discussions.id", ondelete="CASCADE"), nullable=False
    )

    # Detected language of the analysed text (English-only MVP, but recorded per item).
    language: Mapped[str | None] = mapped_column(Text)

    sentiment_label: Mapped[str | None] = mapped_column(Text)
    # Polarity in [-1, 1]: -1 most negative, +1 most positive.
    sentiment_score: Mapped[float | None] = mapped_column(Float)
    sentiment_model_version: Mapped[str | None] = mapped_column(Text)

    # Stance is relative to the owning run's topic, by construction.
    stance_label: Mapped[str | None] = mapped_column(Text)
    stance_confidence: Mapped[float | None] = mapped_column(Float)
    stance_method_version: Mapped[str | None] = mapped_column(Text)

    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        # A discussion's analysis rows across runs, and the discussion-delete cascade.
        Index("ix_discussion_analysis_discussion_id", "discussion_id"),
        UniqueConstraint(
            "analysis_run_id", "discussion_id", name="uq_discussion_analysis_run_discussion"
        ),
        CheckConstraint(
            f"sentiment_label IS NULL OR {sql_in('sentiment_label', SentimentLabel)}",
            name="sentiment_label_valid",
        ),
        CheckConstraint(
            f"stance_label IS NULL OR {sql_in('stance_label', StanceLabel)}",
            name="stance_label_valid",
        ),
        CheckConstraint(
            "sentiment_score IS NULL OR (sentiment_score >= -1 AND sentiment_score <= 1)",
            name="sentiment_score_range",
        ),
        CheckConstraint(
            "stance_confidence IS NULL OR (stance_confidence >= 0 AND stance_confidence <= 1)",
            name="stance_confidence_range",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"DiscussionAnalysis(run={self.analysis_run_id!r}, discussion={self.discussion_id!r})"
        )


class Embedding(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A versioned embedding vector for one discussion."""

    __tablename__ = "embeddings"

    discussion_id: Mapped[UUID] = mapped_column(
        ForeignKey("discussions.id", ondelete="CASCADE"), nullable=False
    )

    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    model_version: Mapped[str] = mapped_column(Text, nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)

    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS), nullable=False)

    # Provenance only: which run first computed it. Nullable so an embedding survives a run
    # being deleted (it is a property of the text and model, not of the run).
    created_by_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="SET NULL")
    )

    __table_args__ = (
        # Approximate nearest-neighbour search over embeddings, using cosine distance (the
        # standard metric for sentence embeddings). At MVP corpus sizes an exact scan is also
        # viable and the planner chooses; the index pays off as the table grows.
        Index(
            "ix_embeddings_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        UniqueConstraint(
            "discussion_id", "model_name", "model_version", name="uq_embeddings_discussion_model"
        ),
        CheckConstraint(
            f"dimensions = {EMBEDDING_DIMENSIONS}", name="dimensions_match_vector_column"
        ),
        CheckConstraint("length(btrim(model_name)) > 0", name="model_name_not_blank"),
        CheckConstraint("length(btrim(model_version)) > 0", name="model_version_not_blank"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Embedding(discussion={self.discussion_id!r}, model={self.model_name!r})"


class Cluster(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An opinion group discovered by one run's clustering."""

    __tablename__ = "clusters"

    analysis_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False
    )

    # The clustering algorithm's own label for this group (e.g. "0", "1"). Kept separate from
    # the human-readable label so re-labelling never changes identity.
    cluster_key: Mapped[str] = mapped_column(Text, nullable=False)

    label: Mapped[str | None] = mapped_column(Text)
    label_source: Mapped[str | None] = mapped_column(Text)

    algorithm: Mapped[str] = mapped_column(Text, nullable=False)
    algorithm_version: Mapped[str | None] = mapped_column(Text)

    # Optional centroid for ordering/visualisation; same dimensionality as the embeddings.
    centroid: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))

    members: Mapped[list["ClusterMember"]] = relationship(
        back_populates="cluster", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("analysis_run_id", "cluster_key", name="uq_clusters_run_key"),
        # Redundant with the primary key, but required so child tables can reference
        # (cluster, run) together and thereby prove they belong to the same run.
        UniqueConstraint("id", "analysis_run_id", name="uq_clusters_id_run"),
        CheckConstraint("length(btrim(cluster_key)) > 0", name="cluster_key_not_blank"),
        CheckConstraint("length(btrim(algorithm)) > 0", name="algorithm_not_blank"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Cluster(key={self.cluster_key!r}, label={self.label!r})"


class ClusterMember(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """The assignment of one discussion within one run's clustering."""

    __tablename__ = "cluster_members"

    analysis_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False
    )
    # NULL exactly when the item is noise (enforced by a CHECK below).
    cluster_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    discussion_id: Mapped[UUID] = mapped_column(
        ForeignKey("discussions.id", ondelete="CASCADE"), nullable=False
    )

    distance: Mapped[float | None] = mapped_column(Float)
    probability: Mapped[float | None] = mapped_column(Float)
    is_noise: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))

    cluster: Mapped["Cluster | None"] = relationship(back_populates="members")

    __table_args__ = (
        # Members of a cluster (the cluster detail view).
        Index("ix_cluster_members_cluster_id", "cluster_id"),
        # Which groups a discussion belongs to across runs; also the discussion-delete cascade.
        Index("ix_cluster_members_discussion_id", "discussion_id"),
        # A discussion belongs to at most one group (or to noise) per run.
        UniqueConstraint(
            "analysis_run_id", "discussion_id", name="uq_cluster_members_run_discussion"
        ),
        # Composite FK: the referenced cluster must belong to the same run. Not enforced for
        # noise rows, because MATCH SIMPLE skips a constraint when any column is NULL.
        ForeignKeyConstraint(
            ["cluster_id", "analysis_run_id"],
            ["clusters.id", "clusters.analysis_run_id"],
            ondelete="CASCADE",
            name="fk_cluster_members_cluster_run",
        ),
        CheckConstraint("(cluster_id IS NULL) = is_noise", name="noise_consistency"),
        CheckConstraint(
            "probability IS NULL OR (probability >= 0 AND probability <= 1)",
            name="probability_range",
        ),
        CheckConstraint("distance IS NULL OR distance >= 0", name="distance_non_negative"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"ClusterMember(cluster={self.cluster_id!r}, noise={self.is_noise!r})"
