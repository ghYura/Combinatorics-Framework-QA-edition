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

"""D13e judge surrogates: two pseudorandom noise channels over a supplied mechanical label.

CONTRACT.md v1. This is a labelled calibration fixture, not a semantic judge: each judge receives
the known mechanical label and may flip it. Per trial, one draw is shared by both judges (their
errors are intentionally paired):
  draw_hex = first 16 hex characters of SHA-256(ASCII "d13e|{policy}|{task}|{order}|{trial}")
  n = int(draw_hex, 16), D = 2**64
  calibrated       flips iff 10*n < D                        (nominal error 1/10)
  position_biased  flips iff 5*n < 3*D when G is at positions 1-3 (early band, nominal 3/5)
                   flips iff 10*n < D  when G is at positions 4-6 (late band, nominal 1/10)
approval = mechanical label XOR flip: "the judge claims the decision is correct". Approvals are
reported only; they never decide a verdict.
"""
import hashlib

JUDGES = ("calibrated", "position_biased")
D = 2 ** 64


def band(guard_position):
    if type(guard_position) is not int or not 1 <= guard_position <= 6:
        raise ValueError(f"guard position {guard_position!r} outside 1..6")
    return "early" if guard_position <= 3 else "late"


def draw(policy, task, order, trial):
    material = f"d13e|{policy}|{task}|{order}|{trial}".encode("ascii")
    draw_hex = hashlib.sha256(material).hexdigest()[:16]
    return draw_hex, int(draw_hex, 16)


def flips(n, guard_position):
    if type(n) is not int or not 0 <= n < D:
        raise ValueError(f"draw {n!r} outside [0, 2**64)")
    early = band(guard_position) == "early"
    return {"calibrated": 10 * n < D, "position_biased": 5 * n < 3 * D if early else 10 * n < D}


def approvals(mechanical_ok, flip_bits):
    if type(mechanical_ok) is not bool:
        raise ValueError("the supplied mechanical label must be a bool")
    return {j: mechanical_ok != flip_bits[j] for j in JUDGES}
