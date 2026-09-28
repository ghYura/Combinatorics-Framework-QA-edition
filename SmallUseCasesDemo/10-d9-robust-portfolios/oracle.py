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

"""D9 reference: an independently declared per-module, per-world benefit table (16 worlds x 6 modules).

Worlds are (demand, disruption) in lexicographic order. The table is written out row by row from
the contract's module rules rather than computed by them; costs come from a separate literal. The
reference never reads frozen results.
"""

MODULE_ORDER = ["cache", "quota", "network_backup", "disk_replica", "staff_reserve", "cross_region"]
COST = [3, 2, 5, 6, 4, 8]
GROSS = {                      # (demand, disruption) -> gross loss = [4,11,22,15][d] + [0,14,19,9][x]
    (0, 0): 4, (0, 1): 18, (0, 2): 23, (0, 3): 13,
    (1, 0): 11, (1, 1): 25, (1, 2): 30, (1, 3): 20,
    (2, 0): 22, (2, 1): 36, (2, 2): 41, (2, 3): 31,
    (3, 0): 15, (3, 1): 29, (3, 2): 34, (3, 3): 24,
}
BENEFIT = {                    # (demand, disruption) -> benefit of each module, in MODULE_ORDER
    (0, 0): [0, 0, 0, 0, 0, 0], (0, 1): [0, 0, 11, 0, 0, 8], (0, 2): [0, 0, 0, 14, 0, 8], (0, 3): [0, 0, 0, 0, 6, 0],
    (1, 0): [3, 2, 0, 0, 0, 0], (1, 1): [3, 2, 11, 0, 0, 8], (1, 2): [3, 2, 0, 14, 0, 8], (1, 3): [3, 2, 0, 0, 6, 0],
    (2, 0): [8, 6, 0, 0, 0, 0], (2, 1): [8, 6, 11, 0, 0, 8], (2, 2): [8, 6, 0, 14, 0, 8], (2, 3): [8, 6, 0, 0, 6, 0],
    (3, 0): [6, 7, 0, 0, 0, 0], (3, 1): [6, 7, 11, 0, 0, 8], (3, 2): [6, 7, 0, 14, 0, 8], (3, 3): [6, 7, 0, 0, 6, 0],
}


def expected(mask, d, x):
    """mask: six 0/1 flags in module order."""
    red = [f * b for f, b in zip(mask, BENEFIT[(d, x)])]
    raw = GROSS[(d, x)] - sum(red)
    fixed = sum(f * c for f, c in zip(mask, COST))
    return {"fixed_cost": fixed, "gross_loss": GROSS[(d, x)], "reductions": red, "raw_loss": raw,
            "residual_loss": raw if raw > 0 else 0, "total_cost": fixed + (raw if raw > 0 else 0)}
