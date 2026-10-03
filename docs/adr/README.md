# Architecture Decision Records

ADRs capture **decisions that shaped the architecture**, with their context and
consequences — so a future reader can tell *why* something is the way it is, and when it
would be right to change it.

## Format

Each ADR uses: **Status · Date · Context · Decision · Consequences · Alternatives ·
Revisit trigger**. Status is one of `Proposed`, `Accepted`, `Superseded by ADR-XXXX`,
`Deprecated`.

## Rules

1. An ADR is written when a decision is **hard to reverse** or **surprising to a new
   reader**.
2. ADRs are **immutable** once accepted. To change a decision, add a new ADR that
   supersedes the old one; do not rewrite history.
3. Scope changes (adding or removing an MVP capability) require an ADR — see
   [mvp-scope.md §6](../mvp-scope.md#6-scope-change-protocol).

## Index

| ADR | Title | Status |
|---|---|---|
| [0001](0001-monorepo-layout.md) | Monorepo with `backend/` + `frontend/` | Accepted |
| [0002](0002-postgres-pgvector-single-datastore.md) | PostgreSQL + pgvector as the single datastore | Accepted |
| [0003](0003-synchronous-sqlalchemy.md) | Synchronous SQLAlchemy + psycopg 3 | Accepted |
| [0004](0004-batch-offline-processing.md) | Batch/offline processing model | Accepted |
| [0005](0005-provider-independent-llm.md) | Provider-independent LLM abstraction | Accepted |
| [0006](0006-sentence-transformers-embeddings.md) | Sentence-Transformers-class embeddings | Accepted |
| [0007](0007-hdbscan-clustering.md) | Density-based (HDBSCAN) clustering | Accepted |
| [0008](0008-reddit-only-ingestion.md) | Reddit-only ingestion behind a source adapter | Accepted |
| [0009](0009-epistemic-layer-separation.md) | Epistemic layer separation in the data model | Accepted |
| [0010](0010-nextjs-app-router.md) | Next.js App Router + strict TypeScript | Accepted |
| [0011](0011-pnpm-hoisted-node-linker.md) | pnpm with hoisted node linker | Accepted |
| [0012](0012-alembic-migrations.md) | Alembic for all schema changes | Accepted |
| [0013](0013-excluded-infrastructure.md) | Infrastructure excluded from the MVP | Accepted |
| [0014](0014-operator-accounts.md) | Operator accounts (`users`) in the MVP | Accepted |
| [0015](0015-versioned-text-preparation.md) | Versioned text preparation as a Layer 2 record | Accepted |
