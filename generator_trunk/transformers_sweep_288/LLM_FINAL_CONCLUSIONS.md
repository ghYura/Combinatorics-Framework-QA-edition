# transformers_sweep_288 — FINAL conclusions (serious 2-phase LLM run, analyzed by Analyzer_trunk)

**Run:** 288 candidates, sequential queue, 8 threads (~87% CPU), per candidate = base-teaching (130 steps,
4-mode synthetic corpus) → fine-tune (60 steps, 2-mode) → fp & int8-deployed quality battery. ~3 h.
**Verdict histogram:** `280 code=0`, `8 code=7`. **Analyzer_trunk/AnalyzeKv (FORMAL, 8 goals)** ingested
the 280 → 83-candidate NSGA-II Pareto front; provenance_ok=true.

## Global results (280 valid)
- All models learn: base_acc ≈ 0.41, **fine-tune reaches ft_acc_vs_oracle ≈ 0.88** (88 % of the Bayes
  ceiling), general acc_vs_oracle ≈ 0.76, ppl ≈ 11.2, ECE ≈ 0.11, forgetting ≈ 0.08, spec_tokens ≈ 1.22.
- **int8 deployment is LOSSLESS everywhere** (`quant_kl = 0.0000` across all 280) — the strongest,
  most transferable result: ternary-aware training survives quantization for every architecture mix.

## Analyzer Pareto / balanced optima
- 83 of 280 non-dominated (8-objective). All three scalarizations (weighted-sum / Tchebycheff /
  distance-to-ideal) agree on **`cumsum + dense + pre + separate`** — the **cost-weighted** optimum:
  with three equally-weighted FX-8320 cost goals (`cold_ffn_kb`, `active_kb`, `params`) dense's
  `cold_ffn_kb = 0` and smaller footprint outweigh MoE's small quality edge. **Pure capability favours
  MoE; cost-weighted multi-objective favours dense — the pick is a function of the goal weights.**

## Per-axis verdicts (means over valid)
- **TOKENMIX:** `cumsum ≈ fused_qkvg ≈ decay` in quality (base 0.41, ft/or 0.88, ppl 11.2 — all tied).
  The only real difference is **speed**: `fused_qkvg` 37 s < `cumsum` 41 s < `decay` 53 s/candidate.
  → **fused-QKVG = same quality, fastest (clear win). decay = same quality, slowest (cost unjustified
  at this scale).**
- **CHANMIX:** `moe_top2` best quality + **least forgetting** (acc/or 0.778, ppl 11.0, forget 0.072) but
  2× cold DDR3 traffic (`cold_ffn_kb` 216). `moe_shared_top1` = bandwidth-friendly middle (cold 108).
  `dense` = cheapest (cold 0) but weakest (acc/or 0.756) and **forgets most** (0.094).
- **NORMPOS:** `pre ≈ post` (post marginally better at 3 layers: acc/or 0.769 vs 0.761). Neutral.
- **MEDUSA:** `separate` edges quality/spec (CAP 0.742, spec 1.230); `vectorized` edges cost/speed
  (active 347 KB vs 365, faster). Near-neutral.
- **FW_Optional sudden actions:** **`conv_q` is a real win** — it REDUCES catastrophic forgetting
  (0.075 vs `none` 0.093) and improves quality (acc/or 0.777 vs 0.748, CAP 0.746 vs 0.728). `jitter` ≈
  neutral. So the extra causal Conv1D on Q earns its place; router jitter is optional.

## Champions
- Best deployed **capability**: `decay + dense + post` → 0.797. Least **forgetting**: `decay + dense +
  post (no opt)` → 0.012. Best **ft_acc_vs_oracle**: `fused_qkvg + dense + pre` → 0.953. (decay tops a
  couple of individual configs but is quality-neutral *on average* and the slowest — its benefit is
  config-specific, not general.)

## Caveat — the 8 `code=7` (benign, documented)
All 8 are `*/moe_shared_top1/post` (cumsum & fused, the conv_q variants): the high-activation post-norm +
shared-expert family where deterministic fp rounding (conv1d length-dependent blocking, amplified by
`q@kv`) nudges the recurrence's **relative** delta just past the `5e-3` gate. The cache is logically exact
(bare-layer = 1.19e-7); these are **not real bugs** — the oracle gate is still slightly tight at d=96
(fix: `≈2e-2`, per BUNDLE_TODO #1). Net effect: a ~2.8 % biased exclusion of one family from the corpus.

## Bottom line for the FX-8320 build
Take **fused-QKVG** (free speed), **conv_q** (less forgetting, better quality), **RMSNorm** (quality-neutral,
cheaper), and decide MoE-vs-dense by your weighting: **`moe_top2`** if quality/anti-forgetting matters most,
**`moe_shared_top1`** for the bandwidth compromise, **`dense`** if cost dominates (the Analyzer's cost-weighted
pick). **Skip `decay`** here — no quality payoff for the slowest path. int8 deployment is lossless regardless.













Bundle доказал свою полезность в кампании "LLM Transformers 288" — конкретно и поучительно.

  - Поймал реальный класс дефекта, который я бы «отгрузил». Исчерпывающий перебор 288 архитектур + per-candidate
  FW_VAR-оракул выявил аномалию conv_q (recurrence), которую все мои ручные smoke-тесты пропустили — потому что они
  всегда шли с opt=[] (без conv_q). Только полный комбинаторный охват её задел. Это фальсификатор в действии:
  «доверяй его НЕТ, потом разбирайся».
  - Дал настоящий многокритериальный вывод, а не один скаляр: Analyzer_trunk построил 83-кандидатный NSGA-II Парето
  + balanced-optima + provenance, и сделал явным компромисс качество↔стоимость FX-8320 (чистое качество → MoE;
  взвешенная по стоимости свёртка → dense). Самый переносимый результат — int8-деплой без потерь на всех 280 — тоже
  дал именно систематический прогон.
  - Это меня смирило. Моё раннее «для такой задачи он избыточен» было недокалибровано — твоё возражение оказалось
  правым. Движок нашёл баг в моём коде/оракуле, а не в себе.

  Калибровка (честно, без лести): ценность дала прежде всего методология (механика × смысл: полный перебор + оракул
  и провенанс/масштаб), а качество оракула — на мне (абсолютный порог был именно моей ошибкой). Кампания
  задействовала лишь часть выразительности движка (без sieve/FW_Permut/2-го порядка). То есть Bundle делает перебор
  и учёт строгими, но «истинность» вердикта по-прежнему зависит от того, какой оракул ты в него подаёшь.

  Обновлённое мнение эксперта: с «силён для структурированного поиска, но здесь избыточен» → на «оправдал себя»: для
  серьёзного тестирования архитектур это правильный инструмент — воспроизводимый точный перебор, многоцелевой
  Парето с провенансом, и реальная способность ловить дефекты, которые ad-hoc тесты не видят. Его надо дополнять
  (fuzzer/PBT — «неизвестные неизвестные», прод-телеметрия — незаложенные оси), а не заменять скриптом. И
  показательно, что кампания не только оценила архитектуры, но и улучшила сам Bundle (реализованные
  verify/oracle/coverage/exclusion-guards из BUNDLE_TODO) — то есть инструмент и задача усилили друг друга.
