# Run report — 02_optional_queue_saga

- spec: `llm_selfposed_bundle_tasks/02_optional_queue_saga/scenario.toml`  sha256 `ce176d66c0666d4f...`
- category: optional sudden actions  | pattern: usecases/event_order
- plan: final=24 mode=EXACT run_class=S
- run_id: `llm-selfposed-02-saga-001`  db: `llm_selfposed_02_saga`  sieve: False
- candidates executed: 24
- verdict distribution: 2x PASS, 12x ack before process (order violation), 8x process before fetch (order violation), 2x double process (idempotency violation on redelivery)
- formal Pareto front: 12 non-dominated (PASS on front: 0/12; provenance_ok)
- Pareto note: the formal front is over ALL executed candidates; DOMAIN_FAIL members are findings, not deployable — pick the best PASS candidate to deploy
- evidence: run.json, state.json, executor-summary.json, metrics.kv, provenance.json
- PASS exemplar: `app=queue_saga order=fetch>process>ack dup=0 crash=0 process_count=1 acked=1 breach=none FW_VAR=0`
- DOMAIN_FAIL exemplar: `app=queue_saga order=fetch>process>ack dup=1 crash=0 process_count=2 acked=1 breach=none FW_VAR=4`
- DOMAIN_FAIL exemplar: `app=queue_saga order=fetch>ack>process dup=0 crash=0 process_count=1 acked=0 breach=ack_before_process FW_VAR=2`
- DOMAIN_FAIL exemplar: `app=queue_saga order=process>fetch>ack dup=0 crash=0 process_count=0 acked=0 breach=process_before_fetch FW_VAR=3`
