# 25 — Plan-2: Control-Plane ADR, Current-Path Baseline & Increment Report

> **Dated implementation record (2026-06-22).** The standalone Java control-plane work described
> here still exists, but it must not be read as the Bundle launcher's entire supported matrix.
> The launcher has narrower language/transport/pool/repeat boundaries; see
> [document 21](21_ARCHITECTURE_DECISIONS.md) and the
> [2026-07-21 code audit](CURRENT_CODE_AUDIT_2026-07-21.md).

**Author:** Claude Opus 4.8, 2026-06-22 (at Yuri's direction: "plan for yourself and implement Plan 2").
**Status:** ADR proposed (to be promoted into `21_ARCHITECTURE_DECISIONS.md` on Automation acceptance);
control-plane increment **landed + green** in `Analyzer_trunk`.
**Companion:** [document 24](24_PLAN1_PHASE0_CONTRACT_DELTA.md) (Plan-1, which this executes).
The historical combined plan containing the original Plan-2 specification is not included in this
publishable tree; its implemented constraints are preserved in this ADR and baseline. This is the
Phase-8 deliverable (ADR + current-path baseline) plus the first Phase-9 increment (the runtime control
plane), delivered together.

---

## A. Current-path baseline (traced, not assumed)

What dispatch looks like **today**, with file:symbol evidence — the thing Plan-2 evolves:

- **`LineExecutor`** (`Analyzer_trunk/.../optimization/LineExecutor.java:21`) — the execution seam:
  `String execute(int lineNo, String raw)`. One candidate in, metric text out.
- **`LineExecutor.RemoteWorker`** (`LineExecutor.java:264`) — the remote dispatcher: writes the
  candidate file into `srcDir` (atomic move, `:321-337`) then **polls a single candidate id in a
  blocking loop until a result row or timeout** (`execute`, `:314-360`). It is **sequential and
  single-candidate** — one `execute` call blocks one thread until that candidate resolves. The loop
  **honours `Thread.interrupt()`** (`:354-357`, returns `remote_status=interrupted`).
- **`RemoteWorker.ResultPoller`** (`:269`) — the poll seam, `Map<String,String> pollOnce(String
  candidateId)`. **`JdbcPoller`** (`:374`) is the production implementation:
  `SELECT <cols> FROM <table> WHERE <idColumn> = ? LIMIT 1`, fresh connection per call (`:412-435`).
  Keyed by **`candidate_id` only** today.
- **Plan-1 results identity is already landed** (`Executor_trunk/.../ResultsV2SchemaMigrator.java:55-69`,
  `ResultsV2Writer.java:132-134`): `results_v2` carries `repeat_idx integer NOT NULL DEFAULT 0` and
  `env_id text NOT NULL DEFAULT ''`; the sample key is `(run_id, candidate_id, attempt, repeat_idx,
  env_id)` with idempotent `ON CONFLICT … DO NOTHING`. So the **schema the control plane must target
  exists**.
- **Loom is already in the stack, on the stable API** — `Executors.newVirtualThreadPerTaskExecutor()`
  (Core `SheetWorker.java:255,855,1155`; Reader `ComboGenerationPipeline.java:168`) and
  `Thread.ofVirtual()` (Executor `MainWatch.java`, ~25 sites). **No module uses the preview
  `StructuredTaskScope`; no pom sets `--enable-preview`.**
- **Packaged driver:** `org.postgresql:postgresql:42.7.11` (Analyzer pom) — past the pgjdbc
  `synchronized`→`ReentrantLock` migration that caused virtual-thread carrier pinning.

**Conclusion:** Plan-2 is an *evolution of `RemoteWorker`'s poll seam into a concurrent, policy-aware
orchestrator*, not greenfield — consistent with the historical Plan-2 design summarized by this ADR.

---

## B. ADR-8 — Plan-2 runtime control plane (revises ADR-1, ADR-2, ADR-7)

**Decision.** Introduce a Java virtual-thread **control plane** (`BundleControlPlane`,
`Analyzer_trunk/.../optimization/BundleControlPlane.java`) that owns *runtime execution
orchestration*: expand a plan into `(candidate, repeat_idx, env_id)` work units per Plan-1
`repeatPolicy`, fan them out on virtual threads, bound in-flight work, serialize latency-sensitive
candidates per host, enforce a budget deadline with cooperative cancellation, and collect results
keyed by the Plan-1 identity. **Experiment design / spec authoring / planning stays Python**
(fwgen, ZEN, `[[goals]]`, budget, testme5) — only the dispatch/measurement-orchestration plane moves
to Java/Loom, as recorded by this ADR.

**Rationale.** The dispatch profile is I/O-bound, high fan-out, lots of blocking (DB poll, IPC to
Executors) — the canonical virtual-thread case; and it is homogeneous with the already-Java Data
Plane + JDBC results DB. Plan-1 has stabilized the run/candidate/result contracts (the `repeat_idx`/
`env_id` identity), which is the precondition ADR-7 set for scaling.

**How it revises the existing ADRs:**
- **ADR-1 (Generator owns the control plane, in Python).** *Refined:* the Generator keeps the
  *planning* control plane (Python); the **runtime dispatch** control plane is Java/Loom. The Python
  front-end calls it (or emits the plan it consumes). Planning ≠ dispatch.
- **ADR-2 (components independently runnable, file/manifest comms).** *Preserved and extended:* the
  control plane still talks to Executors through the existing file-drop + results-DB poll (the
  `RemoteWorker`/`ResultPoller` seam) — no in-process candidate execution, clean process boundaries.
  It coordinates those boundaries concurrently rather than serially.
- **ADR-7 (scale follows contract stabilization; "no remote orchestration yet").** *Advanced:* the
  contracts are now stable (Plan-1), so the deferred remote orchestration is now in scope. The
  control plane is the "deterministic worker pool + backpressure on top of the stable contracts"
  ADR-7 named.

**Consequence / boundary.** The control plane is **I/O coordination only** — it must not run metric
crunching (Welford/NSGA-II stay on platform threads in the Analyzer; §P2.4). It composes the existing
seam rather than replacing it: `K=1` is byte-identical to today's sequential `RemoteWorker` (verified
parity). Real *scale across E environments* needs a multi-instance Executor pool (infra) — the
machinery is built and verified with stub executors now; the scale gate stays infra-gated (§E).

---

## C. Resolved design decisions (the doc-22 set relevant to Plan-2)

- **#1 Identity (sample vs retry).** The control plane's `WorkUnit(candidateId, repeatIdx, envId)`
  maps 1:1 onto Plan-1's `(candidate_id, repeat_idx, env_id)` sample identity; `run_id`/`attempt`
  remain Plan-1's, untouched. Every emitted unit is identity-unique (verified, all three policies).
- **#8 ADR.** This document (§B).
- **#9 Java-21 preview decision — RESOLVED: use the stable virtual-thread API, not preview
  `StructuredTaskScope`.** Virtual threads are final in 21; `StructuredTaskScope` is preview
  (`--enable-preview`). The Bundle already standardizes on `newVirtualThreadPerTaskExecutor()` /
  `Thread.ofVirtual()` and enables no preview flags. `BundleControlPlane` therefore uses
  one-vthread-per-unit + `Semaphore` backpressure + `Future` join with a deadline +
  `shutdownNow()` cancellation — the same "fan-out → join → deadline/cancel" structure with **zero
  build-flag churn** and full stack consistency.
- **#10 JDBC pinning — partially resolved.** Packaged driver is pgjdbc **42.7.11** (post-pinning-fix).
  The control-plane orchestration itself is **pin-free**: `BundleControlPlaneVerify` run under
  `-Djdk.tracePinnedThreads=full` reports **0** pinning events. The *live-DB* `JdbcPoller` path under
  load still needs a JFR `jdk.VirtualThreadPinned` run against a real Postgres — **infra-gated** (§E).
  If a future driver pins, the fix is the documented fallback: run the blocking poll on a small
  bounded platform-thread pool, keep orchestration on vthreads.
- **#11 Cancellation.** `cancel()` (and the budget deadline) stop new dispatch and `shutdownNow()`
  interrupts in-flight units; `RemoteWorker`'s interrupt-aware loop unwinds; the result corpus stays
  complete (cancelled units recorded, not dropped). Verified: a 150 ms budget over 5 s units returns
  in ≤ 3 s with 0 completed / 10 accounted-for.
- **#12 Performance vs baseline at equal counts.** Claims are made only against the sequential
  `RemoteWorker` at equal candidate/repeat/env counts (the parity test is that baseline). No "no GIL"
  credit is claimed; backpressure saturation and per-host serialization are measured, not asserted.

---

## D. What landed

- **`Analyzer_trunk/.../optimization/BundleControlPlane.java`** (new). Public API: `RepeatPolicy`
  {LOCAL, DISPERSE, NESTED}; `Candidate`, `WorkUnit`, `UnitResult`, `RunStats`, `RunResult` records;
  `Config` (+ `fromProperties` reading `fw.controlplane.{policy,repeatK,envs,maxInFlight,
  serializePerHost,budgetMillis}`, falling back to Plan-1 `fw.executor.*`); `UnitExecutor` seam +
  `remoteWorkerExecutor(...)` bridge to the existing `RemoteWorker`; `planUnits(...)` (assignment) and
  `run(...)` (fan-out) and `cancel()`.
  - **Assignment strategies:** local = K pinned to one env, candidates round-robin the pool;
    disperse = each candidate's K repeats rotated across envs (balanced block, §4.5); nested = K on
    each of E envs.
  - **Backpressure:** `Semaphore(maxInFlight)`; observed max in-flight is recorded.
  - **Per-host serialization (§P2.3 #6 / §4.4):** per-env `Semaphore(1)` when `serializePerHost`, so
    one latency-sensitive candidate per host at a time while distinct hosts run in parallel.
  - **Budget/cancel (§P2.5):** deadline + `shutdownNow()` interrupt; corpus stays complete.

**Follow-on increments (2026-06-22, same day, Automation-gate lifted by Yuri):**
- **Dispatch → aggregation join (§P2.3 #4).** `toAggregatorCorpus(RunResult)` turns COMPLETED units
  into `candidate_id=… repeat_idx=… env_id=… <metric>` lines (dropping the RemoteWorker envelope);
  `aggregate(RunResult, goals)` hands them to Plan-1's `RepeatAggregator` → per-candidate median +
  order-statistic CI. **Scoped to one-env-per-candidate (`local`/within-env)** — `RepeatAggregator`
  enforces a single `env_id` per candidate; cross-env decomposition for disperse/nested (between-env
  σ²) is the Plan-1 §5 #12 extension, still open.
- **Metric-type serialization (§P2.3 #6).** `MetricSensitivity{DETERMINISTIC,NOISY}` +
  `serializePerHostFor` + `Config.forMetric` + `fw.controlplane.metricSensitivity` (noisy ⇒ serialize;
  explicit `serializePerHost` wins). The dispatcher now *derives* the per-host limit from the metric.
- **Repeat/env-aware poller (§P2.3 #4).** `RepeatEnvJdbcPoller` keys the `results_v2` SELECT on
  `(candidate_id, repeat_idx, env_id)` (vs the legacy `candidate_id`-only poller); `jdbcUnitExecutor`
  wraps it interrupt-aware. `buildSelectSql` is pure + unit-tested; the **live poll stays infra-gated**.
- **Plan JSON seam (§P2.3 #1, Java side).** `Plan.fromJson` ingests a Python-emitted plan; `main()` +
  `unitsToJson` emit the expanded dispatch plan (`candidates × K = executions`) as a dry-run preview.
  The **Python emitter mirror is the one remaining seam piece.**
- **`BundleControlPlaneVerify.java`** now **47 assertions across 13 groups** (added: join,
  metric-sensitivity, JDBC-SQL, plan-JSON round-trip), registered in `AllVerifiersRunner`.

### Target scale (the load-bearing premise — confirmed with Yuri 2026-06-22)
The ADR-8 ROI/necessity case rests on a **production target of hundreds–thousands of Executors**. At
dozens, a Python `asyncio`/threadpool dispatcher would be adequate and Java would not be necessary. At
hundreds–thousands the case becomes decisive: (a) the existing **blocking** `RemoteWorker` seam scales
on Loom *without* an async rewrite, where a Python thread pool hits the OS-thread ceiling; (b) thousands
of concurrent polls demand connection pooling + the `maxInFlight` cap (the connection-per-call
`RepeatEnvJdbcPoller` must move to a pool before that scale is safe); (c) homogeneity with the all-Java
data plane turns a chatty cross-language hot path into in-process JDBC. The *specific* speedup remains
**unmeasured** until a real pool exists (doc 22 #12 — no number credited without a baseline at equal
counts).

---

## E. Acceptance-gate status (Plan-2 §P2.5)

| Gate | Status | Evidence |
|------|--------|----------|
| **Parity** (control plane == current path) | ✅ proven | K=1/local/1-env corpus byte-identical to a sequential `RemoteWorker` loop (`testK1ParityVsSequentialRemoteWorker`). |
| **Budget / cancel** (deadline cancels cleanly) | ✅ proven | 150 ms budget over 5 s units returns ≤ 3 s, complete corpus; explicit `cancel()` likewise. |
| **Backpressure** (bounded in-flight) | ✅ proven | observed max in-flight ≤ and == `maxInFlight`; throttling stretches wall-clock. |
| **Per-host serialization** | ✅ proven | max concurrency per env == 1 under `serializePerHost`, hosts still parallel; contrast case overlaps. |
| **No pinning regressions** | ✅ proven (small scale) | orchestration pin-free under `tracePinnedThreads`; **and the live `RepeatEnvJdbcPoller` path against real Postgres 16.9 / pgjdbc 42.7.11 shows 0 `jdk.VirtualThreadPinned` JFR events (threshold 0)** — see §G. |
| **Scale** (throughput scales with Executors) | ✅ demonstrated (small E) | real run (§H): fixed 24-unit workload, N core-pinned worker processes → real `results_v2` → control-plane collect; wall-clock 1813→1237→831 ms for N=1→2→3 (2.18× at N=3, monotonic; sub-linear from poll interval + worker startup at this scale). |

**Full suite:** `Analyzer_trunk/run-tests.sh` → **27 passed, 0 failed, 1 skipped** (the skip is the
pre-existing optional `SortMockupRun`). Non-regression confirmed.

### G. Live results-DB evidence (2026-06-22, rootless Docker)
With rootless Docker available and `postgres:16.9-alpine` cached, an **isolated ephemeral** Postgres
(`127.0.0.1:15499`, no volume — zero risk to the canonical results DBs on host `:5432`) was used to run
`BundleControlPlaneLiveDbVerify` (ad-hoc, gated on `-Dcp.test.jdbcUrl`, not in the offline suite). It
seeds a minimal `results_v2`, then over **real pgjdbc 42.7.11**:
- `RepeatEnvJdbcPoller` reads back the correct row keyed by `(candidate_id, repeat_idx, env_id)`; an
  unwritten sample returns `null`.
- the control-plane `jdbcUnitExecutor` collects all C·K=12 units from the live DB, the dispatch →
  aggregation join reproduces the expected medians/CIs, and an unwritten sample takes the real
  poll-until-deadline **TIMEOUT** path.
- **JFR `jdk.VirtualThreadPinned` (threshold 0) = 0 events**, and `tracePinnedThreads=full` shows no
  carrier-pin signature → pgjdbc 42.7.11 does not pin under concurrent polling (decision #10 closed at
  this scale). Connection pooling is still required before hundreds–thousands of Executors (§F).

---

## F. Remaining (honest ledger)

**Pure code: ALL DONE.** No pure-code Plan-2 items remain open.
- **Cross-env aggregation (Plan-1 §5 #12) — DONE.** `BundleControlPlane.aggregateNested(run, goals)`
  decomposes a `nested`/`disperse` run per candidate across environments: point = median of per-env
  medians; **between-env spread** = range of per-env medians (σ²_env proxy); **within-env spread** =
  median of per-env sample ranges (σ²_temporal proxy); `NestedMetricStat.envSensitive()` = between >
  within. **Method is nonparametric by choice**, consistent with the order-statistic CIs of QA
  decision #5 (a parametric nested-ANOVA σ² is a possible future alternative — flagged for review).
  Verified (`BundleControlPlaneVerify`): an env-sensitive candidate shows between-env 100.0 vs
  within-env 3.0 → `envSensitive`; an env-insensitive one shows between-env 0.0.
- **Python plan emitter — DONE.** `generator_trunk/bundle/controlplane.py` (`controlplane_plan` /
  `plan_json` / `write_plan_json`) emits the plan JSON the Java `BundleControlPlane.Plan.fromJson`
  consumes; Plan-1 fields from `BundleConfig.validate_repeat()`, Plan-2 deployment fields as optional
  overrides. Cross-language verified: a Python-emitted nested plan (2 cand × 3 env × K2) → Java
  `main()` → 12 planned units. Tests in `test_bundle_controlplane.py` (7/7). The Python↔Java seam
  (§P2.3 #1) is complete both directions.

**Correction (2026-06-22, after reading Reader): the "Executor pool" + disperse scatter ALREADY EXIST
in the data plane — earlier notes overstated this as missing infra.**
`Reader_trunk/.../sink/LooseFileSink.java:88` does a thread-safe **balanced round-robin across a list of
output directories** (`dirs[Math.floorMod(dirRR.getAndIncrement(), dirs.length)]`), the dir list comes
from `reader.out.outZipDirPathList` (ReaderConfig.java:182-183, comma-separated), and the Executor side
watches a `-srcDirList`. That is exactly Plan-1 §5.4's "round-robin candidate×repeat across the Executor
pool, balanced." So a multi-instance pool = run N Executor instances each watching one round-robin dir —
**not** new container orchestration, and the scatter is already implemented. (Containers/cpusets matter
only for *perf isolation* of noisy metrics, §4.4 — measurement validity, not dispatch existence.)

**Infra-gated (what actually remains for a trustworthy disperse/nested run):**
3. **Run E perf-isolated Executor instances** on the round-robin dirs (cpuset/cgroup or containers per
   §4.4 so parallel candidates don't corrupt each other's latency) and assign `env_id` per dir/instance.
4. **Extend the existing sink scatter to candidate×repeat** with `repeat_idx`/`env_id` tagging (Plan-1
   §5.4/§5.5) — today `LooseFileSink` round-robins *candidates*; disperse needs candidate×K.
5. **Connection pooling** for the poller (the live poll is exercised, §G, but is connection-per-call).

**Architectural note:** the Java control plane's disperse *assignment* (`planUnits` round-robin) overlaps
Reader's existing sink round-robin. For the **push** path the scatter should reuse Reader's sink
(Plan-1 §5.4); the control plane's distinctive value is policy + backpressure + cancel + the
poll/collect + the aggregation join, not reinventing fan-out.

*(Closed since the first cut: live `RepeatEnvJdbcPoller` + live-DB JFR pinning (§G); the Python plan
emitter; and cross-env aggregation §12 — all above.)*

**Status:** all pure-code Plan-2 work is landed and green, and Plan-2 is now **demonstrated end-to-end**
on real infra (§H). What remains for *production* scale (hundreds–thousands of Executors) is operational
hardening: connection pooling for the poller, and wiring the scatter to Reader's real `LooseFileSink`
dirs + the real MainWatch/py_executor instead of the demo's worker stand-in.

---

## H. End-to-end scale demonstration (2026-06-22, rootless Docker, real compute)

`BundleControlPlaneScaleDemo` (+ `cp_demo_worker.py`) drives the **real control-plane code** against N
real, `taskset`-core-pinned worker processes (Plan-1 §4.4 isolation) that do genuine CPU work and write
real `results_v2` rows; the control plane plans the `(candidate, repeat, env)` scatter
(`planUnits` — the same balanced round-robin Reader's `LooseFileSink` does), then collects via
`RepeatEnvJdbcPoller` + `run` and decomposes via `aggregateNested`. Isolated ephemeral
`postgres:16.9-alpine` (`:15500`, no volume).

**Scale — fixed 24-unit (8 cand × K3, disperse) workload, N pinned workers:**

| N | units | completed | wall (ms) | speedup |
|---|-------|-----------|-----------|---------|
| 1 | 24 | 24 | 1813 | 1.00× |
| 2 | 24 | 24 | 1237 | 1.47× |
| 3 | 24 | 24 | 831 | 2.18× |

Throughput rises monotonically with pinned workers — the FW_VAR-style verdict path scales with
Executors. Sub-linear (2.18× not 3× at N=3) from the 50 ms poll interval + worker process/connection
startup + control-plane coordination at this small scale — honest, and amortized at larger workloads.

**§12 over real latencies — nested 3 cand × E3 × K4:** the decomposition runs on real measured
latencies and reports per-candidate `grandMedian` / `betweenEnvRange` / `withinEnvMedianRange` /
`envSensitive`. On a single 8-core host all candidates came back **env-insensitive** (within-env timing
jitter exceeded between-env range) — the truthful result for one machine; a genuine between-env signal
needs physically distinct hosts. The machinery is correct on real data.

This closes the **Scale** gate at small E with a real throughput curve. The remaining delta to a
*production* claim is scale (hundreds–thousands of Executors, on distinct hosts) + connection pooling —
infrastructure, not Plan-2 code.
