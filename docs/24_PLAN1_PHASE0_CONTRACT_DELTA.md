# 24 — Plan-1 Phase 0: traced mechanics + design-contract delta (v4)

> **Superseded design snapshot (2026-06-19).** Production code now implements the five-column
> `(run_id, candidate_id, attempt, repeat_idx, env_id)` unique sample key, drops the retired
> three-column index, preserves samples with `ON CONFLICT ... DO NOTHING`, and supports repeat-aware
> execution/analysis. Statements below saying those phases are blocked or unimplemented describe
> the state when this design was written. See [document 21](21_ARCHITECTURE_DECISIONS.md) and the
> [current code audit](CURRENT_CODE_AUDIT_2026-07-21.md).

**Author:** Claude Opus 4.8, Senior System Architect/developer. **Date:** 2026-06-19 (v1 12:10Z; v2 12:32Z;
v3 12:42Z; **v4 12:52Z**, after Automation QA REJECT #3 identified narrow Phase-2 contract gaps).
The dated review artifact itself is not included in this publishable tree; the resulting corrections
are preserved in this document. **Status at publication:** documentation/design only; no production
code was claimed by this revision.

**Honest scope (v4):**
- **RESOLVES** the Plan-1 implementation contract: QA points **#1, #2, #3, #5, #6** + the **RunClass** decision.
- **FOUNDATION TRACED / DEFERRED:** point **#4** (repeat *measurement protocol* — §5 names the knobs; the values
  are a Phase-4 contract, gated before any repeat-execution code) and point **#7** (retry lease / late-duplicate /
  resume — dispatch phase). **#8–#12** are Plan-2, traced only; **Plan-2 stays blocked.**

**Revision log:** v1 overclaimed "resolves 12" (v2). v2's count plan didn't close algebraically; v3 rebuilt it
around record kinds (`canonical_rows == processed == V`, six-cell worked example) — Automation accepted the algebra,
migration fencing, and statistics in v3. **v4 closes the five narrow Phase-2 contract gaps Automation #24 raised:** an
authoritative `E` input for nested (§3.0); a K=1 normalization rule so `--repeat-policy nested` can't plan `C·E`
and execute `C` (§3.0/§4); corrected `disperse/metrics` semantics that don't re-run deterministic FW_VAR (§3.1);
renaming the planned metric count to `measurement_opportunities`, observed rows being runtime (§2–§3); and typing
CountPlan fields as `CardinalityEstimate`s with a separate `metric_artifact_bytes` disk dimension (§3.0/§3.3).

**Acceptance bar:** [`22_PLAN1_PLAN2_QA_READINESS.md`](22_PLAN1_PLAN2_QA_READINESS.md). The historical
combined plan is not included in this publishable tree; this document is its repository-local contract
delta, and [document 25](25_PLAN2_CONTROL_PLANE_ADR_AND_BASELINE.md) records the implemented baseline.
Claims anchored to `file:line` were read in the original review session.

---

## 0. Executive delta (vs. the plan's assumptions)
1. **Idempotency key is the triple `(run_id, candidate_id, attempt)`**, `candidate_id` composite text — not
   `combi_id_final`. The three identity columns already exist and are distinct; `repeat_idx`/`env_id` are additive.
2. **`attempt` = retry**, orthogonal to the new **sample** `repeat_idx`.
3. **`results_v2` rows are honest verdicts only.** A metric-only re-measurement is **not** a verdict and gets **no**
   canonical row — metric samples live in a **repeat-aware metrics artifact** (§3). This is what makes the count
   model close.
4. **Counts are a set of distinct record kinds, policy-specific, planned-vs-runtime separated** (§2–§3) — not one
   scalar, not a single per-policy multiplier.
5. **Median CI from the order-statistic over the per-candidate reservoir** (deterministic), with `n_min(α)` derived,
   not Welford `m2` and not a hard-coded threshold (§6).

---

## 1. Results identity & `results_v2` (QA #1, #2)

### 1.1–1.3 Schema, key, identity columns — *Automation-confirmed (unchanged from v2)*
- Schema/index: Java `ResultsV2SchemaMigrator.java:34-57`; Python `py_executor.py:140-164`. Columns incl.
  `run_id text, candidate_id text, attempt int DEFAULT 1, outcome text NOT NULL, …`; unique index
  `(run_id, candidate_id, attempt)`.
- Upsert: `ON CONFLICT (run_id, candidate_id, attempt) DO NOTHING`, never `DO UPDATE` (`ResultsV2Writer.java:122-127`;
  `py_executor.py:245-251`); column-list inference over a plain unique *index* (`ResultsV2Writer.java:110-121`).
- `candidate_id` = composite text `combi_id_final_combi_id_optional_fw_optJ` (`SchemaMigrator.java:30-33`; Java
  writes `resRepl`, `MainWatch.java:477+`). `attempt` = external retry id (`py_executor.py:951-953`), read-time
  `attempt DESC` selection, never UPDATE (`ResultsV2Writer.java:29-37`; `MainWatch.java:174-175`).
- **`outcome text NOT NULL`** (`SchemaMigrator.java:40`): **every `results_v2` row is a verdict** — load-bearing for §3.

### 1.4 Sample identity + read-time selection — *Automation-confirmed (v2)*
Sample identity = `(run_id, candidate_id, repeat_idx, env_id)`; `attempt` nested inside. Unique index becomes
`(run_id, candidate_id, attempt, repeat_idx, env_id)`. Aggregation read: `SELECT DISTINCT ON (run_id, candidate_id,
repeat_idx, env_id) … ORDER BY …, attempt DESC` (partitioned by the full sample key, not by `(run_id,candidate_id)`).
In-memory accumulators (Java `MainWatch.java:176`; Python `py_executor.py:1045`) re-key to
`(candidate_id, repeat_idx, env_id)`. `env_id` is dispatcher-assigned + persisted (manifest → executor →
`results_v2.env_id`); `worker` (pid, `py_executor.py:1055`) stays as process provenance only.

### 1.5 Legacy table stays additive — *Automation-confirmed*
`ResultsDbProvisioner.java:129,141` — `combi_id_final bigint NULL`, no PK/UNIQUE. Repeat identity lives only in
`results_v2`. Atomic legacy+v2 commit (`py_executor.py:260-266`).

### 1.6 Schema migration: version-gated cutover with genuine-old-binary fencing (revised per Automation #5)
**Status: phase 3a IMPLEMENTED** (2026-06-19, Phase 3). The additive `repeat_idx`/`env_id` columns are live in both
executors (`ResultsV2SchemaMigrator.java` `CREATE_TABLE_SQL` + `ADD_REPEAT_COLUMNS_SQL`; `py_executor.py`
`RESULTS_V2_ADD_REPEAT_COLUMNS_SQL`), applied via `ADD COLUMN IF NOT EXISTS` (no-op on fresh, backfill on prior
tables with K=1 defaults `repeat_idx=0, env_id=''`). The **3-col unique index + `ON CONFLICT` target are unchanged**
and the writer is unchanged (defaults populate K=1 rows ⇒ K=1 **behavior-compatible**: the named-column writer,
uniqueness, replay, and outcome behaviour are unchanged — adding physical columns does change tuple/`SELECT *` bytes,
so "behavior-compatible", not "byte-identical", per Automation #33). **The capability self-probe + old-binary fencing
described in 3b below are NOT implemented in 3a** — only the additive DDL is (Automation #33 limitation 1). **3b/3c (the
5-col sample-index cutover, the probe, + K>1 enablement) are DEFERRED to the executor phase** — K>1 stays refused
before any run dir / DB mutation (`REPEAT_K_REQUIRES_EXECUTOR_CAPABILITY`).

The 3-col and 5-col unique indexes **cannot coexist** for K>1 (the 3-col index rejects rows differing only in
`repeat_idx`/`env_id`), and `ON CONFLICT` target + unique index are co-versioned. Bundle runs are discrete batch
jobs (`bundle_run.py:11`), so cutover is between runs. **The new risk (Automation #5): a genuinely old executor binary
has no capability probe, and its `ensureSchema` calls `CREATE UNIQUE INDEX IF NOT EXISTS` for the *3-col* index
(`SchemaMigrator.java:55-57`) — so it would silently re-create the dropped index after cutover.** Therefore:

- **3a — additive columns, K≡1, old index kept** (IMPLEMENTED). `ADD COLUMN IF NOT EXISTS repeat_idx int NOT NULL
  DEFAULT 0, env_id text NOT NULL DEFAULT ''` (STEP-27 pattern). **No capability self-probe is implemented yet**
  (Automation #33 limitation 1): 3a is additive DDL only. The "v1-capability writer" with a launcher-invokable,
  pre-connect capability self-report is a **3b prerequisite** (below), to be implemented in Java + Python before any
  3b cutover.
- **3b — cutover owned by the launcher/migration owner, not lazily by a writer.** The launcher **verifies every
  Executor artifact is ≥ v1-capability BEFORE it connects** (fences out pre-Plan-1 binaries whose `ensureSchema`
  would resurrect the 3-col index), then performs, **in one explicit DB transaction**: bump
  `results_v2_schema_meta.version`; `CREATE UNIQUE INDEX results_v2_sample_uk (run_id, candidate_id, attempt,
  repeat_idx, env_id)`; `DROP INDEX results_v2_run_candidate_attempt_uk`. A writer probes the meta version/index at
  connect and **fails closed** (`RESULTS_V2_SCHEMA_CAPABILITY_MISMATCH`, non-zero exit) if its `ON CONFLICT` arity
  ≠ the live index — never a raw crash, never a silent duplicate.
- **3c — enable K>1** once `results_v2_sample_uk` is confirmed and all artifacts are capability ≥ v2.
- **Rollback boundary (Automation #5):** the down-migration (recreate 3-col, drop 5-col) is **lossless only before any
  K>1 row exists** (i.e. pre-3c). **After 3c, K>1 rows make 3-col uniqueness unsatisfiable**, so rollback requires
  archival/collapse of repeat rows and is *not* a lossless revert — stated as a hard boundary.
- **Tests:** (a) pre-3c rollback restores a writable K=1 schema; (b) old/non-probe binary is refused before
  connect (no index resurrection); (c) v1-writer vs 5-col-only schema ⇒ `RESULTS_V2_SCHEMA_CAPABILITY_MISMATCH`,
  no dup; (d) 3b is idempotent; (e) post-3c rollback is correctly refused as non-lossless.

---

## 2. Record kinds: planned vs. runtime/structural (rebuilt per Automation #1, #3)

`results_v2.outcome NOT NULL` ⇒ **a canonical row is an honest verdict**. So the model separates **planned** counts
(exact functions of `policy, scope, C, K, E`) from **runtime/structural** counts (outcome-dependent, checked against
the executor's own tallies). v2's error was treating metric-only re-measurements as canonical rows.

**Minimal independent planned quantities** (everything else derives):
- `A` = `assignment_units` — control-plane dispatch units (**policy-specific**, §3).
- `V` = `full_verdict_invocations` — runs producing a verdict ⇒ exactly `V` `results_v2` canonical rows ⇒
  `processed == attempted == canonical_rows == V`.
- `I` = `candidate_invocations` = `measurement_opportunities` — total sandbox runs = `V` + `metric_only_invocations`.
  Each invocation is **one chance to observe a metric**; whether it *produces* a row is a runtime fact (§2.2), so the
  planned field is `measurement_opportunities`, **not** an assumed-observed `metric_samples` (Automation #24-4).
- `metric_only_invocations = I − V`.

**Metric observations live in a repeat-aware metrics artifact, not `results_v2`** (Automation model (a)): the existing
metrics corpus (`_write_metrics_corpus`, `py_executor.py:710-730`, today keyed by `candidate_id` only) becomes keyed
by `(candidate_id, repeat_idx, env_id)` — up to `I` rows, fewer when measurements are missing (§2.2). Per-candidate
aggregation (§6) reads **valid `metric_rows` from this artifact**; `results_v2` carries verdict identity/outcome only.

| invariant (`bundle/invariants.py`) | line | kind | v3 form |
|---|---|---|---|
| `reader.emitted_eq_expected` | 33-35 | **planned** | `emitted == A` |
| `handoff.candidate_count_matches` | 48-50 | **planned** | `manifest_units == A` |
| `results_v2.attempted_matches_processed` | 153-160 | structural | `attempted == processed` (== `V`) |
| `results_v2.write_counts_consistent` | 122-150 | structural | unchanged |
| `executor.processed_eq_sum` | 64-76 | structural | `processed == pass+fail+broken+timeout+infra_fail+skipped+cancelled` (§2.1) |
| `executor.inserted_matches_policy` | 108-119 | structural | unchanged (`inserted == pass+fail`) |
| `results_db.count_eq_inserted` | 163-165 | **structural (runtime subset)** | `db_total == inserted`; plan exposes only an *expected-eligible max* `≤ V` (Automation #3) |
| `analyzer.input_matches_metrics` | 168-177 (WARN) | **runtime + missing tally** | `metric_rows + missing_measurements == measurement_opportunities` (§2.2) |

### 2.1 SKIPPED / CANCELLED (Automation, prior round)
Extend `processed_eq_sum` to include `skipped + cancelled`: **CANCELLED counts** toward `processed` (dispatched then
aborted — resume must see it); **SKIPPED counts only if seen-and-skipped**, never-dispatched work is a separate
`planned − dispatched` bucket. Both 0 pre-dispatch ⇒ non-regression now; required before Plan-2 concurrent dispatch.

### 2.2 Missing measurements are real (Automation #3)
A verdict can emit **no** metric line: `py_executor.py:1203` writes a metrics entry only `if metrics_capture and
metrics_capture[0]` — an empty capture ⇒ no line. So the planned `measurement_opportunities` is an **opportunity
count, not an observed-row count** (Automation #24-4). Define a runtime `missing_measurements` tally closing as
`metric_rows + missing_measurements == measurement_opportunities`; `analyzer.input_matches_metrics` stays WARNING;
a `--formal` mode may fail closed on `missing_measurements > 0`. The Analyzer (§6) consumes only valid `metric_rows`,
so a candidate's per-candidate `n` is its valid-row count **after** missing (which can drop it below `n_min(α)` ⇒
tie-ineligible).

---

## 3. The structured count plan (closed; policy-specific) — resolves QA #3

### 3.0 Definitions, inputs, typing
`C` distinct candidates = `plan.final`, a **`CardinalityEstimate`** (EXACT/BOUNDED/ESTIMATED/UNKNOWN); `K` repeats
(exact int); `E` executor environments. The **verdict execution is metric sample 0** (inline harvest
`py_executor.py:1199-1204`). Under `scope=metrics` the verdict runs **once per candidate** (local/disperse) or once
per **`(candidate, env)`** (nested) — **not** once per assignment (disperse/metrics has `A=C·K` but `V=C`; Automation #26
Limitation 1, implement the §3.1 table) — and the remaining opportunities are metric-only, respecting the approved
"do not re-run deterministic FW_VAR" (the historical repeat-scope rule preserved in §3.1); `scope=all`
makes every sample a full verdict.

- **`E` is an authoritative input, not derived (Automation #24-1).** A new typed config `fw.executor.repeatEnvironments`
  / CLI `--repeat-environments E` (int ≥ 1), **required for `nested` with K>1** and **rejected with a named
  validation error if unknown** — never optimistically defaulted (that would under-budget `C·E·K`). For
  `local`/`disperse` it does not enter the counts. `--workers` is stress concurrency, explicitly **not** `E`. The
  plan-only output records `E` and its **source** (`--repeat-environments`, or a future recorded pool-inventory
  artifact); dynamic discovery may replace the explicit value only via a recorded inventory + re-budget before
  execution, and the planned `E` must equal the count of distinct `env_id`s the dispatcher later assigns.
- **CountPlan fields are `CardinalityEstimate`s (Automation #24-5).** `count_plan` multiplies `C` by the exact ints
  `K`/`E` through the existing confidence-preserving discipline
  (`resources.py:_scaled_estimate`/`fg._combine_product`): **UNKNOWN stays UNKNOWN** (never 0 or integer-only),
  BOUNDED keeps lower/upper, mode + reasons propagate.
- **K=1 normalization (Automation #24-2).** When `K==1`, repeat policy/scope/environments are **operationally inactive**:
  `E_effective=1`, so `A == V == I == C` for **every** policy/scope. `count_plan` applies this at the top; the
  plan-only output prints a note that the topology flags are inactive at K=1. This makes K=1 a true non-regression
  regardless of stray `--repeat-policy`/`--repeat-environments`, tested for **all** policy×scope combinations.

### 3.1 Policy-specific dispatch (Automation #2)
The approved semantics retained from the historical combined plan: **disperse scatters
`candidate×repeat` across Executors** (between-environment variance) ⇒ K independently assignable units;
**local** sends a candidate to one Executor that loops K (within-environment variance) ⇒ one unit; **nested** =
one unit per `(candidate,env)`, each looping K. So `A` is policy-specific (not just `E`):

| policy | scope | `A` (assignment_units) | `V` (=canonical=processed) | `I` (=measurement_opportunities) | `metric_only` = I−V |
|---|---|---|---|---|---|
| local | all | `C` | `C·K` | `C·K` | 0 |
| local | metrics | `C` | `C` | `C·K` | `C·(K−1)` |
| disperse | all | `C·K` | `C·K` | `C·K` | 0 |
| disperse | metrics | `C·K` | `C` | `C·K` | `C·(K−1)` |
| nested | all | `C·E` | `C·E·K` | `C·E·K` | 0 |
| nested | metrics | `C·E` | `C·E` | `C·E·K` | `C·E·(K−1)` |

(All rows are *before* the K=1 normalization of §3.0, which overrides them to `A=V=I=C` when `K=1`.)

**`disperse/metrics` respects the approved scope semantics (corrected per Automation #24-3).** v3 wrongly set
`disperse/metrics == disperse/all` (`V=C·K`), which would re-run the deterministic FW_VAR verdict K times —
contradicting the retained repeat-scope rule above. Correct: the verdict runs **once** (sample 0, `V=C`) while the
`C·(K−1)` scattered units are **metric-only** across environments (`A=C·K` still scatters, for between-environment
variance). "No cheap metrics mode" was a *current candidate-runner* limitation Phase 4 changes — **not** a
consequence of distribution — so it is not encoded as a count rule.

### 3.2 Worked example — every cell, proving closure (Automation #1 requirement)
`C=2, K=3, E=2` (E used by nested only). Verify per cell: `canonical_rows == processed == V`;
`measurement_opportunities == I == V + metric_only`; `A` is the dispatch count.

| policy/scope | A | V=canonical=processed | metric_only | I=measurement_opportunities | closes? |
|---|---|---|---|---|---|
| local/all | 2 | 6 | 0 | 6 | `6==6`, `6==6+0` ✓ |
| local/metrics | 2 | 2 | 4 | 6 | `2==2` (no false verdicts), `6==2+4` ✓ |
| disperse/all | 6 | 6 | 0 | 6 | ✓ |
| disperse/metrics | 6 | 2 | 4 | 6 | `2==2` (verdict once), `6==2+4` ✓ |
| nested/all | 4 | 12 | 0 | 12 | ✓ |
| nested/metrics | 4 | 4 | 8 | 12 | ✓ |

The v2 contradiction (local/metrics: `processed=2` vs `canonical_rows=6`) is gone: canonical rows = `V`; the metric
observations are up to `I` rows in the metrics artifact, not falsified verdicts; `legacy_rows ≤ V` (runtime). At
`K=1` the §3.0 normalization forces every cell to `A=V=I=2`.

### 3.3 Consumer map (each consumer names its field)
- **Planned (exact, as `CardinalityEstimate`s):** `reader.emitted_eq_expected ← A`;
  `handoff.candidate_count_matches ← A`; budget `results_db_bytes ← V·canonical_row_bytes` (**verdict rows only**);
  **new** budget `metric_artifact_bytes ← I·metric_row_bytes` (the `metrics.kv` **file** artifact, Automation #24-5);
  budget `duration_seconds ← V·t_v + metric_only·t_m` (÷ realized parallelism); budget `request_count ← I·r_ext`
  where `r_ext` = assumed external requests **per candidate invocation** (metric-only invocations can issue
  requests) — control-plane `A` tracked **separately**, not folded in; RunClass `← I` (§3.5).
- **Disk budget extended (Automation #24-5):** the disk sum is currently `Core+Results+sources`
  (`bundle/budgets.py:108-121`); Phase 2 **adds `metric_artifact_bytes`** (`Core+Results+sources+metric-artifact`)
  rather than mislabel filesystem data as Results-DB rows; `results_db_bytes` stays `V·canonical_row_bytes`.
- **Runtime/structural (not plan-exact):** `results_db.count_eq_inserted` (`db_total==inserted`),
  `processed_eq_sum`, `attempted_matches_processed`, `write_counts_consistent`; plan exposes *expected-eligible*
  `legacy_rows ≤ V` and `metric_rows ≤ measurement_opportunities` as **upper bounds**, never equalities.
- **Unchanged by K:** budget `core_db_bytes ← plan.mandatory` (`resources.py:156-158`); budget `final_candidates ← C`.

### 3.4 `source_files` — corrected factor (Automation #4)
`source_files = C · mat`, **`mat ∈ {1, S}`** where `S` = samples/candidate (`K`, or `E·K` nested): `mat=1` when one
source is reused per candidate (default), `mat=S` when each sample is materialized as its own file. (v2's `C·M,
M∈{0,1}` was arithmetically wrong — `M=1`/default needed `C·S`/`C`, not `0`/`C`.) **Logical** `source_records` is
this; **physical** inode/file count is a *separate* function of the shard sink's packing limits
(`ShardCorpusEmitter`, STEP 32), not the logical sample count — traced in phase 5, not assumed here.

### 3.5 RunClass — RESOLVED (QA-approved)
`RunClass` (`resources.py:24-57`) classifies **total execution work `I`** (incl. nested `E`); `final_candidates`
keeps counting distinct `C`. **Both** `final_count` **and** `I` are preserved in the resource-plan JSON
(`resources.py:243-259`) and human output (`:273-287`).

### 3.6 Where it wires (no code yet)
One pure, fully-tested `count_plan(policy, scope, C, K, E) -> CountPlan` (proposed `bundle/counts.py`) returning the
named fields above, consumed by `estimate_resources` (`resources.py:138`), `evaluate_budgets` (`budgets.py:100`),
the planned invariants, and progress/timeout. Structural invariants keep reading runtime tallies.

---

## 4. K=1 compatibility + fail-closed K>1 boundary (QA #2) — *Automation-confirmed (v2)*
- *Byte-identical at K=1:* legacy `py_executor DONE:` line (`py_executor.py:1085-1086`), legacy rows, Handoff-v2
  manifest absent repeat fields, Core output.
- *Additive:* `results_v2`/metrics rows gain `repeat_idx=0, env_id=''`; `RESULTS_V2:`/`OUTCOMES:` lines already
  additive (`:1090-1094`).
- *K=1 ⇒* the §3.0 normalization makes **`A=V=I=C`** (and the *derived* `metric_only=0`, not C — Automation #26
  Limitation 1; byte/time budget fields keep their own units/formulas) for **every** policy/scope (topology flags
  inactive), schema is the 3a phase — true non-regression, tested across all policy×scope combinations (Automation #24-2).
- **Fail-closed K>1:** until the schema-capable (§1.6) + executor phases land, `K>1` is **rejected before launch**
  (`REPEAT_K_REQUIRES_EXECUTOR_CAPABILITY`); Phase 2 may print the plan-only count plan + budgets but must not
  execute. **K=1 stays the only executable path.**

---

## 5. Measurement protocol & cache — point #4 FOUNDATION TRACED / DEFERRED to Phase 4 (Automation)
**Re-scoped:** v2 marked #4 "resolved"; it is not. §5 *traces the foundation* but the protocol *values* are a
**Phase-4 contract, gated before any repeat-execution code lands.**
- **Foundation (traced):** metrics are harvested in the same in-sandbox pass as the verdict, no re-run
  (`py_executor.py:1199-1204`, `:1382-1385`); the verdict run is metric sample 0; `repeatScope=metrics` re-invokes
  **only the measurement** through the **same** sandbox/oracle path (`sandbox.provision()` `:1145`) — never a bypass.
- **Deferred to Phase 4 (must be decided + gated):** warm-up discard count, exact interleave order (+ recorded
  seed), fresh-vs-reused process, state reset, per-measure timeout, host/`env_id` identity, isolation.
- **Cache bypass (decided):** `LineExecutor.Caching` (`CachingExecutorVerify.java:53`, cap 64) skips re-execution on
  identical raw input (`RemoteWorkerVerify.java:32`); for `repeatEachCandidate>1` bypass it on the measurement path
  or cache only the per-candidate **aggregate** — never the per-repeat value.

---

## 6. Statistics & significance tiers — RESOLVED (revised per Automation #6)

### 6.1 Median + order-statistic CI
Substrate: the per-candidate **Algorithm-R reservoir** of actual values (`OnlineMetricAggregator.java:34-92`,
deterministic seed `:70-72`), **per `candidate_id` group**, **not** Welford `m2` (population stdev `:156`).
- **Point:** sample median (even-`n`: mean of the two central order statistics).
- **Interval:** distribution-free median CI from symmetric order-statistic ranks `l = max{ r : 2·BinomCDF(r−1; n,
  ½) ≤ α }`, `u = n+1−l`, confidence `1−α` (default 0.95, `fw.analyzer.repeat.ciAlpha`). Report **achieved** coverage
  (discrete `≥` target) — the *sample* is exact (for `n ≤ 1024`, §6.3), the *interval* coverage is achieved-not-nominal.
- **`n_min(α)` derived, not hard-coded (Automation #6):** the widest (extreme-rank `l=1,u=n`) interval has coverage
  `1 − 2^{-(n-1)}`, so **`n_min(α) = 1 + ⌈log₂(1/α)⌉`**. Matches the independent check:
  `α=.10 → n=5 (.9375)`, `.05 → n=6 (.96875)`, `.01 → n=8 (.9921875)`. For `n ≥ n_min(α)` use interior ranks for
  coverage nearer nominal. For `2 ≤ n < n_min(α)`: report `median` + `[min,max]`, `ci_method="range_insufficient_n"`,
  `coverage_achieved=null`. For `n=1` (K=1): `median=value, ci=null, ci_method="point_k1"`.
- **Determinism:** order statistics need no RNG.
- **TARGET goals (Automation #6):** transform **each raw sample** to `|value − target|` **before** computing the median
  and CI (transforming interval endpoints is *not* equivalent).
- **Output schema:** `{candidate_id, metric, n_total, n_used, median, ci_low, ci_high, ci_alpha, ci_method,
  ci_rank_low, ci_rank_high, coverage_achieved, reservoir_capped}`.

### 6.2 Significance tier — anchored neighborhoods (no transitive closure)
Per objective `j` with direction from `GoalSpec` (MIN/MAX/TARGET, TARGET on the transformed samples): `A,B`
**indistinguishable on `j`** iff median CIs overlap (`max(lo) ≤ min(hi)`); a missing value on `j` ⇒ distinguishable.
`A,B` **pairwise noise-tied** iff indistinguishable on **every** objective. **Tier `T(P) = { Q ∈ front : pairwise
noise-tied with P }`** — anchored neighborhoods, **no transitive closure** (so `A~B, B~C, A≁C` ⇒ `T(A)={A,B}`,
`T(C)={B,C}`, never `{A,B,C}`). **Tie-eligibility (Automation #6):** a candidate with `ci=null`
(`range_insufficient_n`/`point_k1`) has no interval to overlap ⇒ **tie-ineligible**, its own singleton, flagged
`tie_eligible=false`. Multiple comparisons: per-pairwise `α`; `|front|` + `α` reported (consumer may Bonferroni).
Integration: deterministic post-pass over `OnlinePareto.snapshot()`/`frontVectors()` (`OnlineMetricAggregator.java:307-309`);
`NsgaIIVerify` consumes the same per-candidate median point. **Required test:** `A~B, B~C, A≁C` ⇒ `T(A)={A,B}`,
`T(C)={B,C}`, no `{A,B,C}`; + determinism.

### 6.3 Reservoir cap = primary contract bound (Automation #6)
Reservoir merge is only approximately uniform for unequal shard sizes and seeding alone does not fix merge order
(`OnlineMetricAggregator.java:97-102`). **Decision:** the primary order-statistic contract **supports per-candidate
repeat groups of `n ≤ 1024`** (`RESERVOIR_CAP`), where the reservoir is the **exact** sample and merge is plain
concatenation (order-independent, no subsampling). `K ≤ 1024` is the realistic regime. For `n > 1024` the contract is
**not** offered: fail closed / flag `reservoir_capped=true` and do not emit an order-statistic CI (a weighted,
merge-order-independent overflow estimator + tests is deferred, only if ever needed).

---

## 7. TRACED / DEFERRED (not resolved here)
- **#7 retry lease / late-duplicate / resume** — foundation set (exact idempotency key §1.4 ⇒ at-least-once +
  exact key); ownership/lease/timeout/late-dup/resume designed in the disperse/nested phase (doc 22 phase 6) before
  concurrent dispatch. §2.1 pre-specifies CANCELLED/`processed` to keep it consistent.
- **#8–#12 Plan-2 (blocked):** sequential single-candidate `RemoteWorker` poller (`RemoteWorkerVerify.java:30,70,
  84-90,148-157,173`) → fan-out ADR (#8); `StructuredTaskScope` preview decision (#9); pgjdbc skew
  (Analyzer/Executor/Reader `42.7.11`, Reader declares it twice; Core `42.7.2`) verified on the **packaged** jar via
  JFR (#10); `Outcome.CANCELLED` exists (`py_executor.py:114`, #11) + §2.1; RemoteWorker baseline (#12).

---

## 8. Verified-vs-to-trace ledger
**VERIFIED (file:line):** `results_v2` triple key + `outcome NOT NULL` + `ON CONFLICT` arbiter (both executors);
composite `candidate_id`; external `attempt` + read-time latest-wins; accumulators keyed by candidate; legacy table
no unique key; verdict-without-metric-line path (`py_executor.py:1203`); the eight invariants; budget dimensions and
their `plan.final`/`plan.mandatory` bases; metrics one-pass harvest; `LineExecutor.Caching` skip; reservoir
(Algorithm-R, deterministic, cap 1024) vs Welford population stdev; sequential RemoteWorker; pgjdbc POM versions;
`Outcome.CANCELLED`.
**NOT yet traced (deferred to the consuming phase):** full Java `MainWatch` dispatch loop body; the `disperse`
dispatch point + `source_files` physical packing in `ShardCorpusEmitter`; how `bundle/stages.py` launches/waits on
Executors; whether the Analyzer reads metrics from the corpus vs polling; assignment-time `env_id` plumbing through
the manifest; the **packaged** pgjdbc + JFR pinning; cgroup/cpuset isolation on the target host; the metrics-artifact
schema (repeat-aware corpus) detail.

---

## 9. Proposed next increment (for QA to gate before any code)
**Plan-1 Phase 2 — config + the structured count plan, PLAN-ONLY for K>1:**
1. Parse/validate `repeatEachCandidate (K)`, `repeatPolicy ∈ {disperse,local,nested}`, `repeatScope ∈ {all,metrics}`,
   and **`repeatEnvironments (E)`** in `bundle/config.py` (+ `bundle_run.py` CLI). Validation: `E ≥ 1`, **required for
   `nested` with K>1, named error if unknown** (§3.0); `--workers` is not `E`; negative-case tests.
2. `count_plan(policy, scope, C, K, E) -> CountPlan` (§3) as one pure, fully-tested function whose fields are
   **`CardinalityEstimate`s** (UNKNOWN/BOUNDED `C` preserved through ×K/×E — tested); asserting the §3.2 six-cell
   closure **and** the §3.0 **K=1 normalization for every policy×scope** (not just defaults); wire named fields into
   `estimate_resources`/`evaluate_budgets` + `bundle plan`'s budget evaluation; RunClass per §3.5 with both
   `final_count` and `I` in JSON + human output. **DEFERRED:** wiring the count plan into the *runtime* count
   invariants (`bundle/invariants.py`) and progress is safe to defer while K>1 execution is blocked — it lands with
   the executor phase that actually runs repeats, not Phase 2 (Automation #29 limitation 3).
3. **Budget:** add the `metric_artifact_bytes` disk dimension and include it in the `Core+Results+sources` disk sum
   (`budgets.py:108-121`); keep `results_db_bytes = V·canonical_row_bytes` (§3.3).
4. **Fail-closed gate (§4):** K>1 ⇒ plan-only; execution rejected with `REPEAT_K_REQUIRES_EXECUTOR_CAPABILITY`;
   K=1 non-regression tests across all policy×scope.
5. **No schema, executor, Analyzer, metrics-artifact, or dispatch changes** (phases 3–6). The repeat-aware
   metrics-artifact schema and the `disperse` physical materialization are phase-5 traces, not assumed here.

**Status: IMPLEMENTED** (Phase 2a 15:34Z + 2b 16:40Z + Automation #29 integration fixes 17:01Z — `bundle/counts.py`,
`config.py`, `resources.py`, `budgets.py`, `cli.py`; tests in `test_bundle_counts.py` + `test_bundle_budgets.py`;
owning suite **97 green**). `bundle plan` now evaluates budgets and persists `budget_checks` (Automation #29 finding 1);
`count_plan` defensively validates types/E (finding 2); `I` keeps its `CardinalityEstimate` confidence in
diagnostics — `execution count I = UNKNOWN`, never `None` (finding 3). Plan mode is analysis-only and exits 0 with a
visible + persisted BLOCKING status; the run path is the enforcement point.
