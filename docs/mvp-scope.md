# NarraX — MVP Scope

**Purpose:** state, unambiguously, what the MVP includes, what it excludes, and the exact
conditions under which an exclusion may be revisited. Reference:
[product-requirements.md](product-requirements.md) · [success-criteria.md](success-criteria.md).

**Governing principle:** the MVP exists to test **one hypothesis** — that semantic
clustering + stance + sentiment + LLM narrative extraction produce coherent, useful,
evidence-grounded narratives. Infrastructure that does not serve that hypothesis is out.

---

## 1. MVP envelope (fixed)

| Dimension | MVP value | Rationale |
|---|---|---|
| Source | **Reddit only** | One API, one ToS, one content model to get right |
| Access method | Official Reddit API (OAuth) | Legal/ToS-compliant, stable enough, rate-limited |
| Language | **English only** | Model + validation cost per language is real |
| Processing | **Batch / offline** | The hypothesis is about coherence, not latency |
| Scale | **~500–5,000 discussions** per topic (+ comments) | Enough signal, single-node feasible |
| Deployment | **Single node** + local `docker compose` | Operational simplicity |
| Storage | **PostgreSQL + pgvector** | One datastore for relational + vector |
| Backend | **Python + FastAPI** | Ecosystem fit for NLP/ML |
| Frontend | **Next.js + TypeScript** | Typed, fast to build, deployable |
| Embeddings | Sentence-Transformers-class model | Local, CPU-capable, no API dependency |
| Clustering | Density-based (HDBSCAN-class) | Unknown number of groups; explicit noise |
| Sentiment | Validated pretrained NLP model | Off-the-shelf, versioned |
| Stance | Validated classifier/model/LLM, **topic-relative** | Core to "belief", not just tone |
| LLM | **Provider-independent** (≥2 providers swappable by config) | Avoid lock-in; cost control |
| Evaluation | **Human judgment** on a sample | The only way to test the hypothesis |

---

## 2. In scope (MVP must deliver)

Each item maps to requirements in [product-requirements.md](product-requirements.md).

### 2.1 Data

- [ ] Define a topic with query terms, subreddits, and a time window (FR-1)
- [ ] Batch-ingest public Reddit discussions + comments (FR-2)
- [ ] Store source truth unmodified, with provenance, idempotently (FR-2.1–2.3, FR-2.5)
- [ ] Respect API rate limits; fail loudly on auth/rate errors (FR-2.4)
- [ ] Record why items were excluded (FR-2.6)

### 2.2 Intelligence

- [ ] Embeddings with model/version/dimension recorded (FR-4)
- [ ] Density-based clustering with versioned params + explicit noise (FR-5)
- [ ] Human-readable cluster labels from member content (FR-5.3, FR-5.4)
- [ ] Sentiment per unit (FR-6)
- [ ] Topic-relative stance with confidence (FR-7)
- [ ] LLM narrative extraction — structured, provenance-bound (FR-8)
- [ ] Mandatory evidence links; no evidence → no narrative (FR-9, FR-9.3)
- [ ] Narrative relations: supports / contradicts / refines / co-occurs (FR-10)
- [ ] Snapshots + trend + emerging narratives (FR-11)
- [ ] Group and community comparison (FR-12)

### 2.3 Surfaces

- [ ] Documented HTTP API with epistemic labels + structured errors (FR-14)
- [ ] Web UI: narratives, groups, evidence, trend, corpus scope always visible (FR-15)
- [ ] Full provenance on every derived record (FR-16)
- [ ] Export narrative + evidence (FR-17)

### 2.4 Operations & quality

- [ ] Resumable batch pipeline per topic (FR-18, FR-20)
- [ ] Per-stage status/counts/errors (FR-19)
- [ ] Model/pipeline versioning everywhere (NFR-5, NFR-6)
- [ ] LLM budget cap + graceful degradation (NFR-9, NFR-10)
- [ ] Explicit failures, timeouts, bounded retries (NFR-12, NFR-13)
- [ ] Structured logging, liveness/readiness, per-stage metrics (NFR-16–18)
- [ ] Secrets via env only; `.env.example` committed (NFR-19, NFR-20)
- [ ] Tests, typing, lint/format enforcement (NFR-22–26)
- [ ] Human evaluation executed against SC-1..4 (success-criteria)

---

## 3. Out of scope (and the exact revisit trigger)

Nothing here is "hard to build"; each is excluded because it adds surface before the
hypothesis is proven. An exclusion is revisited **only** when its trigger is observed —
not when it becomes interesting.

| # | Excluded | Revisit trigger |
|---|---|---|
| X-1 | Real-time / streaming ingestion | A measured need for sub-hour reaction |
| X-2 | Kafka / message bus | Sustained event throughput that a batch job cannot meet |
| X-3 | Kubernetes | Multi-service deployment actually required |
| X-4 | ClickHouse / columnar analytics store | Analytical query volume/latency exceeds Postgres capability |
| X-5 | Neo4j / graph DB | Multi-hop narrative-graph analytics required |
| X-6 | Elasticsearch / OpenSearch | Relevance ranking beyond Postgres text/trigram search |
| X-7 | Dedicated vector DB | >~10M vectors **or** vector-query SLO breach |
| X-8 | Additional ingestion platforms | Reddit-only quality proven + adapter pattern exists |
| X-9 | Local large LLM hosting | Cost/privacy requirement measured |
| X-10 | Microservices split | A single deployable becomes a proven bottleneck |
| X-11 | Multi-tenancy / accounts / RBAC | External users need isolation |
| X-12 | Mobile app | Web demand proven |
| X-13 | Model fine-tuning / custom training | Off-the-shelf accuracy proven insufficient |
| X-14 | Scheduled reports / PDF export | Stakeholder reporting demand |
| X-15 | Non-English corpora | English pipeline validated against SC-1..4 |
| X-16 | Cross-platform *sources* (content) | Reddit path proven; per-platform ethics reviewed |
| X-17 | Automatic model retraining / drift detection | Model degradation observed in production |

---

## 4. Permanently prohibited (never in scope)

These are not deferrals. They are excluded by the ethical boundaries in
[data-safety.md](data-safety.md) and §13 of the PRD. No trigger will make them in scope.

- Deanonymization / re-identification of authors
- Personal dossiers, individual profiles, individual political profiling
- Private-user surveillance or hidden user tracking
- Cross-platform **identity** stitching
- Inference of sensitive personal attributes
- Any output about an identifiable individual rather than an aggregate

**Enforcement:** features that cannot satisfy the aggregate-only constraint are rejected
at review, not postponed.

---

## 5. Deferred-but-designed-for

The architecture must not *preclude* these, but must not *implement* them. Each has a
named seam:

| Deferred capability | Seam that keeps it possible |
|---|---|
| Additional platforms | `ingestion/` source-adapter boundary |
| Additional languages | Language is a parameter, not an assumption, in ingestion + models |
| Scheduling / near-real-time | Pipeline runs are idempotent and resumable per topic |
| Swapping embedding/clustering/stance models | Versioned observation tables; new run ≠ mutation |
| Multiple LLM providers | Provider abstraction behind configuration (ADR-0005) |
| Horizontal scale | Single-node first; persistence layer already authoritative |

---

## 6. Scope-change protocol

An item may move from §3 into scope only when **all** of the following hold:

1. **Measured trigger** — the revisit trigger for that item has actually been observed
   (a number, not an impression).
2. **Hypothesis first** — the core hypothesis has been evaluated (SC-1..4 measured) or
   the item is required to evaluate it.
3. **Ethics check** — the item passes §4 and the data-safety review gate.
4. **Recorded decision** — an ADR is added/updated documenting the change and its cost.

Scope **removal** (dropping an in-scope item) requires the same rigour: an ADR stating
what was cut, why, and the consequence for the success criteria.

---

## 7. Definition of done for the MVP

The MVP is done when:

- Every §2 checkbox is delivered or explicitly descoped by ADR, **and**
- SC-5 (auditability) and SC-6 (honesty) pass at 100% — hard gates, **and**
- SC-1..SC-4 meet their thresholds in [success-criteria.md](success-criteria.md), **and**
- A single end-to-end run is reproducible from a clean checkout using only documented
  commands.
