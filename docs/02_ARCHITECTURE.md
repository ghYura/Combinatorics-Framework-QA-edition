# 02 — Architecture

> **Product boundary.** Bundle is an executable combinatorial design-space and evidence engine; AI
> response testing is a reference application. The layer model, the allowed dependency direction and
> the gate that enforces them are in
> [30_ENGINE_FIRST_ARCHITECTURE.md](30_ENGINE_FIRST_ARCHITECTURE.md). This document describes how
> the engine is built; that one describes what is engine and what is not.

## Control plane vs data plane

The refactor's central decision (ADR-2 / high-level plan §3.2) is a clean split:

- **Control plane** — `generator_trunk/bundle/` (Python, ~25 modules). Owns the CLI, typed config,
  planning & budgets, the run/stage manifests, the state journal, cross-stage invariants,
  lifecycle (resume/cancel/cleanup), diagnostics (doctor), deploy, benchmark, inventory, hygiene,
  the execution-policy model, the Handoff v2 model, and the shard helper. It is pure orchestration
  and **never executes generated candidate code in-process**.
- **Data plane** — the five trunks do the work, each as a **separate OS process**:
  - **Generator** (`fwgen`, Python, in-proc helper) → an `.xlsx` workbook the Core understands.
  - **Core** (`Core_trunk`, Java + PostgreSQL) → materializes combinatorial relations into
    `fw_final` (and `fw_opt*` for optional actions).
  - **Sieve** (`constraints/sieve.py`, Python + PostgreSQL) → deletes invalid rows from `fw_final`.
  - **Reader** (`Reader_trunk`, Java) → reconstructs each surviving row into loose files or shards,
    or streams it live over gRPC, and writes the legacy handshake **and** the Handoff v2 manifest.
  - **Executor** → runs each candidate under a policy, classifies the outcome, persists results.
    Two language paths, both launcher-wired by the manifest's `language` / `--lang`: **Python**
    (`Executor_trunk/py_executor.py`, `sandbox.py` backends) and **Java** (`MainWatch` +
    `AdaptiveJavaCompiler`, Janino/ECJ, `-dirJars` deps), the latter verified end-to-end in
    trusted-local (see [09](09_READER_EXECUTOR_AND_RESULTS.md)).
  - **Analyzer** (`Analyzer_trunk`, Java `AnalyzeKv`) → ingests candidate `K=V` metrics, aggregates
    repeat-aware samples, computes a selected multi-objective front, and writes provenance and an
    optional `BundleSeed` feedback artifact.

`bundle_run.py` is a thin compatibility shim: `from bundle.cli import main`.

## Top-level flow

```mermaid
flowchart LR
  spec[TOML spec v1] --> plan[bundle plan\nbudgets/run-class]
  plan -->|under budget| gen[Generator\nfwgen → .xlsx]
  gen --> core[Core (Java)\nfw_final in main DB]
  core --> sieve[Sieve (Python)\nprune invalid rows]
  sieve --> reader[Reader (Java)\ncandidates + Handoff v2]
  reader --> exec[Executor (Python or Java)\npolicy-controlled run + verdict]
  exec --> resdb[(Results DB\nlegacy + results_v2)]
  exec --> analyzer[Analyzer (Java)\nformal/exploratory Pareto]
  resdb --> analyzer
  analyzer --> report[provenance.json\nPareto front]
  subgraph controlplane[Control plane — generator_trunk/bundle]
    plan
  end
```

## Process, DB, artifact and security boundaries

```mermaid
flowchart TB
  subgraph host[Host (trusted)]
    cli[bundle CLI / launcher]
    maindb[(main DB :5433\ncluster 'main')]
    resdb[(results DB :5432\ncluster 'my_second_instance')]
    cli -->|spawn| corep[Core JVM]
    cli -->|spawn| readerp[Reader JVM]
    cli -->|spawn| execp[py_executor]
    cli -->|spawn| azp[AnalyzeKv JVM]
    corep --> maindb
    readerp --> maindb
    execp --> resdb
  end
  subgraph sbx[Sandbox (untrusted candidates)]
    cand[candidate.py\nread-only root, cap-drop ALL\nmem/cpu/pids/wall limits]
  end
  execp -->|per candidate| cand
  cand -.->|internal Docker net only\nno host ports, no egress| sut[SUT container]
```

- **Process boundary:** every data-plane stage is a child process (typed `CommandResult` from
  `bundle/process.py`); failures cross back as typed errors, not raw exit codes.
- **DB boundary:** Core/sieve/Reader use the **main** DB; the Executor writes the **results** DB.
  Results has a legacy per-run table `"<db>"` **and** an additive `public.results_v2` table; both
  are written in one combined transaction (atomicity).
- **Artifact boundary:** all exchange goes through the run directory (below) and the versioned
  Handoff v2 manifest; the manifest carries no secret.
- **Security boundary:** secure profiles execute candidates inside a fail-closed sandbox; the
  `trusted-local` profile is unsandboxed and is never a default — it must be selected explicitly
  with an origin classification and a recorded reason. Trusted-local Java runs candidate code
  inside the Executor process. Networking and host exposure therefore depend on the selected
  policy, not merely on the existence of a policy manifest. See
  [10_SECURITY_AND_SANDBOXING.md](10_SECURITY_AND_SANDBOXING.md).

## The run directory (run contract)

A run in run-directory mode (default) gets a stable `run_id` and an atomically-maintained tree
(`bundle/runs.py`, `bundle/journal.py`):

```
<scratch>/<db>/runs/<run_id>/
  run.json              # bundle.run/v1 manifest: id, spec sha256, settings (redacted),
                        #   component inventory, execution policy, status
  state.json            # derived run + per-stage status
  resolved_config.json  # typed config, secrets redacted
  stages/{gen,core,sieve,reader,executor,analyzer}.json   # bundle.stage-result/v1
  wb/*.xlsx             # generated workbook
  core_cwd/, reader_cwd/ fw.properties   # rendered from typed config
  src/                  # candidate artifacts (loose files or *.fwshard); empty for live gRPC
  handshake/{resultsDbURL,sqlTemplate,arguments,runFirstOnce}/   # legacy handshake
  handshake/handoff/manifest.json        # Handoff v2 (bundle.handoff/v2)
  execution_policy.json # secret-free policy the Executor reads
  executor-summary.json # outcomes + sandbox backend
  metrics.kv            # Analyzer corpus (harvested in-sandbox)
  provenance.json       # analyzer.provenance/v1
  logs/, reports/, metrics/, workbooks/, candidates/
```

Contract JSON written through `bundle/jsonio.py` is written temp→fsync→atomic-rename. Legacy
`--legacy-scratch` mode produces a flat tree without `run.json`/journal (no resume).

## Schemas & versions (machine-readable contracts)

| Schema id | File / source | Purpose |
|---|---|---|
| `bundle.spec/v1` | `generator_trunk/bundle-spec-v1.schema.json` | public authoring contract |
| `bundle.handoff/v2` | `generator_trunk/bundle-handoff-v2.schema.json` + `bundle/handoff.py` | Reader→Executor contract |
| `bundle.run/v1` | `bundle/models.py` | run manifest |
| `bundle.stage-result/v1` | `bundle/models.py` | per-stage result |
| `bundle.plan/v1` | `bundle/cli.py cmd_plan` | plan output |
| (policy) | `bundle/policy.py` | execution policy + profiles |
| `bundle.inventory/v1`, `bundle.hygiene/v1`, `bundle.benchmark/v1`, `analyzer.provenance/v1` | respective modules | tooling outputs |
| (unversioned `controlplane_plan.json`), BundleSeed `schemaVersion=1`, `bundle.iterate/v1` | control-plane / Analyzer code | repeat dispatch and iterative feedback |
| results_v2 DDL | `py_executor.py` (mirrors Java `ResultsV2SchemaMigrator`) | results persistence |

A built-in mini JSON-schema validator (`handoff.validate_against_json_schema`) means **no `pip
jsonschema` dependency** is required at runtime.

## Count / invariant boundaries

Cross-stage counts are first-class success criteria (`bundle/invariants.py`, raised by `enforce()`):
see the chain and the full invariant list in
[06_PLANNING_BUDGETS_AND_COUNTS.md](06_PLANNING_BUDGETS_AND_COUNTS.md) and
[08_RUN_CONTRACTS_AND_SCHEMAS.md](08_RUN_CONTRACTS_AND_SCHEMAS.md).

## Retry / resume / idempotency boundaries

- **Resume** (`bundle/resume.py`): reuse a stage only if it `SUCCEEDED`, its critical invariants
  passed, its input hashes/artifacts still match, and (DB stages) live counts match — else that
  stage and everything downstream rerun.
- **Idempotency** (`py_executor.py`, mirrored by Java): `results_v2` uniquely identifies an
  immutable sample by `(run_id, candidate_id, attempt, repeat_idx, env_id)`. The old three-column
  index is retired. “Latest attempt wins” is a read-time query rule; there is no selected-final
  partial index.
- **Cancel/cleanup** (`bundle/cancel.py`, `bundle/cleanup.py`): owned-PID registry; run/DB-identity
  scoped deletion with symlink/traversal refusals.

## Legacy compatibility paths

`--legacy-scratch` (no run dir/journal), `--legacy-handoff` (file handshake authoritative, manifest
skipped), legacy `fw.properties` still rendered, legacy results table + boolean `status` preserved
(`status = outcome == PASS`), pre-v1 specs accepted (compat warns, strict rejects). See
[16_LEGACY_TO_V2_MIGRATION.md](16_LEGACY_TO_V2_MIGRATION.md).

## Where implementation diverges from the high-level plan

- No standalone `bundle status` subcommand for runs (status lives in `state.json`/stage JSON; the
  `status` subcommand belongs to `bundle deploy`).
- The Java Executor is launcher-wired (`--lang java`). Dated 2026-06-11 evidence covers both
  trusted-local and its **container/secure** variant (`SandboxedJavaRunner`). Java + `--analyzer`
  **is supported**: the in-sandbox metrics-harvest transport (`MainWatch -metricsFile`) shipped, so
  there is no fail-closed check for that pair in `preflight()`. See the generated
  [capability matrix](33_CAPABILITY_MATRIX.md), which is derived from the registry rather than
  hand-written.
- Handoff v2 now has three transports: loose files, shards, and live gRPC. gRPC is currently
  Java/verdict/v2/trusted-local only and plaintext/unauthenticated; the launcher starts the Executor
  before the Reader and adopts it after the stream drains.
- Local `metrics` and `all` repeat execution is launcher-wired for Python and Java. Disperse/nested
  remain launcher-refused even though `BundleControlPlane` provides a standalone Java seam.
- These are documented deviations, not defects; see
  [21_ARCHITECTURE_DECISIONS.md](21_ARCHITECTURE_DECISIONS.md).
