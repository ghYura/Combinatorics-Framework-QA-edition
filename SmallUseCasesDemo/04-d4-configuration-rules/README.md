<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D4 — Configuration legality and feature interaction

[Contract](CONTRACT.md) · [Frozen cases](architect-derived.json)

Six legality rules, three adapter policies, two-feature selections and optional
DEBUG. Verified: main 144 mandatory -> 36 -> 66 executions, plus 18 unsieved invalid
controls. Results: main 48 PASS / 18 DOMAIN_FAIL; controls 17 / 1.
Nine legal configurations cover 60 feasible pair obligations. An intentionally
wrong extra bond is evaluated offline to show hidden failures.

## Results (the AI implementer, 2026-09-27)

[Results](evidence/results.md). Main `d4main_20260927T193502Z` on Framework v6: 144 → 36 → 72 → 66,
**48 PASS / 18 DOMAIN_FAIL** (verify 29/29). Controls `d4ctrl_20260927T192718Z`: **17 / 1**
(verify 21/21). Four replays byte-identical. Pairwise suite 60/60 covered; it detects drops_gzip in
6 of 9 rows and never detects ignores_debug_rule. The wrong bond removes 54 candidates and keeps 12
with 0 failures. Framework v5 (exact Reader count under deferred bonds) and v6 (sieve multi-value base
row) were authorized fixes with reproducers. The first main run `d4main_20260927T192553Z` is invalid
(v6 defect) and preserved.
