"""Collection: from a source adapter to stored, prepared Layer 1 data.

This is the use-case that owns a whole collection run. It is the only place that composes
ingestion with the database, and it is responsible for the properties that make the pipeline
re-runnable (docs/data-flow.md §6):

* **Idempotency** — discussions are upserted on the natural key `(source, external_id)`, and an
  existing row's *authored* fields are never rewritten. Only NarraX-owned retrieval metadata
  (`collected_at`, `source_score`, `raw_metadata`) is refreshed.
* **Deduplication in two places** — the platform's own identifier (via the unique constraint) and
  the cleaned text's hash (via `text_preparation`), because the same argument is often pasted
  verbatim into several threads.
* **Explicit accounting** — the run records how many items were seen, stored, refreshed, and
  excluded, and *why*. Corpus size must always be explainable.
* **Partial progress is preserved** — items are flushed as they arrive, so an interrupted run
  leaves valid Layer 1 data and a `partial` run status rather than nothing.

References: docs/ingestion.md §8 · docs/data-flow.md §3 (S1, S2)
"""

import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, literal_column, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.database.models import (
    AnalysisRun,
    Author,
    Community,
    Discussion,
    RunStage,
    Source,
    TextPreparation,
    Topic,
)
from app.database.models.enums import ExclusionReason, RunStatus, Stage, StageStatus
from app.ingestion.base import CollectionStats, SourceAdapter, SourceQuery
from app.ingestion.cleaning import (
    DEFAULT_CLEANING_RULES,
    CleaningResult,
    CleaningRules,
    DuplicateCandidate,
    clean_text,
    find_duplicate_indices,
)
from app.ingestion.language import DEFAULT_LANGUAGE_DETECTOR, LanguageDetector
from app.ingestion.normalized import NormalizedDiscussion

logger = logging.getLogger(__name__)


class CollectionError(Exception):
    """The collection could not be completed."""


@dataclass(frozen=True, slots=True)
class CollectionRequest:
    """What to collect, and how to treat it."""

    topic_id: UUID
    query: SourceQuery
    collect_comments: bool = True
    comment_limit: int = 100
    cleaning_rules: CleaningRules = DEFAULT_CLEANING_RULES


@dataclass(slots=True)
class CollectionReport:
    """What a collection run did. Every number here is traceable to a stage record."""

    run_id: UUID
    posts_seen: int = 0
    discussions_inserted: int = 0
    discussions_refreshed: int = 0
    comments_seen: int = 0
    prepared: int = 0
    usable: int = 0
    excluded: int = 0
    duplicates: int = 0
    exclusion_reasons: dict[str, int] = field(default_factory=dict)
    adapter_stats: dict[str, int] = field(default_factory=dict)

    @property
    def stored_total(self) -> int:
        return self.discussions_inserted + self.discussions_refreshed

    @property
    def usable_share(self) -> float:
        return self.usable / self.prepared if self.prepared else 0.0


def _utcnow() -> datetime:
    return datetime.now(UTC)


# --- row helpers ------------------------------------------------------------------------


def _ensure_source(session: Session, key: str) -> UUID:
    """Upsert the platform row and return its id."""
    statement = (
        pg_insert(Source)
        .values(key=key, name=key.replace("_", " ").title())
        # A no-op update is used rather than DO NOTHING because DO NOTHING returns no row, and the
        # id is what the caller needs.
        .on_conflict_do_update(index_elements=["key"], set_={"updated_at": func.now()})
        .returning(Source.id)
    )
    return session.execute(statement).scalar_one()


def _ensure_community(
    session: Session, source_id: UUID, external_id: str, name: str, cache: dict[str, UUID]
) -> UUID:
    """Upsert a community, caching ids so a run makes one query per distinct community."""
    cached = cache.get(external_id)
    if cached is not None:
        return cached

    statement = (
        pg_insert(Community)
        .values(source_id=source_id, external_id=external_id, name=name)
        # A community can be renamed; refreshing the display name is safe because it is not
        # authored content.
        .on_conflict_do_update(
            index_elements=["source_id", "external_id"],
            set_={"name": name, "updated_at": func.now()},
        )
        .returning(Community.id)
    )
    community_id = session.execute(statement).scalar_one()
    cache[external_id] = community_id
    return community_id


def _ensure_author(
    session: Session, source_id: UUID, external_id: str, cache: dict[str, UUID]
) -> UUID:
    """Upsert a pseudonymous author handle, caching ids for the run's duration."""
    cached = cache.get(external_id)
    if cached is not None:
        return cached

    statement = (
        pg_insert(Author)
        .values(source_id=source_id, external_id=external_id)
        .on_conflict_do_update(
            index_elements=["source_id", "external_id"], set_={"updated_at": func.now()}
        )
        .returning(Author.id)
    )
    author_id = session.execute(statement).scalar_one()
    cache[external_id] = author_id
    return author_id


def _upsert_discussion(session: Session, values: dict[str, Any]) -> tuple[UUID, bool]:
    """Insert or refresh one discussion.

    Returns `(id, inserted)`. The authored columns — `title`, `body`, `source_created_at`,
    `author_id`, `kind`, `parent_discussion_id` — are deliberately **absent** from the update set:
    re-collecting an item must never rewrite what a person wrote. Only retrieval metadata is
    refreshed.

    `xmax = 0` is PostgreSQL's own signal for "this row was inserted, not updated"; using it avoids
    a second round trip to find out which happened.
    """
    statement: Any = (
        pg_insert(Discussion)
        .values(**values)
        .on_conflict_do_update(
            index_elements=["source_id", "external_id"],
            set_={
                "collected_at": values["collected_at"],
                "source_score": values["source_score"],
                "raw_metadata": values["raw_metadata"],
                "updated_at": func.now(),
            },
        )
        .returning(Discussion.id, literal_column("(xmax = 0)").label("inserted"))
    )
    row = session.execute(statement).one()
    return row.id, bool(row.inserted)


def _discussion_values(
    item: NormalizedDiscussion,
    *,
    source_id: UUID,
    community_id: UUID,
    author_id: UUID | None,
    parent_id: UUID | None,
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "community_id": community_id,
        "author_id": author_id,
        "parent_discussion_id": parent_id,
        "external_id": item.external_id,
        "kind": item.kind.value,
        "title": item.title,
        "body": item.body,
        "url": item.url,
        "source_score": item.engagement.score,
        "source_created_at": item.source_created_at,
        "collected_at": item.collected_at,
        "raw_metadata": item.metadata,
    }


# --- preparation helpers -----------------------------------------------------------------


def _existing_content_hashes(
    session: Session, pipeline_version: str, *, current_ids: set[UUID]
) -> set[str]:
    """Hashes already recorded for this cleaning version, excluding this run's own discussions.

    Excluding them matters: re-collecting an item that a previous run already prepared must not
    make it look like a duplicate of itself.
    """
    rows = session.execute(
        select(TextPreparation.content_hash, TextPreparation.discussion_id).where(
            TextPreparation.pipeline_version == pipeline_version,
            TextPreparation.content_hash != "",
        )
    ).all()
    return {
        content_hash for content_hash, discussion_id in rows if discussion_id not in current_ids
    }


def _persist_preparation(
    session: Session, discussion_id: UUID, result: CleaningResult, pipeline_version: str
) -> None:
    values: dict[str, Any] = {
        "discussion_id": discussion_id,
        "pipeline_version": pipeline_version,
        "cleaned_text": result.cleaned_text,
        "content_hash": result.content_hash,
        "language": result.language,
        "language_confidence": result.language_confidence,
        "script": result.script,
        "character_count": result.character_count,
        "word_count": result.word_count,
        "url_count": result.url_count,
        "formatting_artifact_count": result.formatting_artifact_count,
        "is_usable": result.is_usable,
        "exclusion_reason": result.reason.value if result.reason else None,
        "exclusion_detail": result.detail,
    }
    statement = (
        pg_insert(TextPreparation)
        .values(**values)
        .on_conflict_do_update(
            index_elements=["discussion_id", "pipeline_version"],
            set_={
                key: value
                for key, value in values.items()
                if key not in {"discussion_id", "pipeline_version"}
            },
        )
    )
    session.execute(statement)


# --- run bookkeeping ---------------------------------------------------------------------


def _create_run(
    session: Session, topic: Topic, request: CollectionRequest, adapter_key: str
) -> AnalysisRun:
    rules = request.cleaning_rules
    query = request.query
    run = AnalysisRun(
        topic_id=topic.id,
        status=RunStatus.RUNNING.value,
        window_start=query.since,
        window_end=query.until,
        started_at=_utcnow(),
        config={
            "adapter": adapter_key,
            "query": {
                "terms": list(query.terms),
                "communities": list(query.communities),
                "since": query.since.isoformat() if query.since else None,
                "until": query.until.isoformat() if query.until else None,
                "limit": query.limit,
                "sort": query.sort,
                "time_filter": query.time_filter,
                "include_comments": query.include_comments,
            },
            "cleaning": {"pipeline_version": rules.version(), "rules": asdict(rules)},
        },
    )
    session.add(run)
    session.flush()
    return run


def _record_stage(
    session: Session,
    run: AnalysisRun,
    stage: Stage,
    *,
    status: StageStatus,
    items_in: int | None = None,
    items_out: int | None = None,
    items_dropped: int | None = None,
    metrics: dict[str, Any] | None = None,
) -> None:
    session.add(
        RunStage(
            analysis_run_id=run.id,
            stage=stage.value,
            status=status.value,
            items_in=items_in,
            items_out=items_out,
            items_dropped=items_dropped,
            metrics=metrics or {},
            started_at=run.started_at,
            finished_at=_utcnow() if status is not StageStatus.RUNNING else None,
        )
    )


# --- the use-case ------------------------------------------------------------------------


def collect_discussions(
    session: Session,
    adapter: SourceAdapter,
    request: CollectionRequest,
    *,
    clock: Callable[[], datetime] = _utcnow,
    detector: LanguageDetector = DEFAULT_LANGUAGE_DETECTOR,
) -> CollectionReport:
    """Collect a topic's discussions, store them, clean them, and report what happened.

    The caller owns the transaction: this function flushes but never commits, so a caller can
    commit only once every stage has succeeded — or inspect partial progress after a failure.
    """
    topic = session.get(Topic, request.topic_id)
    if topic is None:
        raise CollectionError(f"topic {request.topic_id} does not exist")

    source_id = _ensure_source(session, adapter.key)
    run = _create_run(session, topic, request, adapter.key)

    community_cache: dict[str, UUID] = {}
    author_cache: dict[str, UUID] = {}
    for community in request.query.communities:
        _ensure_community(session, source_id, community, community, community_cache)

    # Identity of every item stored in this run, so comments can be linked to their parents and
    # duplicates can be judged against the rest of the corpus.
    stored_ids: dict[str, UUID] = {}
    collected: list[tuple[NormalizedDiscussion, UUID]] = []
    inserted_count = 0
    refreshed_count = 0

    def store(item: NormalizedDiscussion) -> UUID:
        nonlocal inserted_count, refreshed_count
        community_id = _ensure_community(
            session, source_id, item.community_external_id, item.community_name, community_cache
        )
        author_id = (
            _ensure_author(session, source_id, item.author_external_id, author_cache)
            if item.author_external_id
            else None
        )
        # The adapter yields comments parents-first, so any parent inside this run is already
        # stored. A parent that is absent from `stored_ids` was never collected, and the row keeps a
        # NULL parent rather than being reattached to the post: the thread structure is source
        # truth, and inventing a parent would misstate it. Such rows are counted in the dataset
        # report as orphaned comments.
        parent_id = stored_ids.get(item.parent_external_id) if item.parent_external_id else None

        discussion_id, inserted = _upsert_discussion(
            session,
            _discussion_values(
                item,
                source_id=source_id,
                community_id=community_id,
                author_id=author_id,
                parent_id=parent_id,
            ),
        )
        stored_ids[item.external_id] = discussion_id
        collected.append((item, discussion_id))
        if inserted:
            inserted_count += 1
        else:
            refreshed_count += 1
        return discussion_id

    try:
        for post in adapter.search_discussions(request.query):
            store(post)
            if request.collect_comments and request.query.include_comments and post.is_post:
                for comment in adapter.fetch_comments(post, limit=request.comment_limit):
                    store(comment)
    except Exception:
        # Partial progress is kept and labelled, rather than discarded: the collected discussions
        # are valid Layer 1 data even though the run did not finish.
        run.status = RunStatus.PARTIAL.value
        run.finished_at = _utcnow()
        _record_stage(
            session,
            run,
            Stage.INGEST,
            status=StageStatus.FAILED,
            items_in=adapter.stats.posts_seen + adapter.stats.comments_seen,
            items_out=len(collected),
            items_dropped=adapter.stats.skipped_total,
            metrics=adapter.stats.as_dict(),
        )
        raise

    rules = request.cleaning_rules
    pipeline_version = rules.version()

    # Clean everything, then judge duplicates across the whole run at once: duplicate detection is
    # inherently a corpus-level question, so it cannot be answered item by item.
    results: list[CleaningResult] = []
    for item, _ in collected:
        text_value, content_state = item.analysis_input()
        results.append(
            clean_text(
                text_value,
                content_state=content_state,
                rules=rules,
                detector=detector,
            )
        )

    candidates = [
        DuplicateCandidate(
            index=index,
            content_hash=result.content_hash,
            source_created_at=item.source_created_at,
            external_id=item.external_id,
        )
        for index, ((item, _), result) in enumerate(zip(collected, results, strict=True))
    ]
    duplicates = find_duplicate_indices(
        candidates,
        seen_hashes=_existing_content_hashes(
            session, pipeline_version, current_ids={discussion_id for _, discussion_id in collected}
        ),
    )
    for index, content_hash in duplicates.items():
        original = results[index]
        results[index] = replace(
            original,
            is_usable=False,
            reason=ExclusionReason.DUPLICATE_CONTENT,
            detail=f"duplicate of an earlier item (hash {content_hash[:12]})",
        )

    for (_, discussion_id), result in zip(collected, results, strict=True):
        _persist_preparation(session, discussion_id, result, pipeline_version)

    reason_counts: dict[str, int] = {}
    for result in results:
        if result.reason is not None:
            reason_counts[result.reason.value] = reason_counts.get(result.reason.value, 0) + 1

    usable = sum(1 for result in results if result.is_usable)

    stats: CollectionStats = adapter.stats
    _record_stage(
        session,
        run,
        Stage.INGEST,
        status=StageStatus.SUCCEEDED,
        items_in=stats.posts_seen + stats.comments_seen,
        items_out=len(collected),
        items_dropped=stats.skipped_total,
        metrics=stats.as_dict(),
    )
    _record_stage(
        session,
        run,
        Stage.NORMALIZE,
        status=StageStatus.SUCCEEDED,
        items_in=len(results),
        items_out=usable,
        items_dropped=len(results) - usable,
        metrics={
            "pipeline_version": pipeline_version,
            "duplicates": len(duplicates),
            "exclusion_reasons": reason_counts,
        },
    )

    run.status = RunStatus.SUCCEEDED.value
    run.finished_at = _utcnow()
    run.corpus_size = usable

    session.flush()

    logger.info(
        "collected topic=%s run=%s stored=%d usable=%d excluded=%d",
        topic.id,
        run.id,
        len(collected),
        usable,
        len(results) - usable,
    )

    return CollectionReport(
        run_id=run.id,
        posts_seen=stats.posts_seen,
        discussions_inserted=inserted_count,
        discussions_refreshed=refreshed_count,
        comments_seen=stats.comments_seen,
        prepared=len(results),
        usable=usable,
        excluded=len(results) - usable,
        duplicates=len(duplicates),
        exclusion_reasons=reason_counts,
        adapter_stats=stats.as_dict(),
    )
