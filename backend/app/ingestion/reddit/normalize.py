"""The Reddit → NarraX normalization layer (PROMPT 14).

This module is the **translation boundary**. Reddit's shapes stop here: above it, everything
works with `NormalizedDiscussion`, and swapping or adding a platform means writing another module
like this one.

What it resolves
----------------
* **Identity** — Reddit's `name` (`t3_…`/`t1_…`) is used as `external_id`, so posts and comments
  can never collide, and a comment's `parent_id` matches its parent's `external_id` directly.
* **Absent content** — Reddit signals deletion and removal with sentinel strings (`[deleted]`,
  `[removed]`), an empty body, or `removed_by_category`. Those become an explicit
  `ContentState`, so nothing downstream pattern-matches sentinel text.
* **Deleted accounts** — `author == "[deleted]"` becomes `None` rather than a fake user.
* **Time** — `created_utc` (epoch seconds) becomes timezone-aware UTC.
* **URLs** — the relative `permalink` becomes absolute, and a link post's outbound URL is kept
  separately in metadata so it is never confused with the discussion's own URL.
* **Metadata** — a curated set of platform flags and flair is preserved verbatim; the rest is
  dropped rather than stored indiscriminately.

References: docs/ingestion.md §4 · docs/data-safety.md
"""

from datetime import UTC, datetime
from typing import Any

from app.ingestion.normalized import (
    ContentState,
    DiscussionKind,
    NormalizedDiscussion,
    NormalizedEngagement,
)
from app.ingestion.reddit.schemas import RedditComment, RedditPost

SOURCE_KEY = "reddit"
PERMALINK_BASE = "https://www.reddit.com"
POST_PREFIX = "t3_"
COMMENT_PREFIX = "t1_"

# Reddit's sentinel strings for content it will no longer serve.
DELETED_SENTINEL = "[deleted]"
REMOVED_SENTINEL = "[removed]"
_GONE_AUTHORS = frozenset({DELETED_SENTINEL, REMOVED_SENTINEL})

# `removed_by_category` values that mean "the author deleted it" rather than "it was removed".
_AUTHOR_DELETED_CATEGORIES = frozenset({"deleted"})


def timestamp(created_utc: float) -> datetime:
    """Reddit epoch seconds → timezone-aware UTC `datetime`."""
    return datetime.fromtimestamp(float(created_utc), tz=UTC)


def fullname(kind: str, data_id: str, name: str | None) -> str:
    """Reddit's globally-unique identifier for an item.

    Prefers the API's own `name`, falling back to the documented prefix convention so a payload
    missing `name` still produces a stable identifier.
    """
    if name:
        return name
    prefix = POST_PREFIX if kind == "post" else COMMENT_PREFIX
    return f"{prefix}{data_id}"


def bare_id(external_id: str) -> str:
    """Strip a `t1_`/`t3_` prefix — API endpoints want the bare base-36 id."""
    prefix, separator, remainder = external_id.partition("_")
    return remainder if separator and prefix in {"t1", "t3", "t4", "t5", "t6"} else external_id


def content_state(*, body: str | None, removed_by_category: str | None = None) -> ContentState:
    """Translate Reddit's many ways of saying "this is gone" into one vocabulary.

    Order matters: a sentinel body is conclusive, because Reddit replaces the text when content
    is gone. `removed_by_category` is only consulted when no text is available, since it can be
    set while the text is still served.
    """
    text = (body or "").strip()

    if text == DELETED_SENTINEL:
        return ContentState.DELETED
    if text == REMOVED_SENTINEL:
        return ContentState.REMOVED

    if not text:
        if removed_by_category in _AUTHOR_DELETED_CATEGORIES:
            return ContentState.DELETED
        if removed_by_category:
            return ContentState.REMOVED
        return ContentState.UNAVAILABLE if body is None else ContentState.PRESENT

    return ContentState.PRESENT


def visible_author(value: str | None) -> str | None:
    """A handle, or `None` when the account is gone.

    Reddit writes `[deleted]` where a username would be. Turning that into `None` keeps the
    pseudonymous handle space free of pseudo-handles that would otherwise look like real authors.
    """
    if value is None:
        return None
    stripped = value.strip()
    return None if not stripped or stripped in _GONE_AUTHORS else stripped


def absolute_permalink(permalink: str | None) -> str | None:
    """Relative Reddit permalink → absolute URL."""
    if not permalink:
        return None
    if permalink.startswith(("http://", "https://")):
        return permalink
    return f"{PERMALINK_BASE}{permalink if permalink.startswith('/') else '/' + permalink}"


def post_metadata(post: RedditPost) -> dict[str, Any]:
    """Curated, verbatim platform context for a post."""
    metadata: dict[str, Any] = {}
    if post.link_flair_text:
        metadata["link_flair_text"] = post.link_flair_text
    if post.distinguished:
        metadata["distinguished"] = post.distinguished
    if post.removed_by_category:
        metadata["removed_by_category"] = post.removed_by_category
    for key, value in (
        ("is_self", post.is_self),
        ("over_18", post.over_18),
        ("spoiler", post.spoiler),
        ("locked", post.locked),
        ("stickied", post.stickied),
    ):
        if value is not None:
            metadata[key] = value
    if post.num_crossposts:
        metadata["num_crossposts"] = post.num_crossposts
    # A link post's destination is context, and is deliberately kept separate from `url`, which
    # always points at the discussion itself.
    if post.url and post.is_self is False:
        metadata["outbound_url"] = post.url
    return metadata


def comment_metadata(comment: RedditComment) -> dict[str, Any]:
    """Curated, verbatim platform context for a comment."""
    metadata: dict[str, Any] = {}
    if comment.distinguished:
        metadata["distinguished"] = comment.distinguished
    if comment.link_id:
        metadata["link_id"] = comment.link_id
    for key, value in (
        ("is_submitter", comment.is_submitter),
        ("stickied", comment.stickied),
        ("score_hidden", comment.score_hidden),
    ):
        if value is not None:
            metadata[key] = value
    if comment.controversiality:
        metadata["controversiality"] = comment.controversiality
    return metadata


def normalize_post(post: RedditPost, *, collected_at: datetime) -> NormalizedDiscussion:
    """Convert a Reddit submission into the normalized model."""
    return NormalizedDiscussion(
        source_key=SOURCE_KEY,
        external_id=fullname("post", post.id, post.name),
        kind=DiscussionKind.POST,
        parent_external_id=None,
        community_external_id=post.subreddit,
        community_name=post.subreddit_name_prefixed or post.subreddit,
        author_external_id=visible_author(post.author),
        title=post.title,
        body=post.selftext or "",
        url=absolute_permalink(post.permalink),
        source_created_at=timestamp(post.created_utc),
        collected_at=collected_at,
        content_state=content_state(
            body=post.selftext, removed_by_category=post.removed_by_category
        ),
        engagement=NormalizedEngagement(
            score=post.score,
            comment_count=post.num_comments,
            upvote_ratio=post.upvote_ratio,
        ),
        metadata=post_metadata(post),
    )


def normalize_comment(
    comment: RedditComment, *, collected_at: datetime, post_external_id: str | None = None
) -> NormalizedDiscussion:
    """Convert a Reddit comment into the normalized model.

    `post_external_id` is used only as a fallback parent for a top-level comment whose payload
    omits `parent_id`; the payload's own value always wins, because it is what preserves the
    thread structure.
    """
    parent = comment.parent_id or post_external_id
    return NormalizedDiscussion(
        source_key=SOURCE_KEY,
        external_id=fullname("comment", comment.id, comment.name),
        kind=DiscussionKind.COMMENT,
        parent_external_id=parent,
        community_external_id=comment.subreddit,
        community_name=comment.subreddit,
        author_external_id=visible_author(comment.author),
        title=None,
        body=comment.body or "",
        url=absolute_permalink(comment.permalink),
        source_created_at=timestamp(comment.created_utc),
        collected_at=collected_at,
        content_state=content_state(body=comment.body),
        engagement=NormalizedEngagement(score=comment.score),
        metadata=comment_metadata(comment),
    )
