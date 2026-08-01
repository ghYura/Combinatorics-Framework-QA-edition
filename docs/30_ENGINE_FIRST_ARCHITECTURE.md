# 30 — Engine-first architecture

> **Bundle is an executable combinatorial design-space and evidence engine. AI response testing is a
> reference application.**

That sentence is the product decision this document makes enforceable. It is not a repositioning of
existing prose: the boundary is declared as data in
[`generator_trunk/bundle/architecture.py`](../generator_trunk/bundle/architecture.py), checked by
`bundle_run.py architecture`, and gated by `generator_trunk/test_bundle_architecture.py`.

## 1. Why this document exists

The `AI_combi_testing_platform` derivative is a genuine proof of concept and it produced real
evidence. It is not, and must not become, the definition of the Bundle. Two failure modes follow
from confusing them:

- a reader who meets the AI platform first concludes the Bundle is an LLM-testing tool that happens
  to use combinatorics, rather than a domain-neutral engine one of whose applications tests LLMs;
- an application's own policy choices (a pinned execution profile, a budget ceiling, a language, a
  rendering constraint) get read as engine limits.

The remedy is not a directory reshuffle. It is an enforced dependency direction, a direct engine
path that owes nothing to any application, and a machine-readable audit that keeps *engine
capability* and *application coverage* as separate facts.

## 2. Product hierarchy

```text
Bundle Engine (the primary authored technology)
  Core -> optional Sieve -> Reader -> Executor -> Analyzer

Engine control plane (supporting infrastructure, not a domain)
  specification and workbook generation, cardinality planning and budgets,
  run/stage contracts, execution policy, invariants, lifecycle, diagnostics

Replaceable control and presentation
  Face 1 Old / Face 1 New, intake catalogs, wizards, gateways, reference launchers

Reference applications
  AI_combi_testing_platform, domain SUT adapters, scenario libraries

Private/commercial work
  customer data, private oracles and test packs, managed operation, support,
  training, certification, unpublished research
```

## 3. The authoritative engine boundary

| Layer | Trees | Stability | May import |
|---|---|---|---|
| `engine-core` | `Core_trunk/`, `Reader_trunk/`, `Executor_trunk/`, `Analyzer_trunk/`, `Combinatoricslib3parallel/` | stable | `engine-core` |
| `engine-control-plane` | `generator_trunk/bundle/`, published `bundle-*.schema.json` contracts, `constraints/`, `proto/`, `fwgen*.py`, `fwseq_graph.py`, `bundle_run.py`, `bundle_gateway.py`, `sut_paths.py`, `xlsx_autofit.py`, `code_decompose.py` | stable | `engine-core`, `engine-control-plane` |
| `engine-demonstration` | `generator_trunk/engine_demo/`, `flagship/` | stable | engine layers |
| `domain-application` | `generator_trunk/genetics_model_testing/` (declared, not yet created) | experimental | engine layers, `domain-application` — **not** `reference-application`, **not** `engine-demonstration` |
| `presentation` | `generator_trunk/intake/`, `face1_new/`, `landing/`, `invitation_wizard/`, `fwgen_gui.py` | replaceable | engine layers, `presentation` |
| `reference-application` | `generator_trunk/AI_combi_testing_platform/`, `scenarios/`, `usecases/`, `combinatorial_tests/`, `llm_*/`, `model_usecases/`, … | experimental | engine layers, `reference-application` |
| `tests` | colocated Python/Java test names and `test/` / `tests/` trees | stable | any layer |

Classification is by **responsibility and dependency direction**, never by who or what generated the
code. A tree that no layer claims is a gate failure, so new code cannot acquire an undeclared
architectural position by simply existing.

### Allowed direction

```text
reference application  ──▶  documented Bundle entry point / contracts
Bundle engine, control plane  ──X──▶  reference application
```

`generator_trunk/test_bundle_architecture.py` resolves real Python `import`/`from` statements with `ast`,
so an alias, a rename, or an import nested inside a function body cannot slip past it — a grep
pattern would miss exactly the lazy import that the shared Face 1 catalog actually uses.

The report audits every non-test product layer, not just the engine-originating edges. Its
`engine_revision` hashes implementation/configuration source across the Python control plane and
the Java-heavy Core/Reader/Executor/Analyzer trees. Generated build output, tests and the direct
demonstration are excluded, so changing a real Java engine source cannot leave the revision
unchanged and changing only the proof fixture cannot masquerade as an engine change.

### Reviewed exceptions

### `domain-application` — deliberately narrower than `reference-application`

A domain application models **one subject matter** on top of the engine: its objects, the operations
over them, an oracle that decides them, and the scenarios that enumerate them. It is the position for
work like a genetics-model-testing application — neither an engine demonstration nor part of the AI
testing platform.

Its `may_import` is **engine layers plus itself, and nothing else.** Two exclusions are the point:

- **not `reference-application`.** That layer may import *itself*, so classifying a new domain there
  would leave nothing to stop it growing into, or quietly depending on, the AI testing platform. The
  separation would be a convention rather than a gate.
- **not `engine-demonstration`.** The flagship SUTs are worked examples of the method, not a
  framework. Copying one reproduces its assumptions along with its structure — precisely what a
  second domain exists to avoid.

The shared comparison harness therefore lives in `generator_trunk/bundle/study.py`, i.e. in the
**control plane**, so a domain application can use it without either forbidden edge.

The layer's root is declared *before the directory exists*. An absent root is skipped, so the
boundary is in force from the application's first commit instead of being retrofitted around code
already written. Verified by deliberately introducing both illegal imports: the gate reported four
violations with file and line, and exited non-zero.

Presentation code may *launch* a reference application; that is the allowed direction. Each such
edge is still enumerated one at a time in `DECLARED_CROSS_LAYER_EDGES` with a reason, and a test
fails if a declared edge no longer corresponds to a real import — a stale exception silently
pre-authorizes something nobody re-reviewed. There is currently exactly one:
`intake/scenario_library.py` materializing the AI release-gate sub-suite's dynamic spec.

## 4. Stable and experimental surfaces

**Stable** (changes require characterization tests and a documented contract change): the FW_Seq
combinatorial vocabulary; the spec v1 authoring contract; `bundle.run/v1`,
`bundle.stage-result/v1`, `bundle.handoff/v2`, `bundle.plan/v1`, the execution-policy model, the
canonical outcome taxonomy, `results_v2` identity, and `analyzer.provenance/v1`; the
`bundle_run.py` CLI verbs.

**Experimental** (may change without a migration path): every reference application including
`AI_combi_testing_platform`; live gRPC candidate transport; the Java executor pool; seed/iterate
feedback; the gateway; both Face 1 UIs' internal APIs.

## 5. What a minimal direct engine run requires

```text
a spec directory with one .toml
+ PostgreSQL main and results endpoints
+ Core and Reader jars
+ a Python or Java Executor
+ an execution policy
```

It requires **no** reference application, no LLM adapter, no browser, no network, and no external
SUT. The canonical proof is `generator_trunk/engine_demo/` — see §7.

## 6. Why an application may restrict itself but not the engine

A reference application legitimately pins an execution profile, a candidate transport, budget
ceilings, an Analyzer mode, and a language. Those are *its* policy, recorded per coverage target in
the reference-coverage audit's `policy_restrictions`, with the source line and whether the flag is
always present or scenario-conditional. An `argparse` option or a conditionally forwarded
user-supplied budget is not misreported as a pinned restriction. Policy findings must never be:

- re-expressed as an engine default;
- read as evidence about what the engine supports;
- allowed to remove an operator from the engine's vocabulary.

The audit therefore keeps `exercised_capabilities` and `policy_restrictions` as separate fields and
refuses to fold them into a per-capability "restricted" verdict — which capability a pinned `--lang`
forecloses is not something the launcher source states, and the audit may not guess it.

The report's `coverage_targets` deliberately distinguishes roles. `engine-demo` is a stable
`engine-demonstration`; it is not relabelled as a reference application merely because its small
scenario is useful as a coverage and overhead baseline. The AI and automation suites are
`reference-application` targets.

## 7. The direct engine demonstration

`generator_trunk/engine_demo/` is the minimal path that exercises advanced composition with nothing
from the application layer on it.

- **Structure (the engine's job).** `direct_engine_smoke/scenario.toml` uses `FW_Group`,
  `FW_PermutR(2)`, and a three-link nested-brace chain (`FW_(…)` then two `FW_()` links) to compose a
  fourth-order structure. Intermediate brace targets carry `FW_Exclude`; only the highest-order root
  enters `fw_final`.
- **Domain (the adapter's job).** `record_pipeline.py` turns the emitted marker stream into an
  immutable recursive pipeline — `Atom`, `Sequence`, `Parallel(reducer)`, `Repeat` — and executes it.
  Standard library only.
- **Truth (the oracle's job).** Three independent layers: a differential check between a compiled
  evaluator and a separately written reference interpreter; a structural output-length bound computed
  without executing anything; and an exact service contract deciding the domain question. Only the
  third may report a *domain* failure. A test seeds a defect into one evaluator and asserts the other
  catches it, so the oracle is demonstrably not vacuous.

Measured on this host (see [18_VERIFICATION_AND_RELEASE_REPORT.md](18_VERIFICATION_AND_RELEASE_REPORT.md)
for the dated record): 8 generated, 8 emitted, 8 executed, 6 PASS + 2 DOMAIN_FAIL, 0 BROKEN /
TIMEOUT / INFRA_FAIL, 8 persisted, formal Analyzer over the 6 eligible candidates, `provenance_ok`.
Both domain failures are attributable to stage **order**, not to a template — both grouped modules
are monotone on their own, so only the composition can break the contract.

The plan reports `UNKNOWN` for this scenario and that is correct: brace and `FW_Group` cardinality is
genuinely runtime-known. The launcher pairs `--allow-extreme` with explicit `--budget-*` ceilings, a
bounded materialization gate rather than a fabricated exact count.

## 8. HEAD, BODY, TAIL, `RunMeFirstOnce` and the runtime stages

| Construct | Scope | Owner |
|---|---|---|
| `RunMeFirstOnce` | once per handoff, before the candidate family | engine (Reader exports it, Java `MainWatch` invokes it) — see [RUNMEFIRSTONCE_LOGICAL_CONSTRUCT.md](RUNMEFIRSTONCE_LOGICAL_CONSTRUCT.md) |
| `HEAD` | once per candidate, first | scenario author: imports, deterministic seed/context, the structures BODY writes into |
| `BODY` | the combinatorial atoms and operators | the engine composes these; the author declares them |
| `TAIL` | once per candidate, last | scenario author: finalize, execute, run the oracle, emit exactly one `K=V` metrics line |

`RunMeFirstOnce` is a run-scoped prologue, not a combinatorial factor. Candidate-dependent setup and
verdict logic belong in HEAD/TAIL.

## 9. Higher-order composition is an engine capability

First-, second-, third- and higher-order composition lives in Core (`SeqParser`,
`BraceOperationHandler`, `SheetWorker`) and is reachable from any spec. It has nothing to do with
LLMs:

| Order | Construct | Operates on |
|---|---|---|
| 1 | `FW_Combi(k)`, `FW_CombiR(k)`, `FW_Permut(k)`, `FW_PermutR(k)`, `FW_Subsets*`, `FW_Cartes`, `FW_Separator` | one sheet's values |
| 2 | brace `FW_(start,_,E1,rel,E2,_,end,sep,mult)`, `FW_Group` | prior **result tables** |
| 3+ | `FW_()` / `FW_()G` operands | the most recent prior brace result |

`generator_trunk/bundle/coverage.py` cross-checks its capability registry against the `fwgen`
grammar the Core is verified against: every `FW_` name the grammar recognizes must be owned by
exactly one capability, and every capability's probe token must be accepted by the real parser. A new
engine verb cannot be added without the audit noticing.

## 10. Component status

| Component | Status | Note |
|---|---|---|
| Core, Reader, Executor, Analyzer | stable engine | the primary authored technology |
| `generator_trunk/bundle` control plane | stable engine infrastructure | one entry point, one lifecycle |
| `generator_trunk/engine_demo` | stable demonstration | release-gate sized, self-contained |
| Face 1 Old / Face 1 New | replaceable presentation | removing them removes no engine capability |
| Evaluation gateway | experimental | not a remote security boundary |
| `AI_combi_testing_platform` | experimental reference application | valuable proof of concept; not the product definition |
| `scenarios/automation_scheme_studio` | reference application | higher-order composition against an external SUT |
| Other `usecases/`, `llm_*`, `combinatorial_tests/` trees | reference material | varying maturity |

## 11. Migration rule: characterize before moving

Reclassifying a tree in `architecture.py` is cheap and reviewable. Moving Core/Reader/Executor source
is neither. Therefore:

1. no engine source tree moves without characterization tests that pin current behaviour first;
2. a cosmetic directory reshuffle is **not** architectural separation and must not be presented as
   one;
3. the boundary is changed by editing the declaration and its tests, in the same commit as the code;
4. if a defect is discovered while establishing a boundary, it is isolated with a failing test and
   fixed separately — never folded into a refactor.

## 12. Running the gates

```bash
python generator_trunk/bundle_run.py architecture --json /tmp/architecture.json
python generator_trunk/bundle_run.py coverage --json /tmp/reference-coverage.json
python -m pytest -q generator_trunk/test_bundle_architecture.py \
                   generator_trunk/test_bundle_coverage.py \
                   generator_trunk/engine_demo/test_engine_demo.py
```

Both reports are side-effect-free source analyses: no database, no JAR, no run directory. The
overhead measurement needs infrastructure and is a separate, explicitly bounded step:

```bash
python generator_trunk/bundle_run.py bench --profile 100 \
  --stages 'reference_overhead[engine-demo],reference_overhead[ai-combi]' \
  --scratch /tmp/refovh --out /tmp/refovh/bench.json
python generator_trunk/bundle_run.py coverage --measurements /tmp/refovh/bench.json \
  --json /tmp/reference-coverage.json
```

When a target declares a single-scenario launcher leg, its overhead stage runs the **same**
scenario, policy, candidate count and oracle twice — once through `bundle_run.py` directly, once
through the target's launcher. A target whose launcher can only run a whole suite records the
direct leg and an explicit reason instead of pretending to have a comparison. Both executable legs
use fresh unique database names registered for cleanup on both PostgreSQL clusters and unique run
IDs; a launcher that cannot accept both overrides is not run by the benchmark. The `--profile` value sizes ordinary
micro-benchmark stages only; reference-overhead stages report the actual candidate count of their
fixed bounded scenario. Phases are reported separately
(`bundle_plan`, `engine.gen/core/reader/executor/analyzer`, `bundle_cli_overhead`,
`application_overhead`, totals); an unmeasured phase is absent, never zero. The wrapper's preparation
and post-processing are reported as one aggregate, because separating them from outside requires
instrumenting the wrapper — an invented split would be worse than an honest aggregate.

See also: [02_ARCHITECTURE.md](02_ARCHITECTURE.md),
[21_ARCHITECTURE_DECISIONS.md](21_ARCHITECTURE_DECISIONS.md),
[27_TABLE_ARCHITECTURE_AND_READER_ASSEMBLY.md](27_TABLE_ARCHITECTURE_AND_READER_ASSEMBLY.md),
[../ZEN_OF_COMBINATORICS.md](../ZEN_OF_COMBINATORICS.md).
