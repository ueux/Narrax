"""Health-check endpoints.

- `/health/live`  — process liveness (no dependencies touched).
- `/health/ready` — readiness, including a database connectivity probe.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.health import LivenessResponse

router = APIRouter(tags=["health"])


@router.get("/health/live", response_model=LivenessResponse)
def liveness() -> LivenessResponse:
    """Report process liveness."""
    return LivenessResponse(status="ok")


@router.get("/health/ready")
def readiness(db: Annotated[Session, Depends(get_db)]) -> JSONResponse:
    """Report readiness, probing the database."""
    try:
        db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - surface any DB failure as "not ready"
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unavailable", "database": "unavailable"},
        )
    return JSONResponse(content={"status": "ok", "database": "ok"})
