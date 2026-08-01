# 08 — Run Contracts and Schemas

Every run (run-directory mode, the default) has a stable identity and a machine-readable contract.
See [02_ARCHITECTURE.md](02_ARCHITECTURE.md) for the directory tree.

## Run identity

`run_id` is user-provided (`--run-id`) or a deterministic-safe timestamp+random suffix; characters
are restricted. A collision with an existing run directory **fails closed** (verified: "run
'<id>' already exists … refusing"). Legacy `--legacy-scratch` mode uses a flat per-DB tree with no
`run.json`/journal (and therefore no resume).

## `run.json` — `bundle.run/v1`

Contains: schema, run_id, status, db_name, spec_path + **spec_sha256**, normalized spec hash,
component inventory (per-component version + sha256), Java/Python/PostgreSQL versions, host/platform
fingerprint, **redacted** resolved settings (mode, ports, analyzer goals, budget, execution policy),
scratch path, requested mode/goals, timestamps, and the current terminal status. It **never**
contains a plaintext password — verified: all `*password*` values are `***REDACTED***`.

## `state.json` and stage results — `bundle.stage-result/v1`

`state.json` holds the derived run status and per-stage status. Each `stages/<name>.json` records:
stage, status (`PENDING/RUNNING/SUCCEEDED/FAILED/SKIPPED/INTERRUPTED`), start/finish timestamps,
duration, process exit code, log path, input/output **counts** (name, expected, actual), warnings,
errors, **artifacts** (kind, path, bytes, sha256), and **invariants** (id, expected, actual, passed,
severity). The run status is **computed** from stage statuses, never printed by assumption.

## Handoff v2 — `bundle.handoff/v2`

The Reader→Executor contract (`generator_trunk/bundle-handoff-v2.schema.json`, model
`bundle/handoff.py`). Fields: `schema`, `run_id`, `language`, `candidate_transport`
(`loose-files`/`sharded`/`grpc`), `candidate_count`, `id_format`, `sources` (kind/path/sha256),
`result_target` (host/port/database/user — **no password**), `result_schema_mode`, `verdict_mode`
(`FW_VAR`/`FW_CUSTOM_VAR`), custom verdict map, `arguments`, `shift`, preprocess, and (stamped after
the Reader writes it) `execution_policy_ref`.

Validation (`validate_handoff`): `candidate_count ≥ 0`; **`shift` is never empty** (P6 legacy
gotcha); unknown **major** schema version is rejected (fail closed). A built-in mini JSON-schema
validator (`validate_against_json_schema`) means **no `pip jsonschema`** is needed. `handoff_from_legacy`
converts the legacy file handshake into the same v2 model for compatibility.

For `grpc`, the source is informational (`kind="grpc"`, `path="grpc://host:port"`): there is no
candidate corpus to reread. The launcher starts the Java Executor receiver before Reader and adopts
it after the stream drains. This path is Java/verdict/Handoff-v2/trusted-local only, defaults to
`127.0.0.1:50061`, and is plaintext/unauthenticated. The receiver separately binds an explicit
loopback address and refuses wildcard/non-loopback values; firewall/interface isolation remains
defense in depth. It cannot
be combined with stress mode, legacy handoff, a secure profile, or an Executor pool.

> **Manifest finalization order (BUG-2 fix):** the Reader writes the manifest; the launcher then
> stamps `execution_policy_ref` into it via `_persist_handoff_policy` and writes a secret-free
> `execution_policy.json` beside it. The reader stage records the manifest's sha256 **after** that
> stamp, so a `bundle resume` re-hashing the finalized file matches and reuses the stage.

## Other schemas

- `bundle.plan/v1` — `plan.json` (counts with exactness, run class, resource estimates, graph hash).
- execution policy (`bundle/policy.py`) — `execution_policy.json` (id + sha256 + view; no secret).
- `analyzer.provenance/v1` — `provenance.json` (corpus count, goals, selected candidates + reasons).
- `bundle.inventory/v1`, `bundle.hygiene/v1`, `bundle.benchmark/v1` — tooling outputs.
- `controlplane_plan.json` — currently unversioned repeat assignments/dispatch seam; standalone
  Java supports local/disperse/nested, while the Bundle launcher currently executes local only.
- BundleSeed `schemaVersion=1` / `bundle.iterate/v1` — Analyzer winners and iterative-run lineage.
- `results_v2` DDL — additive results table (see [09](09_READER_EXECUTOR_AND_RESULTS.md)).

## Hashes, IDs, invariants, atomicity

- **Hashes:** spec sha256 (run identity / resume), per-component artifact sha256 (inventory/doctor),
  candidate dir + manifest sha256 (resume reuse), `FW_Seq` graph hash (plan).
- **Candidate IDs:** deterministic `<final>_<opt>_<j>` (e.g. `25_1_2`), preserved across the pipeline
  and into `results_v2` and the Analyzer provenance.
- **Invariants:** cross-stage counts are machine-enforced (`bundle/invariants.py`); a CRITICAL
  failure raises (fail closed). Full list and chain in [06](06_PLANNING_BUDGETS_AND_COUNTS.md).
- **Result identity:** an immutable sample is
  `(run_id,candidate_id,attempt,repeat_idx,env_id)`. K=1 uses `repeat_idx=0, env_id=''`; the retired
  three-column index is dropped. Selected/latest-attempt results are computed at read time.
- **Atomicity:** contract JSON written through `bundle/jsonio.py` uses temp → flush/`fsync` → atomic
  `os.replace`. Legacy + `results_v2` rows commit in **one** transaction.

## Secret exclusions

Manifests/reports/the resolved config redact `password`/`token`/`secret`/`api_key`/`credential`
keys (`jsonio.redact`). The Handoff v2 `result_target` carries no password. Plaintext DB credentials
appear **only** in the run-private `core_cwd/fw.properties` / `reader_cwd/fw.properties` (required by
the JVM JDBC path), in a run-private directory; `cleanup` flags them as credential-shaped files for
deletion. Candidate-env passthrough refuses credential-shaped names.
