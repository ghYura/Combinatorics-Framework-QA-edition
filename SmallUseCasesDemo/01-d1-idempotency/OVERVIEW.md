<!-- SPDX-License-Identifier: BUSL-1.1 -->
# Durable idempotency keys

**What it is.** A retrying service tested under different identity rules and restarts.

**Problem shown.** Separate delivery identity, process lifetime, logical operations and payload equality in a retrying service.

**How the Combinatorics Framework helps.** Enumerates delivery-identity partitions, restart positions and key policies; constraints retain meaningful cases. This exposes retry combinations that ordinary happy-path tests miss.

**How correctness is checked.** Independent operation contract, per-prefix ledger cardinalities and receipt identity/payload checks.

**What this establishes.** A persistent key can still identify the wrong thing. Correctness depends on both logical identity and state lifetime.

**Status.** Accepted demonstration; implementation and evidence reviewed. Verified: 600 raw combinations → 120 valid cases; 77 PASS / 43 DOMAIN_FAIL.

[Detailed explanation](README.md) · [Contract](CONTRACT.md)
