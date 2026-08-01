# Run report — 09_api_compat_matrix

- spec: `llm_selfposed_bundle_tasks/09_api_compat_matrix/scenario.toml`  sha256 `a42969c8e824c6ec...`
- category: API compatibility matrix  | pattern: API/client/payload contract matrix
- plan: final=81 mode=BOUNDED run_class=S
- run_id: `llm-selfposed-09-api-compat-001`  db: `llm_selfposed_09_api_compat`  sieve: True
- candidates executed: 72
- verdict distribution: 60x PASS (compatible API/client/auth/payload combination), 9x v1 API cannot accept bulk_json payloads, 3x beta SDK JWT path requires modern/bulk payload claims
- formal Pareto front: 27 non-dominated (PASS on front: 25/27; provenance_ok)
- Pareto note: the formal front is over ALL executed candidates; DOMAIN_FAIL members are findings, not deployable — pick the best PASS candidate to deploy
- evidence: run.json, state.json, executor-summary.json, metrics.kv, provenance.json
- PASS exemplar: `app=api_compat api_version=v1 client=current_sdk auth=api_key payload=legacy_json compat_score=97 latency_ms=35 migration_effort=4 FW_VAR=0`
- DOMAIN_FAIL exemplar: `app=api_compat api_version=v1 client=current_sdk auth=api_key payload=bulk_json compat_score=104 latency_ms=57 migration_effort=9 FW_VAR=2`
- DOMAIN_FAIL exemplar: `app=api_compat api_version=v1 client=beta_sdk auth=jwt payload=legacy_json compat_score=106 latency_ms=46 migration_effort=11 FW_VAR=3`
