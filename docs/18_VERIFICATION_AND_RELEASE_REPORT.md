# 18 — Verification and Release Report (STEP 44)

**Date:** 2026-06-11 · **Workspace:** Bundle repository root.

This is a dated narrative report. Run-specific machine-readable evidence lives in each run
directory; no repository-level release-gate or scenario-evidence JSON is committed.

## Current-source errata and supersession

This report preserves the order in which evidence was gathered on 2026-06-11. Later paragraphs on
that same date supersede earlier statements: BUG-4 was fixed, fintech was verified, and the Java
secure path was exercised end-to-end after the initial trusted-local addendum. Accordingly, the
final “path to plain READY” sentence from the initial report is superseded by those addenda and is
rewritten below as a historical note.

Several current features postdate this gate and were **not measured by STEP 44**: repeat-aware
`results_v2` schema v2, local K>1 execution, BundleControlPlane/BundleSeed/iterate, Java Executor
pooling, and live gRPC candidate transport. Current schema identity is
`(run_id,candidate_id,attempt,repeat_idx,env_id)` with latest-attempt selection at read time; any
three-column identity quoted below describes the then-current K=1 evidence, not today's DDL.

## Release recommendation: **READY WITH LIMITATIONS**

The Bundle passes all ten STEP 44 critical gates with canonical counts preserved, no secret leaked,
and no orphan/duplicate state. Two **release-blocking** bugs were found during the gate and fixed
(BUG-1, BUG-2), plus one minor test fix (BUG-3) and one pre-existing usability fix (BUG-5). A
follow-on **Java Executor** effort (2026-06-11 addendum) then verified the Java candidate path
end-to-end and fixed two Java seams (BUG-6, BUG-7), the previously-open BUG-4, and added
production-readiness improvements — all detailed below. The limitations below are real but bounded
and documented; none blocks a controlled expert release.

## STEP 44 gate table

| Gate | Name | Result | Key evidence |
|---|---|---|---|
| 2.1 | doctor (host + deploy) | **GREEN** | host `overall: OK`; deploy up → 2 healthy 16.9-alpine containers (127.0.0.1:15433/15432), `doctor --deploy` OK, `down` preserved volumes |
| 2.2 | flagship plan | **GREEN** | mandatory 96 EXACT, post-sieve BOUNDED, optional ×4, final 384 BOUNDED, class S, no DB side effects, no secret in plan.json |
| 2.3 | full 288 sandboxed run | **GREEN** | 96→72→288; 150 PASS/138 DOMAIN_FAIL/0 broken; rootless-Docker backend, `--internal` net (egress blocked, no host ports); run.json has inventory + env fingerprint + policy; provenance reaches Analyzer; **no local fallback** |
| 2.4 | resume no-op & idempotency | **GREEN** | resume ×2 reused all 6 stages, exit 0; results_v2 stayed 288, `distinct attempt={1}`, legacy 288 — no duplicates (after BUG-2 fix) |
| 2.5 | constraint explainability | **GREEN** | explain: removes 24, overlap 0, retained 72 + samples; dry-run mutates nothing (96→96); actual sieve 96→72 reconciles |
| 2.6 | formal Analyzer report | **GREEN** | formal, declared goals only, corpus 288 checked, 3-candidate front, provenance_ok, traceable; exploratory contrast documented (after BUG-1 fix) |
| 2.7 | cleanup dry-run | **GREEN** | enumerates only this run (319 files unchanged, DB matches, 288 rows); refuses mismatched `--db`; deletes nothing |
| 2.8 | 10K stage benchmark | **GREEN** | generator 85,056/s · sieve 4,819/s · core 1,105/s · reader_loose 695/s; stage-isolated, env captured, no large-scale run, no billion claim |
| 2.9 | builds | **GREEN** | Core/Reader/Analyzer offline maven build exit 0; generator/executor py_compile + tests; fresh inventory records artifact sha256 |
| 2.10 | hygiene & leak checks | **GREEN** | `git diff --check` clean ×5; manifests redacted; no orphan processes/containers/networks; no duplicate Results rows |

STEP 44 is **GREEN**: all critical gates green, canonical counts preserved, no secret leaked,
release issues explicitly enumerated.

## Scenario coverage summary

At the time of this dated report, 28 use-case families ([current catalog](14_SCENARIO_CATALOG.md)):
**19 runnable-verified** (incl. the flagship sandbox run, a trusted-local run, the **Java Executor
path** — Janino + ECJ end-to-end, see below — deploy, inventory, hygiene, constraints, benchmark,
resume/cleanup, formal+exploratory Analyzer, provenance, results_v2), **4 runnable-by-test** (sharded
sink, worker pool, backpressure, outcome classes), **2 runnable-by-plan** (pricing, API probe — same
mechanism as the flagship, need a local SUT), **3 blocked** with precise prerequisites (fintech
batches + multi-instance need the `finance_stack` services; external/LLM/cybersec/k8s blocked by the
external-scenario policy).

### Java Executor (post-STEP-44 addendum, 2026-06-11)

The Java candidate path was wired through the launcher and **verified end-to-end** with two
combinable specs under `generator_trunk/java_e2e/` (trusted-local, in-process compile):

- `janino_max` (classic Java) → Core 48 → Reader 48 `.java` → Java MainWatch → **29 PASS / 19
  DOMAIN_FAIL / 0 BROKEN**, `results_v2` 48; every combo compiles on **Janino**.
- `ecj_modern` (records/`var`/streams/lambdas/method-refs/switch-`yield`) → 48 → **24 PASS / 24
  DOMAIN_FAIL / 0 BROKEN**; every combo needs **ECJ** (forced-Janino → 48 BROKEN → fails closed;
  forced-ECJ → green; adaptive routes all to ECJ).
- External **dependency-JAR pass-through** (`-dirJars` `rules-api-1.0.0.jar`,
  `com.example.rules.Scorer`) resolved through **both** backends, visible in `executor.log`.
- Repeatable tests: `test_java_e2e_specs.py` (compiler routing/combinability, no DB) +
  `test_bundle_java_routing.py` (9 tests). At this point in the chronology the container/secure Java
  path (`SandboxedJavaRunner`, `generated-default`) was unit-tested but had not yet been exercised
  end-to-end; the later “Application directions + scale/distribution/secure-Java” addendum below
  records that subsequent E2E run.

## Canonical counts (reference, verified)

```
Core mandatory 96 → sieve removes 24 → post-sieve 72 → Reader 288 (= 72 × optional 4)
→ Executor processed 288 = 150 PASS + 138 DOMAIN_FAIL + 0 BROKEN/TIMEOUT/INFRA
→ persisted 288 (results_v2 288/288 distinct, legacy 288) → Analyzer ingested 288 → formal front 3
```

## Bugs found and corrected

| ID | Severity | Summary | Fix | Regression | Verified |
|---|---|---|---|---|---|
| **BUG-1** | release-blocking (security + correctness) | Analyzer corpus built by **re-executing candidates on the host** (sandbox bypass; truncated corpus 72/288) → formal Gate 2.6 failed | harvest the metrics line in-sandbox during the real run (`py_executor --metricsFile`); collect_kv re-run kept only as trusted-local/legacy fallback | 3 tests in `test_py_executor_outcomes.py` | gate-final corpus 288/288, formal green |
| **BUG-2** | release-blocking (Gate 2.4) | reader recorded the handoff-manifest hash **before** the policy stamp → resume never reused reader/executor on secure runs; networked rerun failed | record the manifest artifact **after** `_persist_handoff_policy` | `test_resume_reuses_reader_when_recorded_manifest_hash_matches_policy_stamped_file` | resume ×2 reuse all stages, no dup rows |
| **BUG-3** | minor (test-only) | stale commit-failure test (`_FakeCursor` missing `rowcount` + outdated assertion); production behavior correct | add `rowcount`; assert stable message prefix | (existing test, repaired) | 9/9 outcome tests pass |
| **BUG-5** | medium (pre-existing usability) | `bundle plan <dir>` writes `plan.json` into the spec dir; the loader ingested it → `run`/`plan` crashed; shipped `api_probe/spec` was broken | `load_specs_dir` skips Bundle artifact JSONs (`schema` starts `bundle.`/`analyzer.`) | `test_load_specs_dir_skips_bundle_artifact_json` | 4 spec dirs load 1 spec each with plan.json present |
| **BUG-4** | minor (was open; now fixed) | the stage benchmark's reader stage provisions a results-side temp DB (`fwbench_*`) not tracked for cleanup → orphan on the results cluster | `PipelineContext.note_results_db()` tracks it; `cleanup()` drops it | (verified) reader benchmark leaves 0/0 fwbench DBs on both clusters | 2000-candidate reader bench → 0 orphans |
| **BUG-6** | medium (Java seam) | Java + `--analyzer` silently produced an EMPTY corpus (Java Executor has no metrics harvest; `collect_kv` lists `*.py` → 0 candidates; count mismatch was WARNING-only) → run went green with a meaningless front | refuse at preflight (mirrors the stress/legacy-handoff Java refusals) | `test_java_with_analyzer_is_rejected_in_preflight` | Java + `--analyzer` now fails closed |
| **BUG-7** | low (Java seam, fragility) | the Java executor stage read `summary_path`'s basename, but MainWatch writes the FIXED `executor-summary.json` into `-out2` → a differently-named `summary_path` would make the launcher look for a file that never existed | read `<out2>/executor-summary.json` regardless of basename | `test_java_summary_is_read_from_out2_fixed_name_not_summary_path_basename` | odd-named summary_path still resolves |

All fixes are minimal and additive; **no canonical truth number was changed** to make anything pass;
no public schema was broken. BUG-1's fix is security-relevant (it removes a sandbox bypass, bringing
the implementation into line with the stated fail-closed policy) — flagged for review. BUG-6's fix is
also fail-closed-aligned (it refuses a silently-degrading path).

### Production-readiness improvements (2026-06-11 addendum)

- **`executor.log`**: both executors (Python + Java) now persist full stdout/stderr to the run dir
  (like `core.log`/`reader.log`); MainWatch's per-candidate / dependency-JAR diagnostics were
  previously captured and dropped except the tail.
- **`--executor-compiler {adaptive,janino,ecj,javac}`**: new typed config field (CLI > env > file)
  that pins the Java compiler backend (`-Dfw.exec.compiler`); an invalid value fails closed.
  Regression: `test_executor_compiler_pins_backend_via_jvm_property`.
- **`unleash_initial_productivity_power`** (bool, default False): an expert opt-in that lifts the
  budget limiter — hard ceilings become advisory and X/extreme needs no `--allow-extreme`; recorded
  in the run manifest. Layered (CLI/env/file) with fail-closed bool parsing. Regression:
  `test_unleash_initial_productivity_power_makes_the_gate_advisory`. (Core's truth/verbs/cardinality
  are unchanged — this lifts the *limiter*, it does not detune the *engine*.)

### Application directions + scale/distribution/secure-Java validated (2026-06-11 addendum)

- **Six application directions** pulled up to verified runnable demos (`generator_trunk/usecases/`,
  see that README + [14](14_SCENARIO_CATALOG.md)): performance/Pareto, ETL, ML/LLM (deterministic +
  **two real local sklearn surrogates**), event-order/saga, and fintech against the **real
  `finance_stack` bank cluster** (blocked→verified).
- **Secure/container Java verified end-to-end** (`generated-default`, `eclipse-temurin`): 48
  candidates → 29 PASS / 19 DOMAIN_FAIL / 0 BROKEN, identical to trusted-local; adversarial seam
  audit all-green (`SandboxedJavaRunnerTest`).
- **Measured scale**: Core generation 10K→100K→1M (1M rows in 17 s, 58.9K rows/s, rising with
  scale); sieve is the bottleneck (~4.8K/s); `reader_shard` ~8× `reader_loose`. Worker pool ~5.5×
  on 8 cores. See [13](13_BENCHMARKS_AND_SCALE_CLAIMS.md).

## Unresolved / open issues (non-blocking)

- **OBS-1:** cleanup of a mismatched `--db` prints the refusal but exits 0 (refusal + no-delete are
  correct; only the exit code is cosmetic).
- **OBS-2:** `stage_analyzer` logs "harvested in-sandbox" even for a trusted-local (unsandboxed) run
  (the no-re-run harvest is correct; wording is imprecise).
- **LIM-1:** a non-no-op resume of a networked secure run does not re-establish the candidate env
  (`TRYOUT_URL`); re-pass `--sandbox-candidate-env`/`--sandbox-network-allowlist`. A clean no-op
  resume reuses all stages and needs nothing.
- **LIM-2 (updated 2026-06-11):** the Java Executor is launcher-wired and **verified end-to-end in
  both trusted-local and the container/secure path** (`generated-default`, `eclipse-temurin`; 48
  candidates identical to trusted-local; adversarial seam audit green). Remaining: Java + `--analyzer`
  is refused (no in-sandbox metrics harvest yet — BUG-6), and the secure path should be validated
  against a multi-tenant threat model (microVM/SEV-SNP) before shared-SaaS use.
- **Build identity:** maven jars are not byte-reproducible (timestamps), so `--baseline --policy
  block` flags every rebuild.

## Orphan / secret / duplicate checks (final)

- **Processes:** 0 orphan candidate/Bundle processes.
- **Containers/networks:** 0 orphan sandbox containers; 0 orphan sandbox networks (one leftover from
  a force-killed resume during the BUG-2 investigation was cleaned).
- **Temp DBs:** the benchmark's `fwbench_*` results DB was dropped; 0 remain.
- **Secrets:** all `*password*`/token/secret values in manifests/reports are `***REDACTED***`; the
  handoff carries no password; plaintext only in run-private `fw.properties` (JDBC necessity, flagged
  by cleanup); docs contain no real secret.
- **Duplicates (then-current K=1 schema):** results_v2 288/288 distinct
  `(run_id,candidate_id,attempt)`; legacy 288. Current schema migration replaces that DB key with
  the five-column repeat-aware sample key described in the errata above.
- **Git:** no commits made; no worktree reset; `git diff --check` clean in all five trunks.
- **Forbidden paths:** nothing matching `*ai-assist*` was read.
- **Scale:** no unapproved 1M/10M/100M/1B run; canonical multi-million fixtures source-confirmed only.

## Release recommendation rationale

The end-to-end secure path was functional, observable, fail-closed, and reproducible at bounded
scale; the two release-blockers were fixed and verified. **READY WITH LIMITATIONS** was therefore
the dated recommendation for a controlled expert release. The initial follow-up list named BUG-4,
Java secure E2E, fintech/multi-instance coverage, and 1M+ stage benchmarks; later addenda in this
same report record BUG-4 fixed, Java secure E2E, fintech verification, and a measured 1M Core stage.
Current remaining limitations are the ones in “Unresolved / open issues” plus features that postdate
this gate; do not reuse the initial follow-up list as today's release checklist.
