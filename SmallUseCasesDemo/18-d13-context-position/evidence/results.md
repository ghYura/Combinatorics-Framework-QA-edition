<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D13e results: context order, reduced coverage and noisy judges

- **Run:** `d13e_20260928T171251Z`. **Databases:** `as0927_d13e_20260928t171251z` on 5433 and 5432 (owner
  role `postgres`; absent on both ports before the run).
  - Retained sizes: main 8,345,279 bytes, results 8,214,207 bytes; the run directory is 2,044,375 bytes;
    `evidence/` 2,224,242 bytes and `archive/` 1,746,319 bytes.
- **Input:** primary `spec/demo.xlsx`; cell-, chain- and message-equivalent to `spec/spec.toml`. No rules,
  no companion, no sieve, no optional axis.
- **Framework build:** accepted v6, no change (checkout `be48836` + the 27 inventoried v6 files; Core jar
  `e705674e…`, Reader jar `71393e9f…`, py_executor `a6820f11…`, all unchanged since the run).
- **Contract:** v1 `00151b59…6cae`; predictions `fde4e4ab…34d5`, `derive.py` `2e7109ab…8651` and
  `coverage.json` `403f7f88…942c` unchanged.
- **Envelope:** `generated-default`, one worker, Framework repeat 1, `-Xmx2g`, budgets 100/100/50,000,000 B/400 s,
  no override. The Bundle took 57.5 s (Core 9.4 s, Reader 13.2 s, Executor 32.8 s).
- **Evidence kind:** Verified/run. `verify.py` passed 35/35 at campaign time (49,788 record fields, 1080 trials,
  2160 judge readings) with no post-run change. It gave the same 35/35 from `archive/…/inputs`, and the five
  named replays were byte-identical (each with its 20 trials).
  - **Parser preflight:** before the campaign, the verifier's candidate parser was run on a locally composed
    candidate (a fixture test, which also executes it and compares its 20 trials with the frozen values).
- **Model:** deterministic local context processors and SHA-derived judge surrogates. There is no external
  model, live judge, API or outbound action, and no claim about such systems.

## Construction and stage counts

- **Factors:** mandatory HEAD, IMPL (3 processors, position 2), TASK (public, secret), ORDER and TAIL; every
  slot uses `FW_Combi(1) → FW_Combi(size)`. ORDER is the certified catalogue: the eight SCA3 orders of
  `coverage.json` in its order, then the preregistered control ABGCDE (nine `set_order("…");` atoms, not 54
  prebuilt programs).
- **Decoding:** the decoded `fw_final` atoms determine policy, task and order. Each rendered candidate equals
  its Core row joined with the recorded sheet endings, byte for byte; each name prefix equals its `combi_id`.

| Stage | Count |
|---|---:|
| Plans (XLSX = TOML; graph `sha256:7836485e…` = the AI architect's shape plan) | mandatory, post-sieve, final **EXACT 54**; optional ×1 |
| Core `fw_final` (1 × 3 × 2 × 9 × 1) | 54 |
| Reader / Executor / results_v2 | 54 / 54 / 54; one attempt each, repeat_idx 0 |
| Internal processor trials (20 per candidate) | 1080 (SCA3 960, control 120) |
| Judge readings (2 per trial, one shared draw) | 2160 |
| Outcomes | **49 PASS / 5 DOMAIN_FAIL**; zero BROKEN, INFRA_FAIL or TIMEOUT |

- **Budget notes:** the planner and the run gave non-blocking warnings (54 rows and 54 candidates above the
  warning threshold 50; hard limit 100). Nothing was overridden.
- **Sizing only:** the native `FW_Permut()` universe (`planning/universe.toml`) plans EXACT 4320 at every stage
  (`precheck/universe-plan/`). It was planned, never executed.

## Coverage certificate and the position control

- **The cover (Derived offline by SciPy/HiGHS, not by Framework):** eight distinct orders of ABCDEG. The
  precheck and the verifier each check that all 120 ordered triples occur as subsequences and that
  `coverage.json` lists exactly the covering orders. Feasibility only; no minimality is claimed.
- **The gap:** G sits at positions 6, 4, 5, 2, 4, 5, 1, 1 in the cover, never third. Covering every ordered
  triple does not cover every absolute position.
- **The control:** ABGCDE (G third), chosen from the known model before any run. It is a preregistered
  witness, not an independently sampled discovery, and it confers no global coverage certificate.

| Suite | Cases / trials | stable | last_marker | third_position |
|---|---|---|---|---|
| SCA3 cover (8 orders) | 48 / 960 | 16/0 | 12/**4** | 16/**0** |
| Position control ABGCDE | 6 / 120 | 2/0 | 2/0 | 1/**1** |

(cells: PASS/DOMAIN_FAIL over both tasks.) The cover finds the four last_marker failures (DCBEGA, DGEBCA,
GABEDC, GCDAEB: A after G) and misses third_position; the control catches it. Every failure is a secret task.

- **The full model (a calculation over 720 orders × 2 tasks × 3 processors = 4320 cases, not runs):** stable 0,
  last_marker 360 (all secret), third_position 120 (all secret). The deliberately selected nine-order suite
  is not a sample of that universe; no full-universe fault rate is estimated from it.

## Mechanisms (replayed)

| Witness | Candidate | Fold G/A… (after each chunk) | Decision × 20 | Verdict |
|---|---|---|---|---|
| last_marker, secret, GABEDC — context-order failure | `34_0_0` | G→DENY, A→**ALLOW**, B,E,D,C keep | ALLOW | **DOMAIN_FAIL** (20/20 trials) |
| stable, secret, GABEDC — matched correct processor | `16_0_0` | G→DENY, the rest ignored | DENY | PASS |
| third_position, secret, ABGCDE — missed by SCA3 | `54_0_0` | A,B keep null, G third→**ALLOW** | ALLOW | **DOMAIN_FAIL** (20/20) |
| stable, public, ABGCDE — useful ALLOW control | `9_0_0` | G→ALLOW | ALLOW | PASS |
| stable, secret, ABCDEG — late-band paired judges | `10_0_0` | A..E keep null, G→DENY | DENY | PASS |

- **Transient state is diagnostic:** last_marker with A before G (ABCDEG, CBAGED, EACGDB, EBDAGC, ABGCDE) holds
  ALLOW transiently on secret tasks, then G sets DENY; all five PASS.
- **Deny-all is excluded:** all 27 public candidates return ALLOW in all 20 trials; a fixture test shows a
  deny-all processor passing every secret task and failing every public one.

## Judge surrogates against mechanical truth

Both judges receive the known mechanical label and flip it on the trial's shared draw (a labelled calibration
fixture, not a semantic judge). Approvals never decide a verdict: an approval-based verdict ("PASS iff all 20
approvals") would change 42 candidates for calibrated and 46 for position_biased.

| Judge \| band | n | TP | FN | FP (false approvals) | TN | Accuracy | Nominal error | Wilson 95% (illustrative) |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| calibrated \| early (G 1–3) | 480 | 364 | 36 | 4 | 76 | 0.916667 | 0.1 | [0.888510, 0.938207] |
| calibrated \| late (G 4–6) | 600 | 515 | 65 | 0 | 20 | 0.891667 | 0.1 | [0.864260, 0.914090] |
| position_biased \| early | 480 | 162 | 238 | 41 | 39 | 0.418750 | 0.6 | [0.375430, 0.463360] |
| position_biased \| late | 600 | 515 | 65 | 0 | 20 | 0.891667 | 0.1 | [0.864260, 0.914090] |

All four cells equal `architect-derived.json` (counts exactly; accuracy and interval ends within 1e-12).
Incorrect decisions: 100 trials (five failing candidates × 20), 80 early and 20 late; late FP is 0 because
none of the 20 late incorrect draws (DCBEGA) fell below D/10.

**Paired table** (both judges on the same trials; T = reading agrees with mechanical truth):

| Band | TT | TF (cal right, biased wrong) | FT | FF | Disagreements |
|---|---:|---:|---:|---:|---:|
| early | 201 | 239 | **0** | 40 | 239 |
| late | 535 | 0 | 0 | 65 | **0** |

- **Late band:** identical thresholds on one draw, so the judges agree exactly.
- **Early band (the declared coupling):** calibrated flips iff n < D/10, biased iff n < 3D/5 ⊃ that set, so a
  calibrated error always implies a biased error (FT = 0) and the 239 disagreements are the draws in
  [D/10, 3D/5). The judges are paired, not independent samples, and are never pooled.

**Strata** (accuracy; full cells in `verification.json`):

| Stratum | calibrated early / late | position_biased early / late |
|---|---|---|
| task public | 0.9250 / 0.8967 | 0.3875 / 0.8967 |
| task secret | 0.9083 / 0.8867 | 0.4500 / 0.8867 |
| stable | 0.8938 / 0.8950 | 0.3875 / 0.8950 |
| last_marker | 0.9625 / 0.9100 | 0.4813 / 0.9100 |
| third_position | 0.8938 / 0.8700 | 0.3875 / 0.8700 |
| suite SCA3 / control (bands pooled) | 0.9010 / 0.9167 | 0.7115 / 0.4417 |

The suite rows mix bands: the control's G is third, so it is entirely early band.

## What the intervals are, and are not

- **Illustrative:** Wilson intervals (z = 1.96) under a Bernoulli approximation to the pseudorandom draws.
- **No new evidence on rerun:** the frozen fixture is deterministic; rerunning or replaying it reproduces the
  same readings.
- **No wider claim:** they do not establish real-judge accuracy, cover-suite representativeness or any
  confidence bound on live-model safety. No significance acceptance gate is applied.

## Provenance

- **Archive:** all 21 recorded inputs byte for byte (`verify.py` unchanged since the campaign).
- **Checks verified:** frozen hashes; the build record; workbook = run-input copy = Core input workbook;
  XLSX/TOML slots, endings, FW_Seq chains and custom message; the ORDER catalogue; source inlining;
  candidate, observation and component hashes; the command envelope and JVM options.

## Limits

Six fixed chunk tokens, three planted processors, two labelled tasks, nine selected orders and a SHA-derived
noise channel over a supplied label. The 20 trials per candidate are internal deterministic calls, not
Framework repeats or distinct contexts. Nothing here measures natural-language prompts, live models or real
judges.
