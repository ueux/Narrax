"""API boundary — the HTTP edge.

Owns request parsing/validation, dependency wiring, status codes, and response shaping.
Contains **no** analysis logic and never opens its own database session.

Modules
-------
- `router.py` — aggregates every route module under a single router.
- `dependencies.py` — shared dependency aliases (`DbSession`, ...) so routes do not
  hand-write `Depends(...)` wiring.
- `routes/` — one module per resource. Phase 1+ adds `topics`, `narratives`, `clusters`,
  `timeline`, alongside `health`.

Rule: every response carries epistemic labels and corpus scope, so a client cannot present
an AI interpretation as source truth (FR-14.1, FR-15.1).
"""
