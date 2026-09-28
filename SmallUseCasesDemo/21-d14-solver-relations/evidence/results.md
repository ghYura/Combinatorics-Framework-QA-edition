<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D14c results: tiny auction solver relations

- **Run:** `d14c_20260928T192507Z`. **Databases:** `as0927_d14c_20260928t192507z` on 5433 and 5432 (owner role
  `postgres`; absent before). Retained: main 8,386,239 B, results 8,861,375 B; run directory 3,197,999 B;
  `evidence/` 2,627,888 B, `archive/` 747,293 B.
- **Input:** primary `spec/demo.xlsx`; cell-, chain- and message-equivalent to `spec/spec.toml`. No rules, no
  companion, no sieve, no optional axis.
- **Framework build:** accepted v6, no change (checkout `be48836` + the 27 inventoried v6 files).
- **Contract:** v1 `9d5d6024…4beb`; predictions `0c78df7c…7310` and `derive.py` `e0fc6dae…4a0` unchanged.
- **Envelope:** `generated-default`, origin generated, container sandbox with `net=none`, one worker, repeat 1,
  `-Xmx2g`, budgets 200/200/150,000,000 B/600 s, no override. The Bundle took 113.2 s (Core 8.8 s, Reader 13.3 s,
  Executor 89.3 s).
- **Evidence kind:** Verified/run. `verify.py` passed 28/28 at campaign time (8,496 record fields, every field of
  all 432 solver results) with no post-run change; the same 28/28 from `archive/…/inputs` (20/20 inputs). The five
  named replays were byte-identical, record digests included.
  - **Before the campaign:** tests ran both DPs against exhaustive enumeration on all 48 distinct inputs, and the
    verifier's parser on a locally composed candidate (including the three-value RELABEL cell).
- **Roles:** the Framework generates the 144 structural cases; the local DP/greedy code is the system under test;
  a separate exhaustive subset oracle measures correctness. No external solver or service.

## Construction and stage counts

| Stage | Count |
|---|---:|
| Plans (XLSX = TOML, one graph `e3e775bd…`) | mandatory, post-sieve, final **EXACT 144**; RELABEL EXACT 6 |
| Core `fw_final` (1 × 3 × 4 × 6 × 2 × 1) | 144 |
| RELABEL rows: the six native FW_Permut orders of `label(0..2);` | 24 rows each |
| Reader / Executor / results_v2 | 144 / 144 / 144; one attempt each, repeat_idx 0 |
| Solver calls (base, relabelled, edited per candidate) | 432 |
| Oracle subset checks (16+16+16 per none, 16+16+32 per dominated) | 8,064 |
| Outcomes | **72 PASS / 72 DOMAIN_FAIL**; zero BROKEN, INFRA_FAIL or TIMEOUT |

- **R comes from the Framework:** each candidate's R is the rendered order of its RELABEL row's three values
  (`label(1);label(0);label(2);` gives R=102); there is no permutation loop or catalogue.
- **Plan graph versus the AI architect's (`f38457f1…`):** edges and per-slot counts are equal; the only difference is the
  RELABEL slot's displayed verb (`shape.toml` shows the placeholder `FW_Combi(1)`, these inputs name the effective
  `FW_Permut()`), as accepted for D14a's DECL. Both chains are `FW_Permut() → FW_Combi(size)`.
- **Budget notes:** non-blocking warnings for 144 rows and candidates (above 100; hard limit 200).

## What each check establishes

| Check | exact_dp | greedy_value | min_only_dp |
|---|---|---|---|
| Structural coverage (4 instances × 6 R × 2 edits) | 48 | 48 | 48 |
| Feasible allocation (all three solves) | 48/48 | 48/48 | **0/48** (all 144 results infeasible) |
| Exact objective (optimal) | 48/48 | 24/48 (tie, overlap) | 0/48 |
| Heuristic gap | 0 | bundle_trap 1, disjoint 6, tie/overlap 0 | undefined (infeasible) |
| solver_relabel / solver_edit hold | 48 / 48 | 48 / 48 | 30 / 48 |
| Verdict PASS / FAIL | **48 / 0** | **24 / 24** | **0 / 48** |

- **Metamorphic agreement is not enough:** 54 failing candidates (all 24 greedy failures and 30 min-only failures)
  satisfy both output relations; only feasibility and exact-optimum checks catch them.
- **Reference relations:** true optima agree across relabelling and across the dominated edit in all 144 cases, as
  the contract's bijection and dominance arguments require (also proven on all 24 inputs before the run).

## Walkthroughs (replayed)

**Tied optima, different selections (both PASS).** `tie` has two optimal allocations of value 10: {b0,b3} and
{b1,b2,b3}.
- exact_dp (`24_0_0`, R=210, dominated) returns [b1,b2,b3] in all three solves (the DP tie rule prefers the
  lexicographically largest ID tuple).
- greedy_value (`72_0_0`) returns [b0,b3] (b0 has the largest value).
- The oracle accepts both, because it compares against every optimal allocation, not the DP's choice.

**Greedy gap (`74_0_0`, disjoint, R=012, dominated → DOMAIN_FAIL).** Greedy takes b3 {0,1,2}:6 first, which blocks
every other bid: value 6. The optimum is b0+b1+b2 = 5+4+3 = 12, so the gap is 6 in all three solves. The allocation
is feasible, and both output relations hold (6 = 6 = 6); only the exact-optimum target fails.

**Planted mask bug: symmetry failure (`125_0_0`, disjoint, R=102, none).** min_only_dp masks b3 {0,1,2} as {0}
only. Base: it selects b1, b2, b3 (reports 13, but b3 overlaps b1 and b2). Relabelled (b0 {1}, b1 {0}): it selects
b0, b2, b3 (reports 14). solver_relabel fails (13 ≠ 14) while the true optimum stays 12.

**Planted mask bug with invariant outputs (`98_0_0`, bundle_trap, R=012, dominated).** min_only_dp selects b0 {0,1},
b2 {1}, b3 {2} (reports 13 > optimum 10; goods 1 used twice) in all three solves. Both output relations hold, so
equal outputs would pass it; the feasibility check fails it. The gap is null, not −3: an infeasible value above the
optimum is not a negative gap.

## Provenance

- **Archive:** all 20 recorded inputs byte for byte (`verify.py` unchanged since the campaign).
- **Checks verified:** frozen hashes; the build record; workbook = run-input copy = Core input workbook; XLSX/TOML
  slots, endings, FW_Seq chains and custom message; the dictionary and the six RELABEL rows; source inlining;
  candidate, observation, component hashes and record digests; the command envelope and JVM options. Feasibility,
  values, optimality, gaps and relations are also recomputed from the recorded bids and selections alone.

## Limits

Three goods of capacity one, four fixed instances of four or five bids, six relabellings, one dominated-bid edit
and two planted solver behaviours (a heuristic and a mask bug). This is synthetic weighted set packing, not an
auction mechanism: no payments, bidder constraints or incentives. No generalisation beyond this finite population.
