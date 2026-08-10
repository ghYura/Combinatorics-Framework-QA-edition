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

"""Cost-free readiness check; it never installs packages or contacts a provider."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile


HERE = Path(__file__).resolve().parent
FRAMEWORK_ROOT = HERE.parents[1]
BUNDLE = FRAMEWORK_ROOT / "generator_trunk" / "bundle_run.py"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--with-tests",
        action="store_true",
        help="also run the focused platform unit tests",
    )
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        raise SystemExit("Python 3.11 or newer is required")
    if not BUNDLE.is_file():
        raise SystemExit(f"Bundle launcher is missing: {BUNDLE}")
    example = json.loads((HERE / "config.example.json").read_text(encoding="utf-8"))
    if any(item.get("enabled") for item in example.get("external_adapters", [])):
        raise SystemExit("config.example.json must keep every external adapter disabled")

    with tempfile.TemporaryDirectory(prefix="ai-combi-readiness-") as output:
        command = [
            sys.executable,
            str(BUNDLE),
            "plan",
            str(HERE / "scenarios" / "00_smoke"),
            "--out",
            output,
        ]
        completed = subprocess.run(command, cwd=FRAMEWORK_ROOT, check=False)
        if completed.returncode:
            return completed.returncode
    if args.with_tests:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                str(HERE / "tests"),
            ],
            cwd=FRAMEWORK_ROOT,
            check=False,
        )
        if completed.returncode:
            return completed.returncode
    print("READY: local deterministic planning is green; external execution remains disabled.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
