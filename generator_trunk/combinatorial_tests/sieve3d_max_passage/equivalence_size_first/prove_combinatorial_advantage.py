#!/usr/bin/env python3
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
