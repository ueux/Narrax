"""Tests for the health endpoints (api boundary)."""

from fastapi.testclient import TestClient


def test_liveness_returns_ok(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_returns_ok_when_database_reachable(
    client: TestClient, reachable_db: None
) -> None:
    response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_readiness_returns_503_when_database_unavailable(
    client: TestClient, unreachable_db: None
) -> None:
    response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": "unavailable"}
