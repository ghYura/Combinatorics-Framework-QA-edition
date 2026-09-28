<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D13c results: bounded agent-message interleavings

- **Run:** `d13c_20260928T101424Z`. **Databases:** `as0927_d13c_20260928t101424z` on 5433 and 5432.
  - Retained sizes: main 8,410,815 bytes, results 8,361,663 bytes; the run directory is 1,551,738 bytes.
- **Input:** primary `spec/demo.xlsx` with its native `demo.constraints.json` (cell- and rule-equivalent to
  `spec/spec.toml`), run with `--sieve`. No optional axes.
- **Framework build:** accepted v6, no change.
- **Contract:** v1 `4517f5b4…e624`; predictions `a18d8ca1…4f73` and `derive.py` `e51666e4…dee0` unchanged.
- **Envelope:** `generated-default`, one worker, repeat 1, `-Xmx2g`, budgets 350/350/50 MB/800 s, no override.
  The Bundle took 57 s.
- **Evidence kind:** Verified/run. Replays were 5/5 byte-identical.
  - **Verifier:** the post-run `verify.py` passed 29/29, including 1,512 record fields, and gave the same 29/29
    from `archive/…/inputs`.
  - **Campaign-time verifier:** it reported 27/29 because of one parser bug (see Provenance). Its output is
    kept as `verification-campaign-time.json`.
- **Aborted launch, disclosed:** a first launch ran `python run_demo.py` in the wrong working directory. Python
  could not open the file, so nothing ran: no preflight, evidence folder, database or stage was created.
- **Model:** two deterministic agent stubs and a local coordinator. There is no live agent, OS thread,
  distributed consensus or general linearizability claim.

## Construction and stage counts

- **Factors:** mandatory HEAD, IMPL (3 policies, position 2), MODE (2), CAP (3), S1..S4 and TAIL. Each Si chooses
  `set_step(i,"A");` or `set_step(i,"B");` through `FW_Combi(1) → FW_Combi(size)`. No schedule is catalogued.
- **Decoding:** the actual `fw_final` rows were decoded atom by atom from `NumberToValue1` and determine each
  schedule.
- **Rendering:** every rendered candidate equals its Core row's atoms joined with the recorded sheet endings,
  byte for byte (54 of 54).

| Stage | Count |
|---|---:|
| Plans (XLSX = TOML, 3 bonds, same graph) | mandatory **EXACT 288**; post-sieve and final **BOUNDED [0, 288]** |
| Core `fw_final` before the sieve (3 × 2 × 3 × 16) | 288 |
| Sieve: per-rule raw matches | two_each 180, causal_ready 72, preemption_cap 84; overlap 90; unique removals 234 |
| Sieve: sequential survivors | 288 → 108 → 81 → **54** |
| Reader / Executor / results_v2 | 54 / 54 / 54; one attempt each |
| Outcomes | **36 PASS / 18 DOMAIN_FAIL**; zero BROKEN, INFRA_FAIL or TIMEOUT |

- **Why BOUNDED:** the planner reports "3 constraint(s) declared", because it does not evaluate sieve
  selectivity. The mode is recorded, not overridden. There were non-blocking warnings for rows and candidates
  (288 above the 175 threshold) and for wall time (576 s estimated above 400).
- **The 288 truth rows agree** across the precheck and the verifier's own evaluation:
  - The AI architect's frozen `raw_bond_truth`;
  - the Framework's `sieve.row_violations`, run offline on the built companion;
  - the live sieve log.

  The 54 surviving rows are exactly the declared population.

## Enabled schedules, the negotiation dependency and caps

**Enabledness** was explored from prefix delivery counts:
- **Independent mode** allows all six two-each words.
- **after_A_offer** allows AABB, ABAB and ABBA. BAAB, BABA and BBAA are disabled at delivery 1, because B's
  inspect waits for A's published offer.

For this fixture, "feasible" equals "first letter A". So the simple bond `MODE.wait == 0 or S1.a == 1` is exact.
It reads only the mode and the first delivery, never allocation state. Tests confirm that the retained
schedules are identical for all three coordinators.

**Preemptions** were computed from prefix completion counts, i.e. a switch away from an agent whose commit is
still undelivered.
- **Agreement:** they equal the contract's expression on all 16 words.
- **Examples:** AABB has 1 switch and 0 preemptions; ABBA 2/1; ABAB 3/2.
- **Cap versus switches:** a cap limits preemptions, not switches. ABBA runs at cap 1, while ABAB needs cap 2.

| Stratum (mode, cap) | Schedules | Denominator (3 policies) |
|---|---|---:|
| independent, 0 / 1 / 2 | AABB BBAA / + ABBA BAAB / + ABAB BABA | 6 / 12 / 18 |
| after_A_offer, 0 / 1 / 2 | AABB / + ABBA / + ABAB | 3 / 6 / 9 |

- **Strata are separate cases:** the same schedule in several strata counts as several declared cases, not
  as extra delivery orders.
- **No extrapolation:** there is no weighting and no extrapolated failure frequency. All six distinct
  schedules are supported.

## Outcomes

| Policy | independent K=0 / 1 / 2 | after_A_offer K=0 / 1 / 2 | Total |
|---|---|---|---|
| compare_version | 2/0, 4/0, 6/0 | 1/0, 2/0, 3/0 | 18 / 0 |
| trust_offer | 2/0, 2/2, 2/4 | 1/0, 1/1, 1/2 | 9 / 9 |
| overwrite_owner | 2/0, 2/2, 2/4 | 1/0, 1/1, 1/2 | 9 / 9 |

- **By cap:** 0 → 9/0, 1 → 12/6, 2 → 15/12.
- **Where the faulty policies fail:** exactly on the schedules where both inspects precede both commits (ABAB,
  ABBA, BAAB, BABA). On serial schedules (AABB, BBAA) the second agent sees `available=false` and receives BUSY
  under every policy.
- **Checks behind the verdict:**
  - **Useful work is required:** in every reference trace exactly one commit is GRANTED, so deny-all fails
    `reference_ok`.
  - **Refusals:** STALE appears only under compare_version (9 records); BUSY appears in 27 records, all PASS.

## Mechanisms (replayed; the marked entry is where the defect appears)

**trust_offer, independent, K=2, ABAB → DOMAIN_FAIL (`134_0_0`, checkpoint 4)**

| # | Message | Reply | Version | Allocations | Promises (from replies) |
|---|---|---|---:|---|---|
| 1 | A:inspect | available, v0 | 0 | {} | {} |
| 2 | B:inspect | available, v0 | 0 | {} | {} |
| 3 | A:commit (echo v0) | GRANTED R:A | 1 | {A} | {A} |
| 4 | B:commit (echo v0) | **GRANTED R:B** | 2 | **{A, B}** | {A, B} |

The cached availability double-books R: capacity and exclusive promises fail.

**overwrite_owner, same case → DOMAIN_FAIL (`230_0_0`, checkpoint 4):**
- **Silent withdrawal:** step 4 grants R:B and replaces the allocations with **{B}**, while the promises
  rebuilt from replies stay **{A, B}**.
- **Capacity passes at every checkpoint.** Only exclusive promises and commitments (allocations = promises)
  expose that A's promise was silently withdrawn.

**compare_version, same case → PASS (`38_0_0`):**
- **What the coordinator sees:** B:commit echoes v0 while the version is 1 and R is allocated.
- **Its reply:** **STALE**, a correct refusal that changes no state.

**overwrite_owner, after_A_offer, K=1, ABBA → DOMAIN_FAIL (`263_0_0`):**
- **The feasible order:** B:inspect is enabled only after A:inspect.
- **Step 3:** grants **R:B**.
- **Step 4:** A's commit, carrying the cached v0 offer, is granted and clears B. Allocations become {A} and
  promises {A, B}: an earlier B promise is withdrawn.

**trust_offer, independent, K=0, AABB → PASS (`100_0_0`):**
- **Steps 1–2:** A inspects and commits and is granted, so the version becomes 1.
- **Step 3:** B's inspect sees `available=false, v1`.
- **Step 4:** B's commit echoes that and gets **BUSY**. The faulty policy is harmless when there is no
  interleaving.

**Why capacity alone is inadequate.** A capacity-only oracle would pass all 9 overwrite_owner failures. The
promise ledger is rebuilt from the observed GRANTED replies, not trusted from the SUT, so a hidden withdrawal
also shows in `commitments_ok`. The supplied `issued_grants` equalled the rebuilt ledger at every checkpoint of
all 54 records. A tampered, missing or dropped promise fails integrity before the four checks; the tests
demonstrate this.

## Provenance and the verifier fix

- **Archive:** it holds all 18 recorded inputs byte for byte, with `verify.py` as executed by the campaign.
- **The bug:** the campaign-time parser collected only bare call statements, so it missed the TAIL's
  `_verdict = finish()` assignment. The rendered-identity field check failed only because of this.
- **The fix:** the parser now accepts exactly that assignment. The evidence is unchanged.
- **Other checks verified:** workbook, TOML and companion equivalence, the chain from the companion to the run
  sidecar, the Core input workbook, source inlining, and candidate and input hashes.

## Limits

One resource of capacity one, two agents with two messages each, no release, retry or expiry, two modes, caps
≤ 2 and three planted coordinators. The bounded strata are not claimed to preserve every fault of unbounded
interleavings.
