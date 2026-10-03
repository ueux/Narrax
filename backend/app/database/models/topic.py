"""Topics and the communities they select.

**Layer 1 (selection metadata).** A `Topic` is the root of the conceptual hierarchy: it names
the subject under study and records the criteria that scope collection. It holds no source
content and no derived values.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.models.mixins import CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Topic(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A saved analysis target: what to study, where, and over which window."""

    __tablename__ = "topics"

    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)

    # Plain list of search terms. Stored as a PostgreSQL text[] rather than JSONB because the
    # shape is a simple array, not flexible metadata.
    query_terms: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )

    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Authorship of the *topic definition* (operator identity), not of any source content.
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    __table_args__ = (
        CheckConstraint("length(btrim(name)) > 0", name="name_not_blank"),
        CheckConstraint(
            "window_start IS NULL OR window_end IS NULL OR window_end >= window_start",
            name="window_order",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Topic(id={self.id!r}, name={self.name!r})"


class TopicCommunity(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Which communities a topic collects from.

    A join table is used rather than a column of ids on `topics` so that community references
    are protected by a foreign key and cannot dangle (the alternative was an unenforceable
    `uuid[]`). The natural key `(topic_id, community_id)` is enforced by a unique constraint.
    """

    __tablename__ = "topic_communities"

    topic_id: Mapped[UUID] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
    )
    community_id: Mapped[UUID] = mapped_column(
        ForeignKey("communities.id", ondelete="CASCADE"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("topic_id", "community_id", name="uq_topic_communities_pair"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"TopicCommunity(topic_id={self.topic_id!r}, community_id={self.community_id!r})"
