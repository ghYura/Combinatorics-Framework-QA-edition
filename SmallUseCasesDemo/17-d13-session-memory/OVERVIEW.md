<!-- SPDX-License-Identifier: BUSL-1.1 -->
# Session identity and memory lifetime

**What it is.** A memory adapter tested across user/session identities and reset boundaries.

**Problem shown.** Memory keyed too broadly or retained across the wrong boundary can expose one session's marker to another.

**How the Combinatorics Framework helps.** Combines canonical identity partitions, state-lifetime cuts and adapter policies. Canary observations distinguish cross-owner leakage from legitimate retention or reset.

**How correctness is checked.** A canary written under one declared owner must never appear in another owner's output or stub tool trace; permitted same-owner retention is checked too.

**What this establishes.** Identity and lifetime are separate obligations; a reset that removes data is not necessarily a defect.

**Status.** Accepted demonstration; implementation and evidence reviewed. Verified: 1152 -> 960 -> 800; 718 PASS / 82 DOMAIN_FAIL; five replays and 25 tests passed.

[Detailed explanation](README.md) · [Contract](CONTRACT.md) · [Results](evidence/results.md)
