<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D10 results: sensor selection and fault diagnosis

- **Run:** `d10_20260928T073948Z`. **Databases:** `as0927_d10_20260928t073948z` on 5433 and 5432.
  - Retained sizes: main 8,689,343 bytes, results 9,524,927 bytes; the run directory is 36,115,954 bytes.
- **Input:** primary `spec/demo.xlsx` (cell-equivalent to `spec/spec.toml`). No sieve, optional or
  scenario axes.
- **Framework build:** accepted v6, no change.
- **Contract:** v1 `d6eba25f…d5a`; predictions `24d5874d…52f9` and `derive.py` unchanged.
- **Envelope:** `generated-default`, one worker, K=1, `-Xmx2g`, budgets 3200/3200/150 MB/7200 s, no
  override. The plans warned but blocked nothing; the Bundle took 1,794 s.
- **Evidence kind:** Verified/run. `verify.py` passed 24/24, including 76,800 record fields, and gave the
  same 24/24 from `archive/…/inputs`. Replays were 5/5 byte-identical.
- **Model:** synthetic status flags and probes with unit costs; nothing is field-calibrated.

## Evaluations and the empty selection

HEAD (an empty selection), SENSORS at position 2 (`select(0)`…`select(7)`), FAULT (twelve distinct
labels) and TAIL are crossed by the Framework. SENSORS uses `FW_Subsets → FW_Subsets`:

| SENSORS work | Derived | Observed (Core log) |
|---|---:|---:|
| First pass | 256 subsets | 256 `fw_` rows |
| Second pass (powerset per nonempty row) | 3⁸ − 1 = 6,560 emissions | 6,560 `fw2_` rows before DISTINCT |
| After DISTINCT | 256 | 256 |

| Stage | Count |
|---|---:|
| Plans (XLSX = TOML graph) | EXACT 3072 (SENSORS EXACT 256) |
| Core `fw_final` (1 × 256 × 12 × 1) | 3072 |
| Reader / Executor / results_v2 | 3072 / 3072 / 3072; one attempt each |
| Outcomes | **3072 PASS**; zero BROKEN, INFRA_FAIL or TIMEOUT |

- **Empty and full masks:** 12 empty-mask cases (in the base row of `fw_final`, rendered with no
  `select()` call) and 12 full-mask cases are present.
- **Three routes agree:** the SUT's flag injection and probe functions, the literal 7 × 8 reference
  table and the verifier's arithmetic produce the same readings on every row.
- **An uninformative selection is not a failure:** it is a design limitation, and those rows still
  pass.

## Observational equivalence

`diagnosis.py` (offline, from the observed matrix) first applies its guard. It requires 256 × 12
PASS rows, one each, with every subset's readings equal to the projection of that label's observed
full signature. It then inferred these full-signature classes:

| Class | Labels | Full signature S0..S7 |
|---|---|---|
| 0 | H0 (declared reference, DB-free control; not observed) | 00000000 |
| 1 | F01, F02 | 10001101 |
| 2 | F03, F04 | 01001011 |
| 3 | F05, F06 | 00100111 |
| 4 | F07, F08 | 00011110 |
| 5 | F09, F10 | 11100001 |
| 6 | F11, F12 | 11111111 |

- **Alias pairs:** even all eight sensors give F01 and F02 the same word, `10001101` (replayed
  `S=11111111|H=F02`). The minimum distance over the unquotiented labels is therefore 0.
- **What identification returns:** a class and both of its labels, never one cause.

## Fixed suites (all 256 masks certified; ties retained)

| Obligation | Minimum cost | First mask (lexicographic) | Feasible masks |
|---|---:|---|---:|
| Detection (every fault class ≠ H0) | 2 | 00000011 | 201 |
| Separation (all seven words distinct) | 4 | 00001111 | 149 |
| One known erasure (min distance ≥ 2) | 6 | 00111111 | 37 |
| One wrong reading (min distance ≥ 3) | 7 | 01111111 | 9 |

`diagnosis.json` holds, for every mask, the seven projected words and all 21 pairwise distances;
minimality is certified over all 256 masks.

**Replayed observations:**
- **Detection mask 00000011 (S6, S7):** F01 → `01` and F09 → `01`. Both differ from health, but not
  from each other.
- **Separation mask 00001111 (S4..S7):** F01 → `1101` and F09 → `0001` (replayed); the two are
  separated.
- **Empty selection:** `S=00000000|H=F01` gives cost 0, readings [] and an empty signature.

## Adaptive diagnosis (noiseless, offline, certified)

The minimax program over all 127 nonempty beliefs gives worst-case cost **3**. That lies between
detection (2) and fixed separation (4). Ties go to the smallest sensor.

```
S0=0 → S4=0 → S2=0: class 0 (H0)       S2=1: class 3 (F05,F06)
       S4=1 → S1=0: class 4 (F07,F08)  S1=1: class 2 (F03,F04)
S0=1 → S1=0: class 1 (F01,F02)
       S1=1 → S3=0: class 5 (F09,F10)  S3=1: class 6 (F11,F12)
```

- **Paths:** the seven paths use 3, 2, 3, 3, 3, 3 and 3 queries. Every leaf names a whole class, and no
  sensor repeats on a path.
- **Status:** this is an offline certified policy over the observed signatures, not a Framework run of
  an interactive service. It assumes no noise and uses no class probabilities.

## Noise controls (finite proofs, offline)

- **Erasure suite 00111111:** every class word, unchanged or with one position replaced by `?` — 49
  controls. Each decodes to exactly its true class.
- **Error suite 01111111:** every class word, unchanged or with one bit flipped — 56 controls. Each
  decodes (Hamming distance ≤ 1) to exactly its true class.

The extra probes beyond the separation suite (cost 4 → 6 → 7) are what buy this tolerance. The adaptive
tree does not handle noise, and the one-erasure and one-error guarantees are not claimed to hold
jointly.

## Limits

This is a synthetic model: four flags, eight probes with unit costs, six alias pairs plus a declared
healthy reference. It implies no optimum beyond this model. Diagnosis certificates are offline
analysis of observed rows; the Framework generated and executed the evaluations but did not diagnose.
