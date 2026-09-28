<!-- SPDX-License-Identifier: BUSL-1.1 -->
# SQL ternary-logic partitioning

**What it is.** A SQL-result adapter tested against real PostgreSQL queries over a small fixed dataset.

**Problem shown.** NULL and predicate transformations can expose inconsistent query results without manually listing every expected row.

**How the Combinatorics Framework helps.** Crosses four query shapes, six predicates and three recombination policies. Each candidate runs the base query and its TRUE, FALSE and UNKNOWN partitions.

**How correctness is checked.** Compare multisets for Q versus the UNION ALL of p, NOT p and p IS NULL partitions; add independently known controls.

**What this establishes.** The observed defects are in adapters that omit UNKNOWN rows or remove duplicates; PostgreSQL is not shown defective.

**Status.** Accepted demonstration; implementation and evidence reviewed. Verified: 72 cases, 36 PASS / 36 DOMAIN_FAIL; 288 data SELECTs; 32 tests and five the AI architect live replays passed.

[Detailed explanation](README.md) · [Contract](CONTRACT.md) · [Results](evidence/results.md)
