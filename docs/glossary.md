# NarraX Glossary

Authoritative terminology for the NarraX project. When a word is used in code, docs, or
UI, it means exactly what is written here. Alphabetical.

Related: [product-requirements.md](product-requirements.md) ·
[epistemic-layers.md](epistemic-layers.md) · [architecture.md](architecture.md)

---

## A

**Aggregate intelligence**
Insight about *groups and patterns*, never about identifiable individuals. NarraX output
is aggregate by design (see [data-safety.md](data-safety.md)).

**AI interpretation**
Output produced by a generative model (e.g. an LLM): narratives, explanations, inferred
relations. Always provenance-bound, always labeled, never presented as source truth.

**Analysis unit**
The atomic text object that observations attach to. In the MVP this is a `Discussion`
(submission) or a `Comment`. Every derived row points at exactly one analysis unit.

**Author (pseudonymous)**
The handle/id of whoever posted a source item. Treated as an opaque label. NarraX never
enriches, links, or profiles authors.

## C

**Cluster**
A group of analysis units that are semantically similar in embedding space. Also called
an **opinion group** when interpreted as a shared position. A cluster is an *ML
observation*, not a narrative.

**Cluster membership**
The assignment of one analysis unit to one cluster, with a distance/probability and an
`is_noise` flag.

**Comment**
A source reply to a discussion or to another comment. Part of Layer 1 (source truth).

**Community**
In the MVP, a subreddit (or a defined set of subreddits). Used as a comparison dimension.

**Confidence**
An explicit, stored measure of how much to trust a derived item (stance label, narrative,
relation). Low confidence must be surfaced, never silently upgraded.

**Corpus**
The set of source items actually analyzed for a topic. Always reported alongside results
("among N analyzed public Reddit discussions").

**Cross-platform**
Combining data from more than one platform. **Out of MVP scope** and, for identity
purposes, prohibited entirely.

## D

**Discussion**
A source submission (a Reddit post): title + body + metadata. Part of Layer 1.

**Derived data**
Anything computed from source truth (embeddings, clusters, sentiment, stance, narratives,
relations, trends). Never overwrites source truth.

## E

**Embedding**
A dense numeric vector representing an analysis unit's meaning, produced by a versioned
model. An ML observation. Stored with model name, version, and dimensionality.

**Emerging narrative**
A narrative that is significant in a later snapshot but absent or negligible in an
earlier one. A temporal observation.

**Entity**
A persisted object in the domain model (Topic, Discussion, Narrative, …). See
[product-requirements.md §6](product-requirements.md#6-core-entities).

**Epistemic layer**
One of the four strictly separated kinds of data: source truth, ML observation, AI
interpretation, temporal observation.

**Evidence**
Source items linked to a narrative that support it. A narrative without evidence is
invalid.

**Evolution (narrative)**
Change in narratives over time, computed from snapshots. A temporal observation.

## G

**Grounding**
Binding an AI interpretation to specific source evidence so a human can verify it.

## H

**HDBSCAN**
Hierarchical Density-Based Spatial Clustering of Applications with Noise. The candidate
clustering algorithm: finds a variable number of groups and explicitly labels outliers as
noise. An implementation choice, not a product concept.

## I

**Idempotent (ingestion)**
Re-running collection over the same window and criteria produces no duplicates and no
mutations to existing source rows.

**Ingestion**
Collecting public source data into Layer 1. In the MVP: Reddit, batch, via the official
API.

**Ingestion run**
One execution of ingestion: topic, window, counts, status, timestamps.

## L

**Layer 1 / 2 / 3 / 4**
Shorthand for source truth / ML observations / AI interpretations / temporal observations.

**LLM (Large Language Model)**
The generative model used for narrative extraction. Accessed only through a
provider-independent abstraction (see ADR-0005).

## M

**ML observation**
A deterministic-ish, model-derived fact: embedding, cluster assignment, sentiment score,
stance label — each with the model and pipeline version that produced it.

**Model record**
A registry row describing a model name, version, and type used anywhere in the system.

## N

**Narrative**
An AI-extracted claim/pattern attributed to an opinion group: a concise claim plus a
short description, with provenance, confidence, and mandatory evidence links. **Not** a
cluster, **not** a topic, **not** a summary of everything.

**Narrative evidence**
The link entity between a narrative and the source items supporting it (with relevance
and rationale).

**Narrative relation**
A typed, provenance-bearing edge between two narratives:
`supports` · `contradicts` · `refines` · `co-occurs-with`.

**Noise (clustering)**
Analysis units that density-based clustering declines to assign to any group. Must remain
representable and must not be forced into a cluster.

## O

**Observation**
See **ML observation**.

**Opinion group**
A cluster interpreted as a set of people sharing a position. Used interchangeably with
"cluster" at the product level; each remains an ML observation.

## P

**pgvector**
The PostgreSQL extension providing the `vector` type and vector indexes. Chosen to avoid
a separate vector database at MVP scale (ADR-0002).

**Pipeline run**
One execution of the analysis pipeline for a topic: which stages ran, with which versions,
over which corpus, with what outcome.

**Provenance**
The recorded origin of a derived item: run, stage, model, prompt/template version, and
timestamp. Mandatory for every Layer 2/3/4 row.

**Provider abstraction**
The interface through which all LLM calls pass, so the concrete provider is chosen by
configuration, not code (ADR-0005).

## R

**Reproducibility**
The ability to re-run a pipeline with pinned versions over immutable source truth and
obtain the same structural result. Nondeterminism (e.g. LLM sampling) must be recorded,
not hidden.

## S

**Semantic representation**
The embedding-space view of the corpus. The layer between raw discussion and opinion
groups.

**Sentiment**
The emotional polarity/valence of an analysis unit (e.g. positive/neutral/negative) with
a score and model version. **Distinct from stance.**

**Snapshot**
A dated record of analysis state for a topic (corpus size, clusters, narratives) enabling
change computation. A temporal observation.

**Source item**
Any Layer 1 record: a discussion or comment (plus its `SourceItemRef` locator).

**Source truth**
The actual collected public data, stored unmodified, never overwritten by derived output.
The highest authority in any dispute.

**Stance**
The position an analysis unit takes **relative to a specific topic** (support / oppose /
neutral / unclear) with confidence and method version. Topic-relative and **distinct from
sentiment**.

**Stage execution**
The per-stage record within a run: status, counts in/out, drops with reasons, duration,
errors.

**Subreddit**
A Reddit community. The MVP's unit of *community* comparison.

## T

**Temporal observation**
A fact about change over time (trend, emerging narrative, first/last seen). Tied to
specific snapshots; never asserted loosely.

**Topic**
The subject under study, with selection criteria (query terms, subreddits, time window).
The root of the conceptual hierarchy. A topic is not a cluster and not a narrative.

**Trend (narrative)**
Per-narrative direction over snapshots: rising / stable / fading, with first-seen and
last-seen.

## U

**Uncertainty**
See **Confidence**. NarraX must express it rather than hide it.

## V

**Version (model / pipeline)**
An explicit identifier pinned to every derived output so results are attributable and
comparable. Changing a model version creates new observations rather than mutating old
ones.

## W

**Window (time window)**
The inclusive date range of source data collected for a topic.

---

## Conceptual hierarchy (canonical)

```text
Topic
  ↓
Discussion
  ↓
Semantic Representation
  ↓
Opinion Group / Cluster
  ↓
Stance + Sentiment
  ↓
Narrative
  ↓
Evidence
  ↓
Narrative Relations
  ↓
Temporal Evolution
```

These levels are **never collapsed into one another**.
