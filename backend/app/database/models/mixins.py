"""Reusable column mixins shared by every NarraX ORM model."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column


class UUIDPrimaryKeyMixin:
    """A UUID surrogate primary key.

    Both a Python-side default and a server-side default are declared:

    * `default=uuid4` lets the ORM assign an id without a database round trip;
    * `server_default=gen_random_uuid()` (built into PostgreSQL 13+, no extension needed)
      keeps raw SQL inserts and bulk operations working.
    """

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=func.gen_random_uuid(),
    )


class CreatedAtMixin:
    """`created_at` only — for append-only rows.

    Observation, evidence, membership and snapshot rows are never updated once written, so
    they carry no `updated_at`: an `updated_at` that can never change would imply a mutability
    the data does not have.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class TimestampMixin(CreatedAtMixin):
    """`created_at` + `updated_at` — for rows that legitimately change.

    `updated_at` is maintained by the ORM (`onupdate`), which covers ORM and SQLAlchemy Core
    writes. It is *not* maintained for hand-written SQL; the trade-off and the trigger-based
    alternative are documented in docs/database.md.
    """

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
