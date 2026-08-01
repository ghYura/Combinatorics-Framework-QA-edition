# api_planner_feedback

Small Bundle-facing direct-versus-combinatorial planner comparison.

Both candidates run the same hard `snake -> eye_snake` body/hole/pose. One
requests `direct-drop` only; the other requests the core richer portfolio.

- `/api/v1/catalog` must advertise passage algorithms;
- `/api/v1/features` must return interactable whole, edge, center, and vertex data;
- `/api/v1/passage` executes only the request-scoped algorithms;
- each candidate brackets passage with `/api/v1/record` action/cut/retrieve
  and emits distinct `record_file`, `record_json`, and `record_steps`;
- replay API-call count and motion-frame count are separate values recorded in
  each run's metadata. They depend on the request-scoped algorithm portfolio
  and returned trace; do not hard-code an expected 28 calls or 24 frames;
- a successfully measured low-passage direct result remains analyzer-eligible;
  target attainment is an objective, not an API-contract verdict;
- the richer `snake_eye` candidate must report feedback cycles/evals;
- only passed volume and estimated cost are optimizer goals. Catalog coverage,
  success, feature counts, and execution counters are validity diagnostics.

Run through Bundle:

```bash
cd generator_trunk
python3 bundle_run.py combinatorial_tests/sieve3d_max_passage/api_planner_feedback \
  --db sieve3d_api_planner_feedback --execution-policy-profile trusted-local \
  --candidate-origin reviewed-checked-in \
  --acknowledge-trusted-local 'reviewed checked-in in-process sieve3d planner fixture' \
  --analyzer "planner_passed_volume_pct:max,planner_estimated_cost:min" \
  --analysis-mode formal --run-id sieve3d-api-planner-feedback
```

The generated metadata contains each exact `.rec` path and its actual replay
counts. These artifacts do not exist until this scenario is run. See the
[GUI replay procedure](../equivalence_size_first/README.md#gui-replay) for
`python3 main.py` and the GUI **File** workflow. The retained evidence named
by that separate guide is historical and is not present in this checkout, so
rerun the acceptance path for current proof.
