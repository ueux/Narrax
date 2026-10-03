"""Replaying recorded platform payloads — ingestion without credentials or network.

Live collection needs OAuth credentials and outbound network access. Neither is always
available: in CI, offline, or while iterating on the pipeline. This adapter replays payloads
captured from the real API through the **same** normalization and parsing code as live
collection, so a fixture exercises production behaviour rather than a parallel mock that can
drift from it.

The recorded corpus is a subset by design: a post with no matching comment file simply has no
recorded comments, which is stated here rather than treated as an error.

References: docs/ingestion.md §7
"""

import json
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.ingestion.base import (
    CollectionStats,
    SourceConfigurationError,
    SourceQuery,
    SourceResponseError,
)
from app.ingestion.normalized import NormalizedDiscussion
from app.ingestion.reddit.normalize import (
    SOURCE_KEY,
    normalize_comment,
    normalize_post,
    timestamp,
)
from app.ingestion.reddit.parsing import children_of, iter_comment_tree
from app.ingestion.reddit.schemas import RedditComment, RedditPost

SEARCH_FILENAME = "search_response.json"
COMMENTS_FILENAME_TEMPLATE = "comments_{external_id}.json"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class RecordedRedditAdapter:
    """Serves Reddit payloads from a directory of recorded API responses."""

    def __init__(self, directory: Path | str, *, clock: Callable[[], datetime] = _utcnow) -> None:
        self._directory = Path(directory)
        if not self._directory.is_dir():
            raise SourceConfigurationError(
                f"recorded payload directory does not exist: {self._directory}"
            )
        self._clock = clock
        self.stats = CollectionStats()

    @property
    def key(self) -> str:
        return SOURCE_KEY

    # --- reading --------------------------------------------------------------------

    def _read_json(self, path: Path) -> Any:
        try:
            with path.open(encoding="utf-8") as handle:
                return json.load(handle)
        except json.JSONDecodeError as exc:
            raise SourceResponseError(f"{path.name} is not valid JSON: {exc}") from exc

    def _search_payloads(self) -> list[dict[str, Any]]:
        """Listings from the recorded search response (a single listing, or a list of them)."""
        path = self._directory / SEARCH_FILENAME
        if not path.is_file():
            raise SourceConfigurationError(f"missing recorded search payload: {path}")

        payload = self._read_json(path)
        if isinstance(payload, dict):
            return [payload]
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        raise SourceResponseError(f"{path.name} is neither a listing nor a list of listings")

    # --- SourceAdapter --------------------------------------------------------------

    def search_discussions(self, query: SourceQuery) -> Iterator[NormalizedDiscussion]:
        communities = {name.lower() for name in query.communities}
        seen_ids: set[str] = set()
        yielded = 0

        for payload in self._search_payloads():
            for node in children_of(payload):
                if yielded >= query.limit:
                    return
                if node.get("kind") != "t3":
                    continue
                data = node.get("data")
                if not isinstance(data, dict):
                    continue

                self.stats.posts_seen += 1
                try:
                    post = RedditPost.model_validate(data)
                except ValidationError:
                    self.stats.skipped_malformed += 1
                    continue

                if communities and post.subreddit.lower() not in communities:
                    self.stats.skipped_out_of_scope += 1
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
                yielded += 1
                yield item

    def fetch_comments(
        self, discussion: NormalizedDiscussion, *, limit: int
    ) -> Iterator[NormalizedDiscussion]:
        if limit <= 0 or not discussion.is_post:
            return

        path = self._directory / COMMENTS_FILENAME_TEMPLATE.format(
            external_id=discussion.external_id
        )
        if not path.is_file():
            return

        payload = self._read_json(path)
        if not isinstance(payload, list) or len(payload) < 2:
            raise SourceResponseError(f"{path.name} is not a [post, comments] payload")

        collected_at = self._clock()
        for raw in iter_comment_tree(payload[1], remaining=limit):
            self.stats.comments_seen += 1
            try:
                comment = RedditComment.model_validate(raw)
            except ValidationError:
                self.stats.skipped_malformed += 1
                continue

            self.stats.comments_yielded += 1
            yield normalize_comment(
                comment, collected_at=collected_at, post_external_id=discussion.external_id
            )
