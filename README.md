# NarraX — Real-Time Narrative Intelligence Engine

NarraX analyzes public online discussions and discovers **what people are actually
believing and saying about a topic, and how those narratives are changing.**

It goes beyond sentiment analysis, keyword counting, and topic modeling. NarraX builds a
layered understanding from raw discussion to semantic clusters, stance, sentiment, and
finally evidence-grounded narratives and their evolution over time.

> Among the analyzed public Reddit discussions… *(never "everyone believes…")*

**Start here:** [Product requirements](docs/product-requirements.md) ·
[Architecture](docs/architecture.md) · [MVP scope](docs/mvp-scope.md) ·
[Success criteria](docs/success-criteria.md)

---

## Status

| Stage | Scope | Status |
|-------|-------|--------|
| 0 | Repository scaffold (layout, DB, API shell) | ✅ done |
| 0.5 | Product requirements, architecture + ADRs, repo structure, engineering foundation | ✅ done |
| 0.6 | Database schema: 18 tables, migrations, indexes, database tests | ✅ done |
| 1 | Reddit ingestion: source adapter, normalization, text cleaning, dataset inspection | ✅ current |
| 2 | Embeddings + semantic clustering (HDBSCAN) | ⬜ planned |
| 3 | Sentiment + stance classification | ⬜ planned |
| 4 | Narrative extraction (provider-independent LLM) | ⬜ planned |
| 5 | Narrative evidence + relations | ⬜ planned |
| 6 | Temporal evolution / emerging narratives | ⬜ planned |
| 7 | Intelligence dashboard (frontend) | ⬜ planned |
| 8 | Evaluation / human-judgment harness | ⬜ planned |

The MVP envelope is fixed and deliberately small — Reddit only, English, batch/offline,
~500–5,000 discussions per topic, one node. See [mvp-scope.md](docs/mvp-scope.md) for what
is explicitly **out** of scope and the exact trigger to revisit each exclusion.

---

## Repository layout

```text
Narrax/
├── backend/                 # Python + FastAPI service
│   ├── app/
│   │   ├── api/             #   HTTP edge: routes, dependencies, router
│   │   ├── cli/             #   terminal edge: commands that call services
│   │   ├── config/          #   settings + logging (leaf package)
│   │   ├── database/        #   engine, session, ORM models
│   │   ├── ingestion/       #   Layer 1 — acquire + normalize + clean  (Phase 1)
│   │   ├── intelligence/    #   Layers 2–4 — embeddings → narratives   (Phases 2–6)
│   │   ├── schemas/         #   API request/response DTOs
│   │   └── services/        #   orchestration / use-cases
│   ├── alembic/             #   schema migrations
│   └── tests/               #   mirrors app/ structure
├── frontend/                # Next.js + TypeScript
│   ├── app/                 #   App Router pages + layouts
│   ├── components/          #   React components
│   ├── hooks/               #   client data-fetching hooks
│   ├── lib/                 #   API client + non-React helpers
│   └── types/               #   shared API contract types
├── docs/                    # product requirements, architecture, ADRs
├── experiments/             # research notebooks + evaluation harness
├── scripts/                 # bootstrap + quality-gate scripts
├── data/                    # local data (contents gitignored)
└── docker-compose.yml       # PostgreSQL + pgvector
```

Module boundaries and their allowed dependency direction are documented in
[architecture.md §7](docs/architecture.md#7-module-boundaries).

---

## Quickstart

Requires **Python 3.11+**, **Node 20+** with **pnpm**, and **Docker**.

```bash
# One-shot setup: database, backend venv + deps, migrations, frontend deps
pwsh -File scripts/bootstrap.ps1      # Windows
./scripts/bootstrap.sh                # macOS / Linux
```

Then run the two dev servers:

```bash
# Terminal 1 — backend
cd backend
.venv\Scripts\activate                # Windows  (source .venv/bin/activate on POSIX)
uvicorn app.main:app --reload         # http://localhost:8000

# Terminal 2 — frontend
cd frontend
pnpm dev                              # http://localhost:3000
```

- API docs: <http://localhost:8000/docs>
- Health: `GET /api/v1/health/live` (liveness) and `GET /api/v1/health/ready` (DB probe)
- Frontend: <http://localhost:3000>

<details>
<summary>Manual setup (what the bootstrap script does)</summary>

```bash
docker compose up -d                  # PostgreSQL + pgvector

cd backend
python -m venv .venv
.venv\Scripts\activate                # or: source .venv/bin/activate
pip install -e ".[dev]"
cp ../.env.example .env               # then edit as needed
alembic upgrade head

cd ../frontend
pnpm install
```
</details>

---

## Quality gates

```bash
pwsh -File scripts/check.ps1          # Windows
./scripts/check.sh                    # macOS / Linux
```

| Gate | Command |
|---|---|
| Backend lint | `ruff check .` |
| Backend format | `ruff format --check .` |
| Backend types | `mypy app` |
| Backend tests | `pytest` |
| Frontend types | `pnpm typecheck` |
| Frontend lint | `pnpm lint` |

`pnpm build` runs the production build (also part of Next's type/lint check) but is excluded
from the fast gate script. See [scripts/README.md](scripts/README.md).

### Database tests

The API and config tests always run. The **database tests need a real PostgreSQL + pgvector**
server, obtained from (in order) `NARRAX_TEST_DATABASE_URL`, or a self-contained embedded server
if the optional extra is installed:

```bash
cd backend
pip install -e ".[dev,db-test]"   # adds pgserver: PostgreSQL + pgvector, no Docker, no admin
pytest tests/database -v
```

With neither available those tests **skip with an explanatory message** rather than failing.

### Collecting a dataset

Live collection needs Reddit OAuth credentials (`REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`,
`REDDIT_USER_AGENT`). Offline, the committed corpus can be replayed through the real pipeline:

```bash
cd backend
alembic upgrade head
python -m app.cli.ingest_recorded --input-dir tests/fixtures/reddit \
  --topic "AI regulation" --communities technology programming --limit 50
python -m app.cli.inspect_dataset --output ../docs/reports/sample-dataset-report.md
```

Collection is idempotent: re-running reports `0 new, 26 refreshed` and changes no authored text.
See [ingestion.md](docs/ingestion.md) for the pipeline and its known limitations.

---

## Documentation

**Product**

- [Product requirements](docs/product-requirements.md) — the source of truth for *what*
- [Glossary](docs/glossary.md) — canonical terminology
- [MVP scope](docs/mvp-scope.md) — what is in, what is out, and when to revisit
- [Success criteria](docs/success-criteria.md) — gates, scored criteria, evaluation method

**Technical**

- [Architecture](docs/architecture.md) — system, components, flows, boundaries, deployment
- [Data flow](docs/data-flow.md) — every stage, its inputs/outputs, idempotency, provenance
- [Database](docs/database.md) — ERD, table reference, review findings, index rationale
- [Ingestion & normalization](docs/ingestion.md) — source adapter, normalized model, cleaning rules, dataset inspection
- [Sample dataset report](docs/reports/sample-dataset-report.md) — what the recorded corpus actually contains
- [ADRs](docs/adr/README.md) — why the architecture is the way it is

**Principles**

- [Epistemic layers](docs/epistemic-layers.md) — source truth vs observations vs interpretations
- [Data safety](docs/data-safety.md) — aggregate-only, pseudonymous, no profiling

---

## Engineering principles

1. Inspect the repository before changing it.
2. Reuse existing code when correct; no duplicate abstractions.
3. Prefer simple architecture until complexity is justified — infrastructure is added only
   against a measured need ([ADR-0013](docs/adr/0013-excluded-infrastructure.md)).
4. Keep modules independently testable; strong typing where practical.
5. Validate inputs, handle failures explicitly, never swallow errors.
6. Version ML models and pipeline versions.
7. Keep raw/source truth separate from ML outputs.
8. Keep AI interpretations separate from observations.
9. Ground narratives in source evidence.
10. Tests with important functionality; migrations for schema changes.
11. Secrets in environment variables; documentation synchronized with code.
