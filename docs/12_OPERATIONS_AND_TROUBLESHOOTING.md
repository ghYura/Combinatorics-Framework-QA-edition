# 12 — Operations and Troubleshooting

## Diagnostics first

Always start with `bundle doctor` ([03](03_INSTALLATION_AND_LOCAL_DEPLOYMENT.md)) — it reports
OK/WARNING/BLOCKING for Python/pg8000, Java, jars, both DBs + privileges, scratch space/inodes,
container runtime, sandbox backend, and the component inventory, without touching any production DB.
Then `bundle plan <spec>` to quantify before running.

## Common failures by stage

| Symptom | Likely cause | Fix |
|---|---|---|
| Preflight: "main/results DB password not configured" | env var unset | `export BUNDLE_{MAIN,RESULTS}_DB_PASSWORD=…` |
| Preflight: "PostgreSQL not accepting on host:port" | cluster down / wrong port | start cluster; check `--main-port/--results-port` |
| Preflight: "expected exactly one .toml in <dir>" | 0 or >1 specs in the dir | keep one `.toml` per spec dir |
| Build/start: unsupported class-file version or Reader/Executor compilation failure | running the current full reactor with JDK 21 | use JDK 25 for Reader/Executor/full reactor; Core/Analyzer libraries still target 21 |
| gen: `KeyError 'values'` parsing a `.json` | a stray spec-shaped `.json` in the dir | (fixed) Bundle artifact JSONs are skipped; remove other stray `.json` |
| core: "Core did not fill :port/db" | JVM/JDBC error | read `core.log`; verify main DB creds/host; `doctor` |
| reader: "emitted 0 candidates" | Core/sieve produced 0 rows, or handshake misconfig | check `core.log`/`reader.log`, sieve count |
| executor: `FATAL — execution policy requires sandbox backend … refusing` | secure profile, no Docker | start rootless Docker, or use `trusted-local` (trusted code only) |
| executor: many BROKEN/INFRA on a networked run | SUT unreachable / `TRYOUT_URL` not forwarded | pass `--sandbox-network-allowlist <target>` + `--sandbox-candidate-env TRYOUT_URL=…`; ensure the target container is running |
| Java Analyzer produces no corpus / summary | current Java Executor artifact is missing its declared metrics-harvest capability or the candidate TAIL emits no metrics | rebuild the current reactor, verify the Java Executor capability probe, and inspect `executor-summary.json`; Java + Analyzer is supported on the current Handoff-v2 verdict path |
| Java run: all BROKEN with `--executor-compiler janino` | spec uses modern Java Janino can't compile | use `adaptive` (default) or `ecj`; inspect `executor.log` for the compile error |
| Java run: need to see which compiler/deps were used | — | read `<run-dir>/executor.log` (MainWatch's full output: dependency-JAR registration, per-candidate compile/verdict) |
| `RESULTS_V2_SCHEMA_CAPABILITY_MISMATCH` | results DB has no v2 metadata stamp, wrong version/index, or the retired 3-column index | let the current migrator run with DDL rights; verify `results_v2_schema_meta` v2 and five-column `results_v2_sample_uk` |
| `REPEAT_K_REQUIRES_EXECUTOR_CAPABILITY` | K>1 requested with an old Executor, disperse/nested launcher policy, or unsupported scope | use current Python/Java Executor with local metrics/all, or use `bundle plan`/the standalone control-plane seam |
| preflight: `executor_pool_size>1 ...` | pool combined with Python, shards/gRPC, stress, legacy handoff, or K>1 | use Java + loose files + verdict + Handoff v2 + K=1 |
| gRPC receiver does not listen / stream fails | port busy, Reader target differs from receiver bind, receiver startup failure, or a refused wildcard/non-loopback bind | inspect reader/executor logs; choose a free `--grpc-port`; keep `grpc_bind_host` on explicit loopback and align `--grpc-host`; gRPC is plaintext trusted-local only |
| analyzer (formal): "declared corpus count N != M ingested" | truncated/incomplete corpus | a real corpus shortfall (e.g. BROKEN candidates) — investigate; formal mode is fail-closed by design |
| `group_replace` had no effect — candidates still contain the placeholder | the pattern was written against rendered value text; `FW_ReplaceRE` only ever sees the code-string of a combination (`"[47, 48]"`, a list of `Short` keys), so it never matched | set `core.replace.patternPolicy=warn` (or `strict`) to reject such a pattern up front, and `core.replace.diagnostics=summary` to see per-pattern hit counts. Author against codes/structure. See [41_FW_REPLACERE_POLICIES.md](41_FW_REPLACERE_POLICIES.md) |
| grouped sheet produced fewer `fw2_` rows than expected, with `failed to parse combo string` in core.log | a rewrite left the code-string non-integer-parseable, so those rows were dropped | `core.replace.unparseablePolicy=fail` turns the drop into a refusal quoting the string before and after; `=drop` silences it when the discard is intentional |
| analyzer (formal): "its classpath could not be resolved" | no persisted `Analyzer_trunk/analyzer_cp.txt` and the one-time self-build failed — usually a cold `~/.m2` with no network, since `maven-dependency-plugin` is not pulled in by the reactor build | run the command the message prints: `cd Analyzer_trunk && mvn -q dependency:build-classpath -Dmdep.outputFile=/tmp/_dep.txt`. Resolution tries offline first, then online; only both failing reaches this. In non-formal modes it degrades to the corpus with a printed note instead |
| a stage silently did nothing but the run still says "full Bundle chain green" | a degrade path that ignored `--analysis-mode formal` | should no longer happen — the Analyzer's unavailable/unresolvable paths both raise in formal mode. If you see it elsewhere, treat it as a defect: a stage that cannot run must fail, not narrate |
| resume: "stage(s) still marked RUNNING … crashed" | process died mid-stage | inspect `stages/<stage>.json` + log; fix `state.json` by hand once artifacts are confirmed, or start fresh |
| resume: "run ID … is ambiguous" | same run-id under two scratch roots | pass the **full run directory path** |

## Resume / cancel / cleanup

- **Resume** (`bundle resume <run-dir>`): reuses each stage only if SUCCEEDED + invariants pass +
  hashes/artifacts/live-counts match; a no-op resume of an unchanged run reuses **all** stages
  (verified) and adds no rows. A changed spec/missing candidate reruns from that point.
- **Cancel** (`bundle cancel <run-dir>`): terminates only this run's owned children, marks
  INTERRUPTED.
- **Cleanup** (`bundle cleanup <run-dir> --dry-run` then `--yes`): scoped to the run root + DB
  identity; refuses a mismatched `--db`, symlink/traversal/shallow paths; never deletes outside the
  run root. Capture evidence before `--yes`.

## DB / process / container cleanup

- **Owned processes:** `cancel` handles the Reader JVM; otherwise check `pgrep -af
  'py_executor|MainWatch|AnalyzeKv'`.
- **Sandbox containers/networks:** a clean run removes its own; after a forced kill, sweep with
  `docker ps -a --format '{{.Names}}' | grep sbx` and `docker network ls | grep sbx`, then
  `docker network rm` (disconnect attached targets first). `sandbox.cleanup_sandbox_networks` is the
  defensive sweep.
- **Temp DBs:** current benchmark cleanup tracks and drops both main- and results-side `fwbench_*`
  DBs (BUG-4 was fixed). After a forced kill, inspect for leftovers and remove only names belonging
  to the interrupted benchmark.
- **Deploy stack:** `deploy down` (keeps volumes) / `deploy down --volumes` (deletes data).
- **Container names are host-wide, not checkout-scoped.** The profile fixes `fwbundle-main-db` /
  `fwbundle-results-db` / `fwbundle-adminer`, so simultaneous per-checkout stacks are unsupported.
  `deploy up` and `deploy down` preflight every existing fixed name: complete ownership labels must
  match the selected `.env`; a legacy DB container is accepted only when its sole named mount
  matches exactly. Foreign or ambiguous containers are left untouched and the whole operation
  fails before mutation.
- **Persistent volume identity is file-owned.** Once the selected `deploy/.env` exists, ambient or
  explicit `BUNDLE_{MAIN,RESULTS}_DB_VOLUME` values cannot redirect this checkout. Other settings
  retain their documented environment precedence.
- **`deploy down --volumes` is additionally fail-closed.** Targets are taken only from the selected
  file; they must be one matching `fwbundle_<16 hex>_{main,results}_data` pair. Legacy unscoped names,
  unknown Docker inspection failures, or references from any foreign container are refused before
  the first container removal. Exact references are rechecked before deletion.
- **The live deploy acceptance test refuses fixed-name conflicts.** It self-skips
  `EXPECTED_OPTIONAL` when any canonical container already exists (running *or* stopped), drops
  ambient `POSTGRES_*` / `BUNDLE_*`, and deletes only the two disposable volume names it minted and
  verified. Bring the stack down to exercise it.

## Logs / artifacts

Per run: `core.log`, `reader.log`, `gen.log`, `stages/*.json` (counts/invariants/artifacts),
`executor-summary.json` (outcomes + sandbox backend), `metrics.kv` (Analyzer corpus),
`provenance.json`, `resolved_config.json` (redacted). The run/stage status is in `state.json`.

## Recovery playbooks

- **Interrupted run** → `bundle resume <run-dir>` (reuses valid stages).
- **Crashed worker** → re-run the same Executor command / resume; finished workers are skipped via
  checkpoints, only crashed partitions rerun (no duplicate legacy rows).
- **Infra failure mid-run (DB lost)** → candidates reclassify to INFRA_FAIL, everything rolls back;
  fix infra, resume (a new attempt; results_v2 idempotent on
  `(run_id,candidate_id,attempt,repeat_idx,env_id)`).
- **gRPC run interrupted between Reader and Executor** → restart from Reader; the live corpus is not
  replayable from disk, so Reader and Executor rerun together.
- **Secure backend unavailable** → start rootless Docker (`export DOCKER_HOST=…`), re-run; never
  switch a secure run to `trusted-local` to "make it pass".
