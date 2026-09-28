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

"""D11 reference: a multilinear indicator expression over a separate term table.

v(x) = sum over terms T of coefficient(T) * product(x_i for i in T), with x the 0/1 membership vector
in A..F order. Singleton terms carry the standalone values; three higher-order terms carry the
interactions. It never reads frozen case results.
"""

TERMS = [((0,), 2), ((1,), 2), ((2,), 1), ((3,), 1), ((4,), 4), ((5,), 0),
         ((0, 1), 12), ((0, 2, 3), 5), ((1, 2, 3), 5)]
NAMES = {(0, 1): "AB", (0, 2, 3): "ACD", (1, 2, 3): "BCD"}


def expected(x):
    """x: six 0/1 flags. Returns (standalone value, interaction bonuses, value)."""
    def term(idx, coef):
        prod = 1
        for i in idx:
            prod *= x[i]
        return coef * prod
    standalone = sum(term(idx, c) for idx, c in TERMS if len(idx) == 1)
    bonuses = {NAMES[idx]: term(idx, c) for idx, c in TERMS if len(idx) > 1}
    return standalone, bonuses, standalone + sum(bonuses.values())
