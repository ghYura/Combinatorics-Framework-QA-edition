<log>
  1. Analysis — and two things the audit turned up

  I read the full tree (8,157 LOC, 115 tests green in 2.5s) and ran two probes. Both found problems that aren't in
  the existing docs:

  The capability ladder isn't monotone in difficulty. FINDINGS_TARGET_MODEL §3.4 reports pass rates of 0.333 / 0.472 /
  0.306 at complexity 3/4/5 and concludes "task size is not the driver." The real story is in
  task_ir/model.py:_ordering_task — odd→even steps add a constraint at fixed entity count (answer gets more
  determined, easier), even→odd steps add an entity (permutation space multiplies). I counted valid orderings per
  level:

  ┌────────────────────────┬──────┬───────┬───────┬───────┬──────┐
  │       complexity       │  2   │   3   │   4   │   5   │  6   │
  ├────────────────────────┼──────┼───────┼───────┼───────┼──────┤
  │ mean # valid orderings │ 2.00 │ 5.00  │ 3.67  │ 8.33  │ 6.33 │
  ├────────────────────────┼──────┼───────┼───────┼───────┼──────┤
  │ measured pass rate     │ —    │ 0.333 │ 0.472 │ 0.306 │ —    │
  └────────────────────────┴──────┴───────┴───────┴───────┴──────┘

  It zigzags, and the three measured pass rates are exactly inversely ordered to it. The ceiling detector is working
  correctly; the axis it sweeps isn't a difficulty axis. solution_count is free — the oracle already enumerates
  permutations.

  The presentation space is enumerated exhaustively when it needn't be. 11 axes = 165,888 renderings per task, run
  as a full Cartesian. I computed covering arrays over exactly those axes: t=2 → 30 tests, t=3 → 131. That's a
  5,529× reduction with all pairs covered. And fwgen.nwise_greedy/nwise_optimal plus the forbidden-tuple sieve
  already exist one directory up — the AI platform imports neither. This is wiring, not research.

  Third, from the sequence side: 16 tool calls, every 3-way ordering covered, 20 tests vs 2×10¹³ exhaustive. That's
  the answer to the "cost is multiplicative" limit.

  2. The catalogue — 48 proposals

  Organized by the six jobs combinatorics does (denominator / oracle / compression / attribution / anti-memorization
  / schedule), in nine families: new verdict sources (9), design compression (7), attribution & statistics (7),
  task-space (6), sequence & agents (6), adversarial (5), retrieval (4), judges (4), programme-level (8). Each
  tagged established-research / extension / new-here, with cost and risk.

  3. What I'd build, in order

  The top three all fix measurements that are currently wrong, not missing:

  1. Distributional orbit verdicts — at K>1, orbit members must be compared as distributions, not digests. With
  measured instability at 0.861, the 0.804 invariance figure is uninterpretable, which the findings doc says as a
  caveat but treats as unfixable. ~40 lines in invariance.py.
  2. Difficulty covariates replacing the complexity integer.
  3. FW_Cover(t) — unlocks everything expensive below it.

  Then: equivariance relations (rename entities, the answer must transform by the same permutation — strictly
  stronger than the six invariance relations, nearly free, and gives a contamination probe for nothing);
  K-from-a-formula with SPRT per cell; a structured-output sub-suite (54% of the live target's failures were format,
  not reasoning); sequence covering arrays; graded verdicts; verifiable-constraint tasks — the actual route past
  the exactly-solvable ceiling, since content needn't be checkable if the constraints are.

  Two things I'd flag: the NIST interaction rule ("t=2 catches most faults") is empirical from conventional software
  and nobody has established LLM failures obey it — I've written it as a hypothesis your own escalation data tests,
  not an assumption. And the neuron-coverage literature is a cautionary tale worth keeping in view: coverage has to
  earn its correlation with fault-finding on your task, not inherit it.
</log>

# Combinatorial methods for testing AI — analysis, catalogue, and build order

**Status: proposal.** Nothing here is built. Part I is an audit of what *is* built, and every number
in it was measured against this tree today, not recalled. Parts II–IV are the catalogue the task
asked for: 48 proposals, each marked as established research, an extension of published work, or new
here.

**Provenance note.** Citations are from model memory and are named so they can be checked. Verify
each before any of this is published externally. The measured numbers (§1.3–§1.5) are reproducible
from this repository and the probe scripts are described inline.

---

# Part I — What is here

## 1.1 The shape of the platform

```
task_ir  →  oracle  →  renderer  →  prompt-program IR  →  adapter  →  parser+oracle  →  metrics  →  Analyzer
(3 families)        (never sees answer)  (recursive)    (2 controls + 2 real)
```

Verified by reading: 8,157 LOC, 115 tests passing in 2.5 s, zero network on the default path.

| Layer | What exists | Ceiling |
|---|---|---|
| **Task space** | `ordering`, `cancellation`, `dispatch`; axes = (family, seed, complexity 1–8, semantic_mode) | one integer `complexity` conflates several difficulty dimensions — see §1.3 |
| **Presentation space** | 11 axes, 165,888 combinations per task | enumerated by **full Cartesian**; no t-way reduction — see §1.4 |
| **Verdict sources** | ① exact oracle ② metamorphic orbits (`invariance.py`) | both are point-valued; ② is confounded by non-determinism — see §1.6 |
| **Failure attribution** | capability / fragility / stability + 2-factor `interaction_map` | 2 factors only, needs a complete grid, no statistical control |
| **Adversarial** | 3 injections × 4 defenses, exact-answer scoring | 12 cells, hand-enumerated |
| **Sequence/agentic** | `dispatch` family, 5 actions | delivery order is *derived from the seed*, not swept |
| **Evidence discipline** | controls labelled, singletons excluded, denominators stated, limits published | genuinely strong — this is the part worth preserving |

The intellectual core is already right, and it is stated in `DESIGN_ADVANCED_COMBINATIONS.md` §2:
**a combinatorially generated space knows by construction which of its points must agree, so the
design is itself an oracle.** Everything below either sharpens that claim or extends it.

## 1.2 The stated ceiling, restated precisely

> A target can only be tested on questions someone can independently answer.

`invariance.py` lifts this halfway: orbit verdicts need no ground truth. But the orbit answers a
*weaker* question (did these agree?) and cannot answer *was it right*. The catalogue's family **A**
is entirely about adding more verdict sources between those two poles.

## 1.3 Finding — the capability ladder is not monotone in difficulty (verified)

`FINDINGS_TARGET_MODEL_2026-08-06.md` §3.4 reports pass rates of **0.333 / 0.472 / 0.306** at
complexity 3 / 4 / 5 and concludes "task size is not the driver here". The truth is stronger and
more actionable: **task size was never varied monotonically.**

From `task_ir/model.py:_ordering_task`:

```python
count            = min(6, 3 + (complexity - 1) // 2)   # entities
constraint_count = min(max(1, complexity), C(count, 2))  # constraints
```

Odd→even steps add a *constraint* at fixed entity count, which makes the answer **more** determined.
Even→odd steps add an *entity*, multiplying the permutation space. The ladder therefore alternates
harder/easier. Measured over the three seeds used in the live run (probe: enumerate all
permutations, count those satisfying every constraint):

| complexity | entities | constraints | permutations | **mean # valid orderings** | measured pass rate |
|---:|---:|---:|---:|---:|---:|
| 2 | 3 | 2 | 6 | 2.00 | — |
| 3 | 4 | 3 | 24 | **5.00** | 0.333 |
| 4 | 4 | 4 | 24 | **3.67** | **0.472** |
| 5 | 5 | 5 | 120 | **8.33** | 0.306 |
| 6 | 5 | 6 | 120 | 6.33 | — |

The valid-ordering count zigzags 2.00 → 5.00 → 3.67 → 8.33 → 6.33, and the three measured pass rates
are **exactly inversely ordered to it**. With three levels this is suggestive rather than conclusive
as a correlation — but the non-monotonicity of the ladder is a structural fact about the generator,
not a correlation at all.

Two conflated skills are hiding here: *find a feasible order* and *select the alphabetically minimal
one among several*. The second is only exercised when the valid set is large, and its strength
varies non-monotonically with `complexity`.

**Consequence.** The ceiling detector is behaving correctly; the axis it sweeps is not a difficulty
axis. Fix in §D1 — the oracle already enumerates permutations, so counting the valid ones is free.

## 1.4 Finding — the presentation space is enumerated exhaustively when it need not be (verified)

Eleven presentation axes (`renderers/core.py:RenderingPlan`): 3·4·2·2·3·3·3·4·2·4·4 =
**165,888 renderings per task**. Every scenario uses `FW_Combi(1)` per sheet, so `fw_final` is the
full Cartesian of whatever subset is enabled.

Computed today with an AETG-style greedy over exactly those axes (a production tool such as ACTS
would do 15–20 % better):

| strength | tests for 100 % coverage | share of full factorial | reduction |
|---|---:|---:|---:|
| **t = 2** (all pairs) | **30** | 0.018 % | 5,529 × |
| **t = 3** (all triples) | **131** | 0.079 % | 1,266 × |

The framework **already has this machinery one floor up** and the AI platform imports neither:

- `generator_trunk/fwgen.py` — `nwise_greedy(combos, n)`, `nwise_optimal(combos, n)` (set-cover);
- `generator_trunk/constraints/sieve.py` — forbidden tuples, conditions, mappings, ordering, optional
  bonds; this is exactly the *constrained* covering-array requirement.

So "add covering arrays" is wiring, not research. This is the single highest-leverage change in the
document, because every expensive proposal below becomes affordable once the presentation axis stops
costing 165,888.

## 1.5 Finding — the sequence axis is where the cost explodes, and it compresses best

`dispatch` derives one delivery order per seed. Real agentic testing needs order *coverage*. Computed
today (greedy sequence covering arrays; matches the logarithmic growth reported by Kuhn et al.):

| events | exhaustive n! | t = 2 | **t = 3** | reduction at t=3 |
|---:|---:|---:|---:|---:|
| 5 | 120 | 2 | 9 | 13 × |
| 8 | 40,320 | 3 | **13** | 3,101 × |
| 10 | 3,628,800 | 3 | 16 | 226,800 × |
| 12 | 479,001,600 | 4 | 18 | 26,611,200 × |
| 16 | 2.09 × 10¹³ | 4 | **20** | 1.05 × 10¹² × |

**Sixteen tool calls, every 3-way ordering covered, twenty tests.** This is the answer to the "cost is
multiplicative" limit in `DESIGN_ADVANCED_COMBINATIONS.md` §8, and it is the strongest single argument
for combinatorial design over sampling in the agentic setting.

## 1.6 Finding — orbit verdicts are point comparisons, and the platform's own data says that is unsafe

`invariance.py:evaluate_orbits` groups digests and reports `VIOLATED` iff `distinct_answers > 1`.
With measured instability of **0.861**, two orbit members differ most of the time *for reasons that
have nothing to do with the axis being varied*. `FINDINGS` §3.2 states this as a caveat. It is
repairable by design: compare **distributions**, not points (§C1).

## 1.7 Five smaller gaps found by reading

1. **All six relations are invariance (INV). Zero directional (DIR), zero equivariance (EQV).**
   CheckList's taxonomy has all three; the two missing kinds are cheaper and catch different bugs (§A1, §A2).
2. **`constraints_met` is computed per-constraint then collapsed to a boolean.** The per-constraint
   vector would attribute failures to prompt position for free (§C6).
3. **`semantic_mode` is in `TASK_IDENTITY_FIELDS`**, correctly — but there is no *neutral relabelling*
   axis, which is the equivariance test and the contamination probe (§A2, §D4).
4. **Repeats have no design.** `stability_profile` finds repeats if they happen to exist; nothing
   allocates K, and nothing tells the operator what K is needed (§C3).
5. **No multiple-comparison control.** A 20-cell interaction map on a stochastic target will report
   interaction-only failures that are noise (§C2).

---

# Part II — What combinatorics actually buys you

Forty-eight proposals is a pile unless they are organised by *job*. Six jobs:

| | Job | The question it answers | Failure if you skip it |
|---|---|---|---|
| **R1** | **Denominator** | out of *what* did you test this many? | "we tried some jailbreaks and none worked" |
| **R2** | **Oracle** | who says the answer is wrong? | you can only test exactly-solvable tasks |
| **R3** | **Compression** | same evidence, affordable | exhaustive is unaffordable, sampling has no guarantee |
| **R4** | **Attribution** | *which* factor, or which pair, broke it? | one number, three causes, no action |
| **R5** | **Anti-memorisation** | is this capability or recall? | benchmark contamination |
| **R6** | **Schedule** | what do I test next, and when do I stop? | budget spent on cells that were already decided |

Every proposal below is tagged with the jobs it does.

---

# Part III — The catalogue

Legend: **[R]** = established research · **[X]** = extension of published work · **[N]** = new here.
Cost is engineering effort in this repo: **S** ≤ 1 day, **M** ≈ a week, **L** > a week.

## A. New verdict sources — lifting the exactly-solvable ceiling

### A1 · Directional metamorphic relations (DIR) — [R] · S · R2 R4
Invariance says "must not change". Directional says "must change *this way*". Adding a constraint to
an ordering task can only shrink the valid set, so the previous answer must either remain the answer
or become infeasible — checkable without solving. Deleting a constraint must keep the old answer
valid. For `cancellation`, increasing `inverse_depth` is invariant, but changing `symbol_value`
predicts an exact new value. CheckList (Ribeiro et al., ACL 2020) calls these DIR tests; the platform
has none.
*Risk:* a wrong direction manufactures violations — same authoring discipline as INV.

### A2 · Equivariance relations (EQV) — the group actually acts on the answer — [X] · S · R2 R4 R5
Rename `Aster→Zephyr` everywhere. The answer must not stay the same — it must **transform by the
same permutation**. This is strictly stronger than invariance and much more informative: it catches
label bias, position bias, and memorisation in one relation, and it is nearly free because
`_stable_order(names, seed, ...)` already parameterises the naming. Formally: the presentation axes
generate a group *G*; invariance asserts the action on answers is trivial; equivariance asserts it is
the induced action. Orbit–stabiliser then gives orbit sizes for free, and Burnside's lemma dedupes
the design.
*This is the highest value-per-line item in the document.*

### A3 · Verifiable-constraint tasks restore an exact oracle for open-ended text — [R] · M · R2
IFEval's insight (Zhou et al., 2023): you cannot check whether a summary is *good*, but you can check
"≤ 120 words, no comma, contains 'therefore', valid JSON, starts with a verb" exactly. Draw *k* of
*N* verifiable constraints — `FW_Subsets` gives C(N,k) tasks with per-constraint exact verdicts, and
mutually unsatisfiable pairs are forbidden tuples for the existing sieve. **This is the cleanest
route past the §1.2 ceiling: the content need not be checkable if the constraints are.**

### A4 · Round-trip relations — [R] · M · R2
Solve → verify; translate → back-translate; NL→SQL→execute vs. NL→answer; code→tests. Each converts
an unoracled task into a checkable one. Combinatorial version: the forward and backward phrasings are
each an axis, and the orbit is over their cross product, so a round-trip failure is attributable to a
direction.

### A5 · Differential testing across models as an oracle — [R] · M · R2 R4
N-version programming. Five models agree, one dissents → candidate defect with no ground truth. Cross
with A2/§C1 to get a 2×2 that names the finding:

| | orbit consistent | orbit violated |
|---|---|---|
| **models agree** | probably correct | shared blind spot / ambiguous task |
| **models disagree** | genuine capability gap | **unreliable — do not deploy this cell** |

### A6 · Semantic entropy over the orbit — graded, not binary — [X] · M · R2 R4
Farquhar et al. (Nature 2024) cluster generations by semantic equivalence and take the entropy.
Applied to an orbit this replaces `distinct_answers > 1` with a real-valued disagreement measure —
which is what makes §2 of the design doc pointable at fuzzy tasks, and what makes `GRADED_PASS` (§H1)
implementable honestly.

### A7 · Self-consistency as a *deployment* result, not only a measurement — [N] · S · R2
`FINDINGS` §3.2 notes that per-cell **majority** answers show only 3–4 distinct values across 12
presentations while raw answers show 0.804 disagreement. That is not just a caveat — it is a
technique. Report `accuracy(orbit-majority) − accuracy(single-sample)`. The harness becomes a product
feature ("presentation-ensemble decoding") and produces a number procurement cares about.

### A8 · Confidence calibration against orbit agreement — [N] · S · R2
Ask for a confidence score; plot stated confidence against orbit agreement rate. **No ground truth
needed.** A model whose confidence does not track its own self-agreement is miscalibrated in the way
that actually hurts, and this falls out of data the orbit already produces.

### A9 · Sycophancy as a directional relation — [X] · S · R2 R4
After a correct answer, apply pressure: mild doubt / confident contradiction / claimed authority /
claimed majority. The relation is directional — a correct answer must not flip. Cross
(initial correctness × pressure type × pressure strength × whether the pressure is true). Sharma et
al. document the phenomenon; the cross product turns it into a measurement with a denominator.

## B. Design compression — the same evidence, affordably

### B1 · `FW_Cover(t)` — t-way covering arrays as a first-class verb — [R] · M · R1 R3
**The keystone.** 165,888 → 30 (t=2) or 131 (t=3), §1.4. NIST's interaction rule (Kuhn, Kacker, Lei,
SP 800-142): most faults are triggered by 1–2 factors and essentially all by ≤6, and covering-array
size grows as *v^t · log k* — logarithmic in the number of axes. Two implementation routes:
- **cheap:** post-filter `fw_final` with the existing `fwgen.nwise_optimal`;
- **proper:** a `seq_extra` verb so the reduction is part of the recorded design, with the achieved
  strength emitted as a dimension. Report **strength**, never "we sampled".

### B2 · Constrained covering arrays — [R] · S · R1 R3
Some cells are illegal (`injection=schema_hijack` with `schema=csv` is incoherent; `defense=delimit`
with `paraphrase=inverted` may be untestable). `constraints/sieve.py` already expresses forbidden
tuples. Constrained generation keeps the denominator honest instead of silently including impossible
cells.

### B3 · Sequence covering arrays — [R] · M · R1 R3
§1.5. Every *t*-way **ordering** of *n* events in O(log n) tests (Kuhn, Higdon, Lawrence, Kacker,
Lei). Applies to: dispatch delivery order, tool-call order, multi-turn constraint introduction order,
retrieved-document order, few-shot exemplar order. `FW_Permut` currently enumerates n!; this is the
verb that makes n ≥ 8 possible at all.

### B4 · Screening designs before full factorial — [R] · S · R3 R4
Eleven axes is already too many to cross with anything expensive. Plackett–Burman or a
resolution-IV fractional factorial screens 11 main effects in 12–16 runs; then cross *only* the 2–3
significant axes fully. Definitive screening designs (Jones & Nachtsheim) additionally catch
curvature. Two-phase budget: 16 screening runs + 40 focused runs beats 500 uniform ones.

### B5 · Group testing for context attribution — [X] · M · R3 R4
Which of 200 retrieved chunks poisoned the answer? Testing each is 200 calls. A *d*-disjunct pooling
matrix identifies up to *d* culprits in **O(d² log N)** — roughly 30–40 calls for N=200, d=2, and
**non-adaptively**, so it parallelises. Same machinery locates the offending few-shot exemplar, the
offending tool description, or the offending system-prompt clause. `FW_Subsets` with a disjunctness
constraint is the natural expression.

### B6 · Isomorph-free task generation — [X] · M · R3 R5
Combinatorial generators emit many instances that are isomorphic (identical up to relabelling).
Testing those wastes budget and inflates confidence. Canonical-form dedup (McKay-style canonical
augmentation) fixes it — **and the discarded isomorphs are exactly the A2 equivariance pairs.** One
piece of machinery, two uses.

### B7 · Cost-weighted design as an optimisation — [X] · M · R3 R6
Cells differ in token cost by an order of magnitude (`long_range=12` vs `0`). Maximise t-way coverage
subject to a token budget: weighted set cover, greedy gives a 1+ln(n) guarantee. Emit the chosen
design and the achieved coverage so the trade is inspectable.

## C. Attribution and statistics — making the numbers mean something

### C1 · Distributional orbit verdicts — [N] · S · R2 R4
**The most important fix in the document.** At K>1, two orbit members are in violation iff their
answer *distributions* differ by more than sampling explains — a two-sample test (exact
multinomial / permutation test), not `digest_a != digest_b`. This converts the uninterpretable 0.804
into a real number and removes the confound `FINDINGS` §3.2 correctly refuses to explain away.
~40 lines in `invariance.py`.

### C2 · False-discovery control across cells — [R] · S · R4
A 20-cell interaction map on a target with 0.861 instability will report interaction-only failures
that are noise. Benjamini–Hochberg over per-cell p-values; report only survivors, and report the
number screened. Without this, `interaction_only_share = 1.00` is not evidence.

### C3 · Tell the operator what K must be — [R] · S · R6
Nobody should guess repeats. Given a target per-cell failure probability *p*, a tolerance, and a
desired power, the required K is a formula (Clopper–Pearson / Wilson). Better: **SPRT per cell** —
stop sampling a cell as soon as its verdict is decided, and spend the saved budget on undecided
cells. This is where §8's "K multiplies everything" stops being fatal.

### C4 · Variance components instead of three hand-computed marginals — [X] · M · R4
A mixed model over (task, presentation, repeat) yields σ²_task, σ²_presentation, σ²_repeat **with
confidence intervals and without mutual confounding** — which is precisely what `decomposition.py`
approximates and what `FINDINGS` §3.2 says it cannot currently do. Same three findings, defensible.

### C5 · Sobol' indices — interaction share, properly defined — [R] · M · R4
`interaction_only_share` is a good idea with an ad-hoc definition (2 factors, needs a complete grid,
needs a designated baseline). Variance-based sensitivity gives first-order *S_i* and total-order
*S_Ti* for **all** factors at once; **S_Ti − S_i is exactly the interaction share**, defined for any
number of factors, with no baseline and no complete-grid requirement.

### C6 · Locating arrays — [R] · L · R1 R4
Colbourn & McClary: a *(d,t)*-locating array not only *detects* interaction faults but **identifies
which** interaction is at fault, for up to *d* simultaneous faults. This is the principled
generalisation of `interaction_map` and it removes the "incomplete grid → no verdict" restriction.
Pair with BEN-style fault localisation (Ghandehari, Lei, Kuhn) for ranked candidate interactions.

### C7 · Per-constraint verdict vectors — [N] · S · R4
The ordering oracle already checks each constraint; the engine collapses it to
`all_constraints_pass`. Emitting the vector lets you ask *which* constraint was dropped, and — crossed
with `constraint_order` — whether dropped constraints cluster at a prompt position. That is a
"lost in the middle" measurement for free from data already computed.

## D. Task-space combinatorics — vary the problem, not only the phrasing

### D1 · Replace `complexity` with measured difficulty covariates — [N] · S · R4 R6
Per §1.3. Emit as measurements: `entity_count`, `constraint_count`, **`solution_count`** (free — the
oracle enumerates already), `constraint_graph_shape` (chain / tree / diamond / disconnected),
`transitive_redundancy`, `answer_is_unique`. Sweep capability over these, not over one integer.
Without this the capability curve measures the generator.

### D2 · Combinatorial structure of the constraint graph — [X] · M · R1 R4
Cross graph *shape* × *density* × *redundancy* × *uniqueness*. Chains and diamonds are different
reasoning problems at identical "complexity". This is the axis that makes the capability profile a
capability *surface*.

### D3 · Skill-Mix — a combinatorial argument that capability is not recall — [R] · L · R2 R5
Yu, Arora et al.: define *N* atomic skills, ask for output exhibiting a random *k*-subset. C(N,k)
explodes past anything memorisable, so success at k=4–5 is evidence of composition rather than
lookup. **This is the most elegant idea in the field and it fits this repo's philosophy exactly** —
the combinatorics *is* the argument, not just the schedule.

### D4 · Contamination probe from the equivariance orbit — [N] · S · R5
`accuracy(canonical labelling) − mean accuracy(relabelled orbit)`. Under no memorisation this is 0.
A positive "canonical advantage" is a contamination signal, and it costs **nothing extra** once A2
exists. Complements the README's honest note that fresh generation ≠ proof of absence from training.

### D5 · Compositional-generalisation splits — [R] · M · R5
SCAN / COGS logic at the prompt level: exercise every atomic skill, hold out one *pair*, test the
held-out pair. Failure is compositional, not lexical. Naturally expressed with `FW_Subsets` + a
sieve exclusion.

### D6 · Structured-output combinatorics — [X] · M · R1 R4
The live run's dominant failure was **format (54 %)**, not reasoning. That deserves its own axis
family: schema depth × required-vs-optional fields × union types × enum cardinality × nesting ×
escaping × delimiter choice × "JSON only" phrasing. For the measured target this is the highest-yield
new sub-suite in the document.

## E. Sequence, state, and agents

### E1 · Sequence covering arrays for tool-call order — [R] · M · R1 R3
B3 applied. Report *t*-way order coverage as a first-class number.

### E2 · Sharded multi-turn prompts — set partitions × permutations — [X] · M · R1 R2
Take a single-turn prompt, split its requirements across turns, and vary **which shard goes in which
turn** (a set partition) and **in what order** (a permutation). Laban et al. show models get lost
when instructions arrive sharded. Set partitions × permutations is precisely what `FW_Subsets` +
`FW_Permut` generate — **arguably the single best fit between this engine's operators and a real,
current LLM failure mode.**

### E3 · N-switch coverage for dialogue state machines — [R] · M · R1
Chow's W-method and *N*-switch coverage give FSM testing a **fault-detection guarantee**. Model the
agent's dialogue policy as an FSM and cover all length-(N+1) transition sequences. This is decades-old
and directly transferable.

### E4 · Partial-order reduction for multi-agent interleavings — [X] · L · R3
Concurrent agents give n! interleavings, but independent actions commute. Mazurkiewicz trace
equivalence means you need **one representative per equivalence class**, not one per interleaving —
often orders of magnitude fewer. Real combinatorics doing real work.

### E5 · Combinatorial fault injection into tool responses — [X] · M · R1 R4
Cross (which tool × failure kind: timeout / malformed / empty / wrong-schema / plausible-but-wrong ×
turn index × whether a retry is available). The `dispatch` family already proves the shape; this
generalises it to real tool use. The **plausible-but-wrong** cell is the one most suites omit and the
one that matters.

### E6 · Delta debugging over prompts, with a non-adaptive parallel form — [X] · M · R4
ddmin (Zeller & Hildebrandt) minimises a failing prompt to its 1-minimal core; HDD handles structure.
The combinatorial version (B5) is non-adaptive and parallel. Ship both: ddmin when calls are serial,
group testing when they are not.

## F. Adversarial and safety

### F1 · Attack composition algebra — [X] · M · R1 R2
The 3×4 matrix asks "does attack *a* beat defense *d*". The next question is whether **composing two
individually-defeated attacks** beats a defense that stops each alone. Enumerate the pair
compositions and publish the Cayley-style table. Non-closure under composition is the finding.

### F2 · Injection-surface coverage for agents — [X] · M · R1
Indirect injection (Greshake et al.) arrives through channels, not through the user prompt. Cross
(channel: tool output / retrieved doc / filename / image alt-text / prior-turn echo / system-prompt
reflection) × (payload class) × (defense) × (available tool sensitivity) × (turn position). Reduce
with B1. Output: **attack-surface coverage with a denominator** — the artifact §6 of the design doc
is reaching for.

### F3 · Refusal-boundary mapping — both error directions — [X] · M · R1 R4
Cross (topic × framing × claimed role × specificity × obfuscation). Report **over-refusal**
(XSTest-style) and under-refusal from the same design. A single "refusal rate" hides the trade; the
surface shows it.

### F4 · Multi-turn / crescendo attacks via SCA — [X] · M · R1 R3
Escalation is an ordering problem. Sequence covering arrays over escalation steps give order coverage
at logarithmic cost, instead of the ad-hoc scripts the field currently uses.

### F5 · Systematic best-of-N — [X] · S · R1
Best-of-N jailbreaking composes random augmentations. A covering array over the same augmentation
axes gives the same attack strength **with a stated coverage** instead of a sample count.

## G. Retrieval, long context, grounding

### G1 · Needle-in-a-haystack as a designed grid, not a 2-D plot — [X] · M · R1 R4
The usual (depth × context length) plot is a 2-factor slice. The real design adds: number of needles,
distractor semantic similarity, needle-question lexical overlap, **needle absent**, contradictory
needles, needle in a different language. The *absent* cell is where hallucination is measured and it
is routinely omitted.

### G2 · Chunk-attribution by group testing — [X] · M · R4
B5 applied to RAG. "Which chunk caused it" answered in O(d² log N).

### G3 · Position/permutation invariance over retrieved documents — [X] · S · R2
Document order is a declared-invariant axis: shuffling equally relevant chunks must not change the
answer. Cheap, needs no ground truth, and directly probes "lost in the middle" (Liu et al.).

### G4 · MCQ option-permutation orbits — [X] · S · R2 R5
Permuting answer options is invariant by construction. Accuracy that drops under permutation is
position bias or memorisation (Zheng et al.; Robinson & Wingate). One of the cheapest high-signal
tests available, and it needs no new task family — only a permutation axis.

## H. Judges, graded verdicts, human evaluation

### H1 · Verdict grades kept structurally distinct — [X] · S · R2
Already flagged as a prerequisite in `DESIGN_ADVANCED_COMBINATIONS.md` §7. Make it a dimension:
`EXACT` / `METAMORPHIC` / `GRADED(confidence)` / `HUMAN`. The framework refuses to collapse `EXACT`
into `BOUNDED` for cardinality; verdicts deserve the same refusal. **Build this before pointing
orbits at fuzzy tasks**, or the evidence grade rots silently.

### H2 · The judge is a factor — cross it — [X] · M · R1 R4
(judge model × rubric phrasing × option order × whether the judge authored the candidate). Judge
invariance is measurable with the same orbit machinery. A judge that fails its own invariance test
cannot certify anything.

### H3 · Latin-square designs against position bias — [R] · S · R1 R4
LLM judges have documented position bias. A Latin square over (item × position × judge) balances it
**by construction** rather than correcting for it afterwards. Graeco-Latin squares balance a fourth
factor at no extra cost.

### H4 · Balanced incomplete block designs for pairwise comparison — [R] · M · R3
Comparing *M* models pairwise is C(M,2) × K. A BIBD gives every pair equal replication at a fraction
of the cost, and keeps the comparison graph connected so Bradley–Terry ranks stay identifiable —
which round-robin sampling does not guarantee.

## I. Programme-level

### I1 · Combinatorial coverage measurement of *existing* benchmarks — [R] · M · R1 R5
NIST's CCM turned around: extract factors from MMLU / GSM8K / your own eval set, measure achieved
t-way coverage, report the holes, then generate tests **for the holes**. Lanus, Freeman, Kuhn & Kacker
show input-space coverage predicts generalisation gaps. Deliverable sentence: *"your suite covers
61 % of 2-way combinations of (domain × format × reasoning depth × language); here are the 39 % you
never test."* This is a product, not a feature.

### I2 · Provider-drift monitor — [N] · S · R1 R6
`README` §Interpretation limits: "providers change models under you." A fixed covering array re-run
on a schedule gives a **diff with a denominator** — which cells flipped, out of how many — instead of
an anecdote. Cheap (30 cells at t=2), and the most immediately saleable item here.

### I3 · Coverage-driven eval-set selection — [X] · M · R3
tinyBenchmarks and Anchor Points select representative subsets by IRT. A covering-array selection
rule ("cover every 2-way combination of item features") is cheaper to compute, easier to justify, and
composes with the rest of this framework.

### I4 · k-path coverage of the prompt-program grammar — [N] · M · R1
`renderers/program.py` builds a recursive `PromptNode` tree and the Bundle supports arbitrarily
nested braces — but there is **no coverage criterion for that tree**. Havrikov & Zeller's k-path
coverage over grammar derivations is the right one. This gives the higher-order brace machinery, the
framework's most distinctive feature, a number it currently lacks.

### I5 · The evidence pack as the deliverable — [N] · S · R1
Ship design + achieved coverage + constraints + results + limits as one signed artifact. The repo
already behaves this way; naming it makes it reviewable. A reviewer's first question is always the
denominator, and this is the only document that has it.

### I6 · Separate model non-determinism from serving non-determinism — [X] · M · R4
Measured instability was 0.861 — but some of that is inference-stack batching, not the model. Cross
(temperature × top_p × seed × batch position × endpoint × time-of-day). Recent work attributes much
LLM non-determinism to batch-size-dependent kernels rather than sampling. If half of that 0.861 is
serving, every downstream number changes.

### I7 · Surface-form invariance at the tokenizer boundary — [X] · S · R2
Same semantics, different bytes: casing, whitespace, unicode homoglyphs, markdown emphasis, smart
quotes, NBSP. A legitimate invariance axis that finds real bugs cheaply. Frame it as surface-form
robustness — **not** as a claim that tokenization makes tasks exponentially harder, which the README
already and correctly rejects.

### I8 · Adaptive strength escalation — [X] · M · R6
Start at t=2 everywhere. Where failures appear, escalate to t=3 **in that subspace only**. Spends
budget where the evidence is, and the achieved strength is per-subspace and reportable.

---

# Part IV — What I would actually build, in order

Ranked by (evidence gained) ÷ (effort), given what already exists here.

| # | Proposal | Why first | Effort | Evidence it produces |
|---|---|---|---|---|
| **1** | **C1** distributional orbit verdicts | Every invariance number is currently uninterpretable at K>1, and the platform's own data proves it | S | 0.804 → a defensible figure |
| **2** | **D1** difficulty covariates | §1.3 — the capability curve currently measures the generator | S | a capability ladder that is one |
| **3** | **B1** `FW_Cover(t)` | 5,529× on presentation; unlocks every expensive item below; the code exists one floor up | M | strength-t coverage with a denominator |
| **4** | **A2** equivariance relations | Strictly stronger than the six INV relations, nearly free, and gives D4 for nothing | S | label bias + memorisation, one axis |
| **5** | **C3** K from a formula, SPRT per cell | Makes multiplicative cost survivable; without it K is a guess | S | "K=7 here, K=2 there", justified |
| **6** | **D6** structured-output sub-suite | 54 % of the measured target's failures were format | M | the finding that actually fixes that target |
| **7** | **B3/E1** sequence covering arrays | 16 events, 3-way order coverage, 20 tests (§1.5) | M | agentic order coverage at all |
| **8** | **H1** graded verdicts | Prerequisite before orbits point at fuzzy tasks — stated in the design doc, still open | S | evidence grade that cannot rot |
| **9** | **A3** verifiable-constraint tasks | The actual route past the exactly-solvable ceiling | M | exact verdicts on open-ended generation |
| **10** | **I2** provider-drift monitor | Cheapest thing here with an external customer | S | a diff with a denominator |

Then, as a second wave: **A5** differential oracle, **E2** sharded multi-turn, **C4/C5** variance
components and Sobol', **F2** injection-surface coverage, **I1** benchmark coverage measurement.

**Sequencing constraint worth stating:** 1, 2 and 5 come before everything else because they fix
*measurements that are currently wrong*, not measurements that are missing. `FINDINGS` §3.2 already
established the rule — stability bounds what every other number can mean — and the same logic applies
to the difficulty axis: a ladder that is not monotone cannot yield a ceiling.

---

# Part V — Honest limits of this whole programme

1. **A relation that is not a relation turns every result into noise.** This is the dominant risk in
   family A, it is authoring judgement, and no engine supplies it. `invariance.py` already gets this
   right by *excluding* `contradictory` and `inverted`; every new relation needs the same argument
   written down next to it.
2. **Coverage is not correlated with fault detection by default.** The neural-network coverage
   literature (DeepXplore, DeepGauge, DeepCT) is a cautionary tale: neuron coverage was shown to
   correlate weakly or not at all with defect finding (Harel-Canada et al.). *Input-space* t-way
   coverage over semantically meaningful factors has better empirical support than *internal-state*
   coverage — but coverage still has to earn its correlation on your task, not inherit it.
3. **t-way strength is an assumption.** The NIST interaction rule is empirical, drawn largely from
   conventional software. Nobody has established that LLM failures obey it. Report achieved strength
   and treat "t=2 suffices" as a hypothesis your own escalation data (I8) tests.
4. **Non-determinism multiplies everything by K before any cell is trustworthy**, and I6 suggests
   some of that K is not even the model.
5. **Cost stays multiplicative.** B1/B3/B4/B7 change the exponent, not the fact. The two-phase
   pattern — exhaustive on a cheap proxy, targeted on the expensive target — remains the only way to
   afford this.
6. **Every measured number in this repository is still a control** except the one the target model run, and
   that run was one account, one day, one task family, through a UI that can change without notice.
7. **More statistics is not more truth.** C2/C4/C5 add rigour and add ways to be confidently wrong.
   The repo's existing habit — publish the denominator, publish the limit, refuse the verdict when
   the grid is incomplete — is worth more than any of them.

---

## Appendix — reproducing §1.3, §1.4, §1.5

Run from the Framework root. No network, no database, no credentials; seconds each.

**§1.3 — the ladder is not monotone.** The oracle already enumerates permutations; this counts the
valid ones instead of returning the first.

```python
import itertools, sys; sys.path.insert(0, ".")
from generator_trunk.AI_combi_testing_platform.task_ir import generate_task
from generator_trunk.AI_combi_testing_platform.oracles.exact import _ordering_valid
for c in range(2, 7):
    for s in (20260806, 777001, 424242):          # the seeds used in the live run
        t = generate_task("ordering", seed=s, complexity=c)
        perms = list(itertools.permutations(sorted(t.entities)))
        valid = [p for p in perms if _ordering_valid(t, p)]
        print(c, s, len(t.entities), len(t.constraints), len(perms), len(valid))
```

**§1.4 — covering-array sizes.** AETG-style greedy over the eleven `RenderingPlan` axes
(3,4,2,2,3,3,3,4,2,4,4). Fill from `renderers/core.py:RenderingPlan.validate`; cover every *t*-subset
of axes and every value tuple within it; when the per-axis greedy plateaus, emit a test that covers a
residual tuple directly so the result is 100 % coverage rather than 97 %. Reported: **t=2 → 30 tests,
t=3 → 131**, against a full factorial of 165,888. A production generator (ACTS/IPOG) should reach
roughly 20–25 and 100–110; treat these as honest upper bounds.

**§1.5 — sequence covering arrays.** Greedy over random permutations of *n* events, keeping the
candidate that covers the most uncovered *t*-way orderings, until every ordered *t*-tuple appears as
a subsequence of some test. Reported: n=16, t=3 → **20 tests** against 2.09 × 10¹³ exhaustive.

---

## Sources named above (verify before external publication)

Kuhn, Kacker & Lei, *Practical Combinatorial Testing* (NIST SP 800-142); ACTS/IPOG · Kuhn, Higdon,
Lawrence, Kacker & Lei, combinatorial event-sequence testing (sequence covering arrays) · Colbourn &
McClary, locating and detecting arrays · Ghandehari, Lei & Kuhn, BEN fault localisation · Lanus,
Freeman, Kuhn & Kacker, input-space coverage for ML · Kuhn, Kacker, Lei & Hunter, combinatorial
methods for explainable AI · Chen, Cheung & Yiu, metamorphic testing; Segura et al. survey; Chen et
al. review · Xie et al., MT for ML classifiers · Sun et al., structure-invariant MT testing · Ribeiro,
Wu, Guestrin & Singh, *CheckList* (ACL 2020) · Zhou et al., *IFEval* · Yu, Arora et al., *Skill-Mix* ·
Mirzadeh et al., *GSM-Symbolic* · Farquhar, Kossen, Kuhn & Gal, semantic entropy (Nature 2024) · Wang
et al., self-consistency · Liu et al., *Lost in the Middle* · Zheng et al., LLMs are not robust MCQ
selectors; Robinson & Wingate · Zhao, Wallace, Feng, Klein & Singh, *Calibrate Before Use* · Sharma et
al., sycophancy · Wei, Haghtalab & Steinhardt, *Jailbroken* · Greshake et al., indirect prompt
injection · Röttger et al., *XSTest* · Laban et al., multi-turn degradation · Liang et al., *HELM* ·
Polo et al., *tinyBenchmarks*; Vivek et al., *Anchor Points* · Chow, W-method · Zeller &
Hildebrandt, delta debugging; Misherghi & Su, HDD · Havrikov & Zeller, *Systematically Covering Input
Structure* · Dorfman; Du & Hwang, combinatorial group testing · Sobol', variance-based sensitivity ·
Plackett & Burman; Jones & Nachtsheim, definitive screening designs · Benjamini & Hochberg, FDR ·
Wald, SPRT · McKay, canonical augmentation · Mazurkiewicz traces; Flanagan & Godefroid, DPOR ·
Bradley & Terry; Chiang et al., Chatbot Arena · Pei et al., *DeepXplore*; Ma et al., *DeepGauge*,
*DeepCT*; Harel-Canada et al., neuron-coverage critique.
