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

"""STEP 38 — the run manifest records the Analyzer's formal-vs-exploratory
analysis contract (mode/goals/weights/normalization), and stage_analyzer passes
the mode (+ corpus count for formal) through to AnalyzeKv.

No Executor / Core / live SUT is run here (per the step's minimal check).
Run: `python3 -m pytest test_bundle_analysis_mode.py -q`.
"""
import sys
import tempfile
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from bundle import stages
from bundle.jsonio import read_json
from bundle.models import analysis_block, run_manifest_from_dict, RunStatus, to_dict, RunManifest
from bundle.runs import create_run, file_sha256


# --------------------------------------------------------------------------- #
def test_analysis_block_parses_goals_directions_weights():
    blk = analysis_block("formal", "security_failures:max,latency_ms:min,coverage")
    assert blk["mode"] == "formal"
    assert blk["normalization"] == "none"
    assert blk["goals"] == [
        {"key": "security_failures", "dir": "max", "weight": 1.0},
        {"key": "latency_ms", "dir": "min", "weight": 1.0},
        {"key": "coverage", "dir": "min", "weight": 1.0},     # bare key defaults to min
    ]
    assert blk["weights"] == {"security_failures": 1.0, "latency_ms": 1.0, "coverage": 1.0}


def test_analysis_block_empty_goals():
    blk = analysis_block("exploratory", "")
    assert blk == {"mode": "exploratory", "goals": [], "weights": {}, "normalization": "none"}


def test_manifest_records_and_roundtrips_analysis():
    blk = analysis_block("formal", "security_failures:max")
    m = RunManifest(schema="bundle.run/v1", run_id="r1", status=RunStatus.PENDING,
                    db_name="secure_pipeline", spec_path="s.toml", analysis=blk)
    rt = run_manifest_from_dict(to_dict(m))
    assert rt.analysis == blk
    assert rt.analysis["mode"] == "formal"


def test_create_run_writes_analysis_block_to_disk():
    with tempfile.TemporaryDirectory() as d:
        spec = Path(d) / "spec.toml"
        spec.write_text("title = 'x'\n", encoding="utf-8")
        blk = analysis_block("formal", "security_failures:max,latency_ms:min")
        layout = create_run(
            runs_root=Path(d) / "runs", db_name="secure_pipeline", spec_path=spec,
            spec_sha256=file_sha256(spec), mode="verdict", goals="security_failures:max,latency_ms:min",
            scratch_root=Path(d) / "scratch", run_id="sp-analysis", settings={"main_port": 5433},
            analysis=blk,
        )
        on_disk = read_json(layout.manifest_path)
        assert on_disk["analysis"]["mode"] == "formal"
        assert {g["key"] for g in on_disk["analysis"]["goals"]} == {"security_failures", "latency_ms"}
        # security_failures direction is the EXPLICIT max — never re-inferred to min
        sf = next(g for g in on_disk["analysis"]["goals"] if g["key"] == "security_failures")
        assert sf["dir"] == "max"
        assert read_json(layout.manifest_path)["analysis"]["normalization"] == "none"

        manifest = run_manifest_from_dict(on_disk)
        assert manifest.analysis["mode"] == "formal"


def test_create_run_defaults_to_empty_analysis_when_absent():
    with tempfile.TemporaryDirectory() as d:
        spec = Path(d) / "spec.toml"
        spec.write_text("title='x'\n", encoding="utf-8")
        layout = create_run(
            runs_root=Path(d) / "runs", db_name="db", spec_path=spec,
            spec_sha256=file_sha256(spec), mode="verdict", goals="",
            scratch_root=Path(d) / "scratch", run_id="no-analysis", settings={},
        )
        assert read_json(layout.manifest_path)["analysis"] == {}


# --------------------------------------------------------------------------- #
def _fake_run_recorder(commands):
    def fake(cmd, *a, **kw):
        commands.append(cmd if isinstance(cmd, str) else " ".join(map(str, cmd)))
        return types.SimpleNamespace(stdout="", stderr="", returncode=0)
    return fake


def _install_fake_analyzer(monkeypatch, root: Path) -> None:
    """Give command-wiring tests a self-contained Analyzer installation.

    Freshness/rebuild behavior has its own tests; these two tests exercise only
    the arguments passed to AnalyzeKv, so no Maven build or Java bytecode is
    needed here.
    """
    fake_src = root / "bundle-src"
    analyzer = fake_src / "Analyzer_trunk"
    (analyzer / "target/analyzekv").mkdir(parents=True)
    (analyzer / "target/classes").mkdir()
    (analyzer / "target/heuristic-analyzer-flatlaf-1.0.0.jar").write_text(
        "test fixture\n", encoding="utf-8"
    )
    (analyzer / "AnalyzeKv.java").write_text(
        "final class AnalyzeKv {}\n", encoding="utf-8"
    )
    (analyzer / "analyzer_cp.txt").write_text(
        str(analyzer / "target/heuristic-analyzer-flatlaf-1.0.0.jar"),
        encoding="utf-8",
    )
    monkeypatch.setattr(stages, "SRC", fake_src)
    monkeypatch.setattr(stages, "_ensure_analyzer_classes_fresh", lambda *a, **kw: True)


def test_stage_analyzer_passes_formal_mode_and_corpus_count(monkeypatch, tmp_path):
    """stage_analyzer threads --mode (+ --corpus-count for formal) to AnalyzeKv."""
    _install_fake_analyzer(monkeypatch, tmp_path)
    cmds: list = []
    monkeypatch.setattr(stages, "run", _fake_run_recorder(cmds))
    src, scratch = tmp_path / "src", tmp_path / "scratch"
    src.mkdir(); scratch.mkdir()
    stages.stage_analyzer(src, scratch, "security_failures:max", mode="formal", corpus_count=42)
    analyze = [c for c in cmds if "AnalyzeKv" in c]
    assert analyze, f"AnalyzeKv was not invoked; cmds={cmds}"
    assert "--mode formal" in analyze[0] and "--corpus-count 42" in analyze[0]


def test_stage_analyzer_exploratory_omits_corpus_count(monkeypatch, tmp_path):
    _install_fake_analyzer(monkeypatch, tmp_path)
    cmds: list = []
    monkeypatch.setattr(stages, "run", _fake_run_recorder(cmds))
    src, scratch = tmp_path / "src", tmp_path / "scratch"
    src.mkdir(); scratch.mkdir()
    stages.stage_analyzer(src, scratch, "dq_score:max", mode="exploratory")
    analyze = [c for c in cmds if "AnalyzeKv" in c]
    assert analyze
    assert "--mode exploratory" in analyze[0] and "--corpus-count" not in analyze[0]


# --------------------------------------------------------------------------- #
# Formal contract is a PREFLIGHT gate: `--analysis-mode formal` without explicit
# Analyzer goals must be rejected BEFORE any run directory is created (otherwise
# the run would persist a formal manifest with empty goals and silently skip the
# Analyzer — exactly the implicit-objective degradation formal mode forbids).
# --------------------------------------------------------------------------- #
import subprocess


_MIN_SPEC = ('title = "t"\n[[slots]]\nsheet = "A"\nvalues = ["a1", "a2"]\n')


def test_run_rejects_formal_mode_without_goals_before_run_dir():
    with tempfile.TemporaryDirectory() as d:
        spec_dir = Path(d) / "spec"
        spec_dir.mkdir()
        (spec_dir / "s.toml").write_text(_MIN_SPEC, encoding="utf-8")
        runs = Path(d) / "runs"
        r = subprocess.run(
            [sys.executable, str(HERE / "bundle_run.py"), str(spec_dir),
             "--db", "fw_formal_preflight", "--analysis-mode", "formal",
             "--runs-root", str(runs)],
            cwd=str(HERE), capture_output=True, text=True, timeout=120)
        out = r.stdout + r.stderr
        assert r.returncode != 0, out
        assert "formal" in out and "requires explicit Analyzer goals" in out
        # rejected BEFORE the run directory exists — nothing was created
        assert not runs.exists() or not any(runs.iterdir()), f"a run dir was created: {list(runs.iterdir())}"


def test_run_formal_with_goals_passes_the_formal_preflight():
    """Control: formal WITH goals clears the formal-contract gate (it then fails
    later for an unrelated reason — no live DB/Core here — but NOT on the formal
    goals check)."""
    with tempfile.TemporaryDirectory() as d:
        spec_dir = Path(d) / "spec"
        spec_dir.mkdir()
        (spec_dir / "s.toml").write_text(_MIN_SPEC, encoding="utf-8")
        runs = Path(d) / "runs"
        r = subprocess.run(
            [sys.executable, str(HERE / "bundle_run.py"), str(spec_dir),
             "--db", "fw_formal_ok", "--analysis-mode", "formal",
             "--analyzer", "security_failures:max", "--runs-root", str(runs),
             "--main-port", "1"],   # unreachable port → preflight fails AFTER the formal gate
            cwd=str(HERE), capture_output=True, text=True, timeout=120)
        out = r.stdout + r.stderr
        assert "requires explicit Analyzer goals" not in out, out


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
