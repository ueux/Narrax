# NarraX Frontend

Next.js 15 + TypeScript app shell. See the [root README](../README.md) for the full
quickstart.

## Setup

```bash
pnpm install
pnpm dev            # http://localhost:3000
```

The API base URL comes from `NEXT_PUBLIC_API_BASE_URL` (default `http://localhost:8000`).
Copy [`.env.example`](.env.example) to `.env.local` to override it.

## Checks

```bash
pnpm typecheck      # tsc --noEmit
pnpm lint           # eslint
pnpm build          # production build (also type-checks + lints)
pnpm format         # prettier --write
```

## Structure

```text
frontend/
├── app/            # App Router: routes, layouts, pages (server components)
├── components/     # React components (presentational + feature)
├── hooks/          # client hooks owning the fetch lifecycle
├── lib/            # non-React code: API client, domain calls, helpers
└── types/          # shared API contract types
```

**Data-flow rule:** `components/` never call `fetch`. They use `hooks/`, which use
`lib/api.ts`, which uses the single typed client in `lib/api-client.ts`. Only that client
knows the base URL and how to normalise errors.

## Notable configuration

pnpm settings live in [`pnpm-workspace.yaml`](pnpm-workspace.yaml) — that is where pnpm 11
reads them (`.npmrc` is ignored by this version):

| Setting | Value | Why |
|---|---|---|
| `nodeLinker` | `hoisted` | Flat `node_modules` avoids the Windows junction-resolution problems that break Next's own dependency resolution. See [ADR-0011](../docs/adr/0011-pnpm-hoisted-node-linker.md). |
| `storeDir` | `.pnpm-store` | Keeps the content-addressable store inside the project (gitignored) so installs are hermetic. |
| `verifyDepsBeforeRun` | `false` | Installing is an explicit step (`scripts/bootstrap.*`), which keeps `typecheck`/`lint`/`build` fast and predictable. |
| `allowBuilds` | `sharp: false`, `unrs-resolver: false` | Declines optional native build scripts for now; flip to `true` when Next image optimization or the full ESLint resolver is needed. |

The pnpm version is pinned via `packageManager` in [`package.json`](package.json).
