<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D10 — Sensor selection and fault diagnosis

**Status:** implemented and verified by one recorded campaign (see Results).

[Contract](CONTRACT.md) · [Frozen predictions](architect-derived.json)

Eight binary sensors, all 256 subsets and 12 fault hypotheses give 3,072
plan-checked evaluations. Six fault pairs are observationally indistinguishable;
with the healthy reference, diagnosis distinguishes seven classes.

Derived minimum costs: detection 2, adaptive diagnosis 3, fixed identification 4,
one-erasure tolerance 6, one-wrong-reading tolerance 7. The Framework collects
signatures; offline enumeration, dynamic programming and decoding proofs certify
the diagnostic designs. Every correct sensor evaluation predicts PASS.

## Results (the AI implementer, 2026-09-28)

[Results](evidence/results.md). Run `d10_20260928T073948Z` on Framework v6 (no change): fw_final = Reader =
Executor = 3072, **3072 PASS** (verify 24/24). Five replays were byte-identical.
- SENSORS Subsets -> Subsets: Core logged 256 -> 6560 -> 256, with 12 empty-mask and 12 full-mask cases.
- Fixed-suite costs from the observed matrix: detection 2, separation 4, erasure 6, error 7. Adaptive worst case 3
  (127 beliefs). Noise controls 49/56 all decode to the true class.

Independent audit.
