"""Database session handling for CLI commands.

The engine is built from `settings.database_url` **at call time** rather than reusing the
application's module-level engine. That is deliberate: a caller (a test, a report generator, an
operator pointing at a different database) can set the URL on the settings object immediately
before invoking a command and have it honoured.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import settings


@contextmanager
def session_scope(database_url: str | None = None) -> Iterator[Session]:
    """Yield a session inside a transaction, committing on success and rolling back on error."""
    url = database_url or settings.database_url
    engine = create_engine(url, pool_pre_ping=True, future=True)
    session = Session(bind=engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()
