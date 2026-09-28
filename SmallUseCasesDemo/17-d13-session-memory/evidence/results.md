<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D13d results: session identity and memory lifetime

- **Run:** `d13d_20260928T120843Z`. **Databases:** `as0927_d13d_20260928t120843z` on 5433 and 5432.
  - Retained sizes: main 8,550,079 bytes, results 9,230,015 bytes; the run directory is 16,506,571 bytes.
- **Input:** primary `spec/demo.xlsx` with its native `demo.constraints.json` (cell- and rule-equivalent to
  `spec/spec.toml`), run with `--sieve`. No optional axes.
- **Framework build:** accepted v6, no change.
- **Contract:** v1 `6da4bdc3…7ba5`; predictions `3a53ed96…3c64` and `derive.py` `455dbb37…4de4` unchanged.
- **Envelope:** `generated-default`, one worker, repeat 1, `-Xmx2g`, budgets 1200/1200/150 MB/3000 s, no
  override. The Bundle took 493 s.
- **Evidence kind:** Verified/run. `verify.py` passed 27/27 at campaign time, including 20,800 record fields,
  with no post-run change. It gave the same 27/27 from `archive/…/inputs`, and replays were 5/5
  byte-identical.
  - **Parser preflight:** before the campaign, the verifier's candidate parser was run on a locally composed
    candidate (a fixture test).
- **Model:** a deterministic memory adapter with inert draft-tool stubs. There is no external model, message,
  file-writing tool or network action.

## Construction and stage counts

- **Factors:** mandatory HEAD, IMPL (4 adapters, position 2), WRITE_AT, U1..U3, S1..S3, R12, R23 and TAIL.
  Every slot uses `FW_Combi(1) → FW_Combi(size)`; U1/S1 offer label 0, U2/S2 0–1, U3/S3 0–2.
- **Decoding:** the decoded `fw_final` atoms determine every axis. Each rendered candidate equals its Core row
  joined with the recorded sheet endings, byte for byte. Each candidate's name prefix equals its Core
  `combi_id`.

| Stage | Count |
|---|---:|
| Plans (XLSX = TOML, 2 bonds, same graph) | mandatory **EXACT 1152**; post-sieve and final **BOUNDED [0, 1152]** |
| Core `fw_final` before the sieve (4 × 2 × 6 × 6 × 2 × 2) | 1152 |
| Sieve: per-rule raw matches | user_rgs 192, session_rgs 192; overlap 32; unique removals 352 |
| Sieve: sequential survivors | 1152 → 960 → **800** (= 4 × Bell(3)² × 4 × 2) |
| Reader / Executor / results_v2 | 800 / 800 / 800; one attempt each |
| Outcomes | **718 PASS / 82 DOMAIN_FAIL**; zero BROKEN, INFRA_FAIL or TIMEOUT |

- **Why BOUNDED:** the planner reports "2 constraint(s) declared", because it does not evaluate selectivity.
  The mode is recorded, not overridden. There were non-blocking warnings for rows and candidates (1152 above
  600) and for wall time (2,304 s estimated above 1,500; actual 493 s).
- **The 1152 truth rows agree** across the precheck and the verifier:
  - The AI architect's frozen table;
  - the Framework's `sieve.row_violations`, run offline;
  - the live sieve log.
- **Population:** the five canonical label strings are exactly the Bell(3) set partitions, and all 25
  user × session partition pairs survive.

## Outcomes and leak accounting

| Policy | PASS / FAIL | Leaking read checkpoints (kind) |
|---|---|---|
| scoped | 200 / 0 | — |
| user_only | 172 / 28 | 30 cross_session |
| session_only | 172 / 28 | 30 cross_user |
| ignores_reset | 174 / 26 | 28 expired |

**Three counts kept apart:** 82 failed cases contain **88 leaking read checkpoints**; 6 cases (2 per faulty
policy) leak twice. Each leaking checkpoint exposes the canary in both the reply and the draft-tool argument,
giving **176 occurrences** (88 + 88).

| Stratum | PASS / FAIL |
|---|---|
| Cuts X=00 / 01 / 10 / 11 | 168/32, 180/20, 181/19, 189/11 |
| Write position W=1 / 2 | 350/50, 368/32 |

- **Where each faulty policy fails:**
  - **user_only and session_only** fail at X=00 (W=1: 10, W=2: 6), X=01/W=1 (6) and X=10/W=2 (6). The
    colliding reader must share the write epoch.
  - **ignores_reset** fails only when a cut follows the write: X=01 (4 + 4), X=10/W=1 (7) and X=11 (7 + 4).
- **The full split:** policy × cut × write tallies are in `verification.json`. This is an enumerated finite
  population, with no empirical user weights.

## Mechanisms (replayed)

**session_only, U=010, S=000, X=00, W=1 → DOMAIN_FAIL (`649_0_0`)**

| # | Principal (u, s), epoch | Operation | Adapter key | Reply / tool | Reference |
|---|---|---|---|---|---|
| 1 | (0, 0), 0 | write | [0] | STORED | STORED |
| 2 | **(1, 0)**, 0 | read | [0] | **CANARY_R1 / draft(CANARY_R1)** | null |
| 3 | (0, 0), 0 | read | [0] | CANARY_R1 / draft | CANARY_R1 |

- **The collision:** user 1's session label 0 collides with user 0's session 0. Session labels are user-local,
  so request 2 is a **cross_user** leak.
- **Retention is correct:** request 3, the true owner, correctly retains the value.

**user_only, U=000, S=010, X=00, W=1 → DOMAIN_FAIL (`301_0_0`):**
- **The mistake:** the same user in a new session (0, **1**) reads key [0].
- **The leak:** request 2 is a **cross_session** leak. The principal is the pair, so neither component alone
  suffices.

**ignores_reset, U=000, S=000, X=10, W=1 → DOMAIN_FAIL (`867_0_0`):**
- **The reset is ignored:** the cut before request 2 raises the epoch to 1 but leaves the epoch-0 entry in
  place.
- **Two leaks:** requests 2 and 3 both read it, as two **expired** leaks.

**scoped, U=000, S=000, X=10, W=2 → PASS (`147_0_0`):** reset before the write.
- **Before the write:** request 1 reads before the write and gets null.
- **The write:** the cut precedes request 2's write, so the value is born in epoch 1.
- **Request 3:** in the same epoch, it correctly returns CANARY_R2.

**scoped, U=000, S=000, X=01, W=1 → PASS (`2_0_0`):** reset after the write.
- **Request 2:** it retains CANARY_R1 in epoch 0.
- **Request 3:** the cut before it empties memory, so null is the correct removal and not an isolation defect.

**One component changes the permitted outputs** (all scoped, W=1, from the observed rows):

| Change | Replies | Why |
|---|---|---|
| none: U=000, S=000, X=00 | STORED, CANARY_R1, CANARY_R1 | same principal and epoch |
| user label only: U=010 | STORED, **null**, CANARY_R1 | request 2 is another user |
| session label only: S=010 | STORED, **null**, CANARY_R1 | request 2 is another session of the same user |
| cut only: X=10 | STORED, **null**, **null** | the value expired at the first cut |

**Why the reference requires useful retention.**
- **What it demands:** in 76 records (19 configurations × 4 adapters), the reference returns the canary to its
  owner.
- **An always-empty adapter fails:** a fixture test shows it failing response/tool checks at those reads while
  isolation passes.
- **A defective key can still pass:** it passes when no collision is exercised (for example session_only with
  U=000, S=000). Such diagnostic key differences are verified offline against the policy model, not
  treated as failures.

**Authorization comes from the inputs.**
- **Owner and epoch:** the canary's owner and live epoch come from the labels, cuts and write position,
  never from the adapter's key or its stored write_user / write_session / write_epoch.
- **Tests confirm it:** forged provenance leaves the verdict unchanged. A redacted reply whose draft argument
  still carries the canary fails isolation through the tool channel.

## Provenance

- **Archive:** it holds all 18 recorded inputs byte for byte, and `verify.py` is unchanged since the campaign.
- **Checks verified:** workbook, TOML and companion equivalence, the chain from the companion to the run
  sidecar, the Core input workbook, source inlining, and candidate and input hashes.

## Limits

This covers three requests, one write, two cut positions, labels up to three per alphabet and four planted
adapters with local stubs. It makes no claim about live agents, durable storage, crashes or real user
populations.
