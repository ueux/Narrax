"""The source-adapter contract.

A **source adapter** is the only component that knows a platform's API. Everything above it
works with `NormalizedDiscussion`, so adding a platform means writing one adapter — not
touching the pipeline.

The contract is deliberately small: search for discussions, and fetch one discussion's
comments. Pagination, rate limiting, retries and payload parsing are the adapter's problem,
hidden behind these two methods.

References: docs/ingestion.md · docs/adr/0008-reddit-only-ingestion.md
"""

from collections.abc import Iterator
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from app.ingestion.normalized import DiscussionKind, NormalizedDiscussion

# Supported sort orders across platforms (adapters map these to their own values).
SORT_ORDERS = ("relevance", "new", "top", "comments")
TIME_FILTERS = ("hour", "day", "week", "month", "year", "all")


class IngestionError(Exception):
    """Base class for every ingestion failure.

    Raised errors always carry enough context to act on: adapters must not swallow a failure
    and return an empty result, because "no data" and "the request failed" mean very different
    things downstream (NFR-12).
    """


class SourceConfigurationError(IngestionError):
    """The adapter is not usable as configured (missing credentials, bad URL, ...)."""


class SourceAuthError(IngestionError):
    """The platform rejected our credentials. Terminal — retrying cannot help."""


class SourceRateLimitedError(IngestionError):
    """The platform refused the request because of rate limits, after the retry budget."""


class SourceUnavailableError(IngestionError):
    """The platform could not be reached, or returned a server error."""


class SourceResponseError(IngestionError):
    """The platform returned a payload we cannot interpret."""


@dataclass(slots=True)
class CollectionStats:
    """What an adapter saw, and what it deliberately did not yield.

    Adapters mutate their own instance while yielding; the collection service reads it afterwards
    and records it on the run. Without this, "we collected 800 items" would hide the fact that
    4,000 were examined and 3,200 fell outside the window (docs/data-flow.md DF-6).
    """

    posts_seen: int = 0
    posts_yielded: int = 0
    comments_seen: int = 0
    comments_yielded: int = 0
    skipped_malformed: int = 0
    skipped_out_of_window: int = 0
    skipped_out_of_scope: int = 0
    skipped_duplicate_id: int = 0

    @property
    def skipped_total(self) -> int:
        return (
            self.skipped_malformed
            + self.skipped_out_of_window
            + self.skipped_out_of_scope
            + self.skipped_duplicate_id
        )

    def as_dict(self) -> dict[str, int]:
        """Plain dict for JSONB storage."""
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SourceQuery:
    """What to collect, expressed without reference to any platform."""

    # Empty by default: browsing a community needs no search terms, and `__post_init__` rejects a
    # query that specifies neither.
    terms: tuple[str, ...] = ()
    communities: tuple[str, ...] = ()
    since: datetime | None = None
    until: datetime | None = None
    limit: int = 100
    sort: str = "relevance"
    time_filter: str = "year"
    include_comments: bool = True
    comment_limit: int = 100

    def __post_init__(self) -> None:
        if not self.terms and not self.communities:
            raise ValueError("a query needs at least one search term or community")
        if self.sort not in SORT_ORDERS:
            raise ValueError(f"sort must be one of {SORT_ORDERS}, got {self.sort!r}")
        if self.time_filter not in TIME_FILTERS:
            raise ValueError(f"time_filter must be one of {TIME_FILTERS}, got {self.time_filter!r}")
        if self.limit <= 0:
            raise ValueError("limit must be positive")
        if self.comment_limit < 0:
            raise ValueError("comment_limit cannot be negative")
        if self.since and self.until and self.until < self.since:
            raise ValueError("until cannot be earlier than since")

    @property
    def search_text(self) -> str:
        """Terms joined the way a platform search expects."""
        return " ".join(self.terms)

    def in_window(self, moment: datetime) -> bool:
        """Whether a source timestamp falls inside the requested window."""
        if self.since is not None and moment < self.since:
            return False
        return not (self.until is not None and moment > self.until)


@runtime_checkable
class SourceAdapter(Protocol):
    """A replaceable platform integration.

    Implementations yield **normalized** items, so no caller ever sees a platform payload.
    They must be lazy (generators), so a caller can stop early without wasted requests.
    """

    stats: CollectionStats
    """Counters the adapter maintains while yielding, read after a run to explain what it
    skipped and why."""

    @property
    def key(self) -> str:
        """Stable machine key of the platform, e.g. `"reddit"`. Matches `sources.key`."""
        ...

    def search_discussions(self, query: SourceQuery) -> Iterator[NormalizedDiscussion]:
        """Yield top-level posts matching the query, newest-agnostic and de-duplicated."""
        ...

    def fetch_comments(
        self, discussion: NormalizedDiscussion, *, limit: int
    ) -> Iterator[NormalizedDiscussion]:
        """Yield the comments belonging to one post, parents before children."""
        ...


def is_post(item: NormalizedDiscussion) -> bool:
    """Whether a normalized item is a top-level post."""
    return item.kind == DiscussionKind.POST
