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

r"""difftest — materialises Model proposition #4 (Differential Fuzzing / logical-bug
search) as a Combinatorics-Framework use-case.

> "If your text chunks represent test inputs ... combine the calls, execute the target,
>  and track ... combinations that trigger [divergent behaviour]. Automated security and
>  robustness testing for complex, stateful systems like ... compilers."   — Model AI

The repo already does *single-target* fuzzing (cybersec_protocol_fuzz, cybersec_waf_redteam:
one binary, find a crash).  This adds the missing **differential** half: the combinatorics
breeds a structured input, the harness feeds the SAME input to TWO implementations of one
spec, and `FW_VAR != 0` flags a DIVERGENCE — a logical bug with no oracle needed but the
two programs disagreeing (the CSmith / EMI school of compiler testing, in miniature).

Worked target: an arithmetic-expression evaluator.
  * impl_A = a CORRECT precedence evaluator (Python's arithmetic eval).
  * impl_B = a NAIVE strict left-to-right evaluator that ignores precedence & parens
             (a real, extremely common bug).
Differential verdict: divergence  <=>  A(expr) != B(expr).

Decomposition -> which FW_ rule breeds what:
  | piece            | variants            | rule        | what it breeds
  | O1,O2,O3 operands| {1,2,3}             | FW_Combi(1) | orthogonal value axes
  | OP1,OP2 operators| {+,-,*}             | FW_Combi(1) | the precedence-sensitive structure
  | UNARY lead minus | present / absent    | FW_Subsets  | sign-handling interactions
  | PARENS group 1st | present / absent    | FW_Subsets  | grouping the naive parser drops

The Analyzer (`divergences:max`) maximises findings; its top-K / minimal-input view returns
the SIMPLEST counterexample (delta-debugging for free).  Fully offline, stdlib-only,
deterministic; `emit_toml()` writes the equivalent fwgen spec for the real Bundle.

  python3 difftest.py
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

OPERANDS = ["1", "2", "3"]
OPS = ["+", "-", "*"]


# --------------------------- the two implementations -------------------------- #
def impl_A_correct(expr: str) -> int:
    """Reference: full operator precedence + parentheses (Python arithmetic eval)."""
    if not set(expr) <= set("0123456789+-*() "):       # safety: arithmetic only
        raise ValueError(expr)
    return int(eval(expr, {"__builtins__": {}}, {}))


def impl_B_naive(expr: str) -> int:
    """The BUG under test: scan left-to-right, apply each operator immediately,
    ignore precedence AND parentheses (strip them).  Classic hand-rolled-parser bug."""
    s = expr.replace("(", "").replace(")", "").replace(" ", "")
    acc, i, sign = 0, 0, 1
    if s[0] == "-":                                    # leading unary minus
        sign, i = -1, 1
    acc = sign * int(s[i]); i += 1
    while i < len(s):
        op, rhs = s[i], int(s[i + 1])
        acc = acc + rhs if op == "+" else acc - rhs if op == "-" else acc * rhs
        i += 2
    return acc


# ------------------------------- the spec ------------------------------------- #
# (sheet, verb, [(label, fragment)]).  fragment = the literal text piece.
def build_matrix():
    return [
        ("UNARY", "FW_Subsets", [("neg", "-")]),       # optional leading minus
        ("O1", "FW_Combi(1)", [(o, o) for o in OPERANDS]),
        ("OP1", "FW_Combi(1)", [(o, o) for o in OPS]),
        ("O2", "FW_Combi(1)", [(o, o) for o in OPERANDS]),
        ("PAREN", "FW_Subsets", [("grp", "GRP")]),     # optional parens around (O1 OP1 O2)
        ("OP2", "FW_Combi(1)", [(o, o) for o in OPS]),
        ("O3", "FW_Combi(1)", [(o, o) for o in OPERANDS]),
    ]


def _expand(verb, opts):
    if verb == "FW_Combi(1)":
        return [(l, t) for l, t in opts]
    if verb == "FW_Subsets":                           # powerset: each option present/absent
        out = []
        for r in range(len(opts) + 1):
            for c in itertools.combinations(opts, r):
                out.append(("+".join(l for l, _ in c) or "none",
                            "".join(t for _, t in c)))
        return out
    raise SystemExit(f"unhandled verb {verb}")


def assemble(parts: dict) -> str:
    """Render the combinatorial choice into a concrete expression string."""
    lead = "-" if parts["unary"] == "neg" else ""
    inner = f"{parts['o1']} {parts['op1']} {parts['o2']}"
    if parts["paren"] == "grp":
        inner = f"({inner})"
    return f"{lead}{inner} {parts['op2']} {parts['o3']}"


def reassemble(matrix=None):
    matrix = matrix or build_matrix()
    keys = [s.lower() for s, _, _ in matrix]
    per = [_expand(v, o) for _, v, o in matrix]
    for idx, combo in enumerate(itertools.product(*per)):
        labels = {keys[i]: combo[i][0] for i in range(len(combo))}
        yield idx, labels, assemble(labels)


# ------------------------------- emit fwgen spec ------------------------------ #
def _to_toml(matrix) -> str:
    L = ['title = "Differential fuzzing #4 — two expression evaluators (precedence bug hunt)"',
         'note  = "Same combinatorially-bred expression fed to a CORRECT precedence evaluator and '
         'a NAIVE left-to-right one; FW_VAR=2 marks a DIVERGENCE (logical bug). FW_Subsets toggles '
         'leading-minus and parentheses; FW_Combi(1) breeds operands/operators. Analyzer '
         'divergences:max returns the simplest counterexample."',
         'args  = ["impl_a=precedence_correct", "impl_b=naive_left_to_right"]',
         '[[goals]]', 'key = "divergences"', 'dir = "max"',
         '[[goals]]', 'key = "expr_len"', 'dir = "min"', ""]
    for sheet, verb, opts in matrix:
        L += ['[[slots]]', f'sheet = "{sheet}"', f'key   = "{sheet.lower()}"',
              f'verb  = "{verb}"', 'values = [']
        for lab, _frag in opts:
            L.append(f'  "{lab}",')
        L += [']', ""]
    L += ['[[custom_vars]]', 'code = 2',
          'msg  = "implementations DIVERGED on this input (precedence/grouping bug)"', ""]
    return "\n".join(L) + "\n"


def emit_toml(path: Path, matrix):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_to_toml(matrix), encoding="utf-8")
    n = 1
    for _, v, o in matrix:
        n *= len(_expand(v, o))
    print(f"  fwgen spec -> {path}  (full Core product = {n:,} expressions)")


# --------- run-ready spec: slots are RAW code that concatenates into a self-checking .py --------- #
# (concatenator="" -> HEAD + O1 + OP1 + O2 + OP2 + O3 + TAIL is a runnable program that sets
#  module-level FW_VAR and prints the K=V line the Analyzer ingests.)  243 candidates.
RUN_HEAD = '''
def impl_A(e):                       # CORRECT precedence evaluator (reference)
    return int(eval(e, {"__builtins__": {}}, {}))
def impl_B(e):                       # NAIVE left-to-right evaluator (the bug under test)
    s = e.replace(" ", ""); acc = int(s[0]); i = 1
    while i < len(s):
        op = s[i]; rhs = int(s[i + 1])
        acc = acc + rhs if op == "+" else acc - rhs if op == "-" else acc * rhs
        i += 2
    return acc
E = ""
'''
RUN_TAIL = '''
_a = impl_A(E); _b = impl_B(E)
FW_VAR = 0 if _a == _b else 2        # FW_VAR=2 == DIVERGENCE found (impl_B is wrong)
print("app=diff_fuzz expr=%s correct=%d naive=%d divergences=%d FW_VAR=%d"
      % (E, _a, _b, 0 if _a == _b else 1, FW_VAR))   # 'app=' prefix => Analyzer collect_kv picks it up
'''


def emit_run_toml(path: Path):
    """A bundle_run-ready spec (one .toml in its own dir) for a full Core->Reader->Executor run."""
    def raw_slot(sheet, frags):
        L = ['[[slots]]', f'sheet = "{sheet}"', f'key   = "{sheet.lower()}"',
             'verb  = "FW_Combi(1)"', 'raw   = true', 'values = [']
        for f in frags:
            body = f if f.startswith("\n") else "\n" + f
            L.append("'''" + (body if body.endswith("\n") else body + "\n") + "''',")
        return L + [']', '']
    L = ['title = "Differential fuzzing #4 (RUN) — correct vs naive evaluator, full Bundle"',
         'note  = "Slots concatenate into a self-checking .py; FW_VAR=2 marks a precedence divergence."',
         'args  = ["mode=diff_fuzz_run"]',
         '[[goals]]', 'key = "divergences"', 'dir = "max"', '']
    L += raw_slot("HEAD", [RUN_HEAD])
    L += raw_slot("O1", [f'E += "{o}"\n' for o in OPERANDS])
    L += raw_slot("OP1", [f'E += "{o}"\n' for o in OPS])
    L += raw_slot("O2", [f'E += "{o}"\n' for o in OPERANDS])
    L += raw_slot("OP2", [f'E += "{o}"\n' for o in OPS])
    L += raw_slot("O3", [f'E += "{o}"\n' for o in OPERANDS])
    L += raw_slot("TAIL", [RUN_TAIL])
    L += ['[[custom_vars]]', 'code = 2', 'msg  = "implementations DIVERGED (precedence bug)"', '']
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"  RUN spec -> {path}  (243 self-checking candidates for bundle_run.py)")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--run" in sys.argv[1:]:
        emit_run_toml(Path(args[0]) if args else
                      Path(__file__).resolve().parent / "run" / "diff_fuzz" / "diff_fuzz_run.toml")
        return
    out = Path(args[0] if args else
               str(Path(__file__).resolve().parent / "specs" / "diff_fuzz_evaluators.toml"))
    matrix = build_matrix()
    print("=== Differential fuzzing (Model #4): correct vs naive expression evaluator ===\n")

    total = diverge = 0
    examples, minimal = [], None
    for _idx, lab, expr in reassemble(matrix):
        total += 1
        a = impl_A_correct(expr)
        b = impl_B_naive(expr)
        if a != b:
            diverge += 1
            if minimal is None or len(expr) < len(minimal[0]):
                minimal = (expr, a, b)
            if len(examples) < 6:
                examples.append((expr, a, b))

    print(f"  combinatorial inputs swept : {total}")
    print(f"  DIVERGENCES found (bugs)   : {diverge}   ({100 * diverge // total}% of inputs)")
    print(f"  minimal counterexample     : '{minimal[0]}'  ->  correct={minimal[1]}  naive={minimal[2]}")
    print("  sample findings (FW_VAR=2):")
    for e, a, b in examples:
        print(f"    {e:<14} correct={a:<4} naive={b:<4}   K=V -> divergences=1 expr_len={len(e)} expr=\"{e}\"")
    print("\n  diagnosis: impl_B diverges exactly when a higher-precedence '*' follows a +/- ,")
    print("             or when parentheses regroup the operands — both invisible to a")
    print("             left-to-right parser.  The engine found every such input by construction.\n")
    emit_toml(out, matrix)


if __name__ == "__main__":
    main()
