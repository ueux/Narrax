"""Tests for configuration loading and validation.

`_env_file=None` ignores any developer-local `.env`, so these tests assert code defaults
rather than a machine's configuration.
"""

import pytest

from app.config.settings import Settings


def test_api_prefix_default_is_versioned() -> None:
    settings = Settings(_env_file=None)

    assert settings.api_v1_prefix == "/api/v1"
    assert settings.environment == "development"


def test_database_url_uses_psycopg_driver() -> None:
    settings = Settings(_env_file=None)

    assert settings.database_url.startswith("postgresql+psycopg://")


def test_llm_defaults_disable_llm_stages() -> None:
    """No provider configured means LLM-dependent stages stay off (NFR-10)."""
    settings = Settings(_env_file=None)

    assert settings.llm_provider == ""
    assert settings.llm_api_key == ""


def test_environment_variable_overrides_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_V1_PREFIX", "/api/v9")

    assert Settings(_env_file=None).api_v1_prefix == "/api/v9"
