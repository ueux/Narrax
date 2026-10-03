"""Layer 2 — text preparation: what is analysable, and why something is not.

Cleaning is a **deterministic function of the source text plus a rule set**, so its result is not
part of any single analysis run and is not stored there. It gets its own record, keyed by
`(discussion, pipeline_version)`:

* **the cleaned text**, so embedding, sentiment and stance read one canonical form instead of
  each re-deriving it;
* **the decision** — usable, or excluded with one of a closed vocabulary of reasons — so corpus
  size is always explainable and never shrinks silently (FR-2.6);
* **the content hash**, so the same text posted twice is detected rather than counted twice.

Source text is untouched: `discussions.body` remains what the platform served. This table is the
derived view of it (docs/adr/0009-epistemic-layer-separation.md).

`pipeline_version` is a fingerprint of the cleaning rules. Change a threshold and the next run
writes new rows rather than quietly redefining what earlier rows meant.
"""

from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.models.enums import ExclusionReason, sql_in
from app.database.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin


class TextPreparation(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """The cleaning outcome for one discussion under one cleaning configuration."""

    __tablename__ = "text_preparation"

    discussion_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("discussions.id", ondelete="CASCADE"), nullable=False
    )
    # Fingerprint of the cleaning rules that produced this row.
    pipeline_version: Mapped[str] = mapped_column(Text, nullable=False)

    cleaned_text: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    # `''` rather than NULL when nothing was cleaned, so duplicate detection can filter on a
    # single, unambiguous predicate (`content_hash <> ''`).
    content_hash: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))

    # Language of the cleaned text. This table owns it: it was duplicating a column on
    # `discussion_analysis`, which is per-run while language is a property of the text.
    language: Mapped[str | None] = mapped_column(Text)
    language_confidence: Mapped[float | None] = mapped_column(Float)
    script: Mapped[str | None] = mapped_column(Text)

    character_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    url_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    formatting_artifact_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )

    is_usable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    exclusion_reason: Mapped[str | None] = mapped_column(Text)
    exclusion_detail: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint(
            "discussion_id", "pipeline_version", name="uq_text_preparation_discussion_version"
        ),
        # Duplicate detection looks up by hash across the whole corpus; the discussion-id lookup
        # is already served by the leading column of the unique constraint above.
        Index("ix_text_preparation_content_hash", "content_hash"),
        CheckConstraint(
            f"exclusion_reason IS NULL OR {sql_in('exclusion_reason', ExclusionReason)}",
            name="exclusion_reason_valid",
        ),
        CheckConstraint(
            "(is_usable AND exclusion_reason IS NULL) "
            "OR (NOT is_usable AND exclusion_reason IS NOT NULL)",
            name="usable_matches_reason",
        ),
        CheckConstraint("character_count >= 0", name="character_count_non_negative"),
        CheckConstraint("word_count >= 0", name="word_count_non_negative"),
        CheckConstraint("url_count >= 0", name="url_count_non_negative"),
        CheckConstraint("formatting_artifact_count >= 0", name="artifact_count_non_negative"),
        CheckConstraint(
            "language_confidence IS NULL "
            "OR (language_confidence >= 0 AND language_confidence <= 1)",
            name="language_confidence_range",
        ),
        CheckConstraint("length(btrim(pipeline_version)) > 0", name="pipeline_version_not_blank"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        state = "usable" if self.is_usable else f"excluded:{self.exclusion_reason}"
        return f"TextPreparation(discussion={self.discussion_id!r}, {state})"
