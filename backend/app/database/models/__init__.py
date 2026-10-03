"""ORM models, grouped by epistemic layer.

Nothing is defined yet: Phase 1 adds the Layer 1 (source truth) tables, and later phases
add Layers 2–4. Keeping models in this package lets Alembic autogenerate migrations from
`Base.metadata`.

Layout once implemented (see docs/data-flow.md §5):

    models/
    ├── topic.py          Layer 1  topics, ingestion runs
    ├── source.py         Layer 1  discussions, comments, source item refs
    ├── observation.py    Layer 2  embeddings, clusters, sentiment, stance
    ├── narrative.py      Layer 3  narratives, evidence, provenance, relations
    ├── temporal.py       Layer 4  snapshots, trends, emerging narratives
    └── run.py            meta     pipeline runs, stage executions, model records

Explicitly **not** here: business rules (those belong to `services/`) and derived-value
computation (that belongs to `intelligence/`).
"""
