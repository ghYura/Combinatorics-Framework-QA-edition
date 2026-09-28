<!-- SPDX-License-Identifier: BUSL-1.1 -->
# Robust contingency portfolios

**What it is.** A synthetic decision study comparing mitigation portfolios across possible worlds.

**Problem shown.** The best single design/world outcome does not identify a portfolio that performs well across worlds.

**How the Combinatorics Framework helps.** Enumerates every module subset against every declared demand/disruption world. Complete per-design observations support fair minimax and weighted-cost comparisons.

**How correctness is checked.** A declared illustrative cost/loss table, independent recalculation and complete 16-world support per design.

**What this establishes.** Ranking is calculated offline from illustrative costs. The Framework executes evaluations; it does not supply a real investment recommendation.

**Status.** Accepted demonstration; implementation and evidence reviewed. Verified: 1024 PASS, complete portfolio rankings and five replay evaluations.

[Detailed explanation](README.md) · [Contract](CONTRACT.md) · [Results](evidence/results.md)
