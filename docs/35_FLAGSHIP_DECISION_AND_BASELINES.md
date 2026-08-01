# 35 — Flagship: SUT decision record, baseline comparison, and the executed ladder

> **Status: Phase 05 parts A–H complete and executed, plus a second SUT (§6a).** Every number below was produced by a
> command in this repository against a live PostgreSQL pair on 2026-07-31 and can be re-derived by
> re-running it. Nothing here is a release or publication claim; the open reproducibility gaps,
> provenance blockers and owner gates listed in [§8](#8-what-is-still-open) remain open.

## 1. Part A — why this SUT

Selected: **the record-pipeline executor** (`generator_trunk/engine_demo/record_pipeline.py`),
extended with versioned defects in `generator_trunk/flagship/pipeline_flagship.py`.

| Requirement | This SUT | Rejected alternatives |
|---|---|---|
| Exact or independently cross-checked oracle | ✅ differential (compiled vs. independently written interpreter) + structural bound + exact contract | `automation-scheme-studio` has a **threshold** oracle sharing the SUT's own simulation code — it cannot decide correctness, only acceptance |
| Order-sensitive operations | ✅ `sort` and `scale(k=-1)` do not commute | telemetry/fintech are order-sensitive but their oracles are rule/invariant checks, not exact recomputation |
| Interaction among independent factors | ✅ negation × merge × dedupe | present elsewhere, but without an exact oracle the interaction cannot be attributed |
| Deterministic reset | ✅ no state survives a candidate | `automation-scheme-studio` is float-simulation dependent |
| Bounded execution | ✅ integer corpus, sub-second | fintech needs a started gateway (Tier 3) |
| Versioned intentional defects | ✅ two, below | none of the sibling SUTs carries mutants |
| Source availability | ✅ in-repository, no external checkout | telemetry/fintech/automation need the sibling SUT |

The deciding factor is the oracle. A flagship whose oracle is a threshold comparison can show that a
candidate *failed*, not that the SUT is *wrong* — and a defect-detection comparison needs the second.
The record pipeline is the only canonical SUT with an oracle independent of the code it judges.

**Honest limitation, unchanged:** this SUT is small and in-repository. It demonstrates the *method*
on a tractable domain. It is not evidence about large external systems, and §3 compares construction
methods, not products.

## 2. Part C — oracle and mutants

The oracle is independent by construction: a mutant changes only the **compiled** evaluator;
`reference_eval` — the separately written recursive interpreter — is untouched, so nothing marks its
own homework. Outcomes stay in the canonical taxonomy, and a contract violation the reference *also*
produces is recorded as the pipeline's declared behaviour, **not** as a defect discovery. That
separation is what stops a method from scoring domain rejections as detections.

| Version | Defect | Class |
|---|---|---|
| `correct` | none | control — any detection here is a false positive |
| `single_fault` | `clamp` writes `high - 1` instead of `high` | single-factor: visible whenever a clamp actually clamps |
| `interaction_only` | `dedupe` keys on `abs(x)` instead of `x` | needs negation **and** a merge bringing both signs together **and** a dedupe after them |

An earlier `single_fault` mutant used an off-by-one in the *condition* (`x > high + 1`). On this
corpus no value ever equals `high + 1`, so it was **unreachable** and every method scored a false
MISS. An undetectable mutant measures nothing; it was replaced. Recorded because the first run's
numbers would otherwise have looked like a finding about the methods.
`test_bundle_flagship.py::test_every_mutant_is_reachable` now fails if either mutant becomes
unreachable again.

## 3. Part D — baseline comparison

Identical SUT, oracle, corpus, factors and budget. Every method draws from one factor declaration
and assembles through one builder, so a difference in results is a difference in *which candidates
were chosen*, never in how they were built. Structural axes — brace reducer, `FW_Optional` presence,
nesting — are in the shared factor set, so no baseline is denied structure it could express.

```bash
python3 -c "from generator_trunk.flagship import pipeline_flagship as F; print(F.format_comparison())"
```

### 3.1 At L2 width (8 binary factors, 256 combinations)

| Construction method | Candidates | Execs | Ops | `correct` | `single_fault` | `interaction_only` |
|---|---:|---:|---:|---|---|---|
| isolated-stages (non-composing) | 7 | 21 | 270 | 0 — none | 1/7 found (after 7) | **0/7 MISSED** |
| one-factor-at-a-time (composing) | 9 | 27 | 2 421 | 0 — none | 1/9 found (after 2) | 4/9 found (after 2) |
| manual-regression | 9 | 27 | 2 568 | 0 — none | 4/9 found (after 2) | 3/9 found (after 4) |
| pairwise-covering-array (t=2) | 8 | 24 | 3 024 | 0 — none | 2/8 found (after 3) | 4/8 found (after 2) |
| **3-way-covering-array (t=3)** | 16 | 48 | 6 995 | 0 — none | 8/16 found (after 3) | 6/16 found (after 2) |
| flat-cartesian | 256 | 768 | 111 120 | 0 — none | 128/256 found (after 129) | 120/256 found (after 17) |

*Execs* is candidates × 3 SUT versions; *Ops* is element visits inside the SUT, a machine-independent
execution cost; *(after n)* is how many candidates ran before the first detection.

### 3.2 At L3 width (10 factors, 3 456 combinations)

| Construction method | Candidates | Execs | Ops | `correct` | `single_fault` | `interaction_only` |
|---|---:|---:|---:|---|---|---|
| one-factor-at-a-time (composing) | 14 | 42 | 3 549 | 0 — none | 3/14 found (after 2) | **0/14 MISSED** |
| pairwise-covering-array (t=2) | 14 | 42 | 3 836 | 0 — none | 4/14 found (after 3) | 1/14 found (after 8) |
| **3-way-covering-array (t=3)** | 36 | 108 | 10 053 | 0 — none | 15/36 found (after 3) | 1/36 found (after 8) |
| flat-cartesian | 3 456 | 10 368 | 1 054 314 | 0 — none | 1 792/3 456 found (after 2) | 336/3 456 found (after 81) |

`isolated-stages` composes nothing at either width, so repeating it adds no information.
`manual-regression` is a suite written for the L2 factors; inventing "what an engineer would have
written" for a space this document also designed would be fiction, not a baseline.

### 3.3 The two baselines this study was missing — and what they overturn

The earlier version of this document compared against one-factor-at-a-time, a hand suite, a **2-way**
covering array and exhaustive construction, and concluded that "sampling methods lose interaction
defects". Two baselines were absent, and both are now present. **They substantially weaken that
conclusion, and this section says so before anything else.**

**A 3-way covering array never missed either defect, on either SUT, at either width.** That is not
luck. A t=3 array covers *every* triple of factor levels by construction, so a defect requiring
exactly three conditions is within its reach by design — 6/16, 1/36, 1/16 and 6/42 across the four
configurations. If you know the interaction order you are hunting, buying that strength works, at
2–4× the cost of pairwise and roughly two orders of magnitude below exhaustive.

**Random sampling, given exactly the candidate budget the 2-way array spent, found the interaction
defect most of the time** (50 seeds per configuration, `random_baseline_report`):

| Configuration | budget | `single_fault` | `interaction_only` | false positives |
|---|---:|---|---|---|
| SUT 1 narrow | 8 | 49/50 (98 %) | **50/50 (100 %)** | 0/50 |
| SUT 1 wide | 14 | 50/50 (100 %) | 37/50 (74 %) | 0/50 |
| SUT 2 narrow | 8 | 50/50 (100 %) | 35/50 (70 %) | 0/50 |
| SUT 2 wide | 15 | 50/50 (100 %) | 49/50 (98 %) | 0/50 |

Reported over 50 seeds because a single draw measures luck, not method.

### 3.4 What the comparison actually shows, corrected

**What survives.** *Non-composing* construction cannot find an interaction defect — 0/7 and 0/11 —
and one-factor-at-a-time loses it deterministically as the space widens: **0/14 on both SUTs**. Those
are structural facts about the defect class and they hold everywhere tested. A suite that never
composes, or that varies one factor at a time from a fixed baseline, is not a viable way to find
these defects at any budget.

**What does not survive.** The claim that *sampling* loses interaction defects is now too strong to
defend. Random draws at pairwise cost found them in 70–100 % of seeds, and a 3-way array found them
every time. Ranked by what they actually deliver:

| | guarantee | cost |
|---|---|---|
| exhaustive construction | certain | 256–3 456 candidates |
| **t=3 covering array** | **certain for a 3-way defect, by construction** | 16–42 candidates |
| random at pairwise budget | 70–100 % per draw | 8–15 candidates |
| pairwise (t=2) | found it, by a margin of **one candidate** | 8–15 candidates |
| one-factor-at-a-time | **deterministic miss** at width | 9–14 candidates |
| non-composing | **deterministic miss** always | 7–11 candidates |

The pairwise row is the fragile one: it detects, but on a single candidate, and nothing in a 2-way
construction guarantees that candidate exists. t=3 removes that fragility for a 3-way defect.

**What this means for the Bundle.** On a *flattened* factor space — which is what these tables use,
deliberately, so the baselines can consume it — advanced combinatorial construction does **not**
demonstrate detection power over a t-wise array of adequate strength. It cannot: a t=3 array covers
every triple. The honest remaining argument is about what happens *before* the flattening. Both SUTs
were flattened by hand into factors whose levels index structure — scope kind, nesting, optional
presence, transaction outcome. A t-wise tool needs that flat model as its input; something has to
build it, and for a candidate that is a *tree* rather than a tuple, that is the engine's job, not the
covering array's. This study does not measure that advantage, because flattening was a precondition
for running the baselines at all.

## 4. Part B — the Bundle-native chain

§3 is an in-process study. Part B is the same factor space constructed by the **engine**:
`generator_trunk/flagship/bundle_native_l2/scenario.toml`, executed through the real
Generator → Core → (sieve) → Reader → Executor → persistence → Analyzer chain.

```bash
export BUNDLE_MAIN_DB_PASSWORD=… BUNDLE_RESULTS_DB_PASSWORD=…
python3 generator_trunk/flagship/run_flagship.py run --level l2 --version all
```

| Axis | Realized by | Levels |
|---|---|---|
| module stage | `FW_Group` (`group_replace`) over a `FW_Combi(1)` sheet | 2 |
| ordered motif | **`FW_PermutR(2)`** — ordered, with repetition; `sort` and `scale(-1)` do not commute | 4 |
| side branch | `FW_Combi(1)` operand of brace link 2 | 2 |
| brace reducer | `FW_Combi(1)` operand of brace link 3 (`merge` / `concat`) | 2 |
| nesting | `FW_Combi(1)` operand of brace link 4 (`sequence` / `repeat×2` scope) | 2 |
| finalizer | `FW_Combi(1)` operand of brace link 5 | 2 |
| sudden action | **`FW_Optional`** — Core routes it to `fw_opt`, multiplier ×2 | 2 |

The chain is **five nested brace links**, each consuming the previous result table through `FW_()`:

```
SEQ_RESULT    = FW_(SEQ_OPEN,,GROUPED_STAGE,,REPEATED_MOTIF,,SEQ_CLOSE,,M:N)   →   8 rows
BRANCH_RESULT = FW_(NOP,,FW_(),,SIDE_BRANCH,,NOP,,M:N)                         →  16
PAR_RESULT    = FW_(NOP,,PAR_OPEN,,FW_(),,PAR_CLOSE,,M:N)                      →  32
NEST_RESULT   = FW_(NOP,,NEST_OPEN,,FW_(),,NEST_CLOSE,,M:N)                    →  64
ROOT_RESULT   = FW_(ROOT_OPEN,,FW_(),,FINALIZER,,ROOT_CLOSE,,M:N)              → 128
```

`FW_()` appears in **both** operand positions — as `E1` in links 2 and 5, as `E2` in links 3 and 4.
The `E2` form is what lets an opening marker be *prepended* to the structure accumulated so far,
which is the only way a scope can wrap a result the engine already built.

Executed outcomes, three runs differing only in `FLAGSHIP_SUT_VERSION`:

| Version | PASS | contract violation | **oracle disagreement (detection)** | false positives |
|---|---:|---:|---:|---|
| `correct` | 98 | 158 | 0 | **none** |
| `single_fault` | 50 | 78 | **128** | — |
| `interaction_only` | 50 | 86 | **120** | — |

The detections are identical to the in-process study's 128 and 120 (§3.1) — the same experiment, run
two independent ways.

## 5. Part E — the executed ladder and the practical breakpoint

Each level is the same construction with wider axes. The gate budget is declared **in advance** in
`run_flagship.py` (`GATE_BUDGET_SECONDS = 600`): the breakpoint is where a level stops fitting a
budget somebody set beforehand, not whatever the last run happened to cost.

| Level | What changes | Core rows | Sieve | ×optional | Final candidates | Wall (one version) | ms/candidate |
|---|---|---:|---:|---:|---:|---:|---:|
| **L1** `direct_engine_smoke` | 3 brace links, no `FW_Optional` | 8 | — | ×1 | 8 | 27.8 s | 3 473 |
| **L2** `bundle_native_l2` | 5 brace links, `FW_Optional` | 128 | — | ×2 | 256 | 47.4 s | 185 |
| **L3** `bundle_native_l3` | 3rd module, motif over 3 stages, clamp bounds as axes, 2nd `FW_Optional`, **sieve** | 864 | −216 → 648 | ×4 | 2 592 | 247.9 s | 95.7 |
| **L4** `bundle_native_l4` | **one line**: `FW_PermutR(2)` → `FW_PermutR(3)` | 2 592 | −648 → 1 944 | ×4 | 7 776 | **683.3 s** | 87.9 |

L4 differs from L3 by exactly one verb parameter, so the cost difference between them is attributable
to combinatorial order rather than to any other change.

**The practical breakpoint is between L3 and L4** for a 600 s single-version gate: L3 finishes in 247.9 s, L4 in **683.3 s — over budget**.
Per-candidate cost *falls* with scale (fixed Core+Reader startup amortizes), so the ceiling is
imposed by total candidate count, not by any per-candidate inefficiency. The measured L3→L4 marginal rate is
(683.3 − 247.9) / (7 776 − 2 592) = **84.0 ms per additional candidate**, with ~30 s of fixed
Core+Reader startup. A 600 s budget therefore admits about **6 800 candidates per version on this
host** — between L3 and L4, as executed.

### 5.1 The sieve removed only candidates the domain cannot construct

L3 and L4 declare one constraint: a `clamp` whose low exceeds its high cannot be built. The sieve
deleted 216 of 864 `fw_final` rows at L3 (a quarter, as predicted) and 648 of 2 592 at L4.

That the removal was *harmless* is checked, not asserted. Over the full unsieved L3 space (3 456
assignments), **all 864 removed assignments return construction-failure code 2, and none of the 2 592
kept assignments do** (`test_bundle_flagship.py::TestSieveRemovesOnlyInvalidCandidates`). The
engine-side consequence is exact: flat Cartesian over the unsieved space finds 1 792 and 336
detections; the sieved engine run finds **the same 1 792 and 336** from 25 % fewer executions.

### 5.2 A defect this work found in the sieve

`sieve_fw_final` assumed every declared slot has an `fw_final` column. `FW_Exclude`'d slots — every
brace operand and every intermediate brace target — have none, so the first L3 run died with
`KeyError: 'GROUPED_STAGE'`. The sieve had never been exercised together with a brace chain.

Fixed in `generator_trunk/constraints/sieve.py`: decoding now walks the sheets that are actually
materialized, and a constraint naming a non-materialized sheet raises **before any query runs**
rather than silently matching nothing — a bond that cannot fire is indistinguishable from a satisfied
one, which is the worst possible failure mode for a constraint layer. Regression test:
`TestSieveRejectsUnenforceableBonds`.

## 6. Part F — full-chain reconciliation

```bash
PYTHONPATH=. python3 -m generator_trunk.flagship.reconcile --level l2   # also --level l3, --level l4
```

Every count is read from a **different stage's own `bundle.stage-result/v1` artifact**, so a stage
that miscounts is caught by the next stage disagreeing rather than by the reconciler recomputing what
it wishes were true.

| Stage / source | L2 (each of 3 versions) | L3 (each of 3 versions) | L4 (`correct`) |
|---|---:|---:|---:|
| Core `fw_final` | 128 | 864 | 2 592 |
| Sieve `post_sieve` | — | 648 (−216) | 1 944 (−648) |
| Optional-table contract multiplier | ×2 | ×4 | ×4 |
| **Contract-predicted candidates** | **256** | **2 592** | **7 776** |
| Reader emitted | 256 | 2 592 | 7 776 |
| Reader source files on disk | 256 | 2 592 | 7 776 |
| Executor processed | 256 | 2 592 | 7 776 |
| Executor terminal outcomes summed | 256 | 2 592 | 7 776 |
| Executor persisted (`results_v2`) | 256 | 2 592 | 7 776 |
| Results database rows | 256 | 2 592 | 7 776 |
| Analyzer corpus lines | 256 | 2 592 | 7 776 |

Counts agreeing only proves both sides produced the same *number* of things. The stronger check is
the **multiset of executed measurements** — `(stages, depth, branches, ops, retained, reason,
FW_VAR)` per candidate — compared against an in-process twin that builds the same trees from the same
assignments and runs them through the same parser, executor and oracle:

| Level | Version | Distinct metric tuples (engine) | (twin) | Multisets equal |
|---|---|---:|---:|---|
| L2 | `correct` | 138 | 138 | ✅ |
| L2 | `single_fault` | 122 | 122 | ✅ |
| L2 | `interaction_only` | 122 | 122 | ✅ |
| L3 | `correct` | 830 | 830 | ✅ |
| L3 | `single_fault` | 830 | 830 | ✅ |
| L3 | `interaction_only` | 722 | 722 | ✅ |
| L4 | `correct` | 1 341 | 1 341 | ✅ |

Seven runs, 16 320 candidates, every measurement matched. Two chains agreeing on that many
independently produced integer tuples is not a coincidence that survives a wrong tree.

L4 was executed against `correct` only. The breakpoint it establishes is a question about cost, and
running the mutants would have measured the same wall clock three times for no additional
information — the detection comparison is L2/L3 work.

## 6a. Part I — the second SUT: does the finding reproduce?

Everything above rests on one system under test. A study with one SUT measures
that SUT. This part adds a second, chosen to be unlike the first in every
dimension that could be carrying the result — if the finding were an artefact of
pure function composition, or of differential oracles, it should not survive here.

**SUT 2: a transactional store** (`generator_trunk/engine_demo/txn_store.py`,
mutants in `generator_trunk/flagship/store_flagship.py`).

| Dimension | SUT 1 — record pipeline | SUT 2 — transactional store |
|---|---|---|
| state | none survives an operation | **mutable store; surviving state is the subject** |
| composition | pure function composition | **scoped effects with commit/rollback** |
| oracle family | differential (two evaluators) | **invariant + metamorphic + naive replay + bound** |
| what an operation does | maps a value stream | **mutates a keyed map and its secondary index** |
| failure of interest | wrong output value | **wrong surviving state** |

The engine's half is *unchanged*: the same `FW_Group`, `FW_PermutR(2)`,
`FW_Optional` and five-link nested brace chain with `FW_()` in both operand
positions. What the scopes mean changed from pipeline stages to transactions; the
engine never learned the difference. That is the second thing this part shows.

### 6a.1 The mutants

| Version | Defect | Class | Caught by |
|---|---|---|---|
| `correct` | none | control | — |
| `single_fault` | `delete` drops the key from the map but leaves it in the secondary index | single-factor: any candidate that deletes an existing key | **layer 1**, the coherence invariant |
| `interaction_only` | the copy-on-write savepoint flag is keyed by transaction *depth* instead of *entry*, so a re-entered scope rolls back to a stale snapshot | **three-way**: a repeated scope, a rollback, **and** a write between the two entries | **layer 2**, the metamorphic rollback identity |

The two defects are caught by **different oracle layers**, so neither result rests
on a single check. The three-way claim is not a docstring: `test_bundle_flagship_store.py`
asserts that every detecting candidate has all three conditions **and** that
flipping any one of them destroys the detection. If the defect were a two-way
interaction merely correlated with a third factor, that test fails.

An earlier version of this factor space had no level that called `delete` at all,
so `single_fault` was unreachable and every method scored a false MISS. Same trap
as the record pipeline's first mutant, caught the second time by running the
reachability test first. It is recorded here for the same reason as the first one.

### 6a.2 Baseline comparison — narrow width (8 binary factors, 256 combinations)

| Construction method | Candidates | Execs | Ops | `correct` | `single_fault` | `interaction_only` |
|---|---:|---:|---:|---|---|---|
| isolated-operations (non-composing) | 11 | 33 | 39 | 0 — none | 2/11 found (after 6) | **0/11 MISSED** |
| one-factor-at-a-time (composing) | 9 | 27 | 183 | 0 — none | 1/9 found (after 6) | **0/9 MISSED** |
| manual-regression | 6 | 18 | 129 | 0 — none | 3/6 found (after 2) | **0/6 MISSED** |
| pairwise-covering-array (t=2) | 8 | 24 | 219 | 0 — none | 4/8 found (after 2) | 1/8 found (after 3) |
| **3-way-covering-array (t=3)** | 16 | 48 | 480 | 0 — none | 8/16 found (after 2) | 1/16 found (after 3) |
| flat-cartesian | 256 | 768 | 7 680 | 0 — none | 128/256 found (after 9) | 32/256 found (after 6) |

### 6a.3 Baseline comparison — wide width (5 axes at 3 levels, 1 944 combinations)

| Construction method | Candidates | Execs | Ops | `correct` | `single_fault` | `interaction_only` |
|---|---:|---:|---:|---|---|---|
| one-factor-at-a-time (composing) | 14 | 42 | 273 | 0 — none | 3/14 found (after 3) | **0/14 MISSED** |
| pairwise-covering-array (t=2) | 15 | 45 | 372 | 0 — none | 12/15 found (after 2) | 1/15 found (after 8) |
| **3-way-covering-array (t=3)** | 42 | 126 | 1 149 | 0 — none | 30/42 found (after 2) | 6/42 found (after 5) |
| flat-cartesian | 1 944 | 5 832 | 58 320 | 0 — none | 1 368/1 944 found (after 9) | 324/1 944 found (after 6) |

### 6a.4 What reproduces across the two SUTs — and what does not

| | SUT 1 narrow | SUT 2 narrow | SUT 1 wide | SUT 2 wide |
|---|---|---|---|---|
| non-composing | MISSED | **MISSED** | — | — |
| one-factor-at-a-time | 4/9 found | **0/9 MISSED** | **0/14 MISSED** | **0/14 MISSED** |
| manual regression | 3/9 found | **0/6 MISSED** | — | — |
| pairwise (t=2) | 4/8 | 1/8 | 1/14 | 1/15 |
| **3-way (t=3)** | 6/16 | 1/16 | 1/36 | 6/42 |
| random at t=2 budget | 100 % of seeds | 70 % | 74 % | 98 % |
| flat-cartesian | 120/256 | 32/256 | 336/3 456 | 324/1 944 |

**Reproduces on both SUTs:** non-composing construction misses the interaction defect everywhere, and
one-factor-at-a-time misses it at width. On SUT 2 a hand-written regression suite misses it too, and
OFAT misses it at the *narrow* width already. Two systems sharing no state model, no composition
semantics, no oracle family and no defect mechanism agree on this.

**Does not reproduce as a general claim about "sampling":** a 3-way covering array found the defect
in all four configurations, and random sampling at pairwise cost found it in 70–100 % of seeds. See
§3.3 and §3.4 — the correction applies identically to both SUTs, and it is the reason those sections
were rewritten rather than extended.

### 6a.5 Through the real chain

```bash
python3 generator_trunk/flagship/run_flagship.py run --level s2 --version all
PYTHONPATH=. python3 -m generator_trunk.flagship.reconcile --level s2
```

`bundle_native_s2/scenario.toml` produces `fw_final = 128`, ×2 optional = **256**
candidates — the same count as L2 from the same chain shape, with a different
domain adapter underneath.

| Version | PASS | **detections** | reason | wall |
|---|---:|---:|---|---:|
| `correct` | 256 | **0** | — | 57.2 s |
| `single_fault` | 128 | **128** | `index_incoherent` | 51.0 s |
| `interaction_only` | 224 | **32** | `rollback_leaked` | 56.2 s |

All three runs reconcile exactly — every stage count and the full multiset of
executed measurements, against the in-process twin — and the engine's 128 and 32
are the same 128 and 32 the in-process study reports.

### 6a.6 What the second SUT does **not** settle

**Common authorship is the remaining confound.** Both SUTs, both factor spaces and
all four mutants were designed by the same author in the same work, with one idea
of what an "interaction defect" is. The replication is genuine across *domain,
state model, oracle family and defect mechanism*; it is not independent
replication, and an author who unconsciously builds two instances of one intuition
would see exactly this. The next experiment worth running is a SUT someone else
chose.

Still true: both SUTs are small in-repository Python; "pairwise" and
"one-factor-at-a-time" remain construction methods implemented here, not products;
and four mutants across two SUTs say nothing about concurrency, resource
exhaustion, numerical or protocol-level defects.

## 7. How to reproduce

```bash
# in-process comparison — no database, no network
python3 -c "from generator_trunk.flagship import pipeline_flagship as F; print(F.format_comparison())"
python3 -c "from generator_trunk.flagship import store_flagship as S; print(S.format_comparison())"
python3 -m pytest generator_trunk/test_bundle_flagship.py generator_trunk/test_bundle_flagship_store.py -q

# the engine chain (needs the PostgreSQL pair)
export BUNDLE_MAIN_DB_PASSWORD=… BUNDLE_RESULTS_DB_PASSWORD=…
python3 generator_trunk/flagship/run_flagship.py list
python3 generator_trunk/flagship/run_flagship.py run --level l2 --version all
python3 generator_trunk/flagship/run_flagship.py run --level s2 --version all   # second SUT
python3 generator_trunk/flagship/run_flagship.py run --level l3 --version all
python3 generator_trunk/flagship/run_flagship.py run --level l4 --version correct
PYTHONPATH=. python3 -m generator_trunk.flagship.reconcile --level l2
PYTHONPATH=. python3 -m generator_trunk.flagship.reconcile --level s2
PYTHONPATH=. python3 -m generator_trunk.flagship.reconcile --level l3
PYTHONPATH=. python3 -m generator_trunk.flagship.reconcile --level l4 --versions correct
```

The L1 rung is `generator_trunk/engine_demo/run_direct_engine_smoke.py run --db flagship_l1`. It is
pointed at a **fresh** database on purpose: the pre-existing `engine_demo_smoke` and
`ai_combi_00_smoke` databases were left untouched, as instructed.

Runs are written under `/tmp/fw_work/flagship-<level>-<version>/` and are **not** committed:
generated candidates, databases and corpora stay out of source, per the standing rule.

## 8. What is still open

| Part | Status |
|---|---|
| A — SUT decision record | ✅ done |
| B — Bundle-native scenario through the real chain | ✅ done, L2 and L3/L4 |
| C — oracle and versioned mutants | ✅ done |
| D — baseline comparison, two widths | ✅ done |
| E — scaling ladder and practical breakpoint | ✅ done, L1–L4 executed |
| F — full-chain count and measurement reconciliation | ✅ done, 10 runs exact |
| I — second SUT, different domain and oracle family | ✅ done; the finding reproduces (§6a) |
| H — go/no-go report | ✅ written |

**Historical Phase 05 boundary:** the three reproducibility gaps, eight observed provenance blockers
and eight owner gates were not closed by this study. A later 2026-08-01 uncommitted hardening pass
closed the Action/image/Maven/build-backend pin gaps locally; one Python release-scope decision and
the environment-qualified non-zero provenance gate remain. See
[34_RELEASE_REPRODUCIBILITY.md](34_RELEASE_REPRODUCIBILITY.md) §5 for the current state. The
historical publication-specific owner-gate checklist is intentionally omitted from this private QA
edition. This document does not authorize publication or licence activation.
