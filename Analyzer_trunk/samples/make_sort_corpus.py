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

"""Generate the executable-line corpus that `SortMockupRun` analyses.

`SortMockupRun` is the Analyzer's most realistic end-to-end driver: every line
of its input is a self-contained shell command that prints agnostic timing and
memory metrics on stdout, exercising the whole pipeline (execute -> stdout
capture -> K=V parsing -> numeric extraction -> MetricStreamAnalyzer ->
BestLinesReporter).

Historically that corpus was an unversioned local file, so `run-tests.sh`
reported `SKIP (input file not present)` on every clean checkout and the driver
never actually ran. Committing a produced corpus would have been the wrong fix:
it is runtime output. This generator is the source instead — `run-tests.sh`
writes the corpus into a temporary directory, runs the driver against it and
deletes it again, so a clean checkout executes the check without gaining an
untracked artefact.

The corpus is deterministic: identical bytes on every invocation, fixed input
seeds, fixed workload sizes. The *metrics* the lines emit are genuinely measured
at run time (that is the point of the driver), but nothing the driver asserts
depends on their values — only on the metric keys being discovered and the
reports being non-empty.

Usage:
    python3 make_sort_corpus.py OUTPUT_PATH
"""
from __future__ import annotations

import sys
from pathlib import Path

#: (label, element count, sort strategy). Sizes differ per line so the measured
#: streams carry real variance — a corpus of identical workloads would leave
#: MetricStreamAnalyzer with a degenerate (zero-spread) distribution.
WORKLOADS = (
    ("timsort_builtin", 40000, "sorted(d)"),
    ("timsort_reverse", 30000, "sorted(d, reverse=True)"),
    ("timsort_keyed", 25000, "sorted(d, key=lambda x: -x)"),
    ("heapsort_stdlib", 20000, "_heapsort(list(d))"),
    ("selection_partial", 15000, "heapq.nsmallest(len(d) // 4, d)"),
    ("insertion_small", 1200, "_insertion(list(d))"),
    ("merge_recursive", 8000, "_merge(list(d))"),
    ("presorted_best_case", 35000, "sorted(sorted(d))"),
)

#: Pure-Python sorts, inlined into each command so every line stays a
#: self-contained shell command with no import of a project module.
_HELPERS = (
    "import heapq\n"
    "def _heapsort(a):\n"
    " heapq.heapify(a)\n"
    " return [heapq.heappop(a) for _ in range(len(a))]\n"
    "def _insertion(a):\n"
    " for i in range(1,len(a)):\n"
    "  k=a[i];j=i-1\n"
    "  while j>=0 and a[j]>k: a[j+1]=a[j];j-=1\n"
    "  a[j+1]=k\n"
    " return a\n"
    "def _merge(a):\n"
    " if len(a)<2: return a\n"
    " m=len(a)//2;l=_merge(a[:m]);r=_merge(a[m:]);o=[];i=j=0\n"
    " while i<len(l) and j<len(r):\n"
    "  if l[i]<=r[j]: o.append(l[i]);i+=1\n"
    "  else: o.append(r[j]);j+=1\n"
    " return o+l[i:]+r[j:]\n"
)


def _command(label: str, size: int, expression: str) -> str:
    """One corpus line: measure the workload, print agnostic K=V metrics.

    The printed keys are what the driver asserts on. `AnalyzerCore` lowercases
    keys and takes the token immediately before the separator, so `Peak Mem:`
    becomes `mem` and `GC:` keeps its deliberately truncated tuple value.
    """
    body = (
        f"{_HELPERS}"
        "import gc,random,time,tracemalloc\n"
        "random.seed(20260802)\n"
        f"d=[random.random() for _ in range({size})]\n"
        "gc.collect()\n"
        "tracemalloc.start()\n"
        "t0=time.perf_counter();c0=time.process_time()\n"
        f"out={expression}\n"
        "w=time.perf_counter()-t0;c=time.process_time()-c0\n"
        "_cur,pk=tracemalloc.get_traced_memory();tracemalloc.stop()\n"
        "ok=1 if out is not None and len(out)>0 else 0\n"
        f"print('algo: {label}  N: {size}  Wall: %.6f s  CPU: %.6f s  "
        "Blocks: %d  Peak Mem: %.4f MB  GC: %s  Correct: %d'"
        f"%(w,c,{size}//64,pk/1048576.0,gc.get_count(),ok))\n"
    )
    # The Analyzer executes each line with `bash -lc`, and a corpus line must be
    # exactly one line. ANSI-C quoting (`$'...'`) is what turns the escaped
    # newlines back into real ones for `python3 -c`; plain double quotes would
    # hand Python a literal backslash-n and fail to parse.
    escaped = (body.replace("\\", "\\\\")
                   .replace("'", "\\'")
                   .replace("\n", "\\n"))
    return "python3 -c $'" + escaped + "'"


def render() -> str:
    """The corpus text. No blank lines and no comment lines: the driver asserts
    that *every* line produced at least one K=V pair, and a comment would
    execute as a no-op and emit nothing."""
    return "".join(_command(*w) + "\n" for w in WORKLOADS)


def main(argv: "list[str]") -> int:
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 2
    out = Path(argv[1])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(), encoding="utf-8")
    print(f"sort corpus -> {out} ({len(WORKLOADS)} executable lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
