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
