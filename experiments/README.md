# `experiments/` — research and evaluation

Home for **exploratory work that is not production code**: model comparisons, parameter
sweeps, prompt iteration, and the human-evaluation harness.

The MVP's success depends on answerable research questions (see
[../docs/success-criteria.md](../docs/success-criteria.md)). That work belongs here so it
can be rigorous and reproducible without leaking into the shipped pipeline.

## What goes here

| Kind | Examples |
|---|---|
| Notebooks | Embedding model comparison, clustering parameter sweeps, prompt iteration |
| Sweep scripts | `run_clustering_sweep.py`, `compare_embeddings.py` |
| Evaluation harness | Sampling for SC-1/SC-2 rating, agreement computation |
| Findings notes | `findings/embedding-comparison.md` — what was tried and what was learned |

## Conventions

1. **Notebooks are tracked; outputs are not.** `.ipynb_checkpoints/` and
   `experiments/outputs/` are gitignored.
2. **Every experiment records its inputs.** Model name + version, dataset scope, parameters,
   and the date. An experiment whose inputs are unknown is not evidence.
3. **Conclusions become ADRs or requirements**, not folklore. If an experiment changes a
   decision, write it down in [`../docs/adr/`](../docs/adr/) or update the PRD.
4. **Nothing here is imported by `backend/app/`.** Promotion to production means moving
   code into `backend/app/intelligence/` with tests — not importing from `experiments/`.
5. **Experiments never write to Layer 1.** They read source truth or exported copies
   (`../data/exports/`); the database's source tables are written only by ingestion
   (docs/architecture.md §7.1).

## Suggested layout

```text
experiments/
├── README.md
├── notebooks/            # exploratory Jupyter notebooks
├── findings/             # written conclusions (markdown)
└── outputs/              # (gitignored) generated figures/tables
```

## First experiments to run

| Question | Phase | Feeds |
|---|---|---|
| Which embedding model best separates opinion groups on our corpus? | 2 | SC-3, ADR-0006 |
| Which clustering parameters give stable, distinct groups? | 2 | SC-3, ADR-0007 |
| How accurate is the stance classifier on a labeled sample? | 3 | FR-7.3 |
| Which prompt yields narratives that raters judge coherent and grounded? | 4 | SC-1, SC-2 |
| What snapshot cadence makes emerging narratives detectable? | 6 | SC-5 |
