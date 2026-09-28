<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D13a results: bounded tool-call policy traces

- **Run:** `d13a_20260928T091033Z`. **Databases:** `as0927_d13a_20260928t091033z` on 5433 and 5432.
  - Retained sizes: main 8,451,775 bytes, results 8,623,807 bytes; the run directory is 10,437,696 bytes.
- **Input:** primary `spec/demo.xlsx` (cell-equivalent to `spec/spec.toml`). No sieve.
- **Framework build:** accepted v6, no change.
- **Contract:** v1 `32ffeb77…2495`; predictions `b8ccdcfb…607f` and `derive.py` unchanged.
- **Envelope:** `generated-default`, one worker, K=1, `-Xmx2g`, budgets 150 mandatory / 500 final /
  100 MB / 1200 s, no override. The Bundle took 306 s.
- **Evidence kind:** Verified/run. `verify.py` passed 22/22 and gave the same 22/22 from
  `archive/…/inputs`. Replays were 5/5 byte-identical.
- **Tools are inert:** every tool is a local stub. A "send" appends to an in-memory list, and the canary
  is a fixture string. This is a deterministic orchestration test, not live-agent safety evidence.

## Framework construction and stage counts

- **Mandatory sheets:** HEAD, IMPL (4 policies), REPETITIONS (N = 1, 2), READ_MODE (F = 0, 1), ORDER
  (`plan("A")`, `plan("R")`, `plan("S")` through `FW_Permut() → FW_Combi(size)`) and TAIL.
- **Optional sheet:** REVOKE (`FW_Optional`, four `set_revoke(cut)` fragments; absence means no
  revocation) sits before ORDER.
- **Runtime:** expands the S block to N adjacent requests. This is a controlled repetition, not every
  four-action word.

| Stage | Count |
|---|---:|
| Plans (XLSX = TOML graph) | mandatory EXACT 96, optional multiplier EXACT 5, final EXACT 480 |
| Core `fw_final` (mandatory support, 4 × 2 × 2 × 6) | 96 |
| Core `fw_opt1` (REVOKE cuts 0..3) | 4 |
| Assembled = Reader = Executor = results_v2 | 480 = 96 × (absent + 4); one attempt each |
| Outcomes | **454 PASS / 26 DOMAIN_FAIL**; zero BROKEN, INFRA_FAIL or TIMEOUT |

- **Identities:** the 480 identities reassembled from the 96 mandatory rows and the 4 optional rows
  equal the rendered and executed identity sets.
- **Rendering:** `set_revoke` is rendered at its sheet position, before the ORDER fragments, in all 384
  candidates that have it, and it is absent in the other 96.
- **Tool errors stay contained:** every controlled read error was caught inside the orchestrator; none
  escaped to the Executor.
- **What 480 means:** it is the assembled candidate count, not the raw mandatory Core count (96).

## Outcomes and the checks behind them

| Policy | PASS / FAIL | Violation kind (count) |
|---|---|---|
| guarded | 120 / 0 | — |
| sticky_approval | 116 / 4 | unapproved_emit (4) |
| success_only_taint | 106 / 14 | tainted_emit (14) |
| no_dedup | 112 / 8 | duplicate_emit (8) |

**Two checks decide a verdict:**
- **Prefix check (policy-blind):** authorization and taint come from earlier events only, never from
  the orchestrator's own flags.
- **Reference comparison:** each response (request, action, payload) and the outbox must equal the
  independently derived guarded responses.

**A deny-all controller would not pass.** The guarded reference emits in 16 of the 120 configurations,
so blocking everything fails those.

**Failures by axis:**

| Axis | Where the failures fall |
|---|---|
| Repetitions | no_dedup fails only with N = 2 (8). sticky_approval (2 and 2) and success_only_taint (7 and 7) fail equally with N = 1 and N = 2. |
| Read failure | success_only_taint fails only when the read fails (14 of 60). The other policies are unaffected by F. |
| Revocation cut | sticky_approval fails only at cut 1, a revocation between A and S (4). success_only_taint fails at cut none, 0 and 3 (4 each) and cut 1 (2). no_dedup fails at every cut except 1 (2 each). |
| Order | sticky_approval: ASR (4). no_dedup: ASR (8). success_only_taint: ARS (6) and RAS (8). |

**Counts kept apart:** 480 Framework execution attempts contained 720 send requests, which produced 90
outbox effects. The internal requests are not Framework repeats.

## Mechanism timelines (replayed; local state vs the oracle's prefix evidence)

**sticky_approval, ASR, N=1, F=0, X=1 → DOMAIN_FAIL (`26_2_1`)**

| Event | Local approved/tainted | Prefix approved/tainted |
|---|---|---|
| approve | T / F | T / F |
| revoke(1) | **T** / F (ignored) | **F** / F |
| send_result #1 → emit PUBLIC | T / F | F / F → **unapproved_emit** |

**guarded, same case → PASS (`2_2_1`):** after revoke(1) the local flag is F, and the send is
`block(no_approval)`.

**success_only_taint, ARS, N=1, F=1, X=none → DOMAIN_FAIL (`55_0_0`)**

| Event | Local tainted / buffer | Prefix tainted |
|---|---|---|
| read_chunk | **F** / D13A_LOCAL_CANARY | **T** |
| read_error | F / canary | T |
| send_result #1 → emit **D13A_LOCAL_CANARY** | F | T → **tainted_emit** |

The read tool failing does not undo a chunk that was already delivered. Treating only `read_ok` as the
taint source misses partial output from a failed read.

**no_dedup, ASR, N=2, F=0 → DOMAIN_FAIL (`86_0_0`):** emit #1 is followed by emit #2 of the same
`notice-1`, so the outbox holds two effects and #2 is a **duplicate_emit**.

**guarded, ASR, N=2, F=1, X=3 → PASS (`20_4_1`):**
- **Sequence:** emit #1 (PUBLIC), then dedup #2, then read_chunk, read_error and revoke(3).
- **No retroactive invalidation:** the later taint and revocation do not invalidate the earlier
  authorized PUBLIC emission.
- **Final flags mislead:** the final state is approved = F, tainted = T, which would make a final-flags
  oracle unsound here.

## Limits

This covers six base orders, N ≤ 2 adjacent repeats, one read mode axis, one optional revocation and
four planted policies, with equal weight per configuration. It is not an exhaustive interleaving of
arbitrary calls, and it makes no claim about real agents, tools, networks or safety certification.
