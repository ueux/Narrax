"""Declarative base for all NarraX ORM models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class shared by every SQLAlchemy model."""
