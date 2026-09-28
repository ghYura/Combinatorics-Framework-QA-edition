<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D8a — Weak orders, stable sorting and pagination

**Status:** implemented and verified by one recorded campaign (see Results).

[Contract](CONTRACT.md) · [Frozen predictions](architect-derived.json)

All 75 weak orders of four identified records, two directions and three
pagination policies produce 450 cases. Derived: 330 PASS / 120 DOMAIN_FAIL.
Stable composite cursors are the positive control; primary-only cursors omit
records at tied boundaries, and changing tie order between offset pages can
duplicate or reorder records. Comparator laws and global pagination obligations
are checked separately. An auxiliary allowed-order proof distinguishes a valid
rank-only tie permutation from this fixture's declared stable order.

Independent local example under [the protocol](../README.md).

## Results (the AI implementer, 2026-09-28)

[Results](evidence/results.md). Run `d8a_20260928T000339Z` on Framework v6 (no change): fw_final = Reader =
Executor = 450, **330 PASS / 120 DOMAIN_FAIL** (stable_cursor 150/0, score_only_cursor 108/42,
alternating_ties 72/78), verify 24/24, five replays byte-identical. All strict orders pass; all 1,340
comparator matrices are lawful. The allowed-order proof covers 150 valid alternatives, 102 of them rejected by
stable_order.

Independent audit.
