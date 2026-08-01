# Release-gate breakpoint sub-suite

This reusable sub-suite tests whether a target AI can solve an ordinary software
release audit as task size and prompt interference increase. Combinatorics is
the test-construction instrument; the target is never asked a combinatorics
question.

The task factory plants an independently computed answer, while the packaged
runtime oracle re-evaluates every inequality and the complete binary AND/OR
tree. It checks the final decision and the exact set of failed leaf checks.
Strict output-contract compliance and conservatively extractable semantic
correctness remain separate measurements.

## What is configurable

Copy `config.example.json` outside the source tree and replace its target cell.
The configuration controls:

- any number of provider/model/effort cells;
- one through six strictly doubling task sizes, from 2 through 64 checks;
- named phase-one factor signatures;
- the fresh-session instruction printed above every prompt list.

Provider names, model labels, effort labels, dates, request counts, and output
filenames are not embedded in the implementation. For a quick default design,
repeat `--target` instead of creating a file:

```bash
python3 generator_trunk/AI_combi_testing_platform/export_release_gate_exchange.py \
  --out ../release-gate-exchange \
  --target 'provider::exact model label::effort label'
```

Use `--config /path/to/config.json` for custom levels or signatures. The runner
requires `BUNDLE_MAIN_DB_PASSWORD` and `BUNDLE_RESULTS_DB_PASSWORD` in the
environment, removes provider API credentials from the local constructor
process, uses the network-disabled `generated-default` execution policy, and
drops its narrowly named ephemeral databases before publishing the exchange.

Generated exchanges are runtime evidence, not repository source. Keep `--out`
outside the Framework source checkout; the CLI enforces this boundary. Do not
commit exchanges or returned model responses.

## Face 1 local apparatus

Face 1 Old and Face 1 New expose this sub-suite as `AIRG · Fresh release-gate
breakpoint apparatus`. The catalog stores only the reviewed materializer,
source reference, doubling ladder, and immutable safe launch profile; it does
not store a generated held-out task.

Inspecting the entry creates a fresh spec in an operating-system temporary
directory, strictly loads and plans it, and removes that temporary directory.
Starting it creates another fresh spec inside the GUI run's isolated temporary
tree and executes all 2,560 local oracle controls. The profile is
network-disabled, zero-cost, and strips prompt-export settings plus known
provider credentials from the child environment.

That run proves the apparatus is internally executable; it does not contact or
measure a target AI. Use the exporter above, outside the source checkout, for
the separately identity-labelled prompt/response exchange.

## Bundle construction

For each task level, Bundle constructs all `2^9 = 512` prompt plans from:

1. `FW_Permut(2)` section order;
2. numeric surface;
3. context depth;
4. output schema;
5. trust-boundary wording;
6. licensed alternate check labels;
7. licensed alternate decision words;
8. a stale-archive distractor;
9. an embedded-override distractor.

The constructor also uses `FW_Group`, four actual nested result-table braces,
and four independent `FW_Optional` atoms. A five-level configuration therefore
produces 2,560 local exact-control candidates. Phase one exports only the
configured signatures—normally the zero-weight and weight-nine extremes—so
live model calls stay bounded.

`PAIRWISE_COVERING_SIGNATURES` is a 10-row, strength-two follow-up design. Its
row weights are exactly 0 through 9, so the contrast-state scale is
`1, 2, 4, ..., 512`; every factor column is balanced and every factor pair
realizes `00`, `01`, `10`, and `11`.

### Why Core reports 160 while Reader reports 2,560

The five task levels and 32 mandatory construction surfaces materialize as 160
`fw_final` rows. Four one-valued `FW_Optional` atoms are stored separately as
`fw_opt1..4`; Reader combines their absent/present space with every mandatory
row. Consequently, `160 × 2^4 = 2,560` is the expected result, not a mismatch.
The exporter reconciles Reader actual against the Reader stage's declared
runtime expansion and then against Executor/outcome/metrics/provenance counts.
It never requires mandatory `fw_final` rows to equal assembled candidates.

## Exchange contents

The exported package contains:

- exact ordered prompt lists and matching response templates per target cell;
- `bodies/HEAD.py`, split safe-cell sources, `TAIL.py`, and selected fully
  assembled Reader candidates;
- the generated Bundle scenario, plans, held-out task documents, and design
  manifest;
- a standalone deterministic oracle and an exchange bootstrap/scoring driver
  named `RunMeFirstOnce.py` for package compatibility.

The driver verifies immutable hashes before examining or scoring response
files:

```bash
cd /path/to/release-gate-exchange
python3 RunMeFirstOnce.py
python3 RunMeFirstOnce.py --require-complete
```

It never upgrades a strict failure from extracted prose. Multiple distinct
complete answers, partial answers, and refusals fail closed.

This exported filename is intentionally distinguished from the Bundle's
canonical `FW_RunMeFirstOnce` construct. A canonical run-once prologue executes
before one candidate family and establishes shared context; scoring completed
responses belongs to the oracle/reporting phase. Here the single standalone
driver combines package preflight and later scoring for an offline exchange; it
does not redefine the runtime construct.

## Developer verification

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=generator_trunk \
  python3 -m pytest -q \
  generator_trunk/AI_combi_testing_platform/tests/test_optional_reconciliation.py \
  generator_trunk/AI_combi_testing_platform/tests/test_release_gate_runtime.py \
  generator_trunk/AI_combi_testing_platform/tests/test_release_gate_exchange.py \
  generator_trunk/AI_combi_testing_platform/tests/test_release_gate_package.py \
  Executor_trunk/test_py_executor_outcomes.py
```
