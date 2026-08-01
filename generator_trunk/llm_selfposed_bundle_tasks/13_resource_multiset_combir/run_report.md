# Run report — 13_resource_multiset_combir

- spec: `llm_selfposed_bundle_tasks/13_resource_multiset_combir/scenario.toml`  sha256 `80a7913b1af55109...`
- category: resource allocation multiset (FW_CombiR)  | pattern: resource multiset allocation
- plan: final=20 mode=EXACT run_class=S
- run_id: `llm-selfposed-13-combir-001`  db: `llm_selfposed_13_combir`  sieve: False
- candidates executed: 20
- verdict distribution: 12x PASS (safe allocation), 6x zero diversity: all 3 slots same type (single point of failure), 2x serving workload allocated no gpu slot
- formal Pareto front: 6 non-dominated (PASS on front: 3/6; provenance_ok)
- Pareto note: the formal front is over ALL executed candidates; DOMAIN_FAIL members are findings, not deployable — pick the best PASS candidate to deploy
- evidence: run.json, state.json, executor-summary.json, metrics.kv, provenance.json
- PASS exemplar: `app=resource_alloc workload=batch alloc=cpu+mem+mem diversity=2 gpu_slots=0 cost_units=5 FW_VAR=0`
- DOMAIN_FAIL exemplar: `app=resource_alloc workload=serving alloc=cpu+cpu+mem diversity=2 gpu_slots=0 cost_units=4 FW_VAR=3`
- DOMAIN_FAIL exemplar: `app=resource_alloc workload=batch alloc=mem+mem+mem diversity=1 gpu_slots=0 cost_units=6 FW_VAR=2`
