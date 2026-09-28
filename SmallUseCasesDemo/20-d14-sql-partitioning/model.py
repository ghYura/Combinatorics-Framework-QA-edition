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

"""D14b independent logical model: the frozen fixture under SQL three-valued logic (no database, no SQL).

CONTRACT.md v1. Truth values are True, False and None (UNKNOWN), combined with Kleene connectives:
NOT keeps UNKNOWN, AND is FALSE if either side is FALSE, OR is TRUE if either side is TRUE, otherwise
UNKNOWN wins over the remaining definite value; a comparison with a NULL operand is UNKNOWN and
IS NULL is always definite. A WHERE clause keeps a row only when its condition is TRUE, so the false
branch keeps rows whose predicate is FALSE (NOT UNKNOWN stays UNKNOWN) and the unknown branch those
whose predicate is UNKNOWN. Joins are evaluated from the fixture rows (the left join keeps an item
without tags once, with NULL tag columns). The model never sees an adapter policy or a live result.
"""
ITEMS = ((1, "a", None, True), (2, "a", 0, False), (3, "a", 1, None),
         (4, "b", 1, True), (5, "b", 2, False), (6, "b", None, None))          # id, grp, val, flag
TAGS = ((1, "p"), (1, "q"), (3, "p"), (4, "p"), (4, "q"), (5, "p"))              # item_id, tag


def k_not(a):
    return None if a is None else not a


def k_and(a, b):
    if a is False or b is False:
        return False
    return None if a is None or b is None else True


def k_or(a, b):
    if a is True or b is True:
        return True
    return None if a is None or b is None else False


def compare(value, op, constant):
    if value is None:
        return None
    return value > constant if op == ">" else value == constant


def truth(item, predicate):
    _, _, val, flag = item
    table = {"gt0": lambda: compare(val, ">", 0), "eq1": lambda: compare(val, "=", 1), "flag": lambda: flag,
             "and": lambda: k_and(compare(val, ">", 0), flag), "or": lambda: k_or(compare(val, "=", 1), flag),
             "is_null": lambda: val is None}
    return table[predicate]()


def source(query):
    """The joined rows each query shape scans (one entry per result row before projection)."""
    if query == "scan":
        return list(ITEMS)
    if query == "filtered":
        return [i for i in ITEMS if i[1] == "a"]
    out = []
    for item in ITEMS:
        matches = [t for t in TAGS if t[0] == item[0]]
        out += [item] * len(matches) if matches else ([item] if query == "left_join" else [])
    return out


def order(values):
    return sorted(([v] for v in values), key=lambda r: (r[0] is not None, r[0] if r[0] is not None else 0))


def expected(query, predicate):
    rows = source(query)
    if query == "filtered":                                   # the base filter is TRUE for every scanned row
        assert all(i[1] == "a" for i in rows)
    return {"base": order(i[2] for i in rows),
            "true": order(i[2] for i in rows if truth(i, predicate) is True),
            "false": order(i[2] for i in rows if k_not(truth(i, predicate)) is True),
            "unknown": order(i[2] for i in rows if truth(i, predicate) is None)}
