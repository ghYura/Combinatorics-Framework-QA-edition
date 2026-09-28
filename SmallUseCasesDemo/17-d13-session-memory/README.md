<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D13d — Session identity and memory lifetime

**Status:** implemented and verified by one recorded campaign (see Results).

[Contract](CONTRACT.md) · [Frozen predictions](architect-derived.json)

Independent user/session identity partitions, reset cuts and canary placements
exercise four memory adapters. Check both isolation and permitted retention in
user-facing replies and inert draft-tool arguments. Session labels are user-local;
a reset starts a fresh memory epoch without changing identity labels.

Verified: 1152 raw → 960 → 800 valid cases; 718 PASS / 82 DOMAIN_FAIL.
The [plan](planning/plan/plan.json) reports mandatory EXACT 1152 and
post-sieve/final BOUNDED [0,1152], within budgets. The completed campaign matches the frozen predictions.
No external models or real outbound actions are involved.

## Results (the AI implementer, 2026-09-28)

[Results](evidence/results.md). Run `d13d_20260928T120843Z` on Framework v6 (no change), with `--sieve`.
- **Counts:** Core 1152 → sieve 960 → **800** = Reader = Executor; all 25 partition pairs are present. The plan
  stays post-sieve/final BOUNDED [0, 1152], as recorded.
- **Outcomes:** **718 PASS / 82 DOMAIN_FAIL** (verify 27/27 at campaign time). scoped 200/0; user_only 28
  (cross_session); session_only 28 (cross_user); ignores_reset 26 (expired).
- **Leaks:** 88 leaking read checkpoints (30/30/28) and 176 channel occurrences (reply + draft argument).
- Five replays were byte-identical. All tools were inert local stubs.

