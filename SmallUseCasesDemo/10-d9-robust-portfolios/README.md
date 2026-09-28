<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D9 — Robust contingency portfolios

**Status:** implemented and verified by one recorded campaign (see Results).

[Contract](CONTRACT.md) · [Frozen predictions](architect-derived.json)

64 mitigation subsets x 16 worlds = 1,024 evaluations; the architecture sizing
probe reports EXACT 1024. Every evaluation predicts PASS for correct arithmetic.
The decision is a portfolio, ranked from all its world costs. Minimax/uniform
winner: cache+quota; calm expected-cost winner: empty portfolio; stress winner:
cache+quota+disk_replica. Exact sensitivity analysis uses 11 mixtures of the
calm and stress joint distributions. The payoff table is illustrative.

Explicit Subsets -> Subsets preserves the empty design. No historic campaign

## Results (the AI implementer, 2026-09-28)

[Results](evidence/results.md). Run `d9_20260928T071508Z` on Framework v6 (no change): fw_final = Reader =
Executor = 1024, **1024 PASS** (verify 24/24). Five replays were byte-identical.
- DESIGN Subsets -> Subsets: Core logged 64 -> 728 -> 64, and 16 empty-design candidates have no `enable()` call.
- Rankings from observed costs: minimax/uniform 110000 (worst 32, mean 41/2), calm 000000 (25/2), stress 110100
  (239/10). The 11-point sensitivity matches the preregistration.

Independent audit.
