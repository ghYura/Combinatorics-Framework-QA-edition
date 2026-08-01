# Run report — 05_sieve_deploy_matrix

- spec: `llm_selfposed_bundle_tasks/05_sieve_deploy_matrix/scenario.toml`  sha256 `0b9ef00c74314b1c...`
- category: constraint / sieve  | pattern: constraints/diff_fuzz_when
- plan: final=36 mode=BOUNDED run_class=S
- run_id: `llm-selfposed-05-deploy-001`  db: `llm_selfposed_05_deploy`  sieve: True
- candidates executed: 30
- verdict distribution: 26x PASS (valid deployment), 4x enterprise tier under-replicated (replicas < 3)
- formal Pareto front: 10 non-dominated (PASS on front: 10/10; provenance_ok)
- Pareto note: the formal front is over ALL executed candidates; DOMAIN_FAIL members are findings, not deployable — pick the best PASS candidate to deploy
- evidence: run.json, state.json, executor-summary.json, metrics.kv, provenance.json
- PASS exemplar: `app=deploy_matrix region=eu tier=pro replicas=1 under_replicated=0 FW_VAR=0`
- DOMAIN_FAIL exemplar: `app=deploy_matrix region=eu tier=ent replicas=1 under_replicated=1 FW_VAR=2`
