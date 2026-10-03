# NarraX — Technical Architecture (MVP)

**Status:** Design for MVP · **Version:** 1.0
**Scope:** English public Reddit discussions, batch/offline, ~500–5,000 discussions, single node.

This document describes **how** NarraX is built. **What** it must do is defined by
[product-requirements.md](product-requirements.md); scope boundaries by
[mvp-scope.md](mvp-scope.md). Where they disagree, the PRD wins.

Related: [data-flow.md](data-flow.md) · [adr/](adr/README.md) ·
[epistemic-layers.md](epistemic-layers.md) · [data-safety.md](data-safety.md)

---

## 1. Technology stack (MVP)

| Concern | Choice | ADR |
|---|---|---|
| Language (backend) | Python 3.11+ | — |
| HTTP API | FastAPI + Uvicorn | — |
| ORM / DB access | SQLAlchemy 2.0 (sync) + psycopg 3 | [ADR-0003](adr/0003-synchronous-sqlalchemy.md) |
| Database | PostgreSQL + `pgvector` | [ADR-0002](adr/0002-postgres-pgvector-single-datastore.md) |
| Migrations | Alembic | [ADR-0012](adr/0012-alembic-migrations.md) |
| Embeddings | Sentence-Transformers-class model | [ADR-0006](adr/0006-sentence-transformers-embeddings.md) |
| Clustering | HDBSCAN-class density clustering | [ADR-0007](adr/0007-hdbscan-clustering.md) |
| Sentiment | Validated pretrained NLP model | — |
| Stance | Validated classifier/model/LLM, topic-relative | — |
| LLM | Provider-independent abstraction | [ADR-0005](adr/0005-provider-independent-llm.md) |
| Ingestion | Reddit official API (OAuth), batch | [ADR-0008](adr/0008-reddit-only-ingestion.md) |
| Language (frontend) | TypeScript (strict) | — |
| Frontend framework | Next.js App Router | [ADR-0010](adr/0010-nextjs-app-router.md) |
| Frontend package manager | pnpm (hoisted node linker) | [ADR-0011](adr/0011-pnpm-hoisted-node-linker.md) |
| Local runtime | `docker compose` (PostgreSQL + pgvector) | — |
| Processing model | Batch/offline per topic | [ADR-0004](adr/0004-batch-offline-processing.md) |

---

## 2. System architecture

### 2.1 Context

```text
        ┌──────────────┐         ┌──────────────────────────────────────┐
        │  Reddit      │         │             NarraX (MVP)             │
        │  public API  │◀────────│  batch ingestion (read-only, tokens) │
        └──────────────┘         │                                      │
                                 │  ┌────────────────────────────────┐  │
        ┌──────────────┐         │  │ analysis pipeline (batch)      │  │
        │  LLM provider│◀────────│  │ embed→cluster→stance→narrative │  │
        │  (swappable) │         │  └────────────────────────────────┘  │
        └──────────────┘         │                 │                    │
                                 │                 ▼                    │
        ┌──────────────┐         │  ┌────────────────────────────────┐  │
        │  Analyst     │────────▶│  │ HTTP API (FastAPI) + Web UI    │  │
        │  (browser)   │◀────────│  │ (Next.js)                      │  │
        └──────────────┘         │  └────────────────────────────────┘  │
                                 │                 │                    │
                                 │                 ▼                    │
                                 │      PostgreSQL + pgvector           │
                                 └──────────────────────────────────────┘
```

**Boundaries:** NarraX *reads* from Reddit; it never writes to it. It *calls* an LLM
provider through one abstraction. It *serves* analysts over HTTP. It owns exactly one
stateful component: PostgreSQL.

### 2.2 Containers

| Container | Responsibility | Stateful |
|---|---|---|
| `db` | PostgreSQL + pgvector — all Layer 1–4 data | **Yes** |
| `api` | FastAPI — read/query surface, readiness probe | No |
| `web` | Next.js — analyst UI | No |
| `worker` | Batch pipeline CLI (ingestion + analysis) | No (writes via `db`) |

> **Current state (after PROMPT 03/04):** only `db` exists in `docker-compose.yml`; `api`
> and `web` run as local processes, and `worker` is not yet implemented. This document
> specifies the target topology; the pipeline itself arrives in later phases.

---

## 3. Component architecture

### 3.1 Backend package layout

```text
backend/
├── app/
│   ├── main.py              # ASGI app factory: config → logging → routers
│   ├── api/                 # HTTP layer ONLY (no business logic)
│   │   ├── router.py        # aggregates route modules under /api/v1
│   │   ├── dependencies.py  # shared DI aliases (DbSession, SettingsDep, ...)
│   │   └── routes/          # one module per resource (health, topics, narratives, ...)
│   ├── config/              # settings + logging (no domain logic)
│   │   ├── settings.py      # pydantic-settings Settings
│   │   └── logging.py       # logging configuration
│   ├── database/            # persistence primitives
│   │   ├── base.py          # DeclarativeBase
│   │   ├── session.py       # engine, sessionmaker, get_db
│   │   └── models/          # ORM models, grouped by epistemic layer
│   ├── ingestion/           # Layer 1: acquire + normalise source truth
│   ├── intelligence/        # Layers 2–4: embeddings, clusters, sentiment,
│   │                        #   stance, narratives, relations, evolution + llm/
│   ├── services/            # use-cases: orchestrate the above; the only place
│   │                        #   that knows a whole workflow
│   └── schemas/             # Pydantic DTOs for API boundaries (in/out)
├── alembic/                 # migrations (single source of schema truth)
└── tests/                   # mirrors app/ structure
```

**Why these boundaries** (and not others): each corresponds to a stage of the conceptual
hierarchy and to a distinct reason to change. `intelligence/` will contain several
algorithms, but they share one characteristic — they turn stored text into versioned
derived observations — so they belong together rather than in separate top-level packages.

### 3.2 Backend component responsibilities

| Component | Owns | Must never |
|---|---|---|
| `api/` | HTTP parsing/validation, status codes, DI wiring, response shaping | Contain analysis logic or open ad-hoc DB sessions |
| `config/` | Reading + validating environment; log setup | Read domain data |
| `database/` | Engine/session lifecycle, ORM models, schema | Contain business rules or call external APIs |
| `ingestion/` | Reddit client, pagination, rate limiting, normalisation, idempotent upsert of Layer 1 | Compute any derived value |
| `intelligence/` | Embedding, clustering, sentiment, stance, narrative extraction, relations, evolution; LLM provider abstraction | Talk HTTP to the client; own request lifecycle |
| `services/` | Orchestrating multi-step workflows (run pipeline, build snapshot, assemble a topic view) | Duplicate algorithm code; bypass `database/` |
| `schemas/` | DTO contracts at the API edge | Leak ORM internals |

### 3.3 Frontend structure

```text
frontend/
├── app/                # Next.js App Router: routes, layouts, pages (server components)
├── components/         # React components (presentational + feature)
├── hooks/              # reusable client hooks (data fetching, derived state)
├── lib/                # non-React code: API client, formatters, constants
└── types/              # shared TypeScript types (API contracts)
```

| Layer | Owns | Must never |
|---|---|---|
| `app/` | Routing, layouts, server-side data loading, page composition | Contain reusable widgets or fetch logic |
| `components/` | Rendering + local interaction | Call the API directly (go through `lib/`/`hooks/`) |
| `hooks/` | Data fetching lifecycle, derived client state | Contain raw `fetch` calls or URL strings |
| `lib/` | API client, error normalisation, pure helpers | Import React |
| `types/` | API/DTO types shared across the above | Contain runtime logic |

**Epistemic labelling is a UI obligation:** components that render AI interpretations must
visually distinguish them from ML observations and from source text (FR-15.2).

---

## 4. Request flow (synchronous read path)

The read path serves an already-computed topic. It performs **no** ML.

```text
Browser
  │  1. GET /topics/{id}/narratives
  ▼
Next.js (app/ page or server component)
  │  2. hooks/ → lib/api-client.ts  (typed fetch, base URL from env)
  ▼
FastAPI  api/router.py → api/routes/narratives.py
  │  3. Validate path/query via schemas/  → 400 on invalid input
  ▼
services/  (e.g. list_narratives(topic_id))
  │  4. Orchestrate one or more database/ queries
  ▼
database/  SQLAlchemy session  →  PostgreSQL
  │  5. SELECT narratives + evidence + provenance (+ corpus size)
  ▼
services/  →  assemble response DTOs, attach epistemic labels + confidence
  ▼
schemas/    →  serialise (typed, versioned contract)
  ▼
FastAPI → JSON → Next.js → React components
```

**Rules for the read path**

1. **No ML/AI calls.** A request must never trigger embedding, clustering, or an LLM call.
2. **Every response carries scope.** Corpus size and time window travel with the data so
   the client cannot show a narrative without context (FR-15.1).
3. **Every response carries layer labels.** Source text, observations, and interpretations
   are distinct fields, not merged prose (FR-14.1).
4. **Read-only.** The MVP read path never mutates Layer 1; mutations happen only in the
   batch pipeline.

---

## 5. Analysis pipeline (batch path)

The pipeline is a sequence of **idempotent, individually re-runnable stages** (FR-20).
Each stage records a `StageExecution` (status, counts in/out, drops + reasons, duration,
versions) against a `PipelineRun` (FR-19).

```text
S0  Define topic ──────────────▶ Topic (Layer 1)
S1  Ingest (Reddit) ───────────▶ Discussions, Comments (+ provenance)      [Layer 1]
S2  Normalise + filter ────────▶ Exclusions with reasons                   [Layer 1 meta]
S3  Embed ─────────────────────▶ Embeddings (model+version+dim)            [Layer 2]
S4  Cluster (HDBSCAN) ─────────▶ ClusterRun, Clusters, Memberships, noise  [Layer 2]
S5  Sentiment + Stance ────────▶ SentimentScore, StanceLabel               [Layer 2]
S6  Narratives (LLM) ──────────▶ Narrative, NarrativeEvidence, Provenance  [Layer 3]
S7  Relations ─────────────────▶ NarrativeRelation                         [Layer 3]
S8  Snapshot + evolution ──────▶ Snapshot, NarrativeTrend, Emerging        [Layer 4]
S9  Evaluation (offline) ──────▶ Evaluation report artifact                [meta]
```

### Stage contracts

| Stage | Input | Output | Idempotency key | Failure mode |
|---|---|---|---|---|
| S0 | User intent | `Topic` | topic identity | Fail fast; nothing to do |
| S1 | Topic (subreddits, window, terms) | Layer-1 rows | `(source, source_id)` upsert | Retry w/ backoff; abort on auth; **partial run preserved + labelled** |
| S2 | Layer-1 rows | Kept/excluded sets + reasons | per item, deterministic | Skip bad rows, record reason |
| S3 | Kept text + model version | `Embedding` rows | `(unit, model, version)` | Abort stage; earlier layers remain valid |
| S4 | Embeddings + params | `ClusterRun` + memberships | `(run, algo, params hash)` | Abort stage; keep embeddings |
| S5 | Kept text + topic (+ model versions) | Sentiment/stance rows | `(unit, topic, model version)` | Abort stage; keep clusters |
| S6 | Cluster + members + evidence candidates | Narratives + evidence | `(cluster run, prompt version, model)` | Per-cluster retry; drop clusters that fail; **never publish evidence-less narrative** |
| S7 | Narratives (+ embeddings) | Relations | `(from, to, type, inferred_by)` | Abort stage; narratives remain |
| S8 | Current + previous runs | Snapshots + trends | `(topic, as_of, run)` | Abort stage; earlier snapshots untouched |
| S9 | Frozen run + human ratings | Report artifact | `(run, evaluator set)` | Offline; never blocks serving |

### Pipeline invariants

1. **Source truth is immutable.** S1/S2 never rewrite collected text (NFR-8).
2. **New versions create new rows.** Re-embedding or re-clustering adds observations; it
   does not mutate prior ones (FR-4.3, NFR-7).
3. **Publishability.** A narrative is publishable only if it has ≥1 evidence link and
   conforms to the narrative schema (G-1, G-2, NFR-15).
4. **Graceful degradation.** With no LLM configured, S0–S5 and S8 still produce valid
   output; only S6/S7 are unavailable (NFR-10) and the topic is marked "narratives
   unavailable", not "empty".
5. **Resumability.** Re-running resumes from the first incomplete stage (FR-18, FR-20).

---

## 6. Data flow

Full treatment: [data-flow.md](data-flow.md). Summary:

```text
Reddit ──▶ ingestion ──▶ [Layer 1] source truth (immutable)
                              │
                              ├──▶ embeddings ──▶ [Layer 2] observations
                              │        │
                              │        └──▶ clusters ──▶ stance/sentiment
                              │                            │
                              └────────────────────────────┴──▶ [Layer 3] narratives
                                                                   │   └── evidence → Layer 1
                                                                   │   └── relations
                                                                   ▼
                                                          [Layer 4] snapshots/evolution
                                                                   │
                                                                   ▼
                                                          API + UI (read-only)
```

**One-way dependency:** Layer 4 ← Layer 3 ← Layer 2 ← Layer 1. No layer reads upward,
and only `ingestion/` writes Layer 1.

---

## 7. Module boundaries

### 7.1 Allowed dependency direction (backend)

```text
api/ ─────────▶ services/ ─────────▶ intelligence/ ──┐
  │                  │                  │            │
  │                  ├──────────────▶ ingestion/ ────┤
  │                  │                  │            │
  └──────────────────┴──────────────────┴────────────┴──▶ database/
                                  schemas/ ◀── (api, services)
                                  config/  ◀── (everyone)
```

Rules, enforced by convention and review (a lint rule can be added later):

1. `config/` and `schemas/` are leaves — they import no sibling package.
2. `database/` imports only `config/`.
3. `ingestion/` and `intelligence/` import `database/`, `schemas/`, `config/` — **never**
   `services/` or `api/`.
4. `services/` is the only package allowed to compose ingestion + intelligence + database.
5. `api/` imports `services/`, `schemas/`, `database/` (DI only), `config/`.
6. **Nothing imports `api/`.** A cycle into `api/` is a design error.
7. Cross-cutting concerns (logging, settings) come from `config/` — never re-implemented.

### 7.2 Boundary → conceptual hierarchy → phase

| Package | Hierarchy level | Introduced |
|---|---|---|
| `database/models/` | all | Phase 1 |
| `ingestion/` | Discussion (+ Topic) | Phase 1 |
| `intelligence/` (embed/cluster) | Semantic Representation → Opinion Group | Phase 2 |
| `intelligence/` (sentiment/stance) | Stance + Sentiment | Phase 3 |
| `intelligence/` (narratives/llm) | Narrative → Evidence → Relations | Phase 4–5 |
| `intelligence/` (evolution) | Temporal Evolution | Phase 6 |
| `services/` | orchestration across levels | Phase 1+ |
| `api/`, `schemas/` | access surfaces | Phase 1+ |
| `frontend/` | access surfaces | Phase 7 |

---

## 8. Deployment topology

### 8.1 Local development (current, and the supported MVP dev path)

```text
┌──────────────────────────────────────────────────────┐
│ host                                                 │
│  ┌────────────────────┐   ┌───────────────────────┐  │
│  │ uvicorn (api)      │   │ next dev (web)        │  │
│  │ :8000              │   │ :3000                 │  │
│  └─────────┬──────────┘   └──────────┬────────────┘  │
│            │                         │               │
│            └──────────┬──────────────┘               │
│                       ▼                              │
│            ┌────────────────────────┐                │
│            │ docker compose: db     │                │
│            │ postgres + pgvector    │                │
│            │ :5432  + volume        │                │
│            └────────────────────────┘                │
│                                                      │
│  batch pipeline runs as a CLI in the backend venv    │
└──────────────────────────────────────────────────────┘
```

### 8.2 Single-node deployment (target)

```text
┌──────────────────────────────────────────────────────┐
│ one host (or one small VM)                           │
│  [web] ──▶ [api] ──▶ [db: postgres+pgvector+volume]  │
│                        ▲                             │
│              [worker] ─┘  (batch pipeline, on demand) │
└──────────────────────────────────────────────────────┘
```

Characteristics: one stateful volume (the DB), stateless `api`/`web`/`worker`, vertical
scaling first. No orchestration layer, no service mesh, no message broker — see
[ADR-0004](adr/0004-batch-offline-processing.md) and
[ADR-0013](adr/0013-excluded-infrastructure.md).

### 8.3 Configuration surface per environment

| Variable class | dev | prod |
|---|---|---|
| `DATABASE_URL` | local compose | managed/pinned host |
| `NARRAX_ENV` | `development` | `production` (disables `/docs`) |
| Reddit credentials | optional until Phase 1 | required for ingestion |
| `LLM_PROVIDER` / `LLM_API_KEY` | optional (LLM stages off) | required for narratives |
| Budget caps | generous | enforced |

---

## 9. Error boundaries

Errors are handled at the layer that can *do* something about them, and always surfaced.

| Boundary | Catches | Behaviour |
|---|---|---|
| **HTTP edge** (`api/`) | Validation errors, missing resources, unexpected exceptions | 4xx for client errors with structured bodies; 5xx for faults; never leak stack traces or secrets; correlation id in the response |
| **Service** (`services/`) | Domain rule violations (e.g. narrative without evidence) | Raise typed domain errors → mapped to HTTP status |
| **Ingestion** (`ingestion/`) | Auth failure, rate limit, network/timeout, malformed payloads | Bounded retries w/ backoff; auth/rate → terminal stage error; malformed item → counted + skipped with reason; **never abort the whole topic for one bad item** |
| **Intelligence** (`intelligence/`) | Model load failure, insufficient data, invalid LLM output | Model failure → stage abort (previous layers remain valid); insufficient data → explicit "no structure found" result, not an invented one; invalid LLM output → **rejected + recorded**, never persisted |
| **Persistence** (`database/`) | Integrity errors, connection loss | Transaction rollback; connection loss → surfaced as readiness failure, retried at stage level |
| **Pipeline** (`services/`) | Any stage failure | Stage marked failed with counts + error; run marked partial; resumable; downstream stages skipped (not silently) |
| **Frontend** (`lib/`, `hooks/`, `components/`) | Network failure, non-2xx, malformed payload | `api-client` normalises to a typed error; hooks expose `loading/error/data`; components render an explicit error/empty state; **never render a failure as empty-but-fine** |

### Cross-cutting error rules

1. **Never swallow** — no bare `except: pass` (NFR-12).
2. **Typed errors** — distinguish client/domain/infrastructure failures.
3. **Record drops** — every skipped item has a reason attached (FR-2.6, FR-19).
4. **Partial is a first-class state** — visibly labelled, never disguised as complete.
5. **Fail closed on safety** — if evidence/provenance cannot be established, do not publish.

---

## 10. Configuration strategy

### 10.1 Principles

1. **Environment variables are the only source of secrets** (NFR-19); `.env` is local-only
   and gitignored; `.env.example` documents every variable.
2. **Validated at startup** — invalid configuration fails fast with a clear message (NFR-21).
3. **Typed and defaulted** — one `Settings` object (`config/settings.py`) is the single
   access point; no scattering `os.environ` reads across modules.
4. **Explicit per stage** — model versions, prompt versions, and algorithm parameters are
   configuration with recorded values, not hidden constants (NFR-5).
5. **No behaviour-changing defaults in code paths that matter** — a missing LLM key
   disables LLM stages (NFR-10) rather than silently substituting a worse method.

### 10.2 Configuration groups

| Group | Examples | Notes |
|---|---|---|
| Application | `NARRAX_ENV`, `API_V1_PREFIX`, version | `production` disables interactive docs |
| Database | `DATABASE_URL` (+ `POSTGRES_*` for compose) | One URL for app + Alembic |
| Ingestion | `REDDIT_CLIENT_ID/SECRET/USER_AGENT` | Required only for ingestion |
| Models | embedding model + version, sentiment model, stance method | Pinned; recorded on every output |
| Clustering | algorithm + params (min cluster size, metric) | Hashed into `ClusterRun` |
| LLM | `LLM_PROVIDER`, `LLM_API_KEY`, model name, temperature, max tokens | Provider-agnostic |
| Budget | max LLM calls / tokens per run | Enforced with graceful stop (NFR-9) |
| Frontend | `NEXT_PUBLIC_API_BASE_URL` | Public by definition; no secrets |

### 10.3 Precedence

`process environment` **>** `backend/.env` **>** code defaults. Frontend reads only
`NEXT_PUBLIC_*` (Next.js inlines them at build time, so **never** place secrets there).

---

## 11. Security & privacy posture

- No credentials in source control; `.env` gitignored; `.env.example` has placeholders only.
- Authors are opaque pseudonymous identifiers; no enrichment, no cross-platform linking
  ([data-safety.md](data-safety.md)).
- Aggregate-only output; minimum group sizes enforced before a claim is shown.
- Read-only Reddit integration; rate limits respected.
- `production` environment disables `/docs` and `/redoc`; no stack traces to clients.
- LLM calls send only the minimum text needed and never credentials.

---

## 12. Observability

| Concern | Approach |
|---|---|
| Logging | Structured, leveled, one run id threaded through pipeline stages (NFR-16) |
| Health | `GET /api/v1/health/live` (process) and `/health/ready` (DB probe → 503) (NFR-17) |
| Run reporting | `StageExecution` rows + a run summary artifact: counts in/out, drops+reasons, durations, versions (FR-19, NFR-18) |
| Cost | Per-run LLM call/token accounting against the configured cap (NFR-9) |
| Frontend | `api-client` error normalisation → visible pipeline/partial-failure states (FR-15.3) |

---

## 13. Deliberately excluded infrastructure

Full reasoning: [adr/0013-excluded-infrastructure.md](adr/0013-excluded-infrastructure.md)
and [mvp-scope.md §3](mvp-scope.md#3-out-of-scope-and-the-exact-revisit-trigger).

Not present, by design: Kafka/message bus, Kubernetes, ClickHouse, Neo4j,
Elasticsearch/OpenSearch, a dedicated vector database, multiple ingestion platforms,
self-hosted large LLMs, microservices, multi-tenancy, orchestration frameworks.

Each is excluded **until a measured trigger** — not because it is difficult.

---

## 14. Architecture Decision Records

| ADR | Decision |
|---|---|
| [0001](adr/0001-monorepo-layout.md) | Monorepo with `backend/` + `frontend/` |
| [0002](adr/0002-postgres-pgvector-single-datastore.md) | PostgreSQL + pgvector as the single datastore |
| [0003](adr/0003-synchronous-sqlalchemy.md) | Synchronous SQLAlchemy + psycopg 3 |
| [0004](adr/0004-batch-offline-processing.md) | Batch/offline processing model |
| [0005](adr/0005-provider-independent-llm.md) | Provider-independent LLM abstraction |
| [0006](adr/0006-sentence-transformers-embeddings.md) | Sentence-Transformers-class embeddings |
| [0007](adr/0007-hdbscan-clustering.md) | Density-based (HDBSCAN) clustering |
| [0008](adr/0008-reddit-only-ingestion.md) | Reddit-only ingestion behind a source adapter |
| [0009](adr/0009-epistemic-layer-separation.md) | Epistemic layer separation in the data model |
| [0010](adr/0010-nextjs-app-router.md) | Next.js App Router + strict TypeScript |
| [0011](adr/0011-pnpm-hoisted-node-linker.md) | pnpm with hoisted node linker |
| [0012](adr/0012-alembic-migrations.md) | Alembic for all schema changes |
| [0013](adr/0013-excluded-infrastructure.md) | Infrastructure excluded from the MVP |

Index: [adr/README.md](adr/README.md)
