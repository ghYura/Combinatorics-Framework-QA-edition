<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D11 — Small-instance coalition valuation

**Status:** implemented and verified by one recorded campaign (see Results).

[Contract](CONTRACT.md) · [Frozen predictions](architect-derived.json)

64 coalitions of six modules, including empty, evaluate a fixed additive and
interaction model. The architecture plan reports EXACT 64; all evaluations
predict PASS. Grand value 32 is allocated by the declared Shapley rule:
A=B=29/3, C=D=13/3, E=4, F=0. Weighted marginal, permutation and dividend
certificates agree. The allocation is a model convention, not causal blame.

## Results (the AI implementer, 2026-09-28)

[Results](evidence/results.md). Run `d11_20260928T082423Z` on Framework v6 (no change): fw_final = Reader =
Executor = 64, **64 PASS** (verify 24/24). Five replays were byte-identical.
- COALITION Subsets -> Subsets: Core logged 64 -> 728 -> 64. There is one empty coalition, and all 32 F-only pairs
  stay distinct.
- Shapley from observed values: A=B=29/3, C=D=13/3, E=4, F=0 (sum 32). The weighted marginals (192), permutations
  (720) and dividends agree.

Independent audit.
