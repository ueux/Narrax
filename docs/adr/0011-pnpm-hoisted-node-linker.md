# ADR-0011: pnpm with hoisted node linker

- **Status:** Accepted
- **Date:** 2026-03-10
- **Related:** [architecture.md §3.3](../architecture.md#33-frontend-structure)

## Context

The frontend needs a Node package manager. pnpm is preferred for its content-addressable
store and fast, disk-efficient installs. However, pnpm's default `isolated` node linker
creates `node_modules` entries as symlinks/junctions into a virtual store — and Next.js
resolves some of its own dependencies with `require.resolve()` from the **package's own
directory** during startup.

That combination is a known source of failure on Windows: a package resolved through a
junction does not resolve its *nested* dependencies, producing errors such as
`Cannot find module 'styled-jsx/package.json'` even though the package is present in the
store.

This was **observed directly** while verifying the Phase 0 scaffold: with the isolated
linker, `next build` failed on `styled-jsx` resolution; resolving the same specifier from
the real `.pnpm` path succeeded, confirming a junction-resolution problem rather than a
missing package. Switching to a flat layout made the same build succeed with no code change.

A second observation shaped the configuration's *location*: **pnpm 11 reads these settings
from `pnpm-workspace.yaml`, not `.npmrc`.** With the settings in `frontend/.npmrc`,
`pnpm config get node-linker` returned `undefined` and installs used the isolated linker;
moving the same keys into `pnpm-workspace.yaml` made them take effect
(`pnpm config get node-linker` → `hoisted`). `pnpm-workspace.yaml` is therefore the single
source of truth for pnpm settings, and the redundant `.npmrc` was removed.

## Decision

Use **pnpm with the hoisted node linker** (a flat, npm-like `node_modules`), configured in
`frontend/pnpm-workspace.yaml`:

- `nodeLinker: hoisted` — flat `node_modules`.
- `storeDir: .pnpm-store` — project-local content-addressable store (gitignored).
- `verifyDepsBeforeRun: false` — installing is an explicit, documented step
  (`scripts/bootstrap.*`), so `pnpm typecheck` / `lint` / `build` stay fast and do not
  trigger surprise network activity.
- `allowBuilds` — build-script approvals for optional native dependencies, declared
  explicitly rather than left implicit.
- The pnpm version is pinned via `packageManager` in `frontend/package.json`.
- The lockfile is committed; the store is gitignored.

## Consequences

### Positive

- **Predictable module resolution.** Flat `node_modules` removes the junction-dependent
  resolution path that broke `next build`.
- **Cross-platform consistency.** Windows, macOS, and Linux resolve identically.
- **Tooling compatibility.** Tools that assume npm-style hoisting (legacy loaders, some
  ESLint/Next plugins) work without additional flags.
- **Still fast and disk-efficient**, retaining pnpm's store and lockfile benefits.
- **Hermetic store** in-project (`storeDir: .pnpm-store`), so installs do not depend on a
  machine-global store location.

### Negative / costs

- **Loses strict dependency isolation.** Code can import a transitive dependency that is not
  declared in `package.json` ("phantom dependency"), which the isolated linker would reject.
  This is a real risk that hoisting trades away.
- **Larger `node_modules`** on disk than the isolated layout.
- **Non-default configuration location** must be understood by contributors: settings live
  in `pnpm-workspace.yaml` (pnpm 11), not `.npmrc` — documented in the frontend README.
- **Installing is explicit.** With `verifyDepsBeforeRun: false`, adding a dependency and
  running a script without `pnpm install` first fails with a module-not-found error instead
  of self-healing. This is deliberate — the failure is loud and immediate rather than a
  silent multi-minute install in the middle of a check.
- **Project-local store** means each clone has its own store, so it is not shared across
  repositories on the machine.

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| pnpm default (isolated) | Reproduced a real `next build` failure on Windows; requires pinning Next to specific workarounds |
| npm | Works, but slower installs and less efficient disk usage than pnpm |
| Yarn (Berry/PnP) | PnP is a larger behavioural change; classic Yarn offers no advantage over pnpm |
| pnpm isolated + `--preserve-symlinks` on every Next command | Fragile; must be repeated in every script, CI job, and IDE config |

## Revisit trigger

Revisit if pnpm's isolated linker becomes reliable for the pinned Next.js version on all
target platforms (verified by a clean `next build` in CI on Windows), **or** if phantom
dependencies cause a real bug. Until then, hoisted is the deliberate choice.
