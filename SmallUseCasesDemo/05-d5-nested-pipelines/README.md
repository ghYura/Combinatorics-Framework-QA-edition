<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D5 — Higher-order record and query composition

[Phase-A contract](CONTRACT-A.md) · [Frozen predictions](architect-derived-A.json)

A: explicit two-operation ordering, grouped row-by-field Cartesian composition,
and three record-adapter policies; 72 verified cases, 32 PASS / 40 DOMAIN_FAIL.
Phase B implements ordered Group rewrites,
FW_Reuse, equal-length and M:N braces, and nested FW_()/FW_()G with observable
scope/group boundaries. D5 cannot close and D6 cannot start before that scope
is implemented and reviewed.

## Phase A results (the AI implementer, 2026-09-27)

[Results](phase-a/evidence/results.md). Run `d5a_20260927T195647Z` on Framework v6. Core's pass log shows
6 → 12 → 24 OPS rows, and `fw_final` has 72 rows (HEAD, IMPL, OPS, TAIL; no FIELD column). The Reader and
Executor each give 72. Outcomes: **32 PASS / 40 DOMAIN_FAIL** (verify 24/24). Four replays were
byte-identical. `reverse_pair` passes only the 8 commuting cases, where the traces differ but the final
records match.

## Phase B results (the AI implementer, 2026-09-28)

[Results](phase-b/evidence/results.md). Framework v6, unchanged; Core ran with two observation-only
rewrite-diagnostics keys. The ordered E1 rewrites turned `[[op]]` into `[OPEN_X, op, CLOSE]` (each pattern
changed 2 rows; swapping lines 1 and 2 leaves TMP, shown offline). E2's subsets gave 8 → 7 rows, and the
1:1 join used only the 3-code row: JZIP 2×6, JCAT 4×4, ROOT 8×13, with `FW_()` → JCAT and `FW_()G` → ROOT.
- **B1** `d5b1_20260927T231419Z`: 24 candidates, **8 PASS / 16 DOMAIN_FAIL** (verify 26/26).
- **B2** `d5b2_20260927T231532Z`: one 107-code bundle of the eight trees × 3 policies, **1 PASS / 2 DOMAIN_FAIL**
  (verify 27/27).
- **Replays:** 4 extra attempts, all byte-identical.
- **Denominators:** 27 attempts and 48 tree evaluations, reported per campaign.
