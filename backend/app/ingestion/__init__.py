"""Ingestion boundary — **Layer 1: source truth**.

Everything about *acquiring* public discussion data lives here, and nothing else does.

Responsibilities
----------------
- Talk to the source platform (Reddit, official API) — auth, pagination, rate limits.
- Normalise platform payloads into the source-neutral Layer 1 shape.
- Idempotently upsert Layer 1 rows (natural key: `source` + `source_id`), so re-running a
  window never duplicates and never rewrites authored content.
- Record retrieval provenance (`retrieved_at`, permalink) and every exclusion *with a
  reason*.
- Retry transient failures with backoff; fail loudly on auth/rate errors.

Must not
--------
- Compute or store any derived value (embeddings, clusters, sentiment, stance,
  narratives). Those belong to `app.intelligence`.
- Be imported by `app.database` or `app.config` (dependency direction is one-way).
- Enrich, link, or profile authors. Authors are opaque pseudonymous handles only
  (docs/data-safety.md).

Planned layout (Phase 1)
------------------------
    ingestion/
    ├── base.py        # SourceAdapter contract: fetch → normalised items
    ├── reddit.py      # Reddit adapter (official API, OAuth)
    ├── normalize.py   # platform payload → Layer 1 shape
    └── filters.py     # exclusion rules + reasons

References: docs/data-flow.md §3 (S1, S2) · docs/adr/0008-reddit-only-ingestion.md
"""
