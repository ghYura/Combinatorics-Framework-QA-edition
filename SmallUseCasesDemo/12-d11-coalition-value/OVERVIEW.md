<!-- SPDX-License-Identifier: BUSL-1.1 -->
# Small-instance coalition valuation

**What it is.** A small coalition-value study showing how modules contribute in combination.

**Problem shown.** Contribution depends on which other modules are present, so standalone scores can miss complementarity.

**How the Combinatorics Framework helps.** Enumerates every contributor subset, including the empty coalition. Complete coalition values allow independent calculation of allocations and interaction effects.

**How correctness is checked.** Independent value calculation and exact rational allocation identities; declare feasible coalitions and the allocation rule before evaluating.

**What this establishes.** The value function and allocation rule are declared assumptions; an allocation is not causal blame.

**Status.** Accepted demonstration; implementation and evidence reviewed. Verified: 64 PASS, exact allocation totaling 32; five replays.

[Detailed explanation](README.md) · [Contract](CONTRACT.md) · [Results](evidence/results.md)
