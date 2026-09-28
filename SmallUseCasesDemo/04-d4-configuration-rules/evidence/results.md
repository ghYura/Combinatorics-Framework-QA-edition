<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D4 results: configuration legality and feature interaction

| | Main (sieved) | Controls (unsieved) |
|---|---|---|
| Run ID | `d4main_20260927T193502Z` | `d4ctrl_20260927T192718Z` |
| Databases (5433 and 5432) | `as0927_d4main_20260927t193502z` | `as0927_d4ctrl_20260927t192718z` |
| Input | `spec/main/demo.xlsx` + `demo.constraints.json` (R1–R6, params, orders) | `spec/controls/demo.xlsx` (6-row CONFIG catalogue, no rules) |
| Framework build | v6 (below) | v5 (no sieve, so v6 does not apply) |
| Verifier | 29/29 | 21/21 (re-run on the archived inputs) |
| Replays | 2/2 byte-identical | 2/2 byte-identical |

- **Contract:** v1 `4caec19a…b5b0`; frozen cases `d61391ea…1f98`. No prediction was changed.
- **Envelope:** `generated-default` profile, one worker, K=1, `-Xmx2g`. Budgets: 200 mandatory rows,
  300 final candidates, 100 MB disk, 600 s wall. No override.
- **Wall time:** main 66 s, controls 38 s.
- **Evidence kind:** Verified/run. The verifier checks all 1,320 main record fields against its own
  model, which does not import the SUT, reference or runtime.

## Main campaign

| Stage | Derived | Measured |
|---|---:|---:|
| Plans (XLSX = TOML graph) | — | mandatory EXACT 144, optional EXACT 2, post-sieve BOUNDED [0, 144], final BOUNDED [0, 288] |
| Core `fw_final` / `fw_opt1` | 144 / 1 | 144 / 1 |
| Standalone rule matches R1–R5 | 36, 48, 36, 48, 24 | 36, 48, 36, 48, 24 (overlap 57, not summed) |
| Mandatory survivors | 144 → 108 → 72 → 63 → 51 → **36** | **36** |
| Reader assemblies (36 × {no DEBUG, DEBUG}) | 72 | 72 |
| Removed by R6 at Reader assembly | 6 | 6 (expected count 66 was exact before the Reader ran) |
| Reader / Executor / results_v2 | 66 | 66 / 66 / 66; one attempt each |
| Outcomes | 48 PASS / 18 DOMAIN_FAIL | **48 PASS / 18 DOMAIN_FAIL** |

- **Per policy:** correct 22/0, drops_gzip 4/18, ignores_debug_rule 22/0.
- **Failure classes:** all 18 failures are transformation failures (wrong headers: `Content-Encoding`
  is `identity` and the raw body is sent). There were 0 acceptance failures and zero BROKEN,
  INFRA_FAIL or TIMEOUT outcomes.
- **Identity sets:** the case sets from `fw_final` plus the Reader filter, the Reader AST and the
  Executor records each equal the 66 frozen main IDs.
- **R6 did not remove mandatory rows:** it was deferred to the Reader's optional-bond filter.

### A prod row with and without DEBUG

`env=prod|mode=batch|transport=https|features=audit+gzip|workers=2` survives R1–R5 as a
mandatory row. The case without DEBUG was rendered and ran (PASS under `correct`). The same row
with DEBUG was removed at Reader assembly by R6, so it was never rendered. This applies to all six
prod rows.

## Controls campaign

The controls are six preregistered invalid configurations, each violating exactly one rule, crossed
with the three policies: 18 cases, with no sieve.
- **Outcomes:** **17 PASS / 1 DOMAIN_FAIL**, as predicted.
- **Per policy:** correct 6/0, drops_gzip 6/0, ignores_debug_rule 5/1.
- **The one failure:** `ignores_debug_rule` accepts the R6 control
  (`prod/batch/https/audit+gzip/workers=2/debug=1`), a wrong-acceptance failure.
- The other 17 cases are legitimate rejections, so they count as PASS rather than infrastructure
  failures.

## Pairwise certificate and measured detection

| | |
|---|---|
| Legal population | 22 configurations |
| Obligations | 60 feasible pairs over env, mode, transport, features (one unordered-pair level), workers, debug |
| Frozen suite | 9 rows, all legal; covers **60/60** |
| Detects drops_gzip | 6 of 9 rows (every row that selects gzip) |
| Detects ignores_debug_rule | **0** |

The pairwise suite cannot detect `ignores_debug_rule`, because every configuration it can contain is
legal and that fault only shows on an illegal input. Only the separate invalid-input controls expose
it. No claim is made about individual-feature t-wise coverage or minimum suite size.

## Wrong extra bond (offline only)

The deliberately wrong rule "forbid gzip with either mode" was intersected with the live main
records:
- It removes **54** legal candidates and keeps **12**.
- Those 12 contain **0** failures, and every observed drops_gzip failure (18/18) is hidden.

The rule is wrong: it changes the denominator and removes the population where the defect lives.
Unlike R6, which is a correct rule whose violations still have to be exercised through separate
controls, it has no legitimate basis. The live campaign and its evidence were not altered.

## Witnesses (replayed, byte-identical)

| Case | Candidate | Observed |
|---|---|---|
| main correct, dev/batch/https/cache+gzip/w1/d0 | `11_0_0` | accepted; `Cache-Control: max-age=60`, `Content-Encoding: gzip`; body decodes to `{"sensor":7}\n` → PASS |
| main drops_gzip, same configuration | `59_0_0` | accepted; `Content-Encoding: identity`, raw body → DOMAIN_FAIL (`wrong_headers`) |
| controls correct, R6 control | `6_0_0` | rejected with `R6` → PASS |
| controls ignores_debug_rule, R6 control | `18_0_0` | accepted, `X-Debug: 1` → DOMAIN_FAIL (`wrong_acceptance`) |

## Framework changes (authorized, each with a recorded reproducer)

**v5: exact Reader expected count under deferred optional bonds.**
- **Problem:** the orchestrator expected `fw_final × optional factor` (36 × 2 = 72). The Reader
  correctly emits 66 after R6, so the invariant would have failed.
- **Fix:** before the Reader runs, the sieve stage decodes the assemblies and applies only the
  deferred rules, giving an exact count. The invariant was not loosened.
- **Records:** inventory `8db72fc3…`, delta from v4 `e9a71b54…`. Focused DB-free tests: 241
  passed, 8 skipped.

**v6: the sieve decodes every base-row value of a multi-value sheet.**
- **Problem:** `FEATURES = FW_Combi(2)` has a two-value base row (audit, cache). `fw_final`
  stores deviations from that base row, but the sieve decoded only its first value. Rules that
  mention cache therefore missed every row that inherits the base pair.
- **Fix:** `constraints/sieve.py` (`baseline_values`, `build_maps_from_db`, `sieve_fw_final`,
  `decode_assembly`) and `bundle/seedbias.py` now use all base-row values. `bundle/twise.py`
  rejects a multi-value base row explicitly.
- **Reproducer:** `blockers/sieve-multivalue-baseline/` (R2 matched 1 of 2 before the fix, 2 of 2
  after).
- **Records:** inventory `6a182a7e…`, delta from v5 `9630f185…`. Focused DB-free tests: 155
  passed, 10 skipped.

## First main run: invalid, preserved as defect evidence

`d4main_20260927T192553Z` (database `as0927_d4main_20260927t192553z`) ran on v5 and exposed the v6
defect:
- **Sieve:** R2 and R4 matched 24 rows instead of 48, so 48 rows survived instead of 36.
- **Reader:** 96 assemblies → 84 executions.
- **Illegal cases:** 18 (6 configurations with `features=audit+cache` × 3 policies; R2 12, R4 3,
  both 3) ran, and each was a legitimate rejection (PASS).
- **Effect:** outcomes became 66/18 instead of 48/18. The fault count was unchanged, but the PASS
  denominator grew silently.
- **Verification:** the current verifier reports it as failing, 19/29
  (`verify-defect-run/verification.json`). It is kept, not deleted, and nothing was dropped.

## Provenance

- **Input archives:** each run's campaign-time inputs are in `archive/<run-id>/inputs`
  (`ARCHIVE.json`), and every hash equals the run manifest.
  - Two files are later edits, rebuilt exactly for the archive: `framework_change.py` (version-scope
    table added for v6) and `verify.py`.
- **Post-run fixes to `verify.py`:** both are excluded from input drift as post-run tools.
  - A shadowed variable crashed the main campaign's verifier call after the Bundle finished.
  - Records outside the frozen set are now reported as failures instead of raising an error.

## Limits

This is a finite local adapter contract: six rules, three planted policies, three feature pairs,
optional DEBUG and uniform case weights. It makes no claim about real configuration systems,
production failure rates, individual-feature interaction coverage or optimal suites.
