# NarraX Architecture

## Overview

NarraX turns public discussions into layered narrative intelligence. The current MVP
is intentionally small:

```text
Source:       Reddit only
Language:     English
Processing:   Batch / offline
Scale:        ~500–5,000 discussions
Database:     PostgreSQL + pgvector
Backend:      Python + FastAPI
Frontend:     Next.js + TypeScript
Embeddings:   Sentence Transformers (or equivalent)
Clustering:   HDBSCAN (semantic clustering)
Stance:       validated classifier / model / LLM
Sentiment:    validated NLP model
LLM:          provider-independent
```

## System boundaries (MVP)

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                            NarraX (MVP)                                │
│                                                                         │
│  ┌─────────────┐   ┌──────────────┐   ┌──────────────────────────────┐  │
│  │  Ingestion  │──▶│  Storage      │──▶│  Intelligence pipeline        │  │
│  │  (Reddit)   │   │  PostgreSQL   │   │  embed → cluster →            │  │
│  │  batch      │   │  + pgvector   │   │  stance/sentiment → narrative │  │
│  └─────────────┘   └──────────────┘   └──────────────────────────────┘  │
│                                              │                          │
│                                              ▼                          │
│                                     ┌──────────────────────────────┐   │
│                                     │  API + dashboard (FastAPI     │   │
│                                     │  + Next.js)                   │   │
│                                     └──────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

## Conceptual hierarchy

The product model must preserve each distinct layer (never collapse them):

```text
Topic
  ↓
Discussion
  ↓
Semantic Representation
  ↓
Opinion Group / Cluster
  ↓
Stance + Sentiment
  ↓
Narrative
  ↓
Evidence
  ↓
Narrative Relations
  ↓
Temporal Evolution
```

## Epistemic separation

Raw source data, ML observations, AI interpretations, and temporal observations are
stored and presented as separate layers. See [epistemic-layers.md](epistemic-layers.md).

## Deliberately NOT in the MVP

Kafka, Kubernetes, ClickHouse, Neo4j, Elasticsearch/OpenSearch, a dedicated vector
database, multiple ingestion platforms, huge local LLMs, microservices, or distributed
infrastructure. These are introduced only when a concrete scale requirement exists.

## Phase 0 scaffold

- Monorepo: `backend/` (FastAPI) + `frontend/` (Next.js).
- Database via `docker-compose.yml` (PostgreSQL + pgvector), schema via Alembic.
- Configuration via pydantic-settings (`.env`), secrets never committed.
- Health endpoints (liveness/readiness), test + lint tooling.
