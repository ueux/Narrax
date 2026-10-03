# ADR-0007: Density-based (HDBSCAN) clustering

- **Status:** Accepted
- **Date:** 2026-03-10
- **Related:** [architecture.md](../architecture.md) · [product-requirements.md FR-5](../product-requirements.md) · [success-criteria.md SC-3](../success-criteria.md)

## Context

Opinion groups are not known in advance. For any given topic the number of distinct
positions may be 1 (no real split), 3, or 12 — and it differs per topic. Many messages
belong to no coherent group at all (asides, jokes, tangents).

We need a clustering approach that: does not require specifying *k*; tolerates outliers
without distorting groups; produces groups that a human would call distinct (SC-3); and
whose parameters and version can be recorded for reproducibility (NFR-5).

## Decision

Use **density-based clustering (HDBSCAN-class)** over the embedding space.

- The algorithm and its parameters (e.g. minimum cluster size, metric, min samples) are
  configuration, and a **hash of those parameters** identifies a `ClusterRun` (ADR-0009).
- **Noise is a first-class outcome** (`is_noise`): items that do not belong to a dense
  region are labelled noise, not forced into the nearest group (FR-5.2).
- Cluster labels are derived from **member content** (representative items + c-TF-IDF-style
  terms), not invented by an LLM (FR-5.4).
- When the corpus has no dense structure, the honest result is "no distinct groups" — this
  is a valid output and must be reported as such, never padded into groups.

## Consequences

### Positive

- **No *k* to guess.** Group count emerges from the data, matching an unknown-group problem.
- **Outliers are handled explicitly**, which is exactly the behaviour wanted: better fewer,
  coherent groups than many forced ones.
- **Reproducible when pinned.** Params + embedding version determine a run.
- **Parameter sensitivity is measurable** (min cluster size → group count/noise ratio),
  giving a concrete diagnostic for SC-3.
- Widely used on embedding spaces, so failure modes are documented.

### Negative / costs

- **Parameter sensitivity.** Results can shift noticeably with minimum cluster size; some
  tuning per corpus scale is expected.
- **High noise ratios are common** on short, heterogeneous text — a noise ratio above ~50%
  must be investigated and explained in the run report, not ignored.
- **Not incremental.** New data means re-clustering (consistent with ADR-0004).
- **Variable group count** complicates UI/pagination expectations compared with fixed-*k*.
- Cluster *stability* is not guaranteed by the algorithm and must be measured.

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| k-means | Requires *k* in advance; forces every item into a cluster; spherical-bias suits embeddings poorly |
| Hierarchical (agglomerative) | Needs a cut threshold; still assigns all items; less robust to noise |
| Topic modelling (LDA/BERTopic) | Topic ≠ opinion group; BERTopic internally uses density clustering anyway |
| LLM-based grouping | Non-deterministic, costly, and hard to reproduce at corpus scale — and it would blur observation with interpretation |

## Revisit trigger

Repeated evaluation shows group count is unstable under small parameter changes, **or**
noise ratio stays prohibitive at the chosen scale. Response: compare alternatives in
`experiments/` (including BERTopic and HDBSCAN variants) and record the outcome as a new
ADR; keep the clustering result versioned either way.
