# Ingestion, normalization & text preparation

How public discussion data gets from a source platform into NarraX, in a shape the intelligence
pipeline can trust. This is **Layer 1 (source truth)** plus the derived **text-preparation record**;
it is not analysis (see [data-flow.md](data-flow.md) §3, stages S0–S2).

Scope for the MVP: Reddit only, English only, batch/offline (ADR
[0004](adr/0004-batch-offline-processing.md), [0008](adr/0008-reddit-only-ingestion.md)).

---

## 1. Principles

1. **Platform shapes stop at one boundary.** Everything above `app/ingestion/reddit/` works with
   `NormalizedDiscussion`. No caller sees `selftext`, `created_utc`, a relative permalink, or the
   string `[deleted]`.
2. **Source text is immutable.** `discussions.title` and `discussions.body` hold exactly what the
   platform served, forever. Cleaning produces a *separate* record; it never rewrites the source.
3. **Nothing is dropped silently.** Every item that does not enter the analysable corpus is
   recorded with a reason from a closed vocabulary.
4. **Cleaning is deterministic and versioned.** The same text and the same rules always produce the
   same result, and the rules' fingerprint is stored with every result.
5. **Collection is idempotent.** Re-running a window never duplicates and never rewrites authored
   content.
6. **Authors are pseudonymous handles.** No enrichment, no cross-platform identity, no profiling
   (see [data-safety.md](data-safety.md)).

---

## 2. Layout

```
app/ingestion/
├── base.py         SourceAdapter contract, SourceQuery, CollectionStats, error hierarchy
├── normalized.py   the normalized model — the contract with everything above
├── language.py     deterministic, dependency-free language detection
├── cleaning.py     the cleaning pipeline and the exclusion vocabulary
└── reddit/
    ├── client.py     HTTP: OAuth, pacing, retries, pagination
    ├── schemas.py    Reddit payload shapes (the only place Reddit's field names appear)
    ├── normalize.py  Reddit → NormalizedDiscussion
    ├── parsing.py    listing-tree traversal, shared by both adapters
    ├── adapter.py    SourceAdapter over the live API
    └── recorded.py   the same contract, replayed from recorded payloads
```

`app/ingestion/__init__.py` deliberately does **not** re-export the platform adapters: importing
the package must not require an HTTP client, and a caller that wants Reddit should say so.

---

## 3. The adapter contract

A platform integration implements `SourceAdapter` and nothing else:

```python
class SourceAdapter(Protocol):
    stats: CollectionStats
    @property
    def key(self) -> str: ...
    def search_discussions(self, query: SourceQuery) -> Iterator[NormalizedDiscussion]: ...
    def fetch_comments(self, discussion, *, limit: int) -> Iterator[NormalizedDiscussion]: ...
```

Requirements on implementations:

- **Lazy generators.** A caller that stops early must not cause further requests.
- **Normalized output only.**
- **Accurate `stats`.** What was seen, what was skipped, and roughly why.

`SourceQuery` is platform-neutral:

| Field | Default | Meaning |
|---|---|---|
| `terms` | `()` | Search terms, joined with spaces for the platform |
| `communities` | `()` | Communities to scope to |
| `since` / `until` | `None` | Inclusive time window on the *source* timestamp |
| `limit` | `100` | Total item budget for the query |
| `sort` | `relevance` | One of `relevance`, `new`, `top`, `comments` |
| `time_filter` | `year` | One of `hour`, `day`, `week`, `month`, `year`, `all` |
| `include_comments` | `True` | Whether to expand threads |
| `comment_limit` | `100` | Comments per post |

A query with neither terms nor communities is rejected: an unbounded collection is never intended.

Errors form one hierarchy so callers can distinguish *retry later* from *give up*:
`SourceConfigurationError`, `SourceAuthError`, `SourceRateLimitedError`, `SourceUnavailableError`,
`SourceResponseError` — all subclasses of `IngestionError`.

`CollectionStats` records `posts_seen`, `posts_yielded`, `comments_seen`, `comments_yielded`,
`skipped_malformed`, `skipped_out_of_window`, `skipped_out_of_scope`, `skipped_duplicate_id`. The
collection service copies this onto the run, so "we collected 800 items" never hides "we examined
4,000 and 3,200 fell outside the window".

---

## 4. The normalized model (PROMPT 14)

`NormalizedDiscussion` is the single representation of one post or comment. It is frozen, forbids
unknown fields, and validates on construction — a malformed payload fails at the boundary rather
than surfacing as `None` deep in the pipeline.

| Field | Type | Notes |
|---|---|---|
| `source_key` | `str` | Platform key, e.g. `reddit`. Matches `sources.key` |
| `external_id` | `str` | Platform identifier, e.g. `t3_a1b2c3`. Unique per source |
| `kind` | `post` \| `comment` | |
| `parent_external_id` | `str \| None` | Must be `None` for a post |
| `community_external_id` | `str` | Lowercased, so one community cannot split into two rows |
| `community_name` | `str` | Display form, preserved for humans |
| `author_external_id` | `str \| None` | `None` when the account is gone |
| `title` | `str \| None` | Required and non-blank for a post; `None` for a comment |
| `body` | `str` | Exactly what the platform served, including `[deleted]` |
| `url` | `str \| None` | The discussion's own URL, never an outbound link |
| `source_created_at` | `datetime` | Timezone-aware UTC; naive values are rejected |
| `collected_at` | `datetime` | When NarraX retrieved it |
| `content_state` | enum | `present` \| `deleted` \| `removed` \| `unavailable` |
| `engagement` | `NormalizedEngagement` | `score`, `comment_count`, `upvote_ratio` |
| `metadata` | `dict` | Curated, verbatim platform context |

### What the Reddit normalizer resolves

- **Identity.** Reddit's `name` (`t3_…`/`t1_…`) is used as `external_id`, so a post and a comment can
  never collide and a comment's `parent_id` matches its parent's `external_id` directly. If `name`
  is absent, the documented `t3_`/`t1_` prefix convention is used instead.
- **Absent content.** Reddit signals removed or deleted content in several ways: a sentinel string
  (`[deleted]`, `[removed]`), an empty body, or `removed_by_category`. All of them become an
  explicit `ContentState`. A sentinel body is conclusive, because Reddit replaces the text when
  content is gone; `removed_by_category` is consulted only when no text is available, since it can
  be set while the text is still served.
- **Deleted accounts.** `author == "[deleted]"` becomes `None`, so the pseudonymous handle space
  contains no pseudo-handles that would look like real authors.
- **Time.** `created_utc` (epoch seconds) becomes timezone-aware UTC.
- **URLs.** A relative `permalink` becomes absolute, and a link post's *outbound* URL is kept in
  `metadata["outbound_url"]` — never confused with `url`, which always points at the discussion.
- **Metadata.** A curated set of flags and flair is preserved verbatim: `link_flair_text`,
  `distinguished`, `removed_by_category`, `is_self`, `over_18`, `spoiler`, `locked`, `stickied`,
  `num_crossposts`, and for comments `is_submitter`, `stickied`, `score_hidden`, `controversiality`,
  `link_id`.

### `analysis_input()`

Cleaning needs both a text and a content state, and neither is meaningful alone:

- A post's **title survives moderation even when its body does not**, so a post with a removed body
  is still analysable from its headline — the author's own words. Treating it as removed would
  discard a real contribution.
- A comment has no such second field: once its body is gone, the item is gone.

---

## 5. Text cleaning (PROMPT 15)

`clean_text(text, content_state=..., rules=..., detector=...)` returns a `CleaningResult`:
`is_usable`, `reason`, `cleaned_text`, `content_hash`, `language`, `language_confidence`, `script`,
`character_count`, `word_count`, `url_count`, `formatting_artifact_count`, `detail`.

### Order of checks

Reasons are evaluated in a fixed order so every input has exactly one reason, chosen by the most
specific applicable rule:

```
structural → empty → noise → repetition → language → link-dominated → length → low-information
```

The order is not arbitrary:

- **language before length** — scripts that do not separate words with spaces (Chinese, Japanese)
  tokenise to a single "word" and would otherwise be reported as merely short;
- **repetition before language** — the language heuristic counts English function words, so repeated
  slang ("lol lol lol …") would otherwise read as foreign text;
- **link-dominated before length** — a bare link is a link problem, not a brevity problem.

### What is removed

HTML entities are decoded; the text is NFKC-normalised; control and zero-width characters are
removed. Then, in order: markdown images (dropped entirely), markdown links (reduced to their
label — the part a human wrote), bare URLs, `u/` and `r/` mentions, a small allowlist of HTML tags,
backslash escapes, code fences, horizontal rules, headings, blockquote markers, and emphasis
characters (`*`, `~`, backtick). Finally whitespace is collapsed while paragraph breaks survive.

Two deliberate choices: **underscores are preserved** so `snake_case` identifiers survive intact,
and **URLs are removed rather than replaced** by a placeholder token, which would pollute vocabulary
for downstream stages.

### Exclusion vocabulary (closed)

| Reason | Meaning |
|---|---|
| `missing_source_text` | The platform served no body field at all |
| `deleted_content` | The author deleted it |
| `removed_content` | A moderator or the platform removed it |
| `empty_content` | Blank, or reduced to nothing once formatting was stripped |
| `too_short` | Below the minimum length |
| `excessive_noise` | Mostly symbols, emoji, or a repeated character rather than language |
| `repetitive_content` | The same token, line, or phrase repeated rather than composed |
| `link_dominated` | Mostly a URL |
| `duplicate_content` | The same text already exists elsewhere in the corpus |
| `non_english` | Confidently not English, which is outside the MVP's scope |
| `low_information` | Grammatical but contentless — only function words, no distinct terms |

The vocabulary lives in `app/database/models/enums.py` with every other controlled vocabulary,
because the database CHECK constraint and the cleaning stage must share one definition.

### Rules and versioning

`CleaningRules` is a frozen dataclass:

| Rule | Default |
|---|---|
| `min_characters` | 16 |
| `min_words` | 3 |
| `min_letter_share` | 0.5 |
| `max_char_run_share` | 0.5 |
| `max_token_dominance` | 0.6 |
| `min_tokens_for_repetition` | 6 |
| `max_url_share` | 0.5 |
| `allowed_languages` | `("en",)` |
| `min_non_english_confidence` | 0.6 |

`CleaningRules.version()` is a 12-character SHA-256 fingerprint of those values. It is stored on
every preparation row as `pipeline_version`, so changing a threshold writes new rows instead of
silently redefining what earlier rows meant.

### Duplicate detection

`find_duplicate_indices(candidates, seen_hashes=...)` applies one deterministic rule: candidates are
considered in `(source_created_at, external_id, index)` order and **the first occurrence of a
content hash wins**. Anything whose hash was already claimed — earlier in the batch, or already
recorded for this cleaning version — is a duplicate.

Duplicate detection is a corpus-level question, so it cannot be answered item by item; the service
cleans the whole batch first, then judges. Hashes belonging to *this run's* discussions are excluded
from the "already seen" set, so re-collecting an item never makes it a duplicate of itself.

> **Known limitation.** The keeper is the first occurrence *considered*, not necessarily the earliest
> ever authored: re-ingesting an older duplicate later flags the older item rather than re-seating
> the keeper. This is acceptable for the MVP (the corpus is collected in window order) and is the
> revisit trigger for adding a re-evaluation pass.

### Language detection

`HeuristicLanguageDetector` is dependency-free and fully deterministic, which matters because it
runs on every item. It reports **asymmetric confidences**: `english_confidence` is high only when
English function words are genuinely frequent, while `non_english_confidence` is high when either a
non-Latin script dominates or almost no English function words appear.

It names only English positively; other languages come back as `und` with a confidence, so the
language filter is governed by `min_non_english_confidence` rather than by a language list.
`allowed_languages` states the English-only restriction explicitly and is ready for a detector that
can name other languages.

The filter is deliberately conservative — an item is excluded only when the non-English confidence
clears the threshold — because discarding genuine English is worse than retaining some foreign text.

---

## 6. Collecting from Reddit

`RedditClient` is the only place that performs HTTP.

**Authentication.** Application-only OAuth (`client_credentials`). The bearer token is cached and
transparently refreshed **once** on a 401; a second 401 is a failure, not a loop. Credentials come
from `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, and `REDDIT_USER_AGENT` via
`app.config.settings`; a missing or partial set fails fast with `SourceConfigurationError`. The
user agent is sent on every request because Reddit blocks generic ones.

**Pacing.** Two independent mechanisms, because they catch different problems: a minimum interval
between requests prevents self-inflicted bursts, and honouring `x-ratelimit-remaining` /
`x-ratelimit-reset` stops before the quota is exhausted rather than discovering it through a 429.
The sleeper and clock are injectable, which is what makes this testable without a single real second
passing.

**Retries.** Bounded, with exponential backoff, honouring `Retry-After`. Rate limits and 5xx are
retried; 4xx, authentication failures and malformed responses are not, because retrying cannot fix
them.

**Pagination.** `iter_listing` follows the `after` cursor lazily, capped at Reddit's page maximum of
100, so a caller that stops early stops making requests. `more` placeholders are skipped; a listing
with no `children` is an end, while a payload that is not a listing at all is an error — treating it
as empty would silently truncate a run.

**Query mapping.**

| Query | Reddit request |
|---|---|
| terms + communities | `/r/{community}/search?q=…&restrict_sr=1&type=link` (one per community) |
| terms only | `/search?q=…&type=link` |
| communities only | `/r/{community}/{sort}`, with `relevance` degraded to `new` |

`limit` is a budget for the whole query, split evenly across requests so that a multi-community
query is not dominated by whichever community happens to come first.

**Thread assembly.** `/comments/{id}` returns `[post listing, comment listing]` with replies nested
inside each comment. The tree is walked **breadth-first**, which is a deliberate choice rather than
an implementation detail: it guarantees a comment is emitted only after its parent, so the
persistence layer can rely on the database's self-referencing foreign key instead of sorting
comments itself. Reddit writes `""` (an empty string) for "no replies"; that is a normal state, not
an error.

---

## 7. Recorded payloads

`RecordedRedditAdapter` serves Reddit payloads from a directory, so the pipeline can be exercised in
CI, offline, or while iterating — without credentials. It replays through the **same** normalization
and traversal code as live collection, so a fixture can never pass against a divergent
implementation.

```
<directory>/
├── search_response.json          # one listing, or a list of listings
└── comments_t3_<post_id>.json    # the [post, comments] payload for one post
```

It honours `communities`, the time window, and `limit`, exactly as the live adapter does. Two things
it deliberately does **not** do: re-apply a text search (the recorded payloads are already the
result of one), and treat a missing comment file as an error (the recorded corpus is a subset by
design).

The committed corpus lives in `backend/tests/fixtures/reddit/`. It is small but deliberately
adversarial: deleted and removed posts and comments, an empty body, a body field missing entirely,
a URL-only comment, an emoji wall, repeated slang, contentless filler, German and Russian text,
three levels of nesting, a duplicate posted twice, duplicates across two posts, and a comment whose
parent was never collected. Between them they exercise **every** exclusion reason.

---

## 8. Persistence and idempotency

`app/services/collection.py` owns a whole collection run. It flushes but never commits — the caller
owns the transaction — so a caller can commit only once every stage has succeeded, or inspect
partial progress after a failure.

**Idempotency.** Discussions are upserted on the natural key `(source_id, external_id)`. The
authored columns — `title`, `body`, `source_created_at`, `author_id`, `kind`,
`parent_discussion_id` — are deliberately absent from the update set, so re-collecting an item never
rewrites what a person wrote. Only NarraX-owned retrieval metadata is refreshed: `collected_at`,
`source_score`, `raw_metadata`. Insert-versus-update is detected with PostgreSQL's own
`RETURNING (xmax = 0)`, avoiding a second round trip.

**Thread structure is source truth.** The adapter yields parents first, so any parent inside the run
is already stored. A parent that is *not* in this run was never collected, and the row keeps a NULL
parent rather than being reattached to the post — inventing a parent would misstate the thread. Such
rows surface in the dataset report as orphaned comments.

**Accounting.** Each run writes an `analysis_runs` row (status, window, `config` snapshot including
the adapter key, the query, and the cleaning rules fingerprint) and one `run_stages` row per stage:

- `ingest` — items in (seen), items out (stored), items dropped (skipped), with the full
  `CollectionStats` in `metrics`;
- `normalize` — items in (prepared), items out (usable), items dropped (excluded), with the
  `pipeline_version`, the duplicate count, and the exclusion-reason breakdown in `metrics`.

An interrupted run is marked `partial` and its already-collected discussions are kept: they are
valid Layer 1 data even though the run did not finish.

**Text preparation.** Cleaning writes a `text_preparation` row per `(discussion, pipeline_version)`
holding the cleaned text, the usable/excluded decision with its reason, the content hash, and the
measured properties. Source text is untouched. See [database.md](database.md) for the column
reference and ADR [0015](adr/0015-versioned-text-preparation.md) for why it is a separate record.

---

## 9. Dataset inspection (PROMPT 16)

`app/services/inspection.py` produces a read-only `DatasetReport`: volume (discussions, posts,
comments, sources, communities, authors), time range, language distribution, content-length
distribution (min/median/p90/max/means), missing values, quality (prepared / usable / excluded,
duplicate count and share, comments per post, posts with no comments), exclusions by reason, and top
communities. `render_markdown` and `DatasetReport.to_dict()` present it for humans and machines.

It computes **no** embeddings, clusters, sentiment, stance or narratives. Inspection answers *"is
the data sound?"*, not *"what does it mean?"*.

Because a discussion can have a preparation row per cleaning version, the report selects the
**newest row per discussion** with a window function — reporting over all rows would double-count
every re-prepared item.

A generated example is committed at
[reports/sample-dataset-report.md](reports/sample-dataset-report.md).

---

## 10. Commands

Live collection needs credentials in `backend/.env` (see `.env.example`):

```bash
alembic upgrade head
python -m app.cli.ingest_recorded --help      # replay recorded payloads (no credentials needed)
python -m app.cli.inspect_dataset --help      # report on the current dataset
```

Typical offline workflow, which is exactly how the committed sample report was produced:

```bash
cd backend
alembic upgrade head
python -m app.cli.ingest_recorded \
  --input-dir tests/fixtures/reddit \
  --topic "AI regulation" \
  --communities technology programming \
  --limit 50
python -m app.cli.inspect_dataset --top-communities 10 \
  --output ../docs/reports/sample-dataset-report.md
```

Running the ingest twice is safe and expected: the second run reports `0 new, 26 refreshed` and the
resulting dataset is byte-for-byte the same.

---

## 11. Known limitations

Recorded here rather than discovered later:

1. **No live collection has been performed.** It requires OAuth application credentials, which the
   project does not hold. The client is tested against mocked HTTP responses and the pipeline is
   tested against recorded payloads; the sample report is explicitly *not* live data.
2. **The language detector names only English.** Other languages are reported as `und` with a
   confidence. A post with an English title and a foreign body is classified from the combined text
   and may therefore read as English.
3. **Duplicate keepers are chosen by first-considered, not earliest-authored** (see §5).
4. **`raw_metadata` is curated, not exhaustive.** Reddit returns far more fields than NarraX needs;
   a documented allowlist is preserved verbatim and the rest is dropped rather than stored
   indiscriminately.
5. **Removal state is not a column on `discussions`.** It is recoverable from the body sentinel,
   `raw_metadata.removed_by_category`, and `text_preparation.exclusion_reason`; a dedicated column
   would be redundant today.
6. **Comments are collected to a fixed depth budget, not exhaustively.** `comment_limit` bounds each
   post's thread, and Reddit's own `more` placeholders are not expanded.

---

## 12. How this is tested

| Area | Approach |
|---|---|
| HTTP client | `httpx.MockTransport` with a scripted fake; pacing asserted through the limiter's injected sleeper, so no test waits |
| Query mapping | Direct assertions on generated request paths and parameters |
| Normalization | Table-driven tests over every Reddit signal, including a `content_state` truth table |
| Cleaning | Realistic Reddit-shaped examples per exclusion reason, plus determinism and versioning |
| Duplicate detection | Determinism under input reordering, ties, and pre-seen hashes |
| Adapters | Recorded fixtures replaying through the production code path |
| Persistence | Real PostgreSQL: upsert idempotency, foreign-key threading, CHECK constraints, run accounting |
| Inspection | Real PostgreSQL: counts, distributions, and read-only behaviour |

`backend/tests/fixtures/reddit/` is committed, so the offline path is reproducible by anyone.

---

## 13. What this layer must never do

- Embed, cluster, score sentiment or stance, or extract narratives — that is `app.intelligence`.
- Enrich, link, or profile authors, or infer sensitive personal attributes.
- Let a platform's field names or sentinel strings escape `app/ingestion/reddit/`.
- Present an inference as source truth: `content_state`, cleaning decisions and language guesses are
  derived observations, and are stored as such.
