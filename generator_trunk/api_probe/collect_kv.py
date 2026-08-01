#!/usr/bin/env python3
"""collect_kv — run each reassembled candidate and capture its single stdout
K=V metrics line into one corpus file (metrics.kv). This is the "candidate
stdout k=v metrics" channel the Heuristic Analyzer ingests (the open design
thread). Also cross-checks the FW_VAR pass/fail split.

Usage: collect_kv.py <srcdir-of-candidate.py> <out-metrics.kv>
"""
import subprocess
import sys
from pathlib import Path

srcdir = Path(sys.argv[1])
out = Path(sys.argv[2])
# STEP 39: provenance — an optional run id stamped on every metric line so a
# selected (Pareto) candidate is traceable back to THIS run, and a source REF
# (the candidate file name, not its contents) so it traces to the source row.
run_id = sys.argv[3] if len(sys.argv) > 3 else ""
py = sys.executable
cands = sorted(p for p in srcdir.iterdir() if p.is_file() and p.suffix == ".py")


def _prov(p):
    """Provenance tokens for candidate file `p` — a candidate_id (the file stem),
    a source_ref (the file NAME only — a ref, never the full source), and the
    run_id when supplied. Spaces are stripped so the K=V line stays parseable."""
    toks = [f"candidate_id={p.stem.replace(' ', '_')}", f"source_ref={p.name.replace(' ', '_')}"]
    if run_id:
        toks.append(f"run_id={run_id.replace(' ', '_')}")
    return " ".join(toks)

lines, npass, nfail, nbroken = [], 0, 0, 0
for p in cands:
    try:
        r = subprocess.run([py, str(p)], capture_output=True, text=True, timeout=25)
    except subprocess.TimeoutExpired:
        nbroken += 1
        continue
    kv = next((ln.strip() for ln in r.stdout.splitlines()
               if "FW_VAR=" in ln and ln.startswith("app=")), None)
    if kv is None:
        nbroken += 1
        continue
    lines.append(f"{_prov(p)} {kv}")     # provenance tokens first, then the candidate's K=V metrics
    fw = 1
    for tok in kv.split():
        if tok.startswith("FW_VAR="):
            try:
                fw = int(tok.split("=", 1)[1])
            except ValueError:
                fw = 1
            break
    npass += (fw == 0)
    nfail += (fw != 0)

out.parent.mkdir(parents=True, exist_ok=True)
out.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"collected {len(lines)} candidate K=V lines -> {out}")
print(f"cross-check: pass(FW_VAR=0)={npass} fail(FW_VAR!=0)={nfail} broken={nbroken}")
