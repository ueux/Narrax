"""Shared fixtures for ingestion tests."""

import shutil
import tempfile
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "reddit"


@pytest.fixture
def fixture_dir() -> Path:
    """Directory of recorded Reddit payloads, shared by adapter and report tests."""
    return FIXTURE_DIR


@pytest.fixture
def frozen_now() -> datetime:
    """A fixed retrieval timestamp, so normalization tests are deterministic."""
    return datetime(2024, 5, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def scratch_dir() -> Iterator[Path]:
    """A writable scratch directory, removed afterwards.

    Deliberately not pytest's `tmp_path`: that uses `tempfile.mkdtemp`, whose restrictive directory
    mode is not writable in every confined environment (hardened runners, sandboxes). `mkdir` with
    the process umask is portable and sufficient for tests that only need a folder to write into.
    """
    directory = Path(tempfile.gettempdir()) / f"narrax-test-{uuid4().hex}"
    directory.mkdir(parents=True, exist_ok=True)
    try:
        yield directory
    finally:
        shutil.rmtree(directory, ignore_errors=True)
