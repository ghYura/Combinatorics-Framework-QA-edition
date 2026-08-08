# Testing AI request/response with advanced combinations

**Status:** design + reference implementation. Everything described as *built* runs offline against
the platform's declared controls, at zero cost, and is covered by tests in `tests/`.

---

## 1. The constraint this design removes

The platform scores a response against an exact answer. That is why its task families are ones a
solver can settle — `ordering`, `cancellation`. The choice is honest and it is also the ceiling:

> **A target can only be tested on questions someone can independently answer.**

Summarisation, code, retrieval, agent behaviour — the things people deploy — have no exact oracle,
so they are unreachable. Worse, the limit is invisible from inside: this repository's own
`fin_tech_to_test` SUT carries five real defects under a fully green 56-test suite, because nothing
encoded an oracle for them. An engine finds what its oracle was told to look for and nothing else.

So the highest-leverage move is not another presentation axis. It is a second source of verdicts.

## 2. The combinatorial design *is* an oracle — `invariance.py` ✅ built

When a space is generated combinatorially you know **by construction** which points must agree.
Reordering independent constraints, adding declared-neutral context, or changing the output
serialization cannot change what the answer *is*. Those are metamorphic relations, and `FW_Permut`
over an invariant axis enumerates the equivalence class for free.

The verdict becomes a property of a **group**: did every member of this orbit produce the same
answer? No ground truth is consulted. That is what lifts the ceiling — it applies to any task you can
vary invariantly, not only ones you can solve.

Two granularities are emitted per candidate, as `orbit_*` dimensions plus an `answer_digest`:

- the **joint orbit** — every invariant axis varies at once; the real equivalence class, strongest detector;
- **per-axis orbits** — one relation varies, the rest held; weaker, but it *attributes* a violation.

Six relations ship, each carrying the argument for why disagreement is a defect: `neutral_context`,
`output_schema`, `constraint_order`, `instruction_order`, `neutral_distractor`, `paraphrase`.

**What is excluded matters as much.** A `contradictory` distractor is designed to interfere and an
`inverted` paraphrase restructures the ask, so asserting invariance across them would manufacture
violations that are correct behaviour. A relation that is not actually a relation turns every result
into noise — the classic metamorphic-testing failure.

**Measured**, over 48 candidates on one task, no ground truth used:

| adapter | joint | neutral_context | output_schema | constraint_order | instruction_order |
|---|---|---|---|---|---|
| `oracle-control` | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| `fragile-control` | **1.0** | **1.0** | 0.0 | 0.0 | 0.0 |

The fragile control degrades when declared-neutral filler appears — filler whose own text says it
"adds no rule". The detector convicts it, and **attributes the violation to the right axis while
exonerating the other three**. Detection is cheap; attribution is the useful part.

> A pre-existing parser bug surfaced here: `answer=` parsed back as `('',)` rather than `()`, so an
> empty answer disagreed with itself across schemas. That would have produced *false* violations —
> a parser artifact convicting a target of nothing. Fixed in `oracles/exact.py`.

## 3. Make a failure name its own cause — `decomposition.py` ✅ built

`FW_VAR != 0` conflates three findings that demand different actions:

| | means | do |
|---|---|---|
| **capability** | cannot do it at this size | change model |
| **fragility** | can, but this phrasing broke it | fix the prompt |
| **instability** | sometimes can | self-consistency / retries |

A grid separates them because it already contains the controlled comparisons — each is a marginal of
one tensor, so all three come from one run:

- **capability ceiling** — sweep size at fixed presentation. Stops at the *first* failure, not the
  last success: a lucky pass above a failure is noise, and reporting it would overstate the target.
- **fragility coefficient** — sweep presentation at fixed size. The denominator is the whole legal
  space, which only an exhaustive design can state honestly.
- **instability rate** — repeat an identical candidate. Groups of one are excluded; K=1 must never
  read as "perfectly reliable".

**Measured** against `fragile-control`, whose contract is declared in code as
`complexity >= 4 AND (loaded OR context notes >= 3)`:

```
capability ceiling = 3        (declared threshold is 4 — recovered exactly)
fragility          = 0.5      (30/60 of the presentation space)
instability        = 0.0      (deterministic control, K=4)
```

The consequence worth publishing: **a more accurate but fragile model is the worse deployment.** One
accuracy number cannot say that; this decomposition can.

## 4. Interaction-only failures — `interaction_map()` ✅ built

LLM failures are famously interaction failures: handles negation ✓, handles long context ✓,
negation + long context ✗. Second-order composition is the framework's least-used feature and
exactly the right instrument.

A cell's *marginals* are each factor's level paired with the other's baseline — what a
one-factor-at-a-time suite would have seen. A failure whose marginals both pass **could not have been
found without the cross product**.

**Measured**, complexity × neutral filler on `fragile-control` (a declared conjunction):

```
20 cells · 9 failing · interaction_only_failures = 9 · share = 1.00
```

**All nine failures are invisible to any one-factor sweep.** That number is the concrete argument for
combinatorial coverage over sampling, and it is computable rather than asserted. Incomplete grids
yield no verdict rather than assuming the missing side passed.

## 5. Time as an axis: the `dispatch` family ✅ built

Everything above is single-turn. The companion `combination_thinking_tutor` SUT found **120 of 144
legal orderings violate** its dispatch rules — order is where the failures live, and a single-turn
suite cannot reach it.

`dispatch` carries that shape into an LLM task: steps delivered in an arbitrary order, some marked
failed, and the target must report what actually took effect. Simulation keeps the oracle exact while
the question stops being static — state tracking over time, which is the agentic failure mode.

**Measured**, exhaustive over delivery orders × single failure injections:

```
24 cases · 1 dispatches cleanly · 23 degrade = 95.8%
```

The oracle checks three independent properties, so a near-miss is distinguishable from nonsense: only
delivered actions may appear, no failed step may appear, precedence must hold.

## 6. Attack × defense with a denominator ✅ built

"We tried some jailbreaks and none worked" is not evidence — nobody can say what was not tried.
Composing an attack axis (`override`, `smuggled`, `schema_hijack`) with a defense axis
(`restate_contract`, `delimit`, `output_constraint`) produces the artifact a reviewer can use.

The injection never alters the task or its exact answer, so a successful attack is an ordinary wrong
answer — no judgement about tone required. `InjectableControlAdapter` is a pipeline control with a
declared boundary, so the matrix has a subject that behaves in a known way, offline and free.

**Measured:**

```
16 pairings · 6 successful attacks (37.5%)
delimit / restate_contract  defeat all three attacks
output_constraint           defeats none
```

Asserting a mitigation's *failure* matters as much as its success: a matrix in which everything
defends proves only that the attacks were weak.

## 7. Not built — designed

- **Routing as a Pareto answer.** Goals already include `correct`, `latency_us`, `cost_microusd`;
  adding stability as a fourth objective turns the Analyzer's non-dominated front into a procurement
  decision ("read the knee") instead of a leaderboard. Small change, needs a real multi-model run.
- **Graded verdicts kept distinct from exact ones.** The framework refuses to collapse `EXACT` into
  `BOUNDED` for cardinality; verdicts deserve the same honesty — `EXACT_PASS` vs
  `GRADED_PASS(confidence)` — so an LLM-judge result can never be silently read as an exact one.
  **This is a prerequisite** before §2 is pointed at fuzzy tasks, or the evidence grade quietly rots.
- **Session-per-orbit.** Multi-turn needs state surviving across a candidate group; current policy is
  fresh-session-per-candidate.

## 8. Honest limits

- **Cost is multiplicative.** `capability × presentation × K × models` explodes, and each cell costs
  money and latency. The realistic pattern is two-phase: exhaustive on a cheap local proxy, then
  targeted on the expensive target — which is what `bundle iterate` and BundleSeed exist for.
- **A relation must actually be invariant.** A "neutral" distractor that subtly shifts meaning
  generates false positives. This is authoring judgement, and it is the same ceiling as always: the
  engine executes your model of the problem, it does not supply it.
- **Non-determinism multiplies everything by K** before any cell is trustworthy.
- **Every measured number here is a control, not a model.** The controls exist to prove the
  instruments detect what they claim and to fix their boundaries in code. They say nothing about any
  real target's accuracy, fragility, or resistance to injection.
- **Providers change models under you.** Inventory and provenance matter more here than anywhere.

## 9. Files

| Path | |
|---|---|
| `invariance.py` | relations, orbit keys, answer digests, orbit verdicts |
| `decomposition.py` | capability / fragility / stability + interaction map |
| `task_ir/model.py` | `DispatchTask`, `DISPATCH_ACTIONS` |
| `oracles/exact.py` | `simulate_dispatch`, dispatch verification, empty-answer parse fix |
| `renderers/core.py` | dispatch rendering, `injection` / `defense` axes |
| `adapters/local.py` | `InjectableControlAdapter` |
| `engine.py` | orbit + presentation dimensions, `dispatch` family |
| `tests/` | `test_invariance.py`, `test_decomposition.py`, `test_dispatch_family.py`, `test_attack_defense_matrix.py` |
