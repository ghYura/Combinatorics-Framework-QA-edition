# Automation Scheme Studio Bundle campaigns

This scenario family composes real SUT components into typed circuits, compiles
each graph, runs the SUT's fixed-step engine, reads every tester terminal, asks
an independent Oracle for a verdict, and sends formal multi-objective metrics to
Analyzer. Generated snippets contain only architecture decisions; control math
remains in `automation-scheme-studio`.

## Search space

| Spec | Deep rule / purpose | Candidates |
|---|---|---:|
| `00_smoke/scenario.toml` | full-battery integration smoke | 48 |
| `01_ordered_serial/scenario.toml` | `FW_PermutR(3)` over eight forward stages | 49,152 |
| `02_deep_nested/scenario.toml` | branch subsets × three ordered loop slots (identity or feedback SCC) | 90,000 |
| `03_redundant_multiset/scenario.toml` | `FW_CombiR(3)` redundant controller branches | 7,680 |
| `04_brace_join/scenario.toml` | brace M:N join (runtime Core/Reader reconciled) | 1,152 |
| `05_cartesian_refinement/scenario.toml` | `FW_Cartes` tuning/plant matrix, full battery | 7,680 |
| `06_feedback_path_covering/scenario.toml` | 370-front × 16-row deep feedback-path covering | 5,920 |
| **Materialized total** | all candidates, no sampling or sieve | **155,712** |

## Recursive higher-order feedback suite

`advanced_feedback/` is a separate architecture search, not an extension of the 155,712-candidate historical campaign above. Bundle fragments emit an immutable recursive topology whose nodes may be sequence, parallel fan-out/fan-in, serial/parallel repetition, or feedback. Every node type may contain every other node type. The adapter compiles that topology through the SUT’s real `Circuit`, compiler, fixed-step runtime, tester terminals, Oracle, and the same seven-objective formal Analyzer.

| Spec | Higher-order construction | Current evidence |
|---|---|---:|
| `advanced_feedback/00_smoke/scenario.toml` | four recursive circuit families × policy × plant × profile | 32 executed; 1 PASS |
| `advanced_feedback/01_operator_smoke/scenario.toml` | `FW_Group` + `FW_PermutR` + three nested braces | 8 executed; 4 PASS |
| `advanced_feedback/10_third_order_brace/scenario.toml` | ordered pairs of all 16 stages → parallel complex-loop branches → outer feedback | plan green; full run deferred |
| `advanced_feedback/20_grouped_repetition/scenario.toml` | combinations-of-combinations → repeated motifs → nested outer feedback | plan green; full run deferred |

The two advanced smokes completed the full Generate → Core → Reader → Python Executor → Oracle → formal Analyzer chain on 2026-07-25 with zero BROKEN/TIMEOUT/INFRA_FAIL outcomes. The nonzero verdicts were control-quality rejections, not assembly or runtime failures. The heavy scenarios deliberately remain runtime-cardinality class X because later operators consume generated result tables.

Intermediate brace targets are `FW_Exclude` assembly temporaries. Only the highest-order target enters `fw_final`; the operator smoke pins this at 8 meaningful final candidates rather than the 512 redundant candidates produced when all three intermediate targets were independently multiplied.

The screening specs still test transition and stability together: every
candidate receives a step and a deterministic noisy sine. The smoke and
refinement specs add square and ramp cases. Deep-loop candidates include every
ordered length-three word over identity plus four real loop cells: effective
depths zero through three remain comparable, and real cells close feedback
edges through SUT-declared state boundaries. Bundle's static planner proves the
ordinary-verb counts, bounds `FW_Cartes`, and marks brace count unknown; the
brace and redundant-multiset figures above are the actual
Core/Reader-reconciled counts from green runs.

## Run from Face 1

Both Face 1 interfaces load the shared checked-in scenario catalog. The picker offers the seven historical tiers under **Automation Scheme Studio — exhaustive control-chain search** and the four recursive scenarios under **Automation Scheme Studio — recursive higher-order feedback**. The catalog pins the sharded/eight-worker Python profile, formal seven-objective Analyzer, and ports 5433/5432. Runtime-cardinality recursive scenarios also carry the explicit `--allow-extreme` and `--override-budget` acknowledgement required by the Bundle. Database passwords remain server-environment-only. An explicit `BUNDLE_SUT_ROOT` wins; otherwise sibling checkouts named `SUT` or `SUT-main` are discovered.

## Run

From the Framework repository root, point `BUNDLE_SUT_ROOT` at the directory
that contains `automation-scheme-studio` when it is not a sibling checkout
named `SUT` or `SUT-main`.

```bash
python3 generator_trunk/scenarios/automation_scheme_studio/run_campaign.py bootstrap
python3 generator_trunk/scenarios/automation_scheme_studio/run_campaign.py plan
```

The optional `RunMeFirstOnce.py` is a manual preflight; Python Executor does not
execute a special RunMeFirstOnce hook, so each candidate imports `bootstrap.py`
itself.

For an executed smoke or exhaustive campaign, provide both database passwords
through the environment (never a spec or command-line argument), then run:

```bash
python3 generator_trunk/scenarios/automation_scheme_studio/run_campaign.py smoke
python3 generator_trunk/scenarios/automation_scheme_studio/run_campaign.py run
```

The runner uses ports 5433 (Core) and 5432 (Results), sharded candidate storage,
the Python Executor's deterministic local worker dispatcher (up to eight workers
by default), formal Analyzer goals, and the explicit exhaustive-run override.
Select a tier with `--spec 04_brace_join` or tune concurrency with
`--executor-workers N`. Each spec gets
its own database and evidence directory, so a completed earlier tier is not
silently overwritten.

For the recursive suite:

```bash
# no databases: validate all four plans
python3 generator_trunk/scenarios/automation_scheme_studio/advanced_feedback/run_advanced_campaign.py plan

# bounded, verified 32-candidate + 8-candidate checks
python3 generator_trunk/scenarios/automation_scheme_studio/advanced_feedback/run_advanced_campaign.py smoke

# the two deferred higher-order searches; wait for completion and aggregate
python3 generator_trunk/scenarios/automation_scheme_studio/advanced_feedback/run_advanced_campaign.py run
```

`run` does not execute either smoke again. After both heavy runs finish, the launcher validates run journals, Executor reconciliation, outcomes, and formal Analyzer provenance, then writes `common-results.md`, `common-results.json`, and `common-pareto.json` below `advanced_feedback/campaign_results/`. That directory is runtime output and is intentionally ignored by Git.

## HEAD, TAIL, Oracle, and Analyzer

HEAD records all built-in initial component parameters and the complete tester
terminal contract. Combinatorial middle fragments mutate a `SearchPlan`. TAIL
builds and compiles the real circuit, executes the battery, collects actual node
parameters and every nominal terminal value, prints one key=value metrics line,
and sets `FW_VAR`.

Oracle codes: 0 PASS; 2 invalid/build/compile; 3 runtime/non-finite; 4 unstable
response or internal terminal; 5 tracking/convergence miss. All nonzero verdicts
receive dominating penalties on every formal objective, so Analyzer's PASS
Pareto points are usable hypotheses. Raw diagnostics remain available for
failure analysis.

Formal objectives jointly prefer control quality, robustness, stability,
settling time, worst tracking error, overshoot, and effort. `evaluation_ms` is
recorded but intentionally excluded from formal ranking because a single host
run is not a controlled performance benchmark.
