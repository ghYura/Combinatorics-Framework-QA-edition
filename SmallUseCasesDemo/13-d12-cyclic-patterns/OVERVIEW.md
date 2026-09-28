<!-- SPDX-License-Identifier: BUSL-1.1 -->
# Rotation classes for cyclic designs

**What it is.** A cyclic-pattern study separating labelled words from rotation-equivalent designs.

**Problem shown.** Rotating a cyclic motif can duplicate the same design many times and distort ranking.

**How the Combinatorics Framework helps.** Enumerates six-position patterns and executes a second catalogue of canonical representatives. Independent orbit analysis prevents repeated rotations from silently distorting summaries.

**How correctness is checked.** Independent orbit partition, rotation-invariant objective and orbit-size-weighted versus class-uniform summaries.

**What this establishes.** Rotation equivalence does not include reflection. Uniform words and uniform rotation classes have different weights.

**Status.** Accepted demonstration; implementation and evidence reviewed. Verified: 729 words and 130 classes, 859 PASS; weighted mean 14, class-uniform mean 942/65; five replays.

[Detailed explanation](README.md) · [Contract](CONTRACT.md) · [Results](evidence/results.md)
