"""The Reddit source adapter: query mapping, filtering, and thread assembly.

Two behaviours are load-bearing and tested explicitly:

* posts are yielded even when their content is gone, because a deleted post is still source truth;
* comments are yielded parents-first, because the persistence layer relies on the database's
  self-referencing foreign key rather than sorting comments itself.
"""

from datetime import UTC, datetime

import httpx
import pytest

from app.ingestion.base import SourceQuery, SourceResponseError
from app.ingestion.normalized import ContentState, DiscussionKind, NormalizedDiscussion
from app.ingestion.reddit.adapter import RedditSourceAdapter
from app.ingestion.reddit.normalize import normalize_comment, normalize_post
from app.ingestion.reddit.schemas import RedditComment, RedditPost
from tests.ingestion.fake_reddit import (
    FakeReddit,
    comment_thing,
    comments_payload,
    listing,
    post_thing,
)

COLLECTED_AT = datetime(2024, 5, 1, 12, 0, tzinfo=UTC)
POST_TIME = datetime(2024, 1, 15, 12, 0, tzinfo=UTC)
SEARCH_PATH = "/r/technology/search"
SITE_SEARCH = "/search"


def build_adapter(fake: FakeReddit) -> RedditSourceAdapter:
    return RedditSourceAdapter(fake.client(), clock=lambda: COLLECTED_AT)


def normalized_post(**overrides: object) -> NormalizedDiscussion:
    """A normalized post built directly, for tests about traversal rather than search."""
    return normalize_post(
        RedditPost.model_validate(post_thing("a1b2c3", **overrides)["data"]),
        collected_at=COLLECTED_AT,
    )


def normalized_comment(**overrides: object) -> NormalizedDiscussion:
    return normalize_comment(
        RedditComment.model_validate(
            comment_thing("c001", parent_id="t3_a1b2c3", **overrides)["data"]
        ),
        collected_at=COLLECTED_AT,
    )


# --- query mapping ----------------------------------------------------------------------------


def test_terms_with_communities_become_a_restricted_per_community_search() -> None:
    adapter = build_adapter(FakeReddit())

    requests = adapter.search_requests(
        SourceQuery(terms=("ai regulation",), communities=("technology", "programming"))
    )

    assert [path for path, _ in requests] == [
        "/r/technology/search",
        "/r/programming/search",
    ]
    assert requests[0][1]["q"] == "ai regulation"
    assert requests[0][1]["restrict_sr"] == "1"
    assert requests[0][1]["type"] == "link"


def test_terms_without_communities_become_a_site_wide_search() -> None:
    adapter = build_adapter(FakeReddit())

    requests = adapter.search_requests(SourceQuery(terms=("ai regulation",)))

    assert [path for path, _ in requests] == ["/search"]
    assert requests[0][1]["q"] == "ai regulation"


def test_communities_without_terms_browse_the_community() -> None:
    adapter = build_adapter(FakeReddit())

    requests = adapter.search_requests(SourceQuery(communities=("technology",)))

    assert [path for path, _ in requests] == ["/r/technology/new"]


def test_time_filter_is_only_sent_where_the_sort_supports_it() -> None:
    adapter = build_adapter(FakeReddit())

    top = adapter.search_requests(SourceQuery(communities=("technology",), sort="top"))
    new = adapter.search_requests(SourceQuery(communities=("technology",), sort="new"))

    assert top[0] == ("/r/technology/top", {"t": "year"})
    assert new[0] == ("/r/technology/new", {})


def test_search_only_sort_is_mapped_for_listing_endpoints() -> None:
    """`relevance` is meaningless for a listing, so it degrades to `new` rather than 400-ing."""
    adapter = build_adapter(FakeReddit())

    requests = adapter.search_requests(SourceQuery(communities=("technology",), sort="relevance"))

    assert [path for path, _ in requests] == ["/r/technology/new"]


# --- search -----------------------------------------------------------------------------------


def test_search_yields_normalized_posts() -> None:
    fake = FakeReddit(
        {
            SITE_SEARCH: httpx.Response(
                200,
                json=listing(
                    [
                        post_thing("a1b2c3"),
                        post_thing("d4e5f6", subreddit="programming"),
                    ]
                ),
            )
        }
    )
    adapter = build_adapter(fake)

    items = list(adapter.search_discussions(SourceQuery(terms=("audit",))))

    assert [item.external_id for item in items] == ["t3_a1b2c3", "t3_d4e5f6"]
    assert all(item.kind is DiscussionKind.POST for item in items)
    assert items[0].community_external_id == "technology"
    assert items[1].community_external_id == "programming"
    assert adapter.stats.posts_yielded == 2


def test_posts_outside_the_window_are_excluded_and_counted() -> None:
    fake = FakeReddit(
        {
            SITE_SEARCH: httpx.Response(
                200,
                json=listing(
                    [
                        post_thing("in_window", created_utc=1705320000),
                        post_thing("too_old", created_utc=1600000000),
                    ]
                ),
            )
        }
    )
    adapter = build_adapter(fake)

    items = list(
        adapter.search_discussions(
            SourceQuery(terms=("audit",), since=datetime(2024, 1, 1, tzinfo=UTC))
        )
    )

    assert [item.external_id for item in items] == ["t3_in_window"]
    assert adapter.stats.skipped_out_of_window == 1


def test_a_deleted_post_is_still_yielded() -> None:
    """Its removal is recorded as a content state; the item itself is real source truth."""
    fake = FakeReddit(
        {
            SITE_SEARCH: httpx.Response(
                200,
                json=listing(
                    [
                        post_thing(
                            "gone",
                            selftext="[removed]",
                            removed_by_category="moderator",
                            author="[deleted]",
                        )
                    ]
                ),
            )
        }
    )
    adapter = build_adapter(fake)

    items = list(adapter.search_discussions(SourceQuery(terms=("audit",))))

    assert len(items) == 1
    assert items[0].content_state is ContentState.REMOVED
    assert items[0].author_external_id is None


def test_a_malformed_post_is_skipped_and_counted_rather_than_aborting_the_run() -> None:
    fake = FakeReddit(
        {
            SITE_SEARCH: httpx.Response(
                200,
                json=listing(
                    [
                        post_thing("good"),
                        # `subreddit` and `created_utc` are absent, so this cannot be normalized.
                        {"kind": "t3", "data": {"id": "broken", "title": "No subreddit here"}},
                    ]
                ),
            )
        }
    )
    adapter = build_adapter(fake)

    items = list(adapter.search_discussions(SourceQuery(terms=("audit",))))

    assert [item.external_id for item in items] == ["t3_good"]
    assert adapter.stats.skipped_malformed == 1
    assert adapter.stats.posts_seen == 2


def test_repeated_identifiers_across_communities_are_counted_once() -> None:
    fake = FakeReddit(
        {
            "/r/technology/search": httpx.Response(200, json=listing([post_thing("shared")])),
            "/r/programming/search": httpx.Response(200, json=listing([post_thing("shared")])),
        }
    )
    adapter = build_adapter(fake)

    items = list(
        adapter.search_discussions(
            SourceQuery(terms=("audit",), communities=("technology", "programming"), limit=10)
        )
    )

    assert [item.external_id for item in items] == ["t3_shared"]
    assert adapter.stats.skipped_duplicate_id == 1


def test_the_limit_is_shared_across_requests() -> None:
    """One budget for the query, split evenly, so the first community cannot consume everything."""
    fake = FakeReddit(
        {
            "/r/technology/search": httpx.Response(
                200, json=listing([post_thing(f"t{i}") for i in range(10)])
            ),
            "/r/programming/search": httpx.Response(
                200, json=listing([post_thing(f"p{i}", subreddit="programming") for i in range(10)])
            ),
        }
    )
    adapter = build_adapter(fake)

    items = list(
        adapter.search_discussions(
            SourceQuery(terms=("audit",), communities=("technology", "programming"), limit=4)
        )
    )

    assert len(items) == 4
    assert {item.community_external_id for item in items} == {"technology", "programming"}


# --- comments ---------------------------------------------------------------------------------


def test_comments_are_returned_parents_first() -> None:
    reply_to_reply = comment_thing("c003", parent_id="t1_c002")
    reply = comment_thing(
        "c002",
        parent_id="t1_c001",
        replies=listing([reply_to_reply]),
    )
    fake = FakeReddit(
        {
            "/comments/a1b2c3": httpx.Response(
                200,
                json=comments_payload(
                    post_thing("a1b2c3"),
                    [
                        comment_thing("c001", parent_id="t3_a1b2c3", replies=listing([reply])),
                        comment_thing("c004", parent_id="t3_a1b2c3"),
                    ],
                ),
            )
        }
    )
    adapter = build_adapter(fake)
    post = normalized_post()

    comments = list(adapter.fetch_comments(post, limit=10))

    ids = [item.external_id for item in comments]
    assert ids == ["t1_c001", "t1_c004", "t1_c002", "t1_c003"]
    # Every parent must appear before its child, or the self-referencing foreign key would fail.
    positions = {item.external_id: index for index, item in enumerate(comments)}
    for item in comments:
        if item.parent_external_id and item.parent_external_id in positions:
            assert positions[item.parent_external_id] < positions[item.external_id]


def test_comment_parents_and_kinds_are_preserved() -> None:
    fake = FakeReddit(
        {
            "/comments/a1b2c3": httpx.Response(
                200,
                json=comments_payload(
                    post_thing("a1b2c3"), [comment_thing("c001", parent_id="t3_a1b2c3")]
                ),
            )
        }
    )
    adapter = build_adapter(fake)
    post = normalized_post()

    comment = next(iter(adapter.fetch_comments(post, limit=5)))

    assert comment.kind is DiscussionKind.COMMENT
    assert comment.parent_external_id == "t3_a1b2c3"
    assert comment.title is None
    assert adapter.stats.comments_yielded == 1


def test_comment_limit_bounds_traversal() -> None:
    fake = FakeReddit(
        {
            "/comments/a1b2c3": httpx.Response(
                200,
                json=comments_payload(
                    post_thing("a1b2c3"),
                    [comment_thing(f"c{i:03d}", parent_id="t3_a1b2c3") for i in range(20)],
                ),
            )
        }
    )
    adapter = build_adapter(fake)
    post = normalized_post()

    assert len(list(adapter.fetch_comments(post, limit=3))) == 3


def test_comments_are_not_fetched_for_a_comment() -> None:
    adapter = build_adapter(FakeReddit())

    assert list(adapter.fetch_comments(normalized_comment(), limit=5)) == []


def test_comments_skip_deleted_bodies_with_a_state() -> None:
    fake = FakeReddit(
        {
            "/comments/a1b2c3": httpx.Response(
                200,
                json=comments_payload(
                    post_thing("a1b2c3"),
                    [
                        comment_thing(
                            "c001", parent_id="t3_a1b2c3", body="[deleted]", author="[deleted]"
                        ),
                        comment_thing("c002", parent_id="t3_a1b2c3", body=""),
                    ],
                ),
            )
        }
    )
    adapter = build_adapter(fake)
    post = normalized_post()

    comments = list(adapter.fetch_comments(post, limit=10))

    assert comments[0].content_state is ContentState.DELETED
    assert comments[0].author_external_id is None
    assert comments[1].content_state is ContentState.PRESENT


def test_unexpected_comments_payload_is_rejected() -> None:
    fake = FakeReddit({"/comments/a1b2c3": httpx.Response(200, json={"not": "a list"})})
    adapter = build_adapter(fake)

    with pytest.raises(SourceResponseError):
        list(adapter.fetch_comments(normalized_post(), limit=5))
