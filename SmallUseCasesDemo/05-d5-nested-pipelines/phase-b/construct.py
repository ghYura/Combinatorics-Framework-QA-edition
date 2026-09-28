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

"""An independent model of how Core constructs D5 phase B's rows (no Framework, SUT or runtime code).

    python construct.py --precheck     # write precheck/<B1|B2>.json before any campaign (predicted codes)

It follows the Core source semantics the contract names, re-implemented here:
  * dictionary codes: sheet by sheet in workbook order, row by row, starting after the sheet keys;
  * FW_ReplaceRE `+ SHEET +` splice: the quoted replacement's word is the sheet name, replaced by
    that sheet's first value code, quotes removed, split on `\\s?\\+\\s?` and re-joined;
  * the rewrites apply in line order to the grouped string "[[code]]", then every bracket is
    stripped and the rest is split on ", ";
  * FW_Subsets in binary-counting order, empty row skipped by the later pass;
  * 1:1 pairs only equal-length rows and alternates their elements; M:N concatenates
    a, relation, b; start/end wrap the row; FW_()G concatenates all rows of the operand.
verify.py applies the same model to the live dictionary and compares it with Core's decoded rows.
"""
import argparse
import itertools
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPLACE_RE = re.compile(r'(FW_ReplaceRE\(["](.+?)["],\s+("(.*)")\))')


def parse_rewrites(group_cell):
    """[(pattern, quoted replacement expression)] in line order, as Core's matcher reads them."""
    return [(m.group(2), m.group(3)) for m in REPLACE_RE.finditer(group_cell)]


def splice(expr, first_code_of):
    """Core's `+ SHEET +` replacement: (sheet name, resolved replacement text)."""
    sheet = re.sub(r"\W+", "", expr)
    text = re.sub(r"\w+", str(first_code_of(sheet)), expr).replace('"', "")
    return sheet, "".join(re.split(r"\s?\+\s?", text))


def rewrite_steps(opcode, rules, first_code_of):
    """The grouped string before and after each ordered rewrite, and the parsed codes."""
    s = f"[[{opcode}]]"
    steps = [s]
    for pattern, expr in rules:
        _, rep = splice(expr, first_code_of)
        s = re.sub(pattern, lambda _m, r=rep: r, s)
        steps.append(s)
    codes = [int(t) for t in re.sub(r"[{}\[\]]", "", s).split(", ") if t.strip()]
    return steps, codes


def subsets(values):
    """FW_Subsets first pass (binary counting), then the later pass skips the empty row."""
    rows = [[v for i, v in enumerate(values) if mask >> i & 1] for mask in range(2 ** len(values))]
    return rows, [r for r in rows if r]


def join_1to1(a_rows, b_rows):
    out = []
    for a in a_rows:
        for b in (r for r in b_rows if len(r) == len(a)):
            out.append([x for pair in itertools.zip_longest(a, b) for x in pair if x is not None])
    return out


def join_mn(a_rows, b_rows, start=None, rel=None, end=None):
    return [([start] if start is not None else []) + a + ([rel] if rel is not None else []) + b + ([end] if end is not None else [])
            for a in a_rows for b in b_rows]


def construct(codes, group_cell):
    """All intermediate and final rows from a code map {sheet: [codes in row order]}."""
    first = lambda sheet: codes[sheet][0]                       # noqa: E731
    rules = parse_rewrites(group_cell)
    e1 = {}
    for code in codes["E1"]:
        steps, row = rewrite_steps(code, rules, first)
        e1[code] = {"steps": steps, "row": row}
    reversed_rules = [rules[1], rules[0], rules[2]]
    tmp_leak = {code: rewrite_steps(code, reversed_rules, first) for code in codes["E1"]}
    e2_first, e2 = subsets(codes["E2"])
    e3 = [[c] for c in codes["E3"]]
    e1_rows = [e1[c]["row"] for c in codes["E1"]]
    jzip = join_1to1(e1_rows, e2)
    jcat = join_mn(e1_rows, e3)
    root = join_mn(jzip, jcat, start=first("PIPE_OPEN"), rel=first("REL_S"), end=first("PIPE_CLOSE"))
    out = {"rewrites": [{"pattern": p, "replacement": e, "splice": splice(e, first)} for p, e in rules],
           "E1": e1, "E1_rows": e1_rows,
           "reversed_1_2": {c: {"steps": s, "row": r, "contains_TMP": first("TMP") in r} for c, (s, r) in tmp_leak.items()},
           "E2_first_pass": e2_first, "E2": e2, "E2_lengths": sorted(len(r) for r in e2), "E3": e3,
           "JZIP": jzip, "JCAT": jcat, "ROOT": root}
    if "BUNDLE_OPEN" in codes:
        out["SEAL"] = [[c] for c in codes["SEAL"]]
        out["BUNDLE_members"] = root                             # any order; FW_()G concatenates all rows
        out["BUNDLE_length"] = 1 + sum(len(r) for r in root) + 1 + 1
    return out


def predicted_codes(sheets):
    """Core's assignment: first value code = number of data sheets + 1, then sheet by sheet, row by row."""
    codes, nxt = {}, len(sheets) + 1
    for name, values in sheets:
        codes[name] = list(range(nxt, nxt + len(values)))
        nxt += len(values)
    return codes


def workbook_sheets(xlsx):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "generator_trunk"))
    import fwgen as fg
    sheets = fg.workbook_to_json(xlsx)["sheets"]
    seq = next(s for s in sheets if s["name"] == "FW_Seq")["rows"]
    data = [(s["name"], [r[0] for r in s["rows"]]) for s in sheets if not s["name"].startswith("FW_")]
    group = next(c for r in seq for c in r if isinstance(c, str) and c.startswith("FW_Group"))
    return data, group, seq


def decode_tree(values):
    """Parse rendered fragment texts into (calls, trees) with an own stack; raises on bad structure."""
    import ast
    calls, trees, stack = [], [], None
    for v in values:
        body = ast.parse(v).body
        if len(body) != 1 or not isinstance(body[0], ast.Expr) or not isinstance(body[0].value, ast.Call):
            raise ValueError(f"not one call: {v!r}")
        call = body[0].value
        name, args = call.func.id, [ast.literal_eval(a) for a in call.args]
        calls.append([name, *args])
        if name == "begin_pipeline":
            if stack is not None:
                raise ValueError("nested pipeline")
            stack = [[]]
        elif name == "open_scope":
            node = {"scope": args[0], "children": []}
            stack[-1].append(node)
            stack.append(node["children"])
        elif name == "op":
            stack[-1].append(args[0])
        elif name == "close_scope":
            if len(stack) < 2:
                raise ValueError("unbalanced close")
            stack.pop()
        elif name == "end_pipeline":
            if len(stack) != 1:
                raise ValueError("pipeline ends inside a scope")
            trees.append(stack[0])
            stack = None
        elif name not in ("begin_bundle", "seal_bundle", "end_bundle"):
            raise ValueError(f"unexpected fragment {name}")
    if stack is not None:
        raise ValueError("unterminated pipeline")
    return calls, trees


def tree_id(t):
    outer, s, cat, tail = t
    (inner,) = outer["children"]
    z, n = inner["children"]
    (c,) = cat["children"]
    if (outer["scope"], inner["scope"], n, s, cat["scope"]) != ("x", "y", "N", "S", "x"):
        raise ValueError(f"shape: {t}")
    return f"ZIP={z}|CAT={c}|TAIL={tail}"


def precheck(campaign):
    data, group, seq = workbook_sheets(HERE / "spec" / campaign / "demo.xlsx")
    codes = predicted_codes(data)
    model = construct(codes, group)
    text = {c: v for name, vals in data for c, v in zip(codes[name], vals)}
    root_trees = [decode_tree([text[c] for c in row])[1][0] for row in model["ROOT"]]
    derived = json.loads((HERE / "architect-derived.json").read_text())
    ids = sorted(tree_id(t) for t in root_trees)
    by_id = {tree_id(t): t for t in root_trees}
    rep = {"schema": "d5b.precheck/v1", "campaign": campaign, "note": "before execution; codes predicted from the workbook",
           "predicted_codes": codes, "rewrite_cell": group, "model": model,
           "E1_rows_as_text": [[text[c] for c in r] for r in model["E1_rows"]],
           "ROOT_rows_as_text": [[text[c] for c in r] for r in model["ROOT"]],
           "counts": {"E1": len(model["E1_rows"]), "E2_after_subsets": len(model["E2_first_pass"]), "E2_after_identity": len(model["E2"]),
                      "E3": len(model["E3"]), "JZIP": len(model["JZIP"]), "JCAT": len(model["JCAT"]), "ROOT": len(model["ROOT"])},
           "row_lengths": {k: sorted({len(r) for r in model[k]}) for k in ("E1_rows", "JZIP", "JCAT", "ROOT")},
           "tree_ids": ids,
           "trees_equal_frozen": ids == sorted(t["id"] for t in derived["trees"]) and all(by_id[t["id"]] == t["tree"] for t in derived["trees"]),
           "no_TMP_in_valid_rows": all(codes["TMP"][0] not in r for r in model["ROOT"]),
           "reversed_rules_leave_TMP": all(v["contains_TMP"] for v in model["reversed_1_2"].values())}
    if campaign == "B2":
        rep["BUNDLE_length"] = model["BUNDLE_length"]
    return rep


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--precheck", action="store_true", required=True)
    ap.parse_args()
    out = HERE / "precheck"
    out.mkdir(exist_ok=True)
    for campaign in ("B1", "B2"):
        rep = precheck(campaign)
        (out / f"{campaign}.json").write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")
        print(campaign, json.dumps({k: rep[k] for k in ("counts", "row_lengths", "trees_equal_frozen", "no_TMP_in_valid_rows",
                                                        "reversed_rules_leave_TMP")} | ({"BUNDLE_length": rep["BUNDLE_length"]} if campaign == "B2" else {})))


if __name__ == "__main__":
    main()
