# The Bundle (Combinatorics Framework) — Documentation

> **Bundle is an executable combinatorial design-space and evidence engine. AI response testing is a
> reference application.**
>
> A compiler and execution pipeline for **structured experiments**: describe the degrees of
> freedom of a problem, exclude impossible combinations, synthesize executable candidates, run
> them under a domain oracle, and select the useful outcomes by multi-objective analysis.

This QA edition omits historical handoffs, publication-option paperwork, provenance media, and
generated candidate corpora; operational and capability documentation remains.

This documentation set began as the STEP 45 deliverable after the STEP 44 release-candidate gate.
Sections that quote 2026-06-11 runs are **dated evidence**, not a claim that those measurements were
rerun later. Operational references have since been updated for the repeat-aware results schema,
live gRPC transport, Java executor pool, seed/iterate loop, and newer Analyzer. Each document must
therefore distinguish current source-derived behavior from dated measurements.

## What the Bundle is, in one paragraph

The Bundle turns a declarative spec (TOML) of combinatorial *freedoms* — exactly-one, k-of-n,
subsets, orderings, optional "sudden actions" — into a relational expansion in PostgreSQL (the
**Core**), prunes invalid combinations with a constraint **sieve**, reconstructs each surviving
combination into an executable candidate (the **Reader**), runs every candidate under an explicit
execution policy (the **Executor**) recording a canonical outcome and a domain verdict, and
finally selects the non-dominated candidates against explicit objectives (the **Analyzer**). One
CLI (`bundle_run.py` / the `bundle` package) plans, runs, resumes, cancels, cleans up, and
diagnoses the whole chain, with a versioned run contract and machine-enforced cross-stage
invariants.

## Reader routing — by role and goal

| You are… | Start here |
|---|---|
| **Asking what is engine and what is a replaceable application** | [30_ENGINE_FIRST_ARCHITECTURE.md](30_ENGINE_FIRST_ARCHITECTURE.md) |
| **Wanting the smallest complete proof of advanced composition** | [../generator_trunk/engine_demo/README.md](../generator_trunk/engine_demo/README.md) |
| Evaluating whether the Bundle fits your problem | [01_EXECUTIVE_OVERVIEW.md](01_EXECUTIVE_OVERVIEW.md) |
| An architect/reviewer mapping the system | [02_ARCHITECTURE.md](02_ARCHITECTURE.md), [21_ARCHITECTURE_DECISIONS.md](21_ARCHITECTURE_DECISIONS.md), [30_ENGINE_FIRST_ARCHITECTURE.md](30_ENGINE_FIRST_ARCHITECTURE.md) |
| Installing / standing up the local stack | [03_INSTALLATION_AND_LOCAL_DEPLOYMENT.md](03_INSTALLATION_AND_LOCAL_DEPLOYMENT.md) |
| Running it (CLI, lifecycle) | [04_CLI_AND_LIFECYCLE_REFERENCE.md](04_CLI_AND_LIFECYCLE_REFERENCE.md) |
| Authoring a spec | [05_SPEC_V1_AUTHORING_GUIDE.md](05_SPEC_V1_AUTHORING_GUIDE.md), [07_CONSTRAINTS_GUIDE.md](07_CONSTRAINTS_GUIDE.md) |
| Understanding `RunMeFirstOnce` and its boundary with HEAD/TAIL | [RUNMEFIRSTONCE_LOGICAL_CONSTRUCT.md](RUNMEFIRSTONCE_LOGICAL_CONSTRUCT.md) |
| Drawing constraints visually / the end-user "three faces" UX | [07_CONSTRAINTS_GUIDE.md](07_CONSTRAINTS_GUIDE.md) (`--draw`), [26_PLAN3_THREE_FACES_UX.md](26_PLAN3_THREE_FACES_UX.md) |
| Describing a task without FW_ vocabulary (Face 1) + firing/tracing a real run + Face 3 results | [29_FACE1_INTAKE_AND_REAL_RUN.md](29_FACE1_INTAKE_AND_REAL_RUN.md) (`generator_trunk/intake/`) |
| Understanding the DB tables (fw_final/fw_optX/base_copy/NumberToValue1) + Reader assembly | [27_TABLE_ARCHITECTURE_AND_READER_ASSEMBLY.md](27_TABLE_ARCHITECTURE_AND_READER_ASSEMBLY.md) |
| **Understanding the Core engine FAST** (lifecycle, file map, Short codes, verbs, brace nesting / `FW_Group`, stores, the traps) | [../Core_trunk/AI_QUICK_CORE_UNDERSTANDING.md](../Core_trunk/AI_QUICK_CORE_UNDERSTANDING.md), [../ZEN_OF_COMBINATORICS.md](../ZEN_OF_COMBINATORICS.md), [28_SECOND_ORDER_AXES_AND_NESTED_BONDS.md](28_SECOND_ORDER_AXES_AND_NESTED_BONDS.md) |
| Worried about combinatorial explosion / cost | [06_PLANNING_BUDGETS_AND_COUNTS.md](06_PLANNING_BUDGETS_AND_COUNTS.md) |
| Wiring Reader/Executor/results internals | [08_RUN_CONTRACTS_AND_SCHEMAS.md](08_RUN_CONTRACTS_AND_SCHEMAS.md), [09_READER_EXECUTOR_AND_RESULTS.md](09_READER_EXECUTOR_AND_RESULTS.md) |
| Configuring repeats, environments, and the Java control-plane seam | [24_PLAN1_PHASE0_CONTRACT_DELTA.md](24_PLAN1_PHASE0_CONTRACT_DELTA.md), [25_PLAN2_CONTROL_PLANE_ADR_AND_BASELINE.md](25_PLAN2_CONTROL_PLANE_ADR_AND_BASELINE.md) |
| Understanding Executor multi-threading, multi-source watches, and precompiled Docker dispatch | [29_EXECUTOR_CONCURRENCY_AND_PRECOMPILED_DISPATCH_2026-07-02.md](29_EXECUTOR_CONCURRENCY_AND_PRECOMPILED_DISPATCH_2026-07-02.md) |
| Running untrusted/generated code safely | [10_SECURITY_AND_SANDBOXING.md](10_SECURITY_AND_SANDBOXING.md) |
| Open execution-safety findings and the contract audit | [32_EXECUTION_SAFETY_AUDIT.md](32_EXECUTION_SAFETY_AUDIT.md) |
| **QA-edition scope and non-operative personal-use intent** | [qa_edition/README.md](qa_edition/README.md) |
| **Which combinations are supported** (generated) | [33_CAPABILITY_MATRIX.md](33_CAPABILITY_MATRIX.md) |
| Dependency locking, CI tiers, skip classification, SBOM | [34_RELEASE_REPRODUCIBILITY.md](34_RELEASE_REPRODUCIBILITY.md) |
| **Does advanced construction find defects the alternatives miss?** (flagship SUT, mutants, baselines, executed ladder, full-chain reconciliation) | [35_FLAGSHIP_DECISION_AND_BASELINES.md](35_FLAGSHIP_DECISION_AND_BASELINES.md) (§6a: does it reproduce on a second, dissimilar SUT?) |
| Interpreting Analyzer output | [11_ANALYZER_GUIDE.md](11_ANALYZER_GUIDE.md) |
| Operating / troubleshooting | [12_OPERATIONS_AND_TROUBLESHOOTING.md](12_OPERATIONS_AND_TROUBLESHOOTING.md) |
| Reading scale/benchmark claims | [13_BENCHMARKS_AND_SCALE_CLAIMS.md](13_BENCHMARKS_AND_SCALE_CLAIMS.md) |
| Current engine-first evidence (gates, coverage, overhead) | [31_ENGINE_FIRST_EVIDENCE.md](31_ENGINE_FIRST_EVIDENCE.md) |
| Looking for a scenario like yours | [14_SCENARIO_CATALOG.md](14_SCENARIO_CATALOG.md) |
| Reviewing the AI combinatorial testing proof of concept and count fix | [AI_COMBI_SESSION_FINDINGS_2026-07-29.md](AI_COMBI_SESSION_FINDINGS_2026-07-29.md) |
| Doing it end-to-end the first time | [15_FLAGSHIP_TUTORIAL.md](15_FLAGSHIP_TUTORIAL.md) |
| **A command that used to work has stopped working** (Phases 01-05 breaking changes, migration and how to revert) | [38_MIGRATION_PHASE_01_05.md](38_MIGRATION_PHASE_01_05.md) |
| **CI cannot check out the private sibling SUT** (the deploy key / PAT it needs, rotation, and what each pre-flight failure means) | [40_SIBLING_SUT_CREDENTIAL.md](40_SIBLING_SUT_CREDENTIAL.md) |
| Migrating from the pre-refactor Bundle | [16_LEGACY_TO_V2_MIGRATION.md](16_LEGACY_TO_V2_MIGRATION.md) |
| Extending the code | [17_DEVELOPER_GUIDE.md](17_DEVELOPER_GUIDE.md), [19_API_AND_SCHEMA_REFERENCE.md](19_API_AND_SCHEMA_REFERENCE.md) |
| Implementing or independently verifying repeat-policy / Loom plans | [22_PLAN1_PLAN2_QA_READINESS.md](22_PLAN1_PLAN2_QA_READINESS.md) |
| Plan-1 Phase 0: traced mechanics + design-contract delta (v4: resolves #1,2,3,5,6 + RunClass; #4 deferred to Phase 4; #7-12 traced, Plan-2 blocked) | [24_PLAN1_PHASE0_CONTRACT_DELTA.md](24_PLAN1_PHASE0_CONTRACT_DELTA.md) |
| Auditing the release | [18_VERIFICATION_AND_RELEASE_REPORT.md](18_VERIFICATION_AND_RELEASE_REPORT.md) |
| Looking up a term | [20_GLOSSARY.md](20_GLOSSARY.md) |

## Verified support / status statement

- **Platform:** Linux (Ubuntu 24.04, kernel 6.17). The sandbox backends (bubblewrap, rootless
  Docker) and the local deploy stack are Linux-specific.
- **Toolchain:** the 2026-06-11 evidence host used Python 3.12.3, Java 21 (GraalVM), Maven 3.9.15,
  PostgreSQL 18.4 (host) / 16.9 (deploy containers), and Docker 29.5.3 (rootless). The current full
  reactor requires JDK 25 because Reader and Executor target 25; Core, Analyzer, and shared-library
  modules target 21.
- **Maturity:** an advanced engineering/research platform with a working, observable, fail-closed
  end-to-end path. **Release recommendation: READY WITH LIMITATIONS** — see
  [18_VERIFICATION_AND_RELEASE_REPORT.md](18_VERIFICATION_AND_RELEASE_REPORT.md).
- **Proven at bounded scale (288-candidate secure flagship) and a 10K stage benchmark.**
  Multi-million Core invariants are source-confirmed fixtures; billion-scale end-to-end is
  **not** claimed. Every scale number in these docs names its stage and evidence.

> Placeholders: examples use `$PGPW` for the PostgreSQL password (never write a real secret into a
> file), `<run-dir>` for a run directory, and the canonical host DB ports (main `5433`, results
> `5432`). Adjust to your environment.

> Security default: there is **none** — a run refuses to execute until an execution policy is
> explicitly chosen (planning needs none). `generated-default` is sandboxed and fail-closed;
> `trusted-local` is unsandboxed and additionally requires an origin classification and a
> recorded reason. The live Java gRPC candidate channel is
> plaintext, unauthenticated, and supported only with `trusted-local`; keep it on a trusted host
> (loopback by default).
