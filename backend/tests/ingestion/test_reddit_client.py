"""The Reddit HTTP client, exercised against mocked API responses (PROMPT 13).

No network and no real waiting: pacing is asserted through the limiter's own instrumentation, which
is why the sleeper is injectable. Every branch that decides "retry" versus "give up" is covered,
because getting that wrong either hammers Reddit or silently loses data.
"""

import httpx
import pytest

from app.ingestion.base import (
    SourceAuthError,
    SourceConfigurationError,
    SourceRateLimitedError,
    SourceResponseError,
    SourceUnavailableError,
)
from app.ingestion.reddit.client import RateLimiter, RedditClient, RedditCredentials
from tests.ingestion.fake_reddit import TOKEN_PATH, FakeReddit, listing, post_thing

# --- configuration -------------------------------------------------------------------------


def test_incomplete_credentials_fail_fast() -> None:
    with pytest.raises(SourceConfigurationError):
        RedditClient(RedditCredentials(client_id="", client_secret="", user_agent=""))


def test_user_agent_is_sent_on_every_request() -> None:
    """Reddit blocks generic user agents, so this is a functional requirement, not politeness."""
    fake = FakeReddit({"/r/technology/new": httpx.Response(200, json=listing([]))})
    with fake.client() as client:
        list(client.iter_listing("/r/technology/new", limit=1))

    assert fake.api_requests[0].headers["user-agent"] == "narrax-tests/0.1"


# --- authentication ------------------------------------------------------------------------


def test_token_is_fetched_once_and_reused() -> None:
    fake = FakeReddit(
        {
            "/a": httpx.Response(200, json=listing([post_thing("p1")])),
            "/b": httpx.Response(200, json=listing([post_thing("p2")])),
        }
    )
    with fake.client() as client:
        client.get("/a")
        client.get("/b")

    assert fake.token_requests == 1
    assert fake.api_requests[0].headers["authorization"] == "Bearer test-token"


def test_expired_token_is_refreshed_once_and_the_request_retried() -> None:
    calls = {"count": 0}

    def route(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(401, json={"message": "unauthorized"})
        return httpx.Response(200, json=listing([post_thing("p1")]))

    fake = FakeReddit({"/a": route})
    with fake.client() as client:
        payload = client.get("/a")

    assert payload["data"]["children"][0]["data"]["id"] == "p1"
    assert fake.token_requests == 2, "a second token must be requested after a 401"
    assert len(fake.api_requests) == 2


def test_repeated_401_gives_up_rather_than_looping() -> None:
    fake = FakeReddit({"/a": httpx.Response(401, json={})})
    with fake.client() as client, pytest.raises(SourceAuthError):
        client.get("/a")

    assert len(fake.api_requests) == 2, "one original attempt plus one retry after refresh"


def test_forbidden_is_not_retried() -> None:
    """Retrying cannot fix a permissions problem, so it must not be attempted."""
    fake = FakeReddit({"/r/private/search": httpx.Response(403, json={})})
    with fake.client() as client, pytest.raises(SourceAuthError):
        client.get("/r/private/search")

    assert len(fake.api_requests) == 1


def test_rejected_credentials_raise_authentication_error() -> None:
    fake = FakeReddit(token_status=401)
    with fake.client() as client, pytest.raises(SourceAuthError):
        client.get("/a")


def test_token_endpoint_failure_is_reported_as_unavailable() -> None:
    fake = FakeReddit(token_status=503)
    with fake.client() as client, pytest.raises(SourceUnavailableError):
        client.get("/a")


def test_token_response_without_a_token_is_a_response_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == TOKEN_PATH:
            return httpx.Response(200, json={"token_type": "bearer"})
        return httpx.Response(200, json=listing([]))

    credentials = RedditCredentials(client_id="i", client_secret="s", user_agent="ua")
    client = RedditClient(credentials, transport=httpx.MockTransport(handler))
    with client, pytest.raises(SourceResponseError):
        client.get("/a")


# --- retries and rate limits ----------------------------------------------------------------


def test_rate_limit_is_retried_then_reported() -> None:
    fake = FakeReddit({"/a": httpx.Response(429, json={})})
    with fake.client(max_retries=1) as client, pytest.raises(SourceRateLimitedError):
        client.get("/a")

    assert len(fake.api_requests) == 2
    assert fake.slept, "a retry must wait before trying again"


def test_rate_limit_that_clears_is_recovered() -> None:
    calls = {"count": 0}

    def route(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(429, json={})
        return httpx.Response(200, json=listing([post_thing("p1")]))

    fake = FakeReddit({"/a": route})
    with fake.client() as client:
        client.get("/a")

    assert calls["count"] == 2


def test_retry_after_header_is_honoured() -> None:
    fake = FakeReddit({"/a": httpx.Response(429, json={}, headers={"Retry-After": "7"})})
    with fake.client(max_retries=1) as client, pytest.raises(SourceRateLimitedError):
        client.get("/a")

    assert fake.slept == [7.0]


def test_server_error_is_retried_with_growing_backoff() -> None:
    fake = FakeReddit({"/a": httpx.Response(500, json={})})
    with fake.client(max_retries=2) as client, pytest.raises(SourceUnavailableError):
        client.get("/a")

    assert len(fake.api_requests) == 3
    assert fake.slept == [1.0, 2.0]


def test_client_error_is_not_retried() -> None:
    fake = FakeReddit({"/a": httpx.Response(400, json={})})
    with fake.client() as client, pytest.raises(SourceResponseError):
        client.get("/a")

    assert len(fake.api_requests) == 1


def test_not_found_is_reported_as_a_response_error() -> None:
    fake = FakeReddit()
    with fake.client() as client, pytest.raises(SourceResponseError):
        client.get("/does/not/exist")


def test_non_json_success_body_is_rejected() -> None:
    fake = FakeReddit({"/a": httpx.Response(200, text="<html>not json</html>")})
    with fake.client() as client, pytest.raises(SourceResponseError):
        client.get("/a")


# --- pacing ---------------------------------------------------------------------------------


def test_exhausted_quota_pauses_until_the_advertised_reset() -> None:
    """Waiting out the window is better than discovering the limit through a 429."""
    fake = FakeReddit(
        {
            "/a": httpx.Response(
                200,
                json=listing([post_thing("p1")]),
                headers={"x-ratelimit-remaining": "0.0", "x-ratelimit-reset": "30"},
            )
        }
    )
    with fake.client() as client:
        client.get("/a")

    assert fake.slept == [30.0]


def test_remaining_quota_does_not_pause() -> None:
    fake = FakeReddit(
        {
            "/a": httpx.Response(
                200,
                json=listing([post_thing("p1")]),
                headers={"x-ratelimit-remaining": "98.0", "x-ratelimit-reset": "600"},
            )
        }
    )
    with fake.client() as client:
        client.get("/a")

    assert fake.slept == []


def test_minimum_interval_is_enforced_between_requests() -> None:
    # First clock read stamps the first request; the second shows only 0.2s elapsed, so the limiter
    # must wait out the remaining 0.8s of the one-second interval.
    ticks = iter([0.0, 0.2, 0.2])
    limiter = RateLimiter(
        min_interval_seconds=1.0, sleeper=lambda seconds: None, clock=lambda: next(ticks)
    )

    limiter.before_request()
    limiter.before_request()

    assert limiter.sleep_count == 1
    assert limiter.total_slept == pytest.approx(0.8)


def test_rate_limiter_tolerates_unparsable_headers() -> None:
    limiter = RateLimiter(sleeper=lambda seconds: None, clock=lambda: 0.0)

    limiter.observe({"x-ratelimit-remaining": "many", "x-ratelimit-reset": "soon"})
    limiter.observe({"x-ratelimit-remaining": "0", "x-ratelimit-reset": "soon"})

    assert limiter.sleep_count == 1, "the reset header is unusable, so the default pause is used"
    assert limiter.total_slept == 1.0


# --- pagination -----------------------------------------------------------------------------


def test_listing_follows_the_after_cursor() -> None:
    fake = FakeReddit(
        {
            "/search": lambda request: httpx.Response(
                200,
                json=listing(
                    [post_thing("p1"), post_thing("p2")],
                    after="t3_p2" if request.url.params.get("after") is None else None,
                ),
            )
        }
    )
    with fake.client() as client:
        items = list(client.iter_listing("/search", limit=10))

    assert [item["id"] for item in items] == ["p1", "p2", "p1", "p2"]
    assert len(fake.api_requests) == 2
    assert fake.api_requests[1].url.params["after"] == "t3_p2"


def test_listing_stops_at_the_limit_without_requesting_another_page() -> None:
    fake = FakeReddit(
        {
            "/search": lambda request: httpx.Response(
                200, json=listing([post_thing("p1"), post_thing("p2")], after="t3_p2")
            )
        }
    )
    with fake.client() as client:
        items = list(client.iter_listing("/search", limit=2))

    assert len(items) == 2
    assert len(fake.api_requests) == 1, "a satisfied limit must not trigger another request"


def test_listing_skips_more_placeholders() -> None:
    fake = FakeReddit(
        {
            "/search": httpx.Response(
                200,
                json=listing([post_thing("p1"), {"kind": "more", "data": {"count": 40}}]),
            )
        }
    )
    with fake.client() as client:
        items = list(client.iter_listing("/search", limit=5))

    assert [item["id"] for item in items] == ["p1"]


def test_empty_listing_terminates_immediately() -> None:
    fake = FakeReddit({"/search": httpx.Response(200, json=listing([]))})
    with fake.client() as client:
        assert list(client.iter_listing("/search", limit=5)) == []


def test_page_size_is_capped_at_the_platform_maximum() -> None:
    fake = FakeReddit(
        {"/search": lambda request: httpx.Response(200, json=listing([post_thing("p1")]))}
    )
    with fake.client() as client:
        list(client.iter_listing("/search", limit=500))

    assert fake.api_requests[0].url.params["limit"] == "100"


def test_malformed_listing_is_reported_rather_than_ignored() -> None:
    """A payload that is not a listing is an error, not an empty result.

    Treating it as "no items" would silently truncate a collection run, which is the failure mode
    this whole layer exists to prevent.
    """
    fake = FakeReddit({"/search": httpx.Response(200, json={"unexpected": "shape"})})
    with fake.client() as client, pytest.raises(SourceResponseError):
        list(client.iter_listing("/search", limit=5))


def test_listing_without_children_is_treated_as_empty() -> None:
    """Reddit omits `children` for an exhausted listing; that is an end, not an error."""
    fake = FakeReddit({"/search": httpx.Response(200, json={"kind": "Listing", "data": {}})})
    with fake.client() as client:
        assert list(client.iter_listing("/search", limit=5)) == []
