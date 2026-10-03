"""Pydantic schemas — the API's typed contracts.

Schemas define what crosses the HTTP boundary: request payloads and response bodies.
They exist so that ORM models never leak to clients and so every response shape is
explicit and versionable.

Rules
-----
- Response schemas carry **epistemic labels** (source truth / ML observation / AI
  interpretation / temporal observation) and corpus scope, so a client cannot present an
  interpretation as fact (FR-14.1, FR-15.1).
- Schemas are DTOs: no database access, no business rules.
"""
