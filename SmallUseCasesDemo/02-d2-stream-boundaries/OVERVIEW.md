<!-- SPDX-License-Identifier: BUSL-1.1 -->
# Streaming decoder boundaries and EOF

**What it is.** A streaming text decoder tested with the same bytes split into different chunks.

**Problem shown.** A correct whole-stream decoder can be integrated incorrectly by a chunk adapter.

**How the Combinatorics Framework helps.** Generates legal chunk boundaries and crosses them with decoder strategies and error policies. Every declared segmentation becomes a reproducible test.

**How correctness is checked.** Completed incremental text or rejection must equal the whole-stream reference; literal expected results independently check that reference.

**What this establishes.** Per-chunk decoding and omitted finalization can fail even when whole-input decoding succeeds.

**Status.** Accepted demonstration; implementation and evidence reviewed. Verified: 1152 raw -> 480 valid; 332 PASS / 148 DOMAIN_FAIL.

[Detailed explanation](README.md) · [Contract](CONTRACT.md)
