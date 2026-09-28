<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D9 results: robust contingency portfolios

- **Run:** `d9_20260928T071508Z`. **Databases:** `as0927_d9_20260928t071508z` on 5433 and 5432.
  - Retained sizes: main 8,468,159 bytes, results 8,607,423 bytes; the run directory is 13,807,860 bytes.
- **Input:** primary `spec/demo.xlsx` (cell-equivalent to `spec/spec.toml`). No sieve or optional axes.
- **Framework build:** accepted v6, no change.
- **Contract:** v1 `a405d9e2…a059`; predictions `1f015287…e8f0` and `derive.py` unchanged.
- **Envelope:** `generated-default`, one worker, K=1, `-Xmx2g`, budgets 1100/1100/100 MB/2400 s, no
  override. The plans' generic wall-time estimate was 2,048 s, a warning under the 2,400 s limit; the
  Bundle took 615 s.
- **Evidence kind:** Verified/run. `verify.py` passed 24/24, including 31,744 record fields, and gave the
  same 24/24 from `archive/…/inputs`. Replays were 5/5 byte-identical.
- **Payoffs:** illustrative units from the atlas's historical proposal (hash in
  `architect-derived.json`). No historical execution is reused.

## Evaluations and the empty design

HEAD (an empty selection), DESIGN at position 2 (six `enable(module)` fragments), DEMAND (0..3),
DISRUPTION (0..3) and TAIL are crossed by the Framework.

**DESIGN uses the explicit chain `FW_Subsets → FW_Subsets`.** Core's pass log shows:

| DESIGN work | Derived | Observed (Core log) |
|---|---:|---:|
| First pass (`fw_`) | 64 subsets | 64 rows |
| Second pass (per nonempty row, powerset; empty input skipped) | Σ 2^\|S\| = 3⁶ − 1 = 728 emissions | 728 `fw2_` rows before DISTINCT |
| After DISTINCT | 64 | 64 |

The empty design survives because the later pass regenerates the empty subset from nonempty rows.
- **In Core:** `fw_final`'s base row has the empty DESIGN, and 16 decoded rows carry it.
- **In the Reader:** 16 rendered candidates contain no `enable()` call at all.
- **Denominator:** it stays 1,024, not 1,008.

| Stage | Count |
|---|---:|
| Plans (XLSX = TOML graph) | EXACT 1024 (DESIGN EXACT 64) |
| Core `fw_final` (1 × 64 × 4 × 4 × 1) | 1024 |
| Reader / Executor / results_v2 | 1024 / 1024 / 1024; one attempt each |
| Outcomes | **1024 PASS / 0 DOMAIN_FAIL**; zero BROKEN, INFRA_FAIL or TIMEOUT |

**How the evaluations were checked.** Each row is one portfolio in one world. The SUT uses the named
rules, the reference a separately written 16 × 6 benefit table, and the verifier its own arithmetic.
All three agree on every fixed cost, gross loss, six reductions, raw loss, residual and total.
A high modelled loss is not a software defect: every row passes its numerical oracle.

**The final clamp** (replayed `P=111111|D=3|X=1`, `1022_0_0`):
- gross 29, reductions 6 + 7 + 11 + 8 = 32, raw −3, residual 0;
- total cost = fixed 28 + 0 = 28.

24 evaluations have a negative raw loss that the single clamp takes to zero. Buying more cover than
the loss simply pays the fixed costs.

## Ranking whole portfolios from observed costs

`ranking.py` ranked the 64 designs from the OBSERVED `total_cost` of all 16 worlds each.
- **Input guard:** exactly one PASS row per design and world. A missing world, duplicate, unknown ID or
  non-PASS row is refused; the fixture tests show the missing-world and duplicate refusals.
- **Output:** `evidence/d9_…/ranking.json`, with exact fractions as numerator/denominator strings.
- **Verification:** the verifier re-derived every ranking, summary and weight vector and matched both
  `ranking.json` and the preregistration.

| Objective | Winner | Score | Notes |
|---|---|---|---|
| Minimax (worst world, then uniform mean) | **110000** (cache+quota) | worst 32, mean 41/2 | 110001 also has worst 32 but mean 49/2 |
| Uniform expected cost | **110000** | 41/2 | — |
| Calm expected cost | **000000** (nothing) | 25/2 | 110000 ranks 4th (69/5) |
| Stress expected cost | **110100** (cache+quota+disk_replica) | 239/10 | worst 33 |

**Sensitivity.** Mixing the joint distributions (1−α)·calm + α·stress over α = 0, 0.1, …, 1 gives
these winners:

| α | 0 | 0.1 | 0.2 | 0.3 | 0.4 | 0.5 | 0.6 | 0.7 | 0.8 | 0.9 | 1 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Winner | 000000 | 010000 | 010000 | 110000 | 110000 | 110000 | 110000 | 110100 | 110100 | 110100 | 110100 |
| Expected cost | 25/2 | 362/25 | 404/25 | 351/20 | 94/5 | 401/20 | 213/10 | 89/4 | 114/5 | 467/20 | 239/10 |

These are grid samples, not exact continuous breakpoints.

## Why the cheapest row is not the decision

The cheapest single evaluation is `P=000000|D=0|X=0`, costing 4 (replayed, `1_0_0`). But a
portfolio is chosen before the world is known.

| Case (replayed) | Selected | Fixed | Gross | Reductions | Residual | Total |
|---|---|---:|---:|---|---:|---:|
| `P=000000\|D=2\|X=2` (`11_0_0`) | — | 0 | 41 | none | 41 | **41** |
| `P=110000\|D=2\|X=2` (`59_0_0`) | cache, quota | 5 | 41 | 8 + 6 | 27 | **32** |
| `P=110100\|D=2\|X=2` (`187_0_0`) | + disk_replica | 11 | 41 | 8 + 6 + 14 | 13 | **24** |

- **World (2,2)** is the empty design's worst world. There 000000 costs 41, while the minimax winner's
  worst world costs 32. 000000 ranks 27th of 64 under minimax.
- **The same empty portfolio** is the legitimate calm-profile winner (25/2). It pays no fixed cost in
  the likely quiet worlds.
- **The stress winner** buys disk_replica: 6 more fixed cost that removes 14 of loss under disruption 2.

Changing the objective or the weights changes the decision, and no evaluation failed. These are
decision-analysis differences, not SUT defects.

## Limits

These are illustrative costs, six modules, 16 equally enumerated worlds and three stated weight
profiles. The toy assumptions imply no universal best design and no operational recommendation.
The Framework generated and executed the evaluations; design-level aggregation is an offline analysis
over observed rows, not the single-row Analyzer.
