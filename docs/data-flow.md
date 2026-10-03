# NarraX — Data Flow

**Purpose:** trace data from acquisition to presentation, naming every transformation, its
inputs/outputs, where it is stored, how it stays idempotent, and which epistemic layer it
belongs to.

Related: [architecture.md](architecture.md) · [epistemic-layers.md](epistemic-layers.md) ·
[product-requirements.md](product-requirements.md) · [data-safety.md](data-safety.md)

---

## 1. Principles

| # | Principle | Consequence |
|---|---|---|
| DF-1 | **One-way flow.** Layer 4 ← Layer 3 ← Layer 2 ← Layer 1. | No derived value is ever an input to raw acquisition |
| DF-2 | **Only ingestion writes Layer 1.** | Everything downstream is read-only over source truth |
| DF-3 | **Derived data is append-only per version.** | A new model version adds rows; it never rewrites old ones |
| DF-4 | **Every derived row carries provenance.** | run, stage, model/method version, parameters, timestamp |
| DF-5 | **Every transformation is idempotent.** | Re-running a stage over unchanged inputs converges, not duplicates |
| DF-6 | **Exclusions are data.** | Every dropped item is recorded with a reason |
| DF-7 | **Publishability is enforced at the boundary.** | A narrative without evidence never reaches storage/serving |
| DF-8 | **Scope travels with results.** | Corpus size + window accompany every served narrative |

---

## 2. End-to-end flow

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ EXTERNAL                                                                     │
│   Reddit public API                          LLM provider (via abstraction)  │
└────────┬───────────────────────────────────────────────┬─────────────────────┘
         │ (1) read                                      │ (7) prompt → structured JSON
         ▼                                               ▲
┌───────────────────────────┐                  ┌─────────┴─────────────────────┐
│ INGESTION                 │                  │ INTELLIGENCE                  │
│  S1 fetch + normalise     │                  │  S3 embed                     │
│  S2 filter (+ reasons)    │                  │  S4 cluster                   │
└────────┬──────────────────┘                  │  S5 sentiment + stance        │
         │ (2) upsert                          │  S6 narratives + evidence     │
         ▼                                     │  S7 relations                 │
┌───────────────────────────┐                  │  S8 snapshot / evolution      │
│ LAYER 1 · SOURCE TRUTH    │─────────────────▶│                               │
│  topics, ingestion_runs,  │   (3) read text  └────────┬──────────────────────┘
│  discussions, comments    │                           │ (4..8) append
└───────────────────────────┘                           ▼
         ▲                                   ┌───────────────────────────────┐
         │ (9) evidence joins back           │ LAYERS 2–4 · DERIVED          │
         └───────────────────────────────────│  embeddings, clusters,        │
                                             │  memberships, sentiment,      │
                                             │  stance, narratives,          │
                                             │  evidence, relations,         │
                                             │  snapshots, trends            │
                                             └────────────┬──────────────────┘
                                                          │ (10) read-only
                                                          ▼
                                             ┌───────────────────────────────┐
                                             │ SERVICES → API → UI           │
                                             └───────────────────────────────┘
```

---

## 3. Stage-by-stage

Notation: **In** / **Out** / **Store** / **Idempotency** / **Layer**.

### S0 — Topic definition

- **In:** analyst intent (name, description, query terms, subreddits, window)
- **Out:** a persisted `Topic`
- **Store:** `topics`
- **Idempotency:** topic identity is explicit; editing selection criteria creates a new
  revision rather than silently changing history
- **Layer:** 1 (selection metadata, not content)

### S1 — Ingestion (Reddit → source truth)

- **In:** `Topic` (subreddits, terms, window)
- **Out:** `IngestionRun` + `Discussion` + `Comment` rows
- **Store:** `ingestion_runs`, `discussions`, `comments`, `source_item_refs`
- **Transformations:** pagination → dedupe by source id → normalise field names/time →
  attach provenance (`retrieved_at`, permalink, author handle)
- **Idempotency:** natural key `(source, source_id)` upsert; re-fetch updates only
  retrieval metadata, never authored content
- **Failure:** auth/rate → terminal stage error; single malformed item → skipped + counted
- **Layer:** **1**

> **Immutability:** the *authored* fields (title, body, created_at, author handle) are
> write-once. Only NarraX-owned retrieval metadata may be updated.

### S2 — Normalisation & filtering

- **In:** Layer-1 rows
- **Out:** kept set + `exclusion` records (item, reason)
- **Store:** `exclusions` (reason, stage, run)
- **Rules (examples):** empty/whitespace body, deleted/removed marker, non-English
  (language detection), below min length, duplicate text within topic
- **Idempotency:** deterministic per item; same input → same decision
- **Layer:** 1 meta (decisions about source items, not interpretations)

### S3 — Embedding

- **In:** kept items' text + embedding **model name/version**
- **Out:** `Embedding` rows (vector, dim, model, version)
- **Store:** `embeddings` (pgvector `vector` column + metadata)
- **Idempotency:** key `(analysis_unit, model, model_version)` — recomputation overwrites
  only the identical version, never a different one
- **Failure:** model load error → stage abort (Layer 1 stays valid)
- **Layer:** **2** (ML observation)

### S4 — Clustering

- **In:** embeddings for the chosen model version + algorithm params
- **Out:** `ClusterRun`, `Cluster` (label, size, centroid, representatives),
  `ClusterMembership` (distance/probability, `is_noise`)
- **Store:** `cluster_runs`, `clusters`, `cluster_memberships`
- **Idempotency:** `ClusterRun` keyed by `(pipeline_run, algorithm, params_hash, embedding_version)`;
  re-running the same key reuses/overwrites that run only
- **Rules:** noise is a first-class outcome (never force-assign); labels derive from member
  content (FR-5.3, FR-5.4)
- **Layer:** **2**

### S5 — Sentiment & stance

- **In:** kept text (+ `Topic` for stance) + method versions
- **Out:** `SentimentScore`, `StanceLabel` (label, confidence, method version)
- **Store:** `sentiment_scores`, `stance_labels`
- **Idempotency:** `(analysis_unit, topic?, method_version)`; neutral/low-confidence is
  stored explicitly, never upgraded silently
- **Note:** sentiment is text-level; **stance is topic-relative** — the same text may
  receive different stance for different topics
- **Layer:** **2**

### S6 — Narrative extraction (AI interpretation)

- **In:** a cluster + its members + candidate evidence items + prompt/template version
- **Out:** `Narrative` (claim, description, confidence, stats), `NarrativeEvidence`
  (→ Layer-1 items, relevance, rationale), `NarrativeProvenance` (model, prompt version,
  run, timestamp)
- **Store:** `narratives`, `narrative_evidence`, `narrative_provenance`
- **Idempotency:** key `(cluster_run, prompt_version, model)`; re-extraction with an
  unchanged key is a no-op; a changed prompt version appends a new interpretation
- **Validation gate (mandatory):** the LLM must return schema-conforming, machine-readable
  output. Non-conforming output is **rejected and recorded** (NFR-15), never persisted.
  A narrative with **zero** evidence links is **not publishable** (FR-9.3, G-2)
- **Failure:** per-cluster retry; a failing cluster is dropped with a recorded reason;
  other clusters still publish
- **Layer:** **3** (AI interpretation — always labelled, always provenance-bound)

### S7 — Narrative relations

- **In:** narratives (+ embeddings for similarity-based edges)
- **Out:** `NarrativeRelation` (from, to, type ∈ {supports, contradicts, refines,
  co-occurs-with}, confidence, `inferred_by`)
- **Store:** `narrative_relations`
- **Idempotency:** key `(from, to, type, inferred_by, method_version)`
- **Provenance:** `inferred_by` distinguishes ML similarity from LLM judgement (FR-10.1)
- **Layer:** **3**

### S8 — Snapshot & evolution

- **In:** the completed run's aggregates + prior snapshots for the topic
- **Out:** `Snapshot` (as_of, run, corpus size, per-narrative prevalence),
  `NarrativeTrend` (first_seen, last_seen, direction, delta), emerging narratives
- **Store:** `snapshots`, `narrative_trends`, `emerging_narratives`
- **Idempotency:** `(topic, as_of, run)`
- **Rule:** a "changed" claim is itself a temporal observation tied to specific snapshots —
  absolute counts are stored alongside relative share (FR-11.4)
- **Layer:** **4**

### S9 — Evaluation (offline)

- **In:** a frozen run (pinned versions) + human ratings
- **Out:** evaluation report artifact (see [success-criteria.md](success-criteria.md) §8)
- **Store:** artifact outside the served data path
- **Layer:** meta — never rendered as product output

---

## 4. Read path (serving)

```text
GET /api/v1/topics/{id}/narratives
        │
        ├─ services/ assembles: narrative (Layer 3)
        │                       + evidence → source text (Layer 1)
        │                       + provenance (run/model/prompt)
        │                       + trend (Layer 4)
        │                       + corpus scope (Layer 1 counts)
        ▼
   response DTO with explicit layer separation
```

**Guarantees**

1. **No ML on read.** Serving never triggers embedding, clustering, or an LLM call.
2. **No cross-layer merging.** Source text, observation scores, and interpretations are
   separate fields.
3. **Scope always present.** Counts and window accompany every narrative.
4. **Read-only.** No Layer-1 mutation on the read path.

```jsonc
// Illustrative response shape (contract fixed in the API phase)
{
  "topic": { "id": 12, "name": "…", "window": { "from": "…", "to": "…" } },
  "corpus": { "analyzed_items": 3820, "discussions": 940, "comments": 2880,
              "excluded": 417, "scope_note": "Among the analyzed public Reddit discussions…" },
  "narratives": [
    {
      "id": 88,
      "layer": "interpretation",
      "claim": "…",
      "description": "…",
      "confidence": 0.71,
      "cluster": { "id": 5, "label": "…", "size": 412, "is_noise": false },
      "evidence": [
        { "source_item": { "permalink": "…", "created_at": "…", "excerpt": "…" },
          "relevance": 0.83, "rationale": "…" }
      ],
      "provenance": { "model": "…", "prompt_version": "narr-v1", "run_id": 7 },
      "trend": { "direction": "rising", "first_seen": "…", "last_seen": "…" }
    }
  ]
}
```

---

## 5. Layer → storage → consumers

| Layer | Representative tables | Written by | Read by |
|---|---|---|---|
| **1 · Source truth** | `topics`, `ingestion_runs`, `discussions`, `comments`, `source_item_refs` | ingestion only | intelligence, services, API |
| **1 meta** | `exclusions` | ingestion/filtering | services, reporting |
| **2 · ML observations** | `embeddings`, `cluster_runs`, `clusters`, `cluster_memberships`, `sentiment_scores`, `stance_labels` | intelligence | intelligence (later stages), services, API |
| **3 · AI interpretations** | `narratives`, `narrative_evidence`, `narrative_provenance`, `narrative_relations` | intelligence (LLM stages) | services, API |
| **4 · Temporal** | `snapshots`, `narrative_trends`, `emerging_narratives` | intelligence (evolution) | services, API |
| **Run metadata** | `pipeline_runs`, `stage_executions`, `model_records` | services/intelligence | API, reporting |

Detailed column design belongs to the implementation phase; this mapping is the contract.

---

## 6. Idempotency & re-run semantics

| Scenario | Expected behaviour |
|---|---|
| Re-run ingestion, same window | No duplicates; only retrieval metadata refreshed |
| Re-run embedding, same model version | Same-key rows recomputed; other versions untouched |
| Re-run clustering, same params | Same `ClusterRun` reused; no new clusters |
| Re-run clustering, new params | New `ClusterRun`; previous run intact and still queryable |
| Re-run narratives, same prompt version | No-op (same key) |
| Re-run narratives, new prompt version | New interpretations appended; old ones retained |
| Pipeline interrupted mid-stage | Stage marked failed/partial; resumes from first incomplete stage |
| LLM unavailable | S6/S7 skipped; topic marked "narratives unavailable"; S0–S5/S8 remain valid |
| Source item deleted upstream | Existing Layer-1 row retained (historical record) with provenance; not silently removed |

---

## 7. Provenance chain (auditability)

Every published narrative must be resolvable through this chain (gate G-1):

```text
Narrative
 ├─ cluster ──▶ ClusterRun ──▶ embedding model+version ──▶ PipelineRun
 ├─ NarrativeProvenance ──▶ LLM model + prompt version + run + timestamp
 ├─ NarrativeEvidence ──▶ SourceItemRef ──▶ Discussion/Comment   (Layer 1)
 └─ Snapshot/Trend ──▶ run + as_of
```

If any link is missing, the narrative is **not publishable**.

---

## 8. Safety constraints in the flow

| Constraint | Where enforced |
|---|---|
| No author enrichment / no cross-platform identity | Ingestion stores handle only; no other path reads authors |
| Aggregate-only serving | Services enforce minimum group size before emitting a claim |
| Scope honesty | Every response includes corpus size + `scope_note` |
| Evidence grounding | Publishability gate at S6 |
| Secrets never logged | Config/logging boundary; LLM calls carry text only |
| Purpose limitation | Layer 1 written once, read by analysis only |
