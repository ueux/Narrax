# NarraX — Success Criteria

**Purpose:** define, in advance, exactly how we will decide whether the NarraX MVP
succeeded — so the judgement is not made after seeing the results.

Related: [product-requirements.md](product-requirements.md) ·
[mvp-scope.md](mvp-scope.md)

---

## 1. The hypothesis under test

> Semantic clustering + stance + sentiment + LLM narrative extraction produce
> **coherent, useful, evidence-grounded narratives that humans judge meaningful**.

Everything below measures that sentence. Infrastructure quality, throughput, and code
elegance are **not** success criteria for the MVP (they are enablers).

**Corollary:** if the pipeline is fast, pretty, and cloud-native but the narratives are
generic or unsupported, the MVP **failed**.

---

## 2. Gates vs scores

| Type | Meaning | Failure consequence |
|---|---|---|
| **Gate** | Binary, non-negotiable, must be 100% | MVP **fails**, regardless of scores |
| **Score** | Threshold on a measured sample | MVP **fails** if below threshold |

### Hard gates

| ID | Gate | Measurement |
|---|---|---|
| **G-1 (Auditability)** | Every published narrative traces to (a) ≥1 source item, (b) the cluster it came from, (c) the pipeline run, and (d) the model + prompt version | Automated check over the DB: 100% of narratives have all four links |
| **G-2 (Evidence grounding)** | No published narrative has zero evidence links | Automated: `count(narratives with 0 evidence) == 0` |
| **G-3 (Epistemic labeling)** | Source truth, ML observations, AI interpretations, and temporal observations are separable in both API responses and UI | API contract test + UI review: no response mixes layers without a label |
| **G-4 (No-prohibited-output)** | No output identifies, profiles, or re-identifies an individual | Manual audit of a sample + code review of data-access paths |
| **G-5 (Reproducibility)** | One full end-to-end run reproduces its structural result from a clean checkout with pinned versions | Executed once and recorded |

A single gate failure is a **stop-and-fix**, not a "known issue".

---

## 3. Scored criteria

All scored criteria are measured on a **held-out evaluation set** of topics, rated by
humans who did **not** build the pipeline.

### SC-1 — Narrative coherence

**Question:** Is each narrative a coherent, specific claim — rather than a vague
restatement of the topic or a generic platitude?

| Rating | Definition |
|---|---|
| **2 — Coherent** | A specific claim a group actually makes; would be recognisable to someone who read the threads |
| **1 — Acceptable** | Understandable but partly generic or over-broad |
| **0 — Incoherent** | Vague, self-contradictory, or merely restates the topic |

**Threshold:** ≥ **70%** of rated narratives score **2**, and ≤ **10%** score **0**.
**Sample:** ≥ 50 narratives across ≥ 3 topics. **Raters:** ≥ 2 independent; report agreement.

### SC-2 — Evidence grounding

**Question:** Does the cited evidence actually support the narrative it is attached to?

| Rating | Definition |
|---|---|
| **2 — Supported** | Most cited items clearly express the claim |
| **1 — Partly** | Some cited items support it; others are tangential |
| **0 — Unsupported** | The cited items do not express the claim |

**Threshold:** ≥ **80%** of narratives score **2**; ≤ **5%** score **0**.
Note: this is *stricter* than gate G-2 (which only checks that evidence exists).

### SC-3 — Opinion-group distinctness

**Question:** Are discovered groups meaningfully different, or arbitrary slices of one
undifferentiated conversation?

| Rating | Definition |
|---|---|
| **2 — Distinct** | Two groups express recognisably different positions/framings |
| **1 — Weakly distinct** | Different emphasis, same broad position |
| **0 — Not distinct** | Effectively the same group |

**Threshold:** ≥ **60%** of sampled group *pairs* score **2**.
**Sample:** ≥ 20 pairs across ≥ 3 topics.
**Supporting metric (diagnostic, not gate):** noise ratio. A noise ratio > ~50% on a
healthy corpus is a signal-quality warning that must be explained in the run report.

### SC-4 — Analyst utility

**Question:** Would a real analyst use this output — i.e. does it answer "what are people
believing and how is it changing" faster or better than reading threads manually?

**Method:** task-based evaluation. Give an analyst a topic + a time budget, and ask them
to characterise the narratives. Compare (a) NarraX-assisted vs (b) manual reading, on:
completeness of narrative inventory, correctness of attributed positions, and time to a
defensible answer.

**Threshold:** ≥ **2 of 3** raters agree NarraX produced a usable answer faster, **and**
no rater reports that NarraX output was *misleading*.

### SC-5 — Temporal usefulness

**Question:** Does the evolution view surface change that is real and non-trivial?

**Method:** on a topic with a known real-world inflection, check whether (a) an emerging
narrative is correctly surfaced, and (b) rising/fading directions match the raw volume
trend.

**Threshold:** Emerging-narrative detection is correct on **≥ 2 of 3** topics with a known
inflection, with **no** spurious "emerging" claim on a flat topic.

---

## 4. Diagnostic metrics (recorded, not gating)

These inform iteration. They are **not** success criteria; publishing them as such would
confuse effort with outcome.

| Metric | Why we track it |
|---|---|
| Stage durations, items in/out, drop counts + reasons | Find where quality/time is lost |
| Embedding/clustering parameter sensitivity | Understand stability |
| Stance classifier accuracy vs a labeled sample | Know whether stance is trustworthy |
| Sentiment agreement with a labeled sample | Same |
| LLM calls, tokens, and cost per run | Budget control |
| % narratives rejected by schema validation | Prompt/format health |
| Evidence links per narrative (distribution) | Detect thin grounding |
| Clusters discovered, noise ratio, mean intra-cluster distance | Structure health |
| Re-run structural diff (cluster/narrative overlap) | Stability |

---

## 5. Evaluation method (how to actually run it)

1. **Select evaluation topics.** ≥ 3 topics, including at least one with a known
   real-world inflection. Not topics used while developing prompts.
2. **Freeze the pipeline.** Pin model versions, prompt versions, and clustering params.
   Record them in the run report.
3. **Generate output.** Run the full batch pipeline per topic.
4. **Sample.** Draw the SC-1/SC-2 narrative sample and the SC-3 pair sample; record the
   sampling rule so it can be repeated.
5. **Rate blind.** Raters see the narrative + evidence (and the group), but not the
   pipeline's confidence and not each other's ratings.
6. **Compute.** Report per-criterion pass/fail vs threshold, plus rater agreement.
7. **Record.** Publish the run report (versions, corpus sizes, samples, ratings,
   disagreements). Persist it as an artifact, not a chat message.
8. **Decide.** Apply §6.

**Anti-gaming rules**

- No criterion may be tuned by editing the evaluation set after seeing results.
- Raters must not be the prompt authors for the topics they rate.
- "Coherent" cannot be awarded for a narrative that merely restates the topic.
- A topic that yields "no distinct groups" is a **valid** result and must be reported as
  such; inventing groups to satisfy SC-3 is a failure, not a pass.

---

## 6. Decision rule

```text
IF any hard gate (G-1..G-5) fails                        -> MVP not successful: fix and re-evaluate
ELSE IF SC-1..SC-5 all meet thresholds                   -> MVP hypothesis SUPPORTED: proceed to harden
ELSE IF some scores fail but G-1..G-5 pass               -> PARTIAL: iterate on the failing layer, re-run evaluation
ELSE (gates pass but most scores fail)                   -> MVP hypothesis NOT SUPPORTED: return to experiments/
```

A **PARTIAL** result is the expected first outcome and must name the specific layer to
fix (embedding coverage, cluster granularity, stance accuracy, prompt design, or
snapshot cadence) — not "improve quality".

---

## 7. Anti-criteria (explicit non-goals for MVP success)

The MVP is **not** judged successful by: number of endpoints, UI polish, deployment
automation, dataset size, number of models used, test coverage percentage, absence of
bugs, or architectural sophistication. These may be necessary enablers; none is evidence
that the product works.

---

## 8. Reporting template

Every evaluation produces a report containing:

```text
Run id / date / pipeline versions / prompt versions / clustering params
Topics: names, subreddits, windows, corpus sizes, noise ratios
Gate results:  G-1..G-5 (pass/fail + evidence link)
Score results: SC-1..SC-5 (value, threshold, pass/fail, sample size, rater agreement)
Diagnostics:   stage durations, drops+reasons, LLM calls/tokens/cost, validation rejects
Failures:      exact narratives/pairs that scored 0, with links
Decision:      SUPPORTED / PARTIAL(layer) / NOT SUPPORTED
```

If a report cannot be produced, the evaluation did not happen.
