# Run report — 14_control_pair_combi2

- spec: `llm_selfposed_bundle_tasks/14_control_pair_combi2/scenario.toml`  sha256 `783e2c14f827a1ec...`
- category: security control pair selection (FW_Combi(2))  | pattern: security control choose-k pair
- plan: final=12 mode=EXACT run_class=S
- run_id: `llm-selfposed-14-combi2-001`  db: `llm_selfposed_14_combi2`  sieve: False
- candidates executed: 12
- verdict distribution: 8x PASS (safe control pair), 3x admin traffic control pair is missing WAF, 1x public traffic control pair has excessive user friction
- formal Pareto front: 2 non-dominated (PASS on front: 1/2; provenance_ok)
- Pareto note: the formal front is over ALL executed candidates; DOMAIN_FAIL members are findings, not deployable — pick the best PASS candidate to deploy
- evidence: run.json, state.json, executor-summary.json, metrics.kv, provenance.json
- PASS exemplar: `app=control_pair traffic=public_api controls=review_queue+waf coverage_score=70 friction_score=7 cost_units=7 FW_VAR=0`
- DOMAIN_FAIL exemplar: `app=control_pair traffic=admin_api controls=captcha+review_queue coverage_score=66 friction_score=9 cost_units=5 FW_VAR=2`
- DOMAIN_FAIL exemplar: `app=control_pair traffic=public_api controls=captcha+review_queue coverage_score=55 friction_score=9 cost_units=5 FW_VAR=3`
