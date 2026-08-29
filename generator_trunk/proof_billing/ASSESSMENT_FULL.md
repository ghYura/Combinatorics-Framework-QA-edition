# Combinatorics Framework — comprehensive assessment

**Basis for this assessment.** A controlled empirical study run on 2026-08-29: a billing engine
written from experience, hashed and made read-only *before* any combinatorial work began, then
attacked twice — once by a textbook classic suite (including a verified 2-way covering array, and
then that model **exhausted**), and once by the framework's verb algebra across 13 campaigns and
16 runs totalling 11,648 candidates through the real chain. Every number below was observed, not
estimated. Method and reproduction: [README.md](README.md). Narrative report:
https://claude.ai/code/artifact/be7fe9f6-673c-4d57-b721-4f63bf2315cb
Short version: [ASSESSMENT.md](ASSESSMENT.md).

**What this assessment is not.** One SUT, one author's classic suite, one afternoon of campaigns.
What is demonstrated is a *structural* property, proven by exhausting a model — not a general
yield figure, which would need many systems and many authors. Claims are marked where they are
inference rather than observation.

---

## 1. The question, and what the experiment actually settles

The claim under test was: *a wide variety of combinatorics verbs finds bugs in complex systems
that classic methodologies, including pairwise, cannot.*

That claim is easy to make badly. "Pairwise missed it" usually means "the sample was small." The
only way to settle it is to remove sampling from the argument entirely:

> Pairwise is a **sampling strategy over a parameter model**. If a defect is missed because the
> sample was too small, a larger sample finds it. If it is missed because the **model cannot
> express the test case**, then no sample of any size finds it — not 2-way, not 6-way, not exhaustive.

So the classic model was run exhaustively — all 663,552 points of its 13-parameter product,
525,312 of them legal, in 47 seconds.

| | Pairwise, 24 cases | Model **exhausted**, 525,312 cases | Framework, 11,648 candidates |
|---|---|---|---|
| Coverage | 662 pairs, 0 uncovered (verified) | complete | 13 spaces |
| Invariants reached | I4, I8 | **I4, I8** | I4, I5, I8 |
| Distinct defects | 2 | **2** | 10 |

**Exhausting the model bought nothing.** That single fact is the study's load-bearing result: the
gap between the two approaches is not sampling, it is expressiveness.

### The defects

| id | defect | classic model | shipped build (suite green) |
|---|---|---|---|
| F9 | a forged or corrupted webhook id raises a real charge | unreachable | **still present** |
| F7 | "changing" to the plan already active mints credit, repeatably | unreachable | **still present** |
| F1 | re-applying a coupon resets its lifetime allowance | unreachable | **still present** |
| F2 | the same invoice refunded twice exceeds it, to negative cash | unreachable | **still present** |
| F6 | a process restart resets the invoice counter → duplicate numbers | unreachable | **still present** |
| F8 | subscribing on an active account bills the cycle twice | unreachable | **still present** |
| F5 | an invariant breaks mid-run and heals before the end | unreachable | class remains (instance patched) |
| F10 | a redelivery re-executes a refund from *any* distance | unreachable | fixed with F3 (shared root cause) |
| F3 | webhook redelivery re-executes a refund | **found** | fixed |
| F4 | mid-cycle upgrade credits at the new plan's price | **found** | fixed |

Eight of ten lie outside the classic model. **Six survive a build whose classic suite reports
87/87 green** after fixing everything that suite found — including F9, which lets anyone who can
reach the webhook endpoint bill any customer any amount, with the engine's own audit reporting the
books as sound.

Two honesty notes. **Pairwise found real bugs** (F3, F4) — this is not a replacement for classic
technique but a different axis of coverage. And **F10 shares F3's root cause** and is fixed by the
same patch; its value is not that it survives but that it proved the hazard's *shape* was
mis-modelled, which matters to anyone writing a fix, a monitor, or a bond.

---

## 2. Why it finds them — mechanism, not magic

Reduced to essentials, four properties separate the approaches, and only the first is about sample size.

| Property | Covering array | Verb algebra | Defects it unlocked |
|---|---|---|---|
| Sample size | tunable by strength | tunable by verb | — |
| **Order** | none — a canonical order is forced | `FW_Permut`: n! orderings | F3, F10, and the position of every sudden event |
| **Multiplicity** | each parameter takes one value | `FW_PermutR`, `FW_CombiR` | F1, F2, F7 |
| **Interleaving** | no notion of "during" | `FW_Optional` at slot position | F6 |
| **What is combined** | parameter values | **fragments of a program** | everything above |

The fourth line is the root of the other three, and it is the framework's real thesis. Because a
slot's values are code fragments that concatenate into a runnable candidate, the unit of
combination is an **action**. Once that is true, order, repetition, interleaving, sudden events,
chaos, transport pathology and fault injection stop being separate disciplines with separate tools
and become ordinary axes of one product.

That is why the campaign designs that paid best were the ones crossing things no methodology
crosses:

- **Functional × stress × chaos** (C9) — three separate phases, different teams, different reports,
  multiplied into one space. Produced F6.
- **Transport pathology × functional scenario** (C10) — delivery lag and every subset of four
  identifier pathologies. Produced F9, the most severe finding in the study. 216 of 288 candidates
  raised a ghost charge.
- **The observer as part of the experiment** — the oracle evaluated after *every* step, not at the
  end. Produced F5, a class of corruption that heals before any classic assertion runs. In C9, the
  same defect was visible at a 1-cycle horizon in 126 candidates and in **zero** at 1,200 cycles:
  the longer the run, the more thoroughly it hides.
- **Time as a shape, not a scalar** — 30 days as one `tick(30)` versus thirty `tick(1)` calls: same
  elapsed time, different code path.
- **The degenerate call** (C8) — arguments nobody bothers to pass. Produced F7 and F8.

---

## 3. Is it a proof of concept?

**No.** It is a working instrument with production-grade guardrails and researcher-grade
ergonomics. The distinction matters, so here is the assessment broken out by dimension, with what
was observed directly separated from what is inferred.

### 3.1 Engineering maturity — observed, strong

- Five trunks (Core, Reader, Executor, Analyzer, Combinatoricslib) built clean **offline** with
  Maven on first attempt. 122 Java files in Core alone.
- The chain ran **16 times with zero infrastructure failures** across 11,648 candidates and every
  stage: generation, PostgreSQL materialisation, sieve, reassembly, execution, results.
- `fwgen`'s closed-form row estimate matched the Core's actual `fw_final` **exactly in every
  campaign** (18, 72, 256, 288, 108, 625, …). That is a real cardinality model, not a heuristic.
- Sieve removal counts matched predictions computed two independent ways (closed form, and driving
  `sieve.row_violations` offline) **exactly**: 625 → 161 removed → 464; then 625 → 261 → 364.
- `FW_Optional` behaved precisely as documented: `fw_final = 72` mandatory × 2³ optional subsets →
  576 candidates, each optional piece inserted at its slot position.
- The brace joined two *independently computed result tables* (3 pairs ⋈ 3 pairs = 9 rows),
  confirming operands are prior results rather than raw sheets.

### 3.2 Guardrails — observed, unusually good

This is where the project most clearly is not a prototype. Prototypes do not fail closed.

- **Execution policy.** The first campaign attempt was refused:
  `candidate origin 'generated' must not execute under 'trusted-local'`, with the reasoning that
  *an acknowledgement records a decision; it cannot authorize running generated code on the host*.
  That is a correct and unusually principled distinction.
- **Budget gate.** The brace campaign was refused before any stage started, classified `X (extreme)`
  because a brace's output is not statically estimable, and required both `--allow-extreme` and
  `--override-budget "<reason>"`. The reason is recorded.
- **Unenforceable bonds fail loudly.** The sieve *raises* rather than silently keeping rows when a
  constraint names a non-materialized sheet, with the comment: *"Silently keeping every row would
  look exactly like 'the constraint allowed everything', so it fails instead."* That is the correct
  instinct, written down.
- **Determinism is documented as a spec problem, not patched over.** `README_CANONICAL_TRUTH.txt`
  explains an ordering hole in `FW_Group`, the content-sort that closes it, the exact 694,114-row
  consequence, *and why the historical number was not wrong*. Only a mature project writes that.
- Per-candidate policy id and hash recorded in `results_v2`; versioned handoff contract; run
  journal with resume/cancel; atomic temp→fsync→rename for contract JSON.

### 3.3 Where it is not a finished product — observed friction

Each of these cost me real time during the study.

1. **The most powerful operators are the least governable.** `estimate_core_combos` treats
   `FW_Group` and the brace as row-preserving, so exactly the two second-order operators force a
   budget override. Documented, but it means the guardrail and the capability are in tension.
2. **Python execution does not scale out.** `--executor-pool` is gated to Java
   (`POOL_REQUIRES_JAVA`). The Python path is single-process; C5's 6,912 candidates took 372s serially.
3. **Result triage is not in the box.** C5 produced 2,304 failures from a single cause. Without
   minimal-witness reduction and per-axis enrichment, a large campaign yields a pile rather than a
   report. I had to write `analyze_run.py` to make any campaign legible.
4. **Metrics harvesting is off by default.** `metrics.kv` was empty without analyzer goals wired, so
   candidate output had to be re-executed to analyse it.
5. **Authoring is raw and trap-rich.** Slot values are code fragments inside TOML strings.
   `seq_extra` must precede every table or TOML silently binds it elsewhere. No data cell may begin
   with `FW_`. `FW_ReplaceRE` rewrites the `Short` code-string, not value text — a textual
   replacement is a silent no-op. All documented; still traps, and the documentation is the only
   thing standing between an author and a quietly wrong run.
6. **One documentation/implementation gap.** The sidecar schema says an ordered `FW_Permut` sheet's
   array order *is* the sequence. The `fw_final` decoder increments `pos` once per materialized
   **axis** (`sieve.py:743–752`), and placements sharing a position are never paired (`:495`) — so a
   single permuted sheet's internal order is invisible to a positional gate. Verified by driving
   `row_violations` directly. The schema's own stated rule ("a sheet at one slot is one placement")
   is consistent with the code; it is the looser phrase that misleads. **Consequence for authors:**
   to combine ordering with bonds, encode the sequence as one slot per step.

### 3.4 Summary judgement

| Dimension | Assessment |
|---|---|
| Core engine correctness | Mature. Exact cardinality prediction, documented determinism, verified second-order semantics. |
| Safety & governance | Mature, and better than most commercial tools. Fails closed on origin, budget, and unenforceable constraints. |
| Contracts & provenance | Mature. Versioned schemas, journal, policy hashes, atomic writes. |
| Documentation | Extensive and unusually candid about its own traps. One misleading phrase found. |
| Authoring ergonomics | **Immature.** Expert-only. This is the gap between "instrument" and "product." |
| Result analysis | **Missing.** The largest practical gap. |
| Scale-out (Python path) | Limited. |

**Not a proof of concept. An instrument.** The engineering underneath is production-grade; the
surface assumes someone who already knows what they are doing.

---

## 4. The sieve — the feature I did not expect to matter most

The constraints layer is normally sold as pruning: remove impossible combinations, save budget.
That is the least interesting thing it does.

Used as **hypotheses**, bonds become a falsification loop. Each bond asserts *"this shape is already
explained"*; the sieve subtracts it; whatever survives is what your model does not account for.
The same 625-row space, three times, changing only the bonds:

| bonds | candidates | failing | rate | residue |
|---|---|---|---|---|
| none | 625 | 169 | 27.0% | dominated by two known shapes |
| "a refund *immediately followed by* a redelivery is explained" | 464 | 21 | 4.5% | **20 survivors — the hypothesis was wrong** |
| "a refund *co-occurring at any distance* is explained" | 364 | 1 | 0.3% | **1 — the only unexplained defect** |

The middle row is the point. The mask removed 148 of 169 failures and left twenty it *should* have
caught — and those twenty said the model of the hazard was wrong. Following them produced F10:
`replay()` resolves `ledger[-1]`, the last **ledger entry**, not the last operation, so any number
of ledger-silent operations can separate a refund from its redelivery. The adjacency intuition is
simply false, and only `tick()` looks safe — by accident, because it writes a charge that moves the
target.

I have not seen another test tool that offers a falsification loop of this shape. It also directly
solves a problem I hit earlier in the study: **a dominant defect masks everything else** (campaign
C11 was saturated by F4 and could isolate nothing until F4 was patched out). Bonds make that
subtraction explicit, checkable, and reversible.

---

## 5. Limitations that will not go away

1. **The oracle problem is untouched.** The framework put me in a state where invoice numbers were
   duplicated and the SUT's own `audit()` reported *clean*. It multiplies inputs; it does not invent
   judgment. Every campaign's value was capped by the oracle I brought.
2. **Explosion is the author's responsibility**, as the project's own documentation says plainly.
   C5 was 6,912 candidates from a modest-looking spec; a careless one is millions.
3. **Saturation.** A high-frequency defect hides lower-frequency ones. Bonds are the answer, but you
   have to know to reach for them.
4. **Modelling skill is the binding constraint.** The verbs execute the axes you declare; they do
   not find the axes. The study's best findings came from asking *"what can I combine that nobody
   combines?"* — that question is human work, and the tool cannot supply it.
5. **Decomposability is a precondition.** The SUT must be drivable by composable fragments. A
   monolith with no seams gets much less out of this.

---

## 6. Other areas of application

The engine is not really a test tool. It is a **governed generator of executable configurations and
sequences, with a per-candidate verdict and a multi-objective selection front**. Anything of that
shape is in scope. Ranked by fit.

### Tier 1 — the shape matches almost exactly

**Protocol and state-machine conformance.** Loss, duplication, reordering and delay *are* the test
space, and they are precisely what `FW_Permut` / `FW_Optional` / `FW_Subsets` express. C10 was a
small instance of this and found the study's worst defect. Targets: TCP-like retransmission, OAuth
and 3DS flows, gRPC retry semantics, message-queue at-least-once consumers.

**Distributed-systems consistency.** Generate operation histories under reorder and partition; the
oracle is an external linearizability or invariant checker. The framework does the enumeration a
hand-written history generator does badly, and the sieve encodes which histories are physically
possible. Sketch: one slot per operation slot, `FW_PermutR(k)` over the op alphabet, `FW_Optional`
for a partition event, bonds gating impossible orderings.

**Compiler and optimizer testing.** Pass-ordering bugs are notoriously order-shaped and notoriously
hard to sample. `FW_Permut` over pass order × `FW_Subsets` over enabled passes × `FW_Group` for
nested pipelines, with differential execution against `-O0` as the oracle. This is arguably a better
fit than the billing SUT I used.

**Upgrade and migration paths.** Every matrix tool asks *which versions*; almost none ask *in what
order*, with a rollback injected mid-sequence. `FW_Permut` × `FW_Optional` covers exactly that, and
migrations are where order-dependence actually bites.

### Tier 2 — strong fit, needs an oracle investment

**Deployment and infrastructure-as-code.** Sequences of apply / scale / failover / rollback crossed
with chaos events. The brace is the natural fit for joining two independently generated plans — an
application rollout ⋈ a database migration, M:N — which is exactly the second-order construct C6
exercised.

**Security testing.** F9 was a security defect found by transport distortion, which is not a
coincidence: authorization matrices are n-ary (role × resource × action × state) and the sieve's
n-ary bonds with ordinal and presence tiers express legal-state constraints directly. Attack chains
are ordered and repeated. *Scope note: for authorized testing — the same properties that make this
good at finding authorization holes make it a tool that needs an engagement behind it.*

**LLM and agent evaluation.** The repository already leans here, and the fit is real rather than
fashionable: multi-turn conversation **order** is a genuine blind spot in current eval practice,
tool-call sequences are permutations, adversarial turns are textbook `FW_Optional` sudden actions,
and the Analyzer's Pareto front over quality/latency/cost is what evaluation actually needs. The
`RunMeFirstOnce` prologue is well suited to pinning a model version and computing a shared baseline
once for a whole candidate family.

**Regulatory, benefits and insurance rule engines.** Eligibility is genuinely n-ary under hard legal
constraints, and — unusually — this domain needs *auditable evidence of which combinations were
checked*. The run journal, provenance artifacts and recorded policy hashes are worth as much here as
the generation. The sieve's `mapping` / `assert` / ordinal tier maps onto statutory rules cleanly.

### Tier 3 — plausible, different economics

**Scientific and industrial experimental design.** Choosing which factor combinations to run when
each candidate costs real money or lab time. Here the budget gate stops being friction and becomes
the main feature, and the sieve encodes physically infeasible combinations. The repository's
genetics work sits in this space.

**Hardware and firmware configuration matrices.** Device × firmware × peripheral × power-state
*transitions* — the transitions being the part matrix tools miss.

**Hyperparameter and architecture search.** The Analyzer is already a multi-objective selector with
a `BundleSeed` feedback loop, which makes this a search engine as much as a test harness. Fit is
good; competition in this space is stiff.

### Where I would not use it

Exploratory and usability testing (the oracle is a human), single expensive candidates in an
unprunable space, value-shaped bugs where pairwise is cheaper and sufficient, and systems with no
seams to decompose.

---

## 7. Recommendations, prioritized

Ordered by how much each would have helped me during this study.

1. **Ship a result-analysis stage.** Minimal-witness reduction plus per-axis enrichment turns a
   campaign from a pile into a report. This is the single largest gap between instrument and
   product, and `analyze_run.py` in this directory is a crude sketch of what it should do.
2. **Make bonds-as-hypotheses a first-class workflow.** It is the framework's sharpest idea and it
   is currently an emergent use. A documented "mask the explained, inspect the residue" loop —
   ideally with the residue diffed automatically between runs — would be a genuine differentiator.
3. **Give the brace and `FW_Group` a dynamic bound**, or a cheap sampled pre-count, so the two most
   powerful operators stop being the two that trip the budget gate.
4. **Fix the `pos` phrasing in the sidecar schema**, and add a worked example showing the
   one-slot-per-step encoding for ordering × bonds. This is a five-minute documentation fix that
   prevents a whole class of silently-inert constraint.
5. **Parallelise the Python executor**, or document the Java path as the scaling route more prominently.
6. **Enable K=V harvesting by default** so `metrics.kv` is populated without analyzer goals.

---

## 8. Bottom line

The framework's thesis is small and its consequences are large: **make the unit of combination an
action**. The verbs, the brace, `FW_Group`, `FW_Optional` and the sieve all follow from that, and
together they let a tester express test cases that a parameter model has no words for. The study
demonstrates that this is not a matter of degree — exhausting the classic model found nothing its
24-case sample had not already found, while eight defects sat outside it, six of them surviving a
green suite.

What I valued most was not the volume. It was that **asking a hard question became cheap**. Four
campaigns came back clean — the lifecycle machine sound across 256 sequences, no concurrency
divergence, no lost update, atomicity holding across 120 fault-and-retry combinations. Those
negatives are worth as much as the findings, because they are now things I know rather than things
I assume, and I would never have paid to establish them by hand.

Its permanent limit is the oracle, and the project says so itself. The tool holds the lamp; a
person still chooses the road.

---

## Addendum — was the first SUT complex enough?

**No, and the audit is unambiguous:** across all 13 campaigns the study used 5 of ~15 verbs and
never touched `FW_Group`, `FW_Cartes`, `FW_CombiR`, the bounded subset modes, `FW_Separator`,
`FW_ReplaceRE`, the Analyzer, sharding, gRPC or the Java executor path. A 426-line single-class
module has no topology, so the composition operators had nothing to compose.

But the study's two claims need *different* SUTs, and conflating them would be an error:

| claim | what it needs | verdict on SUT v1 |
|---|---|---|
| pairwise has a **structural** blind spot | a model small enough to **exhaust** | **ideal** — 663,552 cases in 47s is only possible because it was small |
| the framework's **ceiling** is high | topology, protocol, real faults | **inadequate** |

The anti-pairwise result therefore stands, and is arguably *stronger* on a simple SUT: exhausting
the model removes sampling from the argument entirely, and that control is impossible on a complex
system. What v1 could not do is show the framework at full stretch.

**A second study was run to close that gap** — [../proof_fulfilment](../proof_fulfilment): a
475-line, five-service order pipeline with a saga, compensation, idempotency keys, retries and
timeouts, as a deterministic simulation so the delivery schedule is enumerable data. 4,114 further
candidates. It found two severe distributed-systems defects (a retry that re-executes the business
operation; a saga orchestrator with no idempotency guard at all, where every downstream service has
one), gave the **brace its first genuine use** (3 computed order-pairs ⋈ 6 computed fault-pairs =
exactly 18, a construct no flat cartesian can express), and surfaced three further observations
about the framework: the estimator honestly flagging its own limits, the Analyzer reporting success
over an empty corpus, and a concatenator trap that broke 2,048 candidates at once.

**Net effect on this assessment:** the verdicts above are unchanged, and two are reinforced —
*authoring is the immature surface* (the concatenator trap cost a whole run) and *saturation is the
main practical obstacle* (the second study's first campaign was 100% failing on a single defect and
told me nothing until it was masked). The framework's ceiling is higher than the first study showed;
its ergonomics are exactly as rough as the first study suggested.
