<!-- SPDX-License-Identifier: BUSL-1.1 -->
# Weak orders, stable sorting and pagination

**What it is.** Sorting and pagination over identified records whose values can tie.

**Problem shown.** Tied records admit multiple valid orders, while unstable tie handling can duplicate or omit records across pages.

**How the Combinatorics Framework helps.** Enumerates weak orders, directions and policies, systematically exercising equality groups. This exposes missing or repeated records across pages without assuming arbitrary tie-breaking.

**How correctness is checked.** Comparator laws, multiset preservation, valid ordering and declared within-tie stability; compare allowed results unless tie-breaking is fixed.

**What this establishes.** The oracle permits valid tied orders unless the contract explicitly requires stability.

**Status.** Accepted demonstration; implementation and evidence reviewed. Verified: 450 cases, 330 PASS / 120 DOMAIN_FAIL; five witness replays verified.

[Detailed explanation](README.md) · [Contract](CONTRACT.md) · [Results](evidence/results.md)
