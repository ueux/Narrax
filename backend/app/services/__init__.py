"""Services boundary — **use-cases and orchestration**.

The only place that knows a *whole workflow*. A service composes ingestion,
intelligence, and database access into something a caller wants to do — and owns the
transaction and error semantics of that workflow.

Responsibilities
----------------
- Orchestrate pipeline stages and record per-stage execution (status, counts, drops,
  durations, versions).
- Assemble read models for the API (e.g. "a topic's narratives with evidence, provenance,
  and corpus scope").
- Enforce domain rules that span layers — most importantly the **publishability gate**
  (no narrative without evidence) and aggregate-only output (minimum group size).
- Map domain failures to typed errors; never swallow exceptions.

Must not
--------
- Duplicate algorithm code that belongs in `app.intelligence`.
- Open ad-hoc database sessions outside the injected session lifecycle.
- Know about HTTP (status codes, request objects). Mapping errors to HTTP is `app.api`'s job.

Planned layout
--------------
    services/
    ├── topics.py      # create/read topics, selection criteria
    ├── pipeline.py    # run + resume the batch pipeline
    └── read_models.py # topic/narrative/evidence views for the API

References: docs/architecture.md §3.2, §5 · docs/data-flow.md §4
"""
