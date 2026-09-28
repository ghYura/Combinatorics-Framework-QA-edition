<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D14c — Tiny-instance solver verification

[Frozen contract](CONTRACT.md) ·
[Predictions](architect-derived.json) · [Sizing plan](planning/plan/plan.json)

A tiny auction allocation problem demonstrates solver feasibility, exact
objectives, tied optima, heuristic gaps and metamorphic relations. Three solver
policies cross four instances, six native Framework relabellings and two edits:
144 cases, each running three independent solves. The prediction is 72 PASS /
72 DOMAIN_FAIL; these counts are derived and plan-checked, not run evidence.

The Framework generates structured tests. A local DP is the SUT; a separate
exhaustive subset oracle measures correctness. Neither role is attributed to
the Framework. The smallest-item mutant can return impossible allocations;
the greedy heuristic can remain feasible yet miss the optimum. Equal outputs
under transformations alone do not establish correctness.

Read CONTRACT.md for implementation, record schema, proofs, budgets and review
EEST-named Markdown files here under [the protocol](../README.md).

## Results (the AI implementer, 2026-09-28)

[Results](evidence/results.md). Run `d14c_20260928T192507Z` on Framework v6 (no change), no sieve.
- **Counts:** plans EXACT 144 (XLSX = TOML); Core 144 = Reader = Executor = results_v2; the six native FW_Permut
  RELABEL orders drive 24 rows each; 432 solver calls; 8,064 oracle subset checks.
- **Outcomes:** **72 PASS / 72 DOMAIN_FAIL** (verify 28/28 at campaign time, no post-run change). exact_dp 48/0;
  greedy_value 24/24 (feasible, gaps 1 and 6); min_only_dp 0/48 (every result infeasible). 54 failures keep both
  output relations, so equal outputs alone would miss them.
- Five replays were byte-identical, record digests included. Local solvers and oracle only.
