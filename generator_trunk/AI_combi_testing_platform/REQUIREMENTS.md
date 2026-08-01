# Executable requirements and traceability

The issue description was treated as problem input, not authority. Useful
claims were converted to the requirements below; speculative or overly broad
claims were narrowed to evidence the platform can actually establish.

| ID | Requirement | Implementation / verification |
|---|---|---|
| R1 | Generate an immutable canonical task before any wording and keep task identity separate from rendering identity. | `task_ir/model.py`; deterministic/hash tests |
| R2 | Compute truth with a deterministic solver that is independent of the adapter and unavailable to the renderer. | `oracles/exact.py`; renderer signature test |
| R3 | Parse output strictly and verify exact answer, schema, entity membership, and every declared constraint. | `verify_response`; oracle tests |
| R4 | Preserve stable task, renderer, adapter/model, prompt version, environment, seed, and structural provenance. | `MetricRecord`; metrics parser tests |
| R5 | Distinguish invalid format/wrong answer from provider or runtime failure. | codes 4/5; adapter infrastructure exceptions propagate to Executor outcomes |
| R6 | Exercise real first-order, repeated, grouped, brace, nested `FW_()`, and grouped `FW_()G` result-table composition. | nine scenario TOMLs; strict parse/operator tests; measured order 4 / depth 5 / 52 nodes / 34 atoms |
| R7 | Exclude intermediate operands from independent final multiplication. | `FW_Exclude`; regression tests; measured operator count 8 |
| R8 | Plan every run, guard unknown/extreme spaces, shard candidates, and never imply authorization for external spend. | `run_campaign.py`; external gates; all-spec plans |
| R9 | Emit exactly one finite, Analyzer-compatible metrics line per domain-verdict candidate. | `metrics/record.py`; engine tests; full-chain metrics reconciliation |
| R10 | Make formal correctness an eligibility gate before multi-objective comparison. | `FW_VAR`; explicit formal goals; Analyzer provenance |
| R11 | Share one engine across router, prompt-CI, and verified-dataset modes. | `CandidatePlan.product_mode`, reporting, `VerifiedDataset` |
| R12 | Export only exact-PASS, deduplicated pairs with license/privacy/source metadata. | `dataset.py`; export tests |
| R13 | Default to cost-free controls and label them as non-models. | local adapters; report claim withholding |
| R14 | Require explicit config, environment credential, authorization, and budgets for external calls. | external adapter + launcher gates |
| R15 | Launch immutable safe profiles from Face 1 Old and Face 1 New. | shared catalog/profile; both-backend tests |
| R16 | Accept a run only after Core mandatory materialization and the Reader-declared optional runtime expansion, Executor, persistence, metrics, formal eligibility, run IDs, and provenance reconcile; never equate `fw_final` directly with assembled candidates when `FW_Optional` is active. | `reporting.reconcile_run`; optional-expansion regression; full-chain smoke |
| R17 | Generate a fresh ordinary-task difficulty ladder, retain only a seed commitment, and cross-check planted answers with an independently implemented runtime oracle. | `sub_suites/release_gate_breakpoint/task_factory.py`, `runtime.py`; oracle/property tests |
| R18 | Keep provider/model/effort cells, doubling difficulty levels, breakpoint signatures, session wording, counts, and filenames configurable rather than provider- or date-specific. | `config.py`, `config.example.json`, collision-resistant cell filenames; config/exchange tests |
| R19 | Use Bundle combinatorics as the construction instrument: nine binary factors, `FW_Permut`, `FW_Group`, four real nested result-table levels, and four independent `FW_Optional` atoms produce 512 candidates per task. | generated scenario; strict parser/cardinality and all-512-plan tests |
| R20 | Export bounded prompt/response exchanges with immutable hashes, exact identities, complete bodies, selected assembled candidates, a strength-two follow-up design, and separate strict/extracted-semantic scoring. | `exchange.py`, `bootstrap.py`; package/bootstrap tests |
| R21 | Run generated controls network-disabled, reject host Python preprocessing under secure policies, remove provider credentials from the constructor process, and make exact ephemeral-database cleanup mandatory. | `runner.py`, `Executor_trunk/py_executor.py`; command, cleanup-boundary, and Executor tests |
| R22 | Expose the fresh release-gate apparatus in Face 1 Old and New without freezing held-out tasks or inheriting workbook/network controls; reject unknown materializers, unsafe profiles, invalid ladders, and out-of-repository sources. | shared dynamic catalog materializer and immutable profile; both-backend launch, freshness, environment, and fail-closed catalog tests |

## Corrected source claims

- Newly generated data is not guaranteed uncontaminated; report it as fresh,
  seeded, structurally hashed evaluation with held-out generators where used.
- Familiar terms may interfere with abstraction, but a particular internal
  neural mechanism cannot be inferred from output errors alone.
- A strong model response is not automatically an ideal training label. It
  becomes an admitted pair only after independent exact verification and still
  retains source/model provenance.
- Pairwise testing does not have a universal “90% bug” guarantee.
- Dynamic routing thresholds are empirical policies tied to a task
  distribution, quality floor, model versions, prices, and environment—not
  universal complexity laws.
- Safety evaluation needs specialized threat models and policies; excessive
  constraints alone do not constitute a complete red-team program.
- A doubling ladder of checks and construction states defines an exponential structural
  contrast scale; it does not prove that cognitive difficulty doubles.
- A generated exchange is apparatus evidence until actual target responses are
  acquired, identity-checked, and scored by the packaged oracle.
