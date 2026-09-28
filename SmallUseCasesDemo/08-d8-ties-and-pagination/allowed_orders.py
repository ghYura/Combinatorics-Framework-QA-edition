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

"""D8a auxiliary proof: rank-only valid orders versus this fixture's stable-order promise (offline).

    python allowed_orders.py        # write proof/allowed-orders.json

For each of the 75 rank vectors and both directions, take the stable sequence (ties in input order)
and reverse every tie block. `valid_order` checks complete identities and primary rank order only;
`stable_order` also requires original input order inside ties. Expected: all 150 alternatives are
valid; stable_order rejects exactly the 102 that contain a tie and accepts the 48 strict orders.
This is not a Framework campaign and adds nothing to the 450 campaign cases.
"""
import itertools
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
IDS = "ABCD"


def stable(ranks, direction):
    s = 1 if direction == "asc" else -1
    return sorted(IDS, key=lambda c: (s * ranks[IDS.index(c)], IDS.index(c)))


def reverse_tie_blocks(seq, ranks):
    out, block = [], []
    for c in seq:
        if block and ranks[IDS.index(c)] != ranks[IDS.index(block[0])]:
            out += block[::-1]
            block = []
        block.append(c)
    return out + block[::-1]


def valid_order(seq, ranks, direction):
    r = [ranks[IDS.index(c)] for c in seq]
    return sorted(seq) == list(IDS) and all((a <= b) if direction == "asc" else (a >= b) for a, b in zip(r, r[1:]))


def stable_order(seq, ranks, direction):
    return valid_order(seq, ranks, direction) and all(
        IDS.index(a) < IDS.index(b) for a, b in zip(seq, seq[1:]) if ranks[IDS.index(a)] == ranks[IDS.index(b)])


def proof():
    vectors = [r for r in itertools.product(range(4), repeat=4) if set(r) == set(range(max(r) + 1))]
    rows = []
    for r in vectors:
        for d in ("asc", "desc"):
            alt = reverse_tie_blocks(stable(r, d), r)
            rows.append({"ranks": "".join(map(str, r)), "direction": d, "stable": stable(r, d), "alternative": alt,
                         "has_tie": len(set(r)) < 4, "valid_order": valid_order(alt, r, d), "stable_order": stable_order(alt, r, d)})
    summary = {"alternatives": len(rows), "valid": sum(x["valid_order"] for x in rows),
               "stable_rejected": sum(not x["stable_order"] for x in rows), "stable_accepted": sum(x["stable_order"] for x in rows),
               "rejected_exactly_the_tied": all(x["stable_order"] != x["has_tie"] for x in rows)}
    example = next(x for x in rows if x["ranks"] == "0000" and x["direction"] == "asc")
    return {"schema": "d8a.allowed-orders/v1", "summary": summary, "example_0000_asc": example, "rows": rows}


def main():
    doc = proof()
    (HERE / "proof").mkdir(exist_ok=True)
    (HERE / "proof" / "allowed-orders.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"summary": doc["summary"], "example_0000_asc": doc["example_0000_asc"]}))


if __name__ == "__main__":
    main()
