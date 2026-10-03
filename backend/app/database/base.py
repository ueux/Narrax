"""Declarative base and metadata conventions for all NarraX ORM models."""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Deterministic constraint names. Without a naming convention PostgreSQL invents names for
# unnamed constraints, and a later migration cannot reliably target one to drop or alter it.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base class shared by every SQLAlchemy model."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
