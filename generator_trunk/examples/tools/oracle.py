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

"""Local oracle: replicate the Core's per-verb expansion + the Reader's
concatenator='' reassembly for a dispersed fwgen spec, then compile+run EVERY
reassembled program to (a) prove they are all valid and (b) get the exact
pass/fail (FW_VAR) counts to verify the Bundle's Results DB against.

This is NOT part of the Bundle — it's an independent reference implementation of
what Core→Reader produce, so we can trust the end-to-end numbers.

Usage:  oracle.py <spec.toml> <java|py> <out_programs_dir>
"""
import itertools
import re
import subprocess
import sys
import tomllib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def powerset(vals):
    for r in range(len(vals) + 1):
        for c in itertools.combinations(vals, r):
            yield c


def expand_slot(verb, values):
    """Return the list of option-strings this slot contributes (each already
    concatenated), replicating the Core engine for the verbs we use."""
    v = verb.strip()
    if v == "FW_Combi(1)":
        return list(values)                                   # choose-1 → each value
    m = re.fullmatch(r"FW_Combi\((\d+)\)", v)
    if m:
        k = int(m.group(1))
        return ["".join(c) for c in itertools.combinations(values, k)]
    if v == "FW_Permut":
        return ["".join(p) for p in itertools.permutations(values)]
    m = re.fullmatch(r"FW_Permut\((\d+)\)", v)
    if m:
        k = int(m.group(1))
        return ["".join(p) for p in itertools.permutations(values, k)]
    if v == "FW_Subsets":
        return ["".join(s) for s in powerset(values)]         # 2^n incl. empty
    raise SystemExit(f"oracle: unhandled verb {verb!r}")


def reassemble(spec):
    slots = spec["slots"]
    per_slot = [expand_slot(s.get("verb", "FW_Combi(1)"), [str(x) for x in s["values"]])
                for s in slots]
    counts = [len(e) for e in per_slot]
    progs = ["".join(combo) for combo in itertools.product(*per_slot)]
    return progs, counts


def run_python(progs, outdir):
    npass = nfail = nbroken = 0
    for i, p in enumerate(progs):
        (outdir / f"prog_{i:04d}.py").write_text(p, encoding="utf-8")
        ns = {}
        try:
            exec(compile(p, f"prog_{i}", "exec"), ns)
            fw = int(ns.get("FW_VAR", -999))
            if fw == 0:
                npass += 1
            else:
                nfail += 1
        except Exception:
            nbroken += 1
    return npass, nfail, nbroken


def run_java(progs, outdir):
    # rename the top-level class to a unique C<i>, write all, batch-compile once
    files = []
    for i, p in enumerate(progs):
        src = re.sub(r"public class LedgerEngine", f"public class C{i}", p, count=1)
        f = outdir / f"C{i}.java"
        f.write_text(src, encoding="utf-8")
        files.append(f)
    cp = subprocess.run(["javac", "-d", str(outdir)] + [str(f) for f in files],
                        capture_output=True, text=True)
    if cp.returncode != 0:
        # find which failed (compile-broken)
        print("javac reported errors (first 1500 chars):\n", cp.stderr[:1500])
    pat = re.compile(r"FW_VAR=(-?\d+)")

    def run_one(i):
        r = subprocess.run(["java", "-cp", str(outdir), f"C{i}"],
                           capture_output=True, text=True, timeout=30)
        m = pat.search(r.stdout)
        if m is None:
            return "broken"
        return "pass" if int(m.group(1)) == 0 else "fail"

    npass = nfail = nbroken = 0
    with ThreadPoolExecutor(max_workers=16) as ex:
        for verdict in ex.map(run_one, range(len(progs))):
            if verdict == "pass":
                npass += 1
            elif verdict == "fail":
                nfail += 1
            else:
                nbroken += 1
    return npass, nfail, nbroken


def main():
    spec_path, lang, out = sys.argv[1], sys.argv[2], Path(sys.argv[3])
    out.mkdir(parents=True, exist_ok=True)
    spec = tomllib.loads(Path(spec_path).read_text(encoding="utf-8"))
    progs, counts = reassemble(spec)
    print(f"spec={Path(spec_path).name} lang={lang}")
    print(f"per-slot option counts = {counts}  product = {len(progs)}")
    if lang == "py":
        npass, nfail, nbroken = run_python(progs, out)
    else:
        npass, nfail, nbroken = run_java(progs, out)
    print(f"TOTAL={len(progs)}  pass(FW_VAR=0)={npass}  fail(FW_VAR!=0)={nfail}  broken(no compile/run)={nbroken}")
    print(f"programs written to {out}")


if __name__ == "__main__":
    main()
