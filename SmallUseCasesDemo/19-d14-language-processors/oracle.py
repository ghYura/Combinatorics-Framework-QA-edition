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

"""D14a mechanical oracle: three policy-blind output relations over one candidate's two variants.

CONTRACT.md v1. Given the original and transformed observations (reference and VM values only):
  original_differential     original VM value == original reference value
  transformed_differential  transformed VM value == transformed reference value
  metamorphic               original VM value == transformed VM value
The two reference values must agree (z is fresh and never read); if they do not, the fixture itself
is wrong and a ValueError is raised (a setup error). PASS requires all three checks; a numeric
discrepancy is DOMAIN_FAIL. Bytecode and traces are diagnostic only and are never compared here.
"""
CHECKS = ("original_differential", "transformed_differential", "metamorphic")


def judge(original, transformed):
    values = (original["reference_value"], transformed["reference_value"], original["vm_value"], transformed["vm_value"])
    if any(type(v) is not int for v in values):
        raise ValueError(f"missing or non-integer value in {values}")
    if original["reference_value"] != transformed["reference_value"]:
        raise ValueError("reference values differ: the dead-code transformation or the reference is wrong")
    checks = {"original_differential": original["vm_value"] == original["reference_value"],
              "transformed_differential": transformed["vm_value"] == transformed["reference_value"],
              "metamorphic": original["vm_value"] == transformed["vm_value"]}
    return checks, "PASS" if all(checks.values()) else "DOMAIN_FAIL"
