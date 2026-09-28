<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D13c — Agent message interleavings

**Status:** implemented and verified by one recorded campaign (see Results).

[Contract](CONTRACT.md) · [Frozen predictions](architect-derived.json)

Two deterministic agents inspect and commit reservations for one resource.
Compare version checking, cached availability and silent owner replacement.
Capacity alone misses the last defect: an earlier reservation promise disappears.
An independent oracle reconstructs outstanding promises from message replies.

Position slots and bonds generate bounded interleavings under independent or
causally ordered negotiation. Verified counts: 288 raw → 108 locally ordered →
81 causally feasible → 54 within caps; 36 PASS / 18 DOMAIN_FAIL.
The [plan](planning/plan/plan.json) reports raw EXACT 288 and post-sieve/final
BOUNDED [0,288]. The completed campaign matches the frozen predictions. No live agents or external actions.

## Results (the AI implementer, 2026-09-28)

[Results](evidence/results.md). Run `d13c_20260928T101424Z` on Framework v6 (no change), with `--sieve`.
- **Counts:** Core 288 → sieve 108 → 81 → **54** = Reader = Executor. The plan stays post-sieve/final
  BOUNDED [0, 288], as recorded.
- **Outcomes:** **36 PASS / 18 DOMAIN_FAIL** (verify 29/29). compare_version 18/0; trust_offer 9 (double
  booking); overwrite_owner 9 (capacity passes, but a promise is silently withdrawn). By cap 9/0, 12/6, 15/12.
- **Causality:** after_A_offer excludes BAAB, BABA and BBAA, because B.inspect waits for A's offer. The bond
  reads only the mode and the first delivery.
- Five replays were byte-identical. All actors were local stubs.

