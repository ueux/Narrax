# ADR-0004: Batch/offline processing model

- **Status:** Accepted
- **Date:** 2026-03-10
- **Related:** [architecture.md](../architecture.md#5-analysis-pipeline-batch-path) · [mvp-scope.md](../mvp-scope.md#3-out-of-scope-and-the-exact-revisit-trigger) · [ADR-0013](0013-excluded-infrastructure.md)

## Context

The product question is *"what are people believing and saying about a topic, and how are
those narratives changing?"* Answering it requires a corpus-level view: embeddings over the
whole corpus, clustering across items, and narrative extraction per group. These operations
are inherently **global** — you cannot meaningfully cluster one message at a time.

An alternative model is streaming/incremental: ingest continuously and update clusters and
narratives as events arrive. That requires a message broker, incremental clustering,
upsert semantics for derived data, and streaming infrastructure.

## Decision

Process in **batch, per topic**, offline.

- A run is triggered explicitly (CLI/worker), covers a topic and a time window, and
  produces a `PipelineRun` with per-stage records.
- Stages are idempotent and individually re-runnable, and a run is resumable after failure.
- Freshness is expressed through **snapshots** (re-running over an extended window), not
  through continuous streaming.

## Consequences

### Positive

- **Simpler and cheaper.** No broker, no streaming state, no incremental-clustering
  algorithm research.
- **Reproducible by construction.** A run is a discrete, versioned, inspectable unit —
  which the success criteria (SC-7, G-5) require.
- **Global algorithms work naturally.** Clustering sees the whole corpus, which is the point.
- **Cost is bounded and forecastable.** LLM spend is per run, not per event, so a budget cap
  is enforceable before the run starts (NFR-9).
- **Partial failure is survivable.** A failed stage marks the run partial; earlier layers
  remain valid and queryable.

### Negative / costs

- Results lag acquisition — acceptable because the MVP hypothesis is about *coherence*, not
  latency.
- Re-running the full pipeline to refresh is more expensive than incrementally updating.
- No real-time alerting; a narrative spike is visible at the next snapshot.
- Snapshot cadence becomes a design parameter that must be chosen explicitly.

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| Kafka/Redpanda + stream processors | Substantial infrastructure for a question that does not require low latency |
| Incremental/online clustering | Algorithmically harder and less stable than batch density clustering; undermines reproducibility |
| Cron-triggered micro-batches only | Fine as a *scheduling* layer later; does not change the processing model |

## Revisit trigger

A **measured** need for sub-hour reaction (e.g. a stakeholder cannot wait for the next
snapshot). Then add scheduling first (cron/worker), and only add streaming if scheduling
provably cannot meet the latency target.
