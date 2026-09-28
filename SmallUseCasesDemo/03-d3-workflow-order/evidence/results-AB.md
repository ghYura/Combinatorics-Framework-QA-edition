<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D3 phases A/B results: workflow order and checkpoint observation

| | Run A | Run B |
|---|---|---|
| Run ID | `d3a_20260927T181801Z` | `d3b_20260927T181920Z` |
| Databases (5433 and 5432) | `as0927_d3a_20260927t181801z` | `as0927_d3b_20260927t181920z` |

- **Input:** `spec/A|B/demo.xlsx`, with matching TOML. No sieve and no companion.
- **Framework build:** D1-accepted v2, checked unchanged.
- **Contract:** v1 `7d55f11c…3961`.
- **Evidence kind:** Verified/run. `verify.py` passed A 23/23 and B 24/24; replays were 5/5
  byte-identical.

## Question and model

**Question.** Does a tiny billing ledger keep its contract when charge (C), refund (F) and renew
(N) come in any order or repeat, and when a restart (S) or reconcile (Q) happens afterwards?

**Model.** Every operation is observed right after it executes, and all four fields plus four
invariants are compared with an independent reference.
- **A:** `OPS = FW_Permut() → FW_Combi(size)` over C,F,N; S and Q are `FW_Optional`.
- **B:** `OPS = FW_PermutR(3) → FW_Combi(size)`.
- **Policies:** one correct policy and two deliberate fault variants.

## Stages

| | A | B |
|---|---:|---:|
| Plans (XLSX = TOML graph) | EXACT 18 mandatory × 4 optional = 72 | EXACT 81 |
| Core per sheet (after DISTINCT) | HEAD 1, IMPL 3, OPS 6, S 1, Q 1 | HEAD 1, IMPL 3, OPS 27 |
| Core tables | `fw_final` 18, `fw_opt1` 2, `fw_opt2` 1 | `fw_final` 81 |
| Rendered identities / attempts | 72 / 72 (18 × {none, S, Q, S+Q}) | 81 / 81 |
| Outcomes | 48 PASS / 24 DOMAIN_FAIL | 66 PASS / 15 DOMAIN_FAIL |
| Hidden by a final-only check | 4 | 0 |

**Per policy:**
- **A:** correct 24/0, refund_unchecked 8/16, restart_cache 16/8.
- **B:** correct 27/0, refund_unchecked 12/15, restart_cache 27/0.

**Agreement:** every field of every trace equals both the frozen `architect-derived.json` and the
verifier's own model (1,944 fields in A, 2,187 in B). There were no BROKEN, INFRA_FAIL or TIMEOUT
outcomes.

**B-alt**, `FW_CombiR(3) → FW_Permut(…IDENTICAL)`, was planned only; there was no campaign.
- The planner gives BOUNDED [3, 180]; OPS is BOUNDED [0, 60] because identical-duplicate
  permutations have no injectivity certificate.
- An independent enumeration gives 10 multisets → 27 distinct orders, the same set as B's product.
- This is Derived, not measured Core support.

## Witnesses

| Case | Candidate | Checkpoints (captures, refunds, balance) |
|---|---|---|
| `A\|refund_unchecked\|FCN\|S0Q0` | `9_0_0` | k1 F: observed `[0],[1],−100` vs `[0],[0],0`; fails at 1, 2, 3 (refund before charge) |
| `B\|refund_unchecked\|CFF\|S0Q0` | `32_0_0` | k3 F: observed refunds `[2]`, −100 vs `[1]`, 0 (duplicate refund) |
| `A\|restart_cache\|CNF\|S1Q1` | `14_1_2` | k4 S: balance 0 vs 100 → **FAIL**; k5 Q: 100 = 100. Main verdict DOMAIN_FAIL; **final-only PASS** |
| `A\|restart_cache\|CNF\|S1Q0` | `14_1_1` | k4 S is the final checkpoint: balance 0 vs 100; both verdicts DOMAIN_FAIL |
| `A\|correct\|CNF\|S1Q1` (control) | `2_1_2` | all five checkpoints ok |

## Checkpoints vs end state

The two checks answer different questions:
- The **final-only** check asks whether the ledger is right when the workflow ends.
- The **checkpoint** check asks whether it was ever wrong while the workflow ran.

Reconcile (Q) repairs the balance that `restart_cache` lost at S. So the end state is correct in
all 4 A cases where S is followed by Q, even though a reader between S and Q saw 0. Only per-step
observation reports those 4 cases.

Conversely, the end state and the checkpoints agree whenever nothing repairs the fault; the
refund faults are an example.

## Limits

This is a local, deterministic state-machine demonstration: three operations, two optional sudden
actions, three explicitly chosen policies and uniform case weights. It makes no claim about real
banks, durable storage, concurrency, arbitrary workflows or production defect rates.

**Contract reading.** The C rule was applied literally: charge iff `captures[epoch]` is zero. See
the delivery note.

**Phase C** (six-event coverage) is still pending, so D3 is not complete.
