# ADR-0012: Alembic for all schema changes

- **Status:** Accepted
- **Date:** 2026-03-10
- **Related:** [architecture.md](../architecture.md) · [data-flow.md §5](../data-flow.md#5-layer--storage--consumers)

## Context

The schema will change repeatedly: Phase 1 adds source-truth tables, Phase 2 adds embedding
and cluster tables, Phase 3+ add stance/narrative/evidence/relation/temporal tables. Some
changes are structural rather than additive (indexes for vector search, constraints that
enforce the provenance chain, enum-like stance labels).

Because derived data must stay explainable across model versions (ADR-0009), an incorrectly
migrated schema can silently destroy the ability to answer "which version produced this?".
Schema changes therefore need to be **reviewable, ordered, and reversible**.

## Decision

Manage **every** schema change through **Alembic migrations**.

- Migrations are the only mechanism that alters the schema — including enabling the
  `pgvector` extension (migration `0001`).
- The database URL is injected from application settings (`config/settings.py`), never
  hard-coded in `alembic.ini`.
- Models are imported into `alembic/env.py` so autogenerate sees `Base.metadata`.
- AI-assistants and developers may use autogenerate, but the generated migration is
  reviewed and hand-corrected before commit.

## Consequences

### Positive

- **Ordered, auditable schema history** — the schema's evolution is part of the repository.
- **Reproducible environments.** A fresh clone plus `alembic upgrade head` produces the exact
  expected schema, including the vector column and indexes.
- **Reversible changes.** Every migration defines `downgrade`, so a bad change can be backed
  out during development.
- **No drift between models and database**, because the same metadata drives autogenerate.
- **Constraints that enforce ADR-0009** (foreign keys along the provenance chain) are created
  as part of versioned migrations rather than ad-hoc SQL.

### Negative / costs

- **Two-step changes.** Editing a model is not enough; a migration must accompany it, or
  tests pass against a stale schema.
- **Merge conflicts** in migration chains when branches add migrations concurrently —
  resolved by re-anchoring down-revisions.
- **Autogenerate is imperfect** (it misses some index/constraint nuances), so review is
  mandatory.
- **Extension coupling.** The initial migration assumes `pgvector` is installable in the
  target environment (guaranteed by the compose image).

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| `Base.metadata.create_all()` | Unversioned; cannot alter existing tables; no history; unusable for vector indexes |
| Hand-written SQL scripts | No ordering guarantees, no state tracking, easy to drift |
| Framework-agnostic migration tool | Adds a dependency without benefit; Alembic integrates with SQLAlchemy metadata |
| Recreate the database each change | Unacceptable once source truth exists — it would destroy Layer 1 |

## Revisit trigger

Do not revisit while SQLAlchemy remains the ORM. If the persistence layer is ever replaced,
its schema-management tooling replaces Alembic — and the migration history becomes the
reference for reconstructing the schema.
