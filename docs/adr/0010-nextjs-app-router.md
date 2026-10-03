# ADR-0010: Next.js App Router + strict TypeScript

- **Status:** Accepted
- **Date:** 2026-03-10
- **Related:** [architecture.md §3.3](../architecture.md#33-frontend-structure)

## Context

NarraX's UI must present a layered, read-mostly intelligence product: browse a topic, read
narratives, inspect evidence, compare groups, view trends. Two properties matter more than
anything else:

1. **Epistemic honesty is a rendering requirement.** The UI must visually distinguish source
   text, ML observations, and AI interpretations (FR-15.2). This is easiest when the data
   contract makes the distinction explicit and typed.
2. **The contract with the API will change frequently** during the MVP. Type errors caught at
   build time are cheaper than runtime surprises in a research tool where a wrong number is
   worse than a missing one.

We must choose a React meta-framework and a routing model.

## Decision

Use **Next.js (App Router)** with **TypeScript in `strict` mode**.

- Routes/pages live under `app/` as server components by default.
- Client interactivity is isolated in `components/` + `hooks/` via `"use client"`.
- Shared API/DTO types live in `types/`, and all network access goes through `lib/api-client.ts`.
- `typecheck` (`tsc --noEmit`) is a required gate, alongside lint and build.

## Consequences

### Positive

- **Strict typing catches contract drift** before runtime, which matters when the numbers are
  the product.
- **Server components fetch data on the server**, so no client-side round trip to render a
  page, and read-path data does not have to be exposed as a separate client call.
- **File-system routing matches the domain** (`/topics/[id]/narratives`), which keeps the
  route tree legible without a routing config.
- **Built-in bundling/optimization** with no separate build pipeline to maintain.
- **Colocation** of layout and page makes the "always show corpus scope" rule easy to apply
  at a shared layout level (FR-15.1).

### Negative / costs

- **Framework coupling.** Migrating off Next.js later is non-trivial.
- **Server/client boundary discipline is required.** `"use client"` misuse leaks server-only
  concerns (or secrets) toward the client; the rule is that only `NEXT_PUBLIC_*` is client-safe.
- **App Router is newer than Pages Router**, so some third-party examples are stale.
- **Build-time inlining** of `NEXT_PUBLIC_*` means changing the API base URL requires a
  rebuild in a static-export setting.

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| Pages Router | Older model; server components and layout composition are weaker |
| Vite + React Router (SPA) | Adds a bespoke data-fetching/build story; no server rendering benefit |
| Remix / React Router framework mode | Viable, but less familiar and not more compelling for a read-mostly dashboard |
| Plain JavaScript | Gives up the compile-time contract checking that this product's trust story depends on |
| Astro | Excellent for content sites; this is a data application with client interactivity |

## Revisit trigger

Revisit only on a concrete limitation (e.g. a required rendering/caching capability Next.js
cannot provide). Do not migrate for novelty — the API contract in `types/` is deliberately
framework-agnostic, so the cost of a future move is bounded.
