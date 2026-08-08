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

from pathlib import Path

import fwgen
from AI_combi_testing_platform.sub_suites.release_gate_breakpoint import task_factory
from face1_new import runtime_model
from face1_new.runtime_model import (
    RunSession,
    default_run_config,
    load_verified_examples,
    plan_verified_example,
)
from intake import serve_face1
from intake.scenario_library import (
    AI_RELEASE_GATE_GOALS,
    AI_RELEASE_GATE_PROFILE,
    AI_GOALS,
    AI_SUBSUITE_SUITE_ID,
    AI_SUITE_ID,
    load_scenarios,
    release_gate_candidate_count,
    scenario_environment,
    scenario_run_config,
    scenario_source_label,
    scenario_spec_document,
    scenarios_in_suite,
)


EXPECTED_IDS = {
    "ai_combi_00_smoke",
    "ai_combi_01_operator_smoke",
    "ai_combi_70_product_modes",
}
RELEASE_GATE_ID = "ai_combi_release_gate_breakpoint"


def test_shared_catalog_exposes_ai_platform_to_both_face1_backends() -> None:
    old_ids = {scenario["id"] for scenario in serve_face1._load_examples()}
    new_ids = {scenario["id"] for scenario in load_verified_examples()}
    assert EXPECTED_IDS | {RELEASE_GATE_ID} <= old_ids
    assert EXPECTED_IDS | {RELEASE_GATE_ID} <= new_ids
    platform = scenarios_in_suite(
        load_scenarios(serve_face1.GEN_DIR),
        AI_SUITE_ID,
    )
    assert {item["id"] for item in platform} == EXPECTED_IDS
    sub_suite = scenarios_in_suite(
        load_scenarios(serve_face1.GEN_DIR),
        AI_SUBSUITE_SUITE_ID,
    )
    assert {item["id"] for item in sub_suite} == {RELEASE_GATE_ID}
    assert sub_suite[0]["run_profile"] == AI_RELEASE_GATE_PROFILE
    assert scenario_source_label(sub_suite[0]).startswith("fresh release_gate_breakpoint")


def test_ai_profile_is_pinned_local_cost_free_and_clears_external_opt_in(
    tmp_path: Path,
) -> None:
    scenario = next(
        item
        for item in load_verified_examples()
        if item["id"] == "ai_combi_00_smoke"
    )
    config = scenario_run_config(
        scenario,
        runtime_model.ROOT,
        {
            "lang": "java",
            "transport": "grpc",
            "analyzer": "wrong:min",
            "profile": "networked-api-probe",
            "candidateOrigin": "reviewed-checked-in",
            "trustedLocalAcknowledgement": "operator reviewed the checked-in AI fixture",
            "unleash": True,
        },
    )
    assert config["lang"] == "py"
    assert config["transport"] == "sharded"
    assert config["profile"] == "trusted-local"
    assert config["candidateOrigin"] == "reviewed-checked-in"
    assert config["trustedLocalAcknowledgement"] == \
        "operator reviewed the checked-in AI fixture"
    assert config["analyzer"] == AI_GOALS
    assert config["mode"] == "formal"
    assert "unleash" not in config
    assert 1 <= config["executorPool"] <= 4

    framework = tmp_path / "framework"
    framework.mkdir()
    env = scenario_environment(
        scenario,
        framework,
        {
            "AI_COMBI_ALLOW_EXTERNAL": "1",
            "AI_COMBI_CONFIG": "/secret/config.json",
            "AI_COMBI_EXPORT_PROMPT": "1",
            "ANTHROPIC_API_KEY": "fixture-value",
            "PYTHONPATH": "/existing",
        },
    )
    assert "AI_COMBI_ALLOW_EXTERNAL" not in env
    assert "AI_COMBI_CONFIG" not in env
    assert env["AI_COMBI_ENVIRONMENT_ID"] == "face1-local-control"
    assert "AI_COMBI_EXPORT_PROMPT" not in env
    assert "ANTHROPIC_API_KEY" not in env
    assert env["PYTHONDONTWRITEBYTECODE"] == "1"
    assert env["PYTHONPATH"].startswith(str(framework))


def _release_gate_example() -> dict:
    return next(
        item for item in load_verified_examples() if item["id"] == RELEASE_GATE_ID
    )


def test_release_gate_profile_materializes_fresh_bounded_local_apparatus(
    monkeypatch,
    tmp_path: Path,
) -> None:
    scenario = _release_gate_example()
    seeds = iter((b"a" * 32, b"b" * 32, b"c" * 32))
    monkeypatch.setattr(task_factory, "new_release_holdout_seed", lambda: next(seeds))
    first, filename = scenario_spec_document(scenario, runtime_model.ROOT)
    second, _ = scenario_spec_document(scenario, runtime_model.ROOT)
    assert filename == "release_gate_breakpoint.toml"
    assert first != second
    assert (b"a" * 32).hex() not in first
    path = tmp_path / filename
    path.write_text(first, encoding="utf-8")
    spec = fwgen.load_spec(path, strict=True)
    assert len(spec.seq_extra) == 4
    assert "2/4/8/16/32 leaves" in spec.note
    assert release_gate_candidate_count(scenario) == 2_560
    assert plan_verified_example(scenario).final.mode.value == "UNKNOWN"

    config = scenario_run_config(
        scenario,
        runtime_model.ROOT,
        {
            "profile": "trusted-local",
            "transport": "grpc",
            "budgetRequests": 999_999,
            "costPerCandidate": 99,
            "unleash": True,
        },
    )
    assert config["profile"] == "generated-default"
    assert config["transport"] == "sharded"
    assert config["analyzer"] == AI_RELEASE_GATE_GOALS
    assert config["budgetMandatoryRows"] == 160
    assert config["budgetFinalCandidates"] == 2_560
    assert config["budgetRequests"] == 2_560
    assert config["budgetMonetaryCost"] == 0
    assert config["costPerCandidate"] == 0
    assert config["allowExtreme"] is True
    assert "unleash" not in config

    env = scenario_environment(
        scenario,
        runtime_model.ROOT.parent,
        {
            "AI_COMBI_ALLOW_EXTERNAL": "1",
            "AI_COMBI_EXPORT_PROMPT": "1",
            "OPENAI_API_KEY": "fixture-value",
        },
    )
    assert env["AI_COMBI_ENVIRONMENT_ID"] == "face1-release-gate-control"
    assert env["PYTHONDONTWRITEBYTECODE"] == "1"
    assert "AI_COMBI_ALLOW_EXTERNAL" not in env
    assert "AI_COMBI_EXPORT_PROMPT" not in env
    assert "OPENAI_API_KEY" not in env


def test_face1_old_launches_checked_in_ai_profile(monkeypatch) -> None:
    captured = {}

    def fake_spawn(toml_text, config, environment=None, launch_cwd=None):
        captured.update(
            toml=toml_text,
            config=config,
            environment=environment,
            launch_cwd=launch_cwd,
        )
        return {"token": "test", "run_id": config["runId"], "db": config["db"]}

    monkeypatch.setattr(serve_face1, "_spawn_run_direct", fake_spawn)
    result = serve_face1._example_run("ai_combi_00_smoke")
    assert result["db"] == "ai_combi_00_smoke"
    assert captured["config"]["transport"] == "sharded"
    assert captured["config"]["analyzer"] == AI_GOALS
    assert captured["config"]["candidateOrigin"] == "reviewed-checked-in"
    assert captured["config"]["trustedLocalAcknowledgement"]
    assert "unleash" not in captured["config"]
    assert "AI_COMBI_ALLOW_EXTERNAL" not in captured["environment"]
    assert captured["launch_cwd"] == serve_face1.GEN_DIR.parent
    assert "run_candidate(PLAN)" in captured["toml"]


def test_face1_new_launches_checked_in_ai_profile(monkeypatch, tmp_path: Path) -> None:
    example = next(
        item
        for item in load_verified_examples()
        if item["id"] == "ai_combi_01_operator_smoke"
    )
    root = tmp_path / "new-ai-example"
    root.mkdir()
    captured = {}

    def fake_spawn(cls, command, run_dir, work_dir, environment=None, launch_cwd=None):
        captured.update(
            command=tuple(command),
            environment=environment,
            launch_cwd=launch_cwd,
        )
        return captured

    monkeypatch.setattr(runtime_model.tempfile, "mkdtemp", lambda prefix: str(root))
    monkeypatch.setattr(RunSession, "_spawn", classmethod(fake_spawn))
    config = default_run_config("workbook")
    config.update({
        "candidateOrigin": "reviewed-checked-in",
        "trustedLocalAcknowledgement": "reviewed checked-in AI-combi scenario",
    })
    RunSession.start_example(example, config)
    command = captured["command"]
    assert command[command.index("--db") + 1] == "ai_combi_01_operator_smoke"
    assert command[command.index("--candidate-sink") + 1] == "sharded"
    assert command[command.index("--analyzer") + 1] == AI_GOALS
    assert command[command.index("--candidate-origin") + 1] == "reviewed-checked-in"
    assert "--acknowledge-trusted-local" in command
    assert "--allow-extreme" in command
    assert "--unleash-initial-productivity-power" not in command
    assert captured["launch_cwd"] == runtime_model.ROOT.parent
    assert "AI_COMBI_ALLOW_EXTERNAL" not in captured["environment"]


def test_face1_old_launches_fresh_release_gate_profile(monkeypatch) -> None:
    captured = {}

    def fake_spawn(toml_text, config, environment=None, launch_cwd=None):
        captured.update(
            toml=toml_text,
            config=config,
            environment=environment,
            launch_cwd=launch_cwd,
        )
        return {"token": "test", "run_id": config["runId"], "db": config["db"]}

    monkeypatch.setattr(task_factory, "new_release_holdout_seed", lambda: b"o" * 32)
    # Any credential-shaped name must be stripped, including one no denylist
    # could have known about in advance.
    monkeypatch.setenv("SOME_UNLISTED_PROVIDER_API_KEY", "fixture-value")
    monkeypatch.setenv("AI_COMBI_EXPORT_PROMPT", "1")
    monkeypatch.setattr(serve_face1, "_spawn_run_direct", fake_spawn)
    result = serve_face1._example_run(RELEASE_GATE_ID)
    assert result["db"] == "ai_combi_release_gate_gui"
    assert captured["config"]["profile"] == "generated-default"
    assert captured["config"]["transport"] == "sharded"
    assert captured["config"]["budgetFinalCandidates"] == 2_560
    assert captured["config"]["costPerCandidate"] == 0
    assert captured["launch_cwd"] == serve_face1.GEN_DIR.parent
    assert "SOME_UNLISTED_PROVIDER_API_KEY" not in captured["environment"]
    assert "AI_COMBI_EXPORT_PROMPT" not in captured["environment"]
    assert "2/4/8/16/32 leaves" in captured["toml"]
    assert (b"o" * 32).hex() not in captured["toml"]


def test_face1_new_launches_fresh_release_gate_profile(
    monkeypatch,
    tmp_path: Path,
) -> None:
    example = _release_gate_example()
    root = tmp_path / "new-release-gate-example"
    root.mkdir()
    captured = {}

    def fake_spawn(cls, command, run_dir, work_dir, environment=None, launch_cwd=None):
        captured.update(
            command=tuple(command),
            environment=environment,
            launch_cwd=launch_cwd,
            work_dir=work_dir,
        )
        return captured

    monkeypatch.setattr(task_factory, "new_release_holdout_seed", lambda: b"n" * 32)
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-value")
    monkeypatch.setattr(runtime_model.tempfile, "mkdtemp", lambda prefix: str(root))
    monkeypatch.setattr(RunSession, "_spawn", classmethod(fake_spawn))
    RunSession.start_example(example, default_run_config("workbook"))
    command = captured["command"]
    assert command[command.index("--db") + 1] == "ai_combi_release_gate_gui"
    assert command[command.index("--candidate-sink") + 1] == "sharded"
    assert command[command.index("--execution-policy-profile") + 1] == "generated-default"
    assert command[command.index("--analyzer") + 1] == AI_RELEASE_GATE_GOALS
    assert command[command.index("--budget-mandatory-rows") + 1] == "160"
    assert command[command.index("--budget-final-candidates") + 1] == "2560"
    assert command[command.index("--budget-requests") + 1] == "2560"
    assert command[command.index("--budget-monetary-cost") + 1] == "0"
    assert command[command.index("--cost-per-candidate") + 1] == "0"
    assert "--allow-extreme" in command
    assert "--unleash-initial-productivity-power" not in command
    assert captured["launch_cwd"] == runtime_model.ROOT.parent
    assert "OPENAI_API_KEY" not in captured["environment"]
    specs = list((root / "spec").glob("*.toml"))
    assert [path.name for path in specs] == ["release_gate_breakpoint.toml"]
    text = specs[0].read_text(encoding="utf-8")
    assert "2/4/8/16/32 leaves" in text
    assert (b"n" * 32).hex() not in text
