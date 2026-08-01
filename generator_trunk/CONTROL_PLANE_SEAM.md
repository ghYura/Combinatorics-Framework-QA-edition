# The Two Control Planes and Their Seam

Date: 2026-07-21 (code/documentation reconciliation).
Scope: `generator_trunk/bundle/` (Python) ↔ `Analyzer_trunk/.../BundleControlPlane.java` (Java).

## Why there are two

The split is deliberate (ADR-8 / Plan-2 §P2.0): **Python owns experiment design,
Java owns high-fan-out dispatch**. They are not two implementations of one thing —
they are two *layers* with one JSON seam between them.

| | Python control plane | Java control plane |
|---|---|---|
| Where | `generator_trunk/bundle/` (cli, stages, config, journal, invariants, budgets, policy, handoff, seedbias, iterate) | `Analyzer_trunk/.../optimization/BundleControlPlane.java` |
| Owns | *What to run and whether it may run*: spec → plan, preflight, budget gate, execution policy, stage orchestration (gen/core/[seed_bias]/[sieve]/reader/executor/[analyzer]), journaling + invariants + lineage, resume/cancel, seed-bias/iteration loop | *How to run many samples fast*: candidate × repeat × env fan-out on virtual threads, in-flight cap (Semaphore), per-host serialization for noisy metrics, budget deadline with cooperative cancel, result collection keyed by the Plan-1 sample identity, nested/disperse cross-env aggregation |
| Cadence | One process per bundle run; seconds–minutes granularity; subprocess orchestration | One object per repeat campaign; microsecond-granularity concurrency control inside a JVM |
| State today | **LIVE** — this is what `bundle_run.py` executes | **DORMANT at runtime** — compiled, self-verified (`BundleControlPlaneVerify`, `...LiveDbVerify`, `...ScaleDemo`), CLI dry-run only; not yet wired into a live run |

## How they interact (the seam)

One direction, one artifact: **Python emits a plan JSON; Java ingests it.**

```
bundle.controlplane.controlplane_plan(cfg, candidates=…, run_id=…)   # Python planner
        │  {"policy","repeatK","repeatScope","envs":[…],
        │   "maxInFlight"?,"serializePerHost"?|"metricSensitivity"?,
        │   "budgetMillis","candidates":[{lineNo,candidateId,raw}]?}
        ▼
BundleControlPlane.Plan.fromJson(json)                                # Java ingest
        → planUnits(): policy expansion to (candidateId, repeatIdx, envId) units
        → run(units, UnitExecutor): vthread fan-out under caps/deadline
        → toAggregatorCorpus()/aggregate()/aggregateNested()
```

CLI dry-run of the Java side (what the seam test drives):
`java -cp Analyzer_trunk/target/classes:$(cat Analyzer_trunk/analyzer_cp.txt) \
  com.yurii.analyzer.core.optimization.BundleControlPlane plan.json`

For every K>1 run the live launcher journals `controlplane_plan.json` in the
run directory (artifact `output.controlplane_plan` of the Executor stage).
That live call currently emits policy, repeat, env, cap, and budget
configuration **without the optional `candidates` array**. It is therefore an
auditable/parseable dispatch configuration, not a directly runnable Java
handoff: `planUnits()` has no units until actual candidate descriptors
(`lineNo`, `candidateId`, and `raw`) are attached. The Python
`controlplane_plan(..., candidates=...)` API and seam tests exercise the full
shape, but the live launcher has not yet wired materialized candidates into it.

## The contract keys (do not drift)

* **Env identity**: the single-host env id is `local:<run_id or 'default'>` —
  byte-identical in three places: the executors' `--envId`/`-envId` flags
  (`stages._repeat_executor_flags` / `_java_repeat_executor_flags`), every
  `results_v2.env_id` row those runs write, and the plan's default `envs`
  (`controlplane._default_envs`). *(Reconciliation fix: the plan used to default
  to `""` — same sample, two identities. Fixed + pinned by tests.)*
* **Budget**: the plan's `budgetMillis` defaults from the layered config's
  `budget_wall_time_seconds`, so the Python budget gate and the Java dispatch
  deadline enforce ONE number. *(Reconciliation fix: previously independent.)*
* **Policy semantics** (pinned cross-language by `test_bundle_controlplane_seam.py`):
  `local` = K repeats pinned to one env (candidates round-robin);
  `disperse` = repeat r of candidate ci → `envs[(ci+r) % E]`;
  `nested` = K repeats on **each** env (C·E·K units).
  `metricSensitivity=noisy` ⇒ `serializePerHost=true`, explicit flag wins.
  `repeatScope` is Plan-1 fidelity data — Java tolerates and ignores it.

## Duplicates audit (what is and is not a duplicate)

* **In-executor K>1 repeats** (`MainWatch -repeat…` / `py_executor --repeat…`)
  vs **BundleControlPlane fan-out** — NOT a conflict: the in-executor path is the
  single-host degenerate (`local`, one env) of the general dispatcher; the Java
  plane exists for the multi-env pool that infra does not have yet. The shared
  env-id convention is what keeps their outputs joinable. Do not re-implement
  multi-env logic in the executors; emit a plan instead.
* **Repeat validation** exists on both sides by design (fail-closed at every
  boundary): Python `BundleConfig.validate_repeat()` gates what may be *planned*;
  Java `Config`'s compact constructor normalizes what may be *dispatched*.
  The seam test keeps their accepted vocabulary identical.
* **`RemoteWorker.JdbcPoller` (candidate-keyed)** vs **`RepeatEnvJdbcPoller`
  (sample-keyed)** — documented evolution inside the Java plane, not a Python/Java
  duplicate; the legacy poller stays exact for K=1/verdict paths.
* **Aggregation** — no duplicate: both AnalyzeKv and BundleControlPlane delegate
  to the same `RepeatAggregator`.

## The local Executor pool and the orchestrator question

`--executor-pool N` (config `executor_pool_size`) runs N Java Executors in parallel by
finally exploiting a capability the Reader carried all along: `reader.out.outZipDirPathList`
is a CSV, `LooseFileSink` round-robins candidates across every listed directory, and the
Handoff manifest declares one source PER directory. The launcher creates `src/e0..e(N-1)`,
the Reader deals candidates into them (±1 even split), and each pool member is a plain
`MainWatch -poolIndex I`: it re-validates the WHOLE manifest (count + per-source checksums —
no member starts on a torn corpus), then scopes itself to source[I] and self-exits when ITS
share is processed. The launcher spawns/records/cancels members, merges their
`executor-summary.json` into the canonical one (summed counts + a `pool` breakdown) and
concatenates their metrics corpora. All existing invariants operate on the merged totals
unchanged. v1 gates (fail-closed in preflight): Java, loose-files, K=1, Handoff-v2 flow.

**Why no external orchestrator (k8s/compose/…):** the Python control plane already IS the
orchestrator for this topology — process registry (`bundle cancel`), journaled stages,
fail-closed reconciliation, budget/timeout ownership. N is single-digit on one host; an
external scheduler would add a second source of truth for lifecycle without adding
capability. **Rootless Docker's place is a different layer**: it is the per-candidate
*sandbox* backend selected by the execution policy (STEP 28/29 container profiles) — i.e.
isolation *inside* a member, not member scheduling. The two compose cleanly later:
containerized or multi-host members would require an explicit remote lifecycle and policy
contract.

Do not treat the current Reader gRPC sink as that remote pool. Today it is a
separate Java-only, `trusted-local` live-feed path: the launcher starts one
Executor before Reader, Reader streams to its `-grpcPort`, and the Executor
stage later adopts that same process. No reusable candidate corpus is written;
Reader and Executor must be rerun together, and `--executor-pool` is rejected
with the gRPC sink. Multi-host gRPC dispatch remains future work. Pool member
identity today is traceable via the `worker` column of `results_v2`
(`java:<pid>`) and the per-member summaries.

## Import behavior

Importing `bundle.stages` is not entirely passive: it installs default
`BUNDLE_REPO_ROOT` and `BUNDLE_SUT_ROOT` values with `setdefault` and
prepends `generator_trunk/` to `sys.path` before importing `fwgen`. It
does not start stages or write run artifacts at import time, but an embedded
caller should set those environment variables before the import and should not
assume `sys.path` is unchanged.

## Tests that guard this document

* `test_bundle_controlplane.py` — Python emitter shape (incl. live env identity
  and budget derivation).
* `test_bundle_controlplane_seam.py` — the cross-language round-trip: Python-emitted
  plans expanded by the compiled Java CLI; policy math + assignment + overrides
  asserted from the Java output. (Before 2026-07-03 each side only tested itself.)
* `Analyzer_trunk/run-tests.sh` → `BundleControlPlaneVerify` — Java-side dispatch
  semantics (caps, serialization, budget/cancel, nested decomposition).
