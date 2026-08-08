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

"""Cross-language contract test for the control-plane seam (2026-07-03).

Before this file, each side of the Python → Java seam was tested only against
ITSELF: `test_bundle_controlplane.py` checked the Python emitter's dict shape,
and `BundleControlPlaneVerify.java` parsed JSON strings it had authored in
Java. Nothing ever fed a PYTHON-EMITTED plan into the JAVA ingester — the
classic recipe for silent contract drift (and one real divergence existed:
the plan's default env id was "" while live results_v2 rows said
"local:<run>").

This test closes that hole: `bundle.controlplane.write_plan_json` emits real
plans, the compiled `BundleControlPlane` CLI (Analyzer_trunk) ingests each via
`Plan.fromJson` and prints the expanded dispatch plan (dry-run), and the
assertions here pin the POLICY SEMANTICS both sides must agree on:

  * local    — all K repeats of a candidate pinned to ONE env (round-robin);
  * disperse — candidate ci's repeat r lands on envs[(ci + r) % E];
  * nested   — K repeats on EACH env (C·E·K units);
  * metricSensitivity=noisy derives serializePerHost=true, but an explicit
    serializePerHost always wins;
  * repeatScope (a Plan-1 fidelity field) is tolerated and ignored by Java;
  * the default env identity is the live executors' "local:<run_id>".

Skips (like the other Java-gated tests) when the Analyzer build is absent.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from bundle.config import BundleConfig            # noqa: E402
from bundle.controlplane import write_plan_json   # noqa: E402
from bundle import stages                          # noqa: E402

_AZ = stages.SRC / "Analyzer_trunk"
_CP_CLASS = _AZ / "target/classes/com/yurii/analyzer/core/optimization/BundleControlPlane.class"
_CP_FILE = _AZ / "analyzer_cp.txt"
_SEAM_READY = _CP_CLASS.exists() and _CP_FILE.exists()

pytestmark = pytest.mark.skipif(not _SEAM_READY,
                                reason="Analyzer build (BundleControlPlane.class + analyzer_cp.txt) not present")

_CANDIDATES = [(1, "101_0_0", "candA"), (2, "102_0_0", "candB")]


def _java_expand(plan_path: Path) -> dict:
    """Run the Java control plane's dry-run CLI on a Python-emitted plan."""
    cp = f"{_AZ}/target/classes:{_CP_FILE.read_text().strip()}"
    r = subprocess.run(
        ["java", "-cp", cp, "com.yurii.analyzer.core.optimization.BundleControlPlane", str(plan_path)],
        capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, f"Java ingest failed:\n{r.stdout}\n{r.stderr}"
    return json.loads(r.stdout)


def _units_by_candidate(doc: dict) -> dict:
    out: dict[str, list] = {}
    for u in doc["units"]:
        out.setdefault(u["candidateId"], []).append((u["repeatIdx"], u["envId"]))
    for v in out.values():
        v.sort()
    return out


def test_local_plan_round_trips_with_live_env_identity(tmp_path):
    cfg = BundleConfig(repeat_each_candidate=3, repeat_policy="local", repeat_scope="metrics")
    plan = tmp_path / "plan_local.json"
    write_plan_json(plan, cfg, candidates=_CANDIDATES, run_id="seam1")
    doc = _java_expand(plan)
    assert doc["policy"] == "local"
    assert doc["plannedUnits"] == doc["executions"] == 2 * 3        # C * K
    by_cand = _units_by_candidate(doc)
    # every candidate: repeats 0..K-1, ALL pinned to the single live-convention env
    for cand in ("101_0_0", "102_0_0"):
        assert by_cand[cand] == [(r, "local:seam1") for r in range(3)]


def test_nested_plan_expands_c_e_k(tmp_path):
    cfg = BundleConfig(repeat_each_candidate=2, repeat_policy="nested",
                       repeat_scope="metrics", repeat_environments=2)
    plan = tmp_path / "plan_nested.json"
    write_plan_json(plan, cfg, candidates=_CANDIDATES, run_id="seam2")
    doc = _java_expand(plan)
    assert doc["plannedUnits"] == 2 * 2 * 2                          # C * E * K
    by_cand = _units_by_candidate(doc)
    for cand in ("101_0_0", "102_0_0"):
        assert by_cand[cand] == [(0, "env-0"), (0, "env-1"), (1, "env-0"), (1, "env-1")]


def test_disperse_rotation_and_noisy_serialization(tmp_path):
    cfg = BundleConfig(repeat_each_candidate=4, repeat_policy="disperse")
    plan = tmp_path / "plan_disperse.json"
    write_plan_json(plan, cfg, candidates=_CANDIDATES, env_names=["h1", "h2"],
                    metric_sensitivity="noisy", max_in_flight=16, run_id="seam3")
    doc = _java_expand(plan)
    assert doc["plannedUnits"] == 2 * 4
    assert doc["serializePerHost"] is True          # derived from metricSensitivity=noisy
    by_cand = _units_by_candidate(doc)
    # candidate ci's repeat r -> envs[(ci + r) % E]  (the balanced rotation)
    assert by_cand["101_0_0"] == [(0, "h1"), (1, "h2"), (2, "h1"), (3, "h2")]
    assert by_cand["102_0_0"] == [(0, "h2"), (1, "h1"), (2, "h2"), (3, "h1")]


def test_explicit_serialize_per_host_wins_over_sensitivity(tmp_path):
    cfg = BundleConfig(repeat_each_candidate=2, repeat_policy="local")
    plan = tmp_path / "plan_override.json"
    write_plan_json(plan, cfg, candidates=_CANDIDATES, metric_sensitivity="noisy",
                    serialize_per_host=False, run_id="seam4")
    doc = _java_expand(plan)
    assert doc["serializePerHost"] is False


def test_budget_and_scope_fields_are_ingested_without_error(tmp_path):
    # budgetMillis defaults from the layered wall-time ceiling; repeatScope is a
    # Plan-1 fidelity field Java must tolerate. Both ride every emitted plan.
    cfg = BundleConfig(repeat_each_candidate=2, repeat_policy="local", repeat_scope="all")
    plan = tmp_path / "plan_budget.json"
    write_plan_json(plan, cfg, candidates=_CANDIDATES, run_id="seam5")
    emitted = json.loads(plan.read_text())
    assert emitted["budgetMillis"] == int(BundleConfig().budget_wall_time_seconds * 1000)
    assert emitted["repeatScope"] == "all"
    doc = _java_expand(plan)                        # ingest must not reject either field
    assert doc["plannedUnits"] == 4
