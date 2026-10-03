"""Persisting a collection run: idempotency, thread structure, and honest accounting.

These tests use the recorded fixture corpus against a real PostgreSQL instance, because the
properties being checked — upsert-on-conflict, the self-referencing foreign key, CHECK constraints —
are database behaviours that a mock would not exercise.
"""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update

from app.database.models import (
    AnalysisRun,
    Author,
    Community,
    Discussion,
    RunStage,
    Source,
    TextPreparation,
)
from app.database.models.enums import ExclusionReason
from app.ingestion.base import SourceQuery
from app.ingestion.reddit.recorded import RecordedRedditAdapter
from app.services.collection import CollectionError, CollectionRequest, collect_discussions
from app.services.topics import ensure_topic

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "reddit"
COLLECTED_AT = datetime(2024, 5, 1, 12, 0, tzinfo=UTC)

TOTAL_ITEMS = 26
TOTAL_POSTS = 6
USABLE_ITEMS = 12
DUPLICATE_ITEMS = 2

ALL_EXCLUSION_REASONS = {reason.value for reason in ExclusionReason}


def collect(session, *, topic_name: str = "AI regulation"):
    """Run one collection over the recorded corpus."""
    adapter = RecordedRedditAdapter(FIXTURES, clock=lambda: COLLECTED_AT)
    query = SourceQuery(communities=("technology", "programming"), limit=50)
    topic = ensure_topic(session, topic_name, query_terms=("ai audit",))
    return collect_discussions(
        session,
        adapter,
        CollectionRequest(topic_id=topic.id, query=query),
        clock=lambda: COLLECTED_AT,
    )


def count(session, model) -> int:
    return int(session.execute(select(func.count()).select_from(model)).scalar() or 0)


# --- storage ---------------------------------------------------------------------------------


def test_posts_and_comments_are_stored(session) -> None:
    report = collect(session)

    assert report.stored_total == TOTAL_ITEMS
    assert report.discussions_inserted == TOTAL_ITEMS
    assert report.discussions_refreshed == 0
    assert count(session, Discussion) == TOTAL_ITEMS

    posts = session.execute(
        select(func.count()).select_from(Discussion).where(Discussion.kind == "post")
    ).scalar()
    assert posts == TOTAL_POSTS


def test_source_community_and_author_rows_are_created_once(session) -> None:
    collect(session)

    assert count(session, Source) == 1
    assert session.execute(select(Source.key)).scalar() == "reddit"
    assert count(session, Community) == 2
    # Distinct pseudonymous handles only: `[deleted]` must not become an author.
    assert count(session, Author) == 23


def test_comments_are_linked_to_their_parents(session) -> None:
    collect(session)

    post = session.execute(
        select(Discussion).where(Discussion.external_id == "t3_a1b2c3")
    ).scalar_one()
    comment = session.execute(
        select(Discussion).where(Discussion.external_id == "t1_c001")
    ).scalar_one()
    reply = session.execute(
        select(Discussion).where(Discussion.external_id == "t1_c002")
    ).scalar_one()

    assert comment.parent_discussion_id == post.id
    assert reply.parent_discussion_id == comment.id


def test_a_comment_whose_parent_was_not_collected_keeps_a_null_parent(session) -> None:
    """Thread structure is source truth: an uncollected parent must not be invented."""
    collect(session)

    orphan = session.execute(
        select(Discussion).where(Discussion.external_id == "t1_c014")
    ).scalar_one()

    assert orphan.parent_discussion_id is None


def test_a_deleted_comment_is_stored_as_source_truth(session) -> None:
    collect(session)

    deleted = session.execute(
        select(Discussion).where(Discussion.external_id == "t1_c004")
    ).scalar_one()

    assert deleted.body == "[deleted]"
    assert deleted.author_id is None


def test_a_removed_post_keeps_its_platform_signal_in_metadata(session) -> None:
    collect(session)

    post = session.execute(
        select(Discussion).where(Discussion.external_id == "t3_g7h8i9")
    ).scalar_one()

    assert post.raw_metadata["removed_by_category"] == "moderator"
    assert post.raw_metadata["stickied"] is True


# --- idempotency -----------------------------------------------------------------------------


def test_recollecting_refreshes_instead_of_duplicating(session) -> None:
    first = collect(session)
    second = collect(session)

    assert first.discussions_inserted == TOTAL_ITEMS
    assert second.discussions_inserted == 0
    assert second.discussions_refreshed == TOTAL_ITEMS
    assert count(session, Discussion) == TOTAL_ITEMS
    assert count(session, Source) == 1
    assert count(session, Community) == 2
    assert count(session, Author) == 23


def test_recollecting_never_rewrites_what_a_person_wrote(session) -> None:
    """Only NarraX-owned retrieval metadata may be refreshed by a later run."""
    collect(session)
    session.execute(
        update(Discussion)
        .where(Discussion.external_id == "t1_c001")
        .values(body="A correction that a later collection must not overwrite.")
    )
    session.flush()

    collect(session)

    comment = session.execute(
        select(Discussion).where(Discussion.external_id == "t1_c001")
    ).scalar_one()
    assert comment.body == "A correction that a later collection must not overwrite."


def test_recollecting_does_not_make_items_duplicates_of_themselves(session) -> None:
    collect(session)
    second = collect(session)

    assert second.duplicates == DUPLICATE_ITEMS
    assert second.exclusion_reasons["duplicate_content"] == DUPLICATE_ITEMS
    assert count(session, TextPreparation) == TOTAL_ITEMS


# --- text preparation ------------------------------------------------------------------------


def test_every_item_is_prepared_exactly_once(session) -> None:
    collect(session)

    assert count(session, TextPreparation) == TOTAL_ITEMS
    leftovers = session.execute(
        select(func.count())
        .select_from(TextPreparation)
        .where(TextPreparation.pipeline_version == "")
    ).scalar()
    assert leftovers == 0


def test_the_usable_decision_matches_the_exclusion_reason(session) -> None:
    """The CHECK constraint enforces this; the test proves the pipeline never relies on it."""
    collect(session)

    usable = session.execute(
        select(func.count()).select_from(TextPreparation).where(TextPreparation.is_usable.is_(True))
    ).scalar()
    excluded = session.execute(
        select(func.count())
        .select_from(TextPreparation)
        .where(TextPreparation.is_usable.is_(False))
    ).scalar()

    assert usable == USABLE_ITEMS
    assert excluded == TOTAL_ITEMS - USABLE_ITEMS
    reasons = set(session.execute(select(TextPreparation.exclusion_reason).distinct()).scalars())
    assert None in reasons, "usable rows must have no exclusion reason"


def test_every_exclusion_reason_is_exercised_by_the_corpus(session) -> None:
    """The fixture corpus is the sample dataset, so it must cover the whole vocabulary."""
    collect(session)

    reasons = {
        reason
        for reason in session.execute(select(TextPreparation.exclusion_reason).distinct()).scalars()
        if reason is not None
    }

    assert reasons == ALL_EXCLUSION_REASONS
    # And the vocabulary is closed: nothing outside the enum can be stored.
    assert reasons <= {member.value for member in ExclusionReason}


def test_a_removed_post_is_analysable_from_its_title(session) -> None:
    """Reddit does not remove titles, so a removed body is not a lost contribution."""
    collect(session)

    post = session.execute(
        select(Discussion).where(Discussion.external_id == "t3_g7h8i9")
    ).scalar_one()
    preparation = session.execute(
        select(TextPreparation).where(TextPreparation.discussion_id == post.id)
    ).scalar_one()

    assert preparation.is_usable is True
    assert "Megathread" in preparation.cleaned_text
    assert "[removed]" not in preparation.cleaned_text


def test_duplicate_text_is_flagged_with_a_reference(session) -> None:
    collect(session)

    duplicates = (
        session.execute(
            select(TextPreparation).where(TextPreparation.exclusion_reason == "duplicate_content")
        )
        .scalars()
        .all()
    )

    assert len(duplicates) == DUPLICATE_ITEMS
    assert all("duplicate of an earlier item" in (row.exclusion_detail or "") for row in duplicates)
    assert all(row.content_hash for row in duplicates)


def test_cleaning_metrics_are_persisted(session) -> None:
    collect(session)

    post = session.execute(
        select(Discussion).where(Discussion.external_id == "t3_a1b2c3")
    ).scalar_one()
    preparation = session.execute(
        select(TextPreparation).where(TextPreparation.discussion_id == post.id)
    ).scalar_one()

    assert preparation.language == "en"
    assert preparation.language_confidence is not None
    assert preparation.character_count == len(preparation.cleaned_text)
    assert preparation.word_count > 0
    assert preparation.url_count >= 1
    assert preparation.formatting_artifact_count >= 1


# --- run accounting --------------------------------------------------------------------------


def test_the_run_and_its_stages_are_recorded(session) -> None:
    report = collect(session)

    run = session.get(AnalysisRun, report.run_id)
    assert run is not None
    assert run.status == "succeeded"
    assert run.corpus_size == USABLE_ITEMS
    assert run.finished_at is not None
    assert run.config["adapter"] == "reddit"
    assert run.config["cleaning"]["pipeline_version"]

    stages = (
        session.execute(select(RunStage).where(RunStage.analysis_run_id == report.run_id))
        .scalars()
        .all()
    )
    by_name = {stage.stage: stage for stage in stages}
    assert set(by_name) == {"ingest", "normalize"}
    assert by_name["ingest"].items_out == TOTAL_ITEMS
    assert by_name["normalize"].items_out == USABLE_ITEMS
    assert by_name["normalize"].items_dropped == TOTAL_ITEMS - USABLE_ITEMS
    assert by_name["normalize"].metrics["exclusion_reasons"]["duplicate_content"] == DUPLICATE_ITEMS


def test_each_run_is_recorded_separately(session) -> None:
    first = collect(session)
    second = collect(session)

    assert first.run_id != second.run_id
    assert count(session, AnalysisRun) == 2
    assert count(session, RunStage) == 4


def test_adapter_counters_are_recorded_on_the_run(session) -> None:
    report = collect(session)

    assert report.adapter_stats["posts_seen"] == TOTAL_POSTS
    assert report.adapter_stats["comments_seen"] == TOTAL_ITEMS - TOTAL_POSTS


def test_collection_requires_an_existing_topic(session) -> None:
    adapter = RecordedRedditAdapter(FIXTURES)
    query = SourceQuery(communities=("technology",), limit=5)

    with pytest.raises(CollectionError, match="does not exist"):
        collect_discussions(
            session,
            adapter,
            CollectionRequest(topic_id=uuid4(), query=query),
        )


def test_a_known_topic_collects_normally(session) -> None:
    """The guard above must reject unknown topics without blocking real ones."""
    topic = ensure_topic(session, "A topic that exists")
    adapter = RecordedRedditAdapter(FIXTURES, clock=lambda: COLLECTED_AT)

    report = collect_discussions(
        session,
        adapter,
        CollectionRequest(
            topic_id=topic.id, query=SourceQuery(communities=("technology",), limit=50)
        ),
    )

    assert report.prepared > 0


def test_the_second_run_is_labelled_as_such(session) -> None:
    collect(session)
    report = collect(session)

    run = session.get(AnalysisRun, report.run_id)
    assert run is not None
    assert run.corpus_size == USABLE_ITEMS  # the corpus is unchanged by re-collection
