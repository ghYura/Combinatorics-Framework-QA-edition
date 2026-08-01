# Genetics model testing — a domain application of the Bundle engine

## The scientific boundary, first

**This package models textual and mathematical representations of genetic objects. It is not human
DNA, it is not clinical, and nothing in it is a claim about biological causality.**

Its alleles are small integers. Its effect sizes come from a checked-in table chosen for arithmetic
convenience. Its "phenotype" is an integer defined by that table and by nothing else — calling it a
phenotype is naming, not a claim.

What the Bundle can validate is a **model, a simulator, a transformation pipeline, and their
implementations**. It cannot establish that any such model corresponds to biology. Establishing that
is a different activity, needs a domain expert, and is explicitly out of scope here — see
[`expert_model.py`](expert_model.py) and
[`docs/37`](../../docs/37_GENETICS_APPLICATION_POSITIONING.md) §5 R1.

There is no external data source of any kind. `test_genetics_model.py` asserts that the model modules
perform no file or network I/O, and that assertion is meant to keep holding.

## What is here

| Module | Responsibility |
|---|---|
| `model/genome.py` | loci, alleles, haplotypes, and diploid genotypes as immutable values |
| `model/operations.py` | point mutation, insertion, deletion, recombination — as *data*, not function calls |
| `model/environment.py` | environmental factors and the genotype-by-environment interaction table |
| `model/oracle.py` | the exact oracle: four cross-check/verdict layers |
| `expert_model.py` | the **D7 seam** — undecided, deliberately unimplemented, do not fill in |

Pure standard library. The package imports nothing from the engine, nothing from either flagship
SUT, and nothing from any reference application. The last two are enforced, not promised: this tree
is classified `domain-application`, which may import only the engine layers and itself
([`docs/30`](../../docs/30_ENGINE_FIRST_ARCHITECTURE.md)).

## The oracle, and why it is four layers

An oracle that simply repeats the code it judges is worthless. The executable checks below use
separate paths where possible. The checked-in effect tables still define this synthetic model; the
oracle validates their implementation, not their relationship to biology.

1. **Direct input/output relation — reciprocal recombination.** The products actually returned must
   equal the two prefix/suffix constructions implied by the parents and crossover point. The check
   uses direct tuple slicing and never calls the recombination implementation.
2. **Differential — two independently written trait evaluators.** One accumulates in a single walk;
   the other recomputes by direct summation over the three effect tables in a different traversal.
   The reference path bypasses the evaluated path's dosage, locus-pair, environment-mapping and GxE
   helpers. Deliberate duplication is the oracle.
3. **Structural pair bound.** Both result lengths are derived from the operation sequence without
   executing it; insert/delete change both lengths and reciprocal crossover swaps them.
4. **Viability contract.** The declared domain question — chromosomes aligned, length in band, trait
   inside the viable range. A contract failure is the model's declared behaviour and is **never**
   reported as a discovered defect. Keeping those apart is what stops a later comparison from scoring
   domain rejections as detections.

## Why this model is worth constructing combinatorially

Three dependency shapes, all exactly computable, none reducible to the one before it:

```
locus 1 = 2/2 alone            trait  -3
locus 3 = 2/2 alone            trait  +9
additive prediction for both   trait  +6
BOTH TOGETHER (actual)         trait +18     <-- +12 epistatic term
```

No single-locus analysis predicts the third row. Similarly, locus 2 contributes `0` at the baseline
environment and `+7` when `temperature=2` — invisible unless the environment is varied *with* the
genotype.

The declared viability band `[-25, 40]` sits inside the exactly reachable range `[-27, 43]`, so both
bounds are crossable and the contract genuinely discriminates. Witnesses for both are asserted in the
tests, because a contract that can never fire is decoration — a lesson learned the hard way on the
second flagship SUT.

## What is deliberately absent

This is **Stage 2 only** of the plan in [`docs/37`](../../docs/37_GENETICS_APPLICATION_POSITIONING.md)
§4: the model and its oracle. Stage 3's required faults are absent on purpose:

- **no versioned faults** — Stage 3's mutants;
- **no factor space, no baseline comparison** — Stages 4;
- **no scenario specifications and no engine run** — Stage 5.

None of it is blocked by what is here. `oracle.evaluate()` already returns a `metrics_line()` using
the same `K=V` keys as the two engine demonstrations, so one Analyzer configuration will serve this
domain unchanged when a specification is written; the comparison harness it would use already exists,
domain-neutral, in `generator_trunk/bundle/study.py`.

**Before any comparison study is built on this model, read `expert_model.py`.** A study over an
author-designed model with author-chosen faults is an engineering demonstration, not external
validation, and must not be labelled as the latter.
