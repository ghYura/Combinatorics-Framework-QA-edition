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

from __future__ import annotations

from face1_new import runtime_model
from face1_new.runtime_model import (
    RunSession,
    default_run_config,
    load_verified_examples,
)


def _authorized_config() -> dict:
    config = default_run_config("workbook")
    config.update({
        "candidateOrigin": "reviewed-checked-in",
        "trustedLocalAcknowledgement": "reviewed checked-in automation scenario",
    })
    return config


def test_face1_new_starts_the_checked_in_automation_profile(
    monkeypatch,
    tmp_path,
) -> None:
    example = next(
        scenario
        for scenario in load_verified_examples()
        if scenario["id"] == "automation_studio_00_smoke"
    )
    root = tmp_path / "new-example"
    root.mkdir()
    captured = {}

    def fake_spawn(cls, command, run_dir, work_dir, environment=None, launch_cwd=None):
        captured.update(
            command=tuple(command),
            run_dir=run_dir,
            work_dir=work_dir,
            environment=environment,
            launch_cwd=launch_cwd,
        )
        return captured

    monkeypatch.setattr(runtime_model.tempfile, "mkdtemp", lambda prefix: str(root))
    monkeypatch.setattr(RunSession, "_spawn", classmethod(fake_spawn))
    result = RunSession.start_example(
        example,
        _authorized_config()
        | {
            "lang": "java",
            "transport": "grpc",
            "draw": True,
            "sieve": True,
        },
    )
    command = result["command"]

    assert command[command.index("--db") + 1] == "automation_studio_00_smoke"
    assert command[command.index("--lang") + 1] == "py"
    assert command[command.index("--candidate-sink") + 1] == "sharded"
    assert "--unleash-initial-productivity-power" in command
    assert "--py-executor" in command
    assert command[command.index("--candidate-origin") + 1] == "reviewed-checked-in"
    assert "--acknowledge-trusted-local" in command
    assert "--draw" not in command and "--sieve" not in command
    assert result["environment"]["AUTOMATION_BUNDLE_EXECUTOR_WORKERS"]
    assert result["launch_cwd"] == runtime_model.ROOT.parent


def test_face1_new_advanced_example_has_budget_acknowledgments(monkeypatch, tmp_path) -> None:
    example = next(
        item for item in load_verified_examples()
        if item["id"] == "automation_studio_advanced_20_grouped"
    )
    root = tmp_path / "new-advanced"
    root.mkdir()
    captured = {}

    def fake_spawn(cls, command, run_dir, work_dir, environment=None, launch_cwd=None):
        captured["command"] = tuple(command)
        return captured

    monkeypatch.setattr(runtime_model.tempfile, "mkdtemp", lambda prefix: str(root))
    monkeypatch.setattr(RunSession, "_spawn", classmethod(fake_spawn))
    RunSession.start_example(example, _authorized_config())
    command = captured["command"]
    assert "--allow-extreme" in command
    assert command[command.index("--override-budget") + 1] == (
        "explicit advanced recursive control-topology search"
    )
