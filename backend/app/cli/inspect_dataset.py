"""Inspect an analysis dataset and print or write a report.

Answers "is the data sound?" before any narrative work is attempted: volume, provenance, language
mix, content length, missing values, duplication, exclusions, time range and coverage. It performs
**no** narrative analysis (PROMPT 16).

    python -m app.cli.inspect_dataset
    python -m app.cli.inspect_dataset --format json --output data/exports/dataset.json
"""

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from app.cli.session import session_scope
from app.services.inspection import inspect_dataset, render_markdown


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="inspect_dataset",
        description="Report on the contents and quality of the analysis dataset.",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="output format (default: markdown)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="write to this file instead of stdout (parent directories are created)",
    )
    parser.add_argument(
        "--top-communities",
        type=int,
        default=10,
        help="how many communities to list (default: 10)",
    )
    parser.add_argument("--database-url", default=None, help="override DATABASE_URL")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    with session_scope(args.database_url) as session:
        report = inspect_dataset(session, top_community_limit=args.top_communities)

    text = (
        render_markdown(report)
        if args.format == "markdown"
        else json.dumps(report.to_dict(), indent=2)
    )

    if args.output is None:
        print(text)
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text + "\n", encoding="utf-8")
    print(f"wrote {args.format} report to {args.output}")
    return 0


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
