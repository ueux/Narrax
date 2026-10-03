"""Shared parsing helpers for Reddit listing trees.

Used by **both** the live adapter and the recorded-payload adapter, which is the point: replaying
captured payloads exercises the same traversal code as production collection, so a fixture can
never pass against a divergent implementation.
"""

from collections import deque
from collections.abc import Iterator
from typing import Any


def children_of(payload: Any) -> list[dict[str, Any]]:
    """Children of a listing payload, tolerating Reddit's quirks.

    Reddit writes `""` (an empty string, not an object) for "this comment has no replies", and a
    `more` placeholder where it truncated a subtree. This returns an empty list for anything that
    is not a listing rather than raising, because "no children" is a normal state.
    """
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    children = data.get("children")
    if not isinstance(children, list):
        return []
    return [child for child in children if isinstance(child, dict)]


def iter_comment_tree(listing_payload: Any, *, remaining: int) -> Iterator[dict[str, Any]]:
    """Breadth-first walk of a comment listing, descending into nested replies.

    Breadth-first is a deliberate choice, not an implementation detail: it guarantees a comment is
    emitted only after its parent, which is what lets the collection service rely on the database's
    self-referencing foreign key instead of sorting comments itself.
    """
    queue: deque[dict[str, Any]] = deque(children_of(listing_payload))
    produced = 0

    while queue and produced < remaining:
        node = queue.popleft()
        if node.get("kind") != "t1":
            # `more` placeholders and anything non-comment carry no content.
            continue
        data = node.get("data")
        if not isinstance(data, dict):
            continue

        yield data
        produced += 1
        queue.extend(children_of(data.get("replies")))
