<!-- SPDX-License-Identifier: BUSL-1.1 -->
# Sensor selection and fault diagnosis

**What it is.** A sensor-selection study distinguishing fault detection from fault identification.

**Problem shown.** Sensors that detect a fault may still fail to identify which fault occurred.

**How the Combinatorics Framework helps.** Evaluates sensor subsets against declared fault hypotheses. The resulting signatures let independent analysis compare detection, separation, adaptive diagnosis and tolerance of bad readings.

**How correctness is checked.** Independent signature table, acquisition cost and pairwise distance checks modulo observational equivalence.

**What this establishes.** A suite that detects every fault may still confuse two faults. Selection and distance calculations are separate analysis steps.

**Status.** Accepted demonstration; implementation and evidence reviewed. Verified: 3072 PASS; detection/adaptive/separation costs 2/3/4, erasure/error costs 6/7; five replays.

[Detailed explanation](README.md) · [Contract](CONTRACT.md) · [Results](evidence/results.md)
