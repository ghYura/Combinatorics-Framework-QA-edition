"""Operations over modelled genetic objects, expressed as immutable values.

An operation is *data*, not a function call: `Substitute(3, 1)` is a value that
can be enumerated, compared, hashed, serialized and — later — emitted by a
combinatorial specification. That is the same shape the two engine
demonstrations use for their node models, and it is the property that lets a
generator construct operation sequences without knowing what any of them mean.

Four operation kinds, matching the classes the application was scoped to:

``Substitute``   one locus takes a different allele (a point mutation)
``Insert``       an allele is spliced in, lengthening the haplotype
``Delete``       a locus is removed, shortening it
``Recombine``    a crossover between two haplotypes at one point

Recombination is the only operation that takes two haplotypes, and it is the one
carrying the exact conservation law the oracle checks: the two *reciprocal*
products of a crossover jointly contain precisely the alleles the two parents
did, at every position. Nothing is created and nothing is lost.

MODELLED REPRESENTATIONS ONLY: not human DNA, not clinical, and no claim
about biological causality. See ``README.md``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, Union

from .genome import ALLELES, GenomeError, Haplotype, MAX_LENGTH, MIN_LENGTH


@dataclass(frozen=True)
class Substitute:
    """Point mutation: the allele at `position` becomes `allele`."""

    position: int
    allele: int


@dataclass(frozen=True)
class Insert:
    """Splice `allele` in before `position`, lengthening the haplotype by one."""

    position: int
    allele: int


@dataclass(frozen=True)
class Delete:
    """Remove the locus at `position`, shortening the haplotype by one."""

    position: int


@dataclass(frozen=True)
class Recombine:
    """Crossover at `point`: take the prefix from one haplotype, the suffix from
    the other. `Recombine(k)` applied to (a, b) yields ``a[:k] + b[k:]``."""

    point: int


Operation = Union[Substitute, Insert, Delete, Recombine]

#: Every operation kind, for enumeration by a future specification.
OPERATION_KINDS = ("substitute", "insert", "delete", "recombine")


def apply(operation: Operation, haplotype: Haplotype,
          other: "Haplotype | None" = None) -> Haplotype:
    """Apply one operation, returning a new haplotype.

    Raises :class:`GenomeError` for a structurally impossible operation — a
    position that does not exist, an allele outside the alphabet, or a length
    that would leave the bounded band. Those are *construction* failures, kept
    distinct from a viable-but-unacceptable result, which is a contract question.
    """
    if isinstance(operation, Substitute):
        _require_position(operation.position, len(haplotype))
        _require_allele(operation.allele)
        alleles = list(haplotype.alleles)
        alleles[operation.position] = operation.allele
        return Haplotype(tuple(alleles))

    if isinstance(operation, Insert):
        # Insertion may land at the very end, so the valid range is one wider
        # than for the other operations.
        if not 0 <= operation.position <= len(haplotype):
            raise GenomeError(
                f"insert position {operation.position} outside 0..{len(haplotype)}")
        _require_allele(operation.allele)
        if len(haplotype) + 1 > MAX_LENGTH:
            raise GenomeError(
                f"insert would take the haplotype to {len(haplotype) + 1}, past "
                f"the bounded maximum {MAX_LENGTH}")
        alleles = list(haplotype.alleles)
        alleles.insert(operation.position, operation.allele)
        return Haplotype(tuple(alleles))

    if isinstance(operation, Delete):
        _require_position(operation.position, len(haplotype))
        if len(haplotype) - 1 < MIN_LENGTH:
            raise GenomeError(
                f"delete would take the haplotype to {len(haplotype) - 1}, below "
                f"the bounded minimum {MIN_LENGTH}")
        alleles = list(haplotype.alleles)
        del alleles[operation.position]
        return Haplotype(tuple(alleles))

    if isinstance(operation, Recombine):
        if other is None:
            raise GenomeError("recombination needs a second haplotype")
        limit = min(len(haplotype), len(other))
        if not 0 <= operation.point <= limit:
            raise GenomeError(
                f"crossover point {operation.point} outside 0..{limit}")
        return Haplotype(haplotype.alleles[:operation.point]
                         + other.alleles[operation.point:])

    raise GenomeError(f"unknown operation {type(operation).__name__}")


def reciprocal(operation: Recombine, first: Haplotype,
               second: Haplotype) -> "tuple[Haplotype, Haplotype]":
    """Both products of one crossover.

    Meiosis produces both; a model that returns only one silently discards half
    the alleles, and the conservation law in `oracle.allele_conservation` exists
    precisely to make that impossible to do accidentally.
    """
    return (apply(operation, first, second), apply(operation, second, first))


def apply_pair(operation: Operation, first: Haplotype,
               second: Haplotype) -> "tuple[Haplotype, Haplotype]":
    """Apply one operation to a diploid pair.

    Non-crossover operations affect both current haplotypes. A crossover is a
    reciprocal operation over the *current* pair. Keeping this step explicit is
    important: evaluating each chromosome independently against the original
    partner gives the wrong semantics after the first crossover.
    """
    if isinstance(operation, Recombine):
        return reciprocal(operation, first, second)
    return apply(operation, first), apply(operation, second)


def apply_all(operations: "Sequence[Operation]", haplotype: Haplotype,
              partner: "Haplotype | None" = None) -> "tuple[Haplotype, int]":
    """Apply a sequence in order. Returns the result and the elementary allele
    visits, which is the machine-independent cost the metrics line reports."""
    visits = 0
    current = haplotype
    for operation in operations:
        current = apply(operation, current, partner)
        visits += len(current)
    return current, visits


def length_bound(operations: "Sequence[Operation]", start: int) -> "tuple[int, int]":
    """The (minimum, maximum) length the result can have, from the operation
    sequence alone.

    This single-haplotype helper is sound only for sequences without
    recombination. Use :func:`pair_length_bounds` for a diploid operation
    sequence: reciprocal crossover swaps the two current lengths when the
    haplotypes are not aligned.
    """
    if any(isinstance(op, Recombine) for op in operations):
        raise GenomeError(
            "single-haplotype length_bound cannot model recombination; "
            "use pair_length_bounds")
    inserts = sum(1 for op in operations if isinstance(op, Insert))
    deletes = sum(1 for op in operations if isinstance(op, Delete))
    return (start - deletes, start + inserts)


def pair_length_bounds(operations: "Sequence[Operation]", first: int,
                       second: int) -> "tuple[tuple[int, int], tuple[int, int]]":
    """Structural length bounds for a reciprocal diploid operation sequence.

    The calculation inspects operation *types* but never executes an operation.
    For this closed model the bounds are exact. They are returned as intervals
    to keep the contract explicit and ready for a future conditional operation.
    """
    first_low = first_high = first
    second_low = second_high = second
    for operation in operations:
        if isinstance(operation, Insert):
            first_low += 1
            first_high += 1
            second_low += 1
            second_high += 1
        elif isinstance(operation, Delete):
            first_low -= 1
            first_high -= 1
            second_low -= 1
            second_high -= 1
        elif isinstance(operation, Recombine):
            first_low, second_low = second_low, first_low
            first_high, second_high = second_high, first_high
        elif not isinstance(operation, Substitute):
            raise GenomeError(f"unknown operation {type(operation).__name__}")
    return ((first_low, first_high), (second_low, second_high))


def _require_position(position: int, length: int) -> None:
    if not 0 <= position < length:
        raise GenomeError(f"position {position} outside 0..{length - 1}")


def _require_allele(allele: int) -> None:
    if allele not in ALLELES:
        raise GenomeError(f"allele {allele!r} is not in {ALLELES}")
