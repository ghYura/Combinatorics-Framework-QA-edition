<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D15 — Bounded recovery faults, contract v1

Implement independently here. Preserve this contract, derive.py and
architect-derived.json. Predictions are not candidate inputs. The Framework
generates schedules; a new local harness injects faults and a separate oracle
checks recovery. This is a deliberately small replicated append service, not
Raft, a linearizable database, a Jepsen replacement or a power-loss test.

## Population and declared service

Three replicas n0,n1,n2; three logical operations o1,o2,o3 with increments
1,10,100. A transport key names an attempt, initially oi:a1. A record is
`{key, op, delta}`; different keys may name the same logical operation. Each
replica deduplicates by key. Matching duplicate keys return success without
another effect; conflicting payloads for one key are rejected as malformed.
All operations and replication sends are serial, in replica index order.

The coordinator writes to every reachable replica. Two successful replies give
ACK; zero or one gives TIMEOUT even when the one responding replica stored a
record. Partial writes are retained. There is no rollback, election or commit
index. Recovery merges the union of accepted records. This bounded protocol
intentionally permits an uncertain operation to survive a timeout.

Detect violations of the end-to-end target: after recovery, every acknowledged
logical operation has one effect, the accepted logical records contain each
operation once, and all replicas agree with the fault-free value 111. Compare
logical multiplicities, not just sums. Fresh transport keys on a retry can
violate this target even with a correctly durable server; do not call that a
storage bug. No timing statistics or probabilistic coverage claim is involved.

Axes: three implementations × seven nonempty failed-node subsets × four cuts
0,1,2,3 × crash/partition × stable/fresh retry = 336 raw Framework cases. The
sieve excludes partition with all three nodes (24 rows), leaving 312 equally
weighted cases, 104 per implementation. The cut is the number of completed
operations before the fault. Preserve labelled subsets and cuts independently;
do not quotient equal final outcomes. Cut 3 partitions are intentional controls
with no operation in the fault window, while cut 3 crashes test stored work.

## Worker implementations and real persistence

Each candidate launches exactly three owned Python subprocesses, using JSON-line
requests/replies over pipes and separate tiny WAL files in its sandbox scratch
directory. A worker owns its accepted-key map and materialized effect list.
It loads state from its WAL when launched. Never reconstruct it from parent
memory or predictions. WAL records are UTF-8 canonical JSON (sorted keys, compact
separators), one newline per record, with no timestamps. Retain append order.

- `durable`: on a new key append the full record, flush and call os.fsync;
  then accept the key, apply its operation once, and reply. Startup loads the
  unique accepted keys and applies every WAL record once in file order.
- `volatile_ack`: accept/apply/reply without writing the WAL. A maintenance
  flush writes pending records in acceptance order and fsyncs. Crash loses
  pending memory. Startup replays only the actual WAL, once.
- `replay_twice`: put/dedup/persistence are durable; startup builds accepted
  keys once but applies the complete WAL twice (two full passes). Initial empty
  WALs make this harmless until a restart. Do not corrupt the WAL itself.

Use worker operations put, snapshot, merge and flush (names may vary). Merge
receives the sorted union of accepted records, puts missing keys in that order,
then flushes all pending records. It must not reset materialized effects;
otherwise repair would hide the replay bug. Flush never applies another effect.
On final flush, WAL key order equals prior WAL order followed by pending keys
in acceptance order. IDs, payloads and types are validated on every IPC input.

Crash means SIGKILL of only the selected Popen-owned workers at a quiescent
boundary, followed by wait/reaping; expected return code -9 is an injected fault.
No signal targets a pre-existing process. Reopen each killed node with a NEW
worker using the same WAL file. Unselected workers stay alive. No close handler
or destructor may flush the killed process. Partition is a deterministic gate
on coordinator writes to the selected subset; workers stay alive. Supervisor
diagnostic snapshots may still inspect them. It is not a kernel/network fault.

Record startup/restart PID, node, generation (0 initial, 1 restart), command,
kill/wait results and WAL byte hashes as provenance. Observe WAL bytes from the
filesystem independently of the worker's accepted map. Include final WAL bytes
or canonical contents in the observation so the archive retains the evidence
when the normal sandbox lifecycle ends. Never touch shared services for faults.
SIGKILL tests loss of process memory with an intact filesystem, not power failure
or physical storage durability; sandbox tmpfs and fsync have that same limit.

## Exact schedule (also formalized in derive.py)

1. Start empty workers; snapshot `initial`. Execute o1..oc at all three nodes,
   recording ACK attempts; snapshot `prefix` (also when c=0).
2. Inject the selected fault; snapshot `faulted`.
3. If c<3, attempt o(c+1):a1 against the reachable complement; snapshot `window`.
   Record ACK or TIMEOUT based solely on the reply count. If c=3 omit this step.
4. Reopen crashed workers or remove the partition gate; snapshot `reopened`.
5. Read accepted records from all workers, take the key-sorted union, and merge
   it into each worker in node order; flush; snapshot `repaired`.
6. Only if the window attempt timed out, retry it once, now against all nodes:
   `stable` keeps oi:a1, `fresh` uses oi:a2. Snapshot `retry`. This must ACK.
7. Execute the remaining operations o(c+2)..o3 against all nodes. Flush every
   worker, without rebuilding effects; snapshot `final`.

Attempt fields: op, key, phase (prefix/window/retry/suffix), targets in index
order, status. All successful puts in an attempt complete before its status.
Snapshots are taken only at the named barriers, never with a request in flight.

Each snapshot contains, per node: node, running, reachable, generation,
accepted (sorted key list), wal (keys in actual file order), effects (logical
operations in application order), counts (all three keys, including zeros),
value. Down nodes expose WAL and generation but accepted/effects/counts/value
are null. A partitioned live node is running=true, reachable=false. Snapshot
data must come from workers/files. Derive the logical op and delta from actual
validated records, and also retain their full payloads in the disk evidence.

Identity: `P=<implementation>|F=<sorted node digits>|C=<cut>|K=<kind>|R=<retry>`.
Emit factors, attempts, trace, acknowledged, checks and verdict, plus source
hashes, record digest and provenance. The deterministic semantic portion must
match derive.py's case structure (predicted_outcome maps to verdict). Separately
hash this semantic portion for replay; live PIDs and paths can differ. FW_VAR is
0 for PASS, 2 for DOMAIN_FAIL: IMPL position 2 is a carrier, not causal blame.

## Oracle, predictions and independent verification

The runtime oracle is policy-blind: use observed histories, snapshots and the
fault-free target. Implement these seven checks with the names in derive.py:

- all_logical_ops_acknowledged: ACK history covers o1,o2,o3.
- acknowledged_survive_repair: at `repaired`, each node has at least one effect
  for each logical operation ACKed before recovery (prefix and ACKed window).
- acknowledged_effects_once: final effects count each acknowledged op once.
- accepted_logical_ops_once: final accepted records contain each op once.
- replicas_agree: final accepted records, count vectors and values agree;
  physical WAL order and process identity need not agree.
- matches_fault_free_reference: all final count vectors are (1,1,1), value 111.
- final_wal_matches_accepted: no duplicate WAL keys, and WAL and accepted maps
  contain the same keys AND full payloads after flush.

PASS requires all seven checks. Well-formed lost/duplicate effects are DOMAIN_FAIL.
IPC/file failures, missing replies, unexpected worker exits, malformed records,
bad hashes or timeout are infrastructure errors. Never turn those into a domain
result. A harness-induced expected -9 exit alone is not an infrastructure error.

Derived results: **216 PASS / 96 DOMAIN_FAIL**: durable 86/18, volatile_ack 80/24,
replay_twice 50/54. Durable+stable passes all 52 cases. Fresh retries duplicate
the uncertain operation exactly when two nodes were unavailable and c<3:
18 cases per implementation. Volatile acknowledgement additionally loses prior
ACKs when all nodes crash at c>0 (six cases). Double replay adds failures whenever
a nonempty prefix is replayed after a crash; account for overlap with retries.
The 312 originals contain 1062 client attempts, 1224 worker starts and 288
injected kills. Report preflight/test/replay counts separately.

Implement a standalone verifier that imports no SUT, harness, oracle, runtime
or derive module. Independently reconstruct the finite transition model and
compare every attempt and snapshot, actual persisted record payload, all checks,
case identities, digests, worker provenance, Core dictionary/rows, rendered
atoms and Executor exports. Do not verify totals alone. A fresh fault-free run
for each implementation must produce exactly three effects/value 111; archive
these three preflight controls outside the campaign denominator.

Focused tests: ACK before/after fsync; actual killed-worker pending loss versus
durable reload; double replay with unique WAL keys; partial quorum and stable
versus fresh retry; all-node crash; partition without restart; cut 0 and cut 3;
convergence masking uniform wrong state; merge deduplication; malformed IPC;
ownership and exit guards; tampered traces; renderer/parser; verifier independence.
Preflight the largest restart case in the real generated-default sandbox.

## Framework, envelope and delivery

Mandatory slots: HEAD, IMPL, FAIL, CUT, KIND, RETRY, TAIL. IMPL has three choices;
CUT four; KIND/RETRY two each. FAIL has atoms fail(0); fail(1); fail(2); and the
native chain FW_Subsets → FW_Combi(size): eight first-pass subsets, seven second
pass rows because the empty input is skipped. Nonempty subsets are intentional.
Other slots explicitly use FW_Combi(1) → FW_Combi(size). Do not replace native
subset generation with a catalogue or Python loop. TAIL executes the schedule.

Use a forbid assert bond: KIND equals fault("partition"); AND FAIL count=3.
Primary XLSX must carry its sidecar and equal the TOML input. --sieve is required.
Sizing plan: mandatory EXACT 336; post-sieve/final BOUNDED [0,336]. Independently
derive 24 rejected / 312 valid and verify the live sieve; do not label its loose
bound exact. No optional expansion. Preserve raw/post-sieve counts and rejected
identities. IMPL position and selected FAIL atoms must survive rendering.

Provide worker/SUT, harness, oracle, runtime, builder, offline explorer/verifier,
run wrapper, replay and focused tests. All runtime source must be local and
hashed/inlined, including the actual worker entry script. Use stdlib only and
generated-default, generated origin, network none, one Executor worker, repeat 1.
At most three node workers concurrently; use bounded IPC waits and reap all owned
children when done. JVM -Xmx2g; new main/results DBs as0927_d15_<stamp>, absent
on both ports. Budgets: mandatory/final 400, disk 200000000 bytes, wall 1200 s;
no override. Preflight disk, plans/equivalence, sidecar, parser and sandbox.

Run one campaign. Replay these five complete archived candidates through the
same sandbox; require identical semantic records/digests and record fresh PIDs:

- P=durable|F=01|C=1|K=crash|R=stable
- P=durable|F=01|C=1|K=partition|R=fresh
- P=volatile_ack|F=012|C=2|K=crash|R=stable
- P=replay_twice|F=0|C=3|K=crash|R=stable
- P=replay_twice|F=012|C=3|K=crash|R=stable

Archive source/input/build hashes, plans, constraints, Core/Reader/Executor
counts and identities, commands, logs, complete observations/provenance,
WAL payload evidence, focused tests, verifier outputs and replays. Walk through
the five mechanisms and distinguish storage defects from fresh-key client
semantics. G1–G7 in ../README.md apply. Preserve accepted examples,
Framework v6 and prior evidence. Necessary evidenced fixes remain authorized.
No external calls, canonical run, broad tests, cleanup of retained artifacts,
pull, commit or push. Communicate by EEST Markdown here; do not start example 23.
