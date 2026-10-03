# ADR-0005: Provider-independent LLM abstraction

- **Status:** Accepted
- **Date:** 2026-03-10
- **Related:** [architecture.md](../architecture.md#10-configuration-strategy) · [product-requirements.md FR-8.5](../product-requirements.md)

## Context

Narratives are the product's core output, and they are produced by an LLM. LLM providers
differ in SDK, auth, pricing, rate limits, structured-output support, context limits, and
availability — and the landscape changes quickly. NarraX must not be coupled to one vendor:
a cost change, an outage, a deprecation, or a better model should be a **configuration**
change, not a refactor.

The pipeline also must keep working when no LLM is configured at all (NFR-10).

## Decision

Define a **provider-independent interface** for LLM use, with concrete providers behind it.

- `intelligence/` depends only on the interface, never on a vendor SDK.
- Selection happens by configuration (`LLM_PROVIDER`, model name, and credentials).
- The interface returns **validated structured output**, not free text.
- Absence of configuration disables only the LLM-dependent stages (S6/S7) and marks the
  topic accordingly; all other layers still produce output.

The interface is intentionally narrow — the operations NarraX actually needs:

```text
complete_structured(prompt, schema, params) -> validated structured output + usage
```

Callers never see vendor types, HTTP details, or retry internals.

## Consequences

### Positive

- **No vendor lock-in.** Swapping providers is configuration.
- **Cost/quality experiments are cheap.** Provider A vs B is one config change, enabling
  evaluation instead of debate.
- **Testability.** The interface can be faked deterministically, so the pipeline can be
  tested for schema conformance without network calls or spend.
- **Graceful degradation is structural**, not an afterthought.
- **Structured output is enforced at the boundary**, which is what makes mandatory evidence
  and provenance possible.

### Negative / costs

- **Lowest-common-denominator risk.** The interface can only expose features all providers
  support; provider-specific capabilities need an explicit extension.
- **Abstraction overhead.** ~1 extra layer between the pipeline and the vendor SDK.
- **Structured-output support varies.** Some providers need prompt-level JSON coercion;
  those differences live inside the adapter, never leak into the pipeline.
- **Version recording is mandatory** (model name + version + prompt version) or auditability
  (G-1) breaks.

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| Use one provider's SDK directly | Lock-in; every provider change becomes a refactor |
| LangChain-style framework as the abstraction | Large dependency and an opinionated model layer; more surface than we need |
| Local-only LLM | Cost/quality/hardware tradeoffs the MVP should not be forced into |
| No abstraction, swap at call sites | Guarantees the coupling we are trying to avoid |

## Revisit trigger

Revisit if ≥2 providers are in real use and the narrow interface demonstrably blocks a
capability that materially improves narrative quality (e.g. native tool use, very long
context). Extend the interface deliberately; do not leak vendor types.
