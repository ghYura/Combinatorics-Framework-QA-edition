# 43 — What combinatorial testing buys: the evidence

> **What this is.** The consolidated result of three controlled studies run against three
> independently written, hash-frozen systems under test. It states a claim, says what would falsify
> it, and reports what happened — including where the framework gave no advantage.
>
> The studies themselves: [proof_billing](../generator_trunk/proof_billing),
> [proof_fulfilment](../generator_trunk/proof_fulfilment),
> [proof_authz](../generator_trunk/proof_authz). Each carries its own README and is reproducible.

---

## 1. The claim, and what would falsify it

> A design expressed in these verbs reaches defects that a conventional parameter model **cannot
> express** — not at 2-way, not at 6-way, not at complete enumeration of that model.

Two phrasings of this are commonly offered and both are worse than the one above.

**"It finds more defects than pairwise."** Not worth making. Every method finds more when it runs
more cases; that is an argument about sample size, and it is answered by raising the strength.

**"Pairwise cannot find these."** True here, but it points at the wrong thing and invites the wrong
reading. The limitation is not a property of a covering array's *strength* — it is a property of the
**model** the array samples. Naming pairwise suggests raising t would help. It does not.

So the claim is falsified if any sampling of the classic model — of any size, up to and including
all of it — reaches what the verbs reached. The study therefore did not compare 24 pairwise cases
against eleven thousand candidates. It **exhausted the classic model** and compared that.

### The honest boundary of the claim

The limit is **practical, not information-theoretic**. Nothing forbids a determined modeller from
encoding order as a parameter — declare `operation_order` with n! values and a covering array will
happily sample it.

But at that point the parameter carries 40,320 values for eight operations, the array's economics
collapse, you must already know which orderings matter, and repetition and interleaving multiply it
again. You are now constructing the combinatorial space by hand — which is the work the verbs do for
you — and it has stopped being a covering array in any useful sense.

So the precise claim is about *the kind of parameter model people actually build*: one whose
parameters are independent value-axes, with no column for "this happened twice", "these happened in
this order", or "this fired between those two". Demonstrating the gap by exhaustion is what removes
sampling from the argument entirely.

### And pairwise is not the loser here

The same study's covering array found two genuine defects — a redelivery re-executing a refund, and
a mid-cycle upgrade crediting at the wrong price — for 24 cases and almost no modelling effort. That
is a good return. Pairwise reaches *value*-shaped defects cheaply; these verbs reach *shape*-shaped
ones. The result below is a statement about coverage of a different axis, not about one technique
defeating another.

## 2. The decisive control

A textbook suite was written first for the billing engine: equivalence partitioning, boundary value
analysis, 0-switch and 1-switch state coverage, nine use-case scenarios, and an IPOG covering array
over a 13-parameter model whose pair coverage was *verified*, not assumed — 662 pairs, none
uncovered. Then that same model was run to exhaustion: every point of its Cartesian product.

| | defects reached |
|---|---|
| pairwise, 24 cases | 2 |
| the same model **exhausted**, 525,312 cases (663,552 declared, 47s) | **the same 2** |
| the verb algebra, ~16,600 candidates across 3 systems | 12 |

**Exhausting the model bought nothing.** Twenty-four cases and half a million cases reach the same
two invariants. The gap is therefore not in the sampling, and no strength — 2-way, 6-way, complete —
closes it. It is in what the model can say.

Eight of the ten defects in the first study lie outside that model. **Six of them survive a build
whose classic suite reports 87/87 green with 100% verified 2-way coverage** — including one where
any string beginning `charge-` bills a customer, because the engine parses an event kind out of an
identifier it never issued.

## 3. Why: the unit of combination is an action

Everything else follows from one property. A slot's values are fragments of a program, so a
candidate is a generated program rather than a filled-in row of parameters. Four consequences:

| | covering array | verb algebra | defects it unlocked |
|---|---|---|---|
| **order** | none — a canonical order is forced | `FW_Permut`, n! orderings | a redelivery re-executing a refund |
| **multiplicity** | one value per parameter | `FW_CombiR`, `FW_PermutR` | a coupon allowance reset by re-applying it; an invoice refunded twice to negative cash |
| **interleaving** | no notion of "during" | `FW_Optional` at slot position | a restart resetting the invoice counter |
| **what is combined** | parameter values | fragments of a program | all of the above |

A parameter model has no column for "this operation happened twice", "these happened in this
order", or "this fired *between* those two" — not a small column, no column. As §1 notes, one can
always be *manufactured* by declaring a parameter whose values enumerate orderings; what cannot be
manufactured is doing so without hand-building the very space the verbs generate.

## 4. Three systems, three shapes of evidence

Each SUT was written to spec as a normal component, hashed, and made read-only **before** the first
campaign. None was designed around the verbs.

### billing_core — 426 lines, 13 campaigns, 11,648 candidates

The expressiveness proof above. Ten defects, of which two were reachable classically. Notable
findings only these verbs could reach: an invariant that **breaks and then heals** before any
end-of-test assertion (visible in 126 candidates at a one-cycle horizon and in *zero* at 1,200 —
the longer the run, the better it hides); a "change plan" to the plan already held minting unlimited
credit; and a forged webhook identifier raising a real charge while the engine's own audit reports
the books sound.

### fulfilment — 475 lines, 3 campaigns, 4,114 candidates

Five services over a message bus, as a **deterministic simulation** — no sockets, no threads, no
wall clock. That decision is what makes the delivery schedule an enumerable data structure, so
interleaving becomes a combinatorial axis instead of a source of flakiness.

Two severe defects: a retry re-executing the business operation (dedupe keyed on transport message
id, not on the operation), and a saga orchestrator with **no idempotency guard at all** while every
downstream service has one — a single redelivered reply advances the state machine twice.

Redelivery is *necessary*: of 648 candidates whose schedule contained none, **zero** failed. Adding
a restart quadruples the rate (12.0% → 50.5%). That is a two-factor interaction where neither factor
alone suffices, stated as a measurement rather than an intuition.

### authz — 351 lines, 4 campaigns, 859 candidates

Chosen because the first two studies had used five of roughly fifteen verbs and **none** of the
sieve's five bond tiers — not because those are weak, but because a billing account and a message
bus offered them nothing to bite on. Seniority is ordinal; a role's actions are a dependent
allowed-set; a clause is built from clauses.

| campaign | predicted | delivered | what it demonstrates |
|---|---|---|---|
| `e1_bounded` | 648 | 648 | `FW_Subsets_EXACT/RANGE/BEFORE` — size as part of the model |
| `e2_multiset` | 72 | 72 | `FW_CombiR` multisets, `FW_Permut` orderings |
| `e3_secondorder` | ≤6 | 6 | `FW_Group` + `FW_Separator` + brace |
| `e4_bonds` | 288→**133** | 288→**133** | `orders`, `assert/geSheet`, `mapping`, `condition`, `when` |

**`FW_Group` is demonstrated by content, not by count.** `FW_Combi(2)` over three predicates yields
three pairs; the assembled candidates carry *four* tokens each — those pairs recombined as atoms,
C(3,2)=3 groups — with the `AND` glue woven between every element. The count 6 = 3×2 would have
looked identical with no grouping at all.

**`e4` is the sharpest single result.** Its post-sieve figure was predicted as 133 by the sieve
pre-count, reproduced independently by a hand model of the four bonds, and confirmed by the sieve
removing 155 of 288. All 133 survivors **pass**: the bonds carve the space down to the legally
reachable region of an authorization model, and inside that region the engine holds. A negative
result that means something, because the region it covers is precisely stated.

## 5. The reflexive evidence

The strongest argument for a testing method is that it works on the thing that produced it. Used
seriously across three studies, the framework found defects in itself and in the tooling built for
it — and its own guardrails caught four author errors.

| found | how |
|---|---|
| **`FW_Permut(k)`'s argument is inert** — `PermutationsSimpleG` takes no size argument, so a slot emits all n! orderings while the estimator reported `P(n,k)`. Live in a shipped scenario where the plan claimed **EXACT 530,841,600,000** for a slot that alone emits 16! ≈ 2.09 × 10¹³. Confidently stated, and low — the only side a budget gate must never be wrong on. | a campaign printed its fragments: `FW_CombiR(2)` produced two, `FW_Permut(2)` produced three |
| an optional slot sized by **declared values** instead of result rows, which tripped `emitted_eq_expected` and made a multi-select optional slot unusable | running one |
| chained braces double-counted, inflating a 12-row space to 48 | running one |
| the post-sieve figure was never computed — a conservative `[0, mandatory]` where the answer is available | building the pre-count |
| the triage stage returning **six findings from six failures** — no reduction, exactly when a saturated run needs it | the `e3` campaign |

The `FW_Permut(k)` case is the study's own thesis in miniature. The **count** agreed —
P(3,2) = 3! = 6, the shape every existing test used — and the **content** did not. Only a method
that generates real artifacts and looks inside them could tell the difference. Arithmetic over the
design would have agreed with itself forever.

## 6. Where it gives no advantage

Stated plainly, because a proof that only reports wins is not a proof.

- **Pairwise found real defects** (a redelivery re-executing a refund; a mid-cycle upgrade crediting
  at the wrong price). This is not a replacement for classic technique. It is a different axis:
  pairwise reaches *value*-shaped defects cheaply, the verbs reach *shape*-shaped ones.
- **Four campaigns found nothing**, and they belong in the record: the lifecycle state machine held
  across all 256 sequences with repetition; concurrency produced no divergence from a serialized
  golden across 360 candidates × 5 repeats; no lost update at 64 workers and a 1 ns switch interval;
  and operations proved atomic under transient fault plus retry across all 120 combinations. Those
  negatives are worth their cost — they are things now known rather than assumed.
- **The oracle problem is untouched.** The framework put a run into a state where invoice numbers
  were duplicated and the engine's own `audit()` reported *clean*. It multiplies inputs; it does not
  invent judgement. Every campaign's value was capped by the oracle brought to it.
- **Saturation is the normal first result.** A dominant defect fires on most candidates and hides
  the rest. That is not failure; it is the shape of a first run. Mask the explained shape — a sieve
  bond, or a config flag — and read the residue.

## 7. When to reach for it

All four should hold:

1. the failure you fear is *shape*-shaped — order, multiplicity, interleaving, co-occurrence —
   rather than value-shaped;
2. you have a cheap mechanical oracle: an invariant, a differential reference, a metamorphic
   relation, or a crash;
3. a candidate is cheap to run relative to the value of finding the defect;
4. you can govern the space — declare it, count it, prune it.

And not when the oracle is human judgement, when a candidate is expensive in a space that will not
prune, when the defect is value-shaped and pairwise is enough, or when the system cannot be
decomposed into composable fragments.

## 8. Reproducing this

```bash
# the control that carries the argument: pairwise, then the same model exhausted
cd generator_trunk/proof_billing/classic
python3 test_classic.py && python3 exhaustive_classic.py

# any campaign, full chain
cd ../..
python3 bundle_run.py proof_authz/e4_bonds --db bauthz4 --lang py --sieve \
  --main-db-user postgres --main-db-password pass \
  --results-db-user postgres --results-db-password pass \
  --execution-policy-profile trusted-local --candidate-origin reviewed-checked-in \
  --acknowledge-trusted-local "reproducing doc 43"

# the findings, grouped, with a minimal witness each
python3 bundle_run.py triage /tmp/fw_work/bauthz4 --write
```

## 9. Scope

Three systems, one engineer's classic suite, one working session. What is demonstrated is a
**structural** property — a parameter model without order, multiplicity or interleaving cannot
express certain test cases — proven by exhausting such a model rather than by out-sampling it. What
is *not* demonstrated is a general defect-yield figure; that would need many systems and many
authors. The concurrency campaigns tested a component whose own docstring declares it
single-threaded, so their clean result speaks to deployment risk rather than to a spec violation,
and the second system is a deterministic simulation: it models loss, duplication and restart
faithfully, but not real network timing or true parallelism.
