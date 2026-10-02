# NarraX Backend

Python + FastAPI service. See the [root README](../README.md) for the full quickstart.

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

- Docs: http://localhost:8000/docs
- Health: `GET /api/v1/health/live` and `GET /api/v1/health/ready`

## Checks

```bash
ruff check .                      # lint
ruff format --check .             # format
mypy app                          # type check
pytest                            # tests
```

## Migrations

```bash
alembic revision --autogenerate -m "description"   # create migration
alembic upgrade head                              # apply
alembic downgrade -1                              # roll back one
```

Migrations are stored in `alembic/versions/` and are the single source of truth for
schema changes.
