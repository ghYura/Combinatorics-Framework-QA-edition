# Verified local smoke evidence

Verification date: 2026-07-26. No external adapter, provider request, or paid
service was used.

## Full Bundle chain

| Scenario | Core `fw_final` | Reader | Executor | PASS | Unexpected outcomes | Metrics | Formal seen |
|---|---:|---:|---:|---:|---:|---:|---:|
| `00_smoke` | 32 | 32 | 32 | 32 | 0 | 32 | 32 |
| `01_operator_smoke` | 8 | 8 | 8 | 8 | 0 | 8 | 8 |
| `60_higher_order_prompt_programs` | 1 | 1 | 1 | 1 | 0 | 1 | 1 |
| `70_router_regression_dataset` | 24 | 24 | 24 | 12 | 0 | 24 | 12 |

Run IDs:

- `ai-combi-00_smoke-20260725T222432Z`
- `ai-combi-01_operator_smoke-20260725T222432Z`
- `ai-combi-60_higher_order_prompt_programs-20260725T223536Z`
- `ai-combi-70_router_regression_dataset-20260725T223031Z`

For all four K=1 runs:

- every stage completed with `SUCCEEDED`;
- generated, emitted, processed, persisted, and metrics counts reconciled;
- `BROKEN`, `TIMEOUT`, `INFRA_FAIL`, `CANCELLED`, and `SKIPPED` were zero;
- formal `candidates_seen` equaled eligible PASS records;
- Analyzer `provenance_ok` was true, issues were empty, and run IDs matched;
- the two-smoke common report withheld a router claim because all 40 samples
  came from the explicitly labeled oracle control;
- 9/9 groups with multiple equivalent renderings in the two smoke runs passed every rendering;
- `AI70` retained 12 exact-control PASS candidates, excluded 12 declared negative-control domain failures from formal analysis, and still reconciled all 24 metrics and persisted verdicts.
- the fourth-order run materialized one exact candidate with order 4, depth 5,
  52 recursive nodes, 34 atoms, and prompt version v2.

## Repeat confirmation

`00_smoke` was also executed with local metric repeat `K=2` under an explicit 64-request and zero-monetary-cost plan. Core, Reader, Executor, and persisted verdicts remained 32; the metrics corpus contained the expected 64 samples; formal Analyzer identity remained 32 unique eligible candidates; and all 32 repeat groups had consistent verdicts. Run ID: `ai-combi-00_smoke-20260725T222903Z`.

Runtime artifacts and the combined machine report remain under `/tmp` and are
not committed as source. The checked-in counts above are durable,
non-credentialed evidence; rerun `run_campaign.py smoke` to reproduce them.

## Generalized release-gate sub-suite verification

Verification date: 2026-07-28. No external provider, browser, API request, or
paid service was used.

| Configuration | Task levels | Core rows | Reader | Executor PASS | Unexpected outcomes | Metrics | Formal seen |
|---|---:|---:|---:|---:|---:|---:|---:|
| default apparatus | 5 | 160 | 2,560 | 2,560 | 0 | 2,560 | 2,560 |
| one-level package closure | 1 | 32 | 512 | 512 | 0 | 512 | 512 |

- Both runs used the network-disabled `generated-default` profile; their stage
  counts and Analyzer provenance were clean. The July 29 qualification below
  corrects a defect in the committed post-run reporter for optional expansion.
- The default run exercised task sizes 2/4/8/16/32 and all 512 nine-factor
  construction coordinates at each level.
- The package-closure run produced the complete exchange, reconciled its empty
  response templates, then scored exact inserted oracle responses at strict
  2/2 and extracted-semantic 2/2.
- The AI-platform plus complete Python-Executor regression selection passed
  159/159 tests in the exact source checkout.
- The raw holdout seed, temporary spec/plan/run/scratch trees, generated
  candidates, response outputs, and both narrowly named databases were removed.
  None is committed.

These are constructor/oracle apparatus results, not evidence about an external
AI model. Such a claim begins only after separately acquired target responses
are identity-checked and scored.

### 2026-07-29 optional-count correction

The then-committed AI-platform reporter compared Core's 160 mandatory
`fw_final` rows directly with Reader's 2,560 assembled candidates. That
`core_equals_reader` check was invalid: four one-valued `FW_Optional` atoms
create an exact Reader multiplier of 16. The defect could reject an otherwise
successful run during exchange packaging; it did not change candidate source,
oracle verdicts, or Analyzer results.

The reporter now requires Reader actual to equal the Reader stage's declared
runtime expansion, then reconciles Reader with Executor, outcomes, metrics, and
provenance. A synthetic regression covers both acceptance of `2 → 32` and
rejection of an incorrect declared expansion. A live safe-profile rerun reached
Core `160` and Reader actual/expected `2,560`, but the secure per-candidate
Executor replay was intentionally stopped because container startup made a
complete 2,560-candidate replay impractical in this environment. No new
successful full-chain live closure is claimed; cleanup and exact scope are
recorded in the dated session findings.

## Anonymized terminal target observation

Verification date: 2026-07-29. The target's vendor and market name are
intentionally omitted; it is recorded as **Target A**, invoked through a local
terminal client at its lowest supported reasoning-effort setting.

| Phase | Fresh sessions | Strict PASS | Semantic PASS |
|---|---:|---:|---:|
| clean/max endpoints across five task levels | 10 | 9 | 9 |
| fixed two-check strength-two follow-up | 10 | 7 | 7 |
| designed total | **20** | **16** | **16** |

A separate preflight smoke passed. Every designed call used a fresh ephemeral,
read-only, tool-free session. On the fixed task, clean passed twice and maximal
construction failed twice; follow-up weights 0..6 passed and 7..9 failed. The
failures were exact semantic errors—the target incorrectly added `RG-002` even
though observed `58` satisfied its `at_least 56` rule—not response-format
failures.

This establishes a bounded proof of concept: clean-only sampling would have
reported 5/5, while Bundle-constructed contrasts exposed a reproducible defect.
It does not establish a universal model rank or calibrated breakpoint. Raw
responses and terminal event streams remain runtime evidence and are not
committed. Full protocol, usage counts, browser non-evidence, and limitations
are in [`docs/AI_COMBI_SESSION_FINDINGS_2026-07-29.md`](../../docs/AI_COMBI_SESSION_FINDINGS_2026-07-29.md).

## Static and focused verification

- The guide's reference `event_order` plan produced exactly 24 candidates.
- All nine platform scenarios parsed strictly and planned successfully.
- `00_smoke` planned at exactly 32.
- `01_operator_smoke` and `60_higher_order_prompt_programs` honestly planned as
  runtime-unknown/X because later operators consume actual result tables.
- The operator smoke materialized 8 candidates, confirming intermediate brace
  targets did not multiply independently.
- Platform, catalog, and both Face 1 integration test selections passed.
