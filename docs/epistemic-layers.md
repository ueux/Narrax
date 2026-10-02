# Epistemic Layers

NarraX keeps distinct kinds of information strictly separated. Never present an AI
interpretation as though it were raw source truth.

## Layer 1 — Source truth

Actual collected public source data (discussions, comments, authors as pseudonyms,
timestamps). This is immutable reference data. It is never overwritten by derived
results.

## Layer 2 — ML observations

Deterministic, model-derived facts: embeddings, cluster assignments, sentiment scores,
stance labels, model + pipeline version that produced them. Observations are versioned
so results can be reproduced and compared.

## Layer 3 — AI interpretations

Narratives, explanations, and inferred relationships produced by LLMs. These are
always stored with their provenance (which evidence, which model, which prompt, which
date) and are clearly labeled as generated interpretation, not observation.

## Layer 4 — Temporal observations

Historical snapshots and evolution records. A narrative or cluster "changed" claim is
itself an observation tied to specific snapshots, not a casual assertion.

## Rules

1. Never merge source truth with ML output in the same field/table.
2. Version every model and pipeline run; record versions on outputs.
3. Keep AI interpretations separate from observations.
4. Ground every narrative claim in source evidence.
5. Use careful, scoped language ("Among the analyzed public Reddit discussions...").
