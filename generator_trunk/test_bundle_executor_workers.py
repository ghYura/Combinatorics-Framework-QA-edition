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
"""--executor-workers: py_executor's local worker pool, reachable from the launcher.

The pool itself (partitioning, summary/metrics merge, crash resume) is proven in
Executor_trunk/test_py_executor.py. What these pin is the launcher side, which
was missing: the option reaches py_executor as `--workers N`, N=1 changes
nothing, and the capability registry refuses every combination the pool is not
verified for -- through the same gate preflight uses.
"""
from __future__ import annotations

import dataclasses
from types import SimpleNamespace

import pytest

from bundle import capabilities as caps
from bundle import stages
from bundle.config import BundleConfig
from bundle.errors import PreflightError
from bundle.stages import capability_gate

def _summary(processed, passed, failed, suffix):
    return (f"py_executor DONE: processed={processed} pass={passed} fail={failed} broken=0 "
            f"inserted={processed} ({suffix})\n"
            f"py_executor OUTCOMES: pass={passed} domain_fail={failed} broken=0 timeout=0 "
            f"infra_fail=0 skipped=0 cancelled=0\n"
            f"py_executor RESULTS_V2: attempted={processed} inserted={processed} "
            f"already_present=0 updated_selected=0\n")


# What a pooled run really prints: every worker's own partition summary first,
# the dispatcher's aggregate last. Reading the first match took one worker's
# share for the whole run (live: 551 of 3456) and failed the Results invariant.
_DONE = (_summary(2, 1, 1, "failOnly=False") + _summary(4, 3, 1, "failOnly=False")
         + _summary(6, 4, 2, "workers=3"))


def _run_executor_stage(monkeypatch, tmp_path, workers: int) -> "list[str]":
    seen = {}

    def fake_run(cmd, **_kw):
        seen["cmd"] = list(cmd)
        return SimpleNamespace(stdout=_DONE, stderr="", returncode=0)

    monkeypatch.setattr(stages, "run", fake_run)
    hs = tmp_path / "handshake"
    hs.mkdir()
    cfg = dataclasses.replace(BundleConfig(), executor_workers=workers)
    counts = stages._stage_python_executor(tmp_path / "src", hs, cfg)
    assert counts[:5] == (6, 4, 2, 0, 6), "a pooled run must read back exactly like a serial one"
    return seen["cmd"]


def test_workers_reach_py_executor(monkeypatch, tmp_path) -> None:
    cmd = _run_executor_stage(monkeypatch, tmp_path, workers=3)
    assert cmd[cmd.index("--workers") + 1] == "3"


def test_one_worker_leaves_the_command_unchanged(monkeypatch, tmp_path) -> None:
    assert "--workers" not in _run_executor_stage(monkeypatch, tmp_path, workers=1)


def _selection(**overrides) -> dict:
    base = {"language": "python", "candidate_sink": "loose-files", "handoff": "v2",
            "run_mode": "verdict", "execution_policy": "trusted-local", "executor_pool": "single",
            "executor_workers": "multi", "repeat": "k1", "analyzer": "none"}
    base.update(overrides)
    return caps.normalize(base)


def _args(selection) -> SimpleNamespace:
    return SimpleNamespace(lang={"python": "py", "java": "java"}[selection["language"]],
                           mode=selection["run_mode"], legacy_handoff=selection["handoff"] == "legacy",
                           analyzer="", analysis_mode="exploratory", lifecycle="run", entrypoint="direct")


def _cfg(selection) -> BundleConfig:
    return dataclasses.replace(
        BundleConfig(), candidate_sink=selection["candidate_sink"],
        execution_policy_profile=selection["execution_policy"],
        executor_workers=4 if selection["executor_workers"] == "multi" else 1,
        repeat_each_candidate=3 if selection["repeat"] == "k_gt_1" else 1)


def test_python_pool_is_runnable_but_marked_experimental() -> None:
    selection = _selection()
    verdict = caps.classify(selection)
    assert verdict.blocking_code is None or verdict.blocking_code == "", verdict.codes
    assert "WORKERS_EXPERIMENTAL" in verdict.codes
    capability_gate(_args(selection), _cfg(selection))          # must not raise


@pytest.mark.parametrize("overrides, code", [
    ({"language": "java"}, "WORKERS_REQUIRE_PYTHON"),
    ({"candidate_sink": "sharded"}, "WORKERS_REQUIRE_LOOSE_FILES"),
    ({"run_mode": "stress"}, "WORKERS_REQUIRE_VERDICT"),
    ({"repeat": "k_gt_1"}, "WORKERS_INCOMPATIBLE_WITH_REPEAT"),
])
def test_unverified_combinations_fail_closed_in_preflight(overrides, code) -> None:
    selection = _selection(**overrides)
    assert code in caps.classify(selection).codes
    with pytest.raises(PreflightError):
        capability_gate(_args(selection), _cfg(selection))


def test_serial_default_is_untouched_by_the_worker_rules() -> None:
    verdict = caps.classify(_selection(executor_workers="single"))
    assert not any(code.startswith("WORKERS_") for code in verdict.codes)


def test_doctor_reports_the_pool_it_would_run() -> None:
    from bundle import doctor
    cfg = dataclasses.replace(BundleConfig(), executor_workers=4, execution_policy_profile="trusted-local")
    check = doctor._check_capability_matrix(cfg)
    assert "'executor_workers': 'multi'" in " ".join(check.details)
