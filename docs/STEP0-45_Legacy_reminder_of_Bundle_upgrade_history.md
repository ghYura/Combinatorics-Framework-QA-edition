# Combinatorics Framework ("the Bundle") Refactoring Master Document

**Role:** Senior Software System Architect / DevOps Executor

**Domain Scope:** `generator_trunk` → `Core_trunk` → `Reader_trunk` → `Executor_trunk` → `Analyzer_trunk`

## I. Architectural Charter & Principles

The objective is to mature the Bundle from an environment-sensitive component chain into a managed, local compilation/execution platform for structured experiments, without degrading its highly scalable Core.

* **Evolutionary Architecture:** Retain existing components as the *data plane*; construct a unified *control plane* around them.
* **No Core Rewrite:** Core logic (combinatorics, memory protection, Postgres/memory paths) remains intact.
* **Contract-First Orchestration:** Stabilize run/candidate identity, stage results, and handoff manifests prior to scale optimizations.
* **Fail-Closed State Machine:** Runs must abort if row counts diverge, constraints break, budgets exceed, or secure backends are missing.
* **Quantitative Honesty:** Output counts must define exactness, bounds, formulas, and stage provenance.
* **ADRs (Architecture Decision Records):**
* **ADR-1 & 2:** Generator owns the control plane; components remain independently executable.
* **ADR-3 & 4:** Shared JSON schemas cross-language; Additive DB migrations to preserve legacy views.
* **ADR-5 & 6:** Strict separation of exploratory vs. formal Analyzer modes; Fail-closed pluggable sandboxes.

---

## II. Target Metrics Matrix

| Domain | Baseline | Target | Optimization Vector |
| --- | --- | --- | --- |
| **Originality & Core Expressiveness** | 9/10 | 9/10 | Freeze semantics; retain mechanics/bonds model. |
| **High-Volume Generation** | 8/10 | 9/10 | Planner integration, stage benchmarks, strict reproducibility. |
| **Constraint Modeling** | 8/10 | 9/10 | Dry-run capabilities, per-rule explain statistics. |
| **End-to-End & Determinism** | 8/10 | 9/10 | Versioned contracts, hashes, manifest IDs, stage resume. |
| **Analyzer Capability** | 8/10 | 9/10 | Explicit objectives, candidate provenance, Pareto non-dominance explanation. |
| **Usability (Authoring / Ops)** | 5-6/10 | 8/10 | Stable schemas, `bundle plan`, domain aliases, CLI state journal, zero-cleanup. |
| **Security & Portability** | 4/10 | 8/10 | Sandbox policies, resource limits, secret redaction, container profiles. |
| **Documentation & Readiness** | 5-6/10 | 7-8/10 | Document *last* post-stabilization; rely on JSON schemas initially. |

---

## III. Strict Execution Protocol (Definition of Done)

Execution strictly iterates sequentially via atomic steps requiring explicit manual user approval (`continue`).

* **Targeted Validation:** Perform minimal `py_compile`, syntax lints, and narrow checks per step.
* **Milestone Testing:** Full 288-candidate E2E workflows only trigger at designated milestone gates; multi-million bounds require explicit bypass.
* **Immutability:** No destructive git rollbacks, `claude`-path traversal, or deletion of historical files without exact authorization.

---

## IV. Integrated Execution Plan (Phases 0–10 / Steps 0–45)

### Phase 0: Baseline Initialization

* **Step 0 (Baseline):** Audit `git status` across all 5 trunks, document entry points/JARs/DB ports without mutations, and freeze canonical counts.

### Phase 1: Control Plane Extraction

* **Step 1 (CLI Skeleton):** Scaffold `generator_trunk/bundle/` package (CLI, processes, DB helpers), leaving `bundle_run.py` as a thin shim.
* **Step 2 (Typed Execution):** Implement `CommandResult` object and centralized `BundleError` hierarchy to eliminate nested `sys.exit` calls.

### Phase 2: Run Contracts & State Machine (Milestone A)

* **Step 3 (JSON Infrastructure):** Introduce versioned atomic JSON writers for `RunStatus`, `StageResult`, and secret redaction utilities.
* **Step 4 (Run Identity):** Generate robust `run_id` and scaffold the atomic directory tree (`run.json`, `stages/`, `logs/`, `handoff/`).
* **Step 5 (Stage Journaling):** Wrap stages in discrete `RUNNING` → `SUCCEEDED`/`FAILED` states, logging I/O counts and artifacts.
* **Step 6 (Invariants Evaluator):** Centralize cross-stage validation (e.g., Core product ≥ post-sieve) blocking execution on cardinality mismatch.
* **Step 7 (Gate A):** Execute a bounded compatibility E2E run validating reference counts (Core 96, sieve 72, Executor 288) against legacy CLI inputs.

### Phase 3: Cardinality Planning & Budgets

* **Step 8 (Spec Schema):** Add `bundle-spec-v1.schema.json` with strict/legacy Python loaders for syntax validation.
* **Step 9 (Confidence Models):** Code `CardinalityEstimate` differentiating EXACT, BOUNDED, and ESTIMATED calculations across operators.
* **Step 10 (Plan Command):** Ship `bundle plan` CLI to statically assess constraint impacts and expected candidate counts without Core materialization.
* **Step 11 (Resource Estimation):** Introduce run classes (S/B/L/X) computing disk IO/inode/wall-time profiles.
* **Step 12 (Budget Gates):** Block generation strictly on hard thresholds (rows, bytes, cost) requiring explicit `--allow-extreme` CLI overrides.

### Phase 4: Configuration & Portability

* **Step 13 (Config Layering):** Implement `BundleConfig` resolving `CLI > env > file > default` priorities.
* **Step 14 (Secret Erasure):** Purge hardcoded paths (`/mnt/F`) and plaintext PG properties, relying on env/config injection.
* **Step 15 (Diagnostics):** Launch `bundle doctor` evaluating JAR hashes, Python/Java versions, backend capabilities, and DB connectivity.

### Phase 5: Handoff v2 (Reader → Executor)

* **Step 16 (Handoff Schema):** Formalize `bundle-handoff-v2.schema.json` mapping candidate arrays, limits, and arguments (e.g., `fwVar.shift`).
* **Step 17 (Reader Output):** Enable Reader dual-write emission supporting legacy directories alongside the unified JSON manifest.
* **Step 18 & 19 (Executors):** Patch Python and Java Executors to natively consume Handoff v2.
* **Step 20 (Launcher):** Wire control plane strictly to Handoff v2, isolating legacy repair logic to explicit adapters.

### Phase 6: Outcomes, Idempotency, Resume (Milestone B)

* **Step 21 (Canonical Outcomes):** Standardize failure classes: `PASS`, `DOMAIN_FAIL`, `BROKEN`, `TIMEOUT`, `INFRA_FAIL`, `SKIPPED`, `CANCELLED`.
* **Step 22 (DB Migration):** Execute additive, non-destructive V2 Results schema capturing attempts, signals, and worker providence.
* **Step 23 (Idempotent IO):** Refactor DB insertions forcing bounded batches to reject silent duplicate execution results.
* **Step 24 (Stage Resume):** Unlock `bundle resume` safely bypassing verified stages matching previous input hashes.
* **Step 25 (Lifecycle UX):** Implement `cancel` (orphan process killing) and `cleanup --dry-run`.
* **Step 26 (Gate B):** Full Bounded V2 workflow verifying zero duplication on interruption and resumability.

### Phase 7: Security Isolation (Milestone C)

* **Step 27 (Policies):** Introduce sandbox definitions dictating timeouts, disk caps, CPU quotas, and whitelist envs.
* **Step 28 (Python Sandbox):** Integrate Linux backend (bubblewrap/systemd) blocking network access on generated binaries.
* **Step 29 (Java Sandbox):** Detach Java workloads from in-process JDK backends into isolated subprocess boundary walls.
* **Step 30 (Gate C):** Bounded secure run testing infrastructure termination via deliberate sandbox violation probes.

### Phase 8: Scaling Paths

* **Step 31 (Sink Interfaces):** Abstract Reader pipelines behind `LooseFileSink` decoupled from raw IO algorithms.
* **Step 32 (Shard Sinks):** Implement deterministic compressed sharding reducing L-class inode bloat.
* **Step 33 (Worker Pools):** Spin local deterministically assigned sharded executor pools.
* **Step 34 (Backpressure):** Cap pipeline queues stalling Readers when Executor processing lags.

### Phase 9: Authoring, Constraints & Analysis

* **Step 35 (Sieve Explain):** Build `bundle constraints explain` analyzing unique subset removals prior to destructive DB filtering.
* **Step 36 (Aliases):** Supply syntax simplifications (`choose_k`, `permute`) compiling down to legacy verbs.
* **Step 37 (FW_Seq DAG):** Produce verifiable JSON/DOT graphs exposing operator logic cycles.
* **Step 38 (Analyzer Modes):** Hard-fork Analyzer UX into explicitly requested `formal` (rigid) and `exploratory` (inferred) operational modes.
* **Step 39 (Provenance):** Wire Analyzer exports to trace objective dominance specifically to upstream candidate IDs.

### Phase 10: Validation & Documentation (Milestone F)

* **Step 40 (Benchmarking):** Deliver configurable 10K/1M bounds-profiling harnesses tracking granular stage metrics (CPU/WAL/Disk).
* **Step 41 (Containerization):** Provide immutable local PostgreSQL dev clusters pinning environment dependencies.
* **Step 42 (SBOMs):** Inject artifact hashing and version matrix extraction across all toolchains.
* **Step 43 (Repo Hygiene):** Isolate legacy backups safely pending User approval, dropping obsolete objects from scan paths.
* **Step 44 (Gate F):** Launch Final Release Candidate E2E checks asserting invariants, dry-runs, and formal outputs.
* **Step 45 (Documentation):** Generate public architectural mappings, CLI guides, schema references, and legacy migrations strictly tracking final stable state.

---

## V. System-Wide Invariants

Cross-boundary reconciliation math required to flag operations `SUCCEEDED`:

* `planned mandatory ≥ 0` & `actual Core mandatory ≥ 0`.
* `post-sieve ≤ Core mandatory`.
* `expected Reader candidates == post-sieve * optional multiplier`.
* `Reader emitted == expected Reader candidates`.
* `Executor processed == PASS + DOMAIN_FAIL + BROKEN + TIMEOUT + INFRA_FAIL + SKIPPED + CANCELLED`.
* `persisted results == persistence-policy expected count`.
