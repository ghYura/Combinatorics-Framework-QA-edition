<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D8b — Incremental DAG evaluation

**Status:** implemented and verified by one recorded campaign (see Results).

[Contract](CONTRACT.md) · [Frozen predictions](architect-derived.json)

64 forward-edge subsets × four input edits × three cache-update policies = 768
cases. Derived: 604 PASS / 164 DOMAIN_FAIL. Correct transitive invalidation with
forward evaluation is compared with direct-neighbour invalidation and reverse
recomputation. Exact path counts independently establish every expected delta.
An auxiliary proof covers all 31 redundant-edge additions and distinguishes
unchanged valid topological-order sets from changed numerical formulas.

Independent local example under [the protocol](../README.md).

## Results (the AI implementer, 2026-09-28)

[Results](evidence/results.md). Run `d8b_20260928T002104Z` on Framework v6 (no change): fw_final = Reader =
Executor = 768, **604 PASS / 164 DOMAIN_FAIL** (closure_forward 256/0, direct_only 228/28, closure_reverse 120/136),
verify 23/23, five replays byte-identical.
- direct_only fails through missing invalidation. In 2 of those cases a dirty D also reads the missed C.
- closure_reverse fails through stale parent reads with a complete dirty set.
- Topological-order proof: 315 pairs; 31 redundant additions preserve the order sets.

Independent audit.
