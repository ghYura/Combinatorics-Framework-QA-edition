# Cold-Start Task: Adaptive Combinatorial Passage for Every Body and Hole

You are resuming a high-rigor implementation and verification task. Work through inspection, code changes, tests, persistent evidence, Bundle/Analyzer execution, and real GUI replay. Do not stop at a proposal.

## Mission

Build a deterministic multi-stage combinatorial search for **every configured 3D body against every configured 2D sieve hole**. For each fixed pair, try:

1. true neutral/simple drop;
2. rotation variants then drop;
3. lateral position-shift variants then drop;
4. mixed rotation plus shift variants then drop;
5. user-declared multi-move descent variants;
6. only as the last chance, adaptive screw/thread-like trajectories using all declared rigid transforms and permitted moves.

Find an exact full passage with minimum measured manipulation-action cost inside the complete user-declared candidate universe realized for the run. If nothing passes, produce a declared-space-exhaustion certificate. Never claim mathematical impossibility or a global optimum over an unmodeled continuous motion space.

The proof must show that the repository's combinatorial machinery is useful: it preserves the neutral baseline, explores meaningful retries only after failure, finds cheaper successful alternatives, selects a minimum independently across the complete legal space chosen by the user, and produces evidence another person can replay and audit.

## Repositories

Set portable checkout roots once:

```bash
export BUNDLE_ROOT="<path-to-bundle-checkout>"
export BUNDLE_SUT_ROOT="<path-to-sut-checkouts>"
```

Current task:

```text
$BUNDLE_ROOT/generator_trunk/combinatorial_tests
```

External SUT:

```text
$BUNDLE_SUT_ROOT/3Dprofile-VS-2Dsieve
```

Bundle generator/executor, one directory above:

```text
$BUNDLE_ROOT/generator_trunk
```

Analyzer ecosystem, two-level context:

```text
$BUNDLE_ROOT/Analyzer_trunk
```

Inspect all four locations first. Trace the actual Core -> Reader -> Executor -> Analyzer path with source references. Do not revert unrelated dirty changes. The SUT may not be a Git repository. Keep final evidence under the task workspace, not only in `/tmp`. Remove accidental `.orig` and `.rej` files.

## Inherited Verified Foundations

Preserve and regression-test these prior fixes:

- continuous vertical collision certification, preventing tunnelling;
- invalid-geometry repair;
- passage ranking by full passage, percentage, cost, and clearance;
- Hungarian body-hole assignment;
- model-integrity checks for scale, disconnection, duplicate names, delimiters, and cache certainty;
- Analyzer filtering through explicit `FW_VAR` infrastructure validity;
- external API recording of `/api/v1/passage`, motion routes, successful responses, and frames;
- synchronized nested async replay;
- replay payload `result.playback` with schema `sieve3d-motion/1`;
- GUI replay animation and separate API-call/motion-frame counts;
- 4 MiB, 10,000-step, and 600-motion-frame upload/replay bounds;
- truthful snapshot-only replay behavior;
- browser evidence that body Z and nonblank canvas pixels change during rich replay.

Historical results were SUT 86/86, combinatorial/parent 27/27, and Bundle 2 generated/2 executed/2 passed with zero provenance issues. Rerun current tests; do not rely on those counts.

Prior persistent evidence:

```text
sieve3d_max_passage/equivalence_size_first/replay_evidence_20260712/proof.json
sieve3d_max_passage/equivalence_size_first/replay_evidence_20260712/sieve3d_rec_results/sieve3d_max_passage_snake_eye_snake_direct_baseline_153859_1783872286565.rec
sieve3d_max_passage/equivalence_size_first/replay_evidence_20260712/sieve3d_rec_results/sieve3d_max_passage_snake_eye_snake_feedback_portfolio_153859_1783872299941.rec
```

A durable GUI-tested copy existed at:

```text
$BUNDLE_SUT_ROOT/3Dprofile-VS-2Dsieve/records/rich-visible-proof.rec
```

That old snake feedback proof is useful replay evidence but **not a minimum-action result**. Fresh measurement found `snake -> eye_snake` reaches 100% with a translation-only retry around `dx=0.3119, dy=0`. The new search must discover and prefer that static solution.

## First Actions After Cold Start

1. Read this entire file.
2. Inventory the live worktree, tests, artifacts, and processes.
3. Inspect SUT geometry, fit, experiment, action-cost, planner, recorder, replay, and GUI code.
4. Inspect search code, TOML specs, proof scripts, tests, and READMEs.
5. Inspect Bundle and Analyzer implementations one and two levels up.
6. Run focused baselines, then publish and maintain a short implementation plan.
7. Treat old process IDs, servers, and `/tmp` databases as disposable.

Likely primary files:

```text
sieve3d_complex_bodies/complex_cases.py
sieve3d_max_passage/equivalence_size_first/max_passage_search.py
sieve3d_max_passage/equivalence_size_first/sieve3d_max_passage.toml
sieve3d_max_passage/equivalence_size_first/test_max_passage_proof.py
sieve3d_max_passage/equivalence_size_first/README.md
../test_sieve3d_max_passage_usecase.py
```

## Known Gaps

At the last audit:

- `cc.BODIES` had 10 bodies, but `BODY_CASES` exposed 5 and the main TOML only 4.
- Bodies were `wave_bar`, `flower`, `twisted_flower`, `hook120`, `snake`, `helix_bar`, `croissant`, `pierced_cube`, `half_pipe`, and `plug`.
- Holes were `wave_slot`, `flower_hole`, `round_small`, `round_generous`, `square_snug`, `square_9`, `arch`, `eye_snake`, `triangle`, and `ring_gap`.
- The live matrix should currently be 100 pairs, but derive it from registries.
- `_run_direct` performed `assign -> set_pose(best) -> drop`; it was not neutral.
- `rank_holes()` collapsed the pose universe to one best-clearance pose.
- Movement strategies reused that one pose.
- `TARGET_PCT` accepted 95% or 99%.
- The snake portfolio minimized planner-estimated cost, not physical actions.
- Failed discovery attempts were absent from complete proof evidence.
- Only winners were recorded, preventing independent tier-exhaustion checks.

Fix behavior, not only assertions.

## Exact Full-Passage Oracle

Recompute success independently:

```python
state["status"] == "passed" and float(state["passed_pct"]) == 100.0
```

Use a tiny documented serialization tolerance only if unavoidable. Reject:

- `crossing` at 100%;
- `passed` at 99.99%;
- `jammed` at any percentage;
- planner `success=True` with partial physical passage.

Require continuous swept collision certification, not endpoint-only checks.

## SUT Cost Semantics

Audit the live code. Previously:

```text
assign:   0 manipulations
reset:    0 manipulations
set_pose: 1 manipulation for any atomic subset of spin/tilt/turn/dx/dy
drop:     1 manipulation
wiggle:   1 manipulation
```

Therefore:

- neutral `assign -> drop` costs 1;
- `assign -> set_pose -> drop` costs 2;
- rotation-only, shift-only, and atomic rotation-plus-shift share the same cost tier;
- semantic family order is still required, but the entire shared cost tier must be exhausted before selection;
- combined pose costs 3 only if rotation and shift are separate API actions;
- cumulative discovery cost differs from the clean winning-plan cost.

Keep these metrics separate:

```text
solution_action_cost
solution_api_calls
solution_keyframes
search_action_cost
search_api_calls
search_attempt_count
planner_estimated_cost
changed_parameter_count
```

Planner estimates, HTTP calls, changed dimensions, frames, and manipulations are not interchangeable.

## Candidate and Attempt Schemas

Each declared candidate must include:

```text
schema_version, candidate_id
body, hole
body_geometry_fingerprint, hole_geometry_fingerprint
stage, semantic_family, measured_action_tier
parent_candidate_id, provenance_sources
pose: spin, tilt, turn, dx, dy
action_plan, dynamic_options
canonical_signature, fit_rank, estimated_clearance
solution_action_cost, user_declared_execution_scope
```

Each attempt must additionally include:

```text
attempt_index, candidate_id, deterministic run identity
request/response summary
status, passed_pct, independently computed full_pass
clearance and collision evidence
measured action/API/keyframe counts
unexpected_exception and infrastructure validity
record path(s), metadata path, checksums
response-frame count, final scene fingerprint
```

The proof manifest must identify the complete universe, exact executed prefix, independent selection, tier exhaustion, skipped candidates/reasons, record files, and Bundle/Analyzer provenance. Do not rely on a self-reported `minimal=True`.

## Combinatorial Rules

Use the repository's real abstractions such as `FW_Combi`, `FW_Subsets`, permutations, and optional factors where appropriate. Do not hide an ad hoc nested loop behind combinatorial terminology.

For every factor:

1. define its domain and physical meaning;
2. calculate raw Cartesian cardinality;
3. state symmetry/equivalence reductions;
4. calculate normalized unique cardinality;
5. reject no-op factors;
6. retain derivation provenance;
7. define deterministic ordering/ties;
8. calculate and expose execution/resource implications before execution without imposing a hidden cap.

Normalize angles modulo 360, near-zero offsets, numerical tolerances, and equivalent action sequences. Apply real body/hole symmetries without losing scale. Generate the universe twice and require canonical JSON equality.

Fit/clearance may order candidates inside a tier but must not silently remove proof candidates. Any pruning must be deterministic, independently checkable, recorded, and tested against false negatives.

### Bundle's Own Sieve and User-Owned Cardinality

Do not confuse the two sieves in this task:

- the **Bundle sieve** is the declarative constraint/bond layer between Core and Reader;
- the **SUT sieve** is the physical plate containing 2D holes through which a 3D body moves.

The Bundle architecture is mechanics x bonds x meaning. Core verbs generate the complete modeled space, the Bundle sieve removes combinations that violate declared forbid/require relations, and the Executor's `FW_VAR` oracle judges the surviving candidates. Inspect `constraints/sieve.py`, including n-ary bonds, conditions, mappings, positional gates, predicates, and deferred optional-sheet enforcement. Use this sieve to remove semantically illegal or contradictory body/pose/action combinations before expensive SUT execution, with exact scanned/removed/retained provenance. Do not use it as an arbitrary sampling mechanism, and do not treat a SUT collision as a Bundle-sieve infrastructure failure.

The Framework must not impose pairwise coverage, a hard candidate ceiling, silent downsampling, or an automatic covering-array fallback. `FW_Combi(2)` is correct only when the modeled freedom is genuinely "choose two," not because the generated space is large. The user owns the domains and verbs; exact cardinality follows from that model.

Manage large spaces through smart authoring before execution: choose the verb matching the real freedom, factor optional actions, use higher-order joins/groups where structurally correct, declare Bundle-sieve bonds for truly invalid combinations, apply only mathematically valid symmetries/equivalences, stage dependencies explicitly, and use the Framework's persistence, sharding, resume, isolation, and parallel execution. Always show the user exact counts and resource implications. If the user declares the full legal product, preserve it; changing it to pairwise/n-wise or another covering design requires an explicit user-authored experiment and a separately stated proof scope.

For this 3D task, the Bundle sieve may remove invalid/no-op experiment definitions. It must not pre-delete physically difficult candidates whose passage outcome is exactly what the external SUT must determine. Mandatory constraints run after Core and before Reader; constraints involving `FW_Optional` values may be deferred to Reader assembly. Verify both paths.

## Required Search Stages

### Stage 0: Neutral Drop

For every live body-hole pair:

```text
fresh scene -> assign(body, hole) -> drop
```

No `set_pose`, no hidden anchor shift, and no retry if exact full passage succeeds. More expensive declared candidates remain in the universe but are marked `skipped_due_to_cost_dominance`.

### Stage 1A: Rotation Then Drop

After neutral failure, enumerate symmetry-reduced rotations with `dx=dy=0`. Draw from canonical poses, campaign poses, audited `_candidate_poses()`, anchor orientations, principal axes, symmetry representatives, user-declared angular samples, and deterministic local refinements.

```text
fresh scene -> assign -> set_pose(rotation only) -> drop
```

### Stage 1B: Shift Then Drop

Enumerate `dx/dy` with all angles zero. Draw from centroid/feature alignment, anchor shifts, clearance-derived offsets, user-declared grids/rings, and deterministic local refinement.

```text
fresh scene -> assign -> set_pose(shift only) -> drop
```

### Stage 1C: Rotation Plus Shift Then Drop

Combine the full user-declared, symmetry-reduced rotation and shift domains. Include anchor/campaign combined poses and five-dimensional refinements. Deduplicate only genuinely equivalent normalized poses across families. Never replace the product with pairwise/n-wise coverage merely because it is large; such a design is valid only when the user explicitly declares that different experiment and accepts its narrower proof scope.

```text
fresh scene -> assign -> one atomic set_pose(rotation + shift) -> drop
```

User-required semantic order is neutral, rotation, shift, then mixed. However, 1A/1B/1C currently share the same two-action tier. Once this tier begins, exhaust all of its normalized candidates before claiming a winner. Family rank may break otherwise equal ties, but cannot pretend to be cheaper.

### Stage 2: User-Declared Multi-Move Descent

Only if the static tier has no full pass, enumerate exact action plans from the user's declared sequence domains, such as:

- incremental descent;
- rotate/translate at selected height bands;
- nudge, jiggle, or wiggle;
- retreat and retry;
- alternate pose and descent;
- collision-aware local correction;
- user-declared monotone/backtracking sequences.

Treat sequence length and contents as factors. A plan with “up to 20 moves” cannot prove a seven-step minimum unless all lower measured-action budgets were exhausted. The task's declared depth is a user-authored proof scope, not a Framework ceiling. Use SUT physics/planner primitives rather than a second hand-written physics engine.

### Final Stage: Screw/Thread-Like Search

Only after all declared cheaper candidates fail, exercise live equivalents of:

- direct-drop planner;
- feedback thread;
- lookahead thread;
- multistart thread;
- adaptive-switch thread;
- depth-dependent rotation/translation;
- PID/collision feedback;
- rollback, retreat, and planner handoff;
- user-declared algorithm queues and parameter schedules.

The trajectory may change direction, step size, pose, and planner mode only inside declared domains/budgets. Record every adaptive decision and trigger so it can be reproduced.

Default to `rigid_only`. “All possible modifications and moves” must not silently reshape the body or hole. Add an explicit policy factor:

```text
rigid_only | explicitly_allowed_physical_modification
```

Keep the main proof rigid. If deformation/scaling/erosion is genuinely allowed, make it a separate experiment with explicit conservation and validity rules.

## Escalation, Selection, and Declared-Space Exhaustion

1. Execute neutral first for every fixed pair.
2. Enter a higher action tier only if no lower tier passes.
3. Once a tier has a full pass, finish every required candidate in that same tier.
4. Select independently among full candidates in the first successful tier.
5. Skip strictly higher tiers and record cost dominance.
6. If all candidates fail, run the final stage and report `declared_space_exhaustion`, never universal impossibility.
7. Collision/jam/partial passage is valid negative evidence. Unexpected exceptions, bad geometry/contracts, or missing evidence invalidate the proof.

Default lexicographic winner:

```text
1. exact full pass
2. minimum measured solution manipulations
3. minimum solution keyframes
4. minimum changed pose-parameter count
5. maximum independently measured worst clearance
6. minimum deterministic candidate_id
```

Report search expense separately.

## Minimality Certificate

For every pair independently recompute:

```text
direct_attempted_first
neutral_pose_was_exact
earlier_success_absent
retries_only_after_failure
candidate_ids_follow_declared_policy
all_lower_cost_tiers_exhausted
first_successful_tier_fully_exhausted
selected_is_independent_argmin
selected_is_exact_full_pass
no_attempt_after_tier_completion
higher_tiers_skipped_only_by_cost_dominance
or exhausted_all_declared_stages
```

Add tamper tests for a skipped/reordered candidate, hidden earlier success, false full flag, higher-tier winner, omitted universe member, altered cost, and missing record.

Correct claim:

> Minimum successful measured-action tier within the complete user-declared candidate universe realized for this fixed geometry and policy.

Never claim globally shortest continuous path or mathematical impossibility.

## Required Matrix and Reports

Produce one row per live body-hole pair:

```text
body, hole, geometry fingerprints
neutral result
first successful family/stage
minimum solution actions
selected pose/trajectory
status, passed_pct, clearance
search attempts/actions/runtime
record/metadata paths and checksums
certificate verdict
declared-space-exhaustion reason
```

Aggregate per body: neutral holes, rotation/shift/mixed holes, dynamic holes, exhausted pairs, best hole/solution, raw/reduced candidate counts, and provenance issues.

Keep fixed-pair retry proofs separate from “choose the easiest hole”. A generous hole must not trivialize a difficult-pair test.

## Empirical Regression Anchors

Remeasure, then preserve if still valid:

```text
flower -> flower_hole:
  neutral 100%, one action, no retry

croissant -> arch:
  neutral 100%, one action, no retry

pierced_cube -> square_snug:
  neutral 100%, one action, no retry

half_pipe -> round_generous:
  neutral 100%, one action, no retry

plug -> square_snug:
  neutral 100%, one action, no retry

wave_bar -> wave_slot:
  neutral 0%
  rotation near spin=270, tilt=90, turn=90 reaches 100%

plug -> triangle:
  neutral 0%
  tested rotation-only and shift-only do not fully pass
  combined near spin=90, tilt=90, turn=180, dx=0, dy=1.71..1.75 reaches 100%

snake -> eye_snake:
  neutral about 0.14%
  shift near dx=0.3119, dy=0 reaches 100%, clearance about 0.1859
  this must outrank the old feedback-thread result
```

Prior probes suggested `twisted_flower`, `hook120`, and `helix_bar` need harder search for their campaign holes. Reverify; use them to exercise dynamic or exhausted branches.

Run isolated attempts in fresh harnesses for clean action counts. A separate recorded campaign may concatenate neutral failure and retries for visible GUI escalation, but its manifest must map every segment to isolated evidence. Distinguish cumulative search cost from fresh winning-plan cost.

## External API Records and GUI Reproduction

Every conclusion must be externally reproducible through the existing recorder API:

- record before neutral;
- retain failed predecessors and the selected result;
- split oversized records deterministically by pair/stage and provide an ordered manifest;
- persist `.rec`, metadata, checksums, and proof JSON;
- capture planner response frames;
- report API calls separately from motion frames;
- never present a one-step snapshot as dynamic proof;
- keep valid jams/partial results Analyzer-eligible with `FW_VAR=0`;
- reserve nonzero infrastructure codes for invalid execution.

Start the GUI server, using a free port:

```bash
cd "$BUNDLE_SUT_ROOT/3Dprofile-VS-2Dsieve"
python3 main.py --port 8642 --no-browser
```

Use File -> record file -> Replay. Automate a real browser for dynamic records and sample over time:

```text
scene/body pose and S.bodyZ
nonblank canvas pixels
canvas hashes at multiple timestamps
API-call and motion-frame counters
final status and passed_pct
```

Require distinct poses/hashes for multi-frame trajectories, nonblank correctly framed rendering, no incoherent overlap, and final state matching the manifest. Do not hard-code the old 28-call/24-frame counts; those belonged to one old trace.

## Bundle and Analyzer Proof

Show this is a real Bundle combinatorial task:

- expose body, hole, family, pose/action factors, and policy in provenance;
- exercise Bundle's own Core -> constraint-sieve -> Reader ordering and prove its legal-candidate classification independently;
- report exact pre-sieve, removed, retained, optional-expanded, emitted, and executed counts;
- prove no full legal product was silently reduced to pairwise/n-wise coverage or capped by the Framework;
- independently match generated cardinality;
- verify Reader parses intended data;
- verify Executor calls the real external SUT;
- preserve valid success, jam, collision, and partial observations;
- reject only infrastructure-invalid results;
- use formal analysis mode where supported;
- prove no survivor bias from filtering failed predecessors;
- keep coverage diagnostics separate from optimization objectives.

Conceptual goals, translated to live syntax:

```text
full_pass:max (winner gate)
passed_volume_pct:max
solution_actions:min
solution_keyframes:min
changed_parameter_count:min
worst_clearance:max
search_attempts:min (search efficiency, not path cost)
```

Run a clean Bundle lifecycle with a new database and run ID. Inspect current help/schema before adapting this pattern:

```bash
cd "$BUNDLE_ROOT/generator_trunk"
python3 bundle_run.py <spec-dir> \
  --db <clean-db> \
  --execution-policy-profile generated-default \
  --analyzer '<valid live goals>' \
  --analysis-mode formal \
  --run-id <unique-id>
```

## Required Tests

Implement at least:

1. all live bodies x all live holes are covered exactly;
2. deterministic unique universe, symmetry/dedup, raw/reduced cardinalities, and no-op rejection;
3. neutral is sole first candidate and has no `set_pose`;
4. direct success stops retries; failure escalates conditionally;
5. lower tiers and the complete first successful tier are exhausted;
6. exact 100%/status oracle rejects partial and planner-only success;
7. atomic versus sequential pose action accounting is correct;
8. independent verifier rejects all tampered certificates;
9. real neutral, rotation, shift, mixed, dynamic, and exhausted branches;
10. pruning cannot hide a known passing candidate;
11. continuous collision/tunnelling regressions;
12. each attempt maps to complete record/metadata evidence;
13. selected replay ends at `passed, 100%`, failures replay honestly, and dynamic GUI motion is visible;
14. Bundle pre-sieve, removed, retained, optional-expanded, emitted, and executed counts reconcile exactly;
15. Bundle sieve independently classifies legal/illegal n-ary and deferred-optional candidates without filtering physically difficult SUT cases;
16. the full legal user-declared product is not silently capped or reduced to pairwise/n-wise coverage;
17. Analyzer independent argmin matches;
18. valid failed geometry remains eligible data while infrastructure errors do not.

Avoid tests that merely call the implementation's selector and assert its own booleans.

## Verification

Inspect live filenames, then run at least:

```bash
cd "$BUNDLE_SUT_ROOT/3Dprofile-VS-2Dsieve"
python3 -m unittest discover -s tests -v
node --check web/app.js
python3 -m py_compile <changed Python files>
```

Run new focused task tests plus live equivalents of:

```text
test_nonmax_spec_contracts.py
sieve3d_max_passage/equivalence_size_first/test_max_passage_proof.py
../test_sieve3d_max_passage_usecase.py
```

Then run clean Bundle generation/execution/formal Analyzer and browser replay acceptance. Record exact commands, counts, run IDs, database/evidence paths, matrix totals, and any skips.

## Deliverables

- deterministic staged candidate generator and driver;
- exact success oracle and independent proof verifier;
- every live body and hole;
- explicit action model;
- complete matrix and per-body reports;
- persistent universe, attempts, certificates, records, checksums, and replay manifests;
- unit, integration, real-SUT, Bundle, replay, and GUI tests;
- meaningful user-declared TOML/use-case factors with exact cardinality;
- updated READMEs with construction, costs, replay steps, and proof scope;
- necessary SUT fixes with regressions;
- clean test evidence and no patch artifacts.

## Definition of Done

1. Every live pair appears once.
2. Every pair starts with true neutral drop.
3. Retries follow declared semantic order and measured tiers.
4. Only `passed` at exact 100% wins.
5. The first successful action tier is fully exhausted and independently minimized.
6. Total failures exhaust the complete user-declared universe without universal claims.
7. solution, search, API, keyframe, and planner costs remain distinct.
8. Tests cover neutral, rotation, shift, mixed, dynamic, and exhaustion.
9. Every conclusion has persistent external-API evidence.
10. Dynamic records visibly animate in the real GUI.
11. Bundle/Analyzer counts, provenance, eligibility, and winners agree independently.
12. Relevant SUT/task/parent/Bundle/replay/browser tests pass.
13. Documentation gives exact manual reproduction steps and the precise user-declared proof scope.

## Quota and Resume Discipline

The user asked to pause at a meaningful checkpoint if model/tool allowance falls below roughly 10% while waiting for a five-hour renewal. Do not abandon a half-written edit. At a checkpoint:

- leave files coherent;
- persist evidence and plan status;
- state exact passed/failed/pending work;
- leave the next command and paths;
- wait for `continue`.

After cold start or compaction, reread this file and inspect persistent state before resuming.
