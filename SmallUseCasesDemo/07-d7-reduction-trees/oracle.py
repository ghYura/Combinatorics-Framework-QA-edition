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
# Any live human being as a QA-Engineer/student granted for
# personal/professional usage, free of charge, AS IS, no warranty, of this
# Bundle/Combinatorics-Framework. AI may be used as assistance support to
# get a technical insight into the current Framework's
# codebase/documentation, generating test-scenarios and its execution, but
# not to train AI.
#
# (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
# Ukraine
#
# See LICENSE and NOTICE.md for the binding terms.

"""D7 reference: the exact rational sum of the five REPRESENTED binary64 inputs, and the budget test.

Policy-blind: it reads only the input hex strings (never the tree or the policy) and sums their exact
Fraction values left to right. Errors are exact rationals; a result passes when it is finite and its
absolute error is at most the frozen budget (inclusive).
"""
import math
from fractions import Fraction


def reference(input_hex):
    total = Fraction(0)
    for h in input_hex:
        total += Fraction(float.fromhex(h))
    return total


def exact_value(result):
    """Fraction of a float or Fraction result; None for a nonfinite float."""
    if isinstance(result, float):
        return Fraction(result) if math.isfinite(result) else None
    return Fraction(result)


def judge(result, ref, budget):
    """(absolute error or None, finite, within budget)."""
    value = exact_value(result)
    if value is None:
        return None, False, False
    err = abs(value - ref)
    return err, True, err <= budget
