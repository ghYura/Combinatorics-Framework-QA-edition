<!-- SPDX-License-Identifier: BUSL-1.1 -->
# Bounded recovery and replication faults

**What it is.** A three-replica append service using real worker processes and small write-ahead logs.

**Problem shown.** Acknowledged work can be lost or duplicated when a component fails at a particular operation boundary.

**How the Combinatorics Framework helps.** Generates failed-node subsets, fault cuts, fault kinds and retry policies; the sieve removes all-node partitions. A separate harness kills/reopens owned workers or gates writes.

**How correctness is checked.** Declared durability/consistency contract, acknowledged-operation multiplicities and convergence after recovery; an independent bounded history checker where needed.

**What this establishes.** The checks distinguish lost acknowledged work, fresh-key duplicates and double replay. This is not a power-loss or general distributed-consistency proof.

**Status.** Accepted demonstration; implementation and evidence reviewed. Verified: 336 raw -> 312 valid; 216 PASS / 96 DOMAIN_FAIL; 31 tests and five the AI architect live replays passed.

[Detailed explanation](README.md) · [Contract](CONTRACT.md) · [Results](evidence/results.md)
