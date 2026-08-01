# Run report — 10_feature_flag_interaction

- spec: `llm_selfposed_bundle_tasks/10_feature_flag_interaction/scenario.toml`  sha256 `6ca57ff665ceffa6...`
- category: feature-flag interaction (FW_Subsets)  | pattern: secure_pipeline FW_Subsets features
- plan: final=32 mode=EXACT run_class=S
- run_id: `llm-selfposed-10-flags-001`  db: `llm_selfposed_10_flags`  sieve: False
- candidates executed: 32
- verdict distribution: 21x PASS (safe flag set), 8x feature dependency violated (experimental_ui without new_router), 3x canary resource conflict (audit + cache in canary)
- formal Pareto front: 5 non-dominated (PASS on front: 5/5; provenance_ok)
- Pareto note: the formal front is over ALL executed candidates; DOMAIN_FAIL members are findings, not deployable — pick the best PASS candidate to deploy
- evidence: run.json, state.json, executor-summary.json, metrics.kv, provenance.json
- PASS exemplar: `app=feature_flags rollout=canary flags=new_router enabled_flags=1 risk_score=0 dep_bad=0 canary_conflict=0 FW_VAR=0`
- DOMAIN_FAIL exemplar: `app=feature_flags rollout=ga flags=experimental_ui enabled_flags=1 risk_score=1 dep_bad=1 canary_conflict=0 FW_VAR=2`
- DOMAIN_FAIL exemplar: `app=feature_flags rollout=canary flags=audit+cache+new_router enabled_flags=3 risk_score=2 dep_bad=0 canary_conflict=1 FW_VAR=3`
