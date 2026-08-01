# Run report — 12_fallback_sequence_permutr

- spec: `llm_selfposed_bundle_tasks/12_fallback_sequence_permutr/scenario.toml`  sha256 `890714e3ac04f1be...`
- category: service fallback sequence (FW_PermutR)  | pattern: service fallback repeated sequence
- plan: final=54 mode=EXACT run_class=S
- run_id: `llm-selfposed-12-permutr-002`  db: `llm_selfposed_12_permutr_v2`  sieve: False
- candidates executed: 54
- verdict distribution: 32x PASS (deployable fallback sequence), 8x critical request sequence never probes primary, 9x interactive request sequence starts with expensive primary probe, 5x fallback sequence policy violation: no diversity or latency budget exceeded
- formal Pareto front: 31 non-dominated (PASS on front: 24/31; provenance_ok)
- Pareto note: the formal front is over ALL executed candidates; DOMAIN_FAIL members are findings, not deployable — pick the best PASS candidate to deploy
- evidence: run.json, state.json, executor-summary.json, metrics.kv, provenance.json
- PASS exemplar: `app=fallback_seq request_class=interactive sequence=replica-cache-replica availability_score=67 latency_ms=34 cost_units=7 FW_VAR=0`
- DOMAIN_FAIL exemplar: `app=fallback_seq request_class=critical sequence=replica-cache-cache availability_score=36 latency_ms=26 cost_units=5 FW_VAR=2`
- DOMAIN_FAIL exemplar: `app=fallback_seq request_class=interactive sequence=replica-replica-replica availability_score=65 latency_ms=42 cost_units=9 FW_VAR=4`
- DOMAIN_FAIL exemplar: `app=fallback_seq request_class=interactive sequence=primary-cache-cache availability_score=78 latency_ms=40 cost_units=8 FW_VAR=3`
