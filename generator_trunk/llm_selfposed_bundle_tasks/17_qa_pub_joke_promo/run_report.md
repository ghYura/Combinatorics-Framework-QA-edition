# Run report — 17_qa_pub_joke_promo

- spec: `llm_selfposed_bundle_tasks/17_qa_pub_joke_promo/scenario.toml`  sha256 `cbb0800b8872e7c8...`
- category: promo/demo (QA tester walks into a pub)  | pattern: boundary/type/domain + order abuse demo
- plan: final=270 mode=EXACT run_class=S
- run_id: `llm-selfposed-17-pubjoke-001`  db: `llm_selfposed_17_pubjoke`  sieve: False
- candidates executed: 270
- verdict distribution: 24x PASS (normal or zero-no-op order accepted), 180x invalid action order (acted before entering), 54x invalid quantity rejected cleanly (type/domain/over-capacity), 12x invalid order target rejected cleanly (a lizard)
- formal Pareto front: 24 non-dominated (PASS on front: 24/24; provenance_ok)
- Pareto note: the formal front is over ALL executed candidates; DOMAIN_FAIL members are findings, not deployable — pick the best PASS candidate to deploy
- evidence: run.json, state.json, executor-summary.json, metrics.kv, provenance.json
- PASS exemplar: `app=qa_pub_joke entry=runs actions=enter>order>sit qty=1 qty_kind=ok target=beer accepted=1 FW_VAR=0`
- DOMAIN_FAIL exemplar: `app=qa_pub_joke entry=runs actions=enter>sit>order qty=999999999 qty_kind=huge target=beer accepted=0 FW_VAR=3`
- DOMAIN_FAIL exemplar: `app=qa_pub_joke entry=runs actions=enter>order>sit qty=1 qty_kind=ok target=lizard accepted=0 FW_VAR=4`
- DOMAIN_FAIL exemplar: `app=qa_pub_joke entry=runs actions=sit>enter>order qty=1 qty_kind=ok target=beer accepted=0 FW_VAR=2`
