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

"""Tests for the Plan-2 control-plane plan emitter (bundle/controlplane.py) — the
Python → Java seam. The emitted dict mirrors `BundleControlPlane.Plan.fromJson`
(Analyzer_trunk), verified cross-language in the Plan-2 verifier/CLI."""
import json

import pytest

from bundle.config import BundleConfig, ConfigError
from bundle.controlplane import controlplane_plan, plan_json, write_plan_json


def test_local_plan_minimal():
    cfg = BundleConfig(repeat_each_candidate=3, repeat_policy="local", repeat_scope="metrics")
    plan = controlplane_plan(cfg)
    assert plan["policy"] == "local"
    assert plan["repeatK"] == 3
    assert plan["repeatScope"] == "metrics"
    # 2026-07-03 reconciliation: the default env id mirrors the LIVE executors'
    # --envId/-envId value (what results_v2 rows actually carry), not "".
    assert plan["envs"] == ["local:default"]
    # budgetMillis now defaults from the layered config's wall-time ceiling, so
    # the Python budget gate and the Java dispatch deadline enforce ONE number.
    assert plan["budgetMillis"] == int(BundleConfig().budget_wall_time_seconds * 1000)
    # Remaining Plan-2 deployment fields are omitted unless explicitly supplied.
    for k in ("maxInFlight", "serializePerHost", "metricSensitivity", "candidates"):
        assert k not in plan


def test_local_env_id_matches_live_executor_convention():
    cfg = BundleConfig(repeat_each_candidate=2, repeat_policy="local")
    assert controlplane_plan(cfg, run_id="r42")["envs"] == ["local:r42"]
    # unlimited wall-time budget ⇒ no budgetMillis emitted
    cfg_nolimit = BundleConfig(repeat_each_candidate=2, repeat_policy="local",
                               budget_wall_time_seconds=None)
    assert "budgetMillis" not in controlplane_plan(cfg_nolimit)


def test_nested_plan_envs_from_repeat_environments():
    cfg = BundleConfig(repeat_each_candidate=2, repeat_policy="nested",
                       repeat_scope="metrics", repeat_environments=3)
    plan = controlplane_plan(cfg)
    assert plan["policy"] == "nested"
    assert plan["repeatK"] == 2
    assert plan["envs"] == ["env-0", "env-1", "env-2"]


def test_control_plane_overrides_included_only_when_given():
    cfg = BundleConfig(repeat_each_candidate=4, repeat_policy="disperse")
    plan = controlplane_plan(cfg, env_names=["h1", "h2"], max_in_flight=16,
                             serialize_per_host=True, metric_sensitivity="noisy",
                             budget_millis=5000)
    assert plan["envs"] == ["h1", "h2"]
    assert plan["maxInFlight"] == 16
    assert plan["serializePerHost"] is True
    assert plan["metricSensitivity"] == "noisy"
    assert plan["budgetMillis"] == 5000


def test_candidates_normalized_from_tuples_and_mappings():
    cfg = BundleConfig(repeat_each_candidate=1, repeat_policy="local")
    plan = controlplane_plan(cfg, candidates=[
        (1, "7", "cand7"),
        {"lineNo": 2, "candidateId": "8", "raw": "cand8"},
        {"line_no": 3, "candidate_id": "9", "raw": "cand9"},  # snake_case aliases
    ])
    assert plan["candidates"] == [
        {"lineNo": 1, "candidateId": "7", "raw": "cand7"},
        {"lineNo": 2, "candidateId": "8", "raw": "cand8"},
        {"lineNo": 3, "candidateId": "9", "raw": "cand9"},
    ]


def test_plan_json_round_trips():
    cfg = BundleConfig(repeat_each_candidate=2, repeat_policy="nested", repeat_environments=2)
    s = plan_json(cfg, max_in_flight=8)
    assert json.loads(s) == controlplane_plan(cfg, max_in_flight=8)


def test_invalid_repeat_fails_closed():
    # nested K>1 without repeat_environments → ConfigError, propagated from validate_repeat().
    cfg = BundleConfig(repeat_each_candidate=2, repeat_policy="nested", repeat_environments=0)
    with pytest.raises(ConfigError):
        controlplane_plan(cfg)


def test_write_plan_json(tmp_path):
    cfg = BundleConfig(repeat_each_candidate=2, repeat_policy="local")
    p = tmp_path / "plan.json"
    write_plan_json(p, cfg, run_id="w1")
    loaded = json.loads(p.read_text())
    assert loaded["policy"] == "local" and loaded["repeatK"] == 2 and loaded["envs"] == ["local:w1"]
