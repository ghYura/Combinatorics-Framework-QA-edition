# transformers_sweep_288 — Bundle conclusions on the architecture-synthesis workflow

> Campaign: synthesize tiny ternary Medusa transformers by combinatorially mixing the logical UNITS
> of the `considerme_as_upgrade1..4` chunks, then **train and measure each one end-to-the-last-end**
> (synthesis → structural oracle → cheap proxy → pre-training on a fixed shared corpus → fp & int8
> deployed quality). Run on a weak FX-8320-class PC. 288 architectures, EXACT.

## 1. What the Bundle contributed (the workflow as a Bundle program)

The transformer was **decomposed into independent units**, and each unit became an axis of *freedom*:

| Unit (axis) | Verb | Variants |
|---|---|---|
| NORM | `FW_Combi(1)` | rmsnorm, layernorm |
| TOKENMIX | `FW_Combi(1)` | lin_cumsum, lin_fused_qkvg, lin_decay |
| CHANMIX | `FW_Combi(1)` | dense, moe_top2, moe_shared_top1 |
| NORMPOS | `FW_Combi(1)` | pre, post |
| MEDUSA | `FW_Combi(1)` | separate, vectorized |
| OPT_JITTER, OPT_CONVQ | `FW_Optional` | present ⊕ absent |

`fw_final = 2·3·3·2·2 × 2² = 288` candidates (mandatory product **falls out** of the verbs;
`fwgen.estimate_core_combos = 72`, × FW_Optional `2²` = 288 — verified). Scaffolding:
**FW_RunMeFirstOnce** = one-time bootstrap (compile the SSSE3/SSE4.1 kernel once, seed, smoke);
**HEAD** = per-candidate metrics init; **TAIL** = the `FW_VAR` oracle + metric stdout; **goals** =
the Analyzer Pareto (`params:min × latency:min × proxy_gradnorm:max`).

This is the framework's real value here: the spec **reads as the design space**, the count is exact and
reproducible, FW_Optional adds ablations without exploding the product, and the genuine transport
(`fwgen → Java Core → Reader → py_executor → Postgres`) makes every candidate an addressable artifact
with a verdict in a DB. The real pipeline ran **green (6/6)** on the `arch_mix_smoke` slice; the full
288 ran DB-free in `run_sweep.py` (one process, resumable, per-candidate SIGALRM cap).

## 2. Empirical results (288/288, fixed order-2 Markov corpus, `uniform_ce = 3.871`)

- **288/288 valid, 0 timeouts, 0 crashes.** Every synthesized architecture built, trained, and
  int8-deployed; held-out CE fell from ~3.98 to **2.93–3.10** (≈14× chance accuracy).
- **int8 deployment is LOSSLESS across all 288** (`quant_gap ≈ 0.000`) — ternary-aware (BitNet)
  training holds for every mix. This is the strongest, most transferable result.
- **Per-axis quality (deployed int8 acc / final CE):** CHANMIX dominates (`moe_top2` 0.290/3.015 >
  `shared_top1` 0.281 ≈ `dense` 0.282); `lin_cumsum ≡ lin_fused_qkvg` (identical quality — the fusion
  is mathematically exact — but **fused is the fastest** to train); `rmsnorm ≈ layernorm`; pre ≈ post;
  vectorized Medusa ≈ separate but faster.
- **Best deployed (this toy task):** `lin_fused_qkvg + moe_top2 + layernorm + post + separate` →
  int8 ppl 18.80, acc 0.303. The cheap/fast Pareto end is dominated by **`lin_fused_qkvg + dense`**
  (~17k params, ~8 ms).

## 3. The headline methodological conclusion

**Cheap synthesis-time proxies did NOT predict trained quality.** Over all 288, the Spearman rank
correlation of `proxy_gradnorm → deployed quality` was **−0.205** (weakly *anti*-correlated);
`params → quality` only +0.254. → For this ternary family you **must actually pre-train** to rank
candidates; zero-cost NAS proxies mislead. The "end-to-last-end" extension was therefore necessary,
not decorative — the cheap oracle alone would have ranked architectures wrongly.

## 4. Honest limitations

- The quality numbers come from a **tiny synthetic order-2 Markov probe at ~31k params**. Rankings are
  task/scale-specific — e.g. `moe_top2 > moe_shared_top1` here does **not** account for `shared_top1`'s
  real win (DDR3 bandwidth: one routed matrix/token) at deployment scale. Use this sweep to **falsify**
  (catch broken/fragile mixes, confirm invariants), not to pick the production model.
- **Calibration correction (the earlier draft was wrong).** My first instinct — "for an unconstrained
  product a Python `itertools.product` loop reproduces it" — holds *only at this toy 288 scale and only
  for ephemeral, in-memory generation*. It misses what the Java Core is **for**: it **materializes and
  persists the entire pre-combination space to the database** (here `fw_final`; by design **>10⁹ rows**),
  and the Reader then fans out **parallel threads/files**, streaming shards to **many isolated Executors
  running against isolated System-Under-Test instances**. `itertools` is lazy, single-process, GIL-bound
  and ephemeral; to match the Core you would have to re-implement DB persistence + sharding + a work
  queue + cross-node fault-tolerance/resume + SUT isolation — i.e. rebuild the Core. On high-end hardware
  (e.g. Supermicro H13/H14, many NUMA cores) that DB-backed, parallel-isolated-execution model is exactly
  what exploits the box; a Python loop is not equivalent. So the honest limitation is that **my 288 toy
  under-exercised the framework**, not that the framework is over-built.
- Separately, the constraint/ordering/second-order machinery (**sieve**, `FW_Permut`, brace / `FW_Group`)
  was also unused here — another sign this campaign touched only a slice of the engine's expressiveness.
- The executor runs **each candidate as its own subprocess** (torch re-import ≈2 s) → impractical for
  288 on a weak PC via the live pipeline; hence the split (real pipeline = small slice; in-process
  driver = full sweep).

## 5. Net verdict

The Bundle is a genuinely useful, well-separated combinatorial-search substrate (mechanics × bonds ×
meaning) with real advantages in **declarativity, exact reproducible counts, DB-persisted provenance,
resumability, and the optional-action algebra**. Its true domain is **DB-backed billion-scale spaces
streamed to parallel isolated executors against isolated SUTs** (the Java Core/Reader/Executor line);
this campaign exercised only a small, constraint-free, in-memory-scale slice of it — yet still produced
a rigorous, auditable run and the data for a non-obvious conclusion: **the synthesized transformers are
robustly composable and int8-lossless, but their quality must be measured by real training, not cheap
proxies.** A fair "is it worth the machinery?" verdict requires testing it at its design scale, not at 288.

## 6. Updated conclusion — fidelity, scale, and the funnel (what a toy sweep can and cannot decide)

This 288-sweep is a **falsifier, not a chooser**. The epistemics are asymmetric:

- **Trust its "NO".** Defects that fail at 31k params fail at any size — non-causal, non-deterministic,
  untrainable (no/NaN grad), recurrence-cache inexact, NaN logits. Those are *architectural*, and scale
  will not cure them. Cheap rejection is sound.
- **Distrust its "YES".** The toy is structurally **blind** to the effects that decide a production model,
  because at ~31k params / order-2 Markov / 2 layers / short context, the relevant pressures never appear:
  - memory-bandwidth wins (`moe_shared_top1` = one routed matrix/token; `fused_qkvg`; vectorized Medusa;
    RMSNorm) — the toy fits in cache, so DDR3 never bottlenecks; at scale on FX-8320/H13/H14 the ranking
    can **flip** (this is why the toy ranked `top2 > shared_top1`, opposite to the bandwidth argument);
  - long-range modelling (`lin_decay`'s forgetting gate) — needs real long-range dependencies the toy lacks;
  - depth-stability (pre- vs post-norm) — only manifests with many layers;
  - MoE router collapse / `load_balance` value — needs many experts, tokens, and training steps;
  - accumulated int8 quantization error — `quant_gap≈0` here is on a 2-layer model; it can grow with depth.

**So: yes — training at scale on the right data WOULD surface the real benefit/drawback of each transformer**
that this sweep cannot see. But scale is *necessary, not sufficient*: it also needs the right data
(genuine long-range/semantic structure — for testme5, the real Bundle-guide corpus), the right metrics
(held-out perplexity on the true distribution, downstream quality, **tokens/s + bandwidth utilisation**,
quant gap, expert balance), and enough steps to converge. And cheap proxies stay untrustworthy (§3).

**The rational protocol is a multi-fidelity funnel, and it is where the engine and the sweep cooperate:**

1. **Falsify cheaply** — the 288 in-process sweep prunes broken/fragile/untrainable mixes (done here).
2. **Promote survivors** up a fidelity ladder (toy → medium → scale), ranking by *actual trained quality*,
   never by proxies.
3. **Confirm at scale** — run the survivors through the **Java Core (DB-persisted space) → Reader →
   parallel isolated Executors against isolated SUT instances**, which is exactly what high-end hardware
   (Supermicro H13/H14, many NUMA cores) is for. The sweep is the *prefilter*; the Core is the *scale judge*.

Net: the toy sweep earns its keep as a fast, auditable **rejection filter and invariant-checker**; the
production decision belongs to the Core running the survivors at design scale on real data.

## 7. The "end to final end" battery — discriminative data + capability checks (`final_probe.py`)

The order-2 Markov sweep (§2-3) was a falsifier that could not *choose* (all archs tied). `final_probe.py`
adds **purpose-built data engineered so the axes separate**, with capability metrics wired in from the
start, fp **and** int8-deployed, kept tiny for the FX-8320 (~5–10 s/candidate here, < the 90 s cap;
balanced 18-cell default over tok×chan×normpos, `--all` for 288).

Task = **mode-switched Markov mixture**: K=3 shared fixed peaked sources, a leading mode token selects
the rule. Two engineered pressures → two discriminators: (a) **per-mode accuracy** (MoE can route to
per-mode specialists, dense must cram K conflicting rules into shared weights); (b) **length
generalization** (train chain S=20, test S=40 — the mode token sits further back, so a forgetting
`decay` state should fade). Plus Medusa T+2/T+3 and int8 + quant gap.

**Findings (18-cell battery; content chance 0.025, oracle ceiling ~0.50, models reach 0.21–0.28):**
- **Channel mixer now SEPARATES** (the signal the toy lacked): `dense` 0.209 < `moe_top2` 0.263 ≈
  `moe_shared_top1` 0.266 mode-acc, and MoE lifts the *worst-mode* min (0.154 → 0.21) with lower
  spread. Routing to specialists genuinely beats a dense FFN at K conflicting rules; **top-8 by deployed
  capability are all MoE**. Best deployed: `lin_fused_qkvg + moe_top2 + pre` (CAP 0.267).
- **Honest null on the token mixer:** length-gen did **not** separate `cumsum` ≈ `fused` ≈ `decay`
  (len_ret ≈ 0.92 for all); at this scale the mode-carry isn't the bottleneck so `decay`'s fade never
  bites. `fused_qkvg` ≡ `cumsum` in quality (exact), `decay` slightly lower and slowest.
- **int8 deployment lossless** (quant_gap ≈ 0.000 across all); Medusa T+2 ≈ 0.11 (Markov ceiling is low).

**What this confirms (ties back to §6):** purpose-built data DOES surface the **capacity/routing** axis at
tiny scale (because K conflicting rules exceed a small dense FFN's capacity — a *local* pressure), but the
**long-range token-mixer** differences still need genuine long-range data **and scale**. So the funnel
stands: this battery sharpens the cheap stage (it can now *choose on capacity*), while the long-range
verdict remains a scale question for the Core. All capability metrics are wired in from the start, so the
same `evaluate_final` runs unchanged when promoted up the fidelity ladder.

_Artifacts:_ `sweep_out/` (order-2 falsifier sweep, 288) · `final_out/results.jsonl` (capability battery).
_Re-run:_ `python3 run_sweep.py --status` · `python3 final_probe.py` (18-cell) · `final_probe.py --all` (288).

## 8. Real-final-quality metrics, analyzed through Analyzer_trunk

`final_probe.py` now computes a thorough **real-LLM-quality** metric set per candidate and hands it to
**`Analyzer_trunk/AnalyzeKv`** (the Bundle's heuristic multi-objective optimizer) — not my own ranker.

Metrics (every candidate, fp **and** int8-deployed):
- **LM quality:** `ppl` (perplexity), `top5`, `acc_vs_oracle` (= model acc / the data's Bayes-optimal ceiling).
- **Trust/calibration:** `ece` (10-bin expected calibration error), `entropy` (collapse guard).
- **Speculative deploy:** `spec_tokens` (expected accepted Medusa draft length = decode speedup).
- **Quant fidelity:** `quant_kl` (fp→int8 distribution KL), `quant_gap` (acc drop).
- **FX-8320 cost:** `params`, `active_kb` (weights read/token), **`cold_ffn_kb`** (routed/COLD DDR3 traffic),
  `latency_ms`, `tokens_per_s`.
- **Robustness:** `len_ret` (length-generalization retention).

Pipeline: each valid candidate → a `key=value` line (with `candidate_id`/`run_id`) in `final_out/corpus.kv`
→ `AnalyzeKv corpus.kv K "<GOALS>" --mode formal --corpus-count N --provenance-out provenance.json`. GOALS =
`acc_vs_oracle:max, ppl:min, ece:min, quant_kl:min, spec_tokens:max, cold_ffn_kb:min, active_kb:min,
params:min`. The Analyzer returns **Welford per-metric stats, an NSGA-II online Pareto front, top-K by score,
balanced optima (weighted-sum / Tchebycheff / distance-to-ideal), and a versioned provenance report**.

**Findings (18-cell, FORMAL, 8 goals):** models reach `acc_vs_oracle μ≈0.49`, `ppl μ≈23`, `ece μ≈0.059`,
**`quant_kl≈0` (int8 distributionally lossless)**, `spec_tokens≈1.12` (Markov ceiling is low), and
`cold_ffn_kb` spans 0/4.5/9 (dense/shared_top1/top2). The **balanced optima favour *dense*** (e.g.
`cumsum+dense+post`) — with the three FX-8320 cost goals weighted equally, dense's `cold_ffn_kb=0` and
smaller footprint outweigh MoE's small quality edge. So the Analyzer makes the trade-off explicit:
**pure capability (§7) favours MoE; cost-weighted multi-objective favours dense — the pick is a function of
the goal weights**, which is exactly the decision the Analyzer (not a hand-coded ranker) should own.

_Analyzer artifacts:_ `final_out/corpus.kv` (KV corpus) · `final_out/provenance.json` (Pareto provenance).
_Run the Analyzer alone:_ `final_probe.py` emits + invokes it; or replay AnalyzeKv on `corpus.kv` with any GOALS.
