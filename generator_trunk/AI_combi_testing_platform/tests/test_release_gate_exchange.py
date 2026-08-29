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
# Some names in this file are name-holders: neutral stand-ins where a
# vendor's product name would otherwise appear. Deliberate, not an
# oversight -- see 'Name-holders' in NOTICE.md.

from __future__ import annotations

import itertools
import json
from pathlib import Path

import fwgen
import pytest

from AI_combi_testing_platform.reporting import parse_metrics_line
from AI_combi_testing_platform.sub_suites.release_gate_breakpoint.cli import (
    FRAMEWORK_SOURCE,
    _inside_framework_source,
)
from AI_combi_testing_platform.sub_suites.release_gate_breakpoint.config import (
    CONFIG_SCHEMA,
    BreakpointVariant,
    TargetCell,
    load_suite_config,
    suite_config,
)
from AI_combi_testing_platform.sub_suites.release_gate_breakpoint.exchange import (
    FULL_SIGNATURE,
    PAIRWISE_COVERING_SIGNATURES,
    RELEASE_CANDIDATES_PER_TASK,
    ZERO_SIGNATURE,
    build_breakpoint_requests,
    build_release_gate_spec_text,
    build_release_head_cells,
    build_release_head_source,
    candidate_coordinates,
    release_cell_filename,
)
from AI_combi_testing_platform.sub_suites.release_gate_breakpoint.runner import (
    RELEASE_GOALS,
    bundle_run_command,
)
from AI_combi_testing_platform.sub_suites.release_gate_breakpoint.task_factory import (
    generate_release_gate_ladder,
)


SEED = b"public-release-gate-exchange-test-seed-v2"


def _config(*, difficulty_units: tuple[int, ...] = (2, 4, 8, 16, 32)):
    return suite_config(
        (
            TargetCell("provider-a", "model/a exact label", "minimal"),
            TargetCell("provider-b", "model-b", "middle"),
        ),
        difficulty_units=difficulty_units,
    )


def _tasks(difficulty_units: tuple[int, ...] = (2, 4, 8, 16, 32)) -> list[dict]:
    return [
        row.task
        for row in generate_release_gate_ladder(SEED, difficulty_units)
    ]


def test_config_is_provider_neutral_round_trip_and_fail_closed(
    tmp_path: Path,
) -> None:
    config = _config(difficulty_units=(4, 8, 16))
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(config.as_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    assert load_suite_config(path) == config
    assert config.as_dict()["schema"] == CONFIG_SCHEMA
    assert config.constructor_candidate_count == 3 * RELEASE_CANDIDATES_PER_TASK
    assert config.request_count == 2 * 3 * 2

    invalid = config.as_dict()
    invalid["difficulty_units"] = [2, 8]
    path.write_text(json.dumps(invalid), encoding="utf-8")
    with pytest.raises(ValueError, match="strictly doubling"):
        load_suite_config(path)


def test_custom_breakpoint_variants_drive_request_count() -> None:
    config = suite_config(
        (TargetCell("provider", "model", "effort"),),
        difficulty_units=(2, 4),
        breakpoint_variants=(
            BreakpointVariant("clean", ZERO_SIGNATURE),
            BreakpointVariant("center", PAIRWISE_COVERING_SIGNATURES[5]),
            BreakpointVariant("stress", FULL_SIGNATURE),
        ),
    )
    assert config.prompts_per_cell == 6
    assert config.request_count == 6


def test_spec_uses_real_fourth_order_prompt_construction(tmp_path: Path) -> None:
    tasks = _tasks()
    text = build_release_gate_spec_text(tasks)
    path = tmp_path / "scenario.toml"
    path.write_text(text, encoding="utf-8")
    spec = fwgen.load_spec(path, strict=True)
    assert len(spec.seq_extra) == 4
    assert sum("FW_()" in row[-1] for row in spec.seq_extra) == 3
    assert "FW_Permut(2)" in text
    assert "group_replace" in text
    assert text.count('flags = ["FW_Optional"]') == 4
    assert [slot.sheet for slot in spec.slots if slot.sheet.endswith("_RESULT")] == [
        "L1_RESULT",
        "L2_RESULT",
        "L3_RESULT",
        "ROOT_RESULT",
    ]
    assert [slot.sheet for slot in spec.slots[:3]] == [
        "HEAD",
        "TASK_DATA",
        "TASK_LEVEL",
    ]
    # nested braces + FW_Group are runtime-known: the plan must never claim an
    # exact number for them (a provable ceiling is allowed and preferred)
    assert fwgen.spec_cardinality_plan(spec).final.mode.value != "EXACT"
    assert len(tasks) * RELEASE_CANDIDATES_PER_TASK == 2560


def test_embedded_holdout_tasks_use_bounded_transport_cells_and_round_trip() -> None:
    tasks = _tasks()
    runtime_head, task_data = build_release_head_cells(tasks)
    assert len(runtime_head) < 32_000
    assert len(task_data) < 32_000
    assert max(map(len, runtime_head.splitlines())) < 1024
    assert max(map(len, task_data.splitlines())) < 1024
    assert build_release_head_source(tasks) == runtime_head + task_data
    namespace: dict = {}
    exec(compile(runtime_head + task_data, "<release-gate-head>", "exec"), namespace)
    assert namespace["RG_TASKS"] == tasks
    assert "RG_TASK_B64_PARTS" not in namespace


def test_six_level_transport_remains_bounded() -> None:
    tasks = _tasks((2, 4, 8, 16, 32, 64))
    runtime_head, task_data = build_release_head_cells(tasks)
    assert max(len(runtime_head), len(task_data)) < 32_000


def test_covering_design_is_balanced_strength_two_and_exponential() -> None:
    rows = [tuple(int(bit) for bit in row) for row in PAIRWISE_COVERING_SIGNATURES]
    assert len(rows) == 10
    assert all(len(row) == 9 for row in rows)
    assert [sum(row) for row in rows] == list(range(10))
    assert [2 ** sum(row) for row in rows] == [2**weight for weight in range(10)]
    for column in range(9):
        assert sum(row[column] for row in rows) == 5
    for left, right in itertools.combinations(range(9), 2):
        assert {(row[left], row[right]) for row in rows} == {
            (0, 0),
            (0, 1),
            (1, 0),
            (1, 1),
        }


def test_reader_source_coordinates_recover_all_nine_factors() -> None:
    source = """
RG_LEVEL = 13
RG_PLAN["section_order"].append("evidence")
RG_PLAN["section_order"].append("policy")
RG_PLAN["numeric_surface"] = "converted"
RG_PLAN["context_depth"] = "long"
RG_PLAN["schema"] = "plain"
RG_PLAN["trust_wording"] = "nested"
RG_PLAN["options"].append("alt_rule_labels")
RG_PLAN["options"].append("alt_decision_words")
RG_PLAN["options"].append("dist_archive")
RG_PLAN["options"].append("dist_override")
"""
    level, plan, signature = candidate_coordinates(source)
    assert level == 13
    assert signature == FULL_SIGNATURE
    assert plan["section_order"] == ["evidence", "policy"]


def test_breakpoint_exchange_uses_configured_cells_levels_and_variants() -> None:
    config = _config(difficulty_units=(4, 8, 16))
    documents = {}
    for level, units in enumerate(config.difficulty_units):
        for variant in config.breakpoint_variants:
            signature = variant.factor_signature
            documents[level, signature] = {
                "candidate_id": f"rgc-{level}{signature}abcdefghi"[:24],
                "task_id": f"rgt-{level:020d}"[:24],
                "difficulty_units": units,
                "prompt": f"level={level} factors={signature}",
            }
    requests = build_breakpoint_requests(documents, config)
    assert len(requests) == config.request_count == 12
    assert [row.level for row in requests[:6]] == [0, 0, 1, 1, 2, 2]
    assert [row.factor_signature for row in requests[:6]] == [
        value
        for _level in range(3)
        for value in (ZERO_SIGNATURE, FULL_SIGNATURE)
    ]
    assert {(row.provider, row.target_model, row.effort) for row in requests} == {
        ("provider-a", "model/a exact label", "minimal"),
        ("provider-b", "model-b", "middle"),
    }
    assert len({row.request_id for row in requests}) == len(requests)


def test_cell_filenames_are_sanitized_and_counted() -> None:
    cell = TargetCell("provider / one", "model label", "middle")
    name = release_cell_filename(
        cell,
        14,
        "prompts",
    )
    assert name.startswith("provider-one__model-label__middle__")
    assert name.endswith("__14-prompts.txt")
    assert len(name.encode("utf-8")) <= 255
    assert "/" not in name
    assert name != release_cell_filename(
        TargetCell("provider-one", "model label", "middle"),
        14,
        "prompts",
    )


def test_runtime_exchange_output_must_be_outside_source_checkout(
    tmp_path: Path,
) -> None:
    assert _inside_framework_source(FRAMEWORK_SOURCE / "generated-exchange")
    assert not _inside_framework_source(tmp_path.resolve())


def test_release_run_command_is_bounded_isolated_and_explicitly_higher_order(
    tmp_path: Path,
) -> None:
    command = bundle_run_command(
        tmp_path / "spec",
        db_name="ai_combi_release_gate_012345abcdef",
        run_id="release-test",
        runs_root=tmp_path / "runs",
        scratch_root=tmp_path / "scratch",
        main_port=5433,
        results_port=5432,
        candidate_count=1536,
    )
    assert command[command.index("--budget-requests") + 1] == "1536"
    assert command[command.index("--execution-policy-profile") + 1] == "generated-default"
    assert command[command.index("--analyzer") + 1] == RELEASE_GOALS
    assert "--allow-extreme" in command
    assert command[command.index("--override-budget") + 1].startswith("reviewed bounded")


def test_release_metrics_use_common_platform_namespace() -> None:
    fields = parse_metrics_line(
        "app=ai_combi_testing study=release_gate_breakpoint "
        "candidate_id=rgc-example correct=1 FW_VAR=0"
    )
    assert fields["app"] == "ai_combi_testing"
    assert fields["study"] == "release_gate_breakpoint"
    assert fields["FW_VAR"] == "0"
