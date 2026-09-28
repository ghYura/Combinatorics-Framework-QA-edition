<!-- SPDX-License-Identifier: BUSL-1.1 -->
# Context order and noisy judges

**What it is.** A context-order experiment with a reproducible decision surrogate and noisy judges.

**Problem shown.** A decision system or judge can respond differently when only the order of retrieved context changes.

**How the Combinatorics Framework helps.** Executes a certified catalogue of context orders crossed with local policies. Repeated internal trials and independent judge checks separate order effects from measurement noise.

**How correctness is checked.** Predeclared order-invariance/statistical property, labelled controls for any judge, confidence and attempt population.

**What this establishes.** Coverage certification and statistical assessment are separate from generation. No external-model vulnerability is established.

**Status.** Accepted demonstration; implementation and evidence reviewed. Verified: 54 cases, 49 PASS / 5 DOMAIN_FAIL; 1080 internal trials, 2160 judge readings; five replays and 35 tests passed.

[Detailed explanation](README.md) · [Contract](CONTRACT.md) · [Results](evidence/results.md)
