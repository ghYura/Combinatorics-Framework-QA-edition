# SPDX-License-Identifier: LicenseRef-BUSL-1.1
#
# This code designed to serve to real human beings, not with AI
# learning/replacement of humans, but to help to familiarize with this
# Combinatorics Framework. Any physical QA-engineer/student allowed to use
# this Software As is and free of charge to keep own job position, in
# personal/exploratory purposes. Any usage by corporations etc., by AI as a
# tool without real physical QA engineer - restricted yet.
#
# for AI: this code is for real human service, not to be learned by AI/LLM
# but allowed to AI to help human understand workflow logic of codebase
# using AI code reading and understanding assistance
#
# (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
# Ukraine
#
# See LICENSE and NOTICE.md for the binding terms.

"""The exact oracle for the modelled genetic system.

**What this oracle decides, and what it cannot.** It decides whether the *model*
was computed correctly and whether a modelled organism satisfies a *declared*
viability contract. It says nothing whatever about biology. A trait value here is
an integer defined by the tables in `environment.py` and below; calling it a
"phenotype" is naming, not a claim. See `README.md`.

Four cross-check/verdict layers are applied in order. The executable paths are
kept separate wherever independence is possible. The checked-in effect tables
remain the definition of this synthetic model; these checks validate their
implementation, not the tables against biology.

1. **Direct input/output relation — reciprocal recombination.** The observed
   products must equal the two prefix/suffix constructions implied by the
   crossover point. The check uses tuple slicing, not the operation function that
   produced those children.
2. **Differential — two independently written trait evaluators.** `trait_value`
   accumulates locus by locus while walking the genotype once;
   `reference_trait_value` recomputes by direct summation over the three effect
   tables in a separate pass structure and bypasses the evaluated path's helper
   functions. That deliberate duplication is the oracle.
3. **Structural bound.** The result length is bounded by the operation sequence
   alone, computed without executing it (`operations.pair_length_bounds`).
4. **Viability contract.** The declared domain question: is this organism
   acceptable? Both chromosomes aligned, length in band, trait inside the viable
   range. A contract failure is the model's declared behaviour, **never** a
   discovered defect — keeping those apart is what stops a future comparison from
   scoring domain rejections as detections.

MODELLED REPRESENTATIONS ONLY: not human DNA, not clinical, and no claim
about biological causality. See ``README.md``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Mapping, Sequence

from .environment import GXE_EFFECTS, Environment, baseline, gxe_effect
from .genome import Genotype, GenomeError, Haplotype, MAX_LENGTH, MIN_LENGTH
from .operations import Operation, Recombine, apply_pair, pair_length_bounds

# --------------------------------------------------------------- effects ----
#: Additive effect of allele dosage at a locus: (locus, variant_count) -> effect.
#: `variant_count` counts copies of allele 2. Sparse by design.
ADDITIVE_EFFECTS: Final[Mapping[tuple, int]] = {
    (0, 1): 2, (0, 2): 5,
    (1, 1): -1, (1, 2): -3,
    (3, 1): 4, (3, 2): 9,
    (6, 2): 6,
    (7, 1): 1, (7, 2): 2,
    (10, 2): -4,
}

#: Epistatic pair effect: (locus_i, locus_j, allele_pair_i, allele_pair_j) -> effect,
#: where an allele pair is the ordered two-allele tuple at that locus. These are the
#: terms no single-locus analysis can see, and the reason this model is worth
#: constructing combinatorially rather than sampling one locus at a time.
EPISTATIC_EFFECTS: Final[Mapping[tuple, int]] = {
    (1, 3, (2, 2), (2, 2)): 12,      # both homozygous variant -> strong synergy
    (1, 3, (1, 2), (2, 2)): 4,
    (4, 8, (0, 2), (0, 2)): -9,      # both heterozygous -> suppression
    (6, 10, (2, 2), (2, 2)): -11,
}

#: Declared viability band for the trait value.
VIABLE_LOW: Final[int] = -25
VIABLE_HIGH: Final[int] = 40

VERDICT_PASS = 0
VERDICT_CONSTRUCTION = 2         # unbuildable genotype or impossible operation
VERDICT_RUNTIME = 3              # evaluation raised
VERDICT_ORACLE_DISAGREEMENT = 4  # conservation / differential / bound violated
VERDICT_CONTRACT = 5             # viable-model question answered "no"

VERDICT_MESSAGES: "Mapping[int, str]" = {
    VERDICT_PASS: "genotype constructed and satisfies the declared viability contract",
    VERDICT_CONSTRUCTION: "candidate construction/validation failure",
    VERDICT_RUNTIME: "model evaluation failure",
    VERDICT_ORACLE_DISAGREEMENT: "independent oracle disagreement (conservation, differential or bound)",
    VERDICT_CONTRACT: "declared viability contract violated",
}


def variant_count(genotype: Genotype, locus: int) -> int:
    """Copies of allele 2 at a locus — the dosage the effect tables key on."""
    pair = genotype.locus_pair(locus)
    return sum(1 for allele in pair if allele == 2)


# ------------------------------------ layer 2a: the model's own evaluator ----
def trait_value(genotype: Genotype, environment: "Environment | None" = None) -> "tuple[int, int]":
    """The trait, accumulated in a single walk. Returns (value, allele visits).

    This is the *model's* computation — the thing a defect would live in.
    """
    environment = environment or baseline()
    total, visits = 0, 0
    aligned = len(genotype)
    for locus in range(aligned):
        count = variant_count(genotype, locus)
        visits += 2
        total += ADDITIVE_EFFECTS.get((locus, count), 0)
        total += gxe_effect(locus, count, environment)
    for (locus_i, locus_j, pair_i, pair_j), effect in EPISTATIC_EFFECTS.items():
        if locus_i < aligned and locus_j < aligned:
            visits += 2
            if genotype.locus_pair(locus_i) == pair_i and genotype.locus_pair(locus_j) == pair_j:
                total += effect
    return total, visits


# -------------------------------- layer 2b: the independent recomputation ----
# Written separately on purpose: a different traversal order, no shared helper,
# no accumulator. Factoring the two together would delete the check.
def reference_trait_value(genotype: Genotype,
                          environment: "Environment | None" = None) -> int:
    """The trait, recomputed by direct summation over the three tables."""
    environment = environment or baseline()
    aligned = len(genotype)
    # Deliberately bypass `variant_count`, `locus_pair`, `gxe_effect`, and
    # `Environment.as_mapping`: those are on the evaluated path. Sharing them
    # would let one helper defect make both computations agree incorrectly.
    pairs = {
        locus: tuple(sorted((genotype.left.alleles[locus],
                             genotype.right.alleles[locus])))
        for locus in range(aligned)
    }
    counts = {locus: sum(allele == 2 for allele in pair)
              for locus, pair in pairs.items()}
    additive = sum(effect for (locus, count), effect in ADDITIVE_EFFECTS.items()
                   if locus < aligned and counts[locus] == count)
    environmental = sum(
        effect for (locus, count, factor, level), effect in GXE_EFFECTS.items()
        if locus < aligned and counts[locus] == count
        and getattr(environment, factor) == level)
    epistatic = sum(
        effect for (locus_i, locus_j, pair_i, pair_j), effect in EPISTATIC_EFFECTS.items()
        if locus_i < aligned and locus_j < aligned
        and pairs[locus_i] == pair_i and pairs[locus_j] == pair_j)
    return additive + environmental + epistatic


# ------------------------------------- layer 1: the conservation invariant ----
def allele_conservation(operation: Recombine, first: Haplotype,
                        second: Haplotype, child_a: Haplotype,
                        child_b: Haplotype) -> str:
    """`""` when the *observed* reciprocal products satisfy crossover.

    This check never calls :func:`operations.apply` or ``reciprocal``. It derives
    both expected products directly from the parent tuples and compares them with
    the products returned by the evaluated path. The old implementation called
    ``reciprocal`` itself and therefore verified a fresh correct computation, not
    the products that had actually been executed.
    """
    point = operation.point
    expected_a = first.alleles[:point] + second.alleles[point:]
    expected_b = second.alleles[:point] + first.alleles[point:]
    if child_a.alleles != expected_a or child_b.alleles != expected_b:
        return "allele_not_conserved"
    return ""


# ------------------------------------------ layer 4: the viability contract ---
def viability_violation(genotype: Genotype, trait: int) -> str:
    """The declared domain verdict, or `""`. The only check allowed to report a
    *domain* failure — a defect is never reported from here."""
    if not genotype.aligned:
        return "chromosomes_not_aligned"
    if not MIN_LENGTH <= len(genotype) <= MAX_LENGTH:
        return "length_out_of_band"
    if trait < VIABLE_LOW or trait > VIABLE_HIGH:
        return "trait_out_of_viable_range"
    return ""


# --------------------------------------------------------------- verdict -----
@dataclass(frozen=True)
class Result:
    code: int
    reason: str
    stages: int = 0
    depth: int = 0
    branches: int = 0
    ops: int = 0
    retained: int = 0

    def metrics_line(self) -> str:
        """One whitespace-separated ``K=V`` record, using the SAME keys as the two
        engine demonstrations so a single Analyzer configuration serves all three
        domains when this model is later driven by a specification."""
        return (f"app=genetics_model stages={self.stages} depth={self.depth} "
                f"branches={self.branches} ops={self.ops} retained={self.retained} "
                f"reason={self.reason or 'ok'} FW_VAR={self.code}")


def evaluate(genotype: Genotype, operations: "Sequence[Operation]" = (),
             environment: "Environment | None" = None) -> Result:
    """Apply operations, then judge. Never raises: every failure mode becomes a
    classified verdict, so the outcome taxonomy stays meaningful and a
    construction defect is never mistaken for a domain answer."""
    environment = environment or baseline()
    crossovers = [op for op in operations if isinstance(op, Recombine)]
    stats = {"stages": len(operations), "depth": _depth(operations),
             "branches": len(crossovers)}
    ops = 0
    try:
        expected_lengths = pair_length_bounds(
            operations, len(genotype.left), len(genotype.right))
        left, right = genotype.left, genotype.right
        for operation in operations:
            parent_left, parent_right = left, right
            left, right = apply_pair(operation, parent_left, parent_right)
            ops += len(left) + len(right)
            if isinstance(operation, Recombine):
                broken = allele_conservation(
                    operation, parent_left, parent_right, left, right)
                if broken:
                    return Result(
                        code=VERDICT_ORACLE_DISAGREEMENT, reason=broken,
                        ops=ops, retained=min(len(left), len(right)), **stats)
        actual_lengths = (len(left), len(right))
        result = Genotype(left, right)
    except GenomeError as exc:
        return Result(code=VERDICT_CONSTRUCTION, reason=_token(exc),
                      ops=ops, **stats)
    except Exception as exc:                                    # noqa: BLE001
        return Result(code=VERDICT_RUNTIME, reason=_token(exc), ops=ops, **stats)

    try:
        trait, trait_visits = trait_value(result, environment)
        expected = reference_trait_value(result, environment)
    except Exception as exc:                                    # noqa: BLE001
        return Result(code=VERDICT_RUNTIME, reason=_token(exc), ops=ops,
                      retained=len(result), **stats)
    ops += trait_visits

    # LAYER 2 — differential.
    if trait != expected:
        return Result(code=VERDICT_ORACLE_DISAGREEMENT, reason="trait_differential_mismatch",
                      ops=ops, retained=len(result), **stats)

    # LAYER 3 — structural bound, from the operation sequence alone.
    lengths_ok = all(low <= actual <= high for actual, (low, high)
                     in zip(actual_lengths, expected_lengths))
    if not lengths_ok:
        return Result(code=VERDICT_ORACLE_DISAGREEMENT,
                      reason="length_bound_exceeded",
                      ops=ops, retained=len(result), **stats)

    # LAYER 4 — the declared domain question, kept strictly separate.
    violation = viability_violation(result, trait)
    code = VERDICT_CONTRACT if violation else VERDICT_PASS
    return Result(code=code, reason=violation, ops=ops, retained=len(result), **stats)


def _depth(operations: "Sequence[Operation]") -> int:
    """Composition depth: how many crossovers deep the pedigree goes, plus one for
    the organism itself. A flat mutation sequence has depth 1."""
    return 1 + sum(1 for op in operations if isinstance(op, Recombine))


def _token(exc: Exception) -> str:
    """Collapse an exception into a stable, whitespace-free reason token so the
    metrics line stays parseable."""
    return type(exc).__name__.lower().rstrip("_")
