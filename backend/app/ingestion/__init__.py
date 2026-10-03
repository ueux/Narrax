"""Ingestion boundary — **Layer 1: source truth**, plus the text-preparation record.

Everything about *acquiring* public discussion data and getting it into a canonical, analysable
form lives here, and nothing else does.

Responsibilities
----------------
- Talk to the source platform — authentication, pagination, rate limits, retries.
- Normalise platform payloads into the source-neutral `NormalizedDiscussion` model, so no
  platform shape or sentinel string leaks into the rest of the system (PROMPT 14).
- Clean text deterministically and decide what is analysable, recording **why** anything is
  excluded (PROMPT 15).
- Idempotently upsert Layer 1 rows (natural key: `source` + `external_id`), so re-running a
  window never duplicates and never rewrites authored content.

Layout
------
    base.py        # SourceAdapter contract, SourceQuery, CollectionStats, error hierarchy
    normalized.py  # the normalized discussion model (the contract with everything above)
    language.py    # deterministic, dependency-free language detection
    cleaning.py    # the text-cleaning pipeline and exclusion vocabulary
    reddit/        # the one platform integration (live + recorded)

Must not
--------
- Embed, cluster, score sentiment or stance, or extract narratives. Those belong to
  `app.intelligence`.
- Enrich, link, or profile authors. Authors are opaque pseudonymous handles only
  (docs/data-safety.md).
- Let a platform's field names or sentinel strings escape `ingestion/reddit/`.

Platform adapters are **not** re-exported here on purpose: importing this package must not
require an HTTP client, and a caller that wants Reddit should say so explicitly by importing
`app.ingestion.reddit`.

References: docs/ingestion.md · docs/data-flow.md §3 (S1, S2)
"""

from app.ingestion.base import (
    CollectionStats,
    IngestionError,
    SourceAdapter,
    SourceAuthError,
    SourceConfigurationError,
    SourceQuery,
    SourceRateLimitedError,
    SourceResponseError,
    SourceUnavailableError,
)
from app.ingestion.cleaning import (
    DEFAULT_CLEANING_RULES,
    CleaningResult,
    CleaningRules,
    DuplicateCandidate,
    ExclusionReason,
    clean_text,
    find_duplicate_indices,
    rules_version,
)
from app.ingestion.language import (
    DEFAULT_LANGUAGE_DETECTOR,
    HeuristicLanguageDetector,
    LanguageDetector,
    LanguageGuess,
)
from app.ingestion.normalized import (
    ContentState,
    DiscussionKind,
    NormalizedDiscussion,
    NormalizedEngagement,
)

__all__ = [
    # contract
    "CollectionStats",
    "IngestionError",
    "SourceAdapter",
    "SourceAuthError",
    "SourceConfigurationError",
    "SourceQuery",
    "SourceRateLimitedError",
    "SourceResponseError",
    "SourceUnavailableError",
    # normalized model
    "ContentState",
    "DiscussionKind",
    "NormalizedDiscussion",
    "NormalizedEngagement",
    # cleaning
    "CleaningResult",
    "CleaningRules",
    "DEFAULT_CLEANING_RULES",
    "DuplicateCandidate",
    "ExclusionReason",
    "clean_text",
    "find_duplicate_indices",
    "rules_version",
    # language
    "DEFAULT_LANGUAGE_DETECTOR",
    "HeuristicLanguageDetector",
    "LanguageDetector",
    "LanguageGuess",
]
