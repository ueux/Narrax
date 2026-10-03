# ADR-0009: Epistemic layer separation in the data model

- **Status:** Accepted
- **Date:** 2026-03-10
- **Related:** [epistemic-layers.md](../epistemic-layers.md) · [data-flow.md](../data-flow.md) · [product-requirements.md §6](../product-requirements.md)

## Context

NarraX mixes four fundamentally different kinds of information:

1. **Source truth** — what people actually posted (verifiable).
2. **ML observations** — what a model computed (deterministic given a version).
3. **AI interpretations** — what an LLM said the data means (plausible, not verifiable).
4. **Temporal observations** — how things changed between snapshots.

If these are stored or presented together, three failures follow:

- **Category error.** A user reads a model's inference as a fact about the world.
- **Silent corruption.** Re-running a model overwrites the evidence it was derived from.
- **Unreproducible results.** There is no way to tell which version produced which output.

The temptation is real: it is simpler to `UPDATE` a row with the model's label, or to let
the LLM write a narrative into the same field as the source text.

## Decision

Separate the layers **structurally**, not by convention.

1. **Distinct tables per layer.** Layer-1 tables are written only by `ingestion/`; derived
   layers live in different tables (see [data-flow.md §5](../data-flow.md#5-layer--storage--consumers)).
2. **Append-only per version.** Derived rows are keyed by *(unit, method, version)*; a new
   version creates new rows. Source truth is never overwritten (FR-4.3, NFR-8).
3. **Mandatory provenance.** Every Layer 2/3/4 row references the run, stage, model, and
   (for interpretations) prompt version that produced it (NFR-5, NFR-6).
4. **Explicit labels at the edge.** API responses and UI put layer identity in the payload
   and in the rendering (FR-8.2, FR-14.1, FR-15.2).
5. **A hard publishability gate.** An AI interpretation without evidence links is invalid
   and is never stored as publishable (FR-9.3, gate G-2).

## Consequences

### Positive

- **Category errors become hard to make**, because the schema does not let you write an
  interpretation where an observation belongs.
- **Auditability is structural** — the provenance chain (gate G-1) is foreign keys, not
  documentation.
- **Model upgrades are safe.** Old observations and interpretations remain queryable and
  explainable after a new version is added.
- **Honest UI is enforceable.** The frontend has distinct fields to render differently.
- **Evaluation is possible.** You can compare versions because both exist side by side.

### Negative / costs

- **More tables and more joins** than a single denormalised table.
- **Storage grows** with each version rather than being overwritten.
- **More discipline at write time** (run/version must be threaded through every stage).
- **Query complexity** for "latest per unit" views (solved with a version/run ordering or a
  materialised view when needed).

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| One table with a `type` column | Loses FK-level auditability; encourages cross-layer writes |
| Overwrite-in-place with a `model_version` column | Destroys history; makes SC-7/G-5 unprovable |
| JSON blob per unit holding all derived data | Unqueryable, unconstrainable, and impossible to validate per layer |
| Convention/comment-based separation | This is exactly the failure mode that documentation cannot prevent |

## Revisit trigger

Do not revisit the separation itself. Revisit only its **mechanics**: if read-path joins
become a measured bottleneck, add targeted materialised views or denormalised read models —
**derived from** the separated tables, never replacing them as the system of record.
