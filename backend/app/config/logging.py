"""Logging configuration.

Phase 0 uses a simple, explicit stdout configuration. Structured (JSON) output, request
correlation ids, and per-run ids are introduced when the pipeline lands (NFR-16); the
`get_logger` entry point stays the same so call sites do not change.
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
