# Run report — 01_order_record_clean

- spec: `llm_selfposed_bundle_tasks/01_order_record_clean/scenario.toml`  sha256 `f380747a975615c7...`
- category: order-sensitive pipeline  | pattern: usecases/etl_pipeline
- plan: final=24 mode=EXACT run_class=S
- run_id: `llm-selfposed-01-order-001`  db: `llm_selfposed_01_order`  sieve: False
- candidates executed: 24
- verdict distribution: 9x PASS (clean, deduped, policy-consistent), 15x duplicate id survived (dedupe ran before normalize)
- formal Pareto front: 3 non-dominated (PASS on front: 0/3; provenance_ok)
- Pareto note: the formal front is over ALL executed candidates; DOMAIN_FAIL members are findings, not deployable — pick the best PASS candidate to deploy
- evidence: run.json, state.json, executor-summary.json, metrics.kv, provenance.json
- PASS exemplar: `app=record_clean order=normalize>nullfix>dedup nullpolicy=keep dedup=by_id rows_out=3 dup_id=0 null_leak=1 FW_VAR=0`
- DOMAIN_FAIL exemplar: `app=record_clean order=nullfix>dedup>normalize nullpolicy=drop dedup=by_email rows_out=4 dup_id=1 null_leak=0 FW_VAR=2`
