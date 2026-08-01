# 31 — Engine-first evidence (current)

Current, regenerable evidence for the engine-first boundary
([30_ENGINE_FIRST_ARCHITECTURE.md](30_ENGINE_FIRST_ARCHITECTURE.md)). The numerical summaries below
were transcribed from the machine-readable reports produced by the commands shown; this explanatory
Markdown is necessarily hand-authored. Dated measurements from 2026-06-11 / 2026-07-21
remain in [13_BENCHMARKS_AND_SCALE_CLAIMS.md](13_BENCHMARKS_AND_SCALE_CLAIMS.md) and
[18_VERIFICATION_AND_RELEASE_REPORT.md](18_VERIFICATION_AND_RELEASE_REPORT.md) and are **not**
restated as current.

The generated reports themselves are runtime artifacts. They belong in `/tmp` or a CI artifact
store and are deliberately not committed; this document records the summary and how to regenerate
the full JSON.

### Post-Phase-01 review correction (2026-07-31)

An independent review after the original Phase 01 run found and fixed four defects in its evidence
machinery: the CLI architecture report omitted reference-application-originating edges even though
pytest checked them; `engine_revision` omitted the Java-heavy engine implementation; the policy
scanner mistook `argparse`/optional budget controls for pinned runtime policy; and wrapper benchmarks
used fixed application DB/run IDs that were not safely isolated/registered for cleanup. Regression tests now pin all
four corrections. The full-chain counts and the single-run timing observations below were not
changed; future timing regeneration uses unique temporary DB names/run IDs and cleans both clusters.

## Measurement environment (2026-07-31)

| | |
|---|---|
| Host | 8 CPU, 31 GiB RAM, Linux 7.0.0-28-generic x86_64 |
| Python | 3.12.3 |
| Java | 25.0.3 LTS (Temurin) |
| PostgreSQL | 18.4 (host clusters: main `:5433`, results `:5432`) |
| Evidence grade | single-host, single-run, bounded. Order-of-magnitude for this hardware — not an SLA, not a throughput claim. |

## 1. Dependency-direction gate

```bash
python generator_trunk/bundle_run.py architecture --json /tmp/architecture.json
```

- 6 declared layers; **0** unclassified repository trees.
- **0** dependency-direction violations across engine, presentation and reference-application
  layers.
- 131 repository-internal Python import edges originate in the engine implementation layers; every one resolves to
  `engine-core` or `engine-control-plane`. No engine module reaches a reference application.
- The architecture report audits all 5 non-test product layers (310 resolved internal Python edges
  at this checkout), rather than relying on a broader pytest-only check.
- `engine_revision` covers 444 implementation/configuration files at this checkout, including 310
  Java and 64 Python files; generated output, test-layer files and `engine-demo` are excluded.
- Exactly **1** reviewed cross-layer exception: `intake/scenario_library.py` (presentation)
  materializing the AI release-gate sub-suite's dynamic spec. It is a lazy import inside a function
  body — detected because the gate parses with `ast`, which a top-of-file grep would have missed.

## 2. The engine runs without the reference layer

`generator_trunk/test_bundle_architecture.py` executes the control plane in a subprocess where
both `AI_combi_testing_platform` and `generator_trunk.AI_combi_testing_platform` imports raise, and
asserts:

- the control plane (`bundle.cli`, `stages`, `coverage`, `architecture`) imports;
- `bundle plan` on the direct engine scenario succeeds and reports its three brace rows;
- the plan's final cardinality mode is `UNKNOWN` — the honest answer for a brace chain, not a
  fabricated exact count.

A guard test confirms the import blocker really blocks, so those two cannot pass for the wrong
reason.

## 3. Direct engine smoke — full-chain reconciliation

```bash
python generator_trunk/engine_demo/run_direct_engine_smoke.py run
```

| Stage | Count | Invariants |
|---|---:|---|
| Core `fw_final` | 8 | `core.count_positive` ✓ |
| Reader emitted | 8 (expected 8, empty 0) | `reader.emitted_eq_expected`, `reader.empty_zero`, `handoff.run_id_matches`, `handoff.candidate_count_matches` ✓ |
| Executor processed | 8 = 6 PASS + 2 DOMAIN_FAIL + 0 BROKEN + 0 TIMEOUT + 0 INFRA_FAIL | `executor.processed_eq_sum`, `executor.broken_zero`, `executor.timeout_zero`, `executor.infra_fail_zero` ✓ |
| Persisted | 8 legacy + 8 `results_v2` (0 already-present) | `results_v2.attempted_matches_processed`, `results_db.count_eq_inserted` ✓ |
| Analyzer corpus | 8 metrics lines | `analyzer.input_matches_metrics` ✓ |
| Formal Analyzer | 6 eligible, 3 non-dominated, `provenance_ok=true`, 0 issues | goals `stages:max, retained:max, ops:min` |

Both DOMAIN_FAILs carry the stable reason `not_non_decreasing` and are attributable to stage
**order** (`sort` then `scale(k=-1)`), under both grouped modules. Neither grouped module can
violate the contract alone — both are monotone — so the failure is a genuine composition
interaction, which is what the demonstration exists to show. The offline enumeration in
`test_engine_demo.py` predicts 8/6/2 independently of the database, and the run matched it.

## 4. Reference-capability coverage targets

```bash
python generator_trunk/bundle_run.py coverage --json /tmp/reference-coverage.json
```

19 engine capabilities are registered (12 first-order, 5 second-order, 2 third-order-and-beyond),
cross-checked against the `fwgen` grammar the Core is verified against: every `FW_` name the grammar
recognizes is owned by exactly one capability, and every capability's probe token is accepted by the
real parser.

| Target | Architectural role | Status | Specs | Max composition order | Exercised | Unexercised |
|---|---|---|---:|---:|---:|---:|
| `ai-combi` | reference application | experimental | 9 | 5 | 12 | 7 |
| `automation-scheme-studio` | reference application | reference | 11 | 4 | 12 | 7 |
| `engine-demo` | engine demonstration | stable | 1 | 4 | 7 | 12 |

Findings, stated as facts rather than a score:

- **Composition depth is not where the application layer limits the engine.** `ai-combi` reaches
  order 5, deeper than the direct demonstration. The earlier concern that the AI layer "suppresses
  the engine's power" is not supported for depth.
- **Breadth is where coverage stops.** No registered target exercises `operator.separator`,
  `operator.subsets`, `flag.reuse_table_only`, `flag.heading`, `flag.last_in_queue` or
  `flag.concatenator`. These are engine capabilities with no current reference usage — an evidence
  gap, not a defect.
- **`engine-demo` deliberately exercises 7 of 19.** It is the *minimal* proof of higher-order
  composition, not a capability showcase.
- **Launchers pin real policy.** Both reference applications and the direct demonstration use
  `--execution-policy-profile trusted-local`, `--candidate-origin reviewed-checked-in`,
  `--acknowledge-trusted-local <reason>`,
  and `--analysis-mode formal` on executable paths.
  Conditional flags are marked conditional in JSON rather than presented as universal;
  `argparse` declarations and optionally forwarded caller budgets are not pinned-policy findings.
  `automation-scheme-studio` additionally passes
  `--unleash-initial-productivity-power`, which makes hard budget gates advisory — recorded here
  because it is a policy choice a reader should see, with its source line in the JSON.

## 5. Application overhead around an identical canonical run

```bash
python generator_trunk/bundle_run.py bench --profile 100 \
  --stages 'reference_overhead[engine-demo],reference_overhead[ai-combi],reference_overhead[automation-scheme-studio]' \
  --scratch /tmp/refovh --out /tmp/refovh/bench.json
```

For `engine-demo` and `ai-combi`, the stage runs the **same** scenario, policy, candidate count and
oracle twice — directly through `bundle_run.py`, then through the target's launcher. The automation
target has no single-scenario launcher leg, so only its direct engine leg is measured and no wrapper
difference is claimed. Wall seconds from the original single run:

| Phase | `engine-demo` (8 cand.) | `ai-combi` 00_smoke (32 cand.) | `automation-scheme-studio` operator smoke (8 cand.) |
|---|---:|---:|---:|
| `bundle_plan` | 0.453 | 0.449 | 0.440 |
| `engine.gen` | 0.456 | 0.454 | 0.562 |
| `engine.core` | 9.350 | 9.166 | 9.286 |
| `engine.reader` | 14.240 | 14.231 | 14.336 |
| `engine.executor` | 1.267 | 5.571 | 6.301 |
| `engine.analyzer` | 0.688 | 0.875 | 1.263 |
| `bundle_cli_overhead` | 1.549 | 1.649 | 1.578 |
| `bundle_direct_total` | 27.550 | 31.947 | 33.325 |
| **`application_overhead`** | **0.488** | **0.583** | not measured¹ |
| `application_total` | 28.039 | 32.530 | — |

¹ Its campaign launcher runs the whole advanced suite rather than one scenario, so there is no
single-scenario wrapper leg to time. The engine leg is reported alone and the report records that
reason.

Interpretation, with the cautions that make these numbers usable:

- **The wrapper was small in this one observation.** ~0.5 s against a ~28–32 s run: under 2% on
  this host/run. It does not justify a general no-overhead claim; repeats and uncertainty bounds
  would be needed for that. It does show no order-of-magnitude wrapper cost in this bounded case.
- **`engine.core` and `engine.reader` are near-constant across 8 and 32 candidates.** At this size
  they are dominated by JVM start and PostgreSQL setup, so they are *fixed costs*, not per-candidate
  costs. Dividing them by candidate count would produce a meaningless throughput figure. For
  per-stage scaling behaviour use the dedicated profiles in
  [13_BENCHMARKS_AND_SCALE_CLAIMS.md](13_BENCHMARKS_AND_SCALE_CLAIMS.md).
- **`engine.executor` is the only phase that tracks candidate count and oracle cost** here
  (1.3 s / 8 candidates vs 5.6 s / 32).
- `application_overhead` aggregates the wrapper's preparation and post-processing. Separating them
  requires instrumenting the wrapper; an invented split is not reported.

## 6. Focused test results

```bash
python -m pytest -q generator_trunk/test_bundle_architecture.py \
                   generator_trunk/test_bundle_coverage.py \
                   generator_trunk/test_bundle_benchmark.py \
                   generator_trunk/engine_demo/test_engine_demo.py
```

| Suite | Tests | Result |
|---|---:|---|
| `test_bundle_architecture.py` | 24 | pass |
| `test_bundle_coverage.py` | 33 | pass |
| `test_bundle_benchmark.py` | 18 | 17 pass, 1 expected infrastructure skip |
| `engine_demo/test_engine_demo.py` | 21 | pass |

No skips. The oracle-non-vacuity test seeds a defect into one evaluator and requires the independent
one to catch it, so a passing differential check is evidence rather than a tautology.

### Original Phase 01 regression check

These broader results are from the original Phase 01 run. The post-review correction reran the
95-pass/1-skip focused set above; it did not silently relabel the broader historical totals as a
fresh run.

| Scope | Tests | Result |
|---|---:|---|
| Control-plane suite (doctor, counts, fwgen, policy, config, benchmark, inventory, hygiene, handoff, runmodel, seq graph) | 222 | pass, 1 skip |
| Reference applications (`AI_combi_testing_platform/tests`, both Face 1 AI/GUI integrations, scenario library, automation advanced feedback) | 71 | pass |

The single skip is `test_bundle_benchmark.py::…` — "Analyzer build not present" — an expected
optional skip: the Analyzer driver classes are built lazily on first `--analyzer` run.

The AI reference application's local deterministic smoke also ran for real as the wrapper leg of the
overhead measurement in §5 (`run_campaign.py run --scenario 00_smoke`, exit 0).

**Pre-existing finding (not introduced here, carried to the release-pipeline phase):**
`scenarios/automation_scheme_studio/advanced_feedback/test_advanced_feedback.py` imports
`automation_constructor` at module scope, so a plain `pytest` collection of that path *errors*
rather than skipping when the sibling SUT checkout is absent. It needs
`PYTHONPATH=$BUNDLE_SUT_ROOT/automation-scheme-studio/src`. A missing optional SUT should produce a
classified skip, not a collection error.

## 7. Execution-safety remediation (Phase 02, 2026-07-31)

The six findings audited in [32_EXECUTION_SAFETY_AUDIT.md](32_EXECUTION_SAFETY_AUDIT.md) were
implemented in the same session. Behaviour verified live on this host, not only in unit tests:

**No implicit trust (F1).** `BundleConfig.execution_policy_profile` is now `""`. A run with no
policy is refused with an actionable message naming both the secure and the reviewed path; `bundle
plan` is unaffected. `trusted-local` additionally requires `--candidate-origin` and
`--acknowledge-trusted-local`, and origins `generated` / `imported-untrusted` / `network-facing`
are refused it outright — an acknowledgement records a decision, it cannot grant a permission.

**Recorded and re-verified (F3).** A live `event_order` run wrote into `run.json`:

```json
{"profile": "trusted-local", "origin": "reviewed-checked-in",
 "acknowledgement": "reviewed checked-in usecase scenario",
 "sandboxed": false, "policy_id": "ep-754535fb074d", "policy_hash": "754535fb…"}
```

A no-op resume of the direct engine smoke printed `⚠ resuming under 'trusted-local'` and reused all
five stages. The same run resumed with `--execution-policy-profile generated-default` was **refused**:

```text
✗ resume would change the execution policy: the run was authorized as 'trusted-local'
  (policy ep-754535fb074d) and this invocation resolves to 'generated-default'
  (policy ep-84ca788101bd). Resume continues an existing decision; start a new run to change it.
```

**One optional-table contract (F4).** The plan now prints and records it, and the run reconciles
against it:

```text
optional table contract: 2 FW_Optional sheet(s), Core produces [1,2],
  Reader consumes [1,2] (complete) -> ×4 per fw_final row
```

Core `fw_final` 6 × 4 = 24 = Reader = Executor = persisted = Analyzer corpus, identical to the
pre-change baseline. The core stage additionally records `optional_multiplier=4` and verifies
`fw_opt1`/`fw_opt2` exist before the Reader starts. All four standalone property templates were
reconciled to satisfy `R ⊆ P` and labelled as development profiles.

**Loopback-only candidate gRPC (F5).** The receiver binds an explicit address and refuses wildcard
or non-loopback values in the JVM itself, so a standalone `MainWatch` cannot bypass the launcher.
`test_bundle_grpc_bind.py` starts the real receiver and asserts the listening socket is reachable on
`127.0.0.1` and **not** on this host's routable address.

**Direct engine smoke, unchanged under the new gates:** 8 generated, 8 emitted, 8 executed
(6 PASS + 2 DOMAIN_FAIL + 0 BROKEN/TIMEOUT/INFRA_FAIL), formal front 3, `provenance_ok`.

### Secret and artifact scan

No credential literals, machine-specific `/home/...` paths, browser-profile references, or cookie
paths in tracked source. `git diff --check` clean; no runtime artifacts in the working tree.
Reported separately, as the audit requires: ignored runtime output exists on disk under `/tmp/fw_work`
(1.2M), `/tmp/refovh` (568K) and `/tmp/refovh-all` (1.9M) — evidence, not source.

The `secret="wrong-secret"` occurrences in `generator_trunk/fintech_oot/batches/*.toml` are
deliberate negative-test fixtures asserting rejection, not credentials.

## What this evidence does not establish

- Nothing here is a throughput, scale, or SLA claim.
- Capability coverage is measured over **registered coverage targets** only; other
  `usecases/` and `llm_*` trees are not yet registered and are not counted.
- The overhead comparison is one bounded scenario per application on one host, single run. It does
  not characterize behaviour at larger candidate counts, where the fixed costs above stop dominating.
- A capability marked `UNEXERCISED` means no registered application uses it. It is not evidence that
  the capability works, nor that it is broken; it marks where reference coverage is missing.
- The execution-safety work restricts *interfaces and defaults*. It does not make the candidate gRPC
  channel secure (no TLS, no peer identity), and it does not establish multi-tenant readiness. The
  origin classification is the operator's assertion: the gate records who decided that code was
  reviewed, not that it actually was.
