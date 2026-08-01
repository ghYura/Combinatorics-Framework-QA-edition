# 09 — Reader, Executor, and Results

## Reader: candidate reconstruction + handshake

The Reader (`Reader_trunk`, Java) streams surviving `fw_final` rows from the main DB and
reconstructs each into an executable candidate, then writes both the **legacy handshake**
(`resultsDbURL/`, `sqlTemplate/insert.sql`, `arguments/`, `runFirstOnce/`) and the **Handoff v2
manifest** (`handshake/handoff/manifest.json`). The launcher drives the Reader as a long-lived owned
subprocess (PID recorded for `cancel`), feeding the `y/y/no` lifecycle on stdin.

### Candidate sinks

- **loose-files** (default): one file per candidate (`<id>.py`). Byte-compatible reference path; one
  inode per candidate (the plan estimates inode pressure).
- **sharded**: compressed `*.fwshard` containers (`ShardSink`), streamed by the Executor
  (`ShardReader`) one record at a time without expanding the whole shard to disk — reduces inode
  pressure for L-class runs. Verified byte-for-byte equal candidate set to loose mode, with a
  count-mismatch guard (`test_shard_reader.py`). Select via `cfg.candidate_sink`.
- **grpc**: no on-disk candidate corpus. `GrpcCandidateSink` streams candidates live to the Java
  Executor receiver with flow-control backpressure, ping, and a count receipt. The launcher starts
  the receiver first and adopts it after Reader completes. Current restrictions: Java, verdict,
  Handoff v2, `trusted-local`, no pool; Reader targets `127.0.0.1:50061` by default. The receiver
  binds an explicit loopback address and refuses wildcard/non-loopback values. The channel remains
  plaintext/unauthenticated; firewall/interface isolation is defense in depth.

### Candidate IDs

Deterministic `<final>_<opt>_<j>` (e.g. `25_1_2`), independent of the sink, preserved through the
Executor into `results_v2` and the Analyzer provenance.

## Executor: run + classify + persist

The Python Executor (`Executor_trunk/py_executor.py`) consumes the Handoff v2 manifest (source of
truth for run id / candidates / result wiring), runs each candidate under the selected execution
policy (a sandbox backend for secure profiles; direct local execution for trusted-local), classifies
a canonical outcome, and persists results.

The launcher routes by candidate language (the Handoff v2 manifest's `language` is authoritative; a
`--lang` that disagrees fails closed): `python` → `py_executor`, `java` → the Java `MainWatch`
Executor. Run a Java spec with `--lang java`.

### RunMeFirstOnce: logical scope and Java contract

`RunMeFirstOnce` is the run-scoped prologue, not a combinatorial factor or a fragment repeated in
every candidate. Core stores its source separately, Reader exports it at the handoff, and Java
`MainWatch` invokes it before evaluating that handoff's candidate family. `MainWatch` captures the
static `FW_ARGS` produced by the prologue and uses that shared vector in preference to ordinary
`FW_Arguments` for candidate calls. In a Java Executor pool, each process has its own run-once
scope.

This boundary keeps runtime observation, shared bootstrap, and deterministic corpus preprocessing
outside the variable candidate body. Candidate-dependent setup and verdict logic must remain in
modeled slots/HEAD/TAIL. See
[RUNMEFIRSTONCE_LOGICAL_CONSTRUCT.md](RUNMEFIRSTONCE_LOGICAL_CONSTRUCT.md) for the complete semantic
contract and the distinction between canonical Java behavior and compatibility paths.

### Python preprocessor boundary

Legacy/Handoff inputs may reuse the `RunMeFirstOnce` field for a Python per-candidate preprocessor.
That is a compatibility extension, not the canonical once-per-handoff Java behavior. The Reader's
normal Java stub is not Python code, so `py_executor` detects the `class RunMeFirstOnce` / Java
`public static` shape and ignores it for Python candidates. Any actual Python preprocessor is
allowed only by the explicitly unsandboxed `trusted-local` profile. A secure profile rejects it
before provisioning or running any candidate; it is never executed on the host in front of a
sandboxed run. This rule is regression-tested in `test_py_executor_outcomes.py` and is exercised
by generated-default AI evaluation sub-suites.

### Java Executor (MainWatch + adaptive compiler)

`MainWatch` consumes the same Handoff v2 manifest, compiles each `.java` candidate with
`AdaptiveJavaCompiler`, runs `main`, reads `FW_VAR`/`FW_CUSTOM_VAR`, and writes the same canonical
count tuple + `results_v2` rows + `executor-summary.json` the Python path does (so the launcher's
invariants stay language-independent). Verified end-to-end via two combinable specs under
`generator_trunk/java_e2e/` (see that dir's README):

- **Compiler routing** (`AdaptiveJavaCompiler`): source containing `->`, `::`, or a modern keyword
  (`record`/`sealed`/`permits`/`yield`/`var <id>`) routes to **ECJ**; otherwise **Janino** is tried
  with an ECJ fallback. `janino_max` (classic Java) runs 48/48 on Janino; `ecj_modern`
  (records/`var`/streams/lambdas/switch-`yield`) fails 0/48 on Janino and runs 48/48 on ECJ. Pin the
  backend with **`--executor-compiler {adaptive,janino,ecj,javac}`** (`-Dfw.exec.compiler`); an
  invalid value fails closed.
- **Dependency-JAR pass-through** (`-dirJars`; Bundle CLI default
  `Executor_trunk/lib-src/target`): each valid `*.jar` is
  registered on a `DynamicURLClassLoader` (`sysLoader`) used as the compile/runtime parent by all
  backends (ECJ/javac also add it to the compile classpath). A candidate that `import`s a class from
  such a jar resolves through Janino's parent classloader and ECJ's classpath alike — verified with
  `com.example.rules.Scorer` (`rules-api-1.0.0.jar`), visible in `executor.log`
  (`dependency JAR directory -> … (1 newly registered, 1 total)`).
- **Class rename**: candidate files are `<id>.java` (e.g. `25_1_2.java`, an invalid Java name);
  MainWatch renames the first top-level `class/interface/enum/record` to a valid `C<id>`. Author the
  main class first; nested `record`/`interface` after it are safe.
- **Trusted vs untrusted (both verified E2E)**: `trusted-local` compiles+runs in-process (the
  current default, for trusted code only). The container/secure path (`SandboxedJavaRunner`,
  `generated-default`) mounts
  source ro under `/src` and dep jars ro under `/deps` with an isolated candidate classpath, in a
  per-candidate `eclipse-temurin:21-jdk-alpine` container (read-only root, `--cap-drop ALL`,
  `--network none`, pids/mem/cpu limits). **Verified 2026-06-11**: `janino_max` under
  `generated-default` produced **29 PASS / 19 DOMAIN_FAIL / 0 BROKEN — identical to trusted-local**,
  and the adversarial seam audit holds (write-outside-scratch → BROKEN, egress blocked,
  cpu-limit → TIMEOUT, corrupt policy → REFUSE). See
  `Executor_trunk/JANINO_ECJ_JAR_NOTICE.md` and [10](10_SECURITY_AND_SANDBOXING.md).
- **Limitation**: Java + `--analyzer` is **refused at preflight** — the Java Executor has no
  in-sandbox metrics-harvest transport yet, and re-running candidates to collect metrics would
  bypass isolation (the BUG-1 anti-pattern). Omit `--analyzer` for Java, or use `--lang py`.

Both executors persist full stdout/stderr to **`executor.log`** in the run dir (like
`core.log`/`reader.log`).

### Worker protocol & backpressure

When `py_executor.py` is invoked directly, its `--workers N` argument runs a dispatcher over
**deterministic id-hash partitions**; 1-worker and N-worker
runs yield the **same** outcome set (verified `test_worker_pool.py`) and the **same** harvested
metrics corpus (`merge_worker_metrics` merges per-worker `metrics-<w>.kv` partitions, sorted by
candidate_id, skipping a crashed worker's missing partition — `test_py_executor_outcomes.py`). Each
worker writes an idempotent result and a checkpoint **only after** its single end-of-run commit, so
a crashed worker is re-run on resume without reprocessing finished partitions. An optional
backpressure state dir bounds how far the Reader (producer) runs ahead of the Executor (consumer) —
verified the producer waits at the high watermark (`test_backpressure.py`). **Measured speedup**
(2026-06-11): 8 workers gave ~5.5× over a single process (2.83 → 15.66 cand/s, 500 candidates) —
see [13](13_BENCHMARKS_AND_SCALE_CLAIMS.md).

This is distinct from the Bundle CLI's stress-only `--workers`. Launcher-level Java concurrency is
`--executor-pool N`: one MainWatch process per Reader round-robin directory, with owned-process
journaling/cancellation and merged summaries. It requires Java, loose files, verdict mode, Handoff
v2, and K=1.

### Repeats

For K>1, the launcher probes the selected Python/Java Executor and the repeat-aware DB schema before
starting. Current runtime support is `local` policy only. With `metrics`, sample 0 supplies the one
full verdict and first measurement, followed by K−1 metric-only invocations; `all` executes K
independent full verdicts. Each raw sample carries
`repeat_idx` and `env_id`; missing measurements remain observable rather than being silently
collapsed. Disperse/nested exist in `BundleControlPlane` planning/execution seams but remain refused
by the Bundle launcher.

### Outcome model (canonical)

`PASS`, `DOMAIN_FAIL`, `BROKEN`, `TIMEOUT`, `INFRA_FAIL`, `SKIPPED`, `CANCELLED`. Mapping:
no verdict marker → BROKEN; per-run timeout → TIMEOUT; spawn/DB infra error → INFRA_FAIL; non-zero
domain verdict → DOMAIN_FAIL; zero → PASS. A boolean `status = (outcome == PASS)` is kept as a
compatibility projection. Launcher success policy: DOMAIN_FAIL is always accepted;
BROKEN/TIMEOUT/INFRA_FAIL fail the run by default but can be downgraded to WARNING with
`--executor-tolerate-outcomes`. Verified flagship: 288 = 150 PASS + 138 DOMAIN_FAIL + 0 others.

### Analyzer metrics harvest (no re-run — BUG-1 fix)

The Executor harvests each candidate's `app=… K=V … FW_VAR=…` line **during its real (sandboxed)
execution** and writes the corpus via `--metricsFile` (one `<candidate_id> <source_ref> <run_id>
<K=V>` line, sorted, atomic). The Analyzer consumes this corpus directly. The old behavior — a
host-side re-execution of every candidate (`collect_kv`) — was a sandbox bypass and produced a
wrong/truncated corpus; it remains only as the trusted-local/legacy fallback when no in-process
corpus exists.

## Results DB: legacy + `results_v2`

- **Legacy table** `"<db>"` — per-run boolean `status` + verdict columns; existing consumers keep
  working.
- **`public.results_v2`** (additive; mirrors Java `ResultsV2SchemaMigrator`/`ResultsV2Writer`):
  run_id, candidate_id, attempt, outcome, verdict_code/message, duration_ms, exit/signal, worker,
  source_hash, stdout/stderr refs, policy_id/policy_hash, `repeat_idx`, `env_id`, `created_at`.
  **Unique
  `(run_id, candidate_id, attempt, repeat_idx, env_id)`**. Migration adds/backfills the repeat
  columns, drops the retired three-column index, creates `results_v2_sample_uk`, and stamps
  `results_v2_schema_meta` version 2. Both Executors validate that capability and fail closed with
  `RESULTS_V2_SCHEMA_CAPABILITY_MISMATCH` before writing. There is no selected-final partial index.

### Idempotency & retry

Replaying the **identical** sample batch (same attempt/repeat/environment) inserts nothing — every
row becomes "already present" via the unique key. A retry after an infrastructure failure creates
a **new attempt** inside the same repeat/environment identity, not a new candidate or repeat.
“Selected/final” means the highest attempt at read time, independently per
`(candidate_id,repeat_idx,env_id)`. Legacy inserts and
`results_v2` rows commit in **one** transaction with a single commit (`commit_legacy_and_v2`); any
failure rolls back everything and reclassifies the affected candidates to INFRA_FAIL. Verified
flagship: `results_v2` 288/288 distinct keys, legacy table 288, no duplicates; a no-op resume adds
no new attempt (`distinct attempt = {1}`).
