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

"""Run AnalyzeKv formally on a persisted staged-search K=V corpus."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
GENERATOR_ROOT = HERE.parents[2]
FRAMEWORK_ROOT = GENERATOR_ROOT.parent
if str(GENERATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(GENERATOR_ROOT))

from bundle.config import BundleConfig  # noqa: E402
from bundle import stages  # noqa: E402


DEFAULT_GOALS = (
    "full_pass:max,passed_volume_pct:max,solution_actions:min,"
    "solution_keyframes:min,changed_parameter_count:min,"
    "worst_clearance:max,search_attempts:min"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--goals", default=DEFAULT_GOALS)
    parser.add_argument("--expected-candidate")
    args = parser.parse_args()
    corpus = args.corpus.resolve()
    if not corpus.is_file():
        raise SystemExit(f"missing corpus: {corpus}")
    count = sum(1 for line in corpus.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.lstrip().startswith("#"))
    if count <= 0:
        raise SystemExit("formal Analyzer corpus is empty")

    analyzer_root = FRAMEWORK_ROOT / "Analyzer_trunk"
    cpfile = analyzer_root / "analyzer_cp.txt"
    clsdir = analyzer_root / "target" / "analyzekv"
    config = BundleConfig()
    if not cpfile.is_file():
        raise SystemExit(f"missing Analyzer classpath file: {cpfile}")
    if not stages._ensure_analyzer_classes_fresh(
            analyzer_root, clsdir, cpfile, config, "formal", corpus):
        raise SystemExit("Analyzer classes could not be refreshed")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    provenance = args.out_dir / "provenance.json"
    stdout_path = args.out_dir / "analyzer.stdout.log"
    stderr_path = args.out_dir / "analyzer.stderr.log"
    classpath = ":".join((
        str(clsdir),
        str(analyzer_root / "target" / "classes"),
        cpfile.read_text(encoding="utf-8").strip(),
    ))
    command = [
        config.java_cmd,
        "-cp", classpath,
        "AnalyzeKv", str(corpus), "10", args.goals,
        "--mode", "formal",
        "--corpus-count", str(count),
        "--provenance-out", str(provenance),
    ]
    completed = subprocess.run(
        command, text=True, capture_output=True, check=False)
    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    provenance_payload = (
        json.loads(provenance.read_text(encoding="utf-8"))
        if provenance.is_file() else {})
    provenance_text = json.dumps(provenance_payload, sort_keys=True)
    expected_present = (
        args.expected_candidate is None or
        args.expected_candidate in completed.stdout or
        args.expected_candidate in provenance_text)
    report = {
        "schema_version": "sieve3d-formal-analyzer-run/2",
        "command": command,
        "corpus": str(corpus),
        "corpus_count": count,
        "goals": args.goals,
        "exit_code": completed.returncode,
        "stdout_path": str(stdout_path.resolve()),
        "stderr_path": str(stderr_path.resolve()),
        "provenance_path": str(provenance.resolve()),
        "provenance_ok": provenance_payload.get("provenance_ok"),
        "provenance_issue_count": len(
            provenance_payload.get("provenance_issues") or ()),
        "expected_candidate_id": args.expected_candidate,
        "expected_candidate_present": expected_present,
        "verdict": completed.returncode == 0 and expected_present and bool(
            provenance_payload.get("provenance_ok", False)),
    }
    report_path = args.out_dir / "formal_analyzer_report.json"
    report_path.write_text(
        json.dumps(report, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0 if report["verdict"] else 6


if __name__ == "__main__":
    raise SystemExit(main())
