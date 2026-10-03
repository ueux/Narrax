"""Aggregates every API route module into one router.

`app.main` mounts this router once, under `settings.api_v1_prefix`. Adding a resource means
creating a module in `app/api/routes/` and including it here — nothing else.
"""

from fastapi import APIRouter

from app.api.routes import health

api_router = APIRouter()
api_router.include_router(health.router)
