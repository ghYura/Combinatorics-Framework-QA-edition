# Deterministic all-body/all-hole staged passage proof

This directory now proves one fixed 3D body/2D hole pair at a time.  The live
registries in `sieve3d_complex_bodies/complex_cases.py` currently contain ten
bodies and ten holes, so the complete matrix contains 100 independent pairs.
Choosing an easier hole is never a substitute for retrying a difficult fixed
pair.

The precise claim is:

> Minimum successful measured-action tier within the complete user-declared
> candidate universe realized for this fixed geometry and policy.

No artifact claims a globally shortest continuous path or mathematical
impossibility.  A complete negative result is named
`declared_space_exhaustion`.

## Live implementation path

The proof-bearing implementation is `staged_passage_search.py`.  The historical
best-hole and planner-probe helpers remain in `max_passage_search.py` only for
backward-compatible API/replay regression tests; its command-line entry now
routes to the staged engine.

The actual execution path is:

1. `fwgen.py` parses the TOML into `Spec`/`Slot`, proves verb cardinalities in
   `spec_cardinality_plan`, and exposes the full `FW_Combi(1)` product through
   `cartesian`.  The staged engine uses that same structured product for its
   rotation, shift, mixed, multi-move, and final-planner factors.
2. `bundle/stages.py:stage_core` runs the real Core JAR.  The main TOML has 200
   mandatory Core rows: 10 bodies x 10 holes x 2 modification declarations.
3. `bundle/stages.py:stage_sieve` invokes `constraints/sieve.py` between Core
   and Reader.  The bond `rigid_policy_forbids_scale` removes exactly the 100
   contradictory scale rows.  It does not remove a physically difficult pair.
4. `bundle/stages.py:stage_reader` assembles the surviving 100 Python
   candidates and writes the Reader/Executor handoff.
5. `bundle/stages.py:stage_executor` launches the real Python Executor.  Each
   candidate calls the live SUT API handlers, writes records, and emits
   `FW_VAR=0` for valid success, collision, jam, partial passage, or declared
   exhaustion.  Only invalid infrastructure/evidence emits nonzero `FW_VAR`.
6. `bundle/stages.py:stage_analyzer` runs `Analyzer_trunk/AnalyzeKv.java` in
   formal mode.  `RepeatAggregator.filterEligible` excludes explicit nonzero
   infrastructure verdicts but retains valid negative physical observations.

The SUT itself supplies the physics.  `sieve3d/experiment.py` counts actions
and validates every move.  `sieve3d/wiggle.py:vertical_motion_margin` certifies
fixed-pose vertical translations at every transformed slab event and interval,
preventing tunnelling.  `sieve3d/passage.py` supplies direct, feedback,
lookahead, multistart, rollback/handoff, and adaptive-switch trajectories.
`sieve3d/recorder.py` and `sieve3d/server.py` provide bounded external replay
with the `sieve3d-motion/1` playback schema.

## Declared search stages and cost

The main policy is `rigid_only`; deformation, scaling, erosion, and hole edits
are forbidden.  Action cost comes from the live SUT:

| Operation | Manipulations |
| --- | ---: |
| `assign`, `reset` | 0 |
| one atomic `set_pose` changing any subset of spin/tilt/turn/dx/dy | 1 |
| `drop`, `wiggle`, accepted waypoint | 1 each |

The ordered stages are:

1. neutral: fresh scene, `assign -> drop` (cost 1, exact zero pose);
2. rotation-only, then shift-only, then atomic rotation-plus-shift (all cost 2);
3. declared multi-move descent prefixes, grouped by action ceiling;
4. only after every cheaper declared prefix fails, the complete declared
   direct/feedback/lookahead/multistart/adaptive final portfolio.

Neutral success skips every retry.  Once the shared static cost-2 tier begins,
every normalized rotation, shift, and mixed candidate is executed even when an
early family succeeds.  A successful multi-move trace records every lower
action prefix and stops at the first `status=passed, passed_pct=100.0` state.
Final planners use 48 physical response frames by default, making their
declared action ceiling strictly larger than every multi-move ceiling.

These values are never conflated:

- `solution_action_cost`, `solution_api_calls`, `solution_keyframes`;
- `search_action_cost`, `search_api_calls`, `search_attempt_count`;
- `planner_estimated_cost`, `changed_parameter_count`.

## Universe construction

Every candidate carries the required schema, body/hole geometry fingerprints,
normalized pose, action plan, parent and source provenance, fit ordering only,
measured tier, canonical signature, and user proof scope.

Angles are normalized modulo 360, tiny shifts become exact zero, Euler aliases
are reduced through the physical rotation matrix, and only symmetries verified
against the live hole polygon are applied.  No unproved body symmetry is used.
Fit/clearance orders a family but never deletes a candidate.  Mixed candidates
are the full normalized rotation x shift product.  The generator is run twice
and canonical JSON must match byte-for-byte.

The default domains are deliberately small and user-owned, not capped:

- named canonical/campaign/anchor rotation representatives, plus a documented
  local refinement around an active campaign angle;
- measured snake shifts around `dx=0.3119` and plug/triangle shifts from
  `dy=1.71` through `1.75`, plus live anchor/feature alignment;
- one general threading seed and any pair campaign/anchor seed;
- wiggle ceilings 1 and 2 generally, with the explicitly declared
  `twisted_flower -> flower_hole` sequence 1, 4, 16, 40;
- all five advertised final algorithm families within the declared small
  planner budget: `budget=declared`, two multistart poses, 48 output frames,
  four controller steps, one round/start/lookahead/retreat, eight local and
  escape evaluations, zero escape rounds, and two adaptive handoffs.  The SUT
  regression proves this mode does not silently inflate those ceilings.

Each universe publishes raw/normalized cardinalities and maximum attempts,
actions, records, and planner work before execution.  There is no framework
candidate ceiling, downsampling, pairwise reduction, or covering-array
fallback.

## Evidence layout

For run ID `RUN`, evidence is stored under:

```text
all_pairs_evidence/RUN/
  pre_execution_resource_plan.json
  planned_universes/<body>--<hole>.json
  pairs/<body>--<hole>/
    universe.json
    attempts/*.json
    records/*.rec
    records/*.json
    proof.json
  matrix.json
  matrix.csv
  per_body.json
  attempts.kv
  pair_results.kv
```

Every executed attempt uses a fresh harness and has request/response summaries,
exact final state, collision evidence, action/API/keyframe counts, final scene
fingerprint, record and metadata checksums, response-frame count, and an
infrastructure-validity verdict.  Higher candidates have an explicit skip
reason.  The independent verifier recomputes execution order, exact success,
tier exhaustion, argmin selection, checksums, and exhaustion without trusting
the runner's certificate booleans.

## Local commands

Set the checkout roots once for the command blocks below:

```bash
export BUNDLE_ROOT="<path-to-bundle-checkout>"
export BUNDLE_SUT_ROOT="<path-to-sut-checkouts>"
```

Focused tests:

```bash
cd "$BUNDLE_ROOT/generator_trunk/combinatorial_tests"
python3 -m unittest test_staged_passage_search -v
python3 -m unittest \
  sieve3d_max_passage.equivalence_size_first.test_max_passage_proof -v
python3 test_nonmax_spec_contracts.py
```

Plan one pair without physical attempts:

```bash
python3 sieve3d_max_passage/equivalence_size_first/staged_passage_search.py \
  --body snake --hole eye_snake --run-id snake-plan --universe-only
```

Execute one pair or all 100 pairs (resume is on by default):

```bash
python3 sieve3d_max_passage/equivalence_size_first/staged_passage_search.py \
  --body snake --hole eye_snake --run-id snake-proof

python3 sieve3d_max_passage/equivalence_size_first/staged_passage_search.py \
  --all --run-id all-pairs-20260712 --workers 1 --pair-workers 6
```

Verify a persisted pair independently:

```bash
python3 sieve3d_max_passage/equivalence_size_first/staged_passage_search.py \
  --verify all_pairs_evidence/RUN/pairs/snake--eye_snake/proof.json
```

## Clean Bundle and formal Analyzer

Use a new database and run ID.  `--sieve` is mandatory for the 200 -> 100 legal
classification:

```bash
cd "$BUNDLE_ROOT/generator_trunk"
export SIEVE3D_SEARCH_RUN_ID=all-pairs-bundle-20260712
export SIEVE3D_STAGED_EVIDENCE_ROOT="$PWD/combinatorial_tests/sieve3d_max_passage/equivalence_size_first/all_pairs_evidence"
python3 bundle_run.py combinatorial_tests/sieve3d_max_passage/equivalence_size_first \
  --db sieve3d_all_pairs_20260712 \
  --sieve \
  --execution-policy-profile trusted-local \
  --candidate-origin reviewed-checked-in \
  --acknowledge-trusted-local 'reviewed checked-in sieve3d equivalence fixture' \
  --analyzer 'full_pass:max,passed_volume_pct:max,solution_actions:min,solution_keyframes:min,changed_parameter_count:min,worst_clearance:max,search_attempts:min' \
  --analysis-mode formal \
  --run-id sieve3d-all-pairs-20260712
```

The formal corpus count is the 100 Reader-emitted pair candidates.  Failed
geometry remains eligible with `FW_VAR=0`; missing records, exceptions, broken
schemas, and invalid certificates use `FW_VAR=6` and are excluded.

### Retained verified run (2026-07-14)

The retained matrix is `all_pairs_evidence/all-pairs-20260712-v5`: all 100
pairs occur exactly once, with 38 exact passes, 62 declared-space exhaustions,
3,763 attempts, and zero infrastructure or provenance failures.  Both the
3,763-row attempt corpus and the 100-row pair corpus pass formal Analyzer
provenance checks with zero issues.

The clean Bundle run is
`bundle_evidence/runs/sieve3d-all-pairs-bundle-20260714-v5-clean`.  Its exact
stage counts are Core 200, mandatory-sieve removal 100, Reader 100, Executor
100 processed / 100 valid / 0 failed, Results DB 100, and formal Analyzer 100
input rows with `provenance_ok=true`.  The complete machine-readable summary is
`verification_report_20260714.json`.

## GUI replay

Start the SUT on a free port:

```bash
cd "$BUNDLE_SUT_ROOT/3Dprofile-VS-2Dsieve"
python3 main.py --port 8642 --no-browser
```

Open `http://127.0.0.1:8642`, choose **File**, select the exact `.rec` named by
an attempt, then press **Replay**.  The GUI uploads and validates the record,
restores its initial scene, reruns API calls, and plays any recorded planner
frames.  API-call count and motion-frame count are separate.  A record with no
motion clip remains truthfully snapshot/action-only; it is never described as
an animation.  Browser acceptance samples body Z, pose, nonblank canvas pixels,
canvas hashes, counters, and the final `status/passed_pct` over time.

The retained automated acceptance uses the same hidden file input and replay
handler as the visible **File** button:

```bash
cd "$BUNDLE_ROOT/generator_trunk/combinatorial_tests/sieve3d_max_passage/equivalence_size_first"
python3 browser_replay_acceptance.py \
  --record /absolute/path/to/selected-planner.rec \
  --output-dir branch_evidence/browser-replay \
  --expected-body snake --require-motion-frames
```

The report is successful only if Firefox observes a running replay, a clean
completion toast, positive API and motion-frame counts, changing body/animation
Z, changing canvas hashes, nonblank rendering, a screenshot, and the exact
final experiment status.
