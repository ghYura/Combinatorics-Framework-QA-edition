<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D6 — Bounded and enabled concurrency schedules

[Contract](CONTRACT.md) · [Frozen predictions](architect-derived.json)

Deterministic simulations: two two-step incrementing threads, and a producer /
consumer queue with enabledness. Caps 0/1/2 retain 2/4/6 counter schedules.
Verified: 24 counter cases (18 PASS/6 DOMAIN_FAIL), six queue cases (5/1).
Three infeasible queue schedules are excluded with reference-state evidence.

## Results (the AI implementer, 2026-09-28)

[Results](evidence/results.md). Framework v6, no change; both campaigns sieved.
- **Counter** `d6counter_20260927T233336Z`: 96 → 36 → 24, **18 PASS / 6 DOMAIN_FAIL** (per cap 4/0, 6/2, 8/4),
  verify 25/25. split_rw loses an update on exactly the four interleavings.
- **Queue** `d6queue_20260927T233436Z`: 32 → 12 → 6, **5 / 1** (stale_empty/PCCP), verify 25/25. Three
  infeasible schedules were excluded by reference-state enabledness.
- **Replays:** four, all byte-identical.
