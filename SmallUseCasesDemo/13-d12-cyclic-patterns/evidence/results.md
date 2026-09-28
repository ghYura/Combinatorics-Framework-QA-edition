<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D12 results: cyclic designs and rotation classes

| | words | classes |
|---|---|---|
| Run | `d12a_20260928T084349Z` | `d12b_20260928T085154Z` |
| Databases (5433 and 5432) | `as0927_d12a_20260928t084349z` | `as0927_d12b_20260928t085154z` |
| Construction | HEAD, P0..P5 (three letters each), TAIL | HEAD, PATTERN (130 canonical representatives), TAIL |
| Plans (XLSX = TOML) | EXACT 729 | EXACT 130 |
| Core / Reader / Executor / results_v2 | 729 / 729 / 729 / 729 | 130 / 130 / 130 / 130 |
| Outcomes | **729 PASS** | **130 PASS** |
| Verifier (also from the archived inputs) | 24/24 | 24/24 (including agreement with the words run) |
| Replays (byte-identical) | 4/4 | 1/1 |
| Bundle time; retained sizes (main / results / run dir) | 448 s; 8.46 / 8.48 / 9.45 MB | 111 s; 8.34 / 8.20 / 1.80 MB |

- **Contract:** v1 `69b849df…b558`; predictions `eff697e4…8e14` and `derive.py` unchanged.
- **Framework:** accepted v6, no change.
- **Envelope:** `generated-default`, one worker, K=1, `-Xmx2g`, each campaign's own budgets, no sieve,
  optional axes or override.
- **Attempts:** 859 original attempts in total. The two populations are never merged into one
  denominator.
- **Construction:** every slot uses `Combi(1) → Combi(size)`. In words, six explicit position
  fragments build the word, and the verifier checks each emitted word against the decoded Core
  identity. The 130-entry PATTERN catalogue was built offline by the builder, which canonicalised all
  729 words. The Framework crossed and executed the catalogue; it did not canonicalise anything, and
  classes Core support is 130 rows, not 729 filtered afterwards.
- **Three routes agree:** the SUT (walking the six cyclic edges), the reference (directed pair counts
  dotted with the matrix, plus doubled-string rotations) and the verifier agree on every field of
  every row.

## Partition certificate (from the observed words run; `analysis.json`)

- **Coverage:** 130 rotation classes cover all 729 words, disjointly and completely. Each
  representative is its word's least distinct rotation.
- **Burnside:** fixed-word counts for shifts 0..5 are **[729, 3, 9, 27, 9, 3]**; their sum divided by
  6 is 130.
- **Orbit sizes:** size 1: 3 classes, size 2: 3, size 3: 8, size 6: 116. The sizes sum to 729, not
  780: weighting every representative by 6 would be wrong.
  - Examples: AAAAAA has size 1, ABABAB size 2, ABCABC size 3 (period 3, stabilizer 2), AAAAAB size 6.
- **Constant cost per orbit:** every word in an orbit has the same observed total cost.
- **Cross-campaign agreement:** all 130 classes-campaign results equal their words-campaign
  representatives field by field.

**The seam.** AAAAAB and BAAAAA (replayed) are the same orbit, and both total **25**: transition 11
plus balance 14.
- Their edge-cost lists are [2,2,2,2,0,3] and [3,2,2,2,2,0]. The list rotates with the word, while
  the aggregate stays invariant.
- A scorer that omits the closing edge gives **22 and 25**, which depends on the arbitrary starting
  position. The fixture tests detect such a scorer.

**Directed reflection is not an equivalence.**
- ABCABC (replayed, all six edges cost 0) totals **0**.
- Its mirror ACBACB (replayed, all six edges cost 3) totals **18**. Reversing the word reverses every
  directed edge.
- 54 classes map to themselves under reflection, and 38 mirror pairs stay separate. Quotienting
  reflection would leave 92 classes and change the declared space.

## Three explicitly labelled populations (from observed costs)

| Population | Weighting | Exact mean |
|---|---|---|
| Uniform labelled words | each of 729 words once | **14** |
| Uniform rotation classes | each of 130 designs once | **942/65** (≈ 14.49) |
| Orbit-weighted classes | each representative × its distinct orbit size | **14** |

| Cost | 0 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 14 | 15 | 16 | 17 | 18 | 19 | 21 | 25 | 36 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Words (729) | 3 | 18 | 6 | 72 | 36 | 18 | 18 | 36 | 126 | 18 | 12 | 162 | 54 | 57 | 36 | 18 | 36 | 3 |
| Classes, uniform (130) | 1 | 3 | 1 | 12 | 6 | 3 | 3 | 6 | 21 | 3 | 4 | 27 | 9 | 13 | 6 | 3 | 6 | 3 |
| Classes, orbit-weighted (729) | 3 | 18 | 6 | 72 | 36 | 18 | 18 | 36 | 126 | 18 | 12 | 162 | 54 | 57 | 36 | 18 | 36 | 3 |

- **Weighting restores the words population:** the orbit-weighted histogram equals the labelled-word
  histogram exactly. So 130 evaluations, weighted by orbit size, answer the labelled-word question.
- **Neither convention is wrong:** weighting classes uniformly asks a different question, about
  designs rather than labelled words.

**Ranking** by (total cost, representative), with ties retained: the unique best class is **ABCABC**
(0), followed by AABCBC, ABABCC, ABBCAC and AABBCC.
- ABCABC stands for three labelled words, ABCABC, BCABCA and CABCAB (the classes replay of ABCABC
  matches its words evaluation).
- Its mass is 1/130 among classes but 3/729 = 1/243 among words.

## Limits

This is an illustrative cost matrix over all oriented length-six words on three letters, with
rotation as the only equivalence. It says nothing about reflection- or renaming-invariant designs, or
field costs. The words→classes reduction is demonstrated here by running both populations; any future
use of the 130-case campaign must re-apply orbit weights to answer labelled-word questions.
