"""Typed models for Reddit's JSON payloads.

These are **the only types in the codebase that know Reddit's field names** (PROMPT 14). They
exist so that a malformed or changed payload fails loudly at the boundary, instead of producing
`None` deep inside the pipeline.

Reddit returns far more fields than NarraX needs. Each model therefore declares the fields that
matter and sets `extra="allow"`, which keeps the full payload available for
`discussions.raw_metadata` without pretending to model fields nobody reads.

Reference: <https://www.reddit.com/dev/api>
"""

from typing import Any

from pydantic import BaseModel, ConfigDict


class RedditThing(BaseModel):
    """One entry in a listing: a `t3` post, a `t1` comment, or a `more` placeholder."""

    model_config = ConfigDict(extra="allow")

    kind: str
    data: dict[str, Any] = {}


class RedditListingData(BaseModel):
    """The body of a listing, including the cursor for the next page."""

    model_config = ConfigDict(extra="allow")

    children: list[RedditThing] = []
    after: str | None = None
    before: str | None = None


class RedditListing(BaseModel):
    """A Reddit listing envelope."""

    model_config = ConfigDict(extra="allow")

    kind: str = "Listing"
    data: RedditListingData


class RedditPost(BaseModel):
    """A submission (`t3`)."""

    model_config = ConfigDict(extra="allow")

    id: str
    name: str | None = None
    subreddit: str
    subreddit_name_prefixed: str | None = None
    title: str
    selftext: str | None = None
    author: str | None = None
    created_utc: float
    permalink: str | None = None
    url: str | None = None
    score: int | None = None
    num_comments: int | None = None
    upvote_ratio: float | None = None
    removed_by_category: str | None = None
    # Flags and flair that carry context worth keeping verbatim.
    is_self: bool | None = None
    over_18: bool | None = None
    spoiler: bool | None = None
    locked: bool | None = None
    stickied: bool | None = None
    distinguished: str | None = None
    link_flair_text: str | None = None
    num_crossposts: int | None = None


class RedditComment(BaseModel):
    """A comment (`t1`)."""

    model_config = ConfigDict(extra="allow")

    id: str
    name: str | None = None
    subreddit: str
    body: str | None = None
    author: str | None = None
    created_utc: float
    permalink: str | None = None
    # `t1_...` for a reply to a comment, `t3_...` for a top-level comment on a post.
    parent_id: str | None = None
    link_id: str | None = None
    score: int | None = None
    is_submitter: bool | None = None
    distinguished: str | None = None
    stickied: bool | None = None
    score_hidden: bool | None = None
    controversiality: int | None = None

    # Either an empty string (no replies) or a nested Listing of replies. Parsed lazily by the
    # adapter's tree walk rather than typed here, because the shape is recursive.
    replies: Any = None
