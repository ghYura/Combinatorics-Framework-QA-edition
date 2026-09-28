<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D15 results: bounded recovery faults

- **Run:** `d15_20260928T195719Z`. **Databases:** `as0927_d15_20260928t195719z` on 5433 and 5432 (absent before).
  Retained: main 8,419,007 B, results 10,319,551 B; run directory 9,446,730 B; `evidence/` 9,205,576 B,
  `archive/` 4,343,404 B.
- **Input:** primary `spec/demo.xlsx` with its native `demo.constraints.json` (one bond, `nontrivial_partition`),
  cell-, chain-, message- and rule-equivalent to `spec/spec.toml`; run with `--sieve`. No optional axis.
- **Framework build:** accepted v6, no change (checkout `be48836` + the 27 inventoried v6 files).
- **Contract:** v1 `5a456c93…0478`; predictions `bbb3317d…6a01` and `derive.py` `c793a8db…1e9a` unchanged.
- **Envelope:** `generated-default`, origin generated, container sandbox `net=none`, one Executor worker, repeat 1,
  `-Xmx2g`, budgets 400/400/200,000,000 B/1200 s, no override. The Bundle took 477.4 s (Core 9.0, sieve 0.2,
  Reader 13.3, Executor 452.9).
- **Evidence kind:** Verified/run. `verify.py` passed 29/29 at campaign time (14,040 record fields) with no post-run
  change; the same 29/29 from `archive/…/inputs` (23/23 inputs, including the preflight record). The five named
  replays were identical in semantic record, semantic digest and WAL evidence.
- **What ran where:** each candidate started three owned Python worker processes (the inlined `worker.py`, written
  to the sandbox scratch and hash-checked) with their own WAL files, inside the Executor's container. SIGKILL
  and reopen touched only those children. No shared service, network or other process was involved.

## Before the campaign (outside the denominator)

- **Sandbox preflight** (`evidence/preflight-20260928T194928Z/preflight.json`), through the Framework's own
  generated-default sandbox:
  - three fault-free controls: every node ended with counts (1,1,1), value 111 and WAL o1:a1, o2:a1, o3:a1;
  - two all-node restart cases (P=replay_twice|F=012|C=2|K=crash|R=fresh, P=volatile_ack|F=012|C=3|K=crash|R=stable):
    three restarts and three −9 kills each, and semantics equal to the predictions.
- **Tests:** 31 with real local worker processes, including the parser on a locally composed candidate, which
  was also executed. A stratified sample of full cases was compared with the frozen predictions, and the
  verifier's model with all 312.
- **Precheck:** own bond evaluation, the Framework's `row_violations` over the built companion and the AI architect's list
  agree on the 24 rejected identities; own model equals all 312 predictions; a closed-form failure rule matches
  all 312.

## Construction and stage counts

| Stage | Count |
|---|---:|
| Plans (XLSX = TOML, one bond, graph `e2da9a88…` = the AI architect's) | mandatory **EXACT 336**; post-sieve and final **BOUNDED [0, 336]** |
| Core `fw_final` before the sieve (1 × 3 × 7 × 4 × 2 × 2 × 1) | 336 |
| FAIL rows: native FW_Subsets → FW_Combi(size) | 7 nonempty subsets (48 rows each; {0,1,2} 24 after the sieve) |
| Sieve: `nontrivial_partition` (partition AND three failed nodes) | matched 24; 336 → **312** |
| Reader / Executor / results_v2 | 312 / 312 / 312; one attempt each, repeat_idx 0 |
| Client attempts / worker starts / injected SIGKILLs | 1,062 / 1,224 / 288 |
| Outcomes | **216 PASS / 96 DOMAIN_FAIL**; zero BROKEN, INFRA_FAIL or TIMEOUT |

- **Why BOUNDED:** the planner does not evaluate the bond's selectivity ("1 constraint(s) declared"); the mode is
  recorded, not overridden. The live sieve log and the decoded rows show the 24 removals; the raw population
  minus the decoded rows equals the 24 rejected identities (all `F=012`, `K=partition`).
- **Rendering:** a FAIL row's values are written back to back (`fail(0);fail(2);`); the runtime receives them in
  that order and each candidate is byte-exactly its Core row with the recorded endings.
- **Budget notes:** non-blocking warnings for 336 rows and candidates (above 200; limit 400) and the 672 s wall
  estimate (above 600; actual 477.4 s).

## Outcomes and checks

| Implementation | PASS / FAIL | crash | partition |
|---|---|---|---|
| durable | 86 / 18 | 47/9 | 39/9 |
| volatile_ack | 80 / 24 | 41/15 | 39/9 |
| replay_twice | 50 / 54 | 11/45 | 39/9 |

| Failed check | durable | volatile_ack | replay_twice |
|---|---:|---:|---:|
| acknowledged_survive_repair | 0 | **6** | 0 |
| acknowledged_effects_once | 18 | 24 | 54 |
| accepted_logical_ops_once | 18 | 24 | 18 |
| replicas_agree | 0 | 0 | 36 |
| matches_fault_free_reference | 18 | 24 | 54 |
| all_logical_ops_acknowledged / final_wal_matches_accepted | 0 / 0 | 0 / 0 | 0 / 0 |

- **Client-key duplication (not a storage bug):** in every implementation the 18 cases with exactly two unavailable
  nodes, c<3 and a fresh retry key fail. One replica kept the timed-out o(c+1):a1 and repair spread it; the fresh
  retry o(c+1):a2 then adds a second logical effect. With stable keys the retry deduplicates, and durable+stable
  passes all 52 cases.
- **Missing work:** volatile_ack loses the acknowledged prefix when all three nodes crash at c>0 (6 cases:
  `acknowledged_survive_repair` fails).
- **Duplicate replay:** replay_twice fails every crash with a nonempty prefix (42 cases) plus the 12 fresh-key cases
  outside those. 36 of its failures leave replicas disagreeing; in the others all replicas agree on the same wrong
  state.
- **Controls:** all cut-3 partitions pass (nothing in the fault window).

## Walkthroughs (replayed)

**Partial quorum, stable key, convergence (`37_0_0`, durable, F=01, C=1, crash → PASS).** o1 is acknowledged by
all three. n0 and n1 are killed (−9). The window write o2:a1 reaches only n2: TIMEOUT, but n2 keeps it. n0 and n1
are reopened as generation 1 and reload o1:a1 from their WALs. Repair merges {o1:a1, o2:a1} everywhere; the
stable retry o2:a1 is a duplicate key (no new effect). o3 follows, and all nodes end with value 111.

**Fresh key duplicates the uncertain operation (`40_0_0`, durable, F=01, C=1, partition, fresh → DOMAIN_FAIL).**
Same partial write, but the gate keeps n0/n1 alive. After repair every node holds o2:a1; the retry o2:a2 is a new
key, so o2 is applied twice: effects o1, o2, o2, o3, value 121 on all nodes. Replicas agree and every WAL matches
its accepted keys, yet `accepted_logical_ops_once`, `acknowledged_effects_once` and the reference check fail.

**Acknowledged work lost (`217_0_0`, volatile_ack, F=012, C=2, crash → DOMAIN_FAIL).** o1 and o2 are ACKed from
memory (WALs still empty at `prefix`). All three workers are killed; reopened workers load empty WALs (value 0),
so the acknowledged o1 and o2 are gone at `repaired`. Only o3 survives (value 100).

**Double replay on one node (`237_0_0`, replay_twice, F=0, C=3, crash → DOMAIN_FAIL).** All three operations are
stored durably. Only n0 restarts; it accepts each key once but applies its WAL twice (effects o1, o2, o3, o1, o2,
o3; value 222) while n1/n2 stay at 111. Merge adds no key and never rebuilds effects, so the replicas disagree.

**Uniform wrong state (`333_0_0`, replay_twice, F=012, C=3, crash → DOMAIN_FAIL).** All three nodes restart and
double-apply: every node reports 222, accepted keys and WALs are identical and unique. `replicas_agree` passes; only
the fault-free reference (and `acknowledged_effects_once`) reveals the defect. Convergence alone would hide it.

## Evidence and provenance

- **Per record:** attempts (op, key, phase, targets, status), every checkpoint snapshot (running, reachable,
  generation, accepted, WAL from the file, effects, counts, value), the seven checks, the semantic digest, the
  final WAL lines of all three nodes with their byte hashes, the final accepted and WAL payloads (equal per node),
  and provenance: every start (PID, generation, argv, WAL hash at start), every kill (SIGKILL, return code −9,
  WAL hash after) and every exit (return code 0).
- **PIDs are container-local:** each candidate runs in a new container with its own PID namespace, so worker PIDs
  repeat across candidates and in the replays (for example 7, 8, 9). They identify processes within one candidate
  run only.
- **Archive:** all 23 recorded inputs byte for byte, including the preflight record and the campaign-time verifier.

## Limits

A three-replica toy append service with three operations, one fault per schedule and cuts at operation
boundaries. SIGKILL tests loss of process memory with an intact (tmpfs) filesystem, not power failure or storage
durability; the partition is a coordinator write gate, not a kernel or network fault. No Raft, linearizability,
timing or probabilistic coverage claim.
