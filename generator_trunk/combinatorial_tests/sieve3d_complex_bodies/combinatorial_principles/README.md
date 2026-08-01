# sieve3d combinatorial principles

This sub-suite is a direct answer to the Claude handoff claim that the useful
work is hand-picked geometry, not Bundle combinatorics. It does not try to find
a new geometric passage. Instead it uses combinatorial generation where the
oracle is cheap and strong: action algebra over the SUT experiment state.

## Specs

| Spec | Main verbs | Oracle |
|---|---|---|
| `action_laws/sieve3d_action_laws.toml` | `FW_Combi(2)` body/sieve cells, `FW_PermutR(2)` action words, `FW_Combi(1)` fault and scale selectors, `FW_Subsets` observers, `FW_Optional` record status | commutation, path independence, batch equivalence, reset idempotence, rejected-action atomicity |
| `interleavings/sieve3d_interleavings.toml` | `FW_Combi(2)` body pairs, `FW_Permut` over four two-body operations, `FW_Subsets`, `FW_Optional` | any interleaving of independent body actions must equal a body-grouped execution that preserves the generated local order for each body |

Every generated candidate starts recording through `/api/v1/record` at the end
of `HEAD`, stops and retrieves the record at the start of `TAIL`, saves `.rec`
and `.json` files beside run results, and prints Analyzer metrics.

The equivalence oracles are explicitly preconditioned: if a generated order
hits a legal collision/boundary rejection before both compared executions can
complete, the candidate is classified as a precondition miss (`FW_VAR=4`), not
as a SUT violation. Observer calls are outside the state-equivalence oracle
because self-measurement can legitimately change API-call telemetry.

Every action-law candidate evaluates both selected body/sieve cells. The chosen
fault is also checked for every selected cell, while the action word and scale
establish the exact pre-rejection state, so those Bundle axes are behavioral
rather than label-only products. Any one selected-cell precondition miss makes
the whole candidate a precondition miss.

These tests show the general combinatorial principle: when the oracle is a
metamorphic law, combinations of entities and action orders are valuable even
without manually known geometry outcomes. They complement, not replace,
absolute geometric anchors such as mass conservation and analytic volume checks.

## Run pattern

Fast regression, including representative generated candidates from every law
family:

```bash
cd generator_trunk
python3 test_sieve3d_combinatorial_principles_usecase.py
```

Full Bundle matrices:

```bash
cd generator_trunk
python3 bundle_run.py combinatorial_tests/sieve3d_complex_bodies/combinatorial_principles/action_laws \
  --db sieve3d_action_laws --execution-policy-profile trusted-local \
  --candidate-origin reviewed-checked-in \
  --acknowledge-trusted-local 'reviewed checked-in sieve3d action-laws fixture' \
  --analyzer "law_evals:max,preconditions_met:max,precondition_skips:min,oracle_checks:max,violations:min,record_steps:max,api_calls:min" \
  --analysis-mode formal --run-id sieve3d-action-laws

python3 bundle_run.py combinatorial_tests/sieve3d_complex_bodies/combinatorial_principles/interleavings \
  --db sieve3d_interleavings --execution-policy-profile trusted-local \
  --candidate-origin reviewed-checked-in \
  --acknowledge-trusted-local 'reviewed checked-in sieve3d interleavings fixture' \
  --analyzer "law_evals:max,preconditions_met:max,precondition_skips:min,oracle_checks:max,violations:min,record_steps:max,api_calls:min" \
  --analysis-mode formal --run-id sieve3d-interleavings
```
