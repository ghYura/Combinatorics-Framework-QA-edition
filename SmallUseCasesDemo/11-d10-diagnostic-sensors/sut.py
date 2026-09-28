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

"""D10 system under test: inject a fault's status flags, then read the selected sensors.

CONTRACT.md v1. Flags (a,b,c,d) are bits 0..3 of the fault's state code (least significant first).
Sensors S0..S7 read a, b, c, d, a^b^d, a^c^d, b^c^d, a^b^c. Each injection starts from a fresh
flag state; only the selected sensors are read, once each, in index order. "H0" (healthy, code 0)
is supported for the declared reference control only. Nothing here knows the reference table or
the verdict.
"""

FAULT_CODES = {"H0": 0, "F01": 1, "F02": 1, "F03": 2, "F04": 2, "F05": 4, "F06": 4, "F07": 8, "F08": 8,
               "F09": 7, "F10": 7, "F11": 15, "F12": 15}
PROBES = (lambda a, b, c, d: a, lambda a, b, c, d: b, lambda a, b, c, d: c, lambda a, b, c, d: d,
          lambda a, b, c, d: a ^ b ^ d, lambda a, b, c, d: a ^ c ^ d, lambda a, b, c, d: b ^ c ^ d,
          lambda a, b, c, d: a ^ b ^ c)


class Plant:
    def __init__(self, label):
        if label not in FAULT_CODES:
            raise ValueError(f"unknown fault label {label!r}")
        code = FAULT_CODES[label]
        self.flags = [(code >> i) & 1 for i in range(4)]

    def read(self, sensor):
        return PROBES[sensor](*self.flags)


def observe(label, selected):
    """(latent flag bits a,b,c,d; readings of the selected sensors in index order)."""
    plant = Plant(label)
    return list(plant.flags), [plant.read(s) for s in sorted(selected)]
