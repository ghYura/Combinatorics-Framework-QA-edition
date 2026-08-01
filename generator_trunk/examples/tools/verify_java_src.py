#!/usr/bin/env python3
"""Ground-truth verifier: compile+run the ACTUAL .java candidate files the Reader
emitted (not the spec expansion), and count FW_VAR pass/fail. Confirms the Results-DB
fail count == the true number of invariant violations among the emitted set.

Usage: verify_java_src.py <java_src_dir> <build_dir>
"""
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

srcdir, build = Path(sys.argv[1]), Path(sys.argv[2])
build.mkdir(parents=True, exist_ok=True)
files = sorted(p for p in srcdir.glob("*.java") if p.stat().st_size > 0)
classes = []
for p in files:
    cls = "C" + p.stem                     # <final>_0_0 -> C<final>_0_0 (valid Java identifier)
    src = re.sub(r"public class LedgerEngine", f"public class {cls}", p.read_text(encoding="utf-8"), count=1)
    (build / f"{cls}.java").write_text(src, encoding="utf-8")
    classes.append(cls)

cp = subprocess.run(["javac", "-d", str(build)] + [str(build / f"{c}.java") for c in classes],
                    capture_output=True, text=True)
print(f"javac rc={cp.returncode}" + ("" if cp.returncode == 0 else "\n" + cp.stderr[:800]))
pat = re.compile(r"FW_VAR=(-?\d+)")


def run(c):
    try:
        r = subprocess.run(["java", "-cp", str(build), c], capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return None
    m = pat.search(r.stdout)
    return int(m.group(1)) if m else None


P = F = B = 0
with ThreadPoolExecutor(max_workers=16) as ex:
    for v in ex.map(run, classes):
        if v is None:
            B += 1
        elif v == 0:
            P += 1
        else:
            F += 1
print(f"emitted_nonempty={len(files)}  pass(FW_VAR=0)={P}  fail(FW_VAR!=0)={F}  broken={B}")
