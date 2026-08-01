# transformers_sweep_288 — Bundle architecture-synthesis campaign

A `generator_trunk` campaign (sibling of `llm_arch_search`, `llm_transformer_campaign`). It uses the
**Combinatorics framework (the Bundle)** to *synthesize and measure* tiny ternary Medusa transformers
by combinatorially mixing the logical UNITS of the `considerme_as_upgrade1..4` chunks (which live in
`$BUNDLE_SUT_ROOT/llm_transformer_testme/testme5upgraded/`). Set `BUNDLE_SUT_ROOT` to the directory
containing the separately checked-out SUT projects. Each unit is a
swappable **axis**; the Bundle takes the product and an oracle judges every composed architecture —
all the way to a **pre-trained, int8-deployed** model ("end-to-last-end").

## Decomposition → recombination (the design space)

| Unit (axis) | Verb | Variants | source chunk |
|---|---|---|---|
| NORM | `FW_Combi(1)` | rmsnorm, layernorm | upgrade2 / baseline |
| TOKENMIX | `FW_Combi(1)` | lin_cumsum, **lin_fused_qkvg**, lin_decay | upg1·2 / **upg4** / upg3 |
| CHANMIX | `FW_Combi(1)` | dense, moe_top2, moe_shared_top1 | baseline / +routing / upg2-4 |
| NORMPOS | `FW_Combi(1)` | pre, post | upg2-4 / upg1 |
| MEDUSA | `FW_Combi(1)` | separate, vectorized | baseline / all upgrades |
| OPT_JITTER, OPT_CONVQ | `FW_Optional` | present ⊕ absent | upg3 |

`fw_final = 2·3·3·2·2 (mandatory) × 2² (FW_Optional) = 288 (EXACT)`. `FW_RunMeFirstOnce` = one-time
bootstrap (compile the FX-8320 kernel once); HEAD = metrics init; TAIL = the `FW_VAR` oracle + stdout;
goals = Analyzer Pareto.

## Files

- `mix_arch.py` — parametric factory + `evaluate()` (structural oracle) + `evaluate_full()`
  (structural + cheap proxy + **pre-training on a fixed shared corpus** + fp & int8 quality) + `bootstrap()`.
- `arch_mix/arch_mix.toml` — the full 288 Bundle spec (validated via `fwgen.load_spec`).
- `arch_mix_smoke/arch_mix_smoke.toml` — 6-candidate slice for the **real** Bundle pipeline.
- `run_sweep.py` — self-monitoring full-288 driver: per-candidate SIGALRM cap, incremental
  `sweep_out/results.jsonl` (resumable), heartbeat, and `--status` stale-detector.
- `_selfcheck.py` — DB-free structural sweep over the same space (fast).
- **`final_probe.py`** — the "end to final end" battery: discriminative data (mode-switched mixture) +
  pre-training + capability checks (per-mode breadth, length-gen, Medusa, int8-deployed). See CONCLUSIONS §7.
- `sweep_out/` — order-2 falsifier sweep results; `final_out/` — capability-battery results.
- **`CONCLUSIONS.md`** — the Bundle's conclusions on this workflow + findings (read this).

## Run

```bash
# full end-to-last-end sweep (synth + pre-train + fp/int8 quality), background-friendly + resumable:
python3 run_sweep.py --fresh          # start ;  --status to ping ;  rerun w/o --fresh to resume

# fast DB-free structural sweep (no training):
python3 _selfcheck.py                 #  --full = 288 ;  --limit N

# "end to final end" capability battery (discriminative data + pre-train + int8-deployed checks).
# Computes real-LLM-quality metrics (ppl, top5, acc_vs_oracle, ece, entropy, spec_tokens, quant_kl,
# active_kb, cold_ffn_kb, len_ret, ...) and ANALYZES THEM THROUGH Analyzer_trunk/AnalyzeKv (NSGA-II
# Pareto + Welford stats + balanced optima + provenance) over GOALS. Writes final_out/corpus.kv.
python3 final_probe.py                #  18-cell ;  --all = 288 ;  --status ;  --topk N ;  --no-analyze ;  --fresh

# GENUINE Bundle transport (Postgres + Java Core + Reader + py_executor), small slice:
cd ..   # generator_trunk
python3 bundle_run.py transformers_sweep_288/arch_mix_smoke --lang py --db archmixsmoke02
```

## Headline findings (see CONCLUSIONS.md)

- 288/288 valid, **int8 deployment lossless** everywhere (`quant_gap≈0`); O(1) recurrence exact for all.
- `lin_fused_qkvg` ≡ `lin_cumsum` in quality (fusion is exact) but **fastest** → dominates the efficient Pareto end.
- **Cheap proxies don't predict trained quality** (Spearman `proxy_gradnorm→quality ≈ −0.2`): you must
  actually pre-train to rank — the end-to-last-end test was necessary.
- Rankings are toy-task-specific (~31k params, order-2 Markov); use the sweep to falsify/confirm
  invariants, not to pick the production model.
