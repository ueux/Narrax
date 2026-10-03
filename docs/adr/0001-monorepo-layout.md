# ADR-0001: Monorepo with `backend/` + `frontend/`

- **Status:** Accepted
- **Date:** 2026-03-10
- **Related:** [architecture.md](../architecture.md) · [PROMPT 03 structure](../architecture.md#31-backend-package-layout)

## Context

NarraX has two deployables (a Python/FastAPI backend and a Next.js frontend) plus
non-deployable research assets (experiments, scripts, docs, local data). The team is
small and the two halves change together: an API contract change usually requires a
frontend change in the same breath.

We must choose between one repository, two repositories, or a shared-workspace monorepo
tool.

## Decision

Use **one repository** containing language-scoped top-level directories:

```text
backend/      Python service, migrations, tests
frontend/     Next.js app
docs/         product + architecture documentation
experiments/  research notebooks and evaluation scripts
scripts/      developer/operational scripts
data/         local data (gitignored content)
```
**No cross-language workspace orchestrator** (no Nx/Turborepo/npm workspaces spanning
Python). Each language keeps its native tooling: `pyproject.toml` for Python, `package.json`
+ pnpm for Node.

## Consequences

### Positive

- **Atomic change.** An API contract and its client change in one commit/PR.
- **One source of truth for docs.** Architecture, PRDs, and ADRs sit next to the code they
  describe, so they are more likely to stay current.
- **Simple onboarding.** One clone, one `README`, one set of scripts.
- **No orchestrator tax.** We avoid learning/operating a build graph tool for two packages.

### Negative / costs

- CI must detect which side changed to avoid running both suites on every commit.
- Repository grows over time; cloning gets slower as assets accumulate.
- Two package managers on one root can confuse newcomers — mitigated by documenting the
  split in the README.

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| Two repositories | Contract drift; cross-repo PRs; docs fragment immediately |
| Monorepo with Nx/Turborepo | Solves a build-graph problem we do not have; extra tooling and config |
| Polyglot workspace (npm workspaces + Python) | The ecosystems do not share a graph; adds ceremony without benefit |

## Revisit trigger

Revisit if the repository becomes large enough that clone/CI time blocks work, or if the
frontend and backend gain genuinely independent release cadences with separate owners.
