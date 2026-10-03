"""Application entrypoint for the NarraX FastAPI service.

Composition order is deliberate: configure logging, build the app, mount the aggregated
API router under the version prefix. No business logic lives here.
"""

from fastapi import FastAPI

from app.api.router import api_router
from app.config import configure_logging, settings

configure_logging()

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url="/redoc" if settings.environment != "production" else None,
    openapi_url="/openapi.json" if settings.environment != "production" else None,
)

app.include_router(api_router, prefix=settings.api_v1_prefix)
