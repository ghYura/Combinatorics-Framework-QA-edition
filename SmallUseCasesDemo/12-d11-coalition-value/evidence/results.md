<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D11 results: coalition value and exact allocation

- **Run:** `d11_20260928T082423Z`. **Databases:** `as0927_d11_20260928t082423z` on 5433 and 5432.
  - Retained sizes: main 8,337,087 bytes, results 8,148,671 bytes; the run directory is 820,588 bytes.
- **Input:** primary `spec/demo.xlsx` (cell-equivalent to `spec/spec.toml`). No sieve, optional axes
  or repeats.
- **Framework build:** accepted v6, no change.
- **Contract:** v1 `1474e64c…f4a6`; predictions `a6a0fa8c…4cf0` and `derive.py` unchanged.
- **Envelope:** `generated-default`, one worker, K=1, `-Xmx2g`, budgets 100/100/50 MB/300 s, no
  override. The Bundle took 62 s.
- **Evidence kind:** Verified/run. `verify.py` passed 24/24, including 1,344 record fields, and gave the
  same 24/24 from `archive/…/inputs`. Replays were 5/5 byte-identical.
- **Model:** a synthetic transferable-value game with the allocation rule fixed in advance. It is not
  causal attribution, measured contribution or a compensation recommendation.

## Evaluations

HEAD (the empty coalition), COALITION at position 2 (`enable("A")`…`enable("F")`) and TAIL are
crossed by the Framework. COALITION uses `FW_Subsets → FW_Subsets`:

| COALITION work | Derived | Observed (Core log) |
|---|---:|---:|
| First pass | 64 | 64 `fw_` rows |
| Second pass (powerset per nonempty row) | 3⁶ − 1 = 728 emissions | 728 `fw2_` rows before DISTINCT |
| After DISTINCT | 64 | 64 |

| Stage | Count |
|---|---:|
| Plans (XLSX = TOML graph) | EXACT 64 (COALITION EXACT 64) |
| Core `fw_final` / Reader / Executor / results_v2 | 64 / 64 / 64 / 64; one attempt each |
| Outcomes | **64 PASS**; zero BROKEN, INFRA_FAIL or TIMEOUT |

- **Distinct identities:** the empty coalition appears exactly once, in the base row, as a rendered
  candidate with no `enable()` call. All 32 pairs of coalitions that differ only by F are present as
  distinct identities, although each pair has equal values.
- **Three routes agree:** the SUT (named rules), the reference (a multilinear term table) and the
  verifier agree on every standalone value, bonus and total.

**Replayed evaluations:**

| Coalition | Candidate | Standalone | Bonuses AB / ACD / BCD | Value |
|---|---|---:|---|---:|
| C=000000 (empty) | `1_0_0` | 0 | 0 / 0 / 0 | 0 |
| C=100000 (A) | `2_0_0` | 2 | 0 / 0 / 0 | 2 |
| C=110000 (A,B) | `4_0_0` | 4 | **12** / 0 / 0 | 16 |
| C=001100 (C,D) | `13_0_0` | 2 | 0 / 0 / 0 | 2 |
| C=101100 (A,C,D) | `14_0_0` | 4 | 0 / **5** / 0 | 9 |

**Context changes contribution.** A alone adds 2. Adding A to B adds 14 (16 − 2). Adding A to C,D
adds 7 (9 − 2).

## Shapley allocation (offline, from observed values; `allocation.json`)

**Input guard:** one PASS row per coalition, with no inference and no merging of equal values. The
fixture tests show it refusing a missing row and a duplicate, and show an altered value being
detected.

| | A | B | C | D | E | F | Sum |
|---|---|---|---|---|---|---|---|
| **Shapley** | **29/3** | **29/3** | **13/3** | **13/3** | **4** | **0** | **32** |
| Standalone | 2 | 2 | 1 | 1 | 4 | 0 | 10 |
| Leave-one-out from the grand coalition | 19 | 19 | 11 | 11 | 4 | 0 | 64 |
| Unweighted mean of 32 marginals (a different rule) | 37/4 | 37/4 | 7/2 | 7/2 | 4 | 0 | 59/2 |

Three certificates agree exactly:

1. **Weighted marginals:** 192 terms (32 per player), each with coalition, integer difference and
   weight |S|!(5−|S|)!/6!. Each player's 32 weights sum to 1. The weighting comes from uniformly
   weighted player orders, not a uniform average over subsets.
2. **Permutations:** all 720 orders, 4,320 sequential marginals, each order telescoping to 32. Player
   sums are 6960, 6960, 3120, 3120, 2880 and 0, divided by 720. This is offline arithmetic on the 64
   measured values, not extra executions.
3. **Dividends by subset inversion:** the only nonzero dividends are A=2, B=2, C=1, D=1, E=4, AB=12,
   ACD=5 and BCD=5. Splitting each equally among its members gives:
   - A = 2 + 12/2 + 5/3 = 29/3;
   - C = 1 + 5/3 + 5/3 = 13/3;
   - E = 4;
   - F = 0.

**Properties checked over all contexts:**
- **Efficiency:** the shares sum to 32 = v(ABCDEF).
- **Symmetry:** A and B, and C and D, have equal marginals in every context that excludes both of the
  pair.
- **E is an additive dummy:** its marginal is exactly 4 in all 32 contexts.
- **F is a null player:** its marginal is 0 in all 32 contexts.

**Why the other scores differ.**
- **Standalone** values miss the interactions. E has the largest standalone value (4), but A and B
  receive the largest shares, because they carry the AB bonus and a part of ACD/BCD.
- **Leave-one-out** differences count each shared bonus once for every member whose removal destroys
  it, so they sum to 64, not 32.
- **The unweighted mean of marginals** is a different value rule (sum 59/2). It is not Shapley, and it
  is not an arithmetic error either: the contract simply fixes Shapley as the allocation convention.

## Limits

This covers one synthetic value function with six players and three interaction terms. The
allocation is a convention fixed before the run, not blame or causal credit. All allocation work is
offline arithmetic over the 64 observed values; the Framework evaluated the coalitions.
