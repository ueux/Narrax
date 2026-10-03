# ADR-0003: Synchronous SQLAlchemy + psycopg 3

- **Status:** Accepted
- **Date:** 2026-03-10
- **Related:** [architecture.md](../architecture.md#31-backend-package-layout)

## Context

The backend has two distinct workloads:

1. **A batch analysis pipeline** — long-running, CPU/IO heavy, essentially sequential, and
   dominated by model inference rather than database round-trips.
2. **A read-only HTTP API** — small, frequent queries that a client waits on.

FastAPI supports both `def` (threadpool) and `async def` handlers; SQLAlchemy supports sync
and async engines. Choosing async everywhere implies `asyncpg`/`psycopg` async, async
sessions, async Alembic, and async-aware test fixtures.

## Decision

Use **synchronous SQLAlchemy 2.0 with the psycopg 3 driver**. FastAPI endpoints that touch
the database are declared as plain `def`, so FastAPI runs them in a worker thread and the
event loop is not blocked.

## Consequences

### Positive

- **The pipeline is naturally sync.** Batch stages read, compute, and write in sequence;
  async would add `await` noise around CPU-bound work that cannot overlap anyway.
- **One mental model.** The same `Session` pattern is used in the pipeline, the API, tests,
  and Alembic.
- **Simpler ecosystem.** Sync SQLAlchemy has the deepest support: Alembic autogenerate,
  test fixtures, type stubs.
- **No event-loop footguns** (accidental blocking calls, `greenlet` context issues).
- **Performance is adequate.** At MVP read volume, threadpool concurrency is not the
  bottleneck; database queries are.

### Negative / costs

- Concurrency is bounded by the threadpool size for DB-touching endpoints.
- A future high-fan-out, IO-bound endpoint pattern would need `run_in_threadpool` tuning or
  a targeted async path.
- Anyone assuming "FastAPI ⇒ async" may be surprised; documented here and in the README.

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| Async SQLAlchemy everywhere | Complexity without benefit: the dominant cost is model inference, not DB IO |
| Mixed sync/async engines | Two session types, two test paths, easy to get wrong; adopt only for a proven hotspot |
| Raw SQL / query builder | Loses models, typed queries, and migration autogenerate |

## Revisit trigger

A **measured** endpoint that is IO-bound and concurrency-limited by the threadpool under
real load. Escalate that endpoint (or the read path) deliberately — do not rewrite the
backend speculatively.
