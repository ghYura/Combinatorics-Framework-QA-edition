<!-- SPDX-License-Identifier: BUSL-1.1 -->
# Bounded and enabled concurrency schedules

**What it is.** Two small concurrent systems tested through deterministic thread interleavings.

**Problem shown.** Interleavings can produce lost updates or stale queue state even when each thread's local order is correct.

**How the Combinatorics Framework helps.** Enumerates step schedules and filters local-order and preemption violations. The harness checks which steps are enabled, making lost-update and stale-queue witnesses replayable.

**How correctness is checked.** A serial reference for the counter and an independent enabled-state transition model for the queue.

**What this establishes.** These are bounded controlled schedules, not a guarantee about arbitrary operating-system timing.

**Status.** Accepted demonstration; implementation and evidence reviewed. Verified: counter 24 valid cases (18 PASS / 6 DOMAIN_FAIL); queue 6 (5 PASS / 1 DOMAIN_FAIL).

[Detailed explanation](README.md) · [Contract](CONTRACT.md) · [Results](evidence/results.md)
