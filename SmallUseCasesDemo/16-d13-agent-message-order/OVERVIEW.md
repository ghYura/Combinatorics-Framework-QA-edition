<!-- SPDX-License-Identifier: BUSL-1.1 -->
# Agent message interleavings

**What it is.** A deterministic simulation of agents sharing a resource through messages.

**Problem shown.** Two agents' individually valid messages can conflict when delivery order changes shared-resource state.

**How the Combinatorics Framework helps.** Enumerates delivery orders subject to local order, causal readiness and a preemption bound. This makes conflicting reservations and stale decisions reproducible.

**How correctness is checked.** A local shared-resource invariant, causal message checks and an independent deterministic transition model.

**What this establishes.** Message contents are fixed; changing live-agent behavior would define a different test population.

**Status.** Accepted demonstration; implementation and evidence reviewed. Verified: 288 -> 108 -> 81 -> 54; 36 PASS / 18 DOMAIN_FAIL; five replays and 31 tests passed.

[Detailed explanation](README.md) · [Contract](CONTRACT.md) · [Results](evidence/results.md)
