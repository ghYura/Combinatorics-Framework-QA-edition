<!-- SPDX-License-Identifier: BUSL-1.1 -->
# Tiny-instance solver verification

**What it is.** A tiny auction-allocation problem comparing exact, greedy and deliberately faulty solvers.

**Problem shown.** A heuristic's objective or a solver transformation can be wrong even when the returned solution looks feasible.

**How the Combinatorics Framework helps.** Crosses four instances with native resource-label permutations, dominated-bid edits and solver policies. Structured variants expose feasibility errors and missed optima.

**How correctness is checked.** Feasibility and exact tiny-instance optimum, objective invariance under symmetry, and a dominated-bid relation only under explicit matching feasibility assumptions.

**What this establishes.** An independent exhaustive oracle solves the tiny instances. The Framework supplies tests, not optimization; greedy gaps are not automatically implementation bugs.

**Status.** Accepted demonstration; implementation and evidence reviewed. Verified: 144 cases, 72 PASS / 72 DOMAIN_FAIL; 432 solver calls; 35 tests and five the AI architect live replays passed.

[Detailed explanation](README.md) · [Contract](CONTRACT.md) · [Results](evidence/results.md)
