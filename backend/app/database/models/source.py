"""Layer 1 — source truth.

Everything the pipeline *collected*, stored unmodified and separate from anything computed.

Tables
------
* `sources`     — platforms NarraX reads from (Reddit only in the MVP).
* `communities` — a community within a source (a subreddit).
* `authors`     — a **pseudonymous** source handle. Deliberately holds no profile data; see
                  docs/data-safety.md.
* `discussions` — a post or a reply. One table with a self-referencing parent models the
                  thread tree, so a comment and its parent are the same kind of thing with
                  the same provenance.

Authorship fields are write-once: only NarraX-owned retrieval metadata (`collected_at`) is
ever refreshed on re-ingestion.
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
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.models.enums import DiscussionKind, sql_in
from app.database.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Source(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A platform that discussions are collected from."""

    __tablename__ = "sources"

    # Stable machine key, e.g. "reddit". Lower-cased so it cannot be duplicated by casing.
    key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    base_url: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))

    __table_args__ = (
        CheckConstraint("key = lower(key)", name="key_lowercase"),
        CheckConstraint("length(btrim(key)) > 0", name="key_not_blank"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Source(key={self.key!r})"


class Community(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A community inside a source (a subreddit in the MVP)."""

    __tablename__ = "communities"

    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    # The source's own identifier for the community, e.g. "technology".
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_communities_source_external"),
        CheckConstraint("length(btrim(external_id)) > 0", name="external_id_not_blank"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Community(external_id={self.external_id!r})"


class Author(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A pseudonymous source author handle.

    Intentionally minimal: an opaque identifier and nothing else. No profile enrichment, no
    cross-platform linking, no inferred attributes (docs/data-safety.md).
    """

    __tablename__ = "authors"

    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_authors_source_external"),
        CheckConstraint("length(btrim(external_id)) > 0", name="external_id_not_blank"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Author(external_id={self.external_id!r})"


class Discussion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A collected post or reply.

    `kind` distinguishes a top-level post from a comment; `parent_discussion_id` links a reply
    to whatever it replied to. A comment whose parent was never collected keeps a NULL parent
    (the parent may have been filtered or deleted upstream), which is why the "comment implies
    parent" invariant is *not* enforced — only the post-side invariants are.
    """

    __tablename__ = "discussions"

    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    community_id: Mapped[UUID] = mapped_column(
        ForeignKey("communities.id", ondelete="CASCADE"), nullable=False
    )
    author_id: Mapped[UUID | None] = mapped_column(ForeignKey("authors.id", ondelete="SET NULL"))
    parent_discussion_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("discussions.id", ondelete="CASCADE")
    )

    # The source's own identifier for this item — the natural key, scoped per source.
    external_id: Mapped[str] = mapped_column(Text, nullable=False)

    kind: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    url: Mapped[str | None] = mapped_column(Text)

    # Upvote-like score as retrieved. Mutable at the source, so it is a point-in-time value;
    # the authoritative analysis fields are `body`/`created_at`.
    source_score: Mapped[int | None] = mapped_column(Integer)

    # When the source says it was written (immutable) ...
    source_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # ... versus when NarraX retrieved it (refreshable).
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Source-specific extras (flair, awards, edit state, ...). Genuinely open-ended metadata
    # that differs per platform, kept out of the relational columns on purpose.
    raw_metadata: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    parent: Mapped["Discussion | None"] = relationship(
        back_populates="children", remote_side="Discussion.id"
    )
    children: Mapped[list["Discussion"]] = relationship(back_populates="parent")

    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_discussions_source_external"),
        # "Discussions by community" and "chronological within a community" in one index; the
        # trailing time column also satisfies ORDER BY on time for a fixed community.
        Index("ix_discussions_community_created_at", "community_id", "source_created_at"),
        # Chronological listing across communities, and the run-window filter
        # (source_created_at BETWEEN ...) that every analysis run applies.
        Index("ix_discussions_source_created_at", "source_created_at"),
        # Thread reconstruction (a post's replies) and the self-referencing FK: PostgreSQL does
        # not index foreign keys, so a parent delete would otherwise scan the whole table.
        Index("ix_discussions_parent_discussion_id", "parent_discussion_id"),
        CheckConstraint(sql_in("kind", DiscussionKind), name="kind_valid"),
        CheckConstraint("kind <> 'post' OR title IS NOT NULL", name="post_has_title"),
        CheckConstraint("kind <> 'post' OR parent_discussion_id IS NULL", name="post_is_root"),
        CheckConstraint(
            "parent_discussion_id IS NULL OR parent_discussion_id <> id", name="no_self_parent"
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Discussion(id={self.id!r}, kind={self.kind!r}, external_id={self.external_id!r})"
