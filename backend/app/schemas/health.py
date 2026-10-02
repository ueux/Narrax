"""Health-check response schemas."""

from pydantic import BaseModel


class LivenessResponse(BaseModel):
    """Liveness: the process is up."""

    status: str


class ReadinessResponse(BaseModel):
    """Readiness: the process can reach its dependencies."""

    status: str
    database: str
