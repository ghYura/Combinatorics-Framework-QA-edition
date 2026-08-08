#!/usr/bin/env python3
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

"""inventory_reconciler — warehouse stock tracking with a DUAL-COUNT invariant.

It applies a short sequence of stock movements to an item while keeping a parallel
"ledger" total that must ALWAYS equal the physical on-hand count. Backorder protection
and a shrinkage allowance are optional features. The module is self-checking: it sets
the verdict variable FW_VAR = 1 whenever an invariant is violated (the ledger drifts
away from on-hand, or on-hand goes negative while backorder protection is on), and
FW_VAR = 0 when every invariant held.

As written, every movement keeps on_hand and ledger in lock-step, so this baseline run
is clean (FW_VAR = 0). The interesting behaviour appears once the individual pieces are
rewritten and recombined: some implementation choices / movement orders / option
combinations break the lock-step and the self-check catches them.

This is the Python analogue of LedgerEngine.java. The Bundle's Executor compiles only
Java, so the Python chain is Core -> Reader (reassemble a .py per combo) -> the Python
Executor analog (py_executor.py), which runs each program and records its FW_VAR verdict.
"""

FW_VAR = 0                  # verdict: 0 = invariants held, 1 = a violation was found

on_hand = 0                 # physical units on hand
ledger = 0                  # independent running total; must equal on_hand exactly
backorder_guard = False     # optional: stop on_hand from going negative
apply_shrinkage = False     # optional: subtract a fixed shrinkage allowance
round_mode = 0              # 0 = none, 1 = floor-to-10, 2 = half-up-to-10


# --- stock movements: each is supposed to keep on_hand and ledger in lock-step ---
def receive(qty):
    global on_hand, ledger
    on_hand += qty
    ledger += qty


def ship(qty):
    global on_hand, ledger
    on_hand -= qty
    ledger -= qty


def reorder_estimate(level):
    return level // 100         # restock hint, ~1% of the level


def shrinkage_units():
    return 3                    # flat shrinkage allowance


# --- rounding: applied identically to on_hand and ledger so they stay equal ---
def round_units(v):
    if round_mode == 1:
        return (v // 10) * 10           # floor to nearest 10
    if round_mode == 2:
        return ((v + 5) // 10) * 10     # half-up to nearest 10
    return v                            # no rounding


# --- optional backorder protection: lift a negative on-hand back to zero ---
def apply_backorder_guard():
    global on_hand, ledger
    if backorder_guard and on_hand < 0:
        correction = -on_hand
        on_hand += correction
        ledger += correction


def main():
    global on_hand, ledger, FW_VAR
    # configuration
    on_hand = 100
    ledger = 100
    move = 120

    # a sequence of stock movements
    receive(move)
    ship(move + 50)
    hint = reorder_estimate(on_hand)
    on_hand += hint
    ledger += hint

    # optional features
    if apply_shrinkage:
        s = shrinkage_units()
        on_hand -= s
        ledger -= s
    apply_backorder_guard()

    # normalise the representation
    on_hand = round_units(on_hand)
    ledger = round_units(ledger)

    # self-check: dual-count drift, or a negative on-hand under protection
    drift = (on_hand != ledger)
    negative = (backorder_guard and on_hand < 0)
    FW_VAR = 1 if (drift or negative) else 0
    print("FW_VAR=%d on_hand=%d ledger=%d" % (FW_VAR, on_hand, ledger))


main()
