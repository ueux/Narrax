"""The Reddit integration.

Everything Reddit-specific lives under this package and **nothing above it may import from it**
except to construct an adapter. `RedditPost`, `RedditComment`, and the field names inside them
must not appear in `intelligence/`, `services/`, `api/`, or the CLI.

    reddit/
    ├── client.py     # OAuth, pacing, retries, pagination — the only place that does HTTP
    ├── schemas.py    # Reddit payload shapes (the only place that knows Reddit's field names)
    ├── normalize.py  # Reddit → NormalizedDiscussion (PROMPT 14's translation boundary)
    ├── parsing.py    # listing-tree traversal, shared with the recorded adapter
    ├── adapter.py    # SourceAdapter implementation over the live API
    └── recorded.py   # the same contract, replayed from recorded payloads

Adding a platform means adding a sibling package with the same shape; nothing else changes
(docs/adr/0008-reddit-only-ingestion.md).
"""

from app.ingestion.reddit.adapter import RedditSourceAdapter
from app.ingestion.reddit.client import RateLimiter, RedditClient, RedditCredentials
from app.ingestion.reddit.recorded import RecordedRedditAdapter

__all__ = [
    "RateLimiter",
    "RecordedRedditAdapter",
    "RedditClient",
    "RedditCredentials",
    "RedditSourceAdapter",
]
