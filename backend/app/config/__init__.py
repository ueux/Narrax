"""Configuration boundary.

Owns everything about *how NarraX is configured and how it logs*:

- `settings.py` — the single typed `Settings` object, read from environment variables
  (and a local `.env`), validated at startup.
- `logging.py` — logging configuration and logger access.

This package is a **leaf**: it must not import any other `app.*` package, so it can be
imported safely from anywhere (including Alembic and tests).
"""

from app.config.logging import configure_logging, get_logger
from app.config.settings import Settings, get_settings, settings

__all__ = [
    "Settings",
    "configure_logging",
    "get_logger",
    "get_settings",
    "settings",
]
