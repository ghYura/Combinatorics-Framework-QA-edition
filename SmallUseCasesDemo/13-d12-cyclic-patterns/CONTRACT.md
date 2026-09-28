<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D12 contract v1 — cyclic designs and rotation classes

Frozen before implementation; apply ../README.md and G1–G7. Question:
rank oriented cyclic motifs and reduce equivalent evaluations while preserving
the declared population. All length-six words over A,B,C are admissible. Two
words are equivalent exactly when related by rotation. Reflection and alphabet
renaming are NOT equivalences. The cost model is illustrative, not field data.

## Objective and observations

Let counts be the numbers of A,B,C. Balance penalty is sum((count-2)^2).
Transition cost sums all SIX directed adjacent edges, including last -> first,
using this matrix (row=source, column=destination, order A,B,C):

| | A | B | C |
|---|---:|---:|---:|
| A | 2 | 0 | 3 |
| B | 3 | 2 | 0 |
| C | 0 | 3 | 2 |

Minimize total_cost = transition_cost + balance_penalty. The score is rotation
invariant but need not be reflection invariant. The canonical representative is
the lexicographically smallest DISTINCT rotation. Orbit size is the number of
distinct rotations, equal here to the least positive shift returning the word
(its period); stabilizer size is 6/orbit_size.

Case identity `W=six_letters`, scoped to its campaign. Record campaign, word,
counts, edge_counts (3×3), edge_costs (six, starting at position 0), transition_cost,
balance_penalty, total_cost, representative, orbit_size, period, stabilizer_size,
oracle agreement, verdict and source/candidate identity. Follow frozen field
meanings. An edge-cost list rotates with the word; aggregate score invariance
does not imply that list is identical at every starting position.

Separate the SUT's cyclic evaluation from an independent reference using directed
pair counts and the matrix dot product. Neither reads frozen results. Correct
high-cost designs PASS; computation disagreement is DOMAIN_FAIL. Malformed words,
missing results or exceptions are unexpected setup/infrastructure failures.

## Two bounded campaigns, sequentially

Build primary XLSX and equivalent TOML under spec/words and spec/classes:

| Campaign | Framework construction | Raw Core = Reader = Executor original attempts |
|---|---|---:|
| words | HEAD, six mandatory position slots P0..P5 (three letter choices each), TAIL | 729 |
| classes | HEAD, PATTERN catalogue of 130 canonical representatives, TAIL | 130 |

Use explicit `Combi(1)->Combi(size)` for every slot. No optional axes, sieve or
repeats. Do not use auto-promoted PermutR(6). Both actual-input plans must be
EXACT for their population. In words, fragments assign a letter to an explicit
position; in classes, a fragment sets the complete pattern. Retain all six
positions and verify the emitted word against the decoded Core identity.

The builder enumerates/canonicalizes 729 words OFFLINE for the catalogue. The
Framework does not natively generate rotation classes, and classes campaign
Core support is 130, not 729 filtered afterward. Run words once, verify it,
then run classes once and verify agreement at each representative. All outcomes
predict PASS: 729 and 130 separately, **859 total original attempts**. K=1 in
both runs; these two populations must not be merged into one sampling denominator.

The representative campaign demonstrates replacing 729 equivalent evaluations
by 130 in a future use of this model. This demonstration actually executes both.
Separate sources/runtime/builder/runner/analysis/verifier/replay; candidates must
be self-contained and not import another example. Use the second mandatory slot
only as the legacy verdict carrier, not causal attribution.

## Partition certificate and population weights

Save each representative and all distinct member words. Independently verify
disjoint complete coverage of 729 words, 130 classes, canonical minima and each
period/stabilizer. Burnside fixed-word counts for shifts 0..5 are
[729,3,9,27,9,3], whose sum divided by 6 is 130. Class counts by orbit size are
size 1:3, size 2:3, size 3:8, size 6:116. Thus class sizes sum to 729, not 780.
Do not blindly weight every representative by six.

Analyze observed costs in three explicitly labelled populations:

- Uniform labelled words: all 729 original positions distinguished.
- Uniform rotation classes: each of 130 designs weighted once.
- Orbit-weighted classes: representative weight equals its distinct orbit size.

Save complete cost histograms and exact means. Frozen means: words 14,
classes-uniform 942/65, classes-weighted 14. The orbit-weighted histogram must
equal the labelled-word histogram exactly. Neither population convention is
inherently wrong; replacing one with the other changes the question. Serialize
fractions as numerator/denominator decimal strings, not rounded floats.

Rank classes by (total_cost, representative), retaining all primary-score ties.
The unique best class is ABCABC, score 0, with three labelled words ABCABC,
BCABCA,CABCAB. Report its class mass 1/130 versus word mass 3/729=1/243.
AAAAAA has size 1, ABABAB size 2, ABCABC size 3, AAAAAB size 6.

Save the reflected-representative map: 54 classes map to themselves and 38
distinct mirror pairs remain separate. ABCABC and ACBACB are different classes
with scores 0 and 18. Accidentally quotienting reflection would leave only 92
classes and change the declared space. No reflection invariance is asserted.

## Review and practical demonstration

From observed rows, require exactly one PASS per expected word in each campaign;
reject missing, duplicate or unknown identities. Check every words-campaign
orbit has a constant aggregate cost; match all 130 classes-campaign results to
their words-campaign representatives. Recompute all three weighted summaries.

The offline verifier must not import SUT/reference/runtime/analysis/derive.py or
execute candidate sources. Independently enumerate identities and orbits, compute
scores, partition certificates and population summaries; compare frozen data.
Verify source inlining/hashes, XLSX/TOML/Core-input equivalence, all stage counts
and one original attempt per identity. Focused tests must detect missing/duplicate
data, altered scores and a scorer that omits the wraparound edge.

Illustrate the seam with AAAAAB and BAAAAA: both total 25. Omitting the closing
edge incorrectly gives 22 and 25, respectively, exposing dependence on a chosen
starting position. Explain directed reflection and different orbit weights using
the examples above. A small histogram/table suffices; no external visual asset.

Replay exactly these five evaluations, separately from original attempts:

- words: W=AAAAAB — total 25.
- words: W=BAAAAA — total 25, same orbit.
- words: W=ABCABC — total 0.
- words: W=ACBACB — total 18, reflected but distinct.
- classes: W=ABCABC — total 0, matches its words evaluation.

Preserve contract, derive.py and architect-derived.json. Archive commands,
source/input/build hashes, both plans per campaign, Core tables/dictionary, all
sources/observations, partition and cross-campaign analysis, verifier output and
concise results.md. Use fresh as0927_d12a_* (words) and as0927_d12b_* (classes)
databases on both ports. generated-default, one worker, K=1, JVM <=2 GB.
Words budgets: mandatory/final 800, disk 100000000 bytes, wall 1800 seconds.
Classes budgets: mandatory/final 150, disk 50000000 bytes, wall 400 seconds.
Preflight disk/ownership before each run and record retained sizes. Preserve
databases and prior artifacts. Focused DB-free tests only; no broad/live-test sweep,
full fixture, external calls, cleanup, commit or push. Necessary evidenced fixes
remain authorized; otherwise preserve v6. Deliver EEST-named Markdown here.
**Do not start D13a.**
