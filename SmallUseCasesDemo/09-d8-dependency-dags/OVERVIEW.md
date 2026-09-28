<!-- SPDX-License-Identifier: BUSL-1.1 -->
# Incremental DAG evaluation

**What it is.** An incremental dependency evaluator tested after changes to a small directed graph.

**Problem shown.** An incremental dependency engine can retain stale values after an edit or invalidate too little of a graph.

**How the Combinatorics Framework helps.** Crosses bounded edge sets with edits and update policies. Comparing each incremental result with fresh recomputation reveals missed invalidation and stale values.

**How correctness is checked.** Fresh recomputation equals incremental values; adding a redundant edge preserves the set of valid topological orders, not an arbitrary chosen order.

**What this establishes.** The graph population uses a fixed topological order; it is not every possible labelled directed graph.

**Status.** Accepted demonstration; implementation and evidence reviewed. Verified: 768 cases, 604 PASS / 164 DOMAIN_FAIL; five witness replays verified.

[Detailed explanation](README.md) · [Contract](CONTRACT.md) · [Results](evidence/results.md)
