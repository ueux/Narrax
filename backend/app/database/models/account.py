"""Application accounts.

Layer 0 — **operator identity**, not source data. A `User` is the analyst who defines a topic
or triggers a run. It is deliberately unrelated to `Author`, which holds pseudonymous source
handles and is never enriched (docs/data-safety.md).

See docs/adr/0014-operator-accounts.md for why this exists in the MVP.
"""

from sqlalchemy import Boolean, CheckConstraint, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An operator/analyst account."""

    __tablename__ = "users"

    # Stored lower-cased so that identity is case-insensitive (enforced by a CHECK).
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    __table_args__ = (
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        CheckConstraint("position('@' in email) > 1", name="email_shape"),
        CheckConstraint("length(btrim(display_name)) > 0", name="display_name_not_blank"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"User(id={self.id!r}, email={self.email!r})"
