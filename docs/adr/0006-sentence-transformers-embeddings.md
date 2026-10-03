# ADR-0006: Sentence-Transformers-class embeddings

- **Status:** Accepted
- **Date:** 2026-03-10
- **Related:** [architecture.md](../architecture.md) · [product-requirements.md FR-4](../product-requirements.md)

## Context

NarraX needs a semantic representation of each analysis unit so that:
- semantically similar messages land near each other (enabling clustering), and
- clusters can be labelled and described from their members.

Requirements: English (MVP), CPU-feasible (NFR-4), deterministic per model version
(NFR-5), no per-call cost, and no dependency on an external API for a core layer.
Text units are short (a comment, a post title + body), often informal.

## Decision

Use a **Sentence-Transformers-class** local embedding model (a bi-encoder producing a
fixed-dimension vector per unit).

- The model name, version, and output dimensionality are **configuration**, recorded on
  every embedding row (FR-4.1).
- Embeddings are stored in a `pgvector` column (ADR-0002).
- Re-embedding with a different model creates **new** observations rather than mutating old
  ones (FR-4.3), so results computed under an older model remain explainable.

## Consequences

### Positive

- **Local and free at inference time.** No per-token cost, no rate limits, no vendor outage
  in a core path.
- **CPU-feasible.** Satisfies NFR-4 without requiring a GPU.
- **Versionable.** Model + revision together form a reproducible observation version.
- **Good fit for short text.** Bi-encoders are designed for sentence/passage similarity.
- **Deterministic per version**, which is what reproducibility (SC-7) needs.

### Negative / costs

- **Quality ceiling.** A general-purpose bi-encoder will not match a large hosted model on
  nuance, irony, or domain jargon.
- **No cross-encoder reranking by default**; clustering is only as good as these vectors, so
  embedding choice directly caps SC-3.
- **Model download and memory.** First run downloads weights; inference consumes RAM/CPU.
- **Vocabulary drift on slang** can require a model upgrade — which is a versioned change,
  not an in-place edit.

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| Hosted embedding API | Per-call cost, rate limits, and an external dependency in a core layer |
| Fine-tuned domain embeddings | No labelled domain data yet; cost before the hypothesis is tested |
| TF-IDF / BM25 only | Lexical, not semantic — misses paraphrase, which is the whole point |
| LLM-generated embeddings | Expensive per unit and unnecessary for similarity |

## Revisit trigger

Evaluation (SC-1/SC-3) shows clusters are driven by surface vocabulary rather than meaning,
**or** the corpus gains a language/domain the chosen model handles poorly. Response:
evaluate alternatives in `experiments/`, then pin the winner as a new version — never
overwrite the existing embedding set.
