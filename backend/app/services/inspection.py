"""Dataset inspection — what is actually in the corpus (PROMPT 16).

A read-only report over Layer 1 and the text-preparation record. It exists to answer the questions
that decide whether a corpus is worth analysing *before* any narrative work is attempted:

* How much of it is there, and where did it come from?
* What languages is it in, and how much survived cleaning?
* How long are the texts, and how much is missing?
* How much of it is duplicated or excluded, and for what reasons?
* What time span does it cover, and how comment-heavy is it?

Nothing here computes embeddings, clusters, sentiment, stance or narratives — by design. Inspection
answers "is the data sound?", not "what does it mean?" (PROMPT 16).

References: docs/ingestion.md §9
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Float, cast, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, aliased

from app.database.models import (
    Author,
    Community,
    Discussion,
    Source,
    TextPreparation,
)


@dataclass(frozen=True, slots=True)
class LengthStats:
    """Distribution of cleaned-text length, in characters and words."""

    minimum: int | None = None
    p50: int | None = None
    p90: int | None = None
    maximum: int | None = None
    mean_characters: float | None = None
    mean_words: float | None = None


@dataclass(frozen=True, slots=True)
class QualityStats:
    """How much of the corpus is analysable, and what stopped the rest."""

    prepared: int = 0
    usable: int = 0
    excluded: int = 0
    usable_share: float = 0.0
    duplicate_count: int = 0
    duplicate_share: float = 0.0
    exclusion_reasons: dict[str, int] = field(default_factory=dict)
    comments_per_post: float = 0.0
    posts_without_comments: int = 0


@dataclass(frozen=True, slots=True)
class DatasetReport:
    """A point-in-time description of an analysis dataset."""

    generated_at: datetime
    # volume
    discussion_count: int
    post_count: int
    comment_count: int
    source_count: int
    community_count: int
    author_count: int
    # content
    language_distribution: dict[str, int]
    content_lengths: LengthStats
    missing_values: dict[str, int]
    # provenance and shape
    time_range: tuple[datetime | None, datetime | None]
    top_communities: Sequence[tuple[str, int]]
    quality: QualityStats

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable view, with datetimes as ISO-8601 strings."""
        earliest, latest = self.time_range
        return {
            "generated_at": self.generated_at.isoformat(),
            "volume": {
                "discussions": self.discussion_count,
                "posts": self.post_count,
                "comments": self.comment_count,
                "sources": self.source_count,
                "communities": self.community_count,
                "authors": self.author_count,
            },
            "content": {
                "language_distribution": self.language_distribution,
                "lengths": {
                    "min_characters": self.content_lengths.minimum,
                    "p50_characters": self.content_lengths.p50,
                    "p90_characters": self.content_lengths.p90,
                    "max_characters": self.content_lengths.maximum,
                    "mean_characters": self.content_lengths.mean_characters,
                    "mean_words": self.content_lengths.mean_words,
                },
                "missing_values": self.missing_values,
            },
            "provenance": {
                "earliest_source_created_at": earliest.isoformat() if earliest else None,
                "latest_source_created_at": latest.isoformat() if latest else None,
                "top_communities": [
                    {"community": name, "discussions": count}
                    for name, count in self.top_communities
                ],
            },
            "quality": {
                "prepared": self.quality.prepared,
                "usable": self.quality.usable,
                "excluded": self.quality.excluded,
                "usable_share": self.quality.usable_share,
                "duplicate_count": self.quality.duplicate_count,
                "duplicate_share": self.quality.duplicate_share,
                "exclusion_reasons": self.quality.exclusion_reasons,
                "comments_per_post": self.quality.comments_per_post,
                "posts_without_comments": self.quality.posts_without_comments,
            },
        }


def _latest_preparation_subquery() -> Any:
    """One preparation row per discussion — the most recent one.

    A discussion can have several preparation rows (one per cleaning version). Reporting on all of
    them would double-count every re-prepared item, so the newest row per discussion is selected
    with a window function.
    """
    ranked = select(
        TextPreparation.discussion_id.label("discussion_id"),
        TextPreparation.language.label("language"),
        TextPreparation.is_usable.label("is_usable"),
        TextPreparation.exclusion_reason.label("exclusion_reason"),
        TextPreparation.character_count.label("character_count"),
        TextPreparation.word_count.label("word_count"),
        TextPreparation.content_hash.label("content_hash"),
        func.row_number()
        .over(
            partition_by=TextPreparation.discussion_id,
            order_by=(TextPreparation.created_at.desc(), TextPreparation.id.desc()),
        )
        .label("rank"),
    ).subquery()

    return select(ranked).where(ranked.c.rank == 1).subquery()


def _to_int(value: Any) -> int:
    """Coerce an aggregate result to `int`.

    SQLAlchemy types the values of an ad-hoc aggregate row as `Any`, so the conversion is made
    explicit once here rather than implied at every call site.
    """
    return int(value) if value is not None else 0


def _to_optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _to_optional_float(value: Any) -> float | None:
    return None if value is None else round(float(value), 1)


def _scalar_int(session: Session, statement: Any) -> int:
    return _to_int(session.execute(statement).scalar())


def inspect_dataset(session: Session, *, top_community_limit: int = 10) -> DatasetReport:
    """Build a report over the whole dataset.

    Read-only: it issues aggregates and no writes, so it is safe to run against a live database at
    any point in a pipeline.
    """
    latest = _latest_preparation_subquery()

    discussion_count = _scalar_int(session, select(func.count()).select_from(Discussion))
    post_count = _scalar_int(
        session, select(func.count()).select_from(Discussion).where(Discussion.kind == "post")
    )
    comment_count = _scalar_int(
        session, select(func.count()).select_from(Discussion).where(Discussion.kind == "comment")
    )

    language_distribution: dict[str, int] = {}
    for language, count in session.execute(
        select(latest.c.language, func.count().label("total"))
        .group_by(latest.c.language)
        .order_by(func.count().desc())
    ).all():
        language_distribution[str(language or "unknown")] = _to_int(count)

    prepared = _scalar_int(session, select(func.count()).select_from(latest))
    usable = _scalar_int(
        session, select(func.count()).select_from(latest).where(latest.c.is_usable.is_(True))
    )

    length_row = session.execute(
        select(
            func.min(latest.c.character_count).label("minimum"),
            func.percentile_cont(0.5).within_group(latest.c.character_count).label("p50"),
            func.percentile_cont(0.9).within_group(latest.c.character_count).label("p90"),
            func.max(latest.c.character_count).label("maximum"),
            func.avg(latest.c.character_count).cast(Float).label("mean_characters"),
            func.avg(latest.c.word_count).cast(Float).label("mean_words"),
        )
    ).one()

    lengths = LengthStats(
        minimum=_to_optional_int(length_row.minimum),
        p50=_to_optional_int(length_row.p50),
        p90=_to_optional_int(length_row.p90),
        maximum=_to_optional_int(length_row.maximum),
        mean_characters=_to_optional_float(length_row.mean_characters),
        mean_words=_to_optional_float(length_row.mean_words),
    )

    # "Missing" means a field a reader would expect to find empty for a reason worth knowing about.
    # A comment having no title is normal and is deliberately not counted.
    missing_values = {
        "no_author (deleted account)": _scalar_int(
            session,
            select(func.count()).select_from(Discussion).where(Discussion.author_id.is_(None)),
        ),
        "no_url": _scalar_int(
            session, select(func.count()).select_from(Discussion).where(Discussion.url.is_(None))
        ),
        "empty_body": _scalar_int(
            session,
            select(func.count())
            .select_from(Discussion)
            .where(func.length(func.btrim(Discussion.body)) == 0),
        ),
        "empty_raw_metadata": _scalar_int(
            session,
            select(func.count())
            .select_from(Discussion)
            .where(Discussion.raw_metadata == cast("{}", JSONB)),
        ),
        "not_prepared": discussion_count - prepared,
        "orphaned_comments": _scalar_int(
            session,
            select(func.count())
            .select_from(Discussion)
            .where(Discussion.kind == "comment", Discussion.parent_discussion_id.is_(None)),
        ),
    }

    earliest, latest_seen = session.execute(
        select(func.min(Discussion.source_created_at), func.max(Discussion.source_created_at))
    ).one()

    top_communities: list[tuple[str, int]] = [
        (str(name), _to_int(total))
        for name, total in session.execute(
            select(Community.name, func.count().label("total"))
            .join(Discussion, Discussion.community_id == Community.id)
            .group_by(Community.name)
            .order_by(func.count().desc(), Community.name)
            .limit(top_community_limit)
        ).all()
    ]

    reason_rows = session.execute(
        select(latest.c.exclusion_reason, func.count().label("total"))
        .where(latest.c.is_usable.is_(False))
        .group_by(latest.c.exclusion_reason)
        .order_by(func.count().desc())
    ).all()
    exclusion_reasons: dict[str, int] = {
        str(reason or "unspecified"): _to_int(total) for reason, total in reason_rows
    }
    duplicate_count = exclusion_reasons.get("duplicate_content", 0)
    excluded = prepared - usable

    comments_per_post = (comment_count / post_count) if post_count else 0.0
    # A correlated EXISTS needs its own alias for the child row, otherwise the inner query
    # captures the outer `discussions` table and compares a row to itself.
    child = aliased(Discussion)
    posts_without_comments = _scalar_int(
        session,
        select(func.count())
        .select_from(Discussion)
        .where(
            Discussion.kind == "post",
            ~select(child.id)
            .where(child.parent_discussion_id == Discussion.id, child.kind == "comment")
            .exists(),
        ),
    )

    return DatasetReport(
        generated_at=datetime.now(UTC),
        discussion_count=discussion_count,
        post_count=post_count,
        comment_count=comment_count,
        source_count=_scalar_int(session, select(func.count()).select_from(Source)),
        community_count=_scalar_int(session, select(func.count()).select_from(Community)),
        author_count=_scalar_int(session, select(func.count()).select_from(Author)),
        language_distribution=language_distribution,
        content_lengths=lengths,
        missing_values=missing_values,
        time_range=(earliest, latest_seen),
        top_communities=top_communities,
        quality=QualityStats(
            prepared=prepared,
            usable=usable,
            excluded=excluded,
            usable_share=round(usable / prepared, 4) if prepared else 0.0,
            duplicate_count=duplicate_count,
            duplicate_share=round(duplicate_count / prepared, 4) if prepared else 0.0,
            exclusion_reasons=exclusion_reasons,
            comments_per_post=round(comments_per_post, 2),
            posts_without_comments=posts_without_comments,
        ),
    )


# --- rendering ---------------------------------------------------------------------------


def _percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def render_markdown(report: DatasetReport) -> str:
    """Human-readable report, suitable for a commit or a review comment."""
    earliest, latest = report.time_range
    lines: list[str] = [
        "# Dataset inspection report",
        "",
        f"Generated: {report.generated_at.isoformat()}",
        "",
        "## Volume",
        "",
        "| Metric | Count |",
        "|---|---|",
        f"| Discussions | {report.discussion_count} |",
        f"| — posts | {report.post_count} |",
        f"| — comments | {report.comment_count} |",
        f"| Sources | {report.source_count} |",
        f"| Communities | {report.community_count} |",
        f"| Authors (pseudonymous) | {report.author_count} |",
        "",
        "## Time range",
        "",
        f"- Earliest source timestamp: `{earliest.isoformat() if earliest else 'n/a'}`",
        f"- Latest source timestamp: `{latest.isoformat() if latest else 'n/a'}`",
        "",
        "## Language distribution",
        "",
        "| Language | Items |",
        "|---|---|",
    ]

    if report.language_distribution:
        lines += [
            f"| {language} | {count} |" for language, count in report.language_distribution.items()
        ]
    else:
        lines.append("| _(nothing prepared yet)_ | 0 |")

    lines += [
        "",
        "`und` means the language was not determined — usually because the item was excluded",
        "before language detection ran, or because the text was too short to judge.",
    ]

    lengths = report.content_lengths
    lines += [
        "",
        "## Content length (cleaned text, characters)",
        "",
        "| Statistic | Value |",
        "|---|---|",
        f"| Minimum | {lengths.minimum if lengths.minimum is not None else 'n/a'} |",
        f"| Median | {lengths.p50 if lengths.p50 is not None else 'n/a'} |",
        f"| p90 | {lengths.p90 if lengths.p90 is not None else 'n/a'} |",
        f"| Maximum | {lengths.maximum if lengths.maximum is not None else 'n/a'} |",
        f"| Mean characters | "
        f"{lengths.mean_characters if lengths.mean_characters is not None else 'n/a'} |",
        f"| Mean words | {lengths.mean_words if lengths.mean_words is not None else 'n/a'} |",
        "",
        "## Missing values",
        "",
        "| Field | Discussions affected |",
        "|---|---|",
    ]
    lines += [f"| {name} | {count} |" for name, count in report.missing_values.items()]

    quality = report.quality
    lines += [
        "",
        "## Quality",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Prepared | {quality.prepared} |",
        f"| Usable | {quality.usable} ({_percent(quality.usable_share)}) |",
        f"| Excluded | {quality.excluded} |",
        f"| Duplicates | {quality.duplicate_count} ({_percent(quality.duplicate_share)}) |",
        f"| Comments per post | {quality.comments_per_post} |",
        f"| Posts with no comments | {quality.posts_without_comments} |",
        "",
        "### Exclusions by reason",
        "",
        "| Reason | Items |",
        "|---|---|",
    ]
    if quality.exclusion_reasons:
        lines += [f"| {reason} | {count} |" for reason, count in quality.exclusion_reasons.items()]
    else:
        lines.append("| _(none)_ | 0 |")

    lines += [
        "",
        "## Top communities",
        "",
        "| Community | Discussions |",
        "|---|---|",
    ]
    if report.top_communities:
        lines += [f"| {name} | {count} |" for name, count in report.top_communities]
    else:
        lines.append("| _(none)_ | 0 |")

    lines.append("")
    return "\n".join(lines)


__all__ = [
    "DatasetReport",
    "LengthStats",
    "QualityStats",
    "inspect_dataset",
    "render_markdown",
]
