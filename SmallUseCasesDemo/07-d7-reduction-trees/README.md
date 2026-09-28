<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D7 — Numeric reduction-tree sensitivity

**Status:** implemented and verified by one recorded campaign (see Results).

[Contract](CONTRACT.md) · [Frozen predictions](architect-derived.json)

Fourteen ordered-leaf bracketings, four binary64 vectors and three policies:
tree_binary64, flat_fsum and tree_rational. Exact represented-input references
and rational error budgets distinguish acceptable rounding from failed limits.
Derived: 168 cases, 156 PASS/12 DOMAIN_FAIL.

## Results (the AI implementer, 2026-09-28)

[Results](evidence/results.md). Run `d7_20260927T234722Z` on Framework v6 (no change): fw_final = Reader =
Executor = 168, **156 PASS / 12 DOMAIN_FAIL** (binary64: cancellation 5/14, swamped 7/14 fail), verify 24/24,
five replays byte-identical. Exact rational references of the represented inputs; nonzero errors within budget
pass (35 cases); decimal_inputs' represented sum is 3/2 + 2^-55.

Independent audit.
