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

"""D14b oracle: policy-blind multiset comparison plus independent checks of every query result.

CONTRACT.md v1. Rows are one-column lists; NULL is None. A bag counts every tuple, NULL included.
  query_checks[b]  the live bag of query b (base, true, false, unknown) equals the model's bag
  tlp_ok           the base bag equals the adapter's recombined bag
  set_equal        the same comparison on sets: a diagnostic only, never the oracle
PASS requires all four query checks and tlp_ok; otherwise DOMAIN_FAIL. A malformed result raises.
"""
from collections import Counter

import model

BRANCHES = ("base", "true", "false", "unknown")


def canonical(rows):
    for r in rows:
        if not isinstance(r, list) or len(r) != 1 or not (r[0] is None or type(r[0]) is int):
            raise ValueError(f"malformed one-column row {r!r}")
    return sorted((list(r) for r in rows), key=lambda r: (r[0] is not None, r[0] if r[0] is not None else 0))


def bag(rows):
    counts = Counter(tuple(r) for r in canonical(rows))
    return [{"row": list(k), "count": n} for k, n in sorted(counts.items(), key=lambda kv: (kv[0][0] is not None, kv[0][0] or 0))]


def judge(query, predicate, query_rows, combined_rows):
    if sorted(query_rows) != sorted(BRANCHES):
        raise ValueError(f"missing query observations: {sorted(query_rows)}")
    want = model.expected(query, predicate)
    checks = {b: bag(query_rows[b]) == bag(want[b]) for b in BRANCHES}
    tlp_ok = bag(query_rows["base"]) == bag(combined_rows)
    set_equal = {tuple(r) for r in query_rows["base"]} == {tuple(r) for r in combined_rows}
    verdict = "PASS" if all(checks.values()) and tlp_ok else "DOMAIN_FAIL"
    return {"query_checks": checks, "tlp_ok": tlp_ok, "set_equal": set_equal, "verdict": verdict}
