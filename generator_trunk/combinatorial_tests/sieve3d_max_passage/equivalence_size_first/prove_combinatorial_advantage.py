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
# (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
# Ukraine
#
# See LICENSE and NOTICE.md for the binding terms.

"""Emit the bounded direct-versus-combinatorial max-passage proof."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import max_passage_search as search


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        help="optional path for the JSON proof artifact",
    )
    parser.add_argument(
        "--record-dir",
        type=Path,
        help="directory under which sieve3d_rec_results is created",
    )
    args = parser.parse_args()
    if args.record_dir is not None:
        os.environ["SIEVE3D_REC_OUT_DIR"] = str(args.record_dir)

    report = search.run_portfolio_proof()
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if report["strict_improvement"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
