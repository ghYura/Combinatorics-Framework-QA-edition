# 19 — API and Schema Reference

Concise field-level reference generated from the current schemas and typed models. For full detail
read the source of record (linked); this page avoids duplicating implementation that is likely to
drift.

## Spec v1 — `bundle.spec/v1`
Source: `generator_trunk/bundle-spec-v1.schema.json`, model `fwgen.Spec`.

| Field | Type | Notes |
|---|---|---|
| `slots` (**required**) | array | each: `sheet`, `key`, `verb`, `flags[]`, `raw`, `values[]`, `separator`, `group_replace[][]` |
| `spec_version` | string | absent → `legacy` |
| `title`/`note`/`args`/`runme` | string/array | metadata / static candidate args / run-scoped RunMeFirstOnce prologue |
| `goals` | array | `{key, dir}` Analyzer objectives |
| `custom_vars` | array | `{code, msg}` custom verdict map |
| `params` | array | `{sheet, value, <attr>:…}` value attributes for the sieve |
| `constraints` | array | `{id, sheets[], when, gate, desc}` sieve rules |
| `seq_extra` | array | **top-level** brace / second-order FW_Seq rows |

## Handoff v2 — `bundle.handoff/v2`
Source: `generator_trunk/bundle-handoff-v2.schema.json`, model `bundle/handoff.py:HandoffV2`.

| Field | Type | Notes |
|---|---|---|
| `schema` | string | `bundle.handoff/v2`; unknown **major** rejected |
| `run_id` | string | matches the run |
| `language` | enum | `python` / `java` |
| `candidate_transport` | enum | `loose-files` / `sharded` / `grpc` |
| `candidate_count` | int ≥ 0 | verified against emission |
| `id_format` | string | e.g. `<combi_id>_0_0` |
| `sources` | array | `{kind, path, sha256?}`; gRPC uses informational `kind=grpc`, `grpc://host:port` |
| `result_target` | object | `{host, port, database, user?}` — **never a password** |
| `result_schema_mode` | string | e.g. `placeholders=14` |
| `verdict_mode` | enum | `FW_VAR` / `FW_CUSTOM_VAR` |
| `custom_verdicts` | array | `{code, message}` |
| `arguments` | array | candidate argv |
| `shift` | int | **never empty** (P6) |
| `preprocess` | string? | RunMeFirstOnce source reference; canonical Java scope is once per handoff, while trusted-local Python compatibility is per candidate |
| `execution_policy_ref` | string | stamped post-write by the launcher |

## Run manifest — `bundle.run/v1` · Stage result — `bundle.stage-result/v1`
Source: `bundle/models.py` (`RunManifest`, `StageResult`, `ArtifactRef`, `CountObservation`,
`InvariantResult`, `RunStatus`, `StageStatus`, `Outcome`, `InvariantSeverity`).

- **RunManifest:** `schema, run_id, status, db_name, spec_path, spec_sha256, spec_version, mode,
  goals, start, scratch_root, settings{…redacted…}` (+ component inventory, env fingerprint,
  execution policy in `settings`).
- **StageResult:** `schema, stage, status, start, finished, duration_ms, process_exit_code,
  log_path, counts[CountObservation], warnings[], errors[], artifacts[ArtifactRef],
  invariants[InvariantResult]`.
- **CountObservation:** `{name, expected, actual, note}`. **ArtifactRef:** `{kind, path, bytes,
  sha256}`. **InvariantResult:** `{id, description, expected, actual, passed, severity}`.
- **RunStatus / StageStatus:** `PENDING, RUNNING, SUCCEEDED, FAILED, SKIPPED, INTERRUPTED` (Run adds
  the terminal set). **Outcome:** `PASS, DOMAIN_FAIL, BROKEN, TIMEOUT, INFRA_FAIL, SKIPPED,
  CANCELLED`. **InvariantSeverity:** `CRITICAL, WARNING`.

## Execution policy
Source: `bundle/policy.py:ExecutionPolicy` (+ `PROFILES`).
`{schema, profile, backend, timeout_seconds, cpu_seconds, memory_bytes, max_processes, fs_read[],
fs_write[], network(disabled|allowlist|unrestricted), network_allowlist[], env_allowlist[],
stdout_max_bytes, stderr_max_bytes, allowed_interpreters[], trusted}`. Profiles: `trusted-local`
(local), `generated-default` (container, net disabled), `networked-api-probe` (container, allowlist).
Persisted secret-free as `execution_policy.json`; id/hash recorded in `results_v2`.
There is no default profile: a run refuses until one is chosen, and `trusted-local` (unsandboxed)
additionally requires an origin classification and a recorded reason. `generated-default` and
`networked-api-probe` must be selected explicitly for untrusted code and fail closed if their
container backend is unavailable.

## Repeat/count contract

`BundleConfig` fields: `repeat_each_candidate` (CLI `--repeat`, K≥1), `repeat_policy`
(`local|disperse|nested`), `repeat_scope` (`metrics|all`), and `repeat_environments` (E, required for
nested K>1). `bundle.counts.CountPlan` carries `assignment_units` (A),
`full_verdict_invocations` (V), `measurement_opportunities` (I), and
`metric_only_invocations`. K=1 normalizes A=V=I=C. The launcher currently executes K>1 only for
Python/Java local metrics/all; standalone `BundleControlPlane` owns the broader policy seam.

## Invariants (`bundle/invariants.py`)
`core_count_positive, post_sieve_le_core, reader_emitted_eq_expected, reader_empty_zero,
handoff_run_id_matches, handoff_candidate_count_matches, handoff_manifest_used,
executor_processed_positive, executor_processed_eq_sum, executor_broken_zero, executor_timeout_zero,
executor_infra_fail_zero, executor_inserted_matches_policy, results_v2_write_counts_consistent,
results_v2_attempted_matches_processed, results_db_eq_inserted, analyzer_input_matches_metrics`.
`enforce()` raises on any CRITICAL failure.

## results_v2 (DDL)
Source: `Executor_trunk/py_executor.py` (mirrors Java `ResultsV2SchemaMigrator`). Columns:
`id, run_id, candidate_id, attempt, outcome, verdict_code, verdict_message, duration_ms, exit_code,
signal, worker, source_hash, stdout_ref, stderr_ref, policy_id, policy_hash, repeat_idx, env_id,
created_at`. Unique
`(run_id, candidate_id, attempt, repeat_idx, env_id)` via `results_v2_sample_uk`. The migration
backfills K=1 defaults (`repeat_idx=0`, `env_id=''`), drops the retired three-column index, and
stamps `results_v2_schema_meta` version 2. Both writers validate the stamp/columns/index before
writing. There is no selected-final partial index; highest `attempt` is selected at read time for
each `(candidate_id,repeat_idx,env_id)`.

## Other artifact schemas
`bundle.plan/v1` (`cmd_plan`), unversioned `controlplane_plan.json`, `analyzer.provenance/v1`
(`provenance.json`), BundleSeed `schemaVersion=1` (`bundle_seed.json`), `bundle.iterate/v1`
lineage (`<base-run-id>-iterate.json`),
`bundle.inventory/v1`, `bundle.hygiene/v1`, `bundle.benchmark/v1`. Run-specific release and
scenario evidence is not committed as a repository-level artifact.

## Transport/runtime constraints

For `candidate_transport=grpc`, the launcher starts MainWatch's receiver before Reader, then adopts
and waits for it. Current constraints are Java, verdict mode, Handoff v2, `trusted-local`, pool=1;
Reader targets `127.0.0.1:50061` by default. The receiver binds explicit `grpc_bind_host` loopback
and refuses wildcard/non-loopback values. The Netty channel is plaintext and unauthenticated, so it is not a
remote trust boundary. `--executor-pool N` instead requires Java loose-files/verdict/v2 and K=1.

## CLI surface
See [04_CLI_AND_LIFECYCLE_REFERENCE.md](04_CLI_AND_LIFECYCLE_REFERENCE.md) — generated from the
verified `--help` of each subcommand. Validate any schema's instances with the built-in
`bundle/handoff.py:validate_against_json_schema` (no `pip jsonschema` needed).
