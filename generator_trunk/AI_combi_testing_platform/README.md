# AI Combinatorial Testing Platform

> **Status: experimental reference application.**
>
> Bundle is an executable combinatorial design-space and evidence engine; AI response testing is one
> application of it. This platform proves *an* application of the Bundle — it does not define the
> Bundle, and it does not bound the engine's capability, supported operators, or measured
> performance. Its pinned execution profile, budgets, language and Analyzer mode are **its** policy,
> not engine defaults.
>
> To see the engine without any application on the path, use
> [`generator_trunk/engine_demo/`](../engine_demo/README.md). For the boundary itself, see
> [`docs/30_ENGINE_FIRST_ARCHITECTURE.md`](../../docs/30_ENGINE_FIRST_ARCHITECTURE.md); for what this
> platform does and does not exercise, run `bundle_run.py coverage`.

This directory is a Bundle-native AI evaluation derivative. It compiles
canonical tasks, renderings, recursive prompt programs, adapter choices, and
product modes through real `FW_Seq` result tables; executes each assembled
candidate; applies an independent exact oracle; and sends one finite metrics
record per candidate to the formal Analyzer.

The default path is deterministic, local, and cost-free. `oracle-control` and
`fragile-control` are pipeline controls, **not AI models**. Reports with only
controls explicitly withhold model-routing claims.

## Architecture

```text
immutable canonical Task IR
  -> exact solver (oracle-only metadata)
  -> renderer(task only; never receives the answer)
  -> recursive prompt-program IR
  -> explicitly selected adapter
  -> independent response parser + per-constraint oracle
  -> one app=... FW_VAR=... metrics line
  -> Bundle results DB + formal Analyzer + reconciled report
```

- `task_ir/`: deterministic ordering and exact rational-cancellation tasks.
- `renderers/`: semantic costumes, paraphrases, instruction order, output
  schemas, distractors, long-range filler, and recursive prompt-program nodes.
- `oracles/`: exhaustive ordering solver, exact `Fraction` arithmetic, strict
  parsers, membership/rule checks, and stable verdict codes.
- `adapters/`: exact positive control, deterministic negative control, and a
  fail-closed opt-in OpenAI-compatible HTTPS boundary.
- `metrics/`: whitespace-safe, finite K=V records with task, renderer, model,
  prompt, environment, seed, cost, latency, token, and program provenance.
- `dataset.py`: exact-PASS-only, metadata-required, deduplicated JSONL export.
- `reporting.py`: count/outcome/provenance reconciliation and shared
  router/prompt-CI/dataset summaries.

The three product modes use `engine.run_candidate`:

1. Router studies vary adapters at fixed task hashes. A routing rule is emitted
   only when non-control evidence exists and a quality floor is documented.
2. Prompt CI compares versioned renderings on fixed canonical tasks plus fresh
   holdouts; correctness and format remain exact gates.
3. Dataset export accepts only exact-oracle PASS pairs and records source kind,
   license, privacy class, structural hash, renderer, adapter, prompt version,
   and seed. A control-generated response is labeled `control`, not “ideal.”

## Scenario ladder

| Scenario | Planned final count | Bundle feature |
|---|---:|---|
| `00_smoke` | 32 exact | bounded first-order full-chain smoke |
| `01_operator_smoke` | runtime-known; 8 measured | `FW_Group`, `FW_PermutR`, three nested braces |
| `10_constraint_stack` | 72 exact | subset-combined pressure and complexity ladder |
| `20_logic_and_cancellation` | 24 exact | `FW_CombiR` repeated exact transformations |
| `30_semantic_interference` | 12 exact | loaded labels, paraphrases, optional noise |
| `40_long_range_dependency` | 9 exact | ordered repeated long-range motifs |
| `50_format_and_instruction_order` | 12 exact | `FW_Permut` section order and schemas |
| `60_higher_order_prompt_programs` | runtime-known; 1 measured | four brace levels including `FW_()G` |
| `70_router_regression_dataset` | 24 exact | shared three-product evidence matrix |

Operands and intermediate brace targets use `FW_Exclude`; only the highest
root enters `fw_final`. Runtime-unknown higher-order plans are intentional and
require the launcher's recorded budget override.

## Commands

From the Framework root:

```bash
python3 generator_trunk/AI_combi_testing_platform/RunMeFirstOnce.py --with-tests
python3 generator_trunk/AI_combi_testing_platform/run_campaign.py list
python3 generator_trunk/AI_combi_testing_platform/run_campaign.py plan
python3 generator_trunk/AI_combi_testing_platform/run_campaign.py smoke
python3 generator_trunk/AI_combi_testing_platform/run_campaign.py run \
  --scenario 10_constraint_stack
```

`plan` is always run immediately before `smoke` or `run`. Executable commands
require the normal `BUNDLE_MAIN_DB_PASSWORD` and
`BUNDLE_RESULTS_DB_PASSWORD` environment variables. Reports go to ignored
`campaign_results/` by default; candidates, databases, responses, and runtime
evidence are not source files.

### Meaning of `RunMeFirstOnce.py` here

The platform-level script is a manual, cost-free readiness preflight: it checks
the local launcher, disabled-by-default external configuration, deterministic
planning, and optionally the focused tests. It is analogous to the Bundle's
run-scoped prologue, but it is not automatically executed as the canonical Java
`FW_RunMeFirstOnce` hook.

For AI experiments, run-once scope freezes one target/configuration/effort cell:
manifest and oracle hashes, adapter readiness, budgets, and session policy.
Creating a fresh session is per prompt candidate; parsing and scoring a response
is post-candidate oracle/reporting work. See the canonical
[`RunMeFirstOnce` definition](../../docs/RUNMEFIRSTONCE_LOGICAL_CONSTRUCT.md).

Both Face 1 Old and Face 1 New expose two AI catalog groups. The exact-oracle
group loads checked-in `AI00`, `AI01`, and `AI70` specs. The advanced
sub-suites group exposes `AIRG`, the release-gate breakpoint apparatus, through
a reviewed dynamic materializer instead of freezing a held-out task in TOML.

Both GUI backends isolate the selected spec from the current workbook. `AIRG`
creates a new five-level 2/4/8/16/32 task ladder at inspection or launch, checks
its planted answers with the independent runtime oracle, and pins the
network-disabled `generated-default` profile, formal goals, bounded 2,560-row
budgets, and zero external cost. GUI launches remove prompt-export controls,
external adapter configuration, and known provider credentials.

This GUI entry validates local constructor/oracle apparatus only. Acquire and
score target-AI responses through the separate exchange workflow below.

## External adapters

`config.example.json` contains no credential and keeps every external adapter
disabled. Enabling one requires all of:

- a reviewed copy of the configuration with `enabled: true`;
- a credential named by `api_key_env`, supplied only through the environment;
- `AI_COMBI_ALLOW_EXTERNAL=1`;
- positive request and explicit monetary budgets;
- explicit launcher acknowledgement of reviewed controlled candidate code.

The adapter refuses missing budgets, insecure HTTP (unless a separate
test-only override is explicit), missing credentials, malformed provider
responses, and implicit network use. Provider/network exceptions propagate so
the Executor cannot mislabel them as wrong domain answers. Never use
`trusted-local` for unreviewed generated code.

## Release-gate breakpoint sub-suite

[`sub_suites/release_gate_breakpoint/`](sub_suites/release_gate_breakpoint/)
is a reusable, acquisition-neutral breakpoint study. It creates fresh ordinary
software-release audits whose leaf count follows a configurable doubling
ladder, then uses nine binary Bundle construction factors to materialize 512
exact-control prompt candidates per level. The target AI is not asked a
combinatorics question; combinatorics constructs the controlled prompts.

Target provider, exact model label, effort label, difficulty levels, phase-one
signatures, and fresh-session wording come from a credential-free JSON config
or repeatable `--target` arguments:

```bash
python3 generator_trunk/AI_combi_testing_platform/export_release_gate_exchange.py \
  --out ../release-gate-exchange \
  --target 'provider::exact model label::effort label'
```

The generated exchange contains ordered prompt/response files, whole and split
HEAD/TAIL bodies, selected assembled Reader candidates, immutable hashes, and a
standalone exact oracle. Its exported `RunMeFirstOnce.py` is an exchange
bootstrap and scoring driver—the historical filename does not make
post-response scoring part of the canonical run-once semantics. The exchange
belongs outside the source tree and must not be committed. See the
[sub-suite guide](sub_suites/release_gate_breakpoint/README.md) for
configuration, Bundle construction, cleanup, and scoring details.

### Anonymized empirical proof of concept

A 2026-07-29 terminal-only study used one intentionally anonymized target at its
lowest supported reasoning-effort setting. Across 20 designed fresh sessions it
passed 16 strict and 16 semantic checks. On one fixed two-check task, the clean
endpoint passed twice while the maximal construction endpoint failed twice with
the same objectively extra failed check; the ten-row follow-up passed weights
0..6 and failed weights 7..9. This is real target evidence that combinatorial
prompt construction can expose a defect hidden by clean-only sampling, not a
model ranking or a calibrated universal breakpoint. See the
[dated findings](../../docs/AI_COMBI_SESSION_FINDINGS_2026-07-29.md).

## Interpretation limits

- Fresh deterministic generation reduces exact static-item lookup; it does not
  prove a task was absent from model training.
- Semantic words can expose abstraction sensitivity, but tokenization does not
  make difficulty “exponential,” and hidden-vector stories are not evidence.
- One model response cannot establish reliability. Use Bundle repeats and
  controlled environments for stochastic systems.
- `pass_rate * complexity` is not a universal intelligence score. Correctness
  gates eligibility; declared quality, cost, latency, and robustness objectives
  form a Pareto front.
- A Pareto front has no universal winner. Apply a documented deployment policy
  after the front is known.

See `REQUIREMENTS.md` for traceability and `RESULTS.md` for durable smoke
evidence.
