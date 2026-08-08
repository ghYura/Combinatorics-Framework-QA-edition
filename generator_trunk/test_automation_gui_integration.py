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

from __future__ import annotations

from face1_new.runtime_model import load_verified_examples
from intake import serve_face1


def test_both_face1_backends_expose_the_automation_suite() -> None:
    old_ids = {scenario["id"] for scenario in serve_face1._load_examples()}
    new_ids = {scenario["id"] for scenario in load_verified_examples()}
    expected = {
        "automation_studio_00_smoke",
        "automation_studio_01_ordered_serial",
        "automation_studio_02_deep_nested",
        "automation_studio_03_redundant_multiset",
        "automation_studio_04_brace_join",
        "automation_studio_05_cartesian_refinement",
        "automation_studio_06_feedback_path_covering",
        "automation_studio_advanced_00_smoke",
        "automation_studio_advanced_01_operator_smoke",
        "automation_studio_advanced_10_third_order",
        "automation_studio_advanced_20_grouped",
    }
    assert expected <= old_ids
    assert expected <= new_ids


def test_legacy_face1_uses_the_checked_in_automation_profile(monkeypatch) -> None:
    captured = {}

    def fake_spawn(toml_text, config, environment=None, launch_cwd=None):
        captured.update(
            toml=toml_text, config=config, environment=environment, launch_cwd=launch_cwd
        )
        return {"token": "test", "run_id": config["runId"], "db": config["db"]}

    monkeypatch.setattr(serve_face1, "_spawn_run_direct", fake_spawn)
    result = serve_face1._example_run("automation_studio_00_smoke")
    config = captured["config"]

    assert result["db"] == "automation_studio_00_smoke"
    assert config["transport"] == "sharded"
    assert config["lang"] == "py"
    assert config["mode"] == "formal"
    assert config["unleash"] is True
    assert config["pyExecutor"].endswith(
        "scenarios/automation_scheme_studio/parallel_py_executor.py"
    )
    assert "initialize_candidate" in captured["toml"]
    assert 1 <= int(
        captured["environment"]["AUTOMATION_BUNDLE_EXECUTOR_WORKERS"]
    ) <= 8
    assert captured["launch_cwd"] == serve_face1.GEN_DIR.parent


def test_legacy_face1_acknowledges_advanced_runtime_cardinality(monkeypatch) -> None:
    captured = {}

    def fake_spawn(toml_text, config, environment=None, launch_cwd=None):
        captured["config"] = config
        return {"token": "test", "run_id": config["runId"], "db": config["db"]}

    monkeypatch.setattr(serve_face1, "_spawn_run_direct", fake_spawn)
    serve_face1._example_run("automation_studio_advanced_10_third_order")
    assert captured["config"]["allowExtreme"] is True
    assert captured["config"]["overrideBudget"] == (
        "explicit advanced recursive control-topology search"
    )
