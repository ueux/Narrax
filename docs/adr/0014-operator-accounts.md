# ADR-0014: Operator accounts (`users`) in the MVP

- **Status:** Accepted
- **Date:** 2026-10-26
- **Related:** [data-safety.md](../data-safety.md) · [mvp-scope.md §3](../mvp-scope.md#3-out-of-scope-and-the-exact-revisit-trigger) · [database.md](../database.md)

## Context

`mvp-scope.md` §3 excludes **multi-tenancy, accounts, and RBAC** (exclusion X-11), on the
grounds that the MVP is single-operator. PROMPT 05 nevertheless specifies a `users` table as
part of the core schema.

Those two positions only conflict if `users` means "end users of a hosted product". They do not
conflict if `users` means **the analyst operating NarraX** — the person who defines a topic and
triggers a run. The MVP already produces records that need an author: a `topic` is someone's
saved analysis target, and an `analysis_run` is someone's execution of a pipeline.

There is also a safety dimension worth making structural. NarraX handles two very different
kinds of identity:

- **operators** — the people using the tool, who are accountable for its use;
- **authors** — pseudonymous people whose public posts were collected, who must never be
  profiled, enriched, or linked (docs/data-safety.md).

Collapsing those into one "user" concept is exactly the modelling mistake that leads to
tooling that treats collected people as account holders.

## Decision

Add a minimal `users` table representing **operator identity only**, and keep it strictly
separate from `authors`:

- `users` — `email` (lower-cased, unique), `display_name`, `is_active`. No roles, no
  permissions, no tenancy, no authentication secrets.
- `authors` — pseudonymous source handles with no profile data whatsoever.
- The two tables never reference each other, and no query joins them.

`topics.created_by_user_id` and `analysis_runs.triggered_by_user_id` are nullable with
`ON DELETE SET NULL`, so deleting an operator never deletes analysis history.

This is a **scope change** under [mvp-scope.md §6](../mvp-scope.md#6-scope-change-protocol) and
is recorded here for that reason.

## Consequences

### Positive

- **Attribution without profiling.** Runs and topics have an accountable owner while collected
  authors remain anonymous.
- **The operator/author separation is enforced by the schema**, not by convention — there is no
  path from a user row to an author row.
- **Deleting an operator is safe.** History survives with a NULL owner.
- **Forward-compatible with X-11.** If real authentication or multi-tenancy is ever added, the
  identity table already exists and gains columns; no data migration of *authors* is implied.

### Negative / costs

- **A table that is barely used at MVP.** There is no login, so rows are created administratively.
- **Reintroduces an excluded concept.** This is precisely why the decision is recorded as an ADR
  rather than slipped in — X-11's exclusion now means "no multi-tenancy or RBAC", not "no
  identity table at all". `mvp-scope.md` is updated to reflect that.
- **No password/credential columns.** If authentication arrives, credentials belong in a
  separate table (or an identity provider), never alongside these rows.

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| Omit `users` entirely | Leaves `topics`/`analysis_runs` with no accountable owner, and contradicts the specified core schema |
| Reuse `authors` for operators | Actively dangerous: it would conflate collected people with tool operators |
| Store the operator name as free text on each row | No referential integrity, no identity, and typo-driven fragmentation |
| Full accounts + RBAC now | Reintroduces the multi-tenancy complexity X-11 excludes, before it is needed |

## Revisit trigger

Add authentication, roles, or tenancy only when NarraX is exposed beyond a single trusted
operator (X-11's trigger). That change adds columns and a credentials mechanism; it must not
alter the `authors` model or introduce any join between operators and collected authors.
