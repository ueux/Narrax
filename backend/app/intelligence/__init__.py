"""Intelligence boundary — **Layers 2–4: observations, interpretations, evolution**.

Everything that *derives* meaning from stored source text lives here.

Responsibilities
----------------
- **Layer 2 (ML observations):** embeddings, clustering, sentiment, stance. Each output is
  versioned and keyed by *(unit, method, method_version)* so a new version appends rather
  than mutates (docs/adr/0009-epistemic-layer-separation.md).
- **Layer 3 (AI interpretations):** narrative extraction and narrative relations, via the
  provider-independent LLM abstraction. Every output carries provenance (model, prompt
  version, run) and is validated against a schema before it is persisted. A narrative with
  no evidence is never publishable.
- **Layer 4 (temporal observations):** snapshots, trends, and emerging narratives computed
  from successive runs.

Must not
--------
- Serve HTTP, own a client request lifecycle, or parse request payloads (that is `app.api`).
- Bypass `app.database` to reach storage, or be imported by `app.database`.
- Persist unvalidated model output — non-conforming output is rejected and recorded.

Planned layout
--------------
    intelligence/
    ├── embeddings.py   # Layer 2  text → vectors (versioned)
    ├── clustering.py   # Layer 2  vectors → clusters + explicit noise
    ├── sentiment.py    # Layer 2  text → sentiment
    ├── stance.py       # Layer 2  text + topic → topic-relative stance
    ├── narratives.py   # Layer 3  cluster → narrative + evidence
    ├── relations.py    # Layer 3  narrative ↔ narrative edges
    ├── evolution.py    # Layer 4  snapshots → trends / emerging narratives
    └── llm/            # provider-independent LLM abstraction (ADR-0005)

References: docs/data-flow.md §3 (S3–S8) · docs/adr/0005 · docs/adr/0006 · docs/adr/0007
"""
