"""PostgreSQL fixtures for database tests.

These tests exercise real constraints — foreign keys, uniqueness, CHECKs, cascades, and
pgvector behaviour — so they need a real PostgreSQL server with the `vector` extension. A
server is obtained in this order:

1. `NARRAX_TEST_DATABASE_URL`, if set (CI, `docker compose`, an existing server);
2. `pgserver`, if installed — a pip-installable, self-contained PostgreSQL + pgvector server
   that needs no admin rights and no Docker (`pip install -e ".[dev,db-test]"`);
3. otherwise the database tests **skip** with an explanatory message rather than failing.

Each test runs inside a transaction that is rolled back afterwards, so tests are independent
and the schema is migrated exactly once per session.
"""

import logging
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _redirect_pgserver_lock() -> None:
    """Move pgserver's cross-process lock into the system temp directory.

    pgserver resolves it via platformdirs' *runtime* directory, which is not writable in every
    environment. Python's temp directory is the conventional, writable choice here.
    """
    import fasteners
    from pgserver import PostgresServer

    lock_dir = Path(tempfile.gettempdir()) / "narrax-pgserver"
    lock_dir.mkdir(parents=True, exist_ok=True)
    PostgresServer.lock_path = lock_dir / ".lockfile"
    PostgresServer._lock = fasteners.InterProcessLock(PostgresServer.lock_path)


def _start_embedded_server() -> tuple[str, object] | None:
    """Start a throwaway PostgreSQL+pgvector server, or return None if unavailable."""
    try:
        import pgserver
    except ImportError:
        return None

    # pgserver logs from an atexit handler, which runs after pytest has closed stdout and would
    # otherwise print a confusing "Logging error" traceback on every run. Startup problems are
    # surfaced through the exception the caller turns into a skip reason.
    logging.getLogger("pgserver").setLevel(logging.CRITICAL)

    _redirect_pgserver_lock()
    pgdata = Path(tempfile.mkdtemp(prefix="narrax-pgtest-"))
    server = pgserver.get_server(str(pgdata), cleanup_mode="delete")
    return str(server.get_uri()), server


def _apply_migrations(database_url: str) -> None:
    """Point application settings at the test database and migrate it to head.

    Alembic's `env.py` reads the URL from application settings, so the cached settings object is
    updated rather than re-created — that keeps both the migrations and the app's own engine
    pointed at the same database.
    """
    from alembic.config import Config

    from alembic import command
    from app.config import settings

    settings.database_url = database_url

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(config, "head")


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """URL of a migrated PostgreSQL database with the vector extension available."""
    explicit = os.environ.get("NARRAX_TEST_DATABASE_URL")
    if explicit:
        _apply_migrations(explicit)
        yield explicit
        return

    try:
        started = _start_embedded_server()
    except Exception as exc:  # noqa: BLE001 - any startup failure means "no database available"
        # An installed-but-unusable server (missing shared memory, no permission to bind, ...)
        # is reported as a skip with the underlying reason, so the rest of the gate stays green
        # while the cause is still visible. Run with `-rs` to see skip reasons.
        pytest.skip(
            f"Embedded PostgreSQL could not start ({exc}). "
            "Set NARRAX_TEST_DATABASE_URL to use an existing server."
        )

    if started is None:
        pytest.skip(
            "No test database available. Set NARRAX_TEST_DATABASE_URL, or install the "
            "'db-test' extra (pip install -e '.[dev,db-test]') to run an embedded PostgreSQL."
        )

    url, server = started
    try:
        _apply_migrations(url)
        yield url
    finally:
        server.cleanup()  # type: ignore[attr-defined]


@pytest.fixture(scope="session")
def engine(database_url: str) -> Iterator[Engine]:
    """Engine bound to the migrated test database."""
    test_engine = create_engine(database_url, pool_pre_ping=True, future=True)
    try:
        yield test_engine
    finally:
        test_engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    """A session whose work is rolled back at the end of every test.

    The outer transaction is never committed, so tests cannot leak state into each other even
    when they deliberately trigger constraint violations (`session.rollback()` then returns to
    the savepoint rather than discarding the whole outer transaction).
    """
    connection = engine.connect()
    transaction = connection.begin()
    test_session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield test_session
    finally:
        test_session.close()
        transaction.rollback()
        connection.close()
