"""A scripted stand-in for Reddit's API.

Shared by the client tests and the adapter tests so both exercise the same transport-level
behaviour: no network, no real waiting, and a request log to assert against.
"""

from collections.abc import Sequence
from typing import Any

import httpx

from app.ingestion.reddit.client import RateLimiter, RedditClient, RedditCredentials

TOKEN_PATH = "/api/v1/access_token"


class FakeReddit:
    """Routes requests by path, records them, and counts token exchanges."""

    def __init__(
        self,
        routes: dict[str, Any] | None = None,
        *,
        token_status: int = 200,
        token: str = "test-token",
    ) -> None:
        self.routes = routes or {}
        self.token_status = token_status
        self.token = token
        self.token_requests = 0
        self.api_requests: list[httpx.Request] = []
        self.slept: list[float] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == TOKEN_PATH:
            self.token_requests += 1
            if self.token_status != 200:
                return httpx.Response(self.token_status, json={})
            return httpx.Response(200, json={"access_token": self.token, "expires_in": 3600})

        self.api_requests.append(request)
        route = self.routes.get(request.url.path)
        if route is None:
            return httpx.Response(404, json={"message": "not found"})
        if callable(route):
            return route(request)
        return route

    def client(self, **kwargs: Any) -> RedditClient:
        credentials = RedditCredentials(
            client_id="client-id", client_secret="client-secret", user_agent="narrax-tests/0.1"
        )
        limiter = RateLimiter(
            min_interval_seconds=0.0,
            sleeper=self.slept.append,
            clock=lambda: 0.0,
        )
        return RedditClient(
            credentials,
            transport=httpx.MockTransport(self.handler),
            rate_limiter=limiter,
            retry_backoff_seconds=1.0,
            **kwargs,
        )


def listing(children: Sequence[dict[str, Any]], after: str | None = None) -> dict[str, Any]:
    """A Reddit listing envelope."""
    return {"kind": "Listing", "data": {"children": list(children), "after": after}}


def post_thing(post_id: str, **overrides: Any) -> dict[str, Any]:
    """A `t3` thing with the minimum fields normalization requires."""
    data: dict[str, Any] = {
        "id": post_id,
        "name": f"t3_{post_id}",
        "subreddit": "technology",
        "title": f"A post about the audit bill ({post_id})",
        "selftext": "The proposed bill would require an independent audit before deployment.",
        "author": "someone",
        "created_utc": 1705320000,
        "permalink": f"/r/technology/comments/{post_id}/a_post/",
    }
    data.update(overrides)
    return {"kind": "t3", "data": data}


def comment_thing(
    comment_id: str, *, parent_id: str, replies: Any = "", **overrides: Any
) -> dict[str, Any]:
    """A `t1` thing, optionally carrying nested replies."""
    data: dict[str, Any] = {
        "id": comment_id,
        "name": f"t1_{comment_id}",
        "subreddit": "technology",
        "parent_id": parent_id,
        "link_id": "t3_a1b2c3",
        "body": f"A comment about the audit threshold ({comment_id}).",
        "author": "commenter",
        "created_utc": 1705323600,
        "permalink": f"/r/technology/comments/a1b2c3/x/{comment_id}/",
        "score": 10,
        "replies": replies,
    }
    data.update(overrides)
    return {"kind": "t1", "data": data}


def comments_payload(post: dict[str, Any], comments: Sequence[dict[str, Any]]) -> list[Any]:
    """The two-element `[post listing, comment listing]` shape `/comments/{id}` returns."""
    return [listing([post]), listing(comments)]
