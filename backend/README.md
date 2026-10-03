# NarraX Backend

Python + FastAPI service. See the [root README](../README.md) for the full quickstart and
[docs/architecture.md](../docs/architecture.md) for the design.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows (or `source .venv/bin/activate`)
pip install -e ".[dev]"
cp ../.env.example .env           # then edit values
alembic upgrade head
```

## Run

```bash
uvicorn app.main:app --reload
```

- Docs: <http://localhost:8000/docs>
- Health: `GET /api/v1/health/live` (liveness) and `GET /api/v1/health/ready` (DB probe)

## Module layout

Each package is a boundary with one reason to change. The allowed dependency direction is
enforced by review — see [architecture.md §7](../docs/architecture.md#7-module-boundaries).

```text
app/
├── api/           # HTTP edge: routes, shared dependencies, router aggregation
├── config/        # settings + logging — a leaf, imported by everything
├── database/      # engine, session, ORM models
├── ingestion/     # Layer 1: acquire + normalise source truth          (Phase 1)
├── intelligence/  # Layers 2–4: embeddings → narratives → evolution    (Phases 2–6)
├── schemas/       # Pydantic DTOs for the HTTP boundary
├── services/      # orchestration / use-cases; the only whole-workflow layer
└── main.py        # composition: config → logging → routers
```

Rules of thumb:

- `api/` holds no analysis logic and opens no sessions of its own.
- `services/` is the only package that composes ingestion + intelligence + database.
- Nothing imports `api/`; `config/` imports nothing from `app.*`.
- Only `ingestion/` writes Layer 1 (source truth).

## Checks

```bash
ruff check .                      # lint
ruff format --check .             # format
mypy app                          # type check
pytest                            # tests (no live database required)
```

Or run every gate at once from the repository root: `pwsh -File scripts/check.ps1`.

## Tests

`tests/` mirrors `app/`. Shared fixtures live in `tests/conftest.py`; the readiness test
overrides the database dependency with an in-memory fake, so the suite needs no services.

```bash
pytest                            # all tests
pytest tests/api                  # one boundary
```

## Migrations

```bash
alembic revision --autogenerate -m "description"   # create migration
alembic upgrade head                              # apply
alembic downgrade -1                              # roll back one
```

Migrations are stored in `alembic/versions/` and are the single source of truth for schema
changes ([ADR-0012](../docs/adr/0012-alembic-migrations.md)). The database URL comes from
application settings, never from `alembic.ini`.

## Environment variables

Every variable is documented in [`../.env.example`](../.env.example). Secrets live only in
`.env` (gitignored) or the process environment.
