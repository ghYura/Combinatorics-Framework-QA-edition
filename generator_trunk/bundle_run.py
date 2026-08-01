#!/usr/bin/env python3
r"""bundle_run — ONE command to run the whole Bundle end to end.

The Bundle is powerful but operationally fragile at the Reader<->Executor seam (CWD-bound
fw.properties, concatenator='', file extension, preserveWhitespace, delayed y/y/no stdin,
fwVar.shift, handshake dirs, fresh DB naming, scratch location). This driver bakes EVERY
one of those gotcha-fixes in, adds a preflight and per-stage verification, and turns the
multi-step dance into:

    python3 bundle_run.py <spec-dir> [--db NAME] [--lang py|java] [--analyzer "k:max,..."]

It runs:  fwgen gen -> Core (fill main DB) -> Reader (reassemble + handshake + Results DB)
          -> language-specific Executor (Python or Java) -> [optional] AnalyzeKv.
Every stage prints OK/FAIL with the numbers, so a stranger can run it and trust the result.
The validated Handoff v2 language selects py_executor.py or the Java MainWatch fat jar.

Implementation lives in the `bundle` package (bundle/cli.py, bundle/stages.py, ...);
this file is a thin compatibility entry point.
"""
from __future__ import annotations

from bundle.cli import main

if __name__ == "__main__":
    main()
