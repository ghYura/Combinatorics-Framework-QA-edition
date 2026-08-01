# 06 — Planning, Budgets, and Counts

The Bundle treats every run as a **resource plan first**. `bundle plan` quantifies a spec without
touching PostgreSQL; budget gates can block a run before any DB write.

## Count vocabulary — never conflate these

| Count | Stage | Meaning |
|---|---|---|
| raw values | spec | declared values per slot |
| per-slot Core rows | Core | `verb_cardinality(slot)` (e.g. `FW_Permut` over 3 → 6) |
| **mandatory Core product** | Core | Π over mandatory (non-Exclude/Heading/Optional) slots |
| **post-sieve** | sieve | mandatory minus pruned rows |
| **optional multiplier** | Reader | Π(nᵢ + 1) over `FW_Optional` slots |
| **final candidates** | Reader | post-sieve × optional multiplier (emitted artifacts) |
| **assignment units (A)** | control plane | dispatch units; depends on repeat policy |
| **full verdict invocations (V)** | Executor | canonical outcome rows; `processed == V` |
| **measurement opportunities (I)** | Executor | full verdict plus metric-only invocations |
| **persisted samples** | results_v2 | immutable five-part sample identities actually written |
| **Analyzer ingested** | Analyzer | observed metric lines, reconciled against I with missing samples |

Every number is tagged **EXACT**, **BOUNDED** `[lo, hi]`, **ESTIMATED**, or **UNKNOWN** with a
formula and the reason for any uncertainty.

## Repeat-aware A/V/I planning

Let C be distinct final candidates, K repeats, and E environments. K=1 normalizes every policy to
`A=V=I=C`. For K>1:

| policy / scope | A | V (verdict rows) | I (measurement opportunities) |
|---|---:|---:|---:|
| local / metrics | C | C | C×K |
| local / all | C | C×K | C×K |
| disperse / metrics | C×K | C | C×K |
| disperse / all | C×K | C×K | C×K |
| nested / metrics | C×E | C×E | C×E×K |
| nested / all | C×E | C×E×K | C×E×K |

The launcher currently executes K>1 only for Python/Java `local` with `metrics` or `all`; the other
rows are planning/control-plane contracts and are launcher-refused. Under `metrics`, sample zero is
the one full verdict and K−1 invocations are metric-only. Under `all`, every repeat is a full
verdict. Results are keyed by `(run_id,candidate_id,attempt,repeat_idx,env_id)`; retry `attempt` is
not a repeat.

## Exactness semantics

- **EXACT** — first-order verbs (`FW_Combi(k)`, `FW_Permut(k)`, `FW_Subsets`, …) and the optional
  multiplier have closed-form cardinality.
- **BOUNDED `[0, mandatory]`** — a declared constraint's selectivity is not known without running
  the sieve, so post-sieve is a provable range, not a point.
- **UNKNOWN** — the brace (`FW_(…)`) and `FW_Group` are second-order: their joined/grouped result
  row counts are not known until Core runs, so the planner refuses to fold them into an exact
  product (verified: `brace_demo`/`group_sep_demo` plan → mandatory UNKNOWN, run class X). This
  matches `estimate_core_combos`, which intentionally does not estimate brace/Group.

## Worked example — the flagship secure-pipeline (verified `bundle plan`)

```
per-slot Core rows:
  HEAD FW_Combi(1) n=1 → 1   MODE FW_Combi(1) n=2 → 2   ORDER FW_Permut n=3 → 6
  FEATURES FW_Subsets n=2 → 4   PAYLOAD FW_Combi(1) n=2 → 2
  OPT_ROTATE [FW_Optional] → 1   OPT_POISON [FW_Optional] → 1   TAIL → 1
mandatory Core product: 96   (EXACT — 1·2·6·4·2)
estimated post-sieve: 96     (BOUNDED [0, 96] — 1 constraint; selectivity not evaluated)
optional multiplier: 4       (EXACT — (1+1)·(1+1))
final candidate count: 384   (BOUNDED [0, 384] — post_sieve × optional)
run class: S
```

Actual at run time (verified, with `--sieve`): Core **96** → sieve removes **24** → post-sieve
**72** → Reader emits **72 × 4 = 288** candidates. (The plan's 384 is the pre-sieve upper bound;
with the constraint applied the realized final is 288 — the plan correctly labels 384 BOUNDED, not
exact.)

## Cross-stage invariant chain (machine-enforced, `bundle/invariants.py`)

```
planned mandatory 96 (EXACT) == actual Core 96
post-sieve 72 ≤ Core 96                       (post_sieve_le_core)
Reader emitted 288 == 72 × optional 4         (reader_emitted_eq_expected)
Executor processed 288 == 150 PASS + 138 DOMAIN_FAIL + 0(BROKEN+TIMEOUT+INFRA)  (processed_eq_sum)
inserted 288 == PASS + DOMAIN_FAIL            (inserted_matches_policy)
results_v2 attempted 288 == processed 288; written counts consistent
Results DB rows == inserted                   (results_db_eq_inserted)
Analyzer ingested 288 == corpus count 288     (analyzer_input_matches_metrics + AnalyzeKv formal check)
```

A failed **CRITICAL** invariant raises and fails the run (fail closed). The displayed 288 chain is
a dated K=1 run, so A=V=I=C and the legacy-looking equality is expected; it must not be generalized
to K>1. BROKEN/TIMEOUT/INFRA_FAIL
are CRITICAL by default but can be downgraded to WARNING with `--executor-tolerate-outcomes`.

## Run classes (S/B/L/X)

Configurable thresholds on the final candidate count (defaults from the high-level plan):

| Class | Scale | Intent |
|---|---|---|
| **S** smoke | ≤ ~100 | spec/oracle validation, local |
| **B** bounded | ≤ ~10,000 | exact enumeration, full artifacts |
| **L** large | ≤ several million | streaming/sharded, explicit budgets |
| **X** extreme | tens of millions+ | Core/sieve benchmarking, distributed; mandatory approval |

Verified classifications: secure-pipeline 288 → **S**; superopt 924 → **B**; api_probe 576 → **B**;
brace/group (UNKNOWN final) → **X** (conservative). Tune with `--class-*-max`.

## Resource estimates

The plan estimates Core/Results DB bytes, candidate source bytes, loose-file inodes, external
request count, and execution duration from the applicable C/A/V/I quantity — each as a range with explicit **assumptions** (e.g. per-unit
byte cost `[200,2000]` without a sample). It names the **dominant resource**. Replace the generic
per-unit assumptions with measured values from the stage benchmark
([13_BENCHMARKS_AND_SCALE_CLAIMS.md](13_BENCHMARKS_AND_SCALE_CLAIMS.md)) for tighter estimates.

## Budget gates and overrides

Seven hard ceilings (defaults are conservative placeholders, all overridable per dimension):
`mandatory_rows`, `final_candidates`, `disk_bytes`, `inodes`, `wall_time_seconds`,
`external_requests`, `monetary_cost`. Exceeding a hard ceiling blocks the run **before** Core/DB
writes. An override requires an explicit flag **and** a non-empty reason recorded in the manifest:

```bash
--budget-final-candidates 500000 --override-budget "approved L-class compatibility sweep"
--budget-final-candidates none      # explicitly disable one dimension's gate
--allow-extreme                      # required additionally for an X-class run
```

A `warn_fraction` (default 0.5) emits warnings before the hard limit. Combinatorial-explosion
prevention is thus mechanical: a synthetic factorial/power-set spec is stopped at plan/budget time,
not after days of DB writes.

## Lifting the limiter — `unleash_initial_productivity_power`

The budget gate is a *limiter*, not an engine governor: Core's generative power is never detuned
(the canonical truth numbers, verbs, and cardinality are untouched). For an expert who controls
their environment and explicitly does **not** want the limiter, a single boolean lifts it:

```bash
--unleash-initial-productivity-power                      # CLI
BUNDLE_UNLEASH_INITIAL_PRODUCTIVITY_POWER=true            # env
{ "unleash_initial_productivity_power": true }            # config file
```

When set: every hard ceiling becomes **advisory** (printed as `⚡ unleashed (limiter off): would
have blocked — …`, not raised), and an **X/extreme** classification proceeds **without**
`--allow-extreme` — Core runs at full power. The choice is recorded in the run manifest
(`"unleash_initial_productivity_power": true`) so lifting the limiter stays accountable. Default is
**False** — the limiter stays on for everyone else. (It is layered like any config: CLI > env >
config file > default; an unparseable boolean fails closed with a named-key `ConfigError`.) This
removes the safety net deliberately — you own the explosion (disk/inodes/time/cost); on a 2012 box
1M generation is ~17 s, but loose-file output at that size is 1M inodes — pair with the shard sink
([09](09_READER_EXECUTOR_AND_RESULTS.md)).
