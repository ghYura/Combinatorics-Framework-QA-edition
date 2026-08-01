# Run report — 08_ci_release_matrix

- spec: `llm_selfposed_bundle_tasks/08_ci_release_matrix/scenario.toml`  sha256 `eec83225ff3d5415...`
- category: CI/CD release matrix  | pattern: release-engineering safety matrix
- plan: final=108 mode=BOUNDED run_class=S
- run_id: `llm-selfposed-08-ci-release-001`  db: `llm_selfposed_08_ci_release`  sieve: True
- candidates executed: 96
- verdict distribution: 78x PASS (release plan accepted), 12x breaking migration released with smoke tests only, 6x canary with enabled feature flag released with smoke tests only
- formal Pareto front: 10 non-dominated (PASS on front: 9/10; provenance_ok)
- Pareto note: the formal front is over ALL executed candidates; DOMAIN_FAIL members are findings, not deployable — pick the best PASS candidate to deploy
- evidence: run.json, state.json, executor-summary.json, metrics.kv, provenance.json
- PASS exemplar: `app=ci_release service=frontend strategy=blue_green migration=none tests=full flag=on risk_score=10 duration_min=50 rollback_score=8 FW_VAR=0`
- DOMAIN_FAIL exemplar: `app=ci_release service=frontend strategy=blue_green migration=breaking tests=smoke flag=off risk_score=21 duration_min=46 rollback_score=4 FW_VAR=2`
- DOMAIN_FAIL exemplar: `app=ci_release service=api strategy=canary migration=none tests=smoke flag=on risk_score=18 duration_min=24 rollback_score=7 FW_VAR=3`
