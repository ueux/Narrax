"""The Reddit → normalized translation boundary (PROMPT 14).

These tests are the contract that keeps Reddit's shapes out of the intelligence pipeline: after
normalization, nothing downstream may see `selftext`, `[deleted]`, `created_utc`, or a relative
permalink.
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.ingestion.normalized import ContentState, DiscussionKind, NormalizedDiscussion
from app.ingestion.reddit.normalize import (
    absolute_permalink,
    bare_id,
    content_state,
    fullname,
    normalize_comment,
    normalize_post,
    timestamp,
    visible_author,
)
from app.ingestion.reddit.schemas import RedditComment, RedditPost

COLLECTED_AT = datetime(2024, 5, 1, 12, 0, tzinfo=UTC)


def make_post(**overrides: object) -> RedditPost:
    payload: dict[str, object] = {
        "id": "a1b2c3",
        "name": "t3_a1b2c3",
        "subreddit": "technology",
        "subreddit_name_prefixed": "r/technology",
        "title": "New AI regulation bill would require independent model audits",
        "selftext": "The proposed bill would require an independent audit before deployment.",
        "author": "policy_watcher",
        "created_utc": 1705320000,
        "permalink": "/r/technology/comments/a1b2c3/new_ai_regulation_bill/",
        "score": 1420,
        "num_comments": 3,
        "upvote_ratio": 0.87,
        "is_self": True,
    }
    payload.update(overrides)
    return RedditPost.model_validate(payload)


def make_comment(**overrides: object) -> RedditComment:
    payload: dict[str, object] = {
        "id": "c001",
        "name": "t1_c001",
        "subreddit": "technology",
        "body": "The audit requirement only applies above the compute threshold.",
        "author": "skeptical_dev",
        "created_utc": 1705323600,
        "permalink": "/r/technology/comments/a1b2c3/x/c001/",
        "parent_id": "t3_a1b2c3",
        "link_id": "t3_a1b2c3",
        "score": 320,
    }
    payload.update(overrides)
    return RedditComment.model_validate(payload)


# --- identity ------------------------------------------------------------------------------


def test_post_uses_the_platform_fullname_as_its_identifier() -> None:
    item = normalize_post(make_post(), collected_at=COLLECTED_AT)

    assert item.external_id == "t3_a1b2c3"
    assert item.kind is DiscussionKind.POST
    assert item.parent_external_id is None
    assert item.is_post is True


def test_missing_name_falls_back_to_the_prefix_convention() -> None:
    item = normalize_post(make_post(name=None), collected_at=COLLECTED_AT)

    assert item.external_id == "t3_a1b2c3"


def test_comment_parent_matches_its_parents_external_id() -> None:
    """Parent linkage only works because both sides use the same identifier scheme."""
    post = normalize_post(make_post(), collected_at=COLLECTED_AT)
    comment = normalize_comment(make_comment(), collected_at=COLLECTED_AT)

    assert comment.parent_external_id == post.external_id


def test_top_level_comment_falls_back_to_the_post_when_parent_is_absent() -> None:
    comment = normalize_comment(
        make_comment(parent_id=None),
        collected_at=COLLECTED_AT,
        post_external_id="t3_a1b2c3",
    )

    assert comment.parent_external_id == "t3_a1b2c3"
    assert comment.kind is DiscussionKind.COMMENT
    assert comment.title is None


def test_bare_id_strips_a_thing_prefix() -> None:
    assert bare_id("t3_a1b2c3") == "a1b2c3"
    assert bare_id("t1_c001") == "c001"
    # An identifier that is not a fullname is returned unchanged rather than mangled.
    assert bare_id("a1b2c3") == "a1b2c3"


def test_fullname_prefers_the_payload_value() -> None:
    assert fullname("post", "a1b2c3", "t3_zzz999") == "t3_zzz999"
    assert fullname("post", "a1b2c3", None) == "t3_a1b2c3"
    assert fullname("comment", "c001", None) == "t1_c001"


# --- provenance ----------------------------------------------------------------------------


def test_community_is_lowercased_so_it_cannot_split_into_two_rows() -> None:
    item = normalize_post(make_post(subreddit="Technology"), collected_at=COLLECTED_AT)

    assert item.community_external_id == "technology"
    # The display form is preserved for a human reading the record.
    assert item.community_name == "r/technology"


def test_timestamps_become_timezone_aware_utc() -> None:
    item = normalize_post(make_post(), collected_at=COLLECTED_AT)

    assert item.source_created_at == datetime(2024, 1, 15, 12, 0, tzinfo=UTC)
    assert item.source_created_at.tzinfo is not None
    assert item.collected_at == COLLECTED_AT


def test_timestamp_helper_is_utc() -> None:
    assert timestamp(1705320000) == datetime(2024, 1, 15, 12, 0, tzinfo=UTC)


def test_permalink_becomes_absolute() -> None:
    item = normalize_post(make_post(), collected_at=COLLECTED_AT)

    assert item.url == (
        "https://www.reddit.com/r/technology/comments/a1b2c3/new_ai_regulation_bill/"
    )


def test_absolute_permalink_leaves_absolute_urls_alone() -> None:
    assert absolute_permalink("https://example.com/x") == "https://example.com/x"
    assert absolute_permalink(None) is None
    assert absolute_permalink("r/x/comments/1") == "https://www.reddit.com/r/x/comments/1"


def test_engagement_is_captured() -> None:
    item = normalize_post(make_post(), collected_at=COLLECTED_AT)

    assert item.engagement.score == 1420
    assert item.engagement.comment_count == 3
    assert item.engagement.upvote_ratio == 0.87


def test_outbound_link_is_kept_separately_from_the_discussion_url() -> None:
    """`url` always points at the discussion; a link post's destination is context, not identity."""
    item = normalize_post(
        make_post(
            is_self=False,
            url="https://example.gov/bills/ai-audit-act",
            link_flair_text="Policy",
        ),
        collected_at=COLLECTED_AT,
    )

    assert item.url is not None and "reddit.com" in item.url
    assert item.metadata["outbound_url"] == "https://example.gov/bills/ai-audit-act"
    assert item.metadata["link_flair_text"] == "Policy"
    assert item.metadata["is_self"] is False


def test_self_post_has_no_outbound_link() -> None:
    item = normalize_post(make_post(is_self=True), collected_at=COLLECTED_AT)

    assert "outbound_url" not in item.metadata


def test_comment_metadata_records_thread_context() -> None:
    item = normalize_comment(
        make_comment(is_submitter=True, controversiality=2, distinguished="moderator"),
        collected_at=COLLECTED_AT,
    )

    assert item.metadata["is_submitter"] is True
    assert item.metadata["controversiality"] == 2
    assert item.metadata["distinguished"] == "moderator"
    assert item.metadata["link_id"] == "t3_a1b2c3"


# --- absent content ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "removed_by_category", "expected"),
    [
        ("A real comment about the bill.", None, ContentState.PRESENT),
        ("[deleted]", None, ContentState.DELETED),
        ("[removed]", None, ContentState.REMOVED),
        # Sentinels win even if a category disagrees: the text is what Reddit serves.
        ("[removed]", "deleted", ContentState.REMOVED),
        ("", None, ContentState.PRESENT),
        (None, None, ContentState.UNAVAILABLE),
        (None, "deleted", ContentState.DELETED),
        (None, "moderator", ContentState.REMOVED),
        ("", "moderator", ContentState.REMOVED),
    ],
)
def test_content_state_translation(
    body: str | None, removed_by_category: str | None, expected: ContentState
) -> None:
    assert content_state(body=body, removed_by_category=removed_by_category) is expected


def test_deleted_account_becomes_no_author() -> None:
    assert visible_author("[deleted]") is None
    assert visible_author("[removed]") is None
    assert visible_author("") is None
    assert visible_author("   ") is None
    assert visible_author("policy_watcher") == "policy_watcher"


def test_deleted_comment_is_still_normalized_with_a_state() -> None:
    """A deleted comment is real source truth: it existed, and that is worth recording."""
    item = normalize_comment(
        make_comment(body="[deleted]", author="[deleted]"), collected_at=COLLECTED_AT
    )

    assert item.content_state is ContentState.DELETED
    assert item.author_external_id is None


def test_removed_post_keeps_its_removal_category_in_metadata() -> None:
    item = normalize_post(
        make_post(selftext="[removed]", removed_by_category="moderator", distinguished="moderator"),
        collected_at=COLLECTED_AT,
    )

    assert item.content_state is ContentState.REMOVED
    assert item.metadata["removed_by_category"] == "moderator"


# --- what gets cleaned ---------------------------------------------------------------------


def test_post_with_a_removed_body_still_offers_its_title() -> None:
    """Reddit does not remove titles, so the author's headline remains analysable."""
    item = normalize_post(
        make_post(selftext="[removed]", removed_by_category="moderator"),
        collected_at=COLLECTED_AT,
    )

    text, state = item.analysis_input()

    assert state is ContentState.PRESENT
    assert text is not None and "independent model audits" in text
    assert "[removed]" not in text


def test_post_with_a_deleted_body_offers_only_its_title() -> None:
    item = normalize_post(
        make_post(selftext="[deleted]", removed_by_category="deleted"), collected_at=COLLECTED_AT
    )

    text, state = item.analysis_input()

    assert state is ContentState.PRESENT
    assert text == "New AI regulation bill would require independent model audits"


def test_a_post_cannot_exist_without_any_readable_text() -> None:
    """A post always has analysable text, because the model forbids a blank title.

    That invariant is what makes `analysis_input` safe: the title is the author's own words and
    survives moderation, so there is no such thing as a text-less post to reason about.
    """
    with pytest.raises(ValidationError):
        normalize_post(
            make_post(title=" ", selftext="[removed]", removed_by_category="moderator"),
            collected_at=COLLECTED_AT,
        )


def test_comment_with_a_removed_body_offers_nothing() -> None:
    """A comment has no second field, so once its body is gone the item is gone."""
    item = normalize_comment(make_comment(body="[removed]"), collected_at=COLLECTED_AT)

    text, state = item.analysis_input()

    assert text is None
    assert state is ContentState.REMOVED


def test_post_analysis_text_joins_title_and_body() -> None:
    item = normalize_post(make_post(), collected_at=COLLECTED_AT)

    text, _ = item.analysis_input()

    assert text is not None
    assert text.startswith("New AI regulation bill")
    assert "independent audit before deployment" in text


# --- model validation ----------------------------------------------------------------------


def test_naive_timestamps_are_rejected() -> None:
    with pytest.raises(ValidationError):
        NormalizedDiscussion(
            source_key="reddit",
            external_id="t3_x",
            kind=DiscussionKind.POST,
            title="A title long enough to be meaningful",
            source_created_at=datetime(2024, 1, 1),  # no tzinfo
            collected_at=COLLECTED_AT,
        )


def test_blank_external_id_is_rejected() -> None:
    with pytest.raises(ValidationError):
        NormalizedDiscussion(
            source_key="reddit",
            external_id="   ",
            kind=DiscussionKind.POST,
            title="A title long enough to be meaningful",
            source_created_at=COLLECTED_AT,
            collected_at=COLLECTED_AT,
        )


def test_post_without_a_title_is_rejected() -> None:
    with pytest.raises(ValidationError):
        NormalizedDiscussion(
            source_key="reddit",
            external_id="t3_x",
            kind=DiscussionKind.POST,
            title="  ",
            source_created_at=COLLECTED_AT,
            collected_at=COLLECTED_AT,
        )


def test_post_with_a_parent_is_rejected() -> None:
    with pytest.raises(ValidationError):
        NormalizedDiscussion(
            source_key="reddit",
            external_id="t3_x",
            kind=DiscussionKind.POST,
            parent_external_id="t3_y",
            title="A title long enough to be meaningful",
            source_created_at=COLLECTED_AT,
            collected_at=COLLECTED_AT,
        )


def test_comment_cannot_be_its_own_parent() -> None:
    with pytest.raises(ValidationError):
        NormalizedDiscussion(
            source_key="reddit",
            external_id="t1_x",
            kind=DiscussionKind.COMMENT,
            parent_external_id="t1_x",
            body="A body long enough to be meaningful",
            source_created_at=COLLECTED_AT,
            collected_at=COLLECTED_AT,
        )
