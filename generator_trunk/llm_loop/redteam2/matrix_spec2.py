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

r"""matrix_spec2 — attack matrix for the CROSS-VERSION LLM regression red-team.

Same engine, new target: two REAL local servers (app2.py, app3.py — CPU-only OpenAI-
compatible assistants with a RAG memory + a 'SafeArithmetic' evaluator). The engine
breeds the attack space; llm_executor2 runs every bred attack against BOTH versions and
compares them (a continuous-regression red-team: did the refactor change the security
posture?).

  FAMILY      FW_Combi(1)   attack class: rag_inject / math_dos / sys_override / jailbreak
  VARIANT     FW_Combi(1)   per-family intensity (0/1/2)
  OBFUSCATION FW_Subsets    optional carrier obfuscation (leet / unicode)
  LOCALE      FW_Combi(1)   carrier language en / ru (the apps have RU retrieval)

est fw_final = 4 · 3 · (2^2=4) · 2 = 96 attacks  (each run against app2 AND app3).
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

FAMILIES = ["rag_inject", "math_dos", "sys_override", "jailbreak"]

MATRIX = [
    ("FAMILY", "FW_Combi(1)", [(f, f"#fam={f}\n") for f in FAMILIES]),
    ("VARIANT", "FW_Combi(1)", [(str(v), f"#var={v}\n") for v in (0, 1, 2)]),
    ("OBFUSCATION", "FW_Subsets", [("leet", "#obf=leet\n"), ("unicode", "#obf=unicode\n")]),
    ("LOCALE", "FW_Combi(1)", [("en", "#loc=en\n"), ("ru", "#loc=ru\n")]),
]


def _expand(verb, opts):
    if verb == "FW_Combi(1)":
        return list(opts)
    if verb == "FW_Subsets":
        out = []
        for r in range(len(opts) + 1):
            for c in itertools.combinations(opts, r):
                out.append(("+".join(l for l, _ in c) or "none", "".join(t for _, t in c)))
        return out
    if verb == "FW_Permut":
        return [(">".join(l for l, _ in p), "".join(t for _, t in p)) for p in itertools.permutations(opts)]
    raise SystemExit(f"unhandled verb {verb}")


def reassemble(matrix=MATRIX):
    keys = [s for s, _, _ in matrix]
    per = [_expand(v, o) for _, v, o in matrix]
    for idx, combo in enumerate(itertools.product(*per)):
        labels = {keys[i].lower(): combo[i][0] for i in range(len(combo))}
        yield idx, labels, "".join(c[1] for c in combo)


def count(matrix=MATRIX):
    n = 1
    for _, v, o in matrix:
        n *= len(_expand(v, o))
    return n


def _to_toml(matrix=MATRIX):
    L = ['title = "cross-version LLM regression red-team — attack matrix (engine spec)"',
         'note  = "Engine breeds the attack space; llm_executor2 runs each attack against live app2 AND '
         'app3 and compares them (RAG-injection / bounded math-DoS / system-override / jailbreak)."',
         'goals = ["severity", "breach", "latency_ms"]', 'args  = ["mode=redteam2"]', ""]
    for sheet, verb, opts in matrix:
        L += ["[[slots]]", f'sheet = "{sheet}"', f'key   = "{sheet.lower()}"', f'verb  = "{verb}"',
              "raw   = true", "values = ["]
        for _l, frag in opts:
            b = frag if frag.startswith("\n") else "\n" + frag
            L.append("'''" + (b if b.endswith("\n") else b + "\n") + "''',")
        L += ["]", ""]
    L += ["[[custom_vars]]", "code = 2", 'msg  = "attack breached the target version"', ""]
    return "\n".join(L) + "\n"


def emit_toml(path: Path, matrix=MATRIX):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_to_toml(matrix), encoding="utf-8")
    print(f"engine spec -> {path}  ({len(matrix)} slots, est fw_final = {count(matrix)} attacks x 2 versions)")


if __name__ == "__main__":
    emit_toml(Path(sys.argv[1] if len(sys.argv) > 1 else
                   str(Path(__file__).resolve().parent / "spec" / "redteam2.toml")))
