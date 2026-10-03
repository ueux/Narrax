"""Command-line entry points.

A thin presentation boundary, the terminal counterpart of `app/api/`: it parses arguments, opens a
session, calls a service, prints a result, and exits with a status. No business logic lives here.

    python -m app.cli.ingest_recorded --help
    python -m app.cli.inspect_dataset --help
"""

from app.cli.session import session_scope

__all__ = ["session_scope"]
