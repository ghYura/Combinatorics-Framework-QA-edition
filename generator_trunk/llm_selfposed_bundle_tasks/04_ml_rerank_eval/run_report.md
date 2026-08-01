# Run report — 04_ml_rerank_eval

- spec: `llm_selfposed_bundle_tasks/04_ml_rerank_eval/scenario.toml`  sha256 `605c6b8bd726b0e5...`
- category: ML/LLM outer-structure evaluation  | pattern: usecases/ml_eval
- plan: final=36 mode=EXACT run_class=S
- run_id: `llm-selfposed-04-rerank-001`  db: `llm_selfposed_04_rerank`  sieve: False
- candidates executed: 36
- verdict distribution: 34x PASS (>= quality gate), 2x below quality gate (accuracy < 0.75)
- formal Pareto front: 5 non-dominated (PASS on front: 5/5; provenance_ok)
- Pareto note: the formal front is over ALL executed candidates; DOMAIN_FAIL members are findings, not deployable — pick the best PASS candidate to deploy
- evidence: run.json, state.json, executor-summary.json, metrics.kv, provenance.json
- PASS exemplar: `app=rerank_eval prep=lowercase>stem>strip_punct chunk=128 rerank=on accuracy=0.7900 latency_ms=28.80 cost_usd=0.02304 FW_VAR=0`
- DOMAIN_FAIL exemplar: `app=rerank_eval prep=lowercase>stem>strip_punct chunk=128 rerank=off accuracy=0.7400 latency_ms=18.00 cost_usd=0.01440 FW_VAR=4`
