# 11 — Analyzer Guide

The Analyzer (`Analyzer_trunk`, headless `AnalyzeKv`) ingests candidate metrics and selects the
non-dominated (Pareto) candidates against objectives. The Bundle feeds it a `K=V` corpus harvested
from the candidates' real execution (see [09](09_READER_EXECUTOR_AND_RESULTS.md)).

The current default front algorithm is **NSGA-II** (fast non-dominated sorting plus crowding
distance). The Analyzer API/UI also implements **NSGA-III**, **SPEA2**, and **MOEA/D**. They preserve
the declared-goal rank-1 membership contract while exposing algorithm-specific diversity/ranking
metadata. `AnalyzeKv` uses the project default; alternate algorithms are API/UI selections rather
than Bundle CLI flags.

## Metrics format

One line per candidate, space-separated `key=value` tokens. The Bundle prefixes provenance tokens
(`candidate_id=… source_ref=… run_id=…`) and appends the candidate's own `app=… K=V … FW_VAR=…`
line. Example (verified, flagship):

```
candidate_id=11_0_0 source_ref=11_0_0.py run_id=gate-final app=secure_pipeline mode=strict \
  order=normalize>tag>redact features=cache payload=ascii ... security_failures=0 correct=1 \
  latency_ms=32.102 FW_VAR=0
```

## Formal vs exploratory modes (`AnalysisMode`)

| | **Formal** (`--analysis-mode formal`) | **Exploratory** (default) |
|---|---|---|
| Objectives | explicit goals **required** | declared + **auto-discovered** |
| Discovery | `DECLARED_ONLY` — no auto axes | auto-discovery on, inferred axes labelled |
| Direction | fixed exactly as declared | declared + inferred |
| Corpus count | **required and checked** (declared == ingested, fail closed) | not required |
| Use | a reproducible Pareto conclusion | exploration |

Verified contrast on the **same** 288-candidate corpus:
- **Formal** with goals `security_failures:max, latency_ms:min, correct:max` → a **3-candidate**
  Pareto front, no auto axes, corpus 288 checked, `provenance_ok`.
- **Exploratory** → auto-discovers extra axes (`candidate_id`, `source_ref`, `rotated`, `poisoned`,
  `leak`, `stale_key`, …) with inferred directions, which **changes the dominance front**. This is
  exactly why formal mode forbids them — an auto-discovered axis must never silently alter a formal
  conclusion. Do not present exploratory output as a formal result.

In **both** modes, an explicit goal whose declared direction disagrees with lexical inference is
**surfaced** (`directionConflicts`) but the explicit direction always wins — never silently mixed.

Formal mode fails closed if goals are empty or the corpus count is missing/non-positive (the
launcher also rejects `--analysis-mode formal` without `--analyzer` goals before any run starts).

## Repeat-aware aggregation

When the corpus contains `repeat_idx`, `AnalyzeKv` validates and deduplicates the full
`(candidate_id,repeat_idx,env_id)` observation identity before ordinary eligibility/ranking. It
produces one objective vector per candidate using the median and a distribution-free
order-statistic confidence interval (default α=0.05); insufficient K is explicitly marked rather
than assigned invented confidence. Conflicting provenance/verdict values fail closed. Overlapping
valid confidence intervals define noise-tied neighborhoods. The formal corpus count closes against
distinct candidate aggregates C, while logs retain the raw-sample count I.

## Goals / directions / weights / normalization

Goals are `key:min` / `key:max` (and `TARGET` goals have no min/max direction). The run manifest
records the mode, goals, weights, and normalization so a report is reproducible. Direction is
inferred lexically only in exploratory mode (e.g. a name containing "failures" → minimize) — which
is wrong for a red-team experiment that intentionally **maximizes** discovered failures, so declare
goals explicitly for formal studies.

## Provenance & non-dominance explanation (`provenance.json`, `analyzer.provenance/v1`)

Every metric line carries `candidate_id`/`run_id`/`source_ref`, so each selected candidate is
traceable to its source row and verdict. The report records `candidates_seen`, the goals,
`provenance_ok` + `provenance_issues`, and per selected candidate: `candidate_id`, `run_id`,
`source_ref`, `line_no`, `objectives`, `dominated_by`, `dominates`, and `reason_non_dominated`.
Verified flagship: `candidates_seen=288`, `provenance_ok=true`, 0 issues, 3 selected. In formal mode
a selected candidate that cannot be traced makes `AnalyzeKv` exit non-zero and fails the stage.

## BundleSeed and iterative search

`--seed-output` asks the Analyzer stage to write schema-v1 `bundle_seed.json` containing Pareto
winners, per-metric champions/balanced winners, declared metrics, ranges, provenance, and available
diversity metadata. A later run can consume it with `--seed-from`; winner rows are decoded against
the DB and narrowing retains a configurable exploration floor and declared-order neighbors.
`bundle iterate SPEC --iterations N --analyzer ...` closes this loop and records iteration lineage
as `bundle.iterate/v1` in `<base-run-id>-iterate.json`. Missing/unsupported seeds, unjoinable
winner IDs, or insufficient support fail
closed or produce an explicit no-signal plan; they never silently narrow to an empty space.

## Interpretation limits

- A Pareto front can be mathematically correct yet operationally unhelpful if the objectives encode
  conflicting meanings — choose objectives deliberately.
- The corpus must be complete for a formal conclusion; this is now enforced (the corpus-count check
  caught BUG-1). Analyzing a truncated corpus is not a formal result.
- The Analyzer judges **metrics**, not correctness; the oracle (the spec's verdict) defines meaning.
- Repeat aggregation reduces noisy observations to a defensible summary; it does not make a small K
  statistically strong. Inspect `ciValid`, sample count, coverage, missing samples, and tie tiers.
