# Run report — 07_constraint_arity

- spec: `llm_selfposed_bundle_tasks/07_constraint_arity/scenario.toml`  sha256 `338fca11842530f4...`
- category: constraint arity (binary vs ternary)  | pattern: constraints/diff_fuzz_when
- plan: final=36 mode=BOUNDED run_class=S
- run_id: `llm-selfposed-07-arity-001`  db: `llm_selfposed_07_arity`  sieve: True
- candidates executed: 30
- verdict distribution: 28x PASS (valid deployment), 2x ternary bond violated (enterprise tier in a restricted region with a single replica) - caught by the oracle because sieve v1 cannot express a 3-sheet rule
- formal Pareto front: 10 non-dominated (PASS on front: 10/10; provenance_ok)
- Pareto note: the formal front is over ALL executed candidates; DOMAIN_FAIL members are findings, not deployable — pick the best PASS candidate to deploy
- evidence: run.json, state.json, executor-summary.json, metrics.kv, provenance.json
- PASS exemplar: `app=constraint_arity region=eu tier=pro replicas=1 ternary_bad=0 FW_VAR=0`
- DOMAIN_FAIL exemplar: `app=constraint_arity region=eu tier=ent replicas=1 ternary_bad=1 FW_VAR=2`
