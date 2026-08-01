"""Genetic objects as immutable mathematical values.

**Scientific boundary, stated first because it governs everything below.** This
module models *textual and mathematical representations* of genetic objects. It
is not human DNA, it is not clinical, and nothing here is a claim about
biological causality. Its alleles are small integers, its effects come from a
checked-in table chosen for arithmetic convenience, and its "phenotype" is an
integer defined by that table and nothing else. What the Bundle can validate is a
*model, a simulator, a transformation pipeline and their implementations* — never
that such a model corresponds to biology. See ``README.md`` and
``docs/37_GENETICS_APPLICATION_POSITIONING.md`` §5 R1.

Objects
-------

``Haplotype``
    One ordered sequence of alleles. Variable length, because insertions and
    deletions have to mean something; bounded, because an unbounded model has no
    exact structural oracle.

``Genotype``
    An **unordered** pair of haplotypes — diploid. Unordered is load-bearing:
    ``{h1, h2}`` and ``{h2, h1}`` are the same organism, so the pair is
    canonicalized on construction and two orderings compare and hash equal.

Both are frozen values. Every operation returns a new object, so no candidate can
observe another's state — the same determinism property the two engine
demonstrations rely on, arrived at by immutability rather than by resetting.

MODELLED REPRESENTATIONS ONLY: not human DNA, not clinical, and no claim
about biological causality. See ``README.md``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Iterable, Sequence

#: Loci in the reference genome. Twelve sits inside the 8–20 the model was scoped
#: to: wide enough for epistatic pairs to be interesting, small enough that the
#: exhaustive space stays computable and the oracle stays exact.
REFERENCE_LOCI: Final[int] = 12

#: Allele alphabet per locus. Uniform and tiny on purpose — the interesting
#: structure lives in the interaction table, not in the alphabet size.
ALLELES: Final[tuple] = (0, 1, 2)

#: Bounded length. Indels move a haplotype inside this band; leaving it is a
#: declared contract failure, not a crash.
MIN_LENGTH: Final[int] = 8
MAX_LENGTH: Final[int] = 16


class GenomeError(ValueError):
    """A structurally invalid genetic object: an allele outside the alphabet, a
    length outside the bounded band, or a position that does not exist."""


@dataclass(frozen=True)
class Haplotype:
    """One ordered allele sequence. Immutable; every operation returns a new one."""

    alleles: "tuple[int, ...]"

    def __post_init__(self) -> None:
        if not MIN_LENGTH <= len(self.alleles) <= MAX_LENGTH:
            raise GenomeError(
                f"haplotype length {len(self.alleles)} outside the bounded band "
                f"{MIN_LENGTH}..{MAX_LENGTH}")
        for position, allele in enumerate(self.alleles):
            if allele not in ALLELES:
                raise GenomeError(
                    f"allele {allele!r} at position {position} is not in {ALLELES}")

    def __len__(self) -> int:
        return len(self.alleles)

    def at(self, position: int) -> int:
        if not 0 <= position < len(self.alleles):
            raise GenomeError(f"position {position} outside 0..{len(self.alleles) - 1}")
        return self.alleles[position]

    def with_alleles(self, alleles: "Iterable[int]") -> "Haplotype":
        return Haplotype(tuple(alleles))


@dataclass(frozen=True)
class Genotype:
    """A diploid pair. Canonicalized so the pair is genuinely unordered."""

    left: Haplotype
    right: Haplotype

    def __post_init__(self) -> None:
        # Canonicalize by allele tuple so {h1,h2} == {h2,h1} under both == and
        # hash(). Doing it here rather than at every comparison site is what makes
        # "unordered" a property of the type instead of a convention every caller
        # has to remember.
        if self.right.alleles < self.left.alleles:
            left, right = self.right, self.left
            object.__setattr__(self, "left", left)
            object.__setattr__(self, "right", right)

    @property
    def aligned(self) -> bool:
        """True when both haplotypes have the same length.

        A length mismatch is not an error: an indel on one chromosome and not the
        other is exactly the kind of state the model must be able to *represent*
        in order to reject it. Whether it is acceptable is a contract question,
        answered in `oracle.viability_violation`, not an exception here.
        """
        return len(self.left) == len(self.right)

    def locus_pair(self, position: int) -> "tuple[int, int]":
        """The two alleles at one locus, ordered, so a pair is comparable."""
        a, b = self.left.at(position), self.right.at(position)
        return (a, b) if a <= b else (b, a)

    def __len__(self) -> int:
        """The aligned locus count — the loci at which both chromosomes exist."""
        return min(len(self.left), len(self.right))


def reference_haplotype() -> Haplotype:
    """The all-zero reference. Every scenario starts from a stated baseline rather
    than from something generated, so a difference is attributable."""
    return Haplotype((0,) * REFERENCE_LOCI)


def haplotype_from(alleles: "Sequence[int]") -> Haplotype:
    return Haplotype(tuple(int(a) for a in alleles))


def homozygous_reference() -> Genotype:
    return Genotype(reference_haplotype(), reference_haplotype())
