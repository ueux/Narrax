# NarraX — Real-Time Narrative Intelligence Engine

NarraX analyzes public online discussions and discovers **what people are actually
believing and saying about a topic, and how those narratives are changing.**

It goes beyond sentiment analysis, keyword counting, and topic modeling. NarraX
builds a layered understanding from raw discussion to semantic clusters, stance,
sentiment, and finally evidence-grounded narratives and their evolution over time.

> Among the analyzed public Reddit discussions... *(never "everyone believes...")*

## Status

| Phase | Scope | Status |
|-------|-------|--------|
| 0 | Repository scaffold (repo layout, DB, API shell, docs) | ✅ current |
| 1 | Reddit ingestion + storage (PostgreSQL + pgvector) | ⬜ planned |
| 2 | Embeddings + semantic clustering (HDBSCAN) | ⬜ planned |
| 3 | Sentiment + stance classification | ⬜ planned |
| 4 | Narrative extraction (provider-independent LLM) | ⬜ planned |
| 5 | Narrative evidence + relations | ⬜ planned |
| 6 | Temporal evolution / emerging narratives | ⬜ planned |
| 7 | Intelligence dashboard (frontend) | ⬜ planned |
| 8 | Evaluation / human-judgment harness | ⬜ planned |

## Repository layout

```text
Narrax/
├── backend/          # Python + FastAPI service, migrations, tests
├── frontend/         # Next.js + TypeScript app shell
├── docs/             # Architecture and principles
├── docker-compose.yml
└── .env.example
```

## Quickstart

```bash
# 1. Start PostgreSQL + pgvector
docker compose up -d

# 2. Backend
cd backend
python -m venv .venv
.venv\Scripts\activate         # Windows (or `source .venv/bin/activate` on macOS/Linux)
pip install -e ".[dev]"
cp ../.env.example .env        # then edit as needed
alembic upgrade head
uvicorn app.main:app --reload  # http://localhost:8000

# 3. Frontend (separate terminal)
cd frontend
pnpm install
pnpm dev                       # http://localhost:3000
```

Health endpoints: `GET /api/v1/health/live` and `GET /api/v1/health/ready`.
Interactive API docs: http://localhost:8000/docs

## Documentation

- [Architecture](docs/architecture.md)
- [Epistemic layers](docs/epistemic-layers.md)
- [Data safety](docs/data-safety.md)

## Engineering principles

1. Inspect the repository before changing it.
2. Reuse existing code when correct; no duplicate abstractions.
3. Prefer simple architecture until complexity is justified.
4. Keep modules independently testable; strong typing where practical.
5. Validate inputs, handle failures explicitly, never swallow errors.
6. Version ML models and pipeline versions.
7. Keep raw/source truth separate from ML outputs.
8. Keep AI interpretations separate from observations.
9. Ground narratives in source evidence.
10. Tests with important functionality; migrations for schema changes.
11. Secrets in environment variables; documentation synchronized with code.
