"""Ingest recorded Reddit payloads.

Live collection needs OAuth credentials and outbound network access; neither is always available.
This command replays recorded payloads through the **real** pipeline — the same normalization,
cleaning, deduplication, and persistence code as a live run — so a developer can exercise and
inspect the pipeline offline, and a report can be regenerated deterministically.

    python -m app.cli.ingest_recorded --topic "AI regulation" --limit 40
    python -m app.cli.ingest_recorded --input-dir tests/fixtures/reddit --topic "Demo"
"""

import argparse
from collections.abc import Sequence
from pathlib import Path

from app.cli.session import session_scope
from app.ingestion.base import IngestionError, SourceQuery
from app.ingestion.reddit import RecordedRedditAdapter
from app.services.collection import CollectionError, CollectionRequest, collect_discussions
from app.services.topics import ensure_topic

DEFAULT_INPUT_DIR = Path("tests/fixtures/reddit")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ingest_recorded",
        description="Ingest recorded Reddit payloads into the NarraX database.",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help=f"directory of recorded payloads (default: {DEFAULT_INPUT_DIR})",
    )
    parser.add_argument("--topic", required=True, help="topic name to collect under")
    parser.add_argument("--terms", nargs="*", default=[], help="search terms for the topic")
    parser.add_argument(
        "--communities", nargs="*", default=[], help="communities to scope the collection to"
    )
    parser.add_argument("--limit", type=int, default=100, help="maximum posts to collect")
    parser.add_argument("--comment-limit", type=int, default=100, help="maximum comments per post")
    parser.add_argument(
        "--no-comments", action="store_true", help="collect posts only, skipping comment threads"
    )
    parser.add_argument("--database-url", default=None, help="override DATABASE_URL")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        query = SourceQuery(
            terms=tuple(args.terms),
            communities=tuple(args.communities),
            limit=args.limit,
            include_comments=not args.no_comments,
            comment_limit=args.comment_limit,
        )
    except ValueError as exc:
        print(f"invalid query: {exc}")
        return 2

    adapter = RecordedRedditAdapter(args.input_dir)

    try:
        with session_scope(args.database_url) as session:
            topic = ensure_topic(session, args.topic, query_terms=tuple(args.terms))
            report = collect_discussions(
                session,
                adapter,
                CollectionRequest(
                    topic_id=topic.id,
                    query=query,
                    collect_comments=not args.no_comments,
                    comment_limit=args.comment_limit,
                ),
            )
    except (IngestionError, CollectionError) as exc:
        print(f"collection failed: {exc}")
        return 1

    print(f"topic:     {args.topic}")
    print(f"run:       {report.run_id}")
    print(
        f"stored:    {report.stored_total} discussions "
        f"({report.discussions_inserted} new, {report.discussions_refreshed} refreshed)"
    )
    print(f"posts:     {report.posts_seen} seen, {report.comments_seen} comments seen")
    print(
        f"prepared:  {report.prepared} "
        f"({report.usable} usable, {report.excluded} excluded, {report.duplicates} duplicates)"
    )
    for reason, count in sorted(report.exclusion_reasons.items(), key=lambda pair: -pair[1]):
        print(f"  {reason:<22} {count}")
    skipped = (
        report.adapter_stats.get("skipped_malformed", 0)
        + report.adapter_stats.get("skipped_out_of_window", 0)
        + report.adapter_stats.get("skipped_out_of_scope", 0)
    )
    if skipped or report.adapter_stats.get("skipped_duplicate_id"):
        print(
            "adapter:   "
            f"{report.adapter_stats.get('skipped_duplicate_id', 0)} duplicate ids, "
            f"{skipped} filtered"
        )
    return 0


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
