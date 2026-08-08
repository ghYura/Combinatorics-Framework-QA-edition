# Bundle-native AI testing — the 48 proposals, re-sorted against real engine capability

**Status: synthesis.** This supersedes the build order in
[`PROPOSALS_COMBINATORIAL_AI_TESTING.md`](PROPOSALS_COMBINATORIAL_AI_TESTING.md), which was written
from an audit of this directory alone and therefore treated as "future work" several things the
engine already does. The proposals themselves stand; their **placement** was wrong.

Verified against: `ZEN_OF_COMBINATORICS.md`, `docs/28_SECOND_ORDER_AXES_AND_NESTED_BONDS.md`,
`constraints/sidecar_schema.md`, `bundle/config.py`, `bundle/cliargs.py`, and the six LLM campaign
trees under `generator_trunk/` (`llm_loop`, `llm_arch_search`, `llm_selfposed_bundle_tasks`,
`llm_transformer_campaign`, `transformers_sweep_288`, `model_usecases`).

---

## 0. Two distinctions that decide everything

### 0.1 The candidate is either code or a prompt

| | candidate | what "execute" means | engine fit |
|---|---|---|---|
| **White-box AI** — architecture search, training sweeps, kernel/quantization studies | executable code | compile, isolate, resource-cap, measure | **The full chain is already the right tool.** `transformers_sweep_288` — 288 candidates, ~3 h, 8 threads, 280 valid → AnalyzeKv formal 8-goal NSGA-II → 83-candidate Pareto front, `provenance_ok=true`. |
| **Black-box AI** — prompt → hosted model → parse | a prompt | one network call, 1–30 s, metered | Assembly semantics wanted; per-candidate process + DB round-trip is not amortisable at 0.06 req/s. |

These are different products sharing one engine. Most confusion in the earlier documents comes from
letting the black-box case speak for both.

### 0.2 The algebra operates on **value-codes and positions**, never on text

This is the single most important fact for AI purposes, and it is documented the hard way in
`ZEN_OF_COMBINATORICS.md`: the Core's store is `Map<Short, List<Short>>`, and `FW_ReplaceRE` rewrites
the **code-string** (`"[47, 48]"`) between grouping and parse-back. A textual replacement inside a
value is a **silent no-op** — the `@S@` → `shape` case that cost a real LLM-transformer campaign.

So the division of labour is fixed by the architecture, not by taste:

| | who does it |
|---|---|
| **Selection** — which fragments, how many, k-of-n, with/without | **engine** (`FW_Combi`, `FW_Subsets`, `FW_CombiR`, `FW_Optional`) |
| **Arrangement** — in what order, at what position, joined how | **engine** (`FW_Permut`, `FW_PermutR`, brace, `FW_Group`, `FW_Separator`, Reader positional insert) |
| **Restriction** — which combinations are illegal | **engine** (sieve: `pairs`, `sets`, `when`, `mapping`, `assert`, and the auto-injected `pos`) |
| **Transformation** — rewriting the text of a fragment | **application** (the renderer, in Python) |
| **Judgement** — was the response right | **application** (oracle) |

## 1. The design mistake to stop repeating

Compare two sibling suites that use the same engine.

**`AI_combi_testing_platform/scenarios/*` — value as a *setter statement*:**

```python
PLAN.schema = "json"        # a sheet value
...
_RESULT = run_candidate(PLAN)   # TAIL: everything real happens in here
```

The Core is choosing among enum labels. All selection, arrangement and restriction then happen
*inside one Python function*, where the engine cannot see them. This forfeits `FW_Optional`
positional insertion, the brace, `FW_Group`, and every sieve bond — and it is why `00_smoke` is a
2⁵ product.

**`llm_loop/prompt_injection_redteam.py` — value as a *prompt fragment*:**

> "the Core combinatorially places them at every position and in every combination via `FW_Optional`"

Here the payloads **are** the values. The Reader inserts each optional piece **at its slot position,
before the TAIL**, so the engine controls placement. `redteam3`: 8 × 2³ = 64 candidates, 56/64
breach. That is a genuine combinatorial red-team, produced by the engine.

> **Rule.** If a sheet value is an assignment to a Python variable, you are using a combinatorial
> dataflow engine as an enum picker. Make the fragment the value.

This one change moves a large block of the catalogue from "to build" to "author a spec".

## 2. What the engine already gives AI testing

| Capability | Verified location | AI-testing job it does |
|---|---|---|
| `FW_Optional` + Reader positional insert | Zen §FW_Optional; `llm_loop/redteam3` | **sudden actions**: injection payloads, tool failures, interruptions, retries — placed at any position, across all co-firing subsets. `fw_final × Π(nᵢ+1)`. |
| `FW_Combi(k)` | Zen §one principle | **Skill-Mix directly**: C(N,k) skill subsets is the default verb, not a research project |
| `FW_Permut` / `FW_PermutR(k)` | Zen | order-is-the-variable: doc order, MCQ options, exemplar order, turn order (n! — see §4 B3) |
| `FW_Subsets` / `_EXACT/RANGE/…` | Zen | k-of-n constraint pools, context-chunk subsets, bounded add-ons |
| brace `FW_(…)` with `mult` and woven `start/rel/sep/end` | Zen §brace; `brace_full_demo` | second-order composition — attack × defense as a **join of two result tables**, not a hand-written 3×4 |
| `FW_Group` + `FW_ReplaceRE` | Zen §FW_Group; `README_CANONICAL_TRUTH.txt` | combinations-of-combinations over prior *rows*; code-string surgery |
| Sieve bonds incl. auto-injected **`pos`** | `constraints/sidecar_schema.md` | constrained designs **and positional constraints** ("payload never in slot 0"); `pairs`/`sets`/`when`/`mapping`/`assert` is more expressive than ACTS forbidden tuples |
| `--repeat K --repeat-policy {local,disperse,nested} --repeat-environments E` | `bundle/config.py:250-286` | K repeats; `disperse` spreads them; **`nested` gives K×E across environments** |
| `--budget-requests`, `--budget-monetary-cost`, `--cost-per-candidate` | `bundle/cliargs.py` | money and call count as **planning-time gates** |
| `plan` (side-effect-free, no DB) | `engine_demo/README.md` | exact cardinality before spending anything |
| `min_winner_support` (default 5), `exploration_floor` (0.25) | `bundle/config.py:183-184` | a winner needs support; budget reserved for exploration |
| Analyzer formal mode, NSGA-II, multi-goal Pareto | `transformers_sweep_288/LLM_FINAL_CONCLUSIONS.md` | 8-objective front + three scalarizations; routing as a Pareto answer |
| Provenance/architecture gates, engine_revision hashing | doc 30 | the evidence chain |

**Note on `--repeat-policy nested`.** This already implements proposal **I6** (separate model
non-determinism from serving non-determinism): K repeats × E environments, same candidate. Given a
measured instability of 0.861, that is the most under-used flag in the system.

## 3. The 48 proposals, re-sorted

### Tier 0 — expressible **today**, spec-only, no code change

| # | Proposal | How |
|---|---|---|
| **F2** | injection-surface coverage | `FW_Optional` payload sheets; sieve `pos` predicate to constrain placement. Proven pattern: `redteam3`. |
| **E5** | tool-response fault injection | `FW_Optional` is *designed* for this ("a failure injected mid-flow, a retry, a replay/attack step") |
| **E2** | sharded multi-turn | `FW_Subsets` over shards × `FW_Permut` over delivery × `FW_Optional` for restatement/contradiction |
| **D3** | Skill-Mix | `FW_Combi(k)` over a skill sheet. The engine's default verb *is* the method. |
| **A3** | verifiable-constraint tasks | `FW_Subsets` over the constraint pool; unsatisfiable pairs → sieve `pairs`/`sets` |
| **F1** | attack composition algebra | brace `M:N` joining two attack result tables, or `FW_Group` over attack rows |
| **G3** | retrieved-document order invariance | `FW_Permut` over the document sheet |
| **G4** | MCQ option-permutation orbits | `FW_Permut` over options |
| **D5** | compositional-generalisation splits | `FW_Subsets` + a sieve exclusion for the held-out pair |
| **B2** | constrained designs | the sieve, as-is |
| **H4** | balanced pairwise model comparison | `FW_Combi(2)` over a model sheet + sieve balance conditions |
| **I6** | model vs serving non-determinism | `--repeat-policy nested --repeat-environments E` |
| **E1/B3** | order coverage at n ≤ 6 | `FW_Permut` (n! is affordable there) |

Thirteen of forty-eight need **no engineering at all**. Worked siblings already exist:
`llm_selfposed_bundle_tasks/16_security_redteam_matrix`, `10_feature_flag_interaction`,
`02_optional_queue_saga`, `12_fallback_sequence_permutr`.

### Tier 1 — control-plane addition (Python; no Java)

| # | Proposal | What to add |
|---|---|---|
| **B1** | **`FW_Cover(t)`** | The one genuinely missing verb. `FW_Combi/CombiR/Permut/PermutR/Subsets/Cartes/Group/brace/Optional` all **generate**; none **reduces to strength t**. `fwgen.nwise_greedy` / `nwise_optimal` exist but sit pre-Core and are unreachable from `FW_Seq`. Measured need: 165,888 → **30** at t=2, **131** at t=3. |
| **B3** | `FW_SeqCover(t)` | sequence covering arrays. Measured: 16 events, all 3-way orderings, **20 tests** vs 2.09 × 10¹³ |
| **C1** | distributional orbit verdicts | compare answer *distributions* at K>1, not digests (~40 lines, `invariance.py`) |
| **C3** | K from a formula; SPRT per cell | extends the existing `min_winner_support` idea from selection into sampling |
| **C2/C4/C5** | FDR, variance components, Sobol' | analysis layer over the metrics corpus |
| **B4** | screening designs | a `fwgen` mode (Plackett–Burman / resolution-IV) before full crossing |
| **B7/I8** | cost-weighted design, adaptive strength | budget-aware selection; escalate t only in failing subspaces (`bundle iterate` / BundleSeed) |

### Tier 2 — genuine engine work

| # | Proposal | Why it is engine-level |
|---|---|---|
| — | **distribution-aware repeats in the Analyzer** | Today K>1 arrives as *more rows*. A stochastic target needs the Pareto front computed over per-cell **distributions** (mean + dispersion), not over replicated points. This is the one real architectural gap for black-box AI, and it is the thing that would let `transformers_sweep_288`-grade analysis apply to a non-deterministic target. |
| **C6** | locating arrays | could be control-plane, but the *count/budget* integration is engine-side |
| — | **lightweight execution transport** | keep Core+Reader assembly; allow an in-process executor for candidates whose "execution" is one network call, emitting the same metrics KV. Check first whether `--candidate-sink grpc` + `--executor-pool` already covers this. |

### Tier 3 — application layer (this directory), engine-neutral

`A1` DIR relations · `A2` **EQV / equivariance** · `A5` differential oracle · `A6` semantic entropy ·
`A7` self-consistency as a deployment result · `A8` calibration vs orbit agreement · `A9` sycophancy ·
`D1` difficulty covariates · `D2` constraint-graph structure · `D6` structured-output suite ·
`G1` needle grid · `G2` chunk attribution · `H1` graded verdicts · `H2` judge-as-factor ·
`H3` Latin squares · `I1` benchmark coverage measurement · `I2` drift monitor · `I5` evidence pack ·
`I7` surface-form invariance.

These are oracle and reporting work. They do not touch the engine and should not wait on it.

### Tier 4 — poor fit; do in Python or not at all

`B5` group testing (d-disjunctness is a property of the *design matrix*, not a bond the sieve
states naturally) · `B6` isomorph-free generation (needs canonical forms; a pre-Core pass) ·
`E4` partial-order reduction (trace equivalence is not a Bundle concept).

## 4. Revised build order

| # | Item | Tier | Why here |
|---|---|---|---|
| **1** | Fix the evidence chain: wire `adapters/browser.py` into `registry.py`/`config.example.json`, and either commit `run_model_k3.py` or retract the reproduction claim in `FINDINGS` §6 | app | The project's pitch is checkability; its one real-model result is currently not reproducible |
| **2** | **C1** distributional orbit verdicts | T1 | Every invariance number is uninterpretable at K>1 today |
| **3** | **D1** difficulty covariates | T3 | The capability curve currently measures the generator |
| **4** | **Re-author one scenario fragment-first** — port the `redteam3` pattern into `AI_combi_testing_platform` | T0 | Proves §1's rule and unlocks all thirteen Tier-0 items at once |
| **5** | **B1 `FW_Cover(t)`** | T1 | The missing verb; 5,529× on presentation; makes everything expensive affordable |
| **6** | **A2** equivariance relations | T3 | Strictly stronger than the six INV relations; gives contamination probe **D4** free |
| **7** | Turn on `--repeat-policy nested` and measure **I6** | T0 | Zero build cost; may reallocate a large share of the measured 0.861 |
| **8** | **C3** K-from-a-formula + SPRT | T1 | Makes multiplicative cost survivable |
| **9** | **D6** structured-output suite | T3 | 54 % of the live target's failures were format, not reasoning |
| **10** | **B3** `FW_SeqCover(t)` | T1 | The only route to n ≥ 8 order coverage |
| **11** | Analyzer distribution-aware repeats | T2 | The one real Java ask; unblocks Pareto on stochastic targets |

## 5. What I would stop doing

- **Stop treating `AI_combi_testing_platform` as the demonstration of Bundle AI capability.** The
  stronger demonstrations already exist — `transformers_sweep_288` (formal Pareto over a real
  trained-model sweep) and `llm_loop/redteam3` (positional combinatorial red-team). This directory's
  distinctive asset is its **oracle and evidence discipline**, not its use of the engine.
- **Stop writing sheet values as setter statements.** See §1.
- **Stop expecting `FW_ReplaceRE` to touch prompt text.** It rewrites `Short` code-strings. Prompt
  templating belongs in the renderer; the Zen document records what believing otherwise cost.
- **Stop justifying engine throughput work with AI testing.** White-box sweeps justify the Executor
  on their own terms; a hosted-model target at 0.06 req/s never will.

## 6. The honest gap that remains

The Bundle is a **deterministic** combinatorial dataflow engine: verbs build a space, bonds prune it,
an oracle judges each candidate, the Analyzer optimises over rows. Black-box AI testing violates the
deterministic assumption at the leaf — the same candidate has a *distribution* of outcomes, and the
platform measured that distribution's width at 0.861.

Everything in Tier 1 and the Analyzer item in Tier 2 is, in the end, one request: **make
distribution a first-class citizen of the result row.** `--repeat K` puts the samples in the corpus;
nothing downstream yet knows they are samples of one thing. That is the single change that would
make the engine as strong for stochastic targets as `transformers_sweep_288` shows it already is for
deterministic ones.

---

## 7. Corrections and caveats *(added on review, 2026-08-08)*

The verified claims above stand — `--repeat-policy nested` (`config.py:26,52-53,249-253`),
`Map<Short, List<Short>>` (ZEN §242 → `SheetWorker.java:600`), the campaign trees, and `redteam3`'s
multi-`FW_Optional` placement were all re-checked independently. Three things need correcting or
qualifying.

### 7.1 B1 is **plumbing, not a missing verb** — t-wise already exists and is tested

§3 Tier 1 calls `FW_Cover(t)` "the one genuinely missing verb". That overstates it. `fwgen.py`
already carries a complete, tested covering-array facility:

| What exists | Where |
|---|---|
| `nwise_greedy(combos, n)` — streaming greedy, one pass | `fwgen.py:1251` |
| `nwise_optimal(combos, n)` — two-pass minimum set cover | `fwgen.py:1271` |
| `reduce_combos(combos, n, optimal)` — dispatcher | `fwgen.py:1308` |
| **`pick_n_for_budget(spec, budget, optimal, hard_cap)`** | `fwgen.py:1312` |
| correctness test: reduced **and still t-complete** | `test_fwgen.py:291` (`_all_pairs(red) == target`) |
| worked example at 9 dimensions | `run_full_pairwise_bundle.py:170` |

The module's own docstring already advertises "OPT-IN N-wise covering-array". So the work is **not**
implementing a verb — it is exposing what is there: a spec key and a CLI flag. Neither
`fwgen_cli.py` nor `bundle/cliargs.py` currently has one.

**`pick_n_for_budget` also settles B7/I8.** Its docstring — *"choose the MOST thorough coverage that
fits `budget`"*, refusing beyond a hard cap — is cost-weighted design with adaptive strength,
already written. §3 files that as future work.

This is the same error this document diagnoses in its own predecessor: treating as future work
something the engine already does. It is easy to make and worth naming rather than quietly fixing.

**Consequence for the build order:** the item that changes the economics is not a Tier-1 build, it
is a wiring job measured in hours. It should move to the front (§8).

### 7.2 Tier 0's confidence is *inferred*, not demonstrated

"Thirteen of forty-eight need no engineering at all" is derived from engine capability, not from a
run. In this project's own evidence vocabulary that is **Grade C** (source-contract), not Grade A.

There is also an internal tension: Tier 0 is labelled "spec-only, no code change", while build-order
item 4 — re-authoring one scenario fragment-first — is what "unlocks all thirteen Tier-0 items at
once". So Tier 0 is gated on a pattern port that has not happened yet.

Neither observation undermines the analysis. Both mean the claim should be graded honestly until one
scenario has actually been re-authored and run.

### 7.3 Two limits that "distribution as a first-class citizen" does **not** remove

§6 correctly identifies stochasticity as the architectural gap. Two further limits sit outside it and
should not be absorbed into it:

**Cost is the binding constraint, not expressiveness.** At ~20 s per hosted request (measured:
108 requests = 29.3 min), the multiplicative grid `tasks × presentations × K × environments × models`
prices out long before the engine runs out of verbs. This is why §7.1 matters more than its position
in the original ordering suggested — t-wise reduction is the only lever that changes the arithmetic.

**Provider drift breaks reproducibility at a level no engine change reaches.** `--repeat-policy
nested` separates model variance from serving variance; nothing separates *"the provider replaced the
model in March"*. The Bundle's strongest property is exact reproducibility — re-verified this month
when a two-month-old flagship run reproduced `288 / pass 150 / fail 138` digit-for-digit. On a hosted
target that property is unattainable **in principle**, not merely unimplemented. Every hosted result
is therefore evidence about *a target on a date*, and the evidence pack (I5) should record the model
label, the date, and the account as part of the result — not as metadata about it.

Neither limit argues against the plan. They argue for stating what a hosted-model number can and
cannot support, which is exactly the discipline this project applies everywhere else.

---

## 8. How we will actually test request→response with the engine

**Constraint: the engine must do the work.** Everything built in this directory so far — including
the metamorphic orbits — computes its combinatorics in Python and uses Bundle as a runner. The
orbits are enumerated with `itertools.product` and grouped post-hoc in reporting, when §1's rule says
`FW_Permut` over an invariant axis *is* the equivalence class. Each stage below is judged by one
question: **would it still work if the Python glue were deleted?**

Stages 0–3 are prerequisites, not features: until they land, every study number is either
unaffordable or uninterpretable.

### Stage 0 — expose t-wise · *hours* · unblocks everything

Wire what §7.1 found: a spec key (`coverage_strength = 2`) and a CLI flag (`--coverage-strength t`,
`--coverage-budget N`) onto `reduce_combos` / `pick_n_for_budget`, applied **pre-Core** in `fwgen`
so `fw_final` is already reduced and the whole downstream chain is unchanged.

*Proves:* the grid is affordable. *Done when:* `plan` reports both the full product and the reduced
count, and `test_fwgen.py:291`'s completeness assertion still passes on a spec-driven run.
*Why first:* nothing else in this list is affordable at full crossing against a metered target.

### Stage 1 — re-author one scenario fragment-first · *1–2 days* · proves §1

Port the `redteam3` pattern into this directory. Concretely, replace setter values:

```python
PLAN.instruction_order = "task_first"      # engine sees an enum label
```

with prompt fragments as sheet values, so the engine owns assembly:

```
sheet TASK_BLOCK      : the task statement fragment
sheet RULES_BLOCK     : the constraint block fragment
sheet FILLER          : FW_Optional  -> placed at every position, every subset
sheet DISTRACTOR      : FW_Optional
FW_Permut over the section sheets   -> section order is the engine's, not a flag
sieve pos             -> "rules never before task", "filler never in slot 0"
```

*Proves:* the rule, and unlocks the thirteen Tier-0 items at once. *Done when:* the same study
reproduces with the renderer reduced to per-fragment templating and no ordering logic. *Grade note:*
this is what moves Tier 0 from Grade C to Grade A (§7.2).

### Stage 2 — stability first, as protocol · *1 run* · zero build

Measured instability was **0.861** — 31 of 36 cells disagreed across three identical repeats, six
gave three distinct answers in three tries. At that level fragility and invariance are re-measuring
non-determinism, so **no study result may be interpreted before its stability is known**.

Run `--repeat-policy nested --repeat-environments E` (I6) to split model variance from serving
variance. *Done when:* every study reports instability alongside its headline number, and the runner
refuses to print a fragility figure without one.

### Stage 3 — distribution-first result rows · *~40 lines + Analyzer* · C1

Today K>1 arrives as *more rows*; nothing downstream knows they are samples of one thing. Orbit
verdicts must compare per-cell **distributions** (majority, dispersion, agreement rate), not digests.

*Proves:* invariance becomes interpretable at K>1. *Done when:* the same corpus yields a
presentation-sensitivity number that does not move when only K changes.

---

Studies below become meaningful only after 0–3.

### Stage 4 — agentic order + fault injection · **highest value**

The single most striking number in this repository is the tutor SUT's **120 of 144 orderings
violate**; the `dispatch` family reproduced 23 of 24 degrading. Order is where agentic systems fail,
and it is exactly what `FW_Permut` + `FW_Optional` were built for.

```
sheet TURN_k          : each turn's content as a fragment
FW_Permut over turns  : delivery order is the variable
sheet TOOL_FAIL_k     : FW_Optional -> "tool times out at step k", every position × subset
sieve when            : forbid impossible traces (a retry before its call)
FW_SeqCover / t-wise  : n! is affordable only with Stage 0
```

*Oracle:* final state is exactly simulable, so the verdict stays exact while the question stops
being static. *Why highest value:* it is where the industry has no rigour, and where the engine's
native verbs map one-to-one onto the failure mode.

### Stage 5 — attack × defense as an engine join

Replace the hand-written 4×4 built in Python with a **brace** joining two result tables (attack rows
× defense rows), with `pos` constraining placement. `redteam3` already proves the pattern at
8 × 2³ = 64, 56/64 breach.

*Proves:* second-order composition on a real target, with an exact denominator over pairings.

### Stage 6 — the oracle escape: metamorphic on unscoreable tasks

This is the scope argument §7.3 says must not be folded into the stochasticity one. Orbits need no
ground truth, so they reach summarisation, code and RAG — tasks no exact solver settles.

Prerequisite: **graded verdicts kept distinct from exact ones** (`EXACT_PASS` vs
`GRADED_PASS(confidence)`, proposal H1). Without it an LLM-judge result silently reads as exact and
the evidence grade rots — the same discipline the framework already applies to `EXACT`/`BOUNDED`
cardinality.

*Done when:* a summarisation study reports invariance with no expected answer anywhere in the chain.

### Stage 7 — routing as a Pareto answer

Goals already include `correct`, `latency_us`, `cost_microusd`; add stability as a fourth objective
and let the Analyzer's non-dominated front answer *"which model × prompt × schema for this task
class"*. `transformers_sweep_288` shows the machinery works on deterministic targets; Stage 3 is what
makes it apply to stochastic ones.

### Order, and why

| | Stage | Gate it removes |
|---|---|---|
| 1 | t-wise wiring | cost — everything else is unaffordable at full crossing |
| 2 | fragment-first re-author | the engine is otherwise an enum picker |
| 3 | stability protocol | every other number is uninterpretable |
| 4 | distribution-first rows | K>1 is currently just more rows |
| 5 | agentic order + faults | highest-value study |
| 6 | attack × defense join | proves second-order on a real target |
| 7 | oracle escape (needs H1) | removes the "only scoreable tasks" ceiling |
| 8 | Pareto routing | the procurement answer |

**Format first, though.** 54% of the live target's failures were output-contract violations, not
reasoning (58 format vs 10 wrong of 108). D6 (structured-output suite) is cheap and would recover
most of the measured gap without touching models — worth doing alongside Stage 0.

### What would falsify this plan

If Stage 1 shows that fragment-first assembly cannot express a realistic prompt — because real
prompts need conditional text the algebra cannot reach (§0.2: codes and positions, never text) —
then the honest conclusion is that Bundle is the right engine for **white-box** AI work and for
**assembly-shaped** black-box work (injection, turn order, tool faults), and that ordinary prompt-CI
belongs in a cheaper harness. That would be a real finding, and Stage 1 is deliberately the earliest
cheap step that can produce it.
