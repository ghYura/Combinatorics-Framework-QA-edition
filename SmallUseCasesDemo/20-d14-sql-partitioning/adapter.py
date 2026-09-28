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

"""D14b system under test: query construction and a result-recombining adapter with three policies.

CONTRACT.md v1. For a base shape and a predicate p, four SELECTs project only i.val:
  base     <shape> WHERE <base filter>
  true     <shape> WHERE (<base filter>) AND (p)
  false    <shape> WHERE (<base filter>) AND NOT (p)
  unknown  <shape> WHERE (<base filter>) AND ((p) IS NULL)
The base filter is i.grp = 'a' for `filtered` and TRUE otherwise, retained in every branch. The adapter
then recombines the three partition results it actually received:
  union_all     true ++ false ++ unknown (duplicates kept)
  omit_unknown  true ++ false            (the collected unknown rows are discarded)
  dedup_union   true ++ false ++ unknown, then duplicate tuples removed (the planted error)
Nothing here knows the fixture, the expected rows or the verdict.
"""
QUERIES = ("scan", "filtered", "inner_join", "left_join")
PREDICATES = {"gt0": "i.val > 0", "eq1": "i.val = 1", "flag": "i.flag", "and": "(i.val > 0) AND i.flag",
              "or": "(i.val = 1) OR i.flag", "is_null": "i.val IS NULL"}
POLICIES = ("union_all", "omit_unknown", "dedup_union")
BRANCHES = ("base", "true", "false", "unknown")
JOINS = {"inner_join": " JOIN fixture.tags AS t ON t.item_id=i.id", "left_join": " LEFT JOIN fixture.tags AS t ON t.item_id=i.id"}


def build_sql(query, predicate):
    if query not in QUERIES or predicate not in PREDICATES:
        raise ValueError(f"unknown query family {query!r}/{predicate!r}")
    prefix = "SELECT i.val FROM fixture.items AS i" + JOINS.get(query, "")
    base = "i.grp = 'a'" if query == "filtered" else "TRUE"
    p = PREDICATES[predicate]
    where = {"base": base, "true": f"({base}) AND ({p})", "false": f"({base}) AND NOT ({p})",
             "unknown": f"({base}) AND (({p}) IS NULL)"}
    return {b: prefix + " WHERE " + where[b] for b in BRANCHES}


def recombine(policy, results):
    """The adapter's reconstruction of the base result from the partition results it received."""
    if policy not in POLICIES:
        raise ValueError(f"unknown adapter policy {policy!r}")
    parts = ("true", "false") if policy == "omit_unknown" else ("true", "false", "unknown")
    rows = [list(r) for part in parts for r in results[part]]
    if policy == "dedup_union":
        seen, unique = set(), []
        for r in rows:
            if tuple(r) not in seen:
                seen.add(tuple(r))
                unique.append(r)
        rows = unique
    return rows
