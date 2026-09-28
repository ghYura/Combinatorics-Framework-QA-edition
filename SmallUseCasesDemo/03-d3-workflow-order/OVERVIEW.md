<!-- SPDX-License-Identifier: BUSL-1.1 -->
# Workflow order, repetition and sudden actions

**What it is.** An order workflow tested under reordered, repeated and unexpectedly inserted actions.

**Problem shown.** An order-service invariant can fail after an intermediate operation and recover before the final check.

**How the Combinatorics Framework helps.** Generates operation orders, bounded repetitions and optional actions, then executes candidates with intermediate checkpoints. This reveals failures that a final-state check can hide.

**How correctness is checked.** An independent lifecycle model and invariants after every operation, including balances and legal transitions.

**What this establishes.** Checkpoints and the independent lifecycle model supply the oracle; structural coverage alone does not guarantee fault detection.

**Status.** Accepted demonstration; implementation and evidence reviewed. Verified campaigns: A=72 (48 PASS / 24 DOMAIN_FAIL), B=81 (66 PASS / 15 DOMAIN_FAIL), C=1440 (1410 PASS / 30 DOMAIN_FAIL).

[Detailed explanation](README.md) · [Contract](CONTRACT.md)
