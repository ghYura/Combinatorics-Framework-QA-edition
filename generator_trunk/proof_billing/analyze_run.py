#!/usr/bin/env python3
"""
analyze_run.py <run_dir_or_scratch> - research harness.

Executes every candidate the Reader reassembled, parses the K=V line each one
prints, and reports:

  * how many candidates violate an invariant, and which
  * for each invariant, the MINIMAL witness (fewest operations)
  * which axis values are enriched among the failures (the signal that tells a
    researcher which degree of freedom is responsible)

It never modifies a candidate; it only runs and reads them.
"""
import collections
import glob
import multiprocessing
import os
import re
import subprocess
import sys


def find_run(arg):
    if os.path.isdir(os.path.join(arg, "src")):
        return arg
    runs = sorted(glob.glob(os.path.join(arg, "runs", "*")))
    if runs:
        return runs[-1]
    runs = sorted(glob.glob(os.path.join(arg, "*", "runs", "*")))
    if runs:
        return runs[-1]
    raise SystemExit("no run dir under %s" % arg)


KV = re.compile(r"(\w+)=([^\s]*)")


def run_candidate(path):
    try:
        p = subprocess.run([sys.executable, path], capture_output=True,
                           text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return {"_error": "timeout"}
    out = p.stdout.strip().splitlines()
    rec = {}
    for line in out:
        if "=" in line:
            rec.update(dict(KV.findall(line)))
    if p.returncode != 0:
        rec["_error"] = (p.stderr.strip().splitlines() or ["?"])[-1][:160]
    rec["_file"] = os.path.basename(path)
    return rec


def main():
    run = find_run(sys.argv[1])
    files = sorted(glob.glob(os.path.join(run, "src", "*.py")))
    print("run      : %s" % run)
    print("candidates: %d" % len(files))

    nproc = max(1, (os.cpu_count() or 4) - 1)
    with multiprocessing.Pool(nproc) as pool:
        recs = pool.map(run_candidate, files, chunksize=8)

    errors = [r for r in recs if "_error" in r]
    ok = [r for r in recs if "_error" not in r]
    bad = [r for r in ok if r.get("inv", "none") not in ("none", "")]

    print("executed ok: %d   crashed/timeout: %d" % (len(ok), len(errors)))
    print("violating  : %d  (%.1f%%)" % (len(bad), 100.0 * len(bad) / max(1, len(ok))))
    if errors:
        c = collections.Counter(r["_error"] for r in errors)
        print("\nUNEXPECTED EXCEPTIONS (crash = a defect class of its own)")
        for msg, n in c.most_common(10):
            print("  %4d  %s" % (n, msg))
            ex = next(r for r in errors if r["_error"] == msg)
            print("        witness: %s" % ex["_file"])

    # per-invariant breakdown with a minimal witness
    per = collections.defaultdict(list)
    for r in bad:
        for inv in r["inv"].split("+"):
            per[inv].append(r)

    print("\nINVARIANT VIOLATIONS")
    for inv in sorted(per):
        rows = per[inv]
        def size(r):
            return len(r.get("trace", "").split(">")) if r.get("trace") else 99
        w = min(rows, key=size)
        print("  %-4s %5d candidates   minimal witness (%d ops): %s"
              % (inv, len(rows), size(w), w.get("trace", "?")))
        det = {k: v for k, v in w.items()
               if k not in ("inv", "trace", "_file", "viol", "FW_VAR")}
        print("       %s   [%s]" % (det, w["_file"]))

    # which axis values are enriched among failures
    axes = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0]))
    for r in ok:
        isbad = r.get("inv", "none") not in ("none", "")
        for k, v in r.items():
            if k in ("inv", "viol", "FW_VAR", "_file", "trace", "cash"):
                continue
            axes[k][v][1] += 1
            if isbad:
                axes[k][v][0] += 1
    print("\nAXIS ENRICHMENT  (failures / total per value)")
    for k in sorted(axes):
        parts = []
        for v, (b, t) in sorted(axes[k].items()):
            parts.append("%s=%d/%d(%.0f%%)" % (v, b, t, 100.0 * b / max(1, t)))
        print("  %-12s %s" % (k, "  ".join(parts)))


if __name__ == "__main__":
    main()
