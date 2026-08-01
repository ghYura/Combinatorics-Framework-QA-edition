# 22 - Plan-1 / Plan-2 QA Readiness and Verification Contract

> **Historical review artifact.** This file records the 2026-06-19 pre-implementation acceptance
> criteria; it is not the current feature-status ledger. Repeat execution, five-column sample
> identity, aggregation, and control-plane seams subsequently landed. Use
> [document 21](21_ARCHITECTURE_DECISIONS.md) and the
> [2026-07-21 code audit](CURRENT_CODE_AUDIT_2026-07-21.md) for present behavior and boundaries.

**Status at publication:** review notes for planned work; no Plan-1 or Plan-2 implementation was
claimed at that time.
**Reviewer:** Automation GPT-5, acting as independent Senior QA.
**Source status:** the historical combined Plan-1/Plan-2 plan reviewed in 2026-06-19 is not
included in this publishable tree. This document preserves its QA acceptance contract; the
repository-local contract delta and implemented control-plane baseline are
[document 24](24_PLAN1_PHASE0_CONTRACT_DELTA.md) and
[document 25](25_PLAN2_CONTROL_PLANE_ADR_AND_BASELINE.md).

## Material reviewed on 2026-06-19

- Claude handoffs `06_40Z`, `07_17Z`, `07_30Z`, `07_39Z`, and `08_00Z`.
- The complete historical combined plan (Plan-1 repeat policy and Plan-2 Java 21/Loom runtime
  control plane). That source artifact is unavailable in this publishable tree; its reviewed
  acceptance requirements are retained below.
- `testme5upgraded/TERNARY_FLOAT_VARIANTS_REPORT.md`, as the experiment that motivated repeated
  performance measurements. Its kernel work is complete and is not part of this refactor.
- Existing documentation index, architecture decisions, developer guide, and release report.
- A path-level inventory of first-party Python/Java tests and the separately vendored Janino tests.

## Independent assessment

Plan-1 addresses a real correctness defect in experimental interpretation: a single noisy timing
sample must not determine a Pareto winner. It should be implemented before Plan-2. Plan-2 can make
large distributed runs easier to reason about, but it is an orchestration and operability change,
not a CPU-speed feature. Its value must be demonstrated by parity, cancellation, bounded resource
use, and scale tests.

The following points are mandatory design decisions or QA gates, not optional polish:

1. **Keep retry identity separate from experiment identity.** Existing documentation describes
   result identity using `run_id`, `candidate_id`, and `attempt`. `repeat_idx` is an intentional
   sample; `attempt` is a retry/recovery fact. Do not replace or conflate them. Trace the actual DDL
   and upsert before choosing the additive composite key, and preserve run isolation.
2. **Define K=1 compatibility precisely.** "Byte-identical" is too broad if a schema or manifest
   gains optional fields. Name the artifacts that must remain byte-identical; otherwise require
   behavioral and result equivalence with absent/default repeat metadata. Existing consumers must
   still parse old and new contracts.
3. **Budget formulas depend on scope and topology.** `candidates * K` is insufficient for `nested`
   (`candidates * executors * K`) and may overstate deterministic work under
   `repeatScope=metrics`. Planning, timeout, progress, and expected-row formulas must share one
   tested execution-count model.
4. **Metric repeats need a measurement protocol.** Specify warm-up, ordering/interleaving, timeout,
   process reuse, state reset, host identity, and resource isolation. Otherwise repeated numbers
   are precise-looking but biased. `repeatScope=metrics` must not silently bypass the sandbox or
   invoke a different oracle path.
5. **Median and Welford answer different questions.** Welford supplies mean/variance, not a valid CI
   for a median. Select and document a statistical method suitable for K and the distribution
   (for example, bootstrap/order-statistic CI for a median, or a mean CI only when assumptions are
   defensible). Define behavior for K=1 and very small K.
6. **CI overlap is not an equivalence relation.** Pairwise overlap can be non-transitive, so a
   "noise-tied tier" needs a deterministic algorithm and tests for A-overlaps-B, B-overlaps-C,
   A-not-overlap-C. Multi-objective and multiple-comparison behavior must also be explicit.
7. **Assignment must survive retries and worker loss.** Define ownership, leases/timeouts,
   duplicate late results, executor replacement, and resume behavior for local/disperse/nested.
   At-least-once dispatch plus an exact idempotency key is safer than assuming exactly-once delivery.
8. **Plan-2 changes documented architecture.** ADR-1 says Generator owns the Python control plane;
   ADR-2 says components communicate through files/manifests; ADR-7 deferred remote orchestration.
   Before implementation, add an ADR defining the retained Python planning plane, the Java runtime
   control-plane boundary, and its versioned plan/result protocol.
9. **Java 21 preview choice is explicit.** Virtual threads are final in Java 21, but
   `StructuredTaskScope` is preview in Java 21. Either accept and consistently configure
   `--enable-preview` for compile/run/package/tests, or use stable virtual-thread APIs. No hidden
   preview dependency is acceptable.
10. **JDBC verification must use the packaged runtime.** POMs currently show differing pgjdbc
    versions across trunks and, in places, two PostgreSQL drivers. Record the actual shaded/runtime
    driver, connection pool, and JFR pinning result. A source-level version check is insufficient.
11. **Cancellation is end-to-end.** Cancelling a scope must stop polling, prevent new dispatch,
    terminate or quarantine in-flight candidate work, close JDBC resources, and leave resumable
    state. A cancelled future alone is not proof.
12. **Performance claims require a baseline.** Compare the current path and Loom path at equal
    candidate/repeat/executor counts. Report throughput, latency, DB connections, platform/carrier
    threads, CPU, memory, and cancellation time. Do not attribute I/O coordination gains merely to
    "no GIL".

## Test estate and ownership

The next QA cold start must read every first-party test before judging coverage.

| Layer | First-party test sources to inventory and read | Important limitation |
|---|---|---|
| Generator/control plane | `generator_trunk/test_*.py`, `testgen_*.py`, and first-party nested `test_*.py` | Includes lifecycle, budgets, contracts, Java routing, E2E specs, provenance, and use-case-specific tests |
| Core | POM/build plus canonical truth fixtures and Core integration callers | No conventional first-party unit-test suite was identified by the path inventory; this is a coverage gap to verify |
| Reader | first-party `*Test.java` / `*SmokeTest.java` under `Reader_trunk/src/main/java` | Classes under `src/main` are not automatically covered by ordinary Maven test discovery |
| Executor Python | root `Executor_trunk/test_*.py` | Some results tests are PostgreSQL-gated and must fail closed when prerequisites are absent |
| Executor Java | first-party `*Test.java` / `*SmokeTest.java` under `Executor_trunk/src/main/java` | Confirm and invoke their `main`/driver entrypoints; `mvn package` alone is not proof they ran |
| Analyzer | `Analyzer_trunk/run-tests.sh`, `AllVerifiersRunner`, and every verifier it invokes | Canonical suite is the script, not `mvn test`, because of the offline plugin state |
| Embedded compiler | vendored `Executor_trunk/janino-master/**/src/test/**` | Separate upstream compatibility suite; run when compiler integration/dependency changes, not as a substitute for Bundle tests |
| End-to-end | launcher tests, Java E2E specs, flagship flow, results/Analyzer gates, and repeat-policy dogfood | Must validate persisted rows and evidence, not only process exit status |

## White-box review checklist

For every implementation increment, Automation verifies:

- requirement-to-symbol trace and an intentionally bounded diff;
- old/new schema readers, writers, migrations, unique keys, and transaction boundaries;
- candidate/repeat/attempt/env identity through plan, handoff, Executor, database, and Analyzer;
- expected/emitted/processed/persisted/ingested count equations for every policy and scope;
- cache behavior, retries, resume, duplicate/late delivery, cancellation, and partial failure;
- concurrency ownership, backpressure, connection limits, host-level performance serialization,
  thread interruption, and resource cleanup;
- deterministic assignment under a recorded seed and balanced environment exposure;
- statistical aggregation and Pareto/tie behavior on adversarial synthetic data;
- fail-closed security behavior, sandbox continuity, secret redaction, and path handling;
- Python/Java contract parity and backward compatibility;
- logs, manifests, evidence, and operator diagnostics sufficient to explain a result.

## Verification sequence for each Claude implementation step

1. Freeze the stated scope and inspect all changed files; unrelated changes are left intact.
2. Perform static/white-box tracing before running tests. Report design blockers first.
3. Run new and directly affected tests, including negative and failure-injection cases.
4. Run the complete owning-component suite, not only the newly added test.
5. Run adjacent contract suites whenever a schema/property/manifest crosses components.
6. Run a bounded end-to-end scenario and reconcile counts and persisted identities.
7. Re-run the established regression/release gates appropriate to the blast radius.
8. Issue `ACCEPT`, `ACCEPT WITH EXPLICIT LIMITATION`, or `REJECT`, with commands and evidence.

Claude should not begin the next implementation step until the current step has a QA verdict, unless
Yuri explicitly changes that coordination rule.

## Planned phase order

1. Plan-1 Phase 0: trace actual mechanics and publish a design/contract delta.
2. Plan-1 configuration, validation, unified execution-count model, and K=1 compatibility.
3. Additive results identity/schema migration mirrored in Python and Java.
4. Local repeat execution plus cache/scope semantics.
5. Analyzer aggregation and statistically defined tie handling.
6. Disperse and nested scheduling, failure recovery, and host isolation.
7. Bundle dogfood with deterministic and noisy metrics.
8. Plan-2 ADR/protocol and current-path baseline.
9. Plan-2 runtime control plane, parity/cancel/backpressure tests, then scale/JFR evidence.

Plan-2 must not destabilize Plan-1's public contracts. If Plan-1 cannot pass its own dogfood gates,
Plan-2 remains blocked.
