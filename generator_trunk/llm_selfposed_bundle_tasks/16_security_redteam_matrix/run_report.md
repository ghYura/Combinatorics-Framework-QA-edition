# Run report — 16_security_redteam_matrix

- spec: `llm_selfposed_bundle_tasks/16_security_redteam_matrix/scenario.toml`  sha256 `461e38f4aaa04b9b...`
- category: security red-team (order + sudden attacks)  | pattern: tryout_own/spec (secure pipeline) + event_order
- plan: final=24 mode=EXACT run_class=S
- run_id: `llm-selfposed-16-redteam-001`  db: `llm_selfposed_16_redteam`  sieve: False
- candidates executed: 24
- verdict distribution: 7x PASS (secure: checks in order, attacks blocked), 12x broken access control: authorize before authenticate, 2x token replay accepted: authn not bound first, 3x privilege escalation: rate limiting before the authorization check
- formal Pareto front: 17 non-dominated (PASS on front: 0/17; provenance_ok)
- Pareto note: red-team run: the formal front intentionally maximizes breach, so DOMAIN_FAIL front members are the desired security findings; PASS candidates are secure baselines, not the optimization target
- evidence: run.json, state.json, executor-summary.json, metrics.kv, provenance.json
- PASS exemplar: `app=security_redteam order=authn>authz>ratelimit replay=0 escalate=0 breach=0 FW_VAR=0`
- DOMAIN_FAIL exemplar: `app=security_redteam order=authn>ratelimit>authz replay=1 escalate=1 breach=1 FW_VAR=4`
- DOMAIN_FAIL exemplar: `app=security_redteam order=authz>authn>ratelimit replay=0 escalate=0 breach=1 FW_VAR=2`
- DOMAIN_FAIL exemplar: `app=security_redteam order=ratelimit>authn>authz replay=1 escalate=0 breach=1 FW_VAR=3`
