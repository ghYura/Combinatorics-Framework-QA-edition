#!/usr/bin/env python3
"""STEP 39 — collect_kv stamps provenance (candidate_id + source_ref [+ run_id])
on every metric line, so a selected candidate is traceable to its source row and
run. The source_ref is the file NAME only (a ref), never the file contents.

Run: `python3 -m pytest test_collect_kv_provenance.py -q`.
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
COLLECT = HERE / "api_probe" / "collect_kv.py"

_CANDIDATE = (
    "print('app=pricing mode=strict region=us latency_ms=12.5 "
    "overcharge_cents=0 FW_VAR={fw}')\n"
)


def _make_candidates(d: Path, n: int = 3):
    for i in range(n):
        (d / f"cand_{i:02d}.py").write_text(_CANDIDATE.format(fw=i % 2), encoding="utf-8")


def test_collect_kv_stamps_candidate_id_and_source_ref(tmp_path):
    src = tmp_path / "src"; src.mkdir()
    _make_candidates(src, 3)
    out = tmp_path / "metrics.kv"
    r = subprocess.run([sys.executable, str(COLLECT), str(src), str(out)],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    lines = [ln for ln in out.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 3
    for ln in lines:
        toks = dict(t.split("=", 1) for t in ln.split() if "=" in t)
        assert toks["candidate_id"].startswith("cand_")          # traces to the source file stem
        assert toks["source_ref"].endswith(".py")                # a REF (file name), not the source body
        assert "run_id" not in toks                              # not requested → absent
        assert "FW_VAR" in toks and "latency_ms" in toks         # the original metrics survive
    # the source_ref is a bare file name, never the candidate's contents
    assert "print(" not in out.read_text(encoding="utf-8")


def test_collect_kv_stamps_run_id_when_given(tmp_path):
    src = tmp_path / "src"; src.mkdir()
    _make_candidates(src, 2)
    out = tmp_path / "metrics.kv"
    r = subprocess.run([sys.executable, str(COLLECT), str(src), str(out), "run-xyz-001"],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    lines = [ln for ln in out.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert lines and all("run_id=run-xyz-001" in ln for ln in lines)


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
