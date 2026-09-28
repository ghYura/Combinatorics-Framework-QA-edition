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

"""An independent model of how Core composes D13b's context expressions (no Framework, SUT or runtime code).

    python construct.py --precheck     # write precheck/precheck.json before any campaign

It re-implements the Core semantics the contract names:
  * dictionary codes: first value code = number of data sheets + 1, then sheet by sheet, row by row;
  * FW_Cartes(X) first pass: each sheet value v gives the row [v, x] for every X value x;
  * FW_Group: the rows are content-sorted, the grouped verb runs over whole rows, the nested
    code-string (Java List.toString, e.g. "[[30, 29], [31, 29]]") is rewritten by each FW_ReplaceRE
    line, then every bracket is stripped and the rest split on ", ";
  * FW_Permut() over the grouped rows emits every order of the complete rows;
  * FW_Combi(size) over one row emits that row unchanged (index-based, duplicates kept);
  * M:N brace: [start] + a + [relation] + b + [end] for every a, b; FW_() is the latest brace target.
Structural decoding parses the rendered ROOT text with `ast` and never executes it. verify.py applies
the same model to the live dictionary and compares it with the rows Core actually wrote. Only the
--precheck path executes anything: the 108 predicted programs, each in a fresh host interpreter.
"""
import argparse
import ast
import itertools
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GEN = Path(__file__).resolve().parents[2] / "generator_trunk"
REPLACE_RE = re.compile(r'(FW_ReplaceRE\(["](.+?)["],\s+("(.*)")\))')
CARRIERS = ("retrieved_page", "tool_result")


def parse_rewrites(group_cell):
    """[(pattern, replacement)] in line order; a quoted empty string means delete."""
    return [(m.group(2), "" if m.group(3) == '""' else m.group(4)) for m in REPLACE_RE.finditer(group_cell)]


def java_list(rows):
    return "[" + ", ".join("[" + ", ".join(str(c) for c in r) + "]" for r in rows) + "]"


def group_emit(rows, rules):
    """One grouped emission: (code-string before, after each rewrite, parsed codes)."""
    s = java_list(rows)
    steps = [s]
    for pattern, rep in rules:
        s = re.sub(pattern, lambda _m, r=rep: r, s)
        steps.append(s)
    codes = [int(t) for t in re.sub(r"[{}\[\]]", "", s).split(", ") if t.strip()]
    return steps, codes


def join_mn(a_rows, b_rows, start=None, rel=None, end=None):
    return [([start] if start is not None else []) + a + ([rel] if rel is not None else []) + b + ([end] if end is not None else [])
            for a in a_rows for b in b_rows]


def construct(codes, group_cell):
    """All intermediate rows from a code map {sheet: [codes in row order]}."""
    first = lambda sheet: codes[sheet][0]                       # noqa: E731
    rules = parse_rewrites(group_cell)
    cartes = [[v, x] for v in codes["CHUNKS"] for x in codes["LEAF_END"]]
    grouped_in = sorted(cartes)
    emissions = [group_emit(list(p), rules) for p in itertools.permutations(grouped_in)]
    chunks = [codes_ for _s, codes_ in emissions]                # FW_Combi(size): each row unchanged
    prefix = [[c] for c in codes["PREFIX"]]
    inner = join_mn(prefix, chunks, rel=first("LIST_OPEN"), end=first("LIST_END"))
    note = [[c] for c in codes["NOTE"]]
    root = join_mn(inner, note, start=first("CONTEXT_OPEN"), rel=first("COMMA"), end=first("CONTEXT_CLOSE"))
    return {"rewrites": rules, "CHUNKS_cartes": cartes, "CHUNKS_group_input": grouped_in,
            "CHUNKS_group_steps": [s for s, _c in emissions], "CHUNKS": chunks, "INNER": inner, "ROOT": root}


def predicted_codes(sheets):
    codes, nxt = {}, len(sheets) + 1
    for name, values in sheets:
        codes[name] = list(range(nxt, nxt + len(values)))
        nxt += len(values)
    return codes


def workbook_sheets(xlsx):
    sys.path.insert(0, str(GEN))
    import fwgen as fg
    sheets = fg.workbook_to_json(xlsx)["sheets"]
    seq = next(s for s in sheets if s["name"] == "FW_Seq")["rows"]
    data = [(s["name"], [r[0] for r in s["rows"]]) for s in sheets if not s["name"].startswith("FW_")]
    group = next(c for r in seq for c in r if isinstance(c, str) and c.startswith("FW_Group"))
    return data, group, seq


def _call(node, name, nargs):
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != name \
            or len(node.args) != nargs or node.keywords:
        raise ValueError(f"expected {name}() with {nargs} argument(s), got {ast.dump(node)[:80]}")
    return node.args


def decode_root(text):
    """Structure of one rendered ROOT expression, by syntax only:
    consume(context([trusted_task(), <carrier>([source_item("a"), source_item("b")]), trusted_note()]))."""
    body = ast.parse(text).body
    if len(body) != 1 or not isinstance(body[0], ast.Expr):
        raise ValueError("ROOT is not one expression statement")
    (ctx,) = _call(body[0].value, "consume", 1)
    (lst,) = _call(ctx, "context", 1)
    if not isinstance(lst, ast.List) or len(lst.elts) != 3:
        raise ValueError("context needs a three-element list")
    task, carrier, note = lst.elts
    _call(task, "trusted_task", 0)
    _call(note, "trusted_note", 0)
    if not isinstance(carrier, ast.Call) or not isinstance(carrier.func, ast.Name) or carrier.func.id not in CARRIERS:
        raise ValueError("middle child is not a carrier constructor")
    (items,) = _call(carrier, carrier.func.id, 1)
    if not isinstance(items, ast.List) or len(items.elts) != 2:
        raise ValueError("a carrier holds exactly two items")
    names = [ast.literal_eval(_call(x, "source_item", 1)[0]) for x in items.elts]
    if sorted(names) != ["filler", "marker"]:
        raise ValueError(f"items {names}")
    return {"carrier": carrier.func.id, "order": "".join(n[0].upper() for n in names), "items": names}


def precheck():
    data, group, seq = workbook_sheets(HERE / "spec" / "demo.xlsx")
    codes = predicted_codes(data)
    model = construct(codes, group)
    text = {c: v for name, vals in data for c, v in zip(codes[name], vals)}
    val = dict(data)
    root_text = ["".join(text[c] for c in row) for row in model["ROOT"]]
    structure = [decode_root(t) for t in root_text]
    # The 108 predicted candidates: sheet columns in order, each followed by a newline as the Reader does.
    programs = {}
    for impl, enc, mark, root in itertools.product(val["IMPL"], val["ENCODING"], val["MARKER"], root_text):
        programs[len(programs)] = "\n".join([val["HEAD"][0], impl, enc, mark, root, val["TAIL"][0]]) + "\n"
    lines = []
    for i, src in programs.items():
        r = subprocess.run([sys.executable, "-c", src], capture_output=True, text=True, timeout=60)
        if r.returncode != 0 or len(r.stdout.splitlines()) != 1:
            raise SystemExit(f"predicted program {i} failed: {r.stderr[-800:]}")
        lines.append(dict(t.split("=", 1) for t in r.stdout.split() if "=" in t))
    derived = json.loads((HERE / "architect-derived.json").read_text())
    frozen = {c["id"]: c["predicted_outcome"] for c in derived["cases"]}
    got = {l["case"]: l["verdict"] for l in lines}
    return {"schema": "d13b.precheck/v1", "note": "before execution; codes predicted from the workbook, programs run on the host",
            "predicted_codes": codes, "rewrite_cell": group, "model": model,
            "counts": {"CHUNKS": len(model["CHUNKS"]), "INNER": len(model["INNER"]), "ROOT": len(model["ROOT"]),
                       "programs": len(programs)},
            "row_lengths": {k: sorted({len(r) for r in model[k]}) for k in ("CHUNKS", "INNER", "ROOT")},
            "CHUNKS_as_text": [[text[c] for c in r] for r in model["CHUNKS"]],
            "ROOT_text": root_text, "ROOT_structure": structure,
            "carriers_x_orders": sorted((s["carrier"], s["order"]) for s in structure),
            "program_ids_equal_frozen": sorted(got) == sorted(frozen),
            "program_verdicts_equal_frozen": got == frozen,
            "program_outcomes": {v: list(got.values()).count(v) for v in sorted(set(got.values()))}}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--precheck", action="store_true", required=True)
    ap.parse_args()
    rep = precheck()
    out = HERE / "precheck"
    out.mkdir(exist_ok=True)
    (out / "precheck.json").write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: rep[k] for k in ("counts", "row_lengths", "carriers_x_orders", "program_ids_equal_frozen",
                                          "program_verdicts_equal_frozen", "program_outcomes")}))
    for t in rep["ROOT_text"]:
        print(repr(t))
    ok = (rep["counts"] == {"CHUNKS": 2, "INNER": 4, "ROOT": 4, "programs": 108}
          and rep["row_lengths"] == {"CHUNKS": [4], "INNER": [7], "ROOT": [11]}
          and rep["carriers_x_orders"] == sorted(itertools.product(CARRIERS, ("FM", "MF")))
          and rep["program_ids_equal_frozen"] and rep["program_verdicts_equal_frozen"])
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
