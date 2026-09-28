<!-- SPDX-License-Identifier: BUSL-1.1 -->
# Numeric reduction-tree sensitivity

**What it is.** A numerical sum evaluated through different binary reduction trees.

**Problem shown.** Changing a parallel reduction tree can change floating-point results without changing the leaves.

**How the Combinatorics Framework helps.** Crosses all declared bracketings with input vectors and evaluation policies. Holding the leaves fixed isolates the effect of tree shape on cancellation and rounding.

**How correctness is checked.** Exact rational reference from the represented inputs, with a separately declared error budget for each numeric policy.

**What this establishes.** Exact arithmetic and declared tolerances determine acceptance. A different floating-point answer is not automatically a defect.

**Status.** Accepted demonstration; implementation and evidence reviewed. Verified: 168 cases, 156 PASS / 12 DOMAIN_FAIL; five witness replays verified.

[Detailed explanation](README.md) · [Contract](CONTRACT.md) · [Results](evidence/results.md)
