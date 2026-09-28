<!-- SPDX-License-Identifier: BUSL-1.1 -->
# Composed untrusted-content boundaries

**What it is.** A local processor tested with composed trusted and untrusted content.

**Problem shown.** Untrusted retrieved material can be mistaken for instructions after nesting or rendering changes.

**How the Combinatorics Framework helps.** Combines carriers, positions and encoding choices into nested contexts using grouping and joins. Canary and stub-action checks reveal lost trust boundaries.

**How correctness is checked.** Canary preservation and forbidden stub-action detectors with clearly identified trusted and untrusted sources.

**What this establishes.** The processor is a controlled local fixture; its failures do not establish a vulnerability in an external language model.

**Status.** Accepted demonstration; implementation and evidence reviewed. Verified: 108 cases, 80 PASS / 28 DOMAIN_FAIL; five replays and 25 tests passed.

[Detailed explanation](README.md) · [Contract](CONTRACT.md) · [Results](evidence/results.md)
