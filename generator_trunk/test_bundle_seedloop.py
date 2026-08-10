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

"""Focused tests for BundleSeed -> seed-bias planning."""
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "constraints"))

import fwgen as fg  # noqa: E402
import sieve as sv  # noqa: E402
from bundle import seedbias, stages  # noqa: E402
from bundle.errors import StageError  # noqa: E402


def _spec(values=("a", "b", "c", "d", "e", "f")):
    return fg.parse_spec({
        "slots": [
            {"sheet": "A", "values": list(values)},
            {"sheet": "B", "values": ["x", "y", "z"]},
        ]
    }, "seedloop_unit")


def _rows_for_a(*vals):
    rows = []
    for i, val in enumerate(vals, 1):
        rows.append(seedbias.WinnerRow(
            candidate_id=f"{i}_0_0",
            line_no=i,
            role="pareto",
            values={"A": (val,), "B": ("x",)},
            score=None,
            crowding_distance=None,
        ))
    return rows


def _seed(n):
    return {
        "schemaVersion": 1,
        "sourceRunId": "seed-run",
        "winners": [{"lineNo": i, "role": "pareto", "kvPairs": {"candidate_id": f"{i}_0_0"}}
                    for i in range(1, n + 1)],
        "observedRanges": {"latency_ms": {"key": "latency_ms", "n": n, "min": 1, "max": 9, "mean": 3, "stdev": 1}},
        "declaredMetrics": ["latency_ms"],
        "totalCandidatesObserved": n,
        "_source_seed_sha256": "0" * 64,
    }


def test_build_bias_plan_enforces_floor_and_is_deterministic():
    spec = _spec()
    rows = _rows_for_a("c", "c", "c", "c", "c")
    plan1 = seedbias.build_bias_plan(spec, rows, _seed(5), exploration_floor=0.25, min_winner_support=5)
    plan2 = seedbias.build_bias_plan(spec, rows, _seed(5), exploration_floor=0.25, min_winner_support=5)

    sheet = plan1.per_sheet["A"]
    assert len(sheet.kept_values) >= sheet.min_keep
    assert set(sheet.kept_values) == {"b", "c", "d"}  # winner plus declared-order neighbors
    assert sheet.excluded_values == ["a", "e", "f"]
    assert json.dumps(seedbias.plan_to_sidecar(plan1), sort_keys=True) == json.dumps(seedbias.plan_to_sidecar(plan2), sort_keys=True)


def test_no_signal_sheet_is_left_untouched():
    spec = fg.parse_spec({"slots": [{"sheet": "A", "values": ["a", "b", "c", "d", "e"]}]}, "covered")
    rows = _rows_for_a("a", "b", "c", "d", "e")
    with pytest.raises(seedbias.DegenerateBiasPlan, match="no exclusions"):
        seedbias.build_bias_plan(spec, rows, _seed(5), exploration_floor=0.25, min_winner_support=5)


def test_degenerate_floor_plan_is_refused():
    spec = _spec(("a", "b", "c", "d"))
    rows = _rows_for_a("a", "a", "a", "a", "a")
    with pytest.raises(seedbias.DegenerateBiasPlan, match="exploration floor"):
        seedbias.build_bias_plan(spec, rows, _seed(5), exploration_floor=0.5, min_winner_support=5)


def test_plan_to_sidecar_is_strict_sieve_valid_and_enforces_assert_form():
    spec = _spec()
    plan = seedbias.build_bias_plan(spec, _rows_for_a("c", "c", "c", "c", "c"),
                                    _seed(5), exploration_floor=0.25, min_winner_support=5)
    sidecar = seedbias.plan_to_sidecar(plan)
    sv.validate_sidecar(sidecar, strict=True)
    row = [[{"sheet": "A", "value": "a", "pos": 0}, {"sheet": "B", "value": "x", "pos": 1}]]
    assert sv.sieve(row, sidecar)["unique_removals"] == 1


def test_load_seed_validates_schema(tmp_path):
    p = tmp_path / "seed.json"
    p.write_text(json.dumps({"schemaVersion": 2, "winners": []}), encoding="utf-8")
    with pytest.raises(seedbias.SeedBiasError, match="schemaVersion"):
        seedbias.load_seed(p)


def test_sparse_metadata_champion_id_is_not_treated_as_bundle_candidate():
    winner = {"role": "champion-min:candidate_id", "kvPairs": {"candidate_id": "1"}, "originalLine": None}
    assert seedbias._candidate_id_from_winner(winner) is None
    winner["originalLine"] = "candidate_id=7_0_0 latency_ms=1 FW_VAR=0"
    assert seedbias._candidate_id_from_winner(winner) == "7_0_0"


def test_non_objective_champions_do_not_drive_bias_signal():
    spec = _spec(("a", "b", "c", "d", "e", "f"))
    rows = [
        seedbias.WinnerRow("1_0_0", 1, "pareto", {"A": ("c",), "B": ("x",)}),
        seedbias.WinnerRow("2_0_0", 2, "pareto", {"A": ("c",), "B": ("x",)}),
        seedbias.WinnerRow("3_0_0", 3, "champion-min:A", {"A": ("a",), "B": ("x",)}),
        seedbias.WinnerRow("4_0_0", 4, "champion-max:latency_ms", {"A": ("c",), "B": ("x",)}),
    ]
    seed = _seed(4)
    seed["declaredMetrics"] = ["latency_ms"]
    plan = seedbias.build_bias_plan(spec, rows, seed, exploration_floor=0.25, min_winner_support=2)
    assert "a" in plan.per_sheet["A"].excluded_values


_AZ = stages.SRC / "Analyzer_trunk"
_ANALYZER_READY = (
    (_AZ / "target/heuristic-analyzer-flatlaf-1.0.0.jar").exists()
    and (_AZ / "target/analyzekv/AnalyzeKv.class").exists()
    and (_AZ / "analyzer_cp.txt").exists()
)


@pytest.mark.skipif(not _ANALYZER_READY, reason="Analyzer jar/AnalyzeKv build not present")
def test_stage_analyzer_seed_out_writes_bundle_seed(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "1_0_0.py").write_text("print('app=x latency_ms=1 score=10 FW_VAR=0')\n", encoding="utf-8")
    (src / "2_0_0.py").write_text("print('app=x latency_ms=5 score=1 FW_VAR=0')\n", encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()
    seed_path = work / "bundle_seed.json"
    stages.stage_analyzer(src, work, "latency_ms:min,score:max", mode="exploratory",
                          corpus_count=2, run_id="seed-stage-test", seed_out=seed_path)
    doc = json.loads(seed_path.read_text(encoding="utf-8"))
    assert doc["schemaVersion"] == 1
    assert doc["winners"]
    assert "latency_ms" in doc["observedRanges"]
    assert doc["sourceRunId"] == "seed-stage-test"

@pytest.mark.skipif(not _ANALYZER_READY, reason="Analyzer jar/AnalyzeKv build not present")
def test_formal_provenance_failure_leaves_no_seed(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "1_0_0.py").write_text("print('app=x latency_ms=1 score=10 FW_VAR=0')\n", encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()
    seed_path = work / "bundle_seed.json"
    with pytest.raises(StageError):
        stages.stage_analyzer(src, work, "latency_ms:min,score:max", mode="formal",
                              corpus_count=1, run_id="", seed_out=seed_path)
    assert not seed_path.exists()
