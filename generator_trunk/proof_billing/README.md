# proof_billing — can combinatorics find what classic testing cannot?

An empirical study run on 2026-08-29 against the full Bundle chain
(fwgen → Core Java+PG → Reader → Python Executor → results DB).

Report: https://claude.ai/code/artifact/be7fe9f6-673c-4d57-b721-4f63bf2315cb

**Assessment of the framework itself:** [ASSESSMENT.md](ASSESSMENT.md) (short) ·
[ASSESSMENT_FULL.md](ASSESSMENT_FULL.md) (comprehensive — maturity, limits, other application areas).

## Method

1. **`sut/billing_core.py`** — a subscription billing engine written to spec in one pass,
   reproducing failure modes seen in real billing systems. Hashed and made read-only
   (`sut/FROZEN.sha256`) *before* the first campaign. Every result is against that artifact.
2. **`classic/test_classic.py`** — the baseline: equivalence partitioning, boundary value
   analysis, 0-switch and 1-switch state-transition coverage, nine use-case scenarios, and an
   IPOG pairwise array over a 13-parameter model whose 662-pair coverage is *verified*, not assumed.
3. **`classic/exhaustive_classic.py`** — the decisive control. Runs the *entire* classic model
   (663,552 cases; 525,312 legal) to separate a sampling gap from a modelling gap.
4. **`c*/`** — thirteen combinatorial campaigns, each answering "what can I combine that nobody
   combines?" 11,648 candidates in total.
5. **`verify_findings.py`** — every finding reduced by hand to a minimal reproducer plus its cause.

## Result in one line

Pairwise (24 cases) and the exhausted model (525,312 cases) reach **the same two invariants**.
Seven further defects lie outside what that model can express, and survive a build whose
classic suite is green at 87/87.

## Campaigns

| dir | the unusual combination | verbs | candidates |
|---|---|---|---|
| `c0_smoke` | chain smoke test | `FW_Permut` | 18 |
| `c1_lifecycle` | lifecycle verbs with their inverses, non-adjacent, repeating | `FW_PermutR(4)` | 256 |
| `c2_money` | all orders × every subset of 3 sudden events × probe after every step | `FW_Permut`, `FW_Optional`×3 | 576 |
| `c3_repeat` | the same operation more than once | `FW_PermutR(4)` | 768 |
| `c4_concurrent` | concurrency vs a serialized golden computed by the Bootstrap | `FW_Combi`, `FW_Optional` | 360 |
| `c5_flagship` | config × order × mid-flight config mutation × sudden events | `FW_Permut`, `FW_Subsets`, `FW_Optional`×2 | 6,912 |
| `c6_brace` | two accounts crossed by the brace, differential vs isolated replay | `FW_(…M:N)` | 9 |
| `c7_race` | interleaving as an axis, incl. the CPython switch interval | `FW_Combi`, `FW_Optional` | 144 |
| `c8_degenerate` | arguments nobody bothers to pass | `FW_Permut`, `FW_Subsets` | 288 |
| `c9_phases` | functional × stress × chaos in one space | `FW_Permut`, `FW_Optional`×2 | 432 |
| `c10_transport` | transport pathology × functional scenario | `FW_Permut`, `FW_Subsets` | 288 |
| `c11_fault` | transient fault inside an operation × the retry that follows | `FW_Permut`, `FW_Combi` | 72 |
| `c12_order_bonds` / `c12c_…` | ordering × sieve bonds — sequence encoded one slot per step | `FW_Combi` + bonds | 1,453 |

`c4_concurrent/runme.py` and `c7_race/runme.py` are `RunMeFirstOnce` prologues: they gate the run
on the SUT's sha256, pre-load a multi-threaded harness, and compute the serialized golden once.

## Findings

| id | defect | reached by classic? |
|---|---|---|
| F9 | a forged or corrupted webhook id raises a real charge | no — model can only deliver a valid id |
| F1 | re-applying a coupon resets its lifetime allowance | no — needs one op twice |
| F2 | the same invoice refunded twice exceeds it | no — needs one op twice |
| F5 | the invariant breaks mid-run and heals before the end | no — all classic oracles assert at the end |
| F6 | a process restart resets the invoice counter → duplicate numbers | no — no chaos axis |
| F7 | "changing" to the plan already active mints credit, repeatably | no — `do_change` has no "same" value |
| F8 | subscribing on an active account bills the cycle twice | no — model calls `subscribe` once |
| F10 | a redelivery re-executes a refund from *any* distance, not just the next step | no — needs a sequence long enough to separate them |
| F3 | webhook redelivery re-executes a refund | **yes** |
| F4 | mid-cycle upgrade credits at the new plan's price | **yes** |

Clean results are part of the record: the lifecycle machine is sound across all 256 sequences
(C1), concurrency produced no divergence or lost update (C4, C7), and operations proved atomic
under transient fault plus retry across all 120 combinations (C11).

C11 was run twice: once against the frozen SUT, where a dominant defect saturated it at 100%, and
once against a locally patched build to see past that saturation. Only the first is shipped — the
patched build was a transient experiment, not an artifact, and a spec pointing at it would not run
for anyone else. The brace joined two
independently computed result tables (3 pairs ⋈ 3 pairs = 9 rows, confirming operands are prior
results rather than raw sheets) and found no cross-instance interference (C6).

C6 is also the one campaign the control plane refused to start: a brace's output is not
statically estimable, so the planner classified it `X (extreme)` and blocked until
`--allow-extreme` and `--override-budget` were given with a reason. That is the documented
behaviour of `estimate_core_combos`, and it is the gate working, not a defect.

## Ordering × bonds (C12)

A positional gate resolves `pos` per materialized **axis** (`sieve.py:743-752`), and two placements
sharing a position are never paired (`:495`). So a single `FW_Permut` sheet's internal order is
invisible to a bond — to combine ordering with bonds, encode the sequence as **one slot per step**.

C12 runs the same 5⁴ = 625 space three times, changing only the bonds, using them as *hypotheses*
("this shape is already explained") so the residue is what the model does not yet account for:

| run | the bond's hypothesis | candidates | failing | residue |
|---|---|---|---|---|
| `c12` (no `--sieve`) | none | 625 | 169 (27.0%) | dominated by two known shapes |
| `c12` (`--sieve`) | refund *immediately followed by* replay | 464 | 21 (4.5%) | **20 × F10 — the hypothesis was wrong** |
| `c12c` (`--sieve`) | refund *co-occurring at any distance* with replay | 364 | 1 (0.3%) | **1 × F1, the only unexplained defect** |

Removal counts were predicted in closed form and by driving `sieve.row_violations` offline before
each run; both agreed with what the chain reported (161→464, then 261→364).

## Running these specs

Every campaign resolves its system under test as
`os.environ.get("PROOF_SUT_ROOT", "<this dir>/sut")`, so run `bundle_run.py` from
`generator_trunk` (as the commands below do) and the relative default resolves. From anywhere else,
point `PROOF_SUT_ROOT` at the `sut/` directory:

```bash
export PROOF_SUT_ROOT=/abs/path/to/generator_trunk/proof_billing/sut
```

## Run it

```bash
# baseline, then the exhaustive control
cd classic && python3 test_classic.py && python3 exhaustive_classic.py

# any campaign, full chain
cd ../..                       # generator_trunk
python3 bundle_run.py proof_billing/c10_transport --db bc10 --lang py \
  --main-db-user postgres --main-db-password pass \
  --results-db-user postgres --results-db-password pass \
  --execution-policy-profile trusted-local \
  --candidate-origin reviewed-checked-in \
  --acknowledge-trusted-local "reviewed spec fragments vs frozen SUT"

# dissect a run: witnesses, minimal reproducers, axis enrichment
python3 proof_billing/analyze_run.py /tmp/fw_work/bc10

# every finding, reduced
python3 proof_billing/verify_findings.py
```

`trusted-local` is used because every candidate is a concatenation of fragments written into a
checked-in spec, run against a hash-frozen local SUT — which is what `reviewed-checked-in` means.
The framework refuses `--candidate-origin generated` under that profile, correctly.

## Scope

One SUT, one author's classic suite, one afternoon. What is shown is a *structural* property —
a parameter model without order, multiplicity or interleaving cannot express certain test cases,
demonstrated by exhausting that model. Not a general yield figure. The concurrency campaigns
tested a component whose docstring declares itself single-threaded, so their clean result speaks
to deployment risk rather than to a spec violation.
