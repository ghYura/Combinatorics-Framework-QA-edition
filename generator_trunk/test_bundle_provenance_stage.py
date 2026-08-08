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

"""STEP 39 end-to-end — stage_analyzer wiring: it stamps run_id onto the corpus,
runs AnalyzeKv with --provenance-out, writes the versioned provenance JSON
artifact, and (formal mode) FAILS the stage when a selected candidate is
unprovenanced. No Core/Reader/Executor — just candidate .py files → collect_kv →
AnalyzeKv.

Run: `python3 -m pytest test_bundle_provenance_stage.py -q`.
"""
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from bundle import stages
from bundle.errors import StageError

_AZ = stages.SRC / "Analyzer_trunk"
_ANALYZER_READY = (
    (_AZ / "target/heuristic-analyzer-flatlaf-1.0.0.jar").exists()
    and (_AZ / "target/analyzekv/AnalyzeKv.class").exists()
    and (_AZ / "analyzer_cp.txt").exists()
)
pytestmark = pytest.mark.skipif(not _ANALYZER_READY, reason="Analyzer jar/AnalyzeKv build not present")

_GOALS = "latency_ms:min,severity:min"
_CAND = "print('app=svc mode={m} latency_ms={lat} severity={sev} FW_VAR={fw}')\n"
_ROWS = [("fast", 1.0, 0, 0), ("safe", 3.0, 0, 0), ("mixed", 2.0, 1, 1), ("slow", 5.0, 2, 0)]


def _make_src(d: Path) -> int:
    src = d / "src"
    src.mkdir()
    for i, (m, lat, sev, fw) in enumerate(_ROWS):
        (src / f"cand_{i:02d}.py").write_text(_CAND.format(m=m, lat=lat, sev=sev, fw=fw), encoding="utf-8")
    return len(_ROWS)


def test_exploratory_writes_versioned_provenance_with_run_id(tmp_path):
    n = _make_src(tmp_path)
    work = tmp_path / "work"; work.mkdir()
    stages.stage_analyzer(tmp_path / "src", work, _GOALS, mode="exploratory",
                          corpus_count=n, run_id="run-xyz-001")

    # corpus carries the run_id provenance on every line
    corpus = (work / "metrics.kv").read_text(encoding="utf-8").splitlines()
    assert corpus and all("run_id=run-xyz-001" in ln and "candidate_id=" in ln for ln in corpus if ln.strip())

    # versioned provenance JSON artifact written
    prov = json.loads((work / "provenance.json").read_text(encoding="utf-8"))
    assert prov["schema"] == "analyzer.provenance/v1"
    assert prov["mode"] == "exploratory"
    assert prov["candidates"], "expected at least one selected candidate"
    for c in prov["candidates"]:
        assert c["candidate_id"] and c["run_id"] == "run-xyz-001"     # traceable to source + run
        assert "reason_non_dominated" in c and "objectives" in c
    # exploratory does not enforce provenance
    assert prov["provenance_issues"] == []


def test_formal_without_run_id_fails_the_stage(tmp_path):
    n = _make_src(tmp_path)
    work = tmp_path / "work"; work.mkdir()
    # formal mode, NO run_id → every selected candidate is missing run attribution
    with pytest.raises(StageError, match="provenance"):
        stages.stage_analyzer(tmp_path / "src", work, _GOALS, mode="formal",
                              corpus_count=n, run_id="")
    # the provenance report was still written, recording the failure
    prov = json.loads((work / "provenance.json").read_text(encoding="utf-8"))
    assert prov["provenance_ok"] is False
    assert any(i["level"] == "error" and "run_id" in i["message"] for i in prov["provenance_issues"])


def test_formal_with_run_id_passes(tmp_path):
    n = _make_src(tmp_path)
    work = tmp_path / "work"; work.mkdir()
    stages.stage_analyzer(tmp_path / "src", work, _GOALS, mode="formal",
                          corpus_count=n, run_id="run-formal-7")    # must NOT raise
    prov = json.loads((work / "provenance.json").read_text(encoding="utf-8"))
    assert prov["mode"] == "formal" and prov["provenance_ok"] is True
    assert all(c["run_id"] == "run-formal-7" for c in prov["candidates"])


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
