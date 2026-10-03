# NarraX — Product Requirements Specification (MVP)

**Status:** Locked for MVP · **Version:** 1.0 · **Owner:** NarraX
**Scope:** English-language public Reddit discussions, batch/offline, ~500–5,000 discussions.

This document is the single source of truth for *what* the MVP must do. It is paired
with, and must stay consistent with:

- [mvp-scope.md](mvp-scope.md) — explicit in/out of scope and deferrals
- [success-criteria.md](success-criteria.md) — how we judge whether it worked
- [glossary.md](glossary.md) — terminology used here
- [architecture.md](architecture.md) — *how* it is built
- [epistemic-layers.md](epistemic-layers.md), [data-safety.md](data-safety.md) — boundaries

Where this document and any other disagree, **this document wins**.

---

## 1. Problem statement

Public online discussion about any contested or evolving topic is large, fragmented,
and fast-moving. A person who needs to understand it can currently answer only narrow
questions with existing tooling:

- **Sentiment tools** say *how positive/negative* the mood is, not *what is believed*.
- **Keyword/volume tools** say *how often* a term appears, not *what claim* it carries.
- **Topic modeling** says *what subjects* are discussed, not *what positions* groups hold.
- **Social listening dashboards** count mentions and influencers, not *narratives*.
- **A chatbot over source data** answers ad-hoc questions but produces no durable,
  evidence-grounded, comparable, or longitudinal artifact.

None of them answer the question that actually matters:

> **What are people actually believing and saying about a topic, and how are those
> narratives changing?**

### Why this is hard

1. **Meaning is distributed.** A narrative is rarely one message; it is a pattern across
   many messages, expressed in different words.
2. **Disagreement is structural.** People cluster into opinion groups that share
   vocabulary; without grouping, aggregate statistics average away the signal.
3. **Claims need evidence.** An assertion like "group X believes Y" is only useful — and
   only honest — if it can be traced to specific source messages.
4. **Meaning moves.** Narratives emerge, mutate, and fade; a single snapshot cannot
   distinguish a stable belief from a two-day spike.

### What NarraX is (and is not)

NarraX is a **narrative intelligence engine**: it turns a body of public discussion into
structured, evidence-grounded, comparable, and time-aware narrative objects.

NarraX is **not** merely sentiment analysis, keyword counting, topic modeling, social
media monitoring, a chatbot over Reddit, or a generic analytics dashboard.

---

## 2. Target users

The MVP serves a **single primary persona** well; others are secondary and must not
drive scope.

| Priority | Persona | Goal | What they need from NarraX |
|---|---|---|---|
| **Primary** | **Research/insight analyst** (social science, media studies, comms, policy) | Characterize how a public topic is being discussed and how that changes | Narrative inventory with supporting quotes, group differences, and trend over time |
| Secondary | **Product / strategy lead** | Understand how a market or user community perceives an issue | Clear narrative summaries and relative prevalence, with caveats |
| Secondary | **Journalist / OSINT analyst** | Detect a shifting or emerging narrative quickly | "What's new / what changed" views with citations |
| Internal | **Operator/developer** (the builder) | Run and re-run the pipeline reproducibly | A batch pipeline, versioned models, and an inspectable database |

### Explicitly *not* a user

- Anyone seeking information about **specific individuals** (see §12).
- Anyone seeking **cross-platform identity** resolution.
- Anyone needing **real-time** (sub-minute) reaction in the MVP (see §7).

### User skill assumptions

Users can phrase a topic, read a chart, and tolerate batch latency. They are **not**
expected to know about embeddings, clustering, or LLMs.

---

## 3. Primary user journey

The MVP optimizes exactly one end-to-end journey. Every functional requirement (FR)
in §4 must serve a step here.

```text
 1. DEFINE      Analyst names a topic, chooses subreddits + a time window (FR-1)
                     │
 2. COLLECT     Operator runs ingestion; raw public discussions land in the DB (FR-2, FR-3)
                     │
 3. ANALYZE     Pipeline runs: embed → cluster → sentiment/stance → narratives (FR-4..FR-8)
                     │
 4. REVIEW      Analyst opens the topic: sees narratives, groups, prevalence (FR-9, FR-14, FR-15)
                     │
 5. VERIFY      Analyst clicks a narrative and reads the exact source evidence (FR-9)
                     │
 6. COMPARE     Analyst compares groups / communities on the same topic (FR-12)
                     │
 7. TRACK       Analyst inspects how narratives changed across snapshots (FR-11)
                     │
 8. EXPORT      Analyst cites or exports narrative + evidence (FR-17)
```

**Journey success:** at step 5 the analyst says *"this is a real pattern I can
verify"*, not *"this is a plausible-sounding summary."*

### Journey variants the MVP must still handle

- **No strong structure found.** Clustering yields one diffuse group → the UI must say
  "no distinct opinion groups detected," not invent groups.
- **Sparse evidence.** A narrative has few supporting messages → it must be labeled
  low-confidence, not hidden or overstated.
- **Pipeline partially failed.** Ingestion succeeded, narrative extraction failed → the
  analyst must still see embeddings/clusters/sentiment and a clear error state.

---

## 4. Functional requirements

Requirements are tagged with a level, a scope dimension, and the pipeline layer they
belong to. `LEVEL` is `MUST` (MVP-blocking), `SHOULD` (MVP if cheap), `MAY` (post-MVP).

### 4.1 Topic & scope definition

| ID | Level | Requirement |
|---|---|---|
| FR-1 | MUST | Define a **Topic** with: a human name, an optional description, a query term set, a target subreddit list, and a time window. |
| FR-1.1 | MUST | A topic is persisted and re-runnable; re-running does not destroy the previous run's output. |
| FR-1.2 | SHOULD | A topic records the exact **selection criteria** used, so a result can be explained and reproduced. |

### 4.2 Ingestion — source truth

| ID | Level | Requirement |
|---|---|---|
| FR-2 | MUST | Ingest **public** Reddit discussions + comments for a topic's subreddits and window. |
| FR-2.1 | MUST | Store ingestion output **unmodified** as source truth, separate from any derived data. |
| FR-2.2 | MUST | Record provenance per item: permalink/id, subreddit, created time, retrieval time, and the ingestion run. |
| FR-2.3 | MUST | Ingestion is **idempotent** — re-running over the same window does not duplicate items. |
| FR-2.4 | MUST | Respect the source API's rate limits and terms; fail loudly on auth/rate errors. |
| FR-2.5 | MUST | Authors are stored only as **pseudonymous handles/ids**; no profile enrichment (see §12). |
| FR-2.6 | SHOULD | Filter out non-English and effectively empty content, recording *why* an item was excluded. |

### 4.3 Semantic representation

| ID | Level | Requirement |
|---|---|---|
| FR-4 | MUST | Compute a vector **Embedding** for each analysis unit (discussion/comment text). |
| FR-4.1 | MUST | Record the embedding **model name + version + dimensionality** with every vector. |
| FR-4.2 | MUST | Embeddings are a versioned **ML observation**, never overwriting source text. |
| FR-4.3 | SHOULD | Re-embedding with a new model creates a new observation set, not a mutation. |

### 4.4 Opinion groups (clustering)

| ID | Level | Requirement |
|---|---|---|
| FR-5 | MUST | Discover **opinion groups / clusters** from embeddings (density-based; no fixed *k* required). |
| FR-5.1 | MUST | Cluster assignment is versioned and stores its **parameters and algorithm version**. |
| FR-5.2 | MUST | Noise/outlier items are representable and must not be forced into a group. |
| FR-5.3 | MUST | Each cluster exposes a **human-readable label** + representative members. |
| FR-5.4 | SHOULD | Cluster label is derived from member content, not invented by an LLM alone. |

### 4.5 Sentiment & stance

| ID | Level | Requirement |
|---|---|---|
| FR-6 | MUST | Compute **sentiment** per analysis unit with a validated model, storing score + label + model version. |
| FR-7 | MUST | Compute **stance** of a unit **relative to the topic** (support / oppose / neutral / unclear), with confidence + method version. |
| FR-7.1 | MUST | Stance is explicitly topic-relative; the same text may have different stance for different topics. |
| FR-7.2 | MUST | Low-confidence stance is recorded as such and is never silently promoted to a firm label. |
| FR-7.3 | SHOULD | Stance quality is validated on a labeled sample before it is trusted (see success-criteria). |

### 4.6 Narratives — AI interpretation

| ID | Level | Requirement |
|---|---|---|
| FR-8 | MUST | Extract **Narratives** from an opinion group: a concise claim + short description + the group it belongs to. |
| FR-8.1 | MUST | Every narrative is stored with **provenance**: model, prompt/template version, run, and timestamp. |
| FR-8.2 | MUST | Narratives are labeled as **AI interpretation**, distinct from ML observations and source truth. |
| FR-8.3 | MUST | A narrative with insufficient supporting evidence is surfaced as low-confidence or omitted — never asserted. |
| FR-8.4 | MUST | Narratives are structured/machine-readable (stable schema), not free prose blobs. |
| FR-8.5 | SHOULD | Narrative extraction is provider-independent (works with ≥2 LLM providers via config). |

### 4.7 Narrative evidence

| ID | Level | Requirement |
|---|---|---|
| FR-9 | MUST | Each narrative links to the **specific source items** that support it. |
| FR-9.1 | MUST | Evidence links are reviewable: the user can read the original text for each. |
| FR-9.2 | SHOULD | Evidence includes a relevance/confidence signal, not just a raw list. |
| FR-9.3 | MUST | A narrative with **zero** evidence links is invalid and must not be published. |

### 4.8 Narrative relations

| ID | Level | Requirement |
|---|---|---|
| FR-10 | MUST | Record at least one relation type between narratives: **supports**, **contradicts**, **refines**, **co-occurs-with**. |
| FR-10.1 | MUST | Relations carry provenance (how inferred: ML similarity vs LLM judgment) and confidence. |
| FR-10.2 | SHOULD | Contradiction pairs are discoverable from the UI. |

### 4.9 Temporal evolution

| ID | Level | Requirement |
|---|---|---|
| FR-11 | MUST | Persist **Snapshots** of analysis state so change over time can be computed. |
| FR-11.1 | MUST | Report per narrative: first seen, last seen, and direction (rising / stable / fading). |
| FR-11.2 | MUST | Identify **emerging narratives** (present in a later snapshot, absent/negligible earlier). |
| FR-11.3 | MUST | A "changed" claim is itself a temporal observation tied to specific snapshots — not a vibe. |
| FR-11.4 | SHOULD | Absolute counts are shown next to relative share to avoid small-sample illusions. |

### 4.10 Comparison

| ID | Level | Requirement |
|---|---|---|
| FR-12 | MUST | Compare opinion groups **within** a topic and communities (subreddits) on the same topic. |
| FR-12.1 | MUST | Comparisons are statistical descriptions of *the analyzed corpus*, with corpus size always visible. |
| FR-13 | MAY | Cross-platform comparison (non-Reddit sources) — interface must not preclude it (see §7). |

### 4.11 Access surfaces

| ID | Level | Requirement |
|---|---|---|
| FR-14 | MUST | A documented HTTP API exposes topics, narratives, evidence, clusters, and temporal series. |
| FR-14.1 | MUST | API responses carry epistemic labels (source / observation / interpretation) so clients cannot conflate them. |
| FR-14.2 | MUST | API validates inputs and returns explicit, structured errors. |
| FR-15 | MUST | A web UI lets a user browse a topic's narratives, groups, evidence, and trend. |
| FR-15.1 | MUST | The UI always shows the analyzed corpus scope ("among N analyzed public Reddit discussions…"). |
| FR-15.2 | MUST | The UI visually distinguishes AI interpretation from observation and from source text. |
| FR-15.3 | SHOULD | The UI exposes pipeline status so a partial failure is legible. |
| FR-16 | MUST | Every derived record is traceable to a **PipelineRun** and model/prompt versions. |
| FR-17 | SHOULD | Narrative + evidence can be exported (e.g., JSON/Markdown) for citation. |

### 4.12 Operations

| ID | Level | Requirement |
|---|---|---|
| FR-18 | MUST | The pipeline is runnable as a **batch** job per topic, resumable after failure. |
| FR-19 | MUST | Each stage records success/failure, counts, duration, and the versions used. |
| FR-20 | SHOULD | A stage can be re-run in isolation (e.g., re-extract narratives without re-ingesting). |
| FR-21 | MAY | Scheduled automatic re-runs (real-time/near-real-time) — post-MVP. |

---

## 5. Non-functional requirements

### 5.1 Scale & performance (MVP envelope)

| ID | Requirement |
|---|---|
| NFR-1 | Must handle **~500–5,000 discussions** (+ associated comments) per topic on a **single node**. |
| NFR-2 | Batch pipeline for the full envelope must complete within a **few hours**, not days. |
| NFR-3 | Interactive API reads (topic, narratives, evidence) must feel responsive (**< ~1 s** typical, p95 < 3 s) at MVP scale. |
| NFR-4 | Embedding/clustering must be feasible on a **CPU-only** machine; GPU is an optimization, not a requirement. |

### 5.2 Reproducibility & provenance

| ID | Requirement |
|---|---|
| NFR-5 | Every ML/AI output records the **model, version, and parameters** that produced it. |
| NFR-6 | Every output records the **pipeline run** and **stage** that produced it. |
| NFR-7 | Re-running the same versions over the same immutable source data yields the same **structural** result (modulo documented nondeterminism, e.g. LLM sampling, which must be recorded). |
| NFR-8 | Source truth is **never** overwritten by derived data. |

### 5.3 Cost & external dependencies

| ID | Requirement |
|---|---|
| NFR-9 | LLM usage is **bounded and observable**: token/call counts per run, with a configurable budget cap and graceful stop. |
| NFR-10 | The system degrades gracefully when the LLM is unconfigured or unavailable: all non-LLM layers still produce output. |
| NFR-11 | The LLM provider is **swappable via configuration** with no code change in the pipeline. |

### 5.4 Reliability & error handling

| ID | Requirement |
|---|---|
| NFR-12 | Failures are **explicit**: no silent swallowing; every stage reports and logs failures with context. |
| NFR-13 | External calls (source API, LLM) use timeouts, bounded retries with backoff, and clear terminal errors. |
| NFR-14 | Partial results are preserved and clearly labeled as partial. |
| NFR-15 | Invalid/malformed model output (e.g., non-conforming LLM JSON) is rejected and recorded, never persisted as valid data. |

### 5.5 Observability

| ID | Requirement |
|---|---|
| NFR-16 | Structured, leveled logging for all significant operations; each run is traceable by run id. |
| NFR-17 | Liveness and readiness endpoints exist; readiness reflects real dependency health. |
| NFR-18 | Per-stage metrics (items in/out, drops with reasons, durations) are recorded per run. |

### 5.6 Security & configuration

| ID | Requirement |
|---|---|
| NFR-19 | **No credentials in source control**; all secrets via environment variables. |
| NFR-20 | A committed `.env.example` documents every required/optional variable. |
| NFR-21 | Configuration is validated at startup; invalid config fails fast and clearly. |

### 5.7 Quality & maintainability

| ID | Requirement |
|---|---|
| NFR-22 | Modules have clear boundaries and are **independently testable**. |
| NFR-23 | Strong typing where practical (Python type hints + mypy, TypeScript strict). |
| NFR-24 | Automated formatting and linting are enforced (ruff; eslint + prettier). |
| NFR-25 | Important functionality has tests; ML/AI outputs are tested for **schema conformance** at minimum. |
| NFR-26 | Database schema changes go through migrations only. |
| NFR-27 | Documentation stays synchronized with implementation. |

### 5.8 Portability

| ID | Requirement |
|---|---|
| NFR-28 | Local development works via `docker compose` + documented commands on Windows and POSIX. |
| NFR-29 | No dependency on a specific cloud provider or managed service for the MVP. |

---

## 6. Core entities

Entities are grouped by **epistemic layer** (see [epistemic-layers.md](epistemic-layers.md)).
The layer column is normative: it determines what may overwrite what.

### 6.1 Layer 1 — Source truth (immutable)

| Entity | Description | Key attributes |
|---|---|---|
| `Topic` | The subject under study and its selection criteria | name, description, query terms, subreddits, time window |
| `IngestionRun` | One execution of collection for a topic | topic, window, started/finished, counts, status |
| `Discussion` | A source post (submission) | source id, subreddit, title, body, created_at, permalink, author handle |
| `Comment` | A source reply | source id, parent, body, created_at, permalink, author handle |
| `SourceItemRef` | Stable locator + provenance for any raw item | source, source_id, permalink, retrieved_at |

### 6.2 Layer 2 — ML observations (versioned, derived)

| Entity | Description | Key attributes |
|---|---|---|
| `PipelineRun` | One execution of the analysis pipeline | topic, stages, versions, window, status |
| `Embedding` | Vector for an analysis unit | unit ref, model name/version, dim, vector, created_at |
| `ClusterRun` | One clustering execution | run, algorithm, params, created_at |
| `Cluster` | A discovered opinion group | cluster run, label, size, centroid, representatives |
| `ClusterMembership` | Unit → cluster assignment | unit ref, cluster, distance/probability, is_noise |
| `SentimentScore` | Sentiment for a unit | unit ref, label, score, model version |
| `StanceLabel` | Topic-relative stance for a unit | unit ref, topic, label, confidence, method version |

### 6.3 Layer 3 — AI interpretations (provenance-bound)

| Entity | Description | Key attributes |
|---|---|---|
| `Narrative` | A claim/pattern attributed to an opinion group | cluster ref, claim, description, confidence, summary stats |
| `NarrativeEvidence` | Link from narrative → supporting source item | narrative, source item ref, relevance, rationale |
| `NarrativeRelation` | Typed edge between narratives | from, to, type (supports/contradicts/refines/co-occurs), confidence, inferred_by |
| `NarrativeProvenance` | How a narrative was produced | model, prompt/template version, run, created_at |

### 6.4 Layer 4 — Temporal observations

| Entity | Description | Key attributes |
|---|---|---|
| `Snapshot` | A dated record of analysis state for a topic | topic, as_of, run ref, corpus size |
| `NarrativeTrend` | Per-narrative change across snapshots | narrative, first_seen, last_seen, direction, delta |
| `EmergingNarrative` | Narrative newly significant in a later snapshot | narrative, snapshot, threshold used |

### 6.5 Supporting (non-epistemic)

| Entity | Description |
|---|---|
| `ModelRecord` | Registry of model name/version/type used anywhere |
| `StageExecution` | Per-stage status, counts, duration, errors for a run |

**Identity rule:** the analysis unit is a `Discussion` or `Comment`; every derived row
points at exactly one unit plus the run/version that produced it.

---

## 7. MVP scope summary

Full detail and rationale: [mvp-scope.md](mvp-scope.md).

**In:** Reddit only · English · batch/offline · ~500–5,000 discussions · PostgreSQL +
pgvector · one FastAPI service · one Next.js app · Sentence-Transformers-class
embeddings · density-based clustering · validated sentiment + stance · provider-independent
LLM narrative extraction · evidence + relations · snapshot-based evolution · human
evaluation.

**Out (explicitly, for the MVP):** real-time/streaming, Kafka, Kubernetes, ClickHouse,
Neo4j, Elasticsearch/OpenSearch, dedicated vector databases, multiple ingestion
platforms, self-hosted large local LLMs, microservices, multi-tenant SaaS, mobile apps,
per-user accounts/authorization, cross-platform identity, non-English languages,
non-Reddit sources, automated dashboards/report scheduling, model fine-tuning.

These are deferred until a **concrete, measured** requirement exists — not because they
are hard, but because they add operational surface before the core hypothesis is proven.

---

## 8. Non-MVP scope (explicit exclusions)

| Excluded | Reason | Revisit trigger |
|---|---|---|
| Real-time streaming updates | Core hypothesis is about *coherence*, not latency | Analysts need sub-hour reaction |
| Cross-platform sources (X, news, forums) | Dilutes MVP; different APIs/ethics per platform | Reddit-only quality is proven and a source-adapter exists |
| Non-English corpora | Model/validation cost per language | English pipeline validated |
| Dedicated vector DB | pgvector is sufficient at this scale | >~10M vectors or query latency SLO breach |
| Message bus / microservices | Single-node batch is sufficient | Multi-topic concurrency or scheduling demand |
| Search engine (ES/OpenSearch) | Postgres text/trigram search covers MVP needs | Complex relevance ranking required |
| Graph DB | Relations are low-volume and queryable in SQL | Deep multi-hop graph analytics required |
| Per-user accounts, multi-tenancy, RBAC | MVP is single-operator | External users / sharing |
| Cross-platform identity, dossier features | **Ethically prohibited** (see §12) | Never |
| Automated PDF/scheduled reports | Not needed to validate the hypothesis | Stakeholder reporting demand |
| Model fine-tuning / custom training | Pretrained + validated classifiers suffice | Off-the-shelf accuracy proven insufficient |

---

## 9. Success criteria (summary)

Full rubric and thresholds: [success-criteria.md](success-criteria.md).

The MVP succeeds only if the **central hypothesis** holds:

> Semantic clustering + stance + sentiment + LLM narrative extraction produce
> **coherent, useful, evidence-grounded narratives that humans judge meaningful**.

| # | Criterion | Threshold (MVP) |
|---|---|---|
| SC-1 | **Narrative coherence** — human raters judge narratives as coherent and non-generic | ≥ 70% rated "coherent" |
| SC-2 | **Evidence grounding** — raters judge that the cited evidence actually supports the narrative | ≥ 80% rated "supported" |
| SC-3 | **Distinctness** — discovered opinion groups are meaningfully different, not arbitrary slices | ≥ 60% of group pairs judged distinct |
| SC-4 | **Utility** — an analyst reports the output answered their question faster/better than manual reading | ≥ 2 of 3 raters agree |
| SC-5 | **Auditability** — every narrative can be traced to source text and to the versions that produced it | 100% (hard gate) |
| SC-6 | **Honesty** — no published narrative lacks evidence; low-confidence items are labeled | 100% (hard gate) |
| SC-7 | **Reproducibility** — a re-run with pinned versions reproduces the structural result | Verified once end-to-end |

SC-5 and SC-6 are **gates**, not scores: failing either fails the MVP regardless of SC-1..4.

---

## 10. Terminology

Authoritative definitions live in [glossary.md](glossary.md). The most load-bearing
distinctions for this document:

- **Source truth** vs **ML observation** vs **AI interpretation** vs **temporal observation**
- **Topic** → **Discussion** → **Semantic representation** → **Opinion group** →
  **Stance/Sentiment** → **Narrative** → **Evidence** → **Relation** → **Evolution**

These layers are **never collapsed**. A narrative is not a cluster; a cluster is not a
topic; sentiment is not stance.

---

## 11. Assumptions

| # | Assumption | If wrong | Fallback |
|---|---|---|---|
| A-1 | Reddit's public API is reachable with OAuth credentials for the chosen subreddits | Ingestion blocked | Use a documented archive/dump as source truth behind the same adapter |
| A-2 | Only **public** content is collected | Boundary violation | Do not collect; stop |
| A-3 | ~500–5,000 discussions carry enough signal | Weak/noisy groups | Raise collection window; report "insufficient signal" honestly |
| A-4 | English-only is acceptable for the MVP | Coverage gap | Add languages later behind a language parameter |
| A-5 | Batch latency is acceptable to users | UX mismatch | Add scheduling; streaming only if measured |
| A-6 | An LLM is available and affordable at MVP volume | No narratives | Echo provider off; other layers still work (NFR-10) |
| A-7 | Pretrained embeddings + classifiers are adequate | Quality floor not met | Evaluate alternatives; fine-tuning is post-MVP |
| A-8 | Density-based clustering suits "unknown number of groups" | Unstable groups | Compare with alternatives in `experiments/` |
| A-9 | A single node suffices | Cost/latency | Scale vertically first; distribute only on measurement |
| A-10 | Human raters are available for evaluation | No SC-1..4 measurement | MVP cannot be declared successful — evaluation is mandatory |
| A-11 | Operators can run `docker compose` + documented commands | Onboarding friction | Improve scripts/docs |

---

## 12. Risks

### 12.1 Technical

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| Embeddings poorly represent short/ironic text | Bad clusters → bad narratives | Medium | Evaluate embedding candidates in `experiments/`; keep model versioned |
| Cluster instability across runs | Users distrust groups | Medium | Pin versions/params; record them; report stability; prefer density-based |
| LLM hallucinated narratives | **Erosion of trust** | High | Mandatory evidence links (FR-9.3); structured output validation; confidence labels; human eval (SC-1/2) |
| LLM cost overrun | Run aborts / budget surprise | Medium | Token accounting + budget cap (NFR-9); batch only where needed |
| LLM output schema violations | Corrupt interpretations | Medium | Strict validation; reject + record (NFR-15) |
| Stance classifier inaccuracy | Misleading group positions | Medium | Validate on labeled sample (FR-7.3); report confidence; treat as observation |
| Reddit rate limits / API change | Ingestion fails | Medium | Idempotent, resumable runs; explicit errors; adapter isolates the source |
| English/Reddit bias over-generalized | Dishonest conclusions | High | Scoped language everywhere; corpus size always shown (FR-15.1) |
| pgvector performance at scale | Slow queries | Low (MVP) | Index tuning; revisit trigger documented in scope |

### 12.2 Product

| Risk | Impact | Mitigation |
|---|---|---|
| Narratives judged "obvious" or generic | No user value | Prefer specific, claim-level narratives; evaluate utility (SC-4) |
| Users read AI interpretation as fact | Harm | Visual + API epistemic labeling (FR-8.2, FR-14.1, FR-15.2) |
| Scope creep into monitoring/surveillance tooling | Ethical breach | Locked non-MVP scope (§8), §13 boundaries, review gate |
| Results not reproducible | Unusable in research | Version pinning + provenance (NFR-5..8) |
| "Insight" not actionable | Abandonment | Validate with the primary persona before building dashboards |

### 12.3 Ethical & legal

| Risk | Impact | Mitigation |
|---|---|---|
| Re-identification of pseudonymous authors | Harm to individuals | Aggregate-only outputs; no profile enrichment; no cross-platform stitching (§13) |
| Platform ToS violation | Access revoked / legal | Respect API terms + rate limits; store only what is permitted |
| Sensitive-attribute inference | Discrimination risk | Prohibited outright; out of scope by policy |
| Over-claiming population representativeness | Misinformation | Mandatory scoped language + corpus size |

Mitigations marked "hard" are enforced by requirements (FR/NFR) or by §13, not by habit.

---

## 13. Ethical & data boundaries

NarraX analyzes public data to produce **aggregate** intelligence. It must never become
a tool for tracking or profiling individuals. Full statement: [data-safety.md](data-safety.md).

### Prohibited (never, not "post-MVP")

- Deanonymization or re-identification of authors
- Personal dossiers or individual profiles
- Private-user surveillance or hidden user tracking
- Cross-platform identity stitching
- Inference of sensitive personal attributes (health, sexuality, politics, religion, etc.)
- Individual political profiling

### Required practice

1. **Pseudonymity:** authors are handled as opaque handles; no enrichment from other data.
2. **Aggregation:** outputs describe groups and patterns, not individuals. Minimum-group
   sizes are enforced before a claim is shown.
3. **Scope honesty:** always say *"Among the analyzed public Reddit discussions…"* —
   never *"Everyone believes…"*.
4. **Evidence grounding:** every narrative cites its source messages; no narrative without
   evidence (FR-9.3).
5. **Epistemic labeling:** consumers can always tell source truth from ML observation from
   AI interpretation from temporal observation.
6. **Purpose limitation:** collected data is used only for the stated aggregate analysis.
7. **Review gate:** any new feature is checked against this section before implementation;
   features that cannot satisfy it are rejected, not deferred.

---

## 14. Traceability

| Product concept | Requirements | Success criteria |
|---|---|---|
| Topic definition | FR-1..FR-1.2 | — |
| Source truth | FR-2..FR-2.6, NFR-8 | SC-5 |
| Semantic representation | FR-4..FR-4.3 | SC-3 |
| Opinion groups | FR-5..FR-5.4 | SC-3 |
| Sentiment / stance | FR-6, FR-7..FR-7.3 | SC-1, SC-3 |
| Narratives | FR-8..FR-8.5 | SC-1, SC-4, SC-6 |
| Evidence | FR-9..FR-9.3 | SC-2, SC-6 |
| Relations | FR-10..FR-10.2 | SC-1 |
| Evolution | FR-11..FR-11.4 | SC-4 |
| Comparison | FR-12..FR-13 | SC-4 |
| Access surfaces | FR-14..FR-17 | SC-4, SC-5 |
| Operations | FR-18..FR-21, NFR-16..18 | SC-7 |
| Ethics | §13, FR-2.5 | SC-6 |
