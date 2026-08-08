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

from io import BytesIO
import json
from pathlib import Path

from openpyxl import load_workbook

import fwgen
from bundle.policy import PolicyError
from face1_new.grid_model import GridProject
from intake.scenario_library import AI_PROFILE
from face1_new.runtime_model import (
    build_worker_command,
    collect_progress,
    collect_results,
    default_run_config,
    example_run_config,
    plan_project,
    results_csv,
    runtime_capability_selection,
    spec_toml,
    supported_control_fields,
    validate_runtime,
)
from face1_new.workbook_runner import exact_workbook_stage_table, parse_args


def test_blank_project_has_exact_honest_plan():
    project = GridProject.blank(visible_rows=1)
    plan = plan_project(project)

    assert plan.mandatory["mode"] == "EXACT"
    assert plan.mandatory["value"] == 2
    assert plan.final["value"] == 2
    assert plan.run_class == "S"


def test_optional_factor_and_brace_uncertainty_are_visible():
    optional = GridProject.blank(visible_rows=1)
    optional.rows[0].directives.insert(0, "FW_Optional")
    optional.directive_columns += 1
    plan = plan_project(optional)
    assert plan.optional_multiplier["mode"] == "EXACT"
    assert plan.optional_multiplier["value"] == 3

    brace = GridProject(name="brace", rows=[], directive_columns=4)
    left = brace.add_row("LEFT", ["a", "b"])
    right = brace.add_row("RIGHT", ["x", "y"])
    joined = brace.add_row("JOINED", ["FW_EMPTY_STRING"])
    left.directives = ["FW_Exclude", "FW_Reuse", "FW_Combi(1)", ""]
    right.directives = ["FW_Exclude", "FW_Reuse", "FW_Combi(1)", ""]
    joined.directives = ["FW_(,,LEFT,,RIGHT,,,,M:N)", "", "", ""]
    plan = plan_project(brace)
    assert plan.final["mode"] == "UNKNOWN"
    assert plan.run_class == "X"


def test_runtime_metadata_round_trips_without_changing_workbook_contract(tmp_path):
    project = GridProject.blank(visible_rows=1)
    project.name = "runtime demo"
    project.run_once_source = (
        'class RunMeFirstOnce { public static String FW_ARGS; '
        'public static void main(String[] args) { FW_ARGS = "--demo"; } }'
    )
    project.arguments = ["alpha", "beta"]
    project.custom_verdicts = [("2", "domain fail")]
    text = spec_toml(project, "latency_ms:min,throughput:max")
    path = tmp_path / "runtime_demo.toml"
    path.write_text(text, encoding="utf-8")

    spec = fwgen.load_spec(path)
    assert spec.slots[0].sheet == "DIMENSION_1"
    assert spec.slots[0].values == ["baseline", "alternative"]
    assert [(goal.key, goal.direction) for goal in spec.goals] == [
        ("latency_ms", "min"), ("throughput", "max")]
    assert spec.runme == project.run_once_source
    assert spec.args == ["alpha", "beta"]

    workbook = load_workbook(BytesIO(project.to_xlsx_bytes()), data_only=False)
    assert workbook["FW_RunMeFirstOnce"]["A1"].value == project.run_once_source


def test_new_control_surface_inherits_the_complete_tested_registry():
    from intake import serve_face1

    actual = {(key, flag, kind) for key, flag, kind in supported_control_fields()}
    expected = set(serve_face1._RUN_FLAG_SPECS) | {
        (key, flag, "value") for key, flag in serve_face1._STRESS_FLAG_SPECS
    }
    assert actual == expected


def test_runtime_capability_validation_uses_stable_registry_reason_codes():
    project = GridProject.blank(visible_rows=1)
    config = default_run_config(project.name)
    config.update({"transport": "grpc", "profile": "generated-default"})
    selection = runtime_capability_selection(config)
    assert selection["language"] == "python" and selection["candidate_sink"] == "grpc"
    errors = [p.message for p in validate_runtime(project, config) if p.severity == "error"]
    assert any(message.startswith("GRPC_REQUIRES_JAVA:") for message in errors)


def test_worker_command_wraps_the_real_full_control_command(tmp_path):
    config = default_run_config("demo") | {
        "drawExact": True,
        "sieve": True,
        "budgetFinalCandidates": "5000",
        "coreTimeout": "90",
        "analyzer": "latency:min",
        "mode": "formal",
    }
    command = build_worker_command(config, tmp_path / "in.xlsx", tmp_path / "spec", tmp_path / "runs")
    assert command[1:3] == ["-m", "face1_new.workbook_runner"]
    assert "--draw-exact" in command
    assert command[command.index("--budget-final-candidates") + 1] == "5000"
    assert command[command.index("--core-timeout") + 1] == "90"
    assert command[command.index("--analyzer") + 1] == "latency:min"
    assert command[command.index("--analysis-mode") + 1] == "formal"


def test_runtime_validation_blocks_formal_without_goals_and_conflicting_draw_modes():
    project = GridProject.blank(visible_rows=1)
    config = default_run_config(project.name) | {"mode": "formal", "draw": True, "drawExact": True}
    messages = [problem.message for problem in validate_runtime(project, config) if problem.severity == "error"]
    assert any("Formal analysis" in message for message in messages)
    assert any("either pre-Core Face 2" in message for message in messages)


def test_runtime_validation_requires_an_explicit_policy_and_trusted_local_evidence():
    project = GridProject.blank(visible_rows=1)
    blank = default_run_config(project.name)
    messages = [p.message for p in validate_runtime(project, blank) if p.severity == "error"]
    assert any("no execution policy selected" in message for message in messages)

    trusted = blank | {"profile": "trusted-local"}
    messages = [p.message for p in validate_runtime(project, trusted) if p.severity == "error"]
    assert any("explicit, recorded reason" in message for message in messages)

    trusted.update({
        "candidateOrigin": "locally-authored",
        "trustedLocalAcknowledgement": "I reviewed this local workbook and its oracle",
    })
    messages = [p.message for p in validate_runtime(project, trusted) if p.severity == "error"]
    assert not any("execution policy" in message or "profile 'trusted-local'" in message
                   for message in messages)


def test_catalog_launch_validates_the_effective_special_profile_before_artifacts():
    example = {
        "id": "ai-example",
        "run_profile": AI_PROFILE,
        "spec": "unused-by-this-unit-test.toml",
    }
    try:
        example_run_config(example, default_run_config())
    except PolicyError as exc:
        assert "explicit, recorded reason" in str(exc)
    else:
        raise AssertionError("trusted special profile was not authorized")

    config = default_run_config()
    config.update({
        "candidateOrigin": "reviewed-checked-in",
        "trustedLocalAcknowledgement": "reviewed repository scenario",
    })
    resolved = example_run_config(example, config)
    assert resolved["profile"] == "trusted-local"
    assert resolved["candidateOrigin"] == "reviewed-checked-in"


def test_worker_argument_parser_and_exact_stage_copy(monkeypatch, tmp_path):
    project = GridProject.blank(visible_rows=1)
    workbook = tmp_path / "source.xlsx"
    workbook.write_bytes(project.to_xlsx_bytes())
    parsed, rest = parse_args(["--workbook", str(workbook), "--", "spec", "--db", "demo"])
    assert parsed == workbook
    assert rest == ["spec", "--db", "demo"]

    import bundle.cli as bundle_cli

    # The Generator is substituted through an explicit StageTable, so nothing on
    # the cli module is mutated and there is no global state to restore.
    stages = exact_workbook_stage_table(workbook)
    assert stages.gen is not bundle_cli.stage_gen
    assert stages.core is bundle_cli.stage_core, "only the Generator may be substituted"

    scratch = tmp_path / "scratch"
    scratch.mkdir()
    copied = stages.gen(tmp_path / "spec", scratch)
    assert copied.read_bytes() == workbook.read_bytes()


def _count(name, value):
    return {"name": name, "actual": value}


def test_progress_results_and_csv_are_read_from_real_artifact_shapes(tmp_path):
    run = tmp_path / "r1"
    (run / "stages").mkdir(parents=True)
    (run / "state.json").write_text(json.dumps({
        "status": "SUCCEEDED",
        "stages": {"core": {"status": "SUCCEEDED"}, "reader": {"status": "SUCCEEDED"},
                   "executor": {"status": "SUCCEEDED"}, "analyzer": {"status": "SUCCEEDED"}},
    }))
    (run / "stages" / "core.json").write_text(json.dumps({"counts": [_count("fw_final", 6)]}))
    (run / "stages" / "reader.json").write_text(json.dumps({"counts": [_count("candidates", 6)]}))
    (run / "stages" / "executor.json").write_text(json.dumps({
        "counts": [_count("processed", 6), _count("pass", 5), _count("fail", 1)]}))
    (run / "executor-summary.json").write_text(json.dumps({"processed": 6, "pass": 5, "fail": 1}))
    (run / "provenance.json").write_text(json.dumps({
        "mode": "FORMAL", "provenance_ok": True,
        "goals": [{"key": "latency", "mode": "MINIMIZE"}],
        "candidates": [{"candidate_id": "c1", "outcome": "PASS",
                        "objectives": {"latency": 12}, "source_ref": "src/c1.py"}],
    }))

    status, stages = collect_progress(run)
    results = collect_results(run)
    csv_text = results_csv(results)
    assert status == "SUCCEEDED"
    assert stages["core"]["counts"]["fw_final"] == 6
    assert results["processed"] == 6 and results["pass"] == 5
    assert results["front"][0]["objectives"]["latency"] == 12
    assert "candidate,outcome,latency" in csv_text


def test_iterate_session_resolves_latest_iteration_directory(tmp_path):
    import subprocess
    from face1_new.runtime_model import RunSession

    runs = tmp_path / "runs"
    (runs / "campaign-it1").mkdir(parents=True)
    latest = runs / "campaign-it2"
    latest.mkdir()
    fake_process = subprocess.Popen(["true"], text=True)
    fake_process.wait()
    session = RunSession(
        "token", fake_process, runs / "campaign", tmp_path, ("true",),
        done=True, exit_code=0,
    )

    assert session._resolved_run_dir() == latest
