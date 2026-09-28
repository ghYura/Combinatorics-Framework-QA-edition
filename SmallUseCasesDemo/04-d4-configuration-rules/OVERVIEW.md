<!-- SPDX-License-Identifier: BUSL-1.1 -->
# Configuration legality and feature interaction

**What it is.** A configuration adapter tested against feature and dependency rules.

**Problem shown.** Configuration rules mix feature subsets, exactly-one choices, optional presence and dependency ordering.

**How the Combinatorics Framework helps.** Combines feature selections and optional parameters; constraint bonds exclude illegal combinations. Separate controls check that filtering does not remove useful tests or admit invalid ones.

**How correctness is checked.** An independently coded configuration grammar plus a local adapter's acceptance and output invariants.

**What this establishes.** Both generation constraints and the adapter need independent checks. A successful pipeline can otherwise conceal a wrong case population.

**Status.** Accepted demonstration; implementation and evidence reviewed. Verified: main campaign 66 cases (48 PASS / 18 DOMAIN_FAIL); controls 18 (17 PASS / 1 DOMAIN_FAIL). The invalid first run is excluded.

[Detailed explanation](README.md) · [Contract](CONTRACT.md) · [Results](evidence/results.md)
