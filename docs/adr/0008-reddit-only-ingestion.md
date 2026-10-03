# ADR-0008: Reddit-only ingestion behind a source adapter

- **Status:** Accepted
- **Date:** 2026-03-10
- **Related:** [architecture.md](../architecture.md#31-backend-package-layout) · [data-flow.md](../data-flow.md) · [data-safety.md](../data-safety.md)

## Context

NarraX needs public discussion data. Candidate sources differ in API shape, licensing,
terms of service, data quality, and the ethics of analysis. Supporting several sources at
once multiplies: clients, rate-limit strategies, normalisation rules, exclusion rules, and
ToS/ethics reviews.

Meanwhile the MVP's hypothesis is about **narrative quality**, not source breadth. If the
intelligence layer cannot produce coherent, evidence-grounded narratives from one
well-understood source, adding sources will not help.

## Decision

Support **Reddit only** for the MVP, collected through the **official API (OAuth)**, behind
an ingestion adapter boundary.

- All source-specific logic (auth, pagination, rate limiting, field mapping) lives in
  `ingestion/`; nothing above it knows it is Reddit.
- Layer-1 schema is source-neutral (`source`, `source_id`, `permalink`, `created_at`,
  `author_handle`, `body`), so a second source is an adapter, not a migration of meaning.
- Only **public** content is collected. Authors are stored as opaque pseudonymous handles
  and are never enriched (see [data-safety.md](../data-safety.md)).
- Ingestion is batch, idempotent, and resumable (ADR-0004; FR-2.3).

## Consequences

### Positive

- **One integration to get right** — auth, rate limits, pagination, and ToS compliance.
- **A single domain of content** to tune exclusions and prompts against.
- **Ethics review is scoped** to one platform's terms and one platform's notion of public.
- **Source breadth is deferred, not precluded** — the adapter boundary and source-neutral
  schema keep a second platform additive.
- Rate-limit handling is confined to one module, so a throttled source cannot corrupt
  derived layers.

### Negative / costs

- **Sampling bias.** Reddit skews young, male, English-speaking, and tech-heavy. Results
  describe *the analyzed corpus*, never a population — enforced by mandatory scoped
  language (FR-15.1) and the `scope_note` in every response.
- **Single point of failure.** An API change, outage, or policy change halts acquisition.
- **No cross-platform comparison** in the MVP (FR-13 is `MAY`).
- **Terms-of-service evolution** may require changes to collection or retention.

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| Multi-platform from day one | Multiplies integration + ethics surface before the core hypothesis is tested |
| Scraping without the official API | ToS/legal exposure; fragile; ethically worse |
| Pre-built public Reddit dumps only | Snapshot bias, no window/terms selection, no provenance of retrieval |
| Synthetic/benchmark corpora | Do not answer the product question |

## Revisit trigger

Reddit-only output passes the success criteria (so the intelligence layer is not the
bottleneck) **and** a user needs cross-platform comparison. Then add a second adapter —
after a per-platform ethics/ToS review recorded as an ADR.
