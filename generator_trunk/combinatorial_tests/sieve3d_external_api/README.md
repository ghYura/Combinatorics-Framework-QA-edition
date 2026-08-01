# sieve3d external API combinatorial tests

This folder contains Bundle specs that drive
`$BUNDLE_SUT_ROOT/3Dprofile-VS-2Dsieve` through its published
`sieve3d.api_v1` contract. `BUNDLE_SUT_ROOT` is the **parent** directory
containing the separately checked-out SUT projects, not the sieve3d checkout
itself. Relative values are resolved from the repository root.

The tests deliberately use the Bundle's three-layer model:

- **Mechanics:** `FW_Combi(1)` selects a route or start pose, `FW_Combi(2)`
  chooses combined body/sieve pairs, `FW_Permut` flips experiment action order,
  `FW_Subsets` explores observer bundles, `FW_Optional` probes the record-status
  side channel, and `FW_PermutR(2)` builds repeated tactic sequences for the
  plasticine challenge.
- **Bonds:** these two specs do not currently declare `[[constraints]]`; their
  space is bounded by the authored value domains and by separating the broad
  ladder from the expensive deep-thread challenge. Physical fit is judged by
  the runtime oracle, not pre-pruned by the constraint sieve. See the
  [max-passage scenario](../sieve3d_max_passage/README.md) for a sieve-backed
  campaign.
- **Meaning:** every candidate imports `sieve3d.api_v1`, calls route handlers
  through the same standardized envelope, declares its Analyzer metric contract
  in `HEAD`, starts SUT recording at the end of `HEAD`, stops and retrieves the
  record at the start of `TAIL`, saves the received `.rec` beside the run
  results, prints the metrics in `TAIL`, and sets `FW_VAR`/`FW_CUSTOM_VAR`.

## Specs

| Spec dir | Purpose | Shape |
|---|---|---|
| `api_ladder/` | Bounded route ladder from L0 predicates through L4 observability. It combines pairs of body/hole cases, route depth, action order, observer subsets, and optional recorder-status checks. | C(6,2) case pairs x 2 action permutations x 5 API routes x 4 observer subsets x optional record-status factor 2 = 1200 final candidates. |
| `deep_thread/` | Small, expensive challenge for the plasticine hook: direct drop, wiggle, and iterative thread tactics, including repeated ordered tactic pairs. | 2 start poses x 3^2 ordered tactic sequences = 18 candidates. |

The ladder keeps an independent oracle record for every selected case. Its
reported feasibility, clearance, and experiment passage are the selected
pair's floor, and each experiment result is checked against that case's own
`min_passed`; one successful body/hole pair cannot hide another failure.

The action permutation also controls selected-case execution order on L0-L2,
so it tests order independence there instead of creating duplicate candidates;
on L3-L4 it additionally remains the physical manipulation order.

Deep-thread treats collision/conflict as expected geometric outcomes and keeps
them separate from API or harness failures. Its effort is cumulative: experiment
effort deltas and every synchronous thread attempt's keyframes are added in
tactic order.

## Run pattern

Use `trusted-local`; these candidates import the local `sieve3d` package and do
not need a network server.

```bash
cd generator_trunk
python3 bundle_run.py combinatorial_tests/sieve3d_external_api/api_ladder \
  --db sieve3d_api_ladder --execution-policy-profile trusted-local \
  --candidate-origin reviewed-checked-in \
  --acknowledge-trusted-local 'reviewed checked-in in-process sieve3d API fixture' \
  --analyzer "passed_volume_pct:max,actions:min,clearance:max,api_route_depth:max,record_steps:max" \
  --analysis-mode formal --run-id sieve3d-api-ladder

python3 bundle_run.py combinatorial_tests/sieve3d_external_api/deep_thread \
  --db sieve3d_deep_thread --execution-policy-profile trusted-local \
  --candidate-origin reviewed-checked-in \
  --acknowledge-trusted-local 'reviewed checked-in in-process sieve3d API fixture' \
  --analyzer "passed_volume_pct:max,effort:min,thread_success:max,record_steps:max" \
  --analysis-mode formal --run-id sieve3d-deep-thread
```

Export `BUNDLE_SUT_ROOT` before launching the Bundle. Set `SIEVE3D_ROOT` only
to override the complete default project path directly. Set
`SIEVE3D_REC_OUT_DIR` when the retrieved recorder files should be written to a
specific run-results directory; otherwise each candidate writes under
`./sieve3d_rec_results`.
