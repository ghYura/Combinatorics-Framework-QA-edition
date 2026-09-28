<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D3 phase C results: certified coverage versus detection

- **Run:** `d3c_20260927T184152Z`. **Databases:** `as0927_d3c_20260927t184152z` on 5433 and 5432.
- **Input:** `spec/full/demo.xlsx` with matching TOML. No sieve.
- **Framework build:** v3 = the D1-accepted v2 plus the per-candidate-seconds setting (see below).
- **Contract:** phase-c `9bb74b12…1191`.
- **Evidence kind:** Verified/run. `verify.py` passed 34/34 (24,480 record fields); replays were
  4/4 byte-identical.

## Benchmark

| Stage | Count |
|---|---:|
| Plans (XLSX = TOML graph) | EXACT 1440; the SCA3 catalogue plans EXACT 20 (planned only, not run) |
| Core per sheet | HEAD 1, IMPL 2, OPS 720, TAIL 1 → `fw_final` 1440 |
| Reader / Executor / results_v2 | 1440 each; the Core, Reader and Executor identity sets are equal |
| Outcomes | **1410 PASS / 30 DOMAIN_FAIL**, all 30 in `late_restart`; correct 720/720 |
| Hidden by final-only | 6 (`CNFSQV CNFSVQ CNFVSQ CNVFSQ CVNFSQ VCNFSQ`) |

The 30 failing orders are exactly those with C < N < F < S, the frozen prediction. There were zero
BROKEN, INFRA_FAIL or TIMEOUT outcomes. The Executor took 830 s, 0.577 s per candidate.

## Coverage certificates vs measured detection

The certificates were recomputed from the rows' positions and projections. The detections are the
campaign's own `late_restart` verdicts for each suite row.

| Suite | Rows | Obligations covered | Measured late_restart detections |
|---|---:|---:|---|
| SCA2 | 2 | 30/30 pairs | none |
| SCA3 | 10 | 120/120 triples | `CNQFSV` |
| ADJ2 | 9 | 30/30 adjacent pairs | `CNFQVS` |
| PROJ (CFQS adjacency) | 5 | 12/12 | `CNQFSV` |
| SCA3_counterexample | 10 | 120/120 triples | **none** |

Every suite passes on the correct policy.

The counterexample was **selected explicitly to exclude every trigger order**. It is a logical
counterexample to "coverage implies detection", not an unbiased effectiveness comparison and not
held-out discovery. No optimality is claimed for any suite.

## Witnesses (balance after each event; `!` marks a failed checkpoint)

| Case | Candidate | Trace |
|---|---|---|
| late_restart `CNFSQV` (heals) | `747_0_0` | C 100 · N 100 · F 100 · **S 0!** · Q 100 · V 100 → final-only PASS |
| late_restart `QCNFSV` (persists) | `1087_0_0` | Q 0 · C 100 · N 100 · F 100 · **S 0!** · **V 0!** → both verdicts DOMAIN_FAIL |
| late_restart `CFNSQV` (not triggered) | `723_0_0` | C 100 · F 0 · N 0 · S 0 · Q 0 · V 0 → PASS |
| correct `CNFSQV` (control) | `27_0_0` | balance 100 throughout → PASS |

## Same ledger state, different orders

The fault depends on a **state**: epoch 1, captures `[1,0]`, refunds `[0,0]` and a refund
attempted in epoch 1. The order C < N < F < S is exactly what reaches that state at S.

- **`CFNSQV` does not trigger.** The same four events refund epoch 0 before the renewal, so at S
  the refunds are `[1,0]` and the recovery branch is not taken.
- **Q decides whether the failure is visible at the end.**
  - Q after S heals the balance, so final-only observation misses the failure (6 orders).
  - Q before S cannot help (`QCNFSV`), and V does not repair.

## Why covering all triples need not expose a four-event condition

SCA3 guarantees that every *three* events appear in every relative order somewhere in the suite.
The trigger needs four events in one order within a *single* row.

The counterexample covers all 120 triples and still contains no row with C < N < F < S, so it
detects nothing. The ordinary greedy SCA3 happens to include one trigger row (`CNQFSV`).
Coverage is a property of the rows; detection is a property of the fault and the observation.

## Framework change v3 (authorized, with a recorded reproducer)

**Problem.** The run's budget gate always estimated wall time with the generic 0.05–2 s per
candidate. That gives 1440 × 2 = 2880 s, over the contract's 1800 s budget, while `plan` already
accepted a measured range.
- Reproducer: `blockers/run-budget-per-candidate/plan-full-demo.xlsx-default-range.log`.

**Fix.** `plan` and the run gate now share `per_candidate_seconds_min/max`, set by a flag or by
`BUNDLE_PER_CANDIDATE_SECONDS_*`. The defaults are unchanged, and the run records the range in its
budget intent.

**This run** used 0.3–1.2 s. That range comes from earlier measured runs: D2 0.575, D3 A 0.576
and D3 B 0.646 s per candidate. No override was used.
- Inventory: `framework-change/v3/` (delta from v2 plus the cumulative patch).
- Tests: 212 focused tests passed, DB-free.

## Limits

This covers only a local, deterministic six-event state machine and one deliberately planted
recovery fault; each distinct case has uniform weight. It makes no claim about production
frequencies, other fault shapes, optimal suites or durable systems.
