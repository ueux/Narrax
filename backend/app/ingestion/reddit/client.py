"""Reddit HTTP client: OAuth, pacing, retries, and pagination.

Everything platform-mechanical lives here so the adapter above it reads like a domain operation:

* **Authentication** — application-only OAuth (`client_credentials`), with the bearer token
  cached and transparently refreshed once on a 401.
* **Pacing** — a minimum interval between requests, *and* honouring the `x-ratelimit-*` headers
  Reddit sends on every response. Two mechanisms because they catch different problems: pacing
  prevents self-inflicted bursts, the headers prevent being throttled by the server.
* **Retries** — bounded, with exponential backoff, honouring `Retry-After`. Rate limits and
  server errors are retried; authentication and malformed responses are not, because retrying
  cannot fix them.
* **Pagination** — `iter_listing` follows the `after` cursor lazily, so a caller that stops early
  stops making requests.

The `sleeper` and `clock` are injectable, which is what makes the rate-limiting behaviour
testable without a single real second passing.

Reference: <https://www.reddit.com/dev/api> · docs/ingestion.md §6
"""

import contextlib
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import ValidationError

from app.ingestion.base import (
    SourceAuthError,
    SourceConfigurationError,
    SourceRateLimitedError,
    SourceResponseError,
    SourceUnavailableError,
)
from app.ingestion.reddit.schemas import RedditListing

DEFAULT_BASE_URL = "https://oauth.reddit.com"
DEFAULT_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"

# Reddit caps a listing page at 100 items.
MAX_PAGE_SIZE = 100


@dataclass(frozen=True, slots=True)
class RedditCredentials:
    """OAuth application credentials.

    Read from the environment by `app.config.settings`; never logged and never persisted.
    """

    client_id: str
    client_secret: str
    user_agent: str

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.user_agent)


class RateLimiter:
    """Client-side pacing plus server-signalled backoff.

    Instrumented (`sleep_count`, `total_slept`) so tests can assert *that* pacing happened
    without waiting for it.
    """

    def __init__(
        self,
        *,
        min_interval_seconds: float = 1.0,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.min_interval_seconds = max(0.0, min_interval_seconds)
        self.sleep_count = 0
        self.total_slept = 0.0
        self._sleeper = sleeper
        self._clock = clock
        self._last_request_at: float | None = None

    def before_request(self) -> None:
        """Space requests out by at least the configured interval."""
        if self._last_request_at is not None:
            elapsed = self._clock() - self._last_request_at
            remaining = self.min_interval_seconds - elapsed
            if remaining > 0:
                self._sleep(remaining)
        self._last_request_at = self._clock()

    def observe(self, headers: Mapping[str, str]) -> None:
        """Honour Reddit's rate-limit headers.

        When the quota is exhausted, wait out the advertised window rather than discovering the
        limit through a 429.
        """
        remaining_header = headers.get("x-ratelimit-remaining")
        if remaining_header is None:
            return
        try:
            remaining = float(remaining_header)
        except ValueError:
            return
        if remaining > 0:
            return

        seconds = 1.0
        reset_header = headers.get("x-ratelimit-reset")
        if reset_header is not None:
            with contextlib.suppress(ValueError):
                seconds = max(1.0, float(reset_header))
        self._sleep(seconds)

    def backoff(self, seconds: float) -> None:
        self._sleep(max(0.0, seconds))

    def _sleep(self, seconds: float) -> None:
        self.sleep_count += 1
        self.total_slept += seconds
        self._sleeper(seconds)


class RedditClient:
    """A minimal, polite client for the endpoints NarraX needs."""

    def __init__(
        self,
        credentials: RedditCredentials,
        *,
        transport: httpx.BaseTransport | None = None,
        base_url: str = DEFAULT_BASE_URL,
        token_url: str = DEFAULT_TOKEN_URL,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        retry_backoff_seconds: float = 2.0,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        if not credentials.is_configured():
            raise SourceConfigurationError(
                "Reddit credentials are incomplete: set REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET "
                "and REDDIT_USER_AGENT."
            )

        self._credentials = credentials
        self._base_url = base_url.rstrip("/")
        self._token_url = token_url
        self._max_retries = max(0, max_retries)
        self._retry_backoff_seconds = retry_backoff_seconds
        self._limiter = rate_limiter or RateLimiter()
        self._token: str | None = None
        self._http = httpx.Client(
            transport=transport,
            timeout=timeout_seconds,
            headers={"User-Agent": credentials.user_agent},
            follow_redirects=False,
        )

    # --- lifecycle ------------------------------------------------------------------

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "RedditClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    @property
    def rate_limiter(self) -> RateLimiter:
        return self._limiter

    # --- authentication -------------------------------------------------------------

    def _access_token(self, *, force: bool = False) -> str:
        """Return a bearer token, requesting one if needed."""
        if self._token is not None and not force:
            return self._token

        self._limiter.before_request()
        response = self._http.post(
            self._token_url,
            data={"grant_type": "client_credentials"},
            auth=(self._credentials.client_id, self._credentials.client_secret),
        )

        if response.status_code in (401, 403):
            raise SourceAuthError("Reddit rejected the application credentials")
        if response.status_code >= 400:
            raise SourceUnavailableError(f"Reddit token endpoint returned {response.status_code}")

        try:
            payload = response.json()
        except ValueError as exc:  # pragma: no cover - defensive
            raise SourceResponseError("token response was not JSON") from exc

        token = payload.get("access_token")
        if not token:
            raise SourceResponseError("token response contained no access_token")
        self._token = str(token)
        return self._token

    # --- requests -------------------------------------------------------------------

    def _retry_delay(self, attempt: int, response: httpx.Response) -> float:
        """`Retry-After` when the server sends it, otherwise exponential backoff."""
        retry_after = response.headers.get("retry-after")
        if retry_after:
            try:
                return max(1.0, float(retry_after))
            except ValueError:
                pass
        return self._retry_backoff_seconds * (2**attempt)

    def get(self, path: str, *, params: Mapping[str, str] | None = None) -> Any:
        """GET a Reddit API path, returning decoded JSON.

        Raises a specific `IngestionError` subclass for every failure mode, so callers can
        distinguish "retry later" from "give up".
        """
        url = f"{self._base_url}{path}"
        attempt = 0
        token_refreshed = False

        while True:
            self._limiter.before_request()
            response = self._http.get(
                url,
                params=dict(params or {}),
                headers={"Authorization": f"Bearer {self._access_token()}"},
            )
            self._limiter.observe(response.headers)
            status = response.status_code

            if status == 200:
                try:
                    return response.json()
                except ValueError as exc:
                    raise SourceResponseError(f"{path} returned non-JSON content") from exc

            if status == 401 and not token_refreshed:
                # An expired token is expected over a long run; refresh once, then give up.
                token_refreshed = True
                self._token = None
                continue

            if status == 429:
                if attempt >= self._max_retries:
                    raise SourceRateLimitedError(
                        f"Reddit rate-limited {path} after {attempt + 1} attempts"
                    )
                self._limiter.backoff(self._retry_delay(attempt, response))
                attempt += 1
                continue

            if 500 <= status < 600:
                if attempt >= self._max_retries:
                    raise SourceUnavailableError(
                        f"Reddit returned {status} for {path} after {attempt + 1} attempts"
                    )
                self._limiter.backoff(self._retry_delay(attempt, response))
                attempt += 1
                continue

            if status in (401, 403):
                raise SourceAuthError(f"Reddit denied access to {path} (HTTP {status})")
            if status == 404:
                raise SourceResponseError(f"{path} does not exist (HTTP 404)")

            raise SourceResponseError(f"{path} returned unexpected HTTP {status}")

    def iter_listing(
        self, path: str, *, params: Mapping[str, str] | None = None, limit: int
    ) -> Iterator[dict[str, Any]]:
        """Yield a listing's item payloads, following the `after` cursor.

        Lazy: nothing is requested beyond what the caller consumes, so a bounded collection run
        makes a bounded number of calls.
        """
        after: str | None = None
        yielded = 0

        while yielded < limit:
            page_params: dict[str, str] = dict(params or {})
            page_params["limit"] = str(min(MAX_PAGE_SIZE, limit - yielded))
            if after:
                page_params["after"] = after

            payload = self.get(path, params=page_params)
            try:
                listing = RedditListing.model_validate(payload)
            except ValidationError as exc:
                raise SourceResponseError(f"{path} returned an unexpected listing shape") from exc

            children = listing.data.children
            if not children:
                return

            for child in children:
                if child.kind == "more":
                    # A "load more" placeholder carries no content of its own.
                    continue
                yield child.data
                yielded += 1
                if yielded >= limit:
                    return

            after = listing.data.after
            if not after:
                return
