"""The dataset inspection report (PROMPT 16).

Inspection must describe the corpus without changing it, and must answer the questions that decide
whether analysis is worth attempting: how much is there, in what language, how long, how much is
missing, how much is duplicated or excluded, over what period, and from where.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select

from app.database.models import Discussion, TextPreparation
from app.ingestion.base import SourceQuery
from app.ingestion.reddit.recorded import RecordedRedditAdapter
from app.services.collection import CollectionRequest, collect_discussions
from app.services.inspection import inspect_dataset, render_markdown
from app.services.topics import ensure_topic

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "reddit"
COLLECTED_AT = datetime(2024, 5, 1, 12, 0, tzinfo=UTC)

TOTAL_ITEMS = 26
TOTAL_POSTS = 6
USABLE_ITEMS = 12
DUPLICATE_ITEMS = 2
TOTAL_AUTHORS = 23


def collect(session) -> None:
    """Ingest the recorded corpus into the test database."""
    adapter = RecordedRedditAdapter(FIXTURES, clock=lambda: COLLECTED_AT)
    topic = ensure_topic(session, "AI regulation", query_terms=("ai audit",))
    collect_discussions(
        session,
        adapter,
        CollectionRequest(
            topic_id=topic.id,
            query=SourceQuery(communities=("technology", "programming"), limit=50),
        ),
        clock=lambda: COLLECTED_AT,
    )


def test_an_empty_dataset_reports_zeroes_without_failing(session) -> None:
    """The report must be safe to run before anything has been collected."""
    report = inspect_dataset(session)

    assert report.discussion_count == 0
    assert report.language_distribution == {}
    assert report.content_lengths.p50 is None
    assert report.top_communities == []
    assert report.quality.usable_share == 0.0
    assert report.time_range == (None, None)


def test_volume_counts_match_the_corpus(session) -> None:
    collect(session)

    report = inspect_dataset(session)

    assert report.discussion_count == TOTAL_ITEMS
    assert report.post_count == TOTAL_POSTS
    assert report.comment_count == TOTAL_ITEMS - TOTAL_POSTS
    assert report.source_count == 1
    assert report.community_count == 2
    assert report.author_count == TOTAL_AUTHORS


def test_language_distribution_is_reported(session) -> None:
    collect(session)

    report = inspect_dataset(session)

    assert report.language_distribution.get("en", 0) > 0
    # `und` covers items excluded before language detection, plus text too short to judge.
    assert report.language_distribution.get("und", 0) > 0
    assert sum(report.language_distribution.values()) == TOTAL_ITEMS


def test_exclusions_are_reported_by_reason(session) -> None:
    collect(session)

    quality = inspect_dataset(session).quality

    assert quality.prepared == TOTAL_ITEMS
    assert quality.usable == USABLE_ITEMS
    assert quality.excluded == TOTAL_ITEMS - USABLE_ITEMS
    assert quality.duplicate_count == DUPLICATE_ITEMS
    assert quality.usable_share == round(USABLE_ITEMS / TOTAL_ITEMS, 4)
    assert set(quality.exclusion_reasons) == {
        "deleted_content",
        "removed_content",
        "empty_content",
        "too_short",
        "excessive_noise",
        "repetitive_content",
        "link_dominated",
        "duplicate_content",
        "non_english",
        "low_information",
        "missing_source_text",
    }
    assert sum(quality.exclusion_reasons.values()) == quality.excluded


def test_time_range_covers_the_corpus(session) -> None:
    collect(session)

    earliest, latest = inspect_dataset(session).time_range

    assert earliest == datetime(2024, 1, 15, 12, 0, tzinfo=UTC)
    assert latest == datetime(2024, 4, 2, 14, 20, tzinfo=UTC)


def test_top_communities_are_ordered_by_volume(session) -> None:
    collect(session)

    top = inspect_dataset(session).top_communities

    assert top[0] == ("technology", 23)
    assert top[1] == ("programming", 3)


def test_the_community_limit_is_respected(session) -> None:
    collect(session)

    assert len(inspect_dataset(session, top_community_limit=1).top_communities) == 1


def test_length_statistics_are_computed_over_cleaned_text(session) -> None:
    collect(session)

    lengths = inspect_dataset(session).content_lengths

    assert lengths.minimum == 0, "excluded items have no cleaned text"
    assert lengths.p50 is not None and lengths.p50 > 0
    assert lengths.p90 is not None and lengths.maximum is not None
    assert lengths.p90 <= lengths.maximum
    assert lengths.mean_words is not None and lengths.mean_words > 0


def test_missing_values_are_counted(session) -> None:
    collect(session)

    missing = inspect_dataset(session).missing_values

    # Two items have no author: a deleted comment and a deleted post.
    assert missing["no_author (deleted account)"] == 2
    # Two have an empty body: an explicitly empty comment and one with no body field at all.
    assert missing["empty_body"] == 2
    assert missing["not_prepared"] == 0
    assert missing["no_url"] == 0
    # The orphan comment's parent was never collected.
    assert missing["orphaned_comments"] == 1


def test_coverage_is_reported(session) -> None:
    collect(session)

    quality = inspect_dataset(session).quality

    assert quality.comments_per_post == round(20 / 6, 2)
    assert quality.posts_without_comments == 3


def test_the_newest_preparation_row_wins(session) -> None:
    """A re-prepared item must be counted once, at its latest state."""
    collect(session)
    discussion = session.execute(
        select(Discussion).where(Discussion.external_id == "t1_c001")
    ).scalar_one()

    session.add(
        TextPreparation(
            discussion_id=discussion.id,
            pipeline_version="future-rules",
            cleaned_text="Angenommen, die Schwelle ist zu niedrig angesetzt worden.",
            content_hash="hash-for-the-newer-preparation",
            language="de",
            language_confidence=0.8,
            script="latin",
            character_count=56,
            word_count=9,
            is_usable=True,
            created_at=datetime.now(UTC) + timedelta(days=1),
        )
    )
    session.flush()

    report = inspect_dataset(session)

    # Still one row per discussion in the report, even though two exist in the table.
    assert sum(report.language_distribution.values()) == TOTAL_ITEMS
    assert report.language_distribution.get("de") == 1


def test_inspection_does_not_modify_the_dataset(session) -> None:
    collect(session)
    before = (
        session.execute(select(func.count()).select_from(Discussion)).scalar(),
        session.execute(select(func.count()).select_from(TextPreparation)).scalar(),
    )

    inspect_dataset(session)

    after = (
        session.execute(select(func.count()).select_from(Discussion)).scalar(),
        session.execute(select(func.count()).select_from(TextPreparation)).scalar(),
    )
    assert before == after


def test_markdown_rendering_contains_every_section(session) -> None:
    collect(session)

    rendered = render_markdown(inspect_dataset(session))

    for heading in (
        "# Dataset inspection report",
        "## Volume",
        "## Time range",
        "## Language distribution",
        "## Content length",
        "## Missing values",
        "## Quality",
        "### Exclusions by reason",
        "## Top communities",
    ):
        assert heading in rendered
    assert f"| Discussions | {TOTAL_ITEMS} |" in rendered
    assert "non_english" in rendered


def test_rendering_an_empty_dataset_does_not_crash(session) -> None:
    rendered = render_markdown(inspect_dataset(session))

    assert "_(nothing prepared yet)_" in rendered
    assert "| Minimum | n/a |" in rendered


def test_the_report_serializes_to_json_safe_structures(session) -> None:
    import json

    collect(session)

    payload = inspect_dataset(session).to_dict()

    # Round-tripping proves datetimes were converted rather than left as objects.
    assert json.loads(json.dumps(payload)) == payload
    assert payload["volume"]["discussions"] == TOTAL_ITEMS
    assert payload["quality"]["duplicate_count"] == DUPLICATE_ITEMS
    assert payload["provenance"]["earliest_source_created_at"].startswith("2024-01-15")
    assert payload["provenance"]["top_communities"][0]["community"] == "technology"
