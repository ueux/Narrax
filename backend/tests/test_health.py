"""Tests for the health endpoints.

These tests do not require a running database: the readiness test overrides the
`get_db` dependency with in-memory fakes.
"""

from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app

client = TestClient(app)


class _OkSession:
    """Fake session whose `execute` succeeds (simulates a reachable database)."""

    def execute(self, *args: object, **kwargs: object) -> None:
        return None


class _FailingSession:
    """Fake session whose `execute` raises (simulates an unreachable database)."""

    def execute(self, *args: object, **kwargs: object) -> None:
        raise RuntimeError("database unavailable")


def _ok_db() -> object:
    yield _OkSession()


def _failing_db() -> object:
    yield _FailingSession()


def test_liveness_returns_ok() -> None:
    response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_returns_ok_when_database_reachable() -> None:
    app.dependency_overrides[get_db] = _ok_db
    try:
        response = client.get("/api/v1/health/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_readiness_returns_503_when_database_unavailable() -> None:
    app.dependency_overrides[get_db] = _failing_db
    try:
        response = client.get("/api/v1/health/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": "unavailable"}
