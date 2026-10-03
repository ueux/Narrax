"""Shared pytest fixtures.

Tests must not require a live database: the readiness dependency is overridden with an
in-memory fake session, so the suite runs in isolation and in CI with no services.
"""

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from app.database.session import get_db
from app.main import app


class FakeSession:
    """Minimal stand-in for a SQLAlchemy `Session`.

    Only `execute` is exercised by the health routes. `fail=True` simulates an
    unreachable database.
    """

    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail

    def execute(self, *args: object, **kwargs: object) -> None:
        if self._fail:
            raise RuntimeError("database unavailable")
        return None


def _db_dependency(*, fail: bool) -> Callable[[], Iterator[FakeSession]]:
    """Build a `get_db` replacement yielding a `FakeSession`."""

    def _get_db() -> Iterator[FakeSession]:
        yield FakeSession(fail=fail)

    return _get_db


@pytest.fixture
def client() -> Iterator[TestClient]:
    """A `TestClient` bound to the app, with startup/shutdown handled."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def reachable_db() -> Iterator[None]:
    """Override the DB dependency with a session that answers `SELECT 1`."""
    app.dependency_overrides[get_db] = _db_dependency(fail=False)
    try:
        yield
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def unreachable_db() -> Iterator[None]:
    """Override the DB dependency with a session that raises on use."""
    app.dependency_overrides[get_db] = _db_dependency(fail=True)
    try:
        yield
    finally:
        app.dependency_overrides.clear()
