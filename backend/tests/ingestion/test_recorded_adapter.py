"""The recorded-payload adapter.

It exists so the pipeline can be exercised without credentials or network, which only holds up if it
goes through the same normalization and traversal code as live collection. These tests use the
committed fixture corpus that also generates the sample dataset report.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.ingestion.base import SourceConfigurationError, SourceQuery, SourceResponseError
from app.ingestion.normalized import ContentState, DiscussionKind
from app.ingestion.reddit.recorded import RecordedRedditAdapter

ALL_POSTS = 6
TECHNOLOGY_POSTS = 5


@pytest.fixture
def adapter(fixture_dir: Path, frozen_now: datetime) -> RecordedRedditAdapter:
    return RecordedRedditAdapter(fixture_dir, clock=lambda: frozen_now)


def test_a_missing_directory_is_a_configuration_error(scratch_dir: Path) -> None:
    with pytest.raises(SourceConfigurationError):
        RecordedRedditAdapter(scratch_dir / "does-not-exist")


def test_a_missing_search_payload_is_a_configuration_error(scratch_dir: Path) -> None:
    adapter = RecordedRedditAdapter(scratch_dir)

    with pytest.raises(SourceConfigurationError):
        list(adapter.search_discussions(SourceQuery(terms=("audit",))))


def test_invalid_json_is_reported_with_the_file_name(scratch_dir: Path) -> None:
    (scratch_dir / "search_response.json").write_text("{not json", encoding="utf-8")
    adapter = RecordedRedditAdapter(scratch_dir)

    with pytest.raises(SourceResponseError) as excinfo:
        list(adapter.search_discussions(SourceQuery(terms=("audit",))))

    assert "search_response.json" in str(excinfo.value)


def test_the_whole_recorded_corpus_is_reachable(adapter: RecordedRedditAdapter) -> None:
    posts = list(adapter.search_discussions(SourceQuery(terms=("audit",), limit=50)))

    assert len(posts) == ALL_POSTS
    assert all(post.kind is DiscussionKind.POST for post in posts)
    assert all(post.source_key == "reddit" for post in posts)
    assert adapter.stats.posts_seen == ALL_POSTS
    assert adapter.stats.posts_yielded == ALL_POSTS


def test_posts_keep_their_provenance_and_ordering(adapter: RecordedRedditAdapter) -> None:
    posts = list(adapter.search_discussions(SourceQuery(terms=("audit",), limit=50)))

    # Fixture timestamps ascend, and the adapter preserves the order the source returned.
    timestamps = [post.source_created_at for post in posts]
    assert timestamps == sorted(timestamps)
    assert {post.community_external_id for post in posts} == {"technology", "programming"}
    assert all(post.url and post.url.startswith("https://www.reddit.com/") for post in posts)


def test_the_limit_is_respected(adapter: RecordedRedditAdapter) -> None:
    posts = list(adapter.search_discussions(SourceQuery(terms=("audit",), limit=2)))

    assert len(posts) == 2


def test_communities_scope_the_collection(adapter: RecordedRedditAdapter) -> None:
    posts = list(
        adapter.search_discussions(
            SourceQuery(terms=("audit",), communities=("technology",), limit=50)
        )
    )

    assert len(posts) == TECHNOLOGY_POSTS
    assert adapter.stats.skipped_out_of_scope == 1


def test_the_window_filters_by_source_timestamp(adapter: RecordedRedditAdapter) -> None:
    posts = list(
        adapter.search_discussions(
            SourceQuery(terms=("audit",), since=datetime(2024, 3, 1, tzinfo=UTC), limit=50)
        )
    )

    assert len(posts) == 3
    assert adapter.stats.skipped_out_of_window == ALL_POSTS - 3


def test_deleted_and_removed_posts_are_kept_with_their_state(
    adapter: RecordedRedditAdapter,
) -> None:
    posts = {
        post.external_id: post
        for post in adapter.search_discussions(SourceQuery(terms=("audit",), limit=50))
    }

    assert posts["t3_g7h8i9"].content_state is ContentState.REMOVED
    assert posts["t3_m4n5o6"].content_state is ContentState.DELETED
    assert posts["t3_m4n5o6"].author_external_id is None
    assert posts["t3_a1b2c3"].content_state is ContentState.PRESENT


def test_comment_threads_are_assembled_with_parents_first(
    adapter: RecordedRedditAdapter,
) -> None:
    posts = list(adapter.search_discussions(SourceQuery(terms=("audit",), limit=50)))
    post = next(item for item in posts if item.external_id == "t3_a1b2c3")

    comments = list(adapter.fetch_comments(post, limit=100))

    positions = {item.external_id: index for index, item in enumerate(comments)}
    assert positions["t1_c001"] < positions["t1_c002"] < positions["t1_c003"]
    for item in comments:
        if item.parent_external_id in positions:
            assert positions[item.parent_external_id] < positions[item.external_id]
    assert adapter.stats.comments_yielded == len(comments)


def test_comment_metadata_is_preserved(adapter: RecordedRedditAdapter) -> None:
    posts = list(adapter.search_discussions(SourceQuery(terms=("audit",), limit=50)))
    post = next(item for item in posts if item.external_id == "t3_a1b2c3")

    comments = {item.external_id: item for item in adapter.fetch_comments(post, limit=100)}

    assert comments["t1_c003"].metadata["is_submitter"] is True
    assert comments["t1_c001"].engagement.score == 320
    assert comments["t1_c011"].content_state is ContentState.PRESENT


def test_a_comment_whose_parent_is_absent_keeps_the_reference(
    adapter: RecordedRedditAdapter,
) -> None:
    """Preserving the dangling reference is deliberate: the parent may be collected later."""
    posts = list(adapter.search_discussions(SourceQuery(terms=("audit",), limit=50)))
    post = next(item for item in posts if item.external_id == "t3_a1b2c3")

    comments = {item.external_id: item for item in adapter.fetch_comments(post, limit=100)}

    assert comments["t1_c014"].parent_external_id == "t1_zzzzzz"
    assert "t1_zzzzzz" not in comments


def test_posts_without_a_recorded_thread_have_no_comments(
    adapter: RecordedRedditAdapter,
) -> None:
    posts = list(adapter.search_discussions(SourceQuery(terms=("audit",), limit=50)))
    post = next(item for item in posts if item.external_id == "t3_p7q8r9")

    assert list(adapter.fetch_comments(post, limit=100)) == []


def test_comment_limit_bounds_the_thread(adapter: RecordedRedditAdapter) -> None:
    posts = list(adapter.search_discussions(SourceQuery(terms=("audit",), limit=50)))
    post = next(item for item in posts if item.external_id == "t3_a1b2c3")

    assert len(list(adapter.fetch_comments(post, limit=4))) == 4


def test_a_single_listing_object_is_accepted(scratch_dir: Path, fixture_dir: Path) -> None:
    """Some captures store one listing; others store a list of them. Both are valid."""
    payload = json.loads((fixture_dir / "search_response.json").read_text(encoding="utf-8"))
    (scratch_dir / "search_response.json").write_text(json.dumps(payload), encoding="utf-8")

    adapter = RecordedRedditAdapter(scratch_dir)

    assert (
        len(list(adapter.search_discussions(SourceQuery(terms=("audit",), limit=50)))) == ALL_POSTS
    )
