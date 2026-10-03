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
├── cli/           # terminal edge: argument parsing + a session, then a service call
├── config/        # settings + logging — a leaf, imported by everything
├── database/      # engine, session, ORM models
├── ingestion/     # Layer 1: acquire + normalize + clean source truth    (Phase 1)
├── intelligence/  # Layers 2–4: embeddings → narratives → evolution      (Phases 2–6)
├── schemas/       # Pydantic DTOs for the HTTP boundary
├── services/      # orchestration / use-cases; the only whole-workflow layer
└── main.py        # composition: config → logging → routers
```

Rules of thumb:

- `api/` and `cli/` hold no analysis logic and open no sessions of their own.
- `services/` is the only package that composes ingestion + intelligence + database.
- Nothing imports `api/` or `cli/`; `config/` imports nothing from `app.*`.
- Only `ingestion/` writes Layer 1 (source truth), and platform-specific field names never escape
  `ingestion/<platform>/` — see [docs/ingestion.md](../docs/ingestion.md).

## Checks

```bash
ruff check .                      # lint
ruff format --check .             # format
mypy app                          # type check
pytest                            # tests (no live database required)
```

Or run every gate at once from the repository root: `pwsh -File scripts/check.ps1`.

## Database

The schema (19 tables across four epistemic layers), its review findings, and the rationale for
every index are documented in [docs/database.md](../docs/database.md).

```bash
# A real PostgreSQL + pgvector server, no Docker and no admin rights required:
pip install -e ".[dev,db-test]"
pytest tests/database -v
```

Alternatively set `NARRAX_TEST_DATABASE_URL` to point at any PostgreSQL with the `vector`
extension. If neither is available the database tests skip with an explanatory message.

## Collecting a dataset

Live collection requires Reddit OAuth credentials (`REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`,
`REDDIT_USER_AGENT` in `.env`). Offline, recorded payloads replay through the same pipeline:

```bash
alembic upgrade head
python -m app.cli.ingest_recorded --input-dir tests/fixtures/reddit \
  --topic "AI regulation" --communities technology programming --limit 50
python -m app.cli.inspect_dataset --top-communities 10
```

Collection is idempotent: a second run reports `0 new, 26 refreshed` and rewrites no authored text.
The pipeline, its cleaning rules, and its known limitations are in
[docs/ingestion.md](../docs/ingestion.md).

## Tests

`tests/` mirrors `app/`. Shared fixtures live in `tests/conftest.py` (API tests use an in-memory
fake session, so they need no services); `tests/database/conftest.py` provisions a real
PostgreSQL server for the constraint, cascade, and pgvector tests.

```bash
pytest                            # all tests
pytest tests/api                  # one boundary
pytest tests/database             # real-database tests
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
