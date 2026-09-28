<!-- SPDX-License-Identifier: BUSL-1.1 -->
# Higher-order record and query composition

**What it is.** A small record/query pipeline built from nested fragments and shared operands.

**Problem shown.** Nested record pipelines and query parameters require constructing a structure before testing its behaviour.

**How the Combinatorics Framework helps.** Groups earlier rows, joins them with braces and reuses operands to construct nested candidates. It generates composition structures whose boundaries and ordering affect behavior.

**How correctness is checked.** An independent tree interpreter checks rendered syntax, scope and final record values; intermediate row and decoded-tree identities are retained.

**What this establishes.** A separate tree interpreter checks syntax, scope and values; row counts alone cannot establish correct composition.

**Status.** Accepted demonstration; implementation and evidence reviewed. Verified: A 72 cases (32 PASS / 40 DOMAIN_FAIL), B1 24 (8/16), B2 3 bundles (1/2); pairs are PASS/DOMAIN_FAIL.

[Detailed explanation](README.md)
