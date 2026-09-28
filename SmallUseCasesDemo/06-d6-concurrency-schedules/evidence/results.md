<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D6 results: bounded and enabled schedules

| | Counter | Queue |
|---|---|---|
| Run | `d6counter_20260927T233336Z` | `d6queue_20260927T233436Z` |
| Databases (5433 and 5432) | `as0927_d6counter_20260927t233336z` | `as0927_d6queue_20260927t233436z` |
| Input | `spec/counter/demo.xlsx` + companion (2 bonds) | `spec/queue/demo.xlsx` + companion (2 bonds) |
| Core `fw_final` → sieve → Reader / Executor / results_v2 | 96 → **24** → 24 / 24 / 24 | 32 → **6** → 6 / 6 / 6 |
| Outcomes | **18 PASS / 6 DOMAIN_FAIL** | **5 PASS / 1 DOMAIN_FAIL** |
| Verifier (also from the archived inputs) | 25/25 (528 record fields) | 25/25 (126 record fields) |
| Replays (byte-identical) | 2/2 | 2/2 |

- **Contract:** v1 `971e0675…bf6d`; predictions `bfe8a15c…d4d6` and `derive.py` unchanged.
- **Framework:** accepted v6, no change.
- **Envelope:** `--sieve`, `generated-default`, one worker, K=1, `-Xmx2g`, budgets 150/150/100 MB/600 s;
  no optional axes and no override. Zero BROKEN, INFRA_FAIL or TIMEOUT outcomes. The Bundle took
  40 s for the counter and 30 s for the queue.
- **Denominators:** the two campaigns are separate populations and are never added together.

## How the schedules were built

- **One step per sheet.** Each of S1..S4 selects its own thread through `FW_Combi(1) → FW_Combi(size)`,
  using the atoms `set_step(i,"A");` / `set_step(i,"B");`, or `"P"`/`"C"` for the queue.
- **No complete schedule is listed.** The runtime rebuilds the schedule from the four rendered atoms.
  The nth occurrence of a thread is its nth local step, so local order holds by construction.
- **Counter population:** the raw product is 2 policies × 3 caps × 2⁴ = 96.
  - `two_each` requires `S1.a + S2.a + S3.a + S4.a == 2` (A has a=1).
  - `preemption_cap` requires the contract's expression to be ≤ `CAP.n`.
- **Queue population:** the raw product is 2 × 2⁴ = 32.
  - `two_each` requires two producer steps (p=1).
  - `producer_first` is a require-assert that S1 is `set_step(1,"P");`.

### Bond truth tables (own evaluation = live sieve log = the Framework's sieve run offline)

| Campaign | Raw | Per-rule raw matches | Overlap | Unique removals | Sequential survivors |
|---|---:|---|---:|---:|---|
| Counter | 96 | two_each 60, preemption_cap 28 | 16 | 72 | 96 → 36 → **24** |
| Queue | 32 | two_each 20, producer_first 16 | 10 | 26 | 32 → 12 → **6** |

The per-rule counts overlap, so they are never added together. The live sieve line reads
"scanned 96, unique removals 72 (overlap 16) → fw_final now 24", and for the queue 32/26/10/6.

## Counter: switches versus preemptions

**The cap expression.** It was derived independently from prefix completion counts: a switch at step i
is a preemption when the outgoing thread has finished fewer than two steps. On all 16 raw words the
expression equals that count (`precheck/counter.json`; `verification.json`, check
`schedule.preemption_expression_all_16_words`). The contract's examples hold:

| Schedule | Context switches | Preemptions |
|---|---:|---:|
| AABB | 1 | 0 |
| ABBA | 2 | 1 |
| ABAB | 3 | 2 |

**Why the switch in AABB is free.** Thread A has completed both steps before B starts, so no work of A
is interrupted. Under the declared bound, a forced switch after completion is not a preemption.

**Results per cap.** Each cap is its own population; repeated schedules across caps are separate
declared cases.

| Cap | Distinct schedules | Cases | PASS / DOMAIN_FAIL |
|---|---|---:|---|
| 0 | AABB, BBAA | 4 | 4 / 0 |
| 1 | + ABBA, BAAB | 8 | 6 / 2 |
| 2 | + ABAB, BABA | 12 | 8 / 4 |

- **atomic_commit:** 12 / 0.
- **split_rw:** 6 / 6. It fails on exactly the four interleavings (ABBA, BAAB, ABAB, BABA), each
  losing one update: the final counter is 1, where the reference is 2. Both serial schedules pass.
- **No extrapolation:** nothing here estimates how often the fault would occur in practice.

**Witnesses** (counter after each step):

| Case | Candidate | Trace | Verdict |
|---|---|---|---|
| split_rw CAP2 ABAB (replayed) | `86_0_0` | 0, 0, 1, **1** (locals A=0, B=0; B writes 0+1) | DOMAIN_FAIL at checkpoint 4 |
| atomic_commit CAP2 ABAB (replayed) | `38_0_0` | 0, 0, 1, 2 | PASS |
| split_rw CAP0 AABB (serial control, original observation) | `52_0_0` | 0, 1, 1, 2 (B reads 1) | PASS |

## Queue: enabledness before execution

**Reference-state exploration** (`precheck/queue.json`; the verifier re-derives it):
- Of the 16 raw words, 10 are malformed (not two steps per thread) and 3 are feasible: PPCC, PCPC,
  PCCP.
- The other 3 two-each words (CPPC, CPCP, CCPP) are infeasible: step 1 would run `wait_readable` on
  the empty queue.
- In this fixture the feasible set equals "first letter is P". The two bonds keep exactly these
  three schedules.

**Infeasible schedules are not SUT defects.** An infeasible schedule has no well-defined execution: its
first step is disabled on the reference state, so no implementation can be observed on it. These
schedules are excluded; they are not PASS, DOMAIN_FAIL or execution attempts. None appears in
`fw_final`, the Reader or the Executor.
- The runtime rejects a disabled or malformed schedule as a setup error, which the fixture tests
  confirm. That rejection is decided on the reference's state, never on the faulty implementation's.

**Result:** actual_queue 3 / 0; stale_empty 2 / 1.

| Case | Candidate | After each step (op: items, published, pop) | Verdict |
|---|---|---|---|
| stale_empty PCCP (replayed) | `23_0_0` | enqueue: [item], F, –; wait: [item], F, –; **try_pop: [item], F, EMPTY**; publish: [item], T, EMPTY | DOMAIN_FAIL at 3, 4 |
| actual_queue PCCP (replayed) | `7_0_0` | enqueue; wait; try_pop: [], F, item; publish: [], F, item | PASS |

- **What goes wrong:** the item exists before publication, so `try_pop` reports EMPTY and leaves the
  item queued.
- **Diagnostic only:** the publication flag was not required to match the queue between publications.

## Provenance

- **Archives:** `archive/<run>/inputs` hold each run's inputs byte-identical to the campaign; the
  manifests record every hash.
- **Other evidence:** plans, constraint explanations, per-sheet Core pass logs (`chain-log.txt`),
  the dictionary and tables, candidates, observations and replays are all in `evidence/<run>/`.

## Limits

These are deterministic step simulations with explicitly controlled operation order: two two-step
threads and one producer/consumer pair, with equal weight per declared case. They say nothing about
OS scheduling, weak memory, real concurrency or fault frequency.
