# `scripts/` — development scripts

Small, explicit scripts for the two things developers do repeatedly: **setting the project
up** and **checking it before committing**. They are deliberately thin wrappers over
documented commands, not a build system.

## Scripts

| Script | Purpose |
|---|---|
| [`bootstrap.ps1`](bootstrap.ps1) / [`bootstrap.sh`](bootstrap.sh) | Prepare a fresh checkout: start the database, create the backend venv, install dependencies, create `.env`, run migrations, install frontend packages |
| [`check.ps1`](check.ps1) / [`check.sh`](check.sh) | Run every quality gate (backend lint/format/types/tests + frontend types/lint) and exit non-zero if any fails |

```powershell
# Windows / PowerShell
pwsh -File scripts/bootstrap.ps1
pwsh -File scripts/check.ps1
pwsh -File scripts/check.ps1 -BackendOnly
```

```bash
# macOS / Linux
./scripts/bootstrap.sh          # or: bash scripts/bootstrap.sh
./scripts/check.sh
```

Both bootstrap scripts are **idempotent**: re-running them will not overwrite an existing
virtualenv or `backend/.env`.

## What the gates are

| Gate | Command | Catches |
|---|---|---|
| Backend lint | `ruff check .` | unused imports, bugs, style |
| Backend format | `ruff format --check .` | formatting drift |
| Backend types | `mypy app` | type errors in application code |
| Backend tests | `pytest` | regressions |
| Frontend types | `pnpm typecheck` (`tsc --noEmit`) | API contract drift, type errors |
| Frontend lint | `pnpm lint` (`eslint .`) | React/Next rule violations |

`pnpm build` is intentionally **not** in `check.ps1`/`check.sh` — it is slow, so it belongs
in CI and in release preparation rather than the inner loop.

### About the database tests

`pytest` runs the API and config tests anywhere. The `tests/database/` suite needs a real
PostgreSQL + pgvector server and is provisioned from, in order:
`NARRAX_TEST_DATABASE_URL`, then `pgserver` (installed by the `db-test` extra that
`bootstrap` installs), otherwise it **skips** with an explanatory message. A skip means the
constraint and cascade tests did not run — check the summary line if that matters.

## Equivalent raw commands

The scripts exist for convenience; nothing depends on them. Everything they do is:

```bash
# Database
docker compose up -d

# Backend
cd backend
python -m venv .venv
.venv\Scripts\activate                 # Windows  (source .venv/bin/activate on POSIX)
pip install -e ".[dev]"
cp ../.env.example .env                # first time only
alembic upgrade head
uvicorn app.main:app --reload          # http://localhost:8000

# Frontend (separate terminal)
cd frontend
pnpm install
pnpm dev                               # http://localhost:3000
```

## Conventions for new scripts

1. **One job per script**, named for what it does (`bootstrap`, `check`).
2. **Fail loudly.** Check exit codes; never swallow an error.
3. **Idempotent where possible**, so a half-finished run can be re-run.
4. **No secrets.** Scripts read configuration from `.env` / environment variables only.
5. **Document it here** when adding one.
