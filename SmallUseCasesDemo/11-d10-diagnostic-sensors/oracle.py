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

"""D10 reference: a literal 7 x 8 signature table (class -> S0..S7) and the label -> class map.

Written out as data, independently of the SUT's flag injection and probe functions; it never reads
frozen case results. Class 0 is the declared healthy reference H0.
"""

SIGNATURES = [
    [0, 0, 0, 0, 0, 0, 0, 0],   # class 0: H0, code 0
    [1, 0, 0, 0, 1, 1, 0, 1],   # class 1: F01, F02, code 1
    [0, 1, 0, 0, 1, 0, 1, 1],   # class 2: F03, F04, code 2
    [0, 0, 1, 0, 0, 1, 1, 1],   # class 3: F05, F06, code 4
    [0, 0, 0, 1, 1, 1, 1, 0],   # class 4: F07, F08, code 8
    [1, 1, 1, 0, 0, 0, 0, 1],   # class 5: F09, F10, code 7
    [1, 1, 1, 1, 1, 1, 1, 1],   # class 6: F11, F12, code 15
]
CLASS_OF = {"H0": 0, "F01": 1, "F02": 1, "F03": 2, "F04": 2, "F05": 3, "F06": 3, "F07": 4, "F08": 4,
            "F09": 5, "F10": 5, "F11": 6, "F12": 6}


def expected_readings(label, selected):
    row = SIGNATURES[CLASS_OF[label]]
    return [row[s] for s in sorted(selected)]
