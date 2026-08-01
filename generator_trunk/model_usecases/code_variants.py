#!/usr/bin/env python3
r"""code_variants — materialises Model proposition #6 (code "variedness" + software
metrics) as a Combinatorics-Framework use-case.

> "find the sum of squares of even numbers in an array. (1) imperative for+if: high
>  cyclomatic complexity, high nesting, high LOC. (2) functional filter().map().reduce():
>  cyclomatic minimal, nesting 0 ... Metrics: Cyclomatic/Cognitive Complexity, Halstead
>  Volume/Difficulty, LOC/SLOC, Maintainability Index, Nesting Depth."   — Model AI

The Bundle breeds many FUNCTIONALLY-EQUIVALENT implementations of one logical block, runs
each against a correctness oracle (FW_VAR=0 iff it matches the reference on every test
array), and emits the software metrics as the K=V line.  The Analyzer then finds, AMONG the
correct variants, the cleanest one (min cyclomatic / min nesting / max Maintainability
Index).  This is "the same block in the maximum number of ways" turned into a measured,
optimisable search.

Decomposition -> FW_ rule (the combinatorics breeds the variety):
  | piece  | variants                                  | rule        | what it breeds
  | STYLE  | for+if / guard / while / comprehension /  | FW_Combi(1) | the paradigm / structure
  |        | listcomp / filter-map-reduce / recursion  |             |
  | EVEN   | x%2==0 / (x&1)==0 / not x%2               | FW_Combi(1) | the even-test phrasing
  | SQ     | x*x / x**2 / pow(x,2)                     | FW_Combi(1) | the square phrasing

Model's exact illustrative example, MEASURED.  Fully offline, stdlib-only (ast + tokenize
+ math), deterministic.  `emit_toml()` writes the equivalent fwgen spec.

  python3 code_variants.py
"""
from __future__ import annotations

import ast
import io
import math
import random
import sys
import tokenize
from pathlib import Path

# Each STYLE is a full function body for `def candidate(a):` with {EVEN} and {SQ} holes.
STYLES = {
    "for_nested_if": (
        "    s = 0\n"
        "    for x in a:\n"
        "        if {EVEN}:\n"
        "            s += {SQ}\n"
        "    return s\n"),
    "for_guard_continue": (
        "    s = 0\n"
        "    for x in a:\n"
        "        if not ({EVEN}):\n"
        "            continue\n"
        "        s += {SQ}\n"
        "    return s\n"),
    "while_loop": (
        "    s = 0\n"
        "    i = 0\n"
        "    while i < len(a):\n"
        "        x = a[i]\n"
        "        if {EVEN}:\n"
        "            s += {SQ}\n"
        "        i += 1\n"
        "    return s\n"),
    "comprehension": (
        "    return sum({SQ} for x in a if {EVEN})\n"),
    "listcomp": (
        "    return sum([{SQ} for x in a if {EVEN}])\n"),
    "filter_map_reduce": (
        "    from functools import reduce\n"
        "    evens = filter(lambda x: {EVEN}, a)\n"
        "    sqs = map(lambda x: {SQ}, evens)\n"
        "    return reduce(lambda p, x: p + x, sqs, 0)\n"),
    "recursion": (
        "    if not a:\n"
        "        return 0\n"
        "    x = a[0]\n"
        "    return ({SQ} if {EVEN} else 0) + candidate(a[1:])\n"),
}
EVEN = {"mod": "x % 2 == 0", "bitand": "(x & 1) == 0", "notmod": "not x % 2"}
SQ = {"mul": "x * x", "pow_op": "x ** 2", "pow_fn": "pow(x, 2)"}


def render(style: str, even: str, sq: str) -> str:
    body = STYLES[style].replace("{EVEN}", EVEN[even]).replace("{SQ}", SQ[sq])
    return "def candidate(a):\n" + body


# --------------------------------- the oracle --------------------------------- #
def reference(a):
    return sum(x * x for x in a if x % 2 == 0)


TESTS = [[], [0], [1], [2], [-4], [1, 2, 3, 4], [-3, -2, -1, 0, 1, 2],
         [10, 11, 12, 13, 14, 15], [7], [2, 2, 2]]
random.seed(7)
TESTS += [[random.randint(-20, 20) for _ in range(random.randint(0, 8))] for _ in range(20)]


def is_correct(src: str) -> bool:
    ns = {}
    try:
        exec(src, ns)
        f = ns["candidate"]
        return all(f(list(t)) == reference(t) for t in TESTS)
    except Exception:
        return False


# ------------------------------- software metrics ----------------------------- #
def sloc(src: str) -> int:
    return sum(1 for ln in src.splitlines() if ln.strip())


def cyclomatic_and_nesting(src: str):
    """McCabe cyclomatic complexity (1 + decision points) and statement nesting depth."""
    tree = ast.parse(src)
    cc = 1
    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.For, ast.While, ast.IfExp)):
            cc += 1
        elif isinstance(node, ast.BoolOp):
            cc += len(node.values) - 1
        elif isinstance(node, ast.ExceptHandler):
            cc += 1
        elif isinstance(node, ast.comprehension):
            cc += len(node.ifs)                        # filter clauses add a path; the loop doesn't
    NEST = (ast.For, ast.While, ast.If, ast.With, ast.Try)

    def depth(node, d=0):
        best = d
        for child in ast.iter_child_nodes(node):
            cd = d + 1 if isinstance(child, NEST) else d
            best = max(best, depth(child, cd))
        return best
    return cc, depth(tree)


_OPERATOR_TOKENS = {tokenize.OP}
_KW_OPERATORS = {"for", "while", "if", "else", "elif", "in", "not", "and", "or",
                 "return", "def", "lambda", "continue", "import", "from", "is"}


def halstead_volume(src: str) -> float:
    operators, operands = {}, {}
    Ntot_op = Ntot_and = 0
    toks = tokenize.generate_tokens(io.StringIO(src).readline)
    for tok in toks:
        if tok.type in _OPERATOR_TOKENS or (tok.type == tokenize.NAME and tok.string in _KW_OPERATORS):
            operators[tok.string] = operators.get(tok.string, 0) + 1
        elif tok.type in (tokenize.NAME, tokenize.NUMBER, tokenize.STRING):
            operands[tok.string] = operands.get(tok.string, 0) + 1
    n1, n2 = len(operators), len(operands)
    N1, N2 = sum(operators.values()), sum(operands.values())
    vocab = max(1, n1 + n2)
    return (N1 + N2) * math.log2(vocab)


def maintainability_index(volume: float, cc: int, lines: int) -> float:
    v = max(volume, 1.0)
    ln = max(lines, 1)
    mi = (171 - 5.2 * math.log(v) - 0.23 * cc - 16.2 * math.log(ln)) * 100.0 / 171.0
    return max(0.0, min(100.0, mi))


def metrics(src: str) -> dict:
    cc, nest = cyclomatic_and_nesting(src)
    vol = halstead_volume(src)
    L = sloc(src)
    return dict(sloc=L, cyclomatic=cc, nesting=nest,
                halstead_volume=round(vol, 1),
                maintainability_index=round(maintainability_index(vol, cc, L), 1))


# ------------------------------- emit fwgen spec ------------------------------ #
def _to_toml() -> str:
    L = ['title = "Code variedness #6 — equivalent implementations ranked by software metrics"',
         'note  = "Same logical block (sum of squares of evens) bred many ways: FW_Combi(1) over '
         'STYLE x EVEN x SQ. Oracle FW_VAR=0 iff the variant matches the reference; Analyzer ranks '
         'the CORRECT variants by Cyclomatic/Nesting/Halstead/Maintainability. Model #6, measured."',
         '# directions overridden — these metric names are not in the MIN/MAX lexicon',
         'args  = ["block=sum_of_squares_of_evens", "lang=python"]',
         '[[goals]]', 'key = "cyclomatic"', 'dir = "min"',
         '[[goals]]', 'key = "nesting"', 'dir = "min"',
         '[[goals]]', 'key = "halstead_volume"', 'dir = "min"',
         '[[goals]]', 'key = "maintainability_index"', 'dir = "max"',
         '[[goals]]', 'key = "sloc"', 'dir = "min"', "",
         '[[slots]]', 'sheet = "STYLE"', 'key = "style"', 'verb = "FW_Combi(1)"',
         'values = [' + ", ".join(f'"{s}"' for s in STYLES) + ']', "",
         '[[slots]]', 'sheet = "EVEN"', 'key = "even"', 'verb = "FW_Combi(1)"',
         'values = [' + ", ".join(f'"{e}"' for e in EVEN) + ']', "",
         '[[slots]]', 'sheet = "SQ"', 'key = "sq"', 'verb = "FW_Combi(1)"',
         'values = [' + ", ".join(f'"{s}"' for s in SQ) + ']', "",
         '[[custom_vars]]', 'code = 2', 'msg  = "variant is NOT equivalent (failed the oracle)"', ""]
    return "\n".join(L) + "\n"


def emit_toml(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_to_toml(), encoding="utf-8")
    n = len(STYLES) * len(EVEN) * len(SQ)
    print(f"  fwgen spec -> {path}  (full Core product = {n} equivalent variants)")


# ---- run-ready spec (materialized): one slot of 63 self-measuring candidates for the full Bundle ---- #
# HEAD embeds the oracle + metric functions; the CANDIDATE slot carries the 63 rendered `def
# candidate`; TAIL runs the oracle, self-measures via inspect.getsource(candidate), sets FW_VAR,
# and prints the K=V the Analyzer ranks (maintainability_index / cyclomatic ...).
RUN_TAIL = '''
_ok = all(candidate(list(t)) == reference(t) for t in TESTS)
FW_VAR = 0 if _ok else 2
_m = metrics(inspect.getsource(candidate))
print("app=codevar correct=%d cyclomatic=%d nesting=%d halstead_volume=%.1f "
      "maintainability_index=%.1f sloc=%d FW_VAR=%d"
      % (1 if _ok else 0, _m["cyclomatic"], _m["nesting"], _m["halstead_volume"],
         _m["maintainability_index"], _m["sloc"], FW_VAR))
'''


def _run_head() -> str:
    import inspect as _i
    return ("import ast, io, math, tokenize, inspect\n"
            + _i.getsource(reference) + _i.getsource(sloc)
            + _i.getsource(cyclomatic_and_nesting)
            + "_OPERATOR_TOKENS = {tokenize.OP}\n_KW_OPERATORS = " + repr(_KW_OPERATORS) + "\n"
            + _i.getsource(halstead_volume) + _i.getsource(maintainability_index)
            + _i.getsource(metrics) + "TESTS = " + repr(TESTS) + "\n")


def emit_run_toml(path: Path):
    def raw_slot(sheet, frags):
        L = ['[[slots]]', f'sheet = "{sheet}"', f'key   = "{sheet.lower()}"',
             'verb  = "FW_Combi(1)"', 'raw   = true', 'values = [']
        for f in frags:
            body = f if f.startswith("\n") else "\n" + f
            L.append("'''" + (body if body.endswith("\n") else body + "\n") + "''',")
        return L + [']', '']
    variants = [render(st, ev, sq) for st in STYLES for ev in EVEN for sq in SQ]
    L = ['title = "Code variedness #6 (RUN) — 63 equivalent variants self-measured, full Bundle"',
         'note  = "Each candidate self-measures (inspect.getsource) and prints its software metrics; '
         'the Analyzer ranks the correct variants by Maintainability/Cyclomatic."',
         'args = ["mode=code_variants_run"]',
         '[[goals]]', 'key = "maintainability_index"', 'dir = "max"',
         '[[goals]]', 'key = "cyclomatic"', 'dir = "min"',
         '[[goals]]', 'key = "nesting"', 'dir = "min"', '']
    L += raw_slot("HEAD", [_run_head()])
    L += raw_slot("CANDIDATE", variants)
    L += raw_slot("TAIL", [RUN_TAIL])
    L += ['[[custom_vars]]', 'code = 2', 'msg  = "variant not equivalent (failed oracle)"', '']
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"  RUN spec -> {path}  ({len(variants)} self-measuring candidates for bundle_run.py)")


def main():
    if "--run" in sys.argv[1:]:
        a = [x for x in sys.argv[1:] if not x.startswith("--")]
        emit_run_toml(Path(a[0]) if a else
                      Path(__file__).resolve().parent / "run" / "code_variants" / "code_variants_run.toml")
        return
    out = Path(sys.argv[1] if len(sys.argv) > 1 else
               str(Path(__file__).resolve().parent / "specs" / "code_variants.toml"))
    print("=== Code variedness (Model #6): rank equivalent variants by software metrics ===")
    print("    block = 'sum of squares of even numbers'; oracle = match reference on 30 arrays\n")

    rows = []
    n_total = n_ok = 0
    for style in STYLES:
        for even in EVEN:
            for sq in SQ:
                n_total += 1
                src = render(style, even, sq)
                ok = is_correct(src)
                if not ok:
                    continue
                n_ok += 1
                m = metrics(src)
                rows.append((style, even, sq, m))

    print(f"  variants bred: {n_total}   |   passed the equivalence oracle (FW_VAR=0): {n_ok}\n")
    # one representative per STYLE (EVEN/SQ phrasing barely moves the metrics)
    by_style = {}
    for style, even, sq, m in rows:
        by_style.setdefault(style, (even, sq, m))
    print(f"    {'style':<20}{'sloc':>5}{'cyclo':>7}{'nest':>6}{'halstead':>10}{'MI':>7}")
    for style in STYLES:
        if style not in by_style:
            continue
        _e, _s, m = by_style[style]
        print(f"    {style:<20}{m['sloc']:>5}{m['cyclomatic']:>7}{m['nesting']:>6}"
              f"{m['halstead_volume']:>10}{m['maintainability_index']:>7}")

    # the Analyzer's pick: lowest cyclomatic, then nesting, then highest MI (among correct)
    best = min(rows, key=lambda r: (r[3]["cyclomatic"], r[3]["nesting"],
                                    -r[3]["maintainability_index"], r[3]["sloc"]))
    worst = max(rows, key=lambda r: (r[3]["cyclomatic"], r[3]["nesting"], r[3]["sloc"]))
    bs, _, _, bm = best
    ws, _, _, wm = worst
    print(f"\n  Analyzer pick (cleanest): {bs}  ->  "
          f"cyclomatic={bm['cyclomatic']} nesting={bm['nesting']} MI={bm['maintainability_index']}")
    print(f"  vs the bulkiest correct : {ws}  ->  "
          f"cyclomatic={wm['cyclomatic']} nesting={wm['nesting']} MI={wm['maintainability_index']}")
    print("  exactly Model's example: the functional chain flattens nesting to 0 and drops")
    print("  cyclomatic to 1, while the nested for+if carries the branches and the depth.\n")
    print(f"  sample K=V (one variant): correct=1 style={bs} "
          f"sloc={bm['sloc']} cyclomatic={bm['cyclomatic']} nesting={bm['nesting']} "
          f"halstead_volume={bm['halstead_volume']} maintainability_index={bm['maintainability_index']}\n")
    emit_toml(out)


if __name__ == "__main__":
    main()
