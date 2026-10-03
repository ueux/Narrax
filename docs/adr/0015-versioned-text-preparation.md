# ADR-0015: Versioned text preparation as a Layer 2 record

- **Status:** Accepted
- **Date:** 2026-10-03
- **Related:** [ingestion.md §5, §8](../ingestion.md) · [data-flow.md §3](../data-flow.md) · [database.md §4](../database.md) · [ADR-0009](0009-epistemic-layer-separation.md)

## Context

Between collecting source text and analysing it, there is a decision that has to be made about every
item: **is this usable, and if not, why not?** Formatting has to be stripped, URLs and markup
removed, language checked, padding and duplicates discarded.

That decision needs somewhere to live, and there were three plausible places:

1. **Nothing is stored; each stage re-derives it.** Embedding, sentiment and stance each clean the
   text themselves. Simple, but the same cleaning runs three times, three implementations drift
   apart, and nothing can explain why the corpus is the size it is.
2. **The result is stored per analysis run**, alongside sentiment and stance. Convenient, but wrong:
   cleaning is a deterministic function of the *text* plus a rule set. It has nothing to do with a
   run. Storing it per run duplicates identical rows across runs and allows two runs to disagree
   about the same text.
3. **A separate, versioned record keyed by `(discussion, cleaning-version)`.** Cleaning is computed
   once per text per rule set and reused by everything downstream.

Two requirements push hard towards the third. `product-requirements.md` FR-2.6 and the diagnostic
reporting in `success-criteria.md` require that **every exclusion is explainable** — corpus size must
never shrink silently. And engineering principle 11 requires ML/AI outputs to be versioned.

There is also an epistemic question. Cleaned text is *derived*, not source truth. Putting it on
`discussions` would blur Layer 1 and Layer 2, which ADR-0009 exists to prevent.

## Decision

Add a `text_preparation` table (Layer 2) with one row per `(discussion_id, pipeline_version)`:

- `cleaned_text` and `content_hash`;
- `language`, `language_confidence`, `script`;
- `character_count`, `word_count`, `url_count`, `formatting_artifact_count`;
- `is_usable`, `exclusion_reason`, `exclusion_detail`.

`pipeline_version` is a 12-character fingerprint of the cleaning rules, so changing a threshold
writes new rows rather than silently redefining what earlier rows meant.

Three supporting decisions follow from it:

- **`discussion_analysis.language` is dropped.** Language is a property of the text, not of a run.
  Keeping it in both places would let two runs disagree about the same text.
- **The exclusion vocabulary is a controlled vocabulary** (`text` + `CHECK`), generated from the same
  `StrEnum` the cleaning code uses, so the database and the code cannot drift.
- **`content_hash` is `NOT NULL DEFAULT ''`** rather than nullable, so duplicate detection filters on
  one unambiguous predicate (`content_hash <> ''`).

## Consequences

**Good**

- Cleaning runs once per text per rule set, and all downstream stages read one canonical form.
- Corpus size is always explainable: "26 prepared, 12 usable, 14 excluded" plus a reason breakdown.
- Changing a cleaning threshold is a new `pipeline_version`; old records keep their meaning and both
  versions can coexist for comparison.
- Source truth stays untouched. `discussions.body` is exactly what the platform served, and the
  cleaned form is visibly a separate, derived record.
- The dataset report has a single place to read language, length and quality from.

**Costs**

- One more table and one more upsert per item during collection.
- The language filter and duplicate detection are computed at ingestion time, so re-cleaning with
  different rules requires re-running preparation rather than just re-reading source text. This is
  accepted: preparation is cheap and deterministic, and re-running it is exactly what the version
  column is for.
- `find_duplicate_indices` is corpus-level, so the whole batch must be held in memory before
  duplicates can be judged. Acceptable at MVP scale (hundreds to thousands of items per run).

## Alternatives considered

- **Cleaning inside each downstream stage.** Rejected: duplicated implementations, no explanation for
  corpus size, and inevitable drift between stages.
- **Storing cleaned text on `discussions`.** Rejected: it would make a derived value look like source
  truth and would have to be overwritten whenever rules change, destroying the audit trail.
- **Storing preparation per analysis run.** Rejected: it couples a text property to run identity and
  duplicates identical rows across runs.
- **A native enum for `exclusion_reason`.** Rejected for consistency with every other vocabulary in
  the schema: `text` + `CHECK` is easier to extend and does not require a type migration.

## Revisit trigger

Revisit this decision if either becomes true:

- preparation becomes expensive enough that recomputing it for a new `pipeline_version` is a
  bottleneck (then a cache or incremental re-preparation scheme is warranted);
- the corpus grows to the point where holding a whole run's items in memory for duplicate detection
  is impractical (then duplicate detection needs a streaming or database-side rule).
