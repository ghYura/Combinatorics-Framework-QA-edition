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

"""D9 system under test: the cost of one portfolio in one operating world, by the named rules.

CONTRACT.md v1. Modules (canonical order) with fixed costs; each module's loss reduction follows its
rule for demand d and disruption x. Gross loss = demand loss + disruption loss; the selected
reductions are summed and subtracted, then the result is clamped ONCE at zero. Total = fixed costs
+ residual loss. Integer arithmetic. Nothing here knows the reference or the verdict.
"""

MODULES = ("cache", "quota", "network_backup", "disk_replica", "staff_reserve", "cross_region")
FIXED = {"cache": 3, "quota": 2, "network_backup": 5, "disk_replica": 6, "staff_reserve": 4, "cross_region": 8}
DEMAND_LOSS = (4, 11, 22, 15)
DISRUPTION_LOSS = (0, 14, 19, 9)


def reduction(module, d, x):
    if module == "cache":
        return (0, 3, 8, 6)[d]
    if module == "quota":
        return (0, 2, 6, 7)[d]
    if module == "network_backup":
        return 11 if x == 1 else 0
    if module == "disk_replica":
        return 14 if x == 2 else 0
    if module == "staff_reserve":
        return 6 if x == 3 else 0
    if module == "cross_region":
        return 8 if x in (1, 2) else 0
    raise ValueError(f"unknown module {module!r}")


def evaluate(selected, d, x):
    reductions = [reduction(m, d, x) if m in selected else 0 for m in MODULES]
    fixed = sum(FIXED[m] for m in selected)
    gross = DEMAND_LOSS[d] + DISRUPTION_LOSS[x]
    raw = gross - sum(reductions)
    residual = max(0, raw)
    return {"fixed_cost": fixed, "gross_loss": gross, "reductions": reductions, "raw_loss": raw,
            "residual_loss": residual, "total_cost": fixed + residual}
