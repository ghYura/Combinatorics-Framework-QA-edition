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

"""Environment variables and the genotype-by-environment interaction table.

The environment exists so that "interaction" in this model is not only
locus-by-locus. A trait can depend on a locus, on a *pair* of loci, and on a
locus *conditioned on an environmental level* — three different shapes of
dependency, all exactly computable, all enumerable by a specification later.

Every effect is a small integer from a checked-in table. That is the whole point:
the numbers are arbitrary and were chosen for arithmetic convenience, so nobody
can mistake this for a biological finding. What is *not* arbitrary is that the
table is fixed, closed and total — which is what makes an exact oracle possible.

MODELLED REPRESENTATIONS ONLY: not human DNA, not clinical, and no claim
about biological causality. See ``README.md``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Mapping

#: Environmental factors and their permitted levels. Small, ordered, integral.
FACTORS: Final[Mapping[str, tuple]] = {
    "temperature": (0, 1, 2),      # cold / baseline / hot
    "nutrient": (0, 1),            # scarce / abundant
    "density": (0, 1),             # sparse / crowded
}


class EnvironmentError_(ValueError):
    """An environment outside the declared factor levels."""


@dataclass(frozen=True)
class Environment:
    """One environmental context. Immutable, and total over `FACTORS`."""

    temperature: int = 1
    nutrient: int = 1
    density: int = 0

    def __post_init__(self) -> None:
        for name, levels in FACTORS.items():
            value = getattr(self, name)
            if value not in levels:
                raise EnvironmentError_(
                    f"environment factor {name}={value!r} is not one of {levels}")

    def as_mapping(self) -> "dict[str, int]":
        return {name: getattr(self, name) for name in FACTORS}


def baseline() -> Environment:
    """The stated reference environment. Scenarios vary *from* it, so a change in
    outcome is attributable to the variation rather than to an unstated default."""
    return Environment()


#: Genotype-by-environment interaction: (locus, allele-count, factor, level) -> effect.
#: `allele_count` is how many copies of allele 2 sit at that locus (0, 1 or 2), so
#: the table expresses dominance as well as environment sensitivity.
#: Deliberately sparse — most (locus, environment) pairs do not interact, which is
#: what makes the ones that do worth finding.
GXE_EFFECTS: Final[Mapping[tuple, int]] = {
    (2, 2, "temperature", 2): 7,    # locus 2, homozygous variant, hot
    (2, 1, "temperature", 2): 3,
    (5, 2, "nutrient", 0): -6,      # locus 5, homozygous variant, scarce nutrient
    (9, 2, "density", 1): 5,        # locus 9, homozygous variant, crowded
    (9, 1, "density", 1): 2,
}


def gxe_effect(locus: int, variant_count: int, environment: Environment) -> int:
    """The environment-conditioned contribution of one locus. Zero unless the
    table names this exact (locus, dosage, factor, level) combination."""
    total = 0
    for factor, level in environment.as_mapping().items():
        total += GXE_EFFECTS.get((locus, variant_count, factor, level), 0)
    return total
