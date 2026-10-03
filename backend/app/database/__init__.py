"""Database boundary.

Owns persistence primitives and nothing else:

- `base.py` — the SQLAlchemy `DeclarativeBase` shared by every model.
- `session.py` — engine, session factory, and the FastAPI session dependency.
- `models/` — ORM models, grouped by epistemic layer (see docs/epistemic-layers.md).

Must not contain business rules and must not call external services.
"""

from app.database.base import Base
from app.database.session import SessionLocal, engine, get_db

__all__ = ["Base", "SessionLocal", "engine", "get_db"]
