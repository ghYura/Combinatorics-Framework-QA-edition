# 17 — Developer Guide

## Repository / component layout

```
Combinatorics-Framework/
  generator_trunk/         # CONTROL PLANE + Generator
    bundle/                # cli, config, planning(budgets,resources), models, runs, journal,
                           #   stages, process, database, invariants, handoff, policy, jsonio,
                           #   resume, cancel, cleanup, doctor, deploy, benchmark, inventory,
                           #   hygiene, shards, counts, controlplane, seedbias
    bundle_run.py          # thin shim -> bundle.cli.main
    fwgen.py / fwgen_cli.py / fwseq_graph.py / code_decompose.py
    bundle-spec-v1.schema.json, bundle-handoff-v2.schema.json
    constraints/sieve.py   # the bonds layer
    test_bundle_*.py, test_fwgen*.py, test_fwseq_graph.py, ...
  Core_trunk/      # Java + PostgreSQL (combinatorial expansion); README_CANONICAL_TRUTH.txt
  Reader_trunk/    # Java 25 (loose/sharded/gRPC sinks, Handoff v2 writer)
  Executor_trunk/  # Java 25 + py_executor.py, sandbox.py, worker_pool.py, backpressure.py, shard_reader.py;
                   #   Java MainWatch + compiler/ + SandboxedJavaRunner; test_*.py
  Analyzer_trunk/  # Java AnalyzeKv + core/optimization/ (AnalysisMode, provenance)
  _archive/        # STEP 43 archived backups (28 files; excluded from compile source sets)
  docs/            # this set
```

## Canonical builds & tests

```bash
# Fresh full-reactor build: use JDK 25. Core/Analyzer/shared modules target 21;
# Reader and Executor target 25. The first build may download dependencies.
mvn -q clean package

# Component builds after the Maven cache is warm (jars are not byte-reproducible):
(cd Core_trunk && mvn -o -q -DskipTests -Dexec.skip=true package)
(cd Reader_trunk && mvn -o -q -DskipTests -Dexec.skip=true package)
(cd Analyzer_trunk && mvn -o -q -DskipTests -Dexec.skip=true package)
python3 -m py_compile generator_trunk/bundle/*.py Executor_trunk/py_executor.py   # interpreted

# Targeted Python tests in the repository-local environment:
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
(cd generator_trunk && python3 -m pytest test_fwgen.py test_fwgen_aliases.py test_bundle_*.py -q)
(cd Executor_trunk && python3 test_py_executor_outcomes.py && python3 -m pytest test_py_executor_sandbox.py -q)
# DB-gated tests need BUNDLE_RESULTS_DB_PASSWORD and a reachable local Postgres (they fail closed otherwise).
```

Verify artifact identity any time:
`python3 generator_trunk/bundle_run.py inventory --out inv.json`.

## Coding / contracts conventions

- **Use the repository-local `.venv`** for development and test extras. A system interpreter can
  run the minimal path, but must not be treated as the canonical fresh-checkout setup.
- **JSON contracts, language-specific implementations** (ADR-3): Python and Java share schemas, not a
  runtime. When you touch a contract on one side, mirror it on the other (e.g. `results_v2`
  DDL/writer exist in both `py_executor.py` and Java `ResultsV2SchemaMigrator`/`ResultsV2Writer`).
- **Atomic contract writes** through the shared JSON/artifact helpers (temp → fsync → replace).
- **Fail closed**: a missing secret, an unknown schema major, an unavailable secure backend, or a
  failed CRITICAL invariant must stop the run, not degrade silently.
- **Quantitative honesty**: tag every count EXACT/BOUNDED/ESTIMATED/UNKNOWN with a formula.
- **Record artifact hashes after finalization** (BUG-2 lesson): if a later step mutates an artifact
  (e.g. the policy stamp on the handoff manifest), record its hash *after* the mutation so resume
  reuse matches.
- **Never re-execute candidates to collect data** (BUG-1 lesson): harvest from the real (sandboxed)
  run; a second host-side run is a sandbox bypass and is wrong for stateful candidates.

## How to add …

- **a spec** → drop one `.toml` (spec v1) in a directory; `bundle plan <dir>` to validate; run with
  `bundle_run.py <dir>`. Use `--out` for `plan` if you keep other files in the dir (Bundle artifact
  JSONs are auto-skipped by the loader — BUG-5 fix — but other stray specs still load).
- **a Java spec** → same TOML model, `raw=true` chunks of Java, run with `--lang java`. Keep all
  shared state in the invariant HEAD (static fields / HEAD-declared `var`); each permutable/optional
  chunk a self-contained statement (so every combo compiles). Author the main `class` first (nested
  `record`/`interface` after it). Worked examples + a repeatable test:
  `generator_trunk/java_e2e/{janino_max,ecj_modern}` + `test_java_e2e_specs.py`. The external
  rules API source/build lives under `Executor_trunk/lib-src/`; the Bundle CLI's current default
  dependency-JAR directory is `Executor_trunk/lib-src/target`. Pin the backend with
  `--executor-compiler` or override `--java-jars-dir`.
- **a constraint** → add `[[params]]` + `[[constraints]]` to the spec; verify with
  `bundle constraints explain/dry-run`. Logic lives in `constraints/sieve.py`.
- **a Reader sink** → implement `CandidateSink` (Java `Reader_trunk/.../sink/`), register in
  `CandidateSinkRegistry`; mirror the handoff/schema/Executor side. Existing transports are loose,
  sharded, and live gRPC; gRPC also needs launcher start-before-Reader/adoption semantics.
- **an Executor backend** → implement `SandboxBackend` (`Executor_trunk/sandbox.py`:
  `build_argv`/`is_available`/`run`/`describe`/`close`), and a profile in `bundle/policy.py`.
- **an Analyzer metric/goal** → goals are data (`key:dir`); for new discovery/normalization logic see
  `Analyzer_trunk/.../optimization/` (`AnalysisMode`, `AutoAnalysisPlanner`).

## Extension points & coupling

Components are independently runnable (ADR-2) and communicate only through the run directory + the
versioned manifests. Keep new coupling behind a schema, not a shared runtime. The control plane never
imports Core/Reader/Executor/Analyzer code — it spawns them.

## Test strategy & remaining gaps

Per-component targeted suites cover the contracts (planning, repeats, config, invariants, handoff,
policy, outcomes, repeat-aware results_v2, worker/executor pools, backpressure, shards, gRPC,
resume, cancel, cleanup, doctor, deploy, provenance, seed iteration, aliases, graph). Dated
2026-06-11 evidence includes Java secure E2E and BUG-4 benchmark cleanup. Remaining boundaries:
some Executor tests are DB/container-gated, Java Analyzer metrics remain refused, the Bundle
launcher does not execute disperse/nested repeat policy, and multi-million regressions are not run
by default. See [18](18_VERIFICATION_AND_RELEASE_REPORT.md).
