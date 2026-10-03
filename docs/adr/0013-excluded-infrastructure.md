# ADR-0013: Infrastructure excluded from the MVP

- **Status:** Accepted
- **Date:** 2026-03-10
- **Related:** [mvp-scope.md §3](../mvp-scope.md#3-out-of-scope-and-the-exact-revisit-trigger) · [architecture.md §13](../architecture.md#13-deliberately-excluded-infrastructure)

## Context

NarraX is a data/AI product, and the ecosystem offers a well-trodden "modern stack":
message brokers, stream processors, a dedicated vector database, a search engine, a graph
database, a columnar store, Kubernetes, and a service mesh. Introducing them is a common
way to look serious.

But the MVP's actual risk is not throughput. It is a single question:

> Do semantic clustering + stance + sentiment + LLM extraction produce narratives that
> humans judge coherent and evidence-grounded?

That question is answered at ~500–5,000 discussions per topic on **one node** with **one
database**. Every additional stateful system adds operational surface, failure modes,
credential handling, and cognitive overhead — while making the pipeline harder to reproduce
(SC-7, gate G-5) and pushing effort away from the only thing being tested.

The temptation is strongest precisely when the core hypothesis is unproven, because
infrastructure work feels productive and is easy to verify.

## Decision

**Exclude the following from the MVP, by policy:** Kafka/message brokers, Kubernetes,
ClickHouse, Neo4j, Elasticsearch/OpenSearch, dedicated vector databases, multiple ingestion
platforms, self-hosted large LLMs, microservices, multi-tenancy, and orchestration
frameworks.

Each is admitted **only** when its specific, measured revisit trigger is observed and an ADR
records the change (see [mvp-scope.md §3](../mvp-scope.md#3-out-of-scope-and-the-exact-revisit-trigger) and
[§6](../mvp-scope.md#6-scope-change-protocol)).

## Consequences

### Positive

- **Effort stays on the hypothesis.** Engineering time goes to narrative quality and
  evaluation, not to cluster operations.
- **Reproducibility is achievable.** One database, one process, pinned versions — a re-run
  is genuinely repeatable (SC-7).
- **Debugging is tractable.** A single node with one datastore can be reasoned about wholly;
  a distributed pipeline cannot.
- **Cost stays near zero** apart from LLM calls, which are capped per run.
- **Honest architecture.** The system is exactly as complex as the problem currently
  requires, which is itself a signal of judgement.

### Negative / costs

- **Some scale ceilings are accepted deliberately.** Vector search, write throughput, and
  concurrent topic processing are bounded by one Postgres and one node.
- **A future migration costs real work** — though the module boundaries (ADR-0009,
  `services/` orchestration) are designed so that extraction is possible, not a rewrite.
- **May look less impressive** to readers equating sophistication with distributed systems;
  mitigated by documenting the reasoning here.

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| "Build it right the first time" — add the full stack now | Optimizes for a scale that does not exist while the core question is unanswered |
| Add just one broker + one vector DB now | Each is a stateful system with its own backup, auth, and upgrade path; the benefit is not yet measurable |
| Defer the decision entirely (no stance) | Ambiguity invites accidental adoption; an explicit exclusion is cheaper to maintain than a vague intention |

## Revisit trigger

Per item, and only on measurement — see
[mvp-scope.md §3](../mvp-scope.md#3-out-of-scope-and-the-exact-revisit-trigger). The general
rule: **the core hypothesis must first be validated (or the item must be required to
validate it), the trigger must be observed as a number, and an ADR must record the change.**
