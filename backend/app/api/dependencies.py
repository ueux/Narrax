"""Shared FastAPI dependency aliases.

Routes depend on these aliases rather than spelling out `Depends(...)` inline, so wiring
changes (e.g. a read-replica session, a request-scoped settings override) happen in one
place.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.database.session import get_db

DbSession = Annotated[Session, Depends(get_db)]
"""Request-scoped SQLAlchemy session, always closed after the request."""
