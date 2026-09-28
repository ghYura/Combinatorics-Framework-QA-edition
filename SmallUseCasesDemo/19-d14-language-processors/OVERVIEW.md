<!-- SPDX-License-Identifier: BUSL-1.1 -->
# Compiler and interpreter relations

**What it is.** A tiny compiler/VM fixture tested with structured program variants.

**Problem shown.** A language processor can miscompile a structural program variant even when ordinary examples agree.

**How the Combinatorics Framework helps.** Composes expression fragments and varies independent declaration order and compiler policy. Each candidate also compares a valid dead-code transformation with its original.

**How correctness is checked.** Cross-implementation/optimization output agreement plus unchanged output under a valid transformation, with independently calculated tiny-program controls.

**What this establishes.** Independent expected values catch equal-but-wrong outputs. Results concern the toy language and planted compiler defects.

**Status.** Accepted demonstration; implementation and evidence reviewed. Verified: 432 cases, 316 PASS / 116 DOMAIN_FAIL; 864 VM executions, five replays and 37 tests passed.

[Detailed explanation](README.md) · [Contract](CONTRACT.md) · [Results](evidence/results.md)
