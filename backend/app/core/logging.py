"""Logging configuration.

Phase 0 uses a simple, explicit stdout configuration. A structured (JSON) formatter
can be introduced later if a log-aggregation requirement appears.
"""

import logging
import sys


def configure_logging(level: int = logging.INFO) -> None:
    """Configure the root logger with a clear, human-readable format."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )


def get_logger(name: str) -> logging.Logger:
    """Return a named logger."""
    return logging.getLogger(name)
