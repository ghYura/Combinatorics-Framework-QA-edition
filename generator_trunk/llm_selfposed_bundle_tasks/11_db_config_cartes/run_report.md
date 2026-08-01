# Run report — 11_db_config_cartes

- spec: `llm_selfposed_bundle_tasks/11_db_config_cartes/scenario.toml`  sha256 `7c6da133027de97a...`
- category: DB-config tuning / FW_Cartes workload matrix  | pattern: database config workload matrix
- plan: final=18 mode=BOUNDED run_class=S
- run_id: `llm-selfposed-11-db-cartes-001`  db: `llm_selfposed_11_db_cartes`  sieve: False
- candidates executed: 18
- verdict distribution: 12x PASS (config/workload/data-size combination accepted), 2x analytics workload under-provisioned: work_mem below 64 MB, 4x OLTP workload under-provisioned: pool_size below 32
- formal Pareto front: 3 non-dominated (PASS on front: 1/3; provenance_ok)
- Pareto note: the formal front is over ALL executed candidates; DOMAIN_FAIL members are findings, not deployable — pick the best PASS candidate to deploy
- evidence: run.json, state.json, executor-summary.json, metrics.kv, provenance.json
- PASS exemplar: `app=db_config config=balanced workload=analytics data_size=large p95_ms=130.41 cost_units=8.40 stability_score=9 FW_VAR=0`
- DOMAIN_FAIL exemplar: `app=db_config config=analytics_heavy workload=oltp data_size=small p95_ms=1.00 cost_units=9.50 stability_score=6 FW_VAR=3`
- DOMAIN_FAIL exemplar: `app=db_config config=low_mem workload=analytics data_size=small p95_ms=95.45 cost_units=2.25 stability_score=7 FW_VAR=2`
