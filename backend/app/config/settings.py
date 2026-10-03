"""Application settings loaded from environment variables and a local `.env` file.

This is the **only** place the application reads the environment. Modules import
`settings` (or the `get_settings()` factory) instead of touching `os.environ`, so that:

- configuration is typed and validated once, at import time (NFR-21);
- every variable is documented in `.env.example` (NFR-20);
- secrets never appear in source control (NFR-19).
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config/settings.py -> app/config -> app -> backend
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime configuration. Values are read from env vars, falling back to `.env`."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "NarraX"
    version: str = "0.1.0"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"

    # Database
    database_url: str = "postgresql+psycopg://narrax:narrax_dev_password@localhost:5432/narrax"

    # LLM (provider-independent; see docs/adr/0005-provider-independent-llm.md).
    # Empty provider/key disables the LLM-dependent pipeline stages only.
    llm_provider: str = ""
    llm_api_key: str = ""

    # Reddit ingestion (docs/adr/0008-reddit-only-ingestion.md)
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "narrax-dev/0.1"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()


settings = get_settings()
