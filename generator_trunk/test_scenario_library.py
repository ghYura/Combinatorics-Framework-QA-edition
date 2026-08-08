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

import json
import os
from pathlib import Path

from intake.scenario_library import (
    AI_RELEASE_GATE_PROFILE,
    AUTOMATION_GOALS,
    AUTOMATION_PROFILE,
    AUTOMATION_SUITE_ID,
    discover_sut_root,
    load_scenarios,
    scenario_environment,
    scenario_run_config,
    scenarios_in_suite,
    suite_catalog,
)


HERE = Path(__file__).resolve().parent


def test_automation_suite_is_complete_and_first() -> None:
    scenarios = load_scenarios(HERE)
    suites = suite_catalog(scenarios)
    automation = scenarios_in_suite(scenarios, AUTOMATION_SUITE_ID)

    assert suites[0][0] == AUTOMATION_SUITE_ID
    assert [scenario["id"] for scenario in automation] == [
        "automation_studio_00_smoke",
        "automation_studio_01_ordered_serial",
        "automation_studio_02_deep_nested",
        "automation_studio_03_redundant_multiset",
        "automation_studio_04_brace_join",
        "automation_studio_05_cartesian_refinement",
        "automation_studio_06_feedback_path_covering",
    ]
    assert [int(scenario["candidates"]) for scenario in automation] == [
        48,
        49_152,
        90_000,
        7_680,
        1_152,
        7_680,
        5_920,
    ]
    assert all(scenario["run_profile"] == AUTOMATION_PROFILE for scenario in automation)


def test_automation_profile_is_pinned_and_does_not_inherit_workbook_knobs() -> None:
    scenario = scenarios_in_suite(load_scenarios(HERE), AUTOMATION_SUITE_ID)[2]
    config = scenario_run_config(
        scenario,
        HERE,
        {
            "transport": "grpc",
            "lang": "java",
            "candidateOrigin": "reviewed-checked-in",
            "trustedLocalAcknowledgement": "operator reviewed the checked-in automation fixture",
            "sieve": True,
            "draw": True,
            "iterations": 9,
            "analyzer": "wrong:min",
        },
    )

    assert config["db"] == "automation_studio_02_deep_nested"
    assert config["runId"].startswith("automation-02_deep_nested-ui-")
    assert config["lang"] == "py"
    assert config["transport"] == "sharded"
    assert config["iterations"] == 1
    assert config["profile"] == "trusted-local"
    assert config["candidateOrigin"] == "reviewed-checked-in"
    assert config["trustedLocalAcknowledgement"] == \
        "operator reviewed the checked-in automation fixture"
    assert config["analyzer"] == AUTOMATION_GOALS
    assert config["mode"] == "formal"
    assert config["unleash"] is True
    assert config["mainPort"] == 5433 and config["resultsPort"] == 5432
    assert config["pyExecutor"].endswith(
        "scenarios/automation_scheme_studio/parallel_py_executor.py"
    )
    assert "sieve" not in config and "draw" not in config


def test_sut_discovery_and_environment_are_portable(tmp_path: Path) -> None:
    framework = tmp_path / "Combinatorics-Framework"
    generator = framework / "generator_trunk"
    generator.mkdir(parents=True)
    sut = tmp_path / "SUT"
    (sut / "automation-scheme-studio" / "src").mkdir(parents=True)
    scenario = {"run_profile": AUTOMATION_PROFILE}

    assert discover_sut_root(framework) == sut
    env = scenario_environment(scenario, framework, {"PATH": "/bin"})
    assert env["BUNDLE_SUT_ROOT"] == str(sut)
    assert env["BUNDLE_FRAMEWORK_ROOT"] == str(framework)
    assert env["PYTHONPATH"] == str(framework)
    assert 1 <= int(env["AUTOMATION_BUNDLE_EXECUTOR_WORKERS"]) <= 8

    explicit = scenario_environment(
        scenario,
        framework,
        {
            "BUNDLE_SUT_ROOT": "/explicit/sut",
            "PYTHONPATH": "/explicit/python",
        },
    )
    assert explicit["BUNDLE_SUT_ROOT"] == "/explicit/sut"
    assert explicit["PYTHONPATH"] == (
        f"{framework}{os.pathsep}/explicit/python"
    )


def test_dynamic_catalog_materializers_and_sources_fail_closed(tmp_path: Path) -> None:
    root = tmp_path / "generator"
    root.mkdir()
    (root / "source.md").write_text("reviewed source", encoding="utf-8")
    (tmp_path / "outside.md").write_text("outside", encoding="utf-8")
    manifest = root / "catalog.json"
    manifest.write_text(
        json.dumps(
            [
                {
                    "id": "valid",
                    "spec_materializer": "release_gate_breakpoint",
                    "run_profile": AI_RELEASE_GATE_PROFILE,
                    "source": "source.md",
                },
                {
                    "id": "unknown",
                    "spec_materializer": "unreviewed_builder",
                    "source": "source.md",
                },
                {
                    "id": "escape",
                    "spec_materializer": "release_gate_breakpoint",
                    "run_profile": AI_RELEASE_GATE_PROFILE,
                    "source": "../outside.md",
                },
                {
                    "id": "unsafe-profile",
                    "spec_materializer": "release_gate_breakpoint",
                    "source": "source.md",
                },
                {
                    "id": "invalid-ladder",
                    "spec_materializer": "release_gate_breakpoint",
                    "run_profile": AI_RELEASE_GATE_PROFILE,
                    "source": "source.md",
                    "difficulty_units": [2, 8],
                },
                {
                    "id": "coerced-ladder",
                    "spec_materializer": "release_gate_breakpoint",
                    "run_profile": AI_RELEASE_GATE_PROFILE,
                    "source": "source.md",
                    "difficulty_units": [2, 4.5],
                },
            ]
        ),
        encoding="utf-8",
    )
    assert [item["id"] for item in load_scenarios(root, manifest)] == ["valid"]
