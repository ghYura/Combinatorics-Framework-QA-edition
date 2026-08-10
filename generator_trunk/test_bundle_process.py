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

"""Targeted tests for bundle.process.run() and the bundle error boundary
(run: `python3 test_bundle_process.py`; pytest also works)."""
import sys

from bundle.errors import BundleError, PreflightError, StageError, report_and_exit
from bundle.process import run


def test_run_success():
    r = run([sys.executable, "-c", "print('hi')"])
    assert r.ok and r.returncode == 0 and not r.timed_out
    assert r.stdout.strip() == "hi"
    assert r.duration >= 0
    assert r.argv[0] == sys.executable


def test_run_non_zero():
    r = run([sys.executable, "-c", "import sys; sys.exit(3)"])
    assert not r.ok
    assert r.returncode == 3
    assert not r.timed_out                 # non-zero exit must be distinct from timeout


def test_run_timeout():
    r = run([sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.2)
    assert not r.ok
    assert r.timed_out
    assert r.returncode != 0                # timeout is reported, not mistaken for a clean exit


def test_error_boundary_single_path():
    assert issubclass(PreflightError, BundleError)
    assert issubclass(StageError, BundleError)
    caught = []
    try:
        report_and_exit(StageError("boom"), debug=False)
    except SystemExit as exc:
        caught.append(exc.code)
    assert caught == [1]                    # concise path: non-zero exit, no traceback propagated
    try:
        report_and_exit(StageError("boom"), debug=True)
    except StageError as exc:
        caught.append(str(exc))
    assert caught == [1, "boom"]             # debug path: original exception propagates with traceback


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\nALL {len(fns)} TESTS PASSED")
