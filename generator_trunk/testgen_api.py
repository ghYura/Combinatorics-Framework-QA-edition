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

r"""Orders-API combinatorial test design — decompose a real test into logical
pieces and DISTRIBUTE each piece to the combination rule that semantically breeds
new tests. Emits: real runnable .java tests, a Core CANDIDATE workbook (materialized),
and a native rich-verb FW_Seq workbook (Core expands).

Why each piece gets the rule it gets (the whole point):
  • orthogonal request dimensions  → CARTESIAN  (FW_Combi(1) leaves)
  • an ORDER-sensitive op sequence  → PERMUTATIONS (FW_Permut)   — ordering/state bugs
  • independent OPTIONAL headers    → SUBSETS    (FW_Subsets)    — header-interaction bugs
  • "apply a few of many" faults    → COMBINATIONS C(n,2) (FW_Combi(2)) — compound-validation gaps
The cross product of these breeds tests no human writes by hand (e.g. a permuted
[delete,create,read] with an expired token, a subset {If-Match,Accept-Encoding}, and a
2-mutation body) — yet each is a real, runnable edge case.
"""
from __future__ import annotations

import itertools
import random
import subprocess
import tempfile
from pathlib import Path

import fwgen as fg
from openpyxl import Workbook

HERE = Path(__file__).resolve().parent
HARNESS = (HERE / "scenarios" / "api_orders" / "harness.java").read_text(encoding="utf-8")
OUT_TESTS = HERE / "generated_tests"
OUT_XLSX = HERE / "scenarios" / "api_orders"

# ---------------------------------------------------------------------------
# 1. Decomposition — each logical piece + the rule it is distributed to
# ---------------------------------------------------------------------------
CARTESIAN = [   # orthogonal request dimensions → FW_Combi(1) (cartesian leaves)
    ("RESOURCE",     "resource", ["/orders", "/users/1/orders"]),
    ("AUTH",         "auth",     ["Bearer valid_token", "Bearer expired_token", "", "Bearer wrong_scope"]),
    ("CONTENT_TYPE", "ctype",    ["application/json", "application/xml", "text/plain", ""]),
    ("QUERY",        "query",    ["", "?limit=-1"]),
    ("EXPECT",       "expect",   ["200", "201", "400", "401", "404", "409"]),   # int target for the oracle
]
PERMUT_OPS     = ["create", "read", "update", "delete"]                          # FW_Permut  → 24 orderings
SUBSET_HEADERS = ['Idempotency-Key:k1', 'If-Match:"v1"', 'Accept-Encoding:gzip',
                  'X-Forwarded-For:127.0.0.1', 'X-Request-ID:r1']                # FW_Subsets → 32 subsets
COMBI_MUTATORS = ["oversize", "drop_required", "wrong_type",
                  "extra_unknown", "null_value", "dup_key"]                      # FW_Combi(2) → C(6,2)=15

VERDICTS = [(2, "server 5xx / crash"), (3, "leaked stacktrace / error text in body"),
            (4, "broke JSON contract (non-JSON for a json request)"),
            (5, "wrong final HTTP status vs expected"),
            (6, "transport / timeout / uncaught exception")]

# ---------------------------------------------------------------------------
# 2. Rule expansions (mirror what the Core verbs do)
# ---------------------------------------------------------------------------
def permutations_of(xs):          return list(itertools.permutations(xs))
def subsets_of(xs):               return [c for r in range(len(xs) + 1) for c in itertools.combinations(xs, r)]
def kcombos_of(xs, k):            return list(itertools.combinations(xs, k))

OP_VALUES  = permutations_of(PERMUT_OPS)        # 24
HDR_VALUES = subsets_of(SUBSET_HEADERS)         # 32
MUT_VALUES = kcombos_of(COMBI_MUTATORS, 2)      # 15

def space_size():
    n = 1
    for _, _, vals in CARTESIAN:
        n *= len(vals)
    return n * len(OP_VALUES) * len(HDR_VALUES) * len(MUT_VALUES)

# ---------------------------------------------------------------------------
# 3. Assemble a real .java test from one combination
# ---------------------------------------------------------------------------
def jstr(s):  return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'
def jarr(items): return "{" + ", ".join(jstr(x) for x in items) + "}"

def assemble(resource, auth, ctype, query, expect, ops, headers, muts) -> str:
    slot_lines = [
        f"String RESOURCE = {jstr(resource)};",
        f"String AUTH = {jstr(auth)};",
        f"String CONTENT_TYPE = {jstr(ctype)};",
        f"String QUERY = {jstr(query)};",
        f"int EXPECT_STATUS = {int(expect)};",
        f"String[] OP_SEQUENCE = {jarr(ops)};",
        f"String[] OPT_HEADERS = {jarr(headers)};",
        f"String[] MUTATORS = {jarr(muts)};",
    ]
    block = "\n            ".join(slot_lines)
    import re
    return re.sub(r"/\* SLOTS-BEGIN.*?SLOTS-END \*/", block, HARNESS, flags=re.S)

# ---------------------------------------------------------------------------
# 4. Curated "unexpected" combinations + baseline + random sample
#    (combo = resource, auth, ctype, query, expect, ops, headers, muts)
# ---------------------------------------------------------------------------
def combo(resource="/orders", auth="Bearer valid_token", ctype="application/json",
          query="", expect="200", ops=("create", "read", "update", "delete"),
          headers=(), muts=()):
    return (resource, auth, ctype, query, expect, list(ops), list(headers), list(muts))

CURATED = [
    ("baseline_happy_path", combo(),
     "Happy path: full CRUD in natural order, valid auth, expect 200."),
    ("delete_before_create", combo(ops=("delete", "create", "read", "update"), expect="404"),
     "PERMUT bug-hunt: act on a resource before it exists — 404 expected, 500 = state bug."),
    ("read_after_delete", combo(ops=("create", "delete", "read"), expect="404"),
     "PERMUT: read-after-delete — stale-cache / soft-delete leak hunt."),
    ("expired_token_write", combo(auth="Bearer expired_token", ops=("create", "update"), expect="401"),
     "CARTESIAN×PERMUT: mutation with an expired token — must be 401, not silent write."),
    ("content_type_mismatch", combo(ctype="text/plain", ops=("create",), expect="400"),
     "CARTESIAN: JSON body sent as text/plain — content-negotiation (expect 400/415)."),
    ("compound_malformation", combo(ops=("create",), muts=("drop_required", "wrong_type"), expect="400"),
     "COMBI(2): two simultaneous body faults — compound-validation gap hunt."),
    ("oversize_plus_gzip", combo(ops=("create",), muts=("oversize", "extra_unknown"),
                                 headers=('Accept-Encoding:gzip',), expect="201"),
     "SUBSET×COMBI(2): huge body + unknown field + gzip negotiation — DoS / parser-limit hunt."),
    ("conditional_idempotency", combo(ops=("update", "update"), headers=('If-Match:"v1"', 'Idempotency-Key:k1'),
                                       expect="409") if False else
                                combo(ops=("update", "read"), headers=('If-Match:"v1"', 'Idempotency-Key:k1'), expect="409"),
     "SUBSET: If-Match + Idempotency-Key together on update — conditional/idempotency interaction (expect 409/412)."),
    ("negative_query_param", combo(query="?limit=-1", ops=("read",), expect="400"),
     "CARTESIAN: negative pagination — boundary validation (expect 400, not 500/empty)."),
    ("no_auth_full_crud", combo(auth="", expect="401"),
     "CARTESIAN: full CRUD with NO Authorization header — every step must 401."),
]

def random_sample(n=4, seed=20260525):
    rnd = random.Random(seed)
    out = []
    for i in range(n):
        c = (rnd.choice(CARTESIAN[0][2]), rnd.choice(CARTESIAN[1][2]), rnd.choice(CARTESIAN[2][2]),
             rnd.choice(CARTESIAN[3][2]), rnd.choice(CARTESIAN[4][2]),
             list(rnd.choice(OP_VALUES)), list(rnd.choice(HDR_VALUES)), list(rnd.choice(MUT_VALUES)))
        out.append((f"random_{i+1}", c, "Random draw from the full space (seeded) — an 'unexpected' test."))
    return out

# ---------------------------------------------------------------------------
# 5. Emit real .java tests + manifest, compile-check, build both workbooks
# ---------------------------------------------------------------------------
def emit_tests():
    OUT_TESTS.mkdir(parents=True, exist_ok=True)
    for f in OUT_TESTS.glob("*.java"):
        f.unlink()
    cases = CURATED + random_sample()
    manifest = ["# Generated Orders-API tests — combination → what it probes", ""]
    programs = []
    for i, (name, c, why) in enumerate(cases):
        prog = assemble(*c)
        (OUT_TESTS / f"{i:02d}_{name}.java").write_text(prog, encoding="utf-8")
        programs.append((f"{i:02d}_{name}", prog))
        manifest.append(f"- **{i:02d}_{name}** — ops={c[5]} auth={c[1]!r} ct={c[2]!r} "
                        f"hdrs={c[6]} muts={c[7]} expect={c[4]}\n    - {why}")
    (OUT_TESTS / "MANIFEST.md").write_text("\n".join(manifest), encoding="utf-8")
    return programs

def compile_check(programs):
    ok = 0
    with tempfile.TemporaryDirectory() as d:
        for name, prog in programs:
            src = Path(d) / "Candidate.java"
            src.write_text(prog, encoding="utf-8")
            r = subprocess.run(["javac", "-d", d, str(src)], capture_output=True, text=True)
            if r.returncode == 0:
                ok += 1
            else:
                print(f"  COMPILE FAIL {name}: {r.stderr.splitlines()[0] if r.stderr else '?'}")
    return ok, len(programs)

def build_materialized_workbook(programs):
    """Each generated test = one CANDIDATE row; the Core passes it through (FW_Combi(1))."""
    spec = fg.parse_spec(fg.build_spec_dict(
        "api_orders_sample",
        [(s, k, v) for (s, k, v) in CARTESIAN],
        title="Orders API — materialized combinatorial test sample",
        goals=["bugs_found"], custom_vars=VERDICTS), "api_orders_sample")
    rows = [p for _, p in programs]
    assert not any("\\n" in r or "\\t" in r for r in rows), "program has literal \\n/\\t — would be mangled"
    path = OUT_XLSX / "api_orders_materialized.xlsx"
    fg.build_materialized(spec, rows, data_sheet="CANDIDATE").save(path)
    return path, fg.validate_workbook(path)

def build_native_fwseq_workbook():
    """The elegant native form: the CORE applies the per-piece rule and concatenates
    HEAD + slot-statements + TAIL. FW_SheetNames wraps each value into a Java statement;
    FW_Group renders array slots. (Structural blueprint — verb distribution is the point.)"""
    head = HARNESS.split("/* SLOTS-BEGIN")[0].rstrip() + "\n"
    tail = HARNESS.split("/* SLOTS-END */", 1)[1]
    NL = "\n            "
    # FW_Seq: (sheet, flag, verb)  — the RULE DISTRIBUTION, made concrete
    seq = [("HEAD", "FW_Reuse", "FW_Combi(1)"),
           ("RESOURCE", "FW_Reuse", "FW_Combi(1)"), ("AUTH", "FW_Reuse", "FW_Combi(1)"),
           ("CONTENT_TYPE", "FW_Reuse", "FW_Combi(1)"), ("QUERY", "FW_Reuse", "FW_Combi(1)"),
           ("EXPECT", "FW_Reuse", "FW_Combi(1)"),
           ("OP", "FW_Reuse", "FW_Permut"),            # ORDER-sensitive sequence
           ("HDR", "FW_Reuse", "FW_Subsets"),          # optional headers present/absent
           ("MUT", "FW_Reuse", "FW_Combi(2)"),         # apply 2 of N faults
           ("TAIL", "FW_Reuse", "FW_Combi(1)")]
    # FW_SheetNames: (sheet, prefix, ending) — wraps each value into a Java statement.
    names = {
        "HEAD": ("FW_EMPTY_STRING", "FW_EMPTY_STRING"),
        "RESOURCE": ('String RESOURCE = "', '";' + NL), "AUTH": ('String AUTH = "', '";' + NL),
        "CONTENT_TYPE": ('String CONTENT_TYPE = "', '";' + NL), "QUERY": ('String QUERY = "', '";' + NL),
        "EXPECT": ("int EXPECT_STATUS = ", ";" + NL),
        "OP": ("String[] OP_SEQUENCE = {", "};" + NL),
        "HDR": ("String[] OPT_HEADERS = {", "};" + NL),
        "MUT": ("String[] MUTATORS = {", "};" + NL),
        "TAIL": ("FW_EMPTY_STRING", "FW_EMPTY_STRING")}
    data = {
        "HEAD": [head + NL], "TAIL": [tail],
        "RESOURCE": CARTESIAN[0][2], "AUTH": CARTESIAN[1][2], "CONTENT_TYPE": CARTESIAN[2][2],
        "QUERY": CARTESIAN[3][2], "EXPECT": CARTESIAN[4][2],
        "OP": PERMUT_OPS, "HDR": SUBSET_HEADERS, "MUT": COMBI_MUTATORS}
    # FW_Group rendering for the array slots: strip [ ] and quote each token into Java elements.
    group = ('FW_Group\nFW_ReplaceRE("^\\[", "")\nFW_ReplaceRE("\\]$", "")\n'
             'FW_ReplaceRE("([^,\\s][^,]*[^,\\s]|[^,\\s])", "\\"$1\\"")\nFW_ReplaceRE("\\"\\, \\"", "\\", \\"")')

    wb = Workbook(); s = wb.active; s.title = "FW_Seq"
    for i, (sh, flag, verb) in enumerate(seq, 1):
        s.cell(i, 1, sh); s.cell(i, 2, flag); s.cell(i, 4, verb)
        if sh in ("OP", "HDR", "MUT"):
            s.cell(i, 5, group)                       # render array tokens → Java string elements
    nm = wb.create_sheet("FW_SheetNames")
    for i, (sh, _, _) in enumerate(seq, 1):
        pre, end = names[sh]; nm.cell(i, 1, sh); nm.cell(i, 2, pre); nm.cell(i, 3, end)
    wb.create_sheet("FW_RunMeFirstOnce").cell(1, 1, "FW_EMPTY_STRING")
    aw = wb.create_sheet("FW_Arguments"); aw.cell(1, 1, "API_BASE=http://localhost:8080")
    cv = wb.create_sheet("FW_CUSTOM_VAR")
    for i, (code, msg) in enumerate(VERDICTS, 1):
        cv.cell(i, 1, int(code)); cv.cell(i, 2, f"FWCUSTOMVAR={code} {msg}")
    info = wb.create_sheet("FW_Info")
    for row in s.iter_rows(values_only=True):
        info.append(row)
    for sh, _, _ in seq:
        ws = wb.create_sheet(sh)
        for r, v in enumerate(data[sh], 1):
            ws.cell(r, 1, str(v))
    path = OUT_XLSX / "api_orders_native_fwseq.xlsx"
    wb.save(path)
    return path


if __name__ == "__main__":
    print("=" * 78)
    print("Orders-API combinatorial test design")
    print("=" * 78)
    print(f"\nRule distribution & space:")
    cart = 1
    for sh, _, vals in CARTESIAN:
        print(f"  {sh:<13} {len(vals):>3}  → FW_Combi(1)  [cartesian]"); cart *= len(vals)
    print(f"  {'OP_SEQUENCE':<13} {len(OP_VALUES):>3}  → FW_Permut    [order-sensitive: {PERMUT_OPS}]")
    print(f"  {'OPT_HEADERS':<13} {len(HDR_VALUES):>3}  → FW_Subsets   [2^{len(SUBSET_HEADERS)} optional-header combos]")
    print(f"  {'MUTATORS':<13} {len(MUT_VALUES):>3}  → FW_Combi(2)   [C({len(COMBI_MUTATORS)},2) compound faults]")
    print(f"\n  cartesian block = {cart}   →  TOTAL SPACE = {space_size():,} runnable tests")

    progs = emit_tests()
    print(f"\nEmitted {len(progs)} real .java tests → {OUT_TESTS.relative_to(HERE)}/  (+ MANIFEST.md)")
    ok, tot = compile_check(progs)
    print(f"javac 21 compile-check: {ok}/{tot} compile clean")

    mpath, merrs = build_materialized_workbook(progs)
    print(f"materialized workbook → {mpath.name}  [{'VALID' if not merrs else merrs}]")
    npath = build_native_fwseq_workbook()
    print(f"native FW_Seq workbook → {npath.name}  (rule distribution + FW_SheetNames code-wrappers + FW_Group)")

    print("\n----- example UNEXPECTED test (delete_before_create) -----")
    eg = assemble(*CURATED[1][1])
    print("\n".join(l for l in eg.splitlines() if "String " in l or "int EXPECT" in l))
