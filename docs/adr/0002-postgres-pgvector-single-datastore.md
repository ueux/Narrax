# ADR-0002: PostgreSQL + pgvector as the single datastore

- **Status:** Accepted
- **Date:** 2026-03-10
- **Related:** [architecture.md](../architecture.md) · [data-flow.md](../data-flow.md)

## Context

NarraX stores four kinds of data: relational source truth (topics, discussions, comments),
vector embeddings, structured derived observations (clusters, sentiment, stance), and
interpretations with provenance (narratives, evidence, relations). The MVP scale is
~500–5,000 discussions per topic — thousands to low millions of rows, tens of thousands of
vectors.

We need relational integrity, transactional writes, vector similarity search, and the
ability to join across layers.

## Decision

Use **one PostgreSQL instance with the `pgvector` extension** as the only datastore.

- Relational data uses normal tables and constraints.
- Embeddings live in a `vector(N)` column alongside their model/version metadata.
- Cross-layer queries are ordinary SQL joins, which enforces the provenance chain (gate
  G-1) with referential integrity.

## Consequences

### Positive

- **One system to run, back up, and reason about** — no second consistency model.
- **Joins across layers are free.** "Which narratives are grounded in this discussion?"
  is a single query, not a cross-store fan-out.
- **Transactions cover the whole pipeline write.** A stage's outputs commit atomically.
- **Referential integrity enforces auditability.** Evidence rows cannot dangle.
- Alembic migrations already own the schema (ADR-0012), including the vector column.

### Negative / costs

- Vector search is not as fast as a purpose-built vector engine at very large scale.
- Index tuning (HNSW/IVFFlat) and `maintenance_work_mem` become our responsibility.
- One database becomes a single point of failure — acceptable at single-node MVP scale.
- Requires the `pgvector` extension to be available in the image/host.

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| Dedicated vector DB (Pinecone/Qdrant/Milvus) | A second stateful system, second backup story, and cross-store joins that break auditability — for a scale we are nowhere near |
| SQLite + a local index | No concurrent access story; no real vector indexing |
| Postgres + separate analytics store | No analytical workload yet; pure cost |
| Store embeddings in files/object storage | Loses transactional coupling with the rows they describe |

## Revisit trigger

> ~10 million vectors, **or** a measured vector-query latency that breaks the read-path SLO
> (NFR-3) after index tuning. Only then evaluate a dedicated vector store — and only for the
> vector workload, keeping PostgreSQL as the system of record.
