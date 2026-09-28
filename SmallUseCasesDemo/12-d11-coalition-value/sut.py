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

"""D11 system under test: the value of one coalition of six modules, by named module and bonus rules.

CONTRACT.md v1. Standalone values A=2, B=2, C=1, D=1, E=4, F=0; bonuses AB=12 (A and B present),
ACD=5 (A, C and D present), BCD=5 (B, C and D present), each applied at most once. Nothing here
knows the reference or the verdict.
"""

PLAYERS = ("A", "B", "C", "D", "E", "F")
STANDALONE = {"A": 2, "B": 2, "C": 1, "D": 1, "E": 4, "F": 0}


def evaluate(members):
    s = set(members)
    standalone = sum(STANDALONE[p] for p in s)
    bonuses = {"AB": 12 if {"A", "B"} <= s else 0,
               "ACD": 5 if {"A", "C", "D"} <= s else 0,
               "BCD": 5 if {"B", "C", "D"} <= s else 0}
    return {"standalone_value": standalone, "interaction_bonuses": bonuses, "value": standalone + sum(bonuses.values())}
