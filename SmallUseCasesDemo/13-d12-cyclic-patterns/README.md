<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D12 — Rotation classes for cyclic designs

**Status:** implemented and verified by one recorded campaign (see Results).

[Contract](CONTRACT.md) · [Frozen predictions](architect-derived.json)

Two sequential campaigns compare 729 labelled six-letter words with 130 rotation
representatives. Both architecture plans report EXACT counts. All evaluations
predict PASS. Directed cyclic transition cost plus a balance penalty yields
best class ABCABC, score 0; its reflected class ACBACB scores 18.

Orbit weights reproduce the labelled-word mean 14, while uniform classes have
mean 942/65. The quotient preserves rotation only; period, seam and reflection
checks explain its scope. Offline certificates justify the reduction.

## Results (the AI implementer, 2026-09-28)

[Results](evidence/results.md). Framework v6 (no change).
- **Words** `d12a_20260928T084349Z`: 729 PASS.
- **Classes** `d12b_20260928T085154Z`: 130 PASS. Both verify 24/24, and the classes results match all 130
  words-campaign representatives.
- Partition: 130 orbits, Burnside [729,3,9,27,9,3]. Means: words 14, classes-uniform 942/65, orbit-weighted 14
  (its histogram equals the words histogram).
- ABCABC 0 vs ACBACB 18 (reflection is not quotiented; 54 self-mirror classes, 38 mirror pairs). 859 original
  attempts in two separate populations.

Independent audit.
