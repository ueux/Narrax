# NarraX Frontend

Next.js 15 + TypeScript app shell. See the [root README](../README.md) for the full
quickstart.

## Setup

```bash
pnpm install
pnpm dev            # http://localhost:3000
```

The app expects the backend at `http://localhost:8000` by default. Override it with
`NEXT_PUBLIC_API_BASE_URL` if needed.

## Checks

```bash
pnpm typecheck      # tsc --noEmit
pnpm lint           # eslint
pnpm build          # production build
pnpm format         # prettier --write
```

## Notes

- `.npmrc` sets `node-linker=hoisted` (flat `node_modules`) — the most robust layout
  for Next.js on Windows — and a project-local pnpm store (`store-dir=.pnpm-store`,
  which is gitignored).
- API client lives in `lib/api.ts`; the landing page (`app/page.tsx`) renders a
  `HealthCheck` client component (`components/health-check.tsx`) that probes the
  backend liveness endpoint.
