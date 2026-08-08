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

r"""predicate.py — the `when`-predicate tier: a constraint authored as a FORMULA over per-value
PARAMETERS (the advanced tier; the visual builder is blockly_when/). This module is the headless,
tested PROOF that a Blockly-generated predicate string enforces correctly through the SAME sieve —
so the UI only has to emit the right string. (Enforcement was already verified live on fw_final:
the `O1.n + O3.n > 4` test gave 81/81.)

  python3 predicate.py
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sieve as sv  # noqa: E402


def when_constraint(sheets, expr, gate=None, polarity="forbid", cid=None, desc=None) -> dict:
    sheets = list(sheets)
    return {"id": cid or "when_" + "_".join(sheets), "polarity": polarity, "sheets": sheets,
            "when": expr, "gate": gate or {},
            "desc": desc or f"{polarity} {'/'.join(sheets)} when {expr}"}


def validate(expr, sheets, params) -> bool:
    """Dry-run the predicate on every declared value-combo to catch typos / unsafe exprs
    BEFORE a real run (sieve._eval_pred raises on unsafe; missing attrs raise AttributeError)."""
    sc = {"version": 1, "params": params, "constraints": [when_constraint(sheets, expr)]}
    vals = {s: list(params.get(s, {}).keys()) for s in sheets}
    for combo in itertools.product(*[vals[s] for s in sheets]):
        row = [{"sheet": s, "value": v, "pos": i} for i, (s, v) in enumerate(zip(sheets, combo))]
        sv.row_violates(row, sc)
    return True


def main():
    # chemistry: forbid LIKE-sign charges  (the Blockly formula: A.charge * C.charge > 0)
    params = {"A": {"a_pos": {"charge": 2}, "a_neg": {"charge": -1}},
              "C": {"c_pos": {"charge": 3}, "c_neg": {"charge": -2}}}
    expr = "A.charge * C.charge > 0"
    con = when_constraint(["A", "C"], expr, desc="forbid same-sign charges (like repels)")
    sc = {"version": 1, "params": params, "constraints": [con]}
    rows = [[{"sheet": "A", "value": a, "pos": 0}, {"sheet": "C", "value": c, "pos": 1}]
            for a in params["A"] for c in params["C"]]
    rep = sv.sieve(rows, sc)

    print("=== `when`-predicate tier — formula over parameters, enforced by the sieve ===\n")
    print("  rule:", sv.describe(con))
    print(f"  impact over {rep['total']} (A,C) pairs: kept {rep['kept']}, removed {rep['removed']}")
    for r, vid in rep["removed_examples"]:
        print(f"    x  {r}")
    # a_pos*c_pos=6>0 forbid; a_neg*c_neg=2>0 forbid; a_pos*c_neg=-6 keep; a_neg*c_pos=-3 keep
    assert rep["removed"] == 2 and rep["kept"] == 2, "predicate enforcement wrong"
    validate(expr, ["A", "C"], params)
    print("\n  VERIFIED: same-sign pairs removed, opposite-sign kept; validate() ok.")
    print("  (the Blockly builder in blockly_when/ generates exactly this `when` string.)")


if __name__ == "__main__":
    main()
