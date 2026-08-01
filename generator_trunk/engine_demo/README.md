# Direct engine demonstration

The minimal path that proves advanced Bundle composition is an **engine** capability, with no
reference application, no LLM adapter, no browser, no network, and no external system under test on
it. Standard library only.

If you want to understand what the Bundle is, start here — not with an application.

```bash
python generator_trunk/engine_demo/run_direct_engine_smoke.py plan     # no database needed
python generator_trunk/engine_demo/run_direct_engine_smoke.py run --db-endpoint deploy
```

`plan` is side-effect-free and needs no database, container, network or credential.

`run` executes the full chain and therefore **needs two PostgreSQL endpoints and their
credentials**. It must also be launched from the repository root (candidate code imports
`generator_trunk.engine_demo...`). Runtime output goes to `/tmp/fw_work`; nothing here writes into
the source tree.

### Choosing the database endpoint

`--db-endpoint` is required for `run` and has **no default**. Ports and credentials always come
from one source together:

| Selection | Ports from | Credentials from |
|---|---|---|
| `--db-endpoint deploy` | `generator_trunk/deploy/.env` | the same file |
| `--db-endpoint manual --main-port P --results-port Q` | those flags | `BUNDLE_MAIN_DB_PASSWORD` / `BUNDLE_RESULTS_DB_PASSWORD` |

For the local stack, start it first and select it:

```bash
python generator_trunk/bundle_run.py deploy up
python generator_trunk/engine_demo/run_direct_engine_smoke.py run --db-endpoint deploy
```

The launcher prints a preflight banner naming the resolved hosts, ports, database and the *source*
of each setting — never a credential value — and it rebuilds the child environment from that one
source, so ambient `BUNDLE_*_DB_*` exports from another cluster cannot redirect the run or supply
half its settings.

There is deliberately no implicit fallback to `5433`/`5432`. Those defaults used to make the
demonstration look like it exercised the deployed stack while it was actually writing into whatever
PostgreSQL happened to listen on the host's default ports. A mixed selection (deploy credentials
with hand-picked ports, or manual ports addressing the deploy stack with foreign credentials) is
refused with an explanation rather than attempted.

## Two demonstrations, one engine

| Adapter | Domain | Oracle family | Scenario |
|---|---|---|---|
| `record_pipeline.py` | pure stream transformation | differential (two evaluators) + structural bound + contract | `direct_engine_smoke/`, `flagship/bundle_native_l2,l3,l4` |
| `txn_store.py` | **stateful store with commit/rollback** | **coherence invariant + metamorphic rollback identity + naive replay + bound** | `flagship/bundle_native_s2` |

They exist as a pair on purpose. The engine's half — `FW_Group`, `FW_PermutR`,
`FW_Optional`, a five-link nested brace chain — is *identical* between them; only the adapter
changes. So the second one answers a question the first cannot: whether a result measured through
this engine is about the engine or about the system that happened to be under it. See
[docs/35 §6a](../../docs/35_FLAGSHIP_DECISION_AND_BASELINES.md).

## What it demonstrates

| Concern | Owner | Where |
|---|---|---|
| structural enumeration | the **engine** | `direct_engine_smoke/scenario.toml` |
| domain realization | the **adapter** | `record_pipeline.py` |
| truth | the **oracle** | `record_pipeline.py` (three independent layers) |

That separation is the whole point: the engine never knows what a record pipeline is, and the
adapter never knows what a brace is.

### The composition (the engine's half)

```text
SEQ_RESULT  = FW_(SEQ_OPEN,,GROUPED_STAGE,,REPEATED_MOTIF,,SEQ_CLOSE,,M:N)
PAR_RESULT  = FW_(PAR_OPEN,,FW_(),,SIDE_BRANCH,,PAR_CLOSE,,M:N)
ROOT_RESULT = FW_(ROOT_OPEN,,FW_(),,FINALIZER,,ROOT_CLOSE,,M:N)
```

- `FW_Group` (via `group_replace`) re-combines a sheet's own prior result rows as atoms.
- `FW_PermutR(2)` produces the four ordered stage pairs *with* repetition.
- Each brace joins two **prior result tables**; the two `FW_()` links consume the previous brace
  result, so the root is a fourth-order composition — not a wider Cartesian product.
- Every operand and intermediate brace target carries `FW_Exclude`. Only `ROOT_RESULT` enters
  `fw_final`. Drop one of those exclusions and the space multiplies instead of composing; the
  launcher's `--budget-final-candidates` ceiling turns that regression into a failed run rather than
  a quietly larger one.

### The pipeline (the adapter's half)

```text
Node := Atom(kind, params)
      | Sequence(children)
      | Parallel(children, reducer)
      | Repeat(child, count)
```

Every node denotes a total function `tuple[int, ...] -> tuple[int, ...]`, so any nesting the engine
produces is executable. Atoms: `scale`, `offset`, `clamp`, `drop_below`, `dedupe`, `sort`.

### The oracle

Three independent layers, in order:

1. **Differential** — a compiled closure-tree evaluator and a separately written recursive
   interpreter must agree. The duplication *is* the oracle; factoring the two together would delete
   the check. `test_the_differential_oracle_is_not_vacuous` seeds a defect into one evaluator and
   asserts the other catches it.
2. **Structural** — an output-length bound computed from the tree without executing anything, sound
   because every atom is non-expanding.
3. **Service contract** — the exact domain question: non-empty, non-decreasing, and inside the
   declared value band. Only this layer may report a *domain* failure.

```text
FW_VAR=0  contract satisfied
FW_VAR=2  construction/compile/validation failure
FW_VAR=3  execution failure
FW_VAR=4  oracle disagreement or structural-bound violation   (a defect, never a domain answer)
FW_VAR=5  service contract violated                            (the domain verdict)
```

Keeping 4 and 5 apart is what stops an infrastructure or implementation defect from being reported
as a discovered domain fault.

## Expected outcome

8 candidates: **6 PASS, 2 DOMAIN_FAIL** with the stable reason `not_non_decreasing`.

Both failures come from stage **order** — `sort` followed by `scale(k=-1)` — and appear under both
grouped modules. Neither template can violate the contract alone: both are monotone. So the failure
is a genuine interaction the engine found by composing, which is the property the demonstration
exists to show.

`bundle plan` reports `UNKNOWN` for this scenario. That is correct, not a limitation: brace and
`FW_Group` cardinality is only known once Core materializes the intermediate result tables. The
launcher therefore pairs `--allow-extreme` with explicit budget ceilings — a bounded materialization
gate instead of a fabricated exact count.

### Why `plan` prints `⛔ BUDGET BLOCKING` and still exits 0

Expected, and not a failure. Because the cardinality is statically `UNKNOWN`, the plan cannot prove
in advance that the run fits under the configured hard ceilings, so every affected dimension is
reported `[BLOCKING]`. Budget evaluation on the plan path is **analysis-only** — the plan itself
labels it `budget evaluation (analysis-only; the run path is the enforcement point)`. Enforcement
belongs to `run`, which is where the ceilings are actually applied and where this launcher passes
its own much smaller gate (`--budget-final-candidates 64`, `--budget-mandatory-rows 64`) plus the
recorded `--override-budget` reason.

So `plan` exits 0 by design: it completed the analysis it was asked for. Do not gate a pipeline on
`plan`'s exit status alone — read the `cardinality`/`budget` fields of the emitted `plan.json`, or
run the `run` path, which fails closed.

## Tests

```bash
python -m pytest -q generator_trunk/engine_demo/test_engine_demo.py \
                   generator_trunk/engine_demo/test_engine_demo_endpoint.py
```

Self-contained: no database, no network. They characterize the structural semantics, prove the
oracle is not vacuous, and pin the 8/6/2 outcome so a regression in Core's brace or grouping
behaviour is visible without a full run.

See [`docs/30_ENGINE_FIRST_ARCHITECTURE.md`](../../docs/30_ENGINE_FIRST_ARCHITECTURE.md).
