"""The Reddit source adapter.

Implements `SourceAdapter` on top of `RedditClient`, which means callers get
`NormalizedDiscussion` objects and never see a Reddit payload. This is the module that would be
replaced to support another platform; nothing above it changes (docs/adr/0008).

Two behaviours are worth calling out:

* **Posts are never dropped for being deleted.** A removed or deleted post is still real source
  truth — it was posted, and its existence is part of the record. The item is yielded with a
  `ContentState`, and the cleaning stage decides it is not analysable and says why.
* **Comments are yielded parents-first.** Breadth-first traversal guarantees that a comment's
  parent has already been persisted when the child arrives, so the self-referencing foreign key
  can never fail on ordering.
"""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime

from pydantic import ValidationError

from app.ingestion.base import CollectionStats, SourceQuery, SourceResponseError
from app.ingestion.normalized import NormalizedDiscussion
from app.ingestion.reddit.client import MAX_PAGE_SIZE, RedditClient
from app.ingestion.reddit.normalize import (
    SOURCE_KEY,
    bare_id,
    normalize_comment,
    normalize_post,
    timestamp,
)
from app.ingestion.reddit.parsing import iter_comment_tree
from app.ingestion.reddit.schemas import RedditComment, RedditPost

# Listing sorts Reddit accepts for `/r/{sub}/{sort}`; anything else is mapped to `new`.
_LISTING_SORTS = frozenset({"new", "top", "hot", "controversial", "rising"})
# Sorts for which the `t` time-filter parameter is meaningful.
_SORTS_USING_TIME_FILTER = frozenset({"top", "controversial"})


def _utcnow() -> datetime:
    return datetime.now(UTC)


class RedditSourceAdapter:
    """Collects normalized discussions from Reddit's official API."""

    def __init__(
        self,
        client: RedditClient,
        *,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._client = client
        self._clock = clock
        self.stats = CollectionStats()

    @property
    def key(self) -> str:
        return SOURCE_KEY

    # --- search ---------------------------------------------------------------------

    def search_discussions(self, query: SourceQuery) -> Iterator[NormalizedDiscussion]:
        """Yield posts matching `query`, in the order the platform returns them."""
        requests = self.search_requests(query)
        if not requests:
            return

        # `limit` is a budget for the whole query, split evenly across requests so that a
        # multi-community query is not dominated by whichever community happens to be first.
        per_request = max(1, query.limit // len(requests))
        seen_ids: set[str] = set()

        for path, params in requests:
            for raw in self._client.iter_listing(path, params=params, limit=per_request):
                self.stats.posts_seen += 1
                try:
                    post = RedditPost.model_validate(raw)
                except ValidationError:
                    # One unexpected payload must not abort a collection run; it is counted so
                    # the run report shows it rather than hiding it.
                    self.stats.skipped_malformed += 1
                    continue

                if not query.in_window(timestamp(post.created_utc)):
                    self.stats.skipped_out_of_window += 1
                    continue

                item = normalize_post(post, collected_at=self._clock())
                if item.external_id in seen_ids:
                    self.stats.skipped_duplicate_id += 1
                    continue

                seen_ids.add(item.external_id)
                self.stats.posts_yielded += 1
                yield item

    def search_requests(self, query: SourceQuery) -> list[tuple[str, dict[str, str]]]:
        """Translate a `SourceQuery` into Reddit request paths and parameters.

        Split out so the mapping is directly testable: an API shape change should be visible in a
        test, not discovered in production.
        """
        requests: list[tuple[str, dict[str, str]]] = []
        time_filter = {"t": query.time_filter}

        if query.terms:
            search_params = {"q": query.search_text, "sort": query.sort, "type": "link"}
            if query.communities:
                for community in query.communities:
                    requests.append(
                        (
                            f"/r/{community}/search",
                            {**search_params, "restrict_sr": "1", **time_filter},
                        )
                    )
            else:
                requests.append(("/search", {**search_params, **time_filter}))
            return requests

        # No terms: browse the communities directly.
        listing_sort = query.sort if query.sort in _LISTING_SORTS else "new"
        params = dict(time_filter) if listing_sort in _SORTS_USING_TIME_FILTER else {}
        for community in query.communities:
            requests.append((f"/r/{community}/{listing_sort}", params))
        return requests

    # --- comments -------------------------------------------------------------------

    def fetch_comments(
        self, discussion: NormalizedDiscussion, *, limit: int
    ) -> Iterator[NormalizedDiscussion]:
        """Yield a post's comments, parents before children."""
        if limit <= 0 or not discussion.is_post:
            return

        post_id = bare_id(discussion.external_id)
        payload = self._client.get(
            f"/comments/{post_id}",
            params={"limit": str(min(MAX_PAGE_SIZE, limit)), "sort": "top"},
        )

        if not isinstance(payload, list) or len(payload) < 2:
            raise SourceResponseError(
                f"/comments/{post_id} returned an unexpected payload (expected [post, comments])"
            )

        collected_at = self._clock()
        for raw in iter_comment_tree(payload[1], remaining=limit):
            self.stats.comments_seen += 1
            try:
                comment = RedditComment.model_validate(raw)
            except ValidationError:
                self.stats.skipped_malformed += 1
                continue

            item = normalize_comment(
                comment, collected_at=collected_at, post_external_id=discussion.external_id
            )
            self.stats.comments_yielded += 1
            yield item
