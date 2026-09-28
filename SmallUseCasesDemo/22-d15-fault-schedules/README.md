<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D15 — Bounded recovery and replication faults

[Frozen contract](CONTRACT.md) ·
[Predictions](architect-derived.json) · [Sizing plan](planning/plan/plan.json)

Three isolated worker processes and small WAL files demonstrate acknowledged
work lost after a crash, duplicates from fresh retry keys, and duplicate replay.
Native Framework subsets select failed replicas; cuts place faults at exact
operation boundaries. A new local harness owns fault injection and observation.

Three implementations × seven subsets × four cuts × two fault kinds × two
retry policies gives 336 raw rows; excluding all-node partitions leaves 312.
Predicted outcomes are 216 PASS / 96 DOMAIN_FAIL. These are derived and
plan-checked, not executed. The planner retains a [0,336] post-sieve bound.

The oracle checks acknowledged operation multiplicities, accepted records,
replica convergence and a fault-free reference. Real subprocess restart retains
filesystem WALs; partitioning is a deterministic write gate. The example makes

## Results (the AI implementer, 2026-09-28)

[Results](evidence/results.md). Run `d15_20260928T195719Z` on Framework v6 (no change), with `--sieve`.
- **Counts:** plans mandatory EXACT 336, post-sieve/final BOUNDED [0, 336] (the AI architect's graph); native FW_Subsets gives
  the 7 FAIL subsets; the sieve removes exactly the 24 all-node partitions → 312 = Reader = Executor = results_v2.
  1,062 client attempts, 1,224 worker starts, 288 SIGKILLs.
- **Outcomes:** **216 PASS / 96 DOMAIN_FAIL** (verify 29/29 at campaign time, no post-run change): durable 86/18,
  volatile_ack 80/24, replay_twice 50/54. Fresh retry keys duplicate an uncertain write in 18 cases per
  implementation; volatile_ack loses acknowledged work in 6; double replay can leave all replicas agreeing on 222.
- A sandbox preflight (three fault-free controls at 111, two all-node restart cases) passed before the campaign;
  five replays were identical in semantics, digests and WAL evidence.
