# 14 — Scenario Catalog

> **Evidence status (2026-07-21):** rows labelled as full runs preserve dated run evidence; this
> documentation audit did not reproduce every historical scenario. Current code/tests, known
> limitations, and the verified SUT resolver are recorded in the
> [current code audit](CURRENT_CODE_AUDIT_2026-07-21.md).

This human-readable catalog lists the discovered scenario/use-case families, their status, safe
commands, and evidence locations. Run-specific machine evidence is produced inside run directories;
no repository-level evidence JSON is committed. More than 70 TOML specs are present across the
workspace, including the Java and application-direction examples.

> **Application-direction demos (2026-06-11)** — bounded, verified pulls in the Tier-2/Tier-3
> directions: `usecases/perf_opt` (Pareto), `usecases/etl_pipeline`, `usecases/ml_eval` +
> `usecases/ml_eval_surrogate` (two real local sklearn surrogates), `usecases/event_order` (saga),
> and `fintech_oot/batches/*` against the local, in-memory `finance_stack` bank simulators. Details:
> `generator_trunk/usecases/README.md`.

**External-scenario operating policy:** do not run a scenario against paid APIs, live financial
systems, or nonlocal LLM endpoints without explicit operator authorization. This is not an automatic
property of the explicitly-selected `trusted-local` profile: that profile runs unsandboxed and may use the host
network. Use an explicit secure profile and allowlist for untrusted or networked candidates.

## Historical full-run evidence

| Family | Spec | Evidence |
|---|---|---|
| Secure pipeline (Combi×Permut×Subsets×Optional×sieve, sandbox, formal Analyzer) | `tryout_own/spec/secure_pipeline.toml` | flagship: 96→72→288, 150 PASS/138 DOMAIN_FAIL, container backend, formal Pareto 3 |
| Local trusted compute + exploratory Analyzer | `model_usecases/run/code_variants` | trusted-local: 63 candidates, exploratory front 38 |
| **Java Executor — Janino** (classic Java) | `java_e2e/janino_max` | `--lang java` trusted-local: 48 → 29 PASS/19 DOMAIN_FAIL/0 BROKEN, every combo on Janino, dep-jar via `-dirJars` |
| **Java Executor — ECJ** (records/var/streams/lambdas/switch-`yield`) | `java_e2e/ecj_modern` | `--lang java` trusted-local: 48 → 24 PASS/24 DOMAIN_FAIL/0 BROKEN, every combo on ECJ (Janino 0/48), dep-jar via `-dirJars` |

## Current focused Automation Studio evidence

The companion `automation-scheme-studio` SUT has two checked-in Bundle families under `generator_trunk/scenarios/automation_scheme_studio/`:

| Family | Status on 2026-07-25 | Scope |
|---|---|---|
| Historical exhaustive campaign (`00`–`06`) | Dated completed total retained in its README: 155,712 candidates | flat/ordered/repeated stages, three loop slots, brace joins, and a 370-front feedback-path covering |
| Recursive smoke (`advanced_feedback/00_smoke`) | full chain green: 32 processed, 1 PASS, 31 DOMAIN_FAIL, 0 broken/timeout/infra; formal front 1 | recursive sequence/parallel/repeat/feedback compiler |
| Higher-order operator smoke (`advanced_feedback/01_operator_smoke`) | full chain green: 8 processed, 4 PASS, 4 DOMAIN_FAIL, 0 broken/timeout/infra; formal front 4 | `FW_Group`, `FW_PermutR`, and three nested brace result-table joins |
| Deferred recursive searches (`advanced_feedback/10_*`, `20_*`) | all plans green; intentionally not executed in the authoring session | all 16 SUT stages, nested feedback SCCs, parallel/signed reducers, serial/parallel repetition, third/fourth-order generation |

These are local focused verification results, not repository-level release evidence; run artifacts remain below the operator-selected runs root and are not committed. Use the suite launcher documented in its README to reproduce them and to create the final common Pareto report.

## Flagship — executed ladder (2026-07-31)

Full chain green at every rung; every count reconciled stage by stage against an in-process twin
(see [35_FLAGSHIP_DECISION_AND_BASELINES.md](35_FLAGSHIP_DECISION_AND_BASELINES.md) §6).

| Level | Spec | Executed |
|---|---|---|
| L1 | `engine_demo/direct_engine_smoke` | 8 candidates, 6 PASS / 2 DOMAIN_FAIL, 27.8 s |
| L2 | `flagship/bundle_native_l2` | 128 mandatory ×2 optional = 256, ×3 SUT versions; 0 false positives, 128 and 120 detections; 47.4 s per version |
| S2 | `flagship/bundle_native_s2` | **second SUT** (transactional store): 128 mandatory ×2 = 256, ×3 versions; 0 false positives, 128 `index_incoherent` and 32 `rollback_leaked` detections; 51–57 s per version |
| L3 | `flagship/bundle_native_l3` | 864 − 216 sieved = 648, ×4 optional = 2 592, ×3 versions; 0 false positives, 1 792 and 336 detections; 247.9 s per version |
| L4 | `flagship/bundle_native_l4` | 2 592 − 648 sieved = 1 944, ×4 = 7 776; 683.3 s — **over** the declared 600 s gate budget, which is where the ladder stops |

Five nested brace links per level with `FW_()` in both operand positions, plus `FW_Group`,
`FW_PermutR`, `FW_Optional`, `FW_Exclude` and a constraint sieve that removed only candidates the
domain cannot construct.

## Plan evidence only (a plan is not an executed scenario)

| Family | Spec | Plan |
|---|---|---|
| Pricing / optimization red-team | `tryout_own/pricing` | mandatory 144, optional ×2, final 288 (class S); needs `PRICING_URL` SUT |
| API probe | `api_probe/spec` | 576 EXACT (class B); needs a local probe target |
| Superoptimization (self-contained) | `model_usecases/run/superopt` | 924 EXACT (class B) — runnable trusted-local |
| QA checkout / testgen | `qa_checkout/spec`, `qa_testgen/spec` | 96 / 216 EXACT |
| Brace / group second-order | `brace_demo`, `group_sep_demo` | UNKNOWN cardinality (correct, class X) |
| Recursive control architecture search | `scenarios/automation_scheme_studio/advanced_feedback/{10_third_order_brace,20_grouped_repetition}` | UNKNOWN/class X by design: later joins consume generated result tables; both plans validated 2026-07-25 |

## Verified by targeted test (mechanism proven without a full bounded run)

| Family | Test |
|---|---|
| Sharded Reader sink | `Executor_trunk/test_shard_reader.py` (byte-for-byte vs loose, count-mismatch guard) |
| Worker pool / determinism / retry | `Executor_trunk/test_worker_pool.py` (1==N, crash-resume) |
| Backpressure | `Executor_trunk/test_backpressure.py` (producer waits) |
| Outcome classes | `Executor_trunk/test_py_executor_outcomes.py` (9 tests) |
| Results DB schema / idempotency / policy | `Executor_trunk/test_results_v2_{schema,idempotency,policy}.py` |
| Java compiler routing (Janino/ECJ/adaptive) + dep-jar | `test_java_e2e_specs.py`, `test_bundle_java_routing.py` (Java path is now **runnable-verified**, above) |
| Aliases / graph | `test_fwgen_aliases.py`, `test_fwseq_graph.py` |
| Handoff legacy↔v2 | `test_bundle_handoff.py` |
| Telemetry catalog constraints + standalone HTTP SUT | `test_telemetry_catalog_e2e.py`, `test_telemetry_catalog_full_e2e.py` (576 optional + 729 sentinel forms exhaustively sent to the local service; embedded-valid subsets all accepted) |
| Cancel / cleanup / deploy / doctor / budgets / resources / config / provenance | `test_bundle_*.py` |

## Service- or environment-gated scenarios

| Family | Current status | Prerequisite |
|---|---|---|
| Fintech/OOT batches | Local simulator only. The 2026-06-11 Bundle counts are dated; the current audit passed all 56 SUT tests but found intentionally permissive/non-production transaction semantics. | `bash fintech_oot/up_instances.sh` then provide an operator-managed `OOT_SECRET` and run `bundle_run.py fintech_oot/batches/<batch>` |
| Multi-instance orchestration | `run_4instance_bundle.py` depends on the same local services | see above |
| External/LLM/cybersec/k8s/RAG/tinyML | `specs/*` + `llm_loop/*` target real WAF/k8s/live or nonlocal LLM/paid APIs | local mock/surrogate per each spec's `note` + explicit operator opt-in; never spend money or send data externally |

## Safe bounded invocation pattern

```bash
export BUNDLE_MAIN_DB_PASSWORD=$PGPW BUNDLE_RESULTS_DB_PASSWORD=$PGPW
python3 bundle_run.py plan <spec-dir> --out /tmp/plan        # 1) quantify (no DB)
# 2a) self-contained, reviewed code only -> trusted-local (unsandboxed):
python3 bundle_run.py <spec-dir> --db <name> --execution-policy-profile trusted-local \
  --candidate-origin reviewed-checked-in \
  --acknowledge-trusted-local "reviewed checked-in candidate fragments" \
  --analyzer "<k:dir,...>" --analysis-mode exploratory --run-id <id>
# 2b) HTTP SUT or untrusted candidate -> use an explicit secure profile (see doc 15)
```

For large scenario families, run the smallest representative that exercises each **distinct
mechanism** — not every Cartesian member.
