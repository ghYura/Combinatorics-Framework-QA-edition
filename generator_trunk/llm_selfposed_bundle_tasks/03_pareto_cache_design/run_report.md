# Run report — 03_pareto_cache_design

- spec: `llm_selfposed_bundle_tasks/03_pareto_cache_design/scenario.toml`  sha256 `73ff9489870cd7ef...`
- category: design-space / Pareto  | pattern: usecases/perf_opt
- plan: final=36 mode=EXACT run_class=S
- run_id: `llm-selfposed-03-cache-001`  db: `llm_selfposed_03_cache`  sieve: False
- candidates executed: 36
- verdict distribution: 36x valid configuration (optimization selects among them)
- formal Pareto front: 9 non-dominated (PASS on front: 9/9; provenance_ok)
- Pareto note: the formal front is over ALL executed candidates; DOMAIN_FAIL members are findings, not deployable — pick the best PASS candidate to deploy
- evidence: run.json, state.json, executor-summary.json, metrics.kv, provenance.json
- PASS exemplar: `app=cache_design evict=lru size=large ttl=short prefetch=on hit_rate=0.9000 memory_mb=128.0 p99_latency_ms=10.000 FW_VAR=0`
