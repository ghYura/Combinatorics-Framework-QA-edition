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

"""Targeted tests for `bundle resume` (STEP 24): run-reference resolution,
crash reconciliation, and the reuse/rerun cascade -- a stage is only ever
reused when its recorded status, invariants, and on-disk/DB artifacts still
agree with what's observable now; once one stage must rerun, every later
stage reruns too (run: `python3 -m pytest test_bundle_resume.py -q`)."""
import dataclasses
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from bundle import cli
from bundle import orchestrator as orch
from bundle.config import BundleConfig
from bundle.handoff import (
    CandidateTransport,
    HANDOFF_SCHEMA,
    HandoffV2,
    handoff_to_dict,
    Language,
    ResultTargetRef,
    SourceLocation,
    VerdictMode,
)
from bundle.jsonio import read_json, write_json_atomic
from bundle.errors import PreflightError, StageError
from bundle.policy import policy_hash, policy_id, resolve_policy
from bundle.models import (
    CountObservation,
    InvariantResult,
    InvariantSeverity,
    RUN_SCHEMA,
    RunManifest,
    RunStatus,
    STAGE_RESULT_SCHEMA,
    StageResult,
    StageStatus,
    run_manifest_from_dict,
)
from bundle.resume import (
    count_actual,
    critical_invariants_ok,
    dir_artifact,
    file_artifact,
    reconcile_interrupted,
    resolve_run_layout,
    ResumeError,
    succeeded_with_invariants,
)
from bundle.runs import file_sha256, RunLayout

CRITICAL = InvariantSeverity.CRITICAL

# A publish-clean checkout deliberately has no Maven ``target`` JARs. These
# resume tests exercise the journal/reuse cascade with mocked stages, so their
# synthetic prior run must not claim that generated binaries participated in
# it. Keep checked-in source/config fingerprints while omitting only build
# outputs from this unit-test fixture. The real-shard tests below still require
# and explicitly detect the compiled Reader classes before running.
_REAL_STAGE_COMPONENT_ARTIFACTS = orch._stage_component_artifacts
_GENERATED_COMPONENT_KINDS = frozenset({
    "component.core_jar",
    "component.reader_jar",
    "component.analyzer_jar",
    "component.java_executor",
    "component.java_dependency_jars",
})


@pytest.fixture(autouse=True)
def _source_only_component_artifacts(monkeypatch):
    def source_only(stage, cfg, language="python"):
        return tuple(
            artifact
            for artifact in _REAL_STAGE_COMPONENT_ARTIFACTS(stage, cfg, language)
            if artifact.kind not in _GENERATED_COMPONENT_KINDS
        )

    monkeypatch.setattr(orch, "_stage_component_artifacts", source_only)


def _inv(id, *, passed=True, severity=CRITICAL) -> InvariantResult:
    return InvariantResult(id=id, description=id, expected="x", actual="x", passed=passed, severity=severity)


# STEP 32: real shards for the sharded-resume tests are produced by the Java ShardSink
# (the production writer), so resume's reuse decision runs against genuine *.fwshard files.
_READER_CLASSES = Path(__file__).resolve().parent.parent / "Reader_trunk" / "target" / "classes"
_SHARD_EMITTER = "com.company.sink.ShardCorpusEmitter"


def _java_shards_available() -> bool:
    return shutil.which("java") is not None and (_READER_CLASSES / "com/company/sink/ShardSink.class").exists()


def _emit_shards(dirpath: Path, n: int, max_records: int = 4) -> int:
    """Write a real compressed-shard corpus into ``dirpath`` via the Java ShardSink; return n."""
    dirpath.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["java", "-cp", str(_READER_CLASSES), _SHARD_EMITTER,
                        str(dirpath), str(n), str(max_records)], capture_output=True, text=True)
    assert r.returncode == 0, f"shard emitter failed: {r.stdout}\n{r.stderr}"
    return n


def _write_stage(layout, name, status, *, counts=(), invariants=(), artifacts=()):
    write_json_atomic(layout.stages_dir / f"{name}.json", StageResult(
        schema=STAGE_RESULT_SCHEMA, stage=name, status=status,
        start="2026-06-07T00:00:00Z", end="2026-06-07T00:01:00Z", duration_seconds=1.0,
        counts=tuple(counts), invariants=tuple(invariants), artifacts=tuple(artifacts)))


#: The execution authorization a normally-launched run records. Resume compares
#: against this; without it there is nothing to prove the policy is unchanged.
_AUTHORIZED = {
    "profile": "trusted-local",
    "origin": "reviewed-checked-in",
    "acknowledgement": "reviewed checked-in fixture candidates",
    "sandboxed": False,
    "policy_id": policy_id(resolve_policy("trusted-local")),
    "policy_hash": policy_hash(resolve_policy("trusted-local")),
}


def _build_run(d, *, n_cands=3, executor_status=StageStatus.FAILED, sharded=False,
               authorization=_AUTHORIZED):
    """Build a tiny on-disk run that already got through gen/core/reader (no
    sieve/analyzer -- keeps the fixture small), mirroring `_run`'s on-disk
    layout closely enough for `cmd_resume`/`_resume_run` to inspect it."""
    root = Path(d) / "scratch" / "demo" / "runs" / "demo-run"
    for sub in ("stages", "logs", "workbooks", "candidates", "handoff", "metrics", "reports", "wb", "src"):
        (root / sub).mkdir(parents=True)
    (root / "handshake" / "handoff").mkdir(parents=True)
    layout = RunLayout(run_id="demo-run", root=root, manifest_path=root / "run.json", state_path=root / "state.json")

    spec_path = Path(d) / "spec.toml"
    spec_path.write_text("title = 'demo'\n", encoding="utf-8")
    sha = file_sha256(spec_path)

    manifest = RunManifest(
        schema=RUN_SCHEMA, run_id="demo-run", status=RunStatus.FAILED, db_name="demo",
        spec_path=str(spec_path), spec_sha256=sha, spec_version="v1", mode="verdict", goals="",
        start="2026-06-07T00:00:00Z", scratch_root=str(Path(d) / "scratch" / "demo"),
        settings={"lang": "py", "main_port": 5433, "results_port": 5434, "mode": "verdict",
                  "sieve": False, "analyzer_goals": "", "budget": None,
                  # Phase 02 / audit F3: resume re-resolves this and refuses to
                  # continue under a different policy. A run recorded without it
                  # cannot be resumed at all -- see the dedicated test below.
                  "execution_authorization": authorization,
                  "optional_table_contract": orch.contract_from_spec(
                      SimpleNamespace(slots=[])).to_dict()})
    write_json_atomic(layout.manifest_path, manifest)
    workbook = root / "wb" / "demo.xlsx"
    workbook.write_bytes(b"fake-xlsx")
    cfg = BundleConfig()

    _write_stage(layout, "gen", StageStatus.SUCCEEDED,
                 artifacts=(file_artifact("input.spec", spec_path),
                            file_artifact("output.workbook", workbook),
                            *orch._stage_component_artifacts("gen", cfg)))
    _write_stage(layout, "core", StageStatus.SUCCEEDED,
                 counts=(CountObservation(name="fw_final", expected=12, actual=12),),
                 invariants=(_inv("core.count_positive"),),
                 artifacts=(file_artifact("input.workbook", workbook),
                            *orch._stage_component_artifacts("core", cfg)))

    if sharded:
        _emit_shards(root / "src", n_cands)
        cand_glob, transport = "*.fwshard", CandidateTransport.SHARDED
    else:
        for i in range(n_cands):
            (root / "src" / f"c{i}.py").write_text(f"# candidate {i}\n", encoding="utf-8")
        cand_glob, transport = "*.py", CandidateTransport.LOOSE_FILES
    handoff = HandoffV2(
        schema=HANDOFF_SCHEMA, run_id="demo-run", language=Language.PYTHON,
        candidate_transport=transport, candidate_count=n_cands,
        id_format="<combi_id>_0_0",
        sources=(SourceLocation(kind="dir", path=str(root / "src")),),
        result_target=ResultTargetRef(host="127.0.0.1", port=5434, database="demo", user="fw"),
        result_schema_mode="placeholders=9", verdict_mode=VerdictMode.FW_VAR,
        arguments=("noargs",), shift=1)
    handoff_path = root / "handshake" / "handoff" / "manifest.json"
    write_json_atomic(handoff_path, handoff_to_dict(handoff))
    candidate_artifact = dir_artifact("output.candidates", root / "src", cand_glob)
    _write_stage(layout, "reader", StageStatus.SUCCEEDED,
                 counts=(CountObservation(name="candidates", expected=12, actual=n_cands),),
                 invariants=(_inv("reader.emitted_eq_expected"), _inv("reader.empty_zero"),
                             _inv("handoff.run_id_matches"), _inv("handoff.candidate_count_matches")),
                 artifacts=(candidate_artifact, file_artifact("output.handoff_manifest", handoff_path),
                            *orch._stage_component_artifacts("reader", cfg)))

    executor_artifacts = [dir_artifact("input.candidates", root / "src", cand_glob),
                          *orch._stage_component_artifacts("executor", cfg)]
    if executor_status == StageStatus.SUCCEEDED:
        summary = root / "executor-summary.json"
        summary.write_text(json.dumps({"processed": n_cands, "sandbox_backend": "local"}),
                           encoding="utf-8")
        executor_artifacts.insert(1, file_artifact("output.executor_summary", summary))
    _write_stage(layout, "executor", executor_status,
                 counts=(CountObservation(name="processed", actual=n_cands),),
                 invariants=(_inv("executor.processed_positive",
                                  passed=(executor_status == StageStatus.SUCCEEDED)),),
                 artifacts=tuple(executor_artifacts))

    write_json_atomic(layout.state_path, {
        "schema": RUN_SCHEMA, "run_id": "demo-run", "status": RunStatus.FAILED.value,
        "stages": {
            "gen": {"status": "SUCCEEDED"}, "core": {"status": "SUCCEEDED"},
            "reader": {"status": "SUCCEEDED"}, "executor": {"status": executor_status.value},
        }})
    return layout, spec_path


_FAKE_SPEC = SimpleNamespace(slots=[], name="demo", constraints=[], spec_version="v1")
_BLANK_ARGS = lambda root: SimpleNamespace(run=str(root), runs_root="", config_file="")  # noqa: E731


def _resume_psql(_port, _db, sql, **_kw):
    # Phase 3b: verdict count is now DISTINCT ON the 5-col sample key (candidate_id, repeat_idx,
    # env_id) at each sample's latest attempt -- still the per-candidate verdict count at K=1.
    if "distinct on (candidate_id, repeat_idx, env_id)" in sql:
        return "3", 0
    if "coalesce(max(attempt),0)" in sql:
        return "1", 0
    if "truncate table" in sql:
        return "", 0
    return "12", 0


def _emit_executor_summary(kwargs, *, processed=1, backend="local"):
    Path(kwargs["summary_path"]).write_text(
        json.dumps({"processed": processed, "sandbox_backend": backend}), encoding="utf-8")


# ----------------------------- resolve_run_layout ---------------------------- #
def test_resolve_run_layout_accepts_a_path_and_a_bare_id_and_fails_closed_otherwise():
    with tempfile.TemporaryDirectory() as d:
        layout, _ = _build_run(d)
        assert resolve_run_layout(str(layout.root)).root == layout.root

        scratch_root = str(Path(d) / "scratch")
        assert resolve_run_layout("demo-run", scratch_root=scratch_root).root == layout.root

        try:
            resolve_run_layout("no-such-run", scratch_root=scratch_root)
        except ResumeError:
            pass
        else:
            raise AssertionError("expected ResumeError for an unknown run id")


# ------------------------------ reconciliation -------------------------------- #
def test_reconcile_interrupted_fails_closed_on_a_stage_stuck_running():
    with tempfile.TemporaryDirectory() as d:
        layout, _ = _build_run(d)
        reconcile_interrupted(layout)                     # nothing RUNNING yet -- passes silently

        state = read_json(layout.state_path)
        state["stages"]["executor"] = {"status": "RUNNING"}
        write_json_atomic(layout.state_path, state)
        try:
            reconcile_interrupted(layout)
        except ResumeError as exc:
            assert "executor" in str(exc) and "RUNNING" in str(exc)
        else:
            raise AssertionError("expected ResumeError for a stage stuck RUNNING")


# --------------------------- small reusable predicates ------------------------ #
def test_stage_trust_predicates():
    succeeded = StageResult(schema=STAGE_RESULT_SCHEMA, stage="core", status=StageStatus.SUCCEEDED,
                            counts=(CountObservation(name="fw_final", actual=12),),
                            invariants=(_inv("core.count_positive"),))
    failed_invariant = dataclasses.replace(succeeded, invariants=(_inv("core.count_positive", passed=False),))
    not_done = dataclasses.replace(succeeded, status=StageStatus.FAILED)

    assert critical_invariants_ok(succeeded) and not critical_invariants_ok(failed_invariant)
    assert succeeded_with_invariants(succeeded)
    assert not succeeded_with_invariants(failed_invariant)
    assert not succeeded_with_invariants(not_done)
    assert not succeeded_with_invariants(None)
    assert count_actual(succeeded, "fw_final") == 12
    assert count_actual(succeeded, "no-such-count") is None
    assert count_actual(None, "fw_final") is None


# ------------------------------- fail-closed gates ---------------------------- #
def test_changed_spec_invalidates_and_reruns_all_stages():
    with tempfile.TemporaryDirectory() as d:
        layout, spec_path = _build_run(d)
        spec_path.write_text("title = 'demo-modified'\n", encoding="utf-8")
        ran = []
        hs = layout.root / "handshake"

        def fake_gen(*_a, **_k):
            ran.append("gen")
            return layout.root / "wb" / "demo.xlsx"

        def fake_core(*_a, **_k):
            ran.append("core")
            return 1

        def fake_reader(*_a, **_k):
            ran.append("reader")
            return layout.root / "src", hs, 1, 0, hs / "handoff" / "manifest.json"

        def fake_executor(*_a, **_k):
            ran.append("executor")
            assert _k["attempt"] == 2
            _emit_executor_summary(_k)
            return (1, 1, 0, 0, 1, 1, 0, 0,
                    {"attempted": 1, "inserted": 1, "already_present": 0, "updated_selected": 0})

        with patch.object(cli, "_load_one_spec", lambda spec_dir: (_FAKE_SPEC, spec_path)), \
             patch.object(orch, "psql", _resume_psql), \
             patch.object(orch, "stage_gen", side_effect=fake_gen), \
             patch.object(orch, "stage_core", side_effect=fake_core), \
             patch.object(orch, "stage_reader", side_effect=fake_reader), \
             patch.object(orch, "_record_handoff_manifest", lambda rec, *_a, **_k: object()), \
             patch.object(orch, "stage_executor", side_effect=fake_executor):
            cli.cmd_resume(_BLANK_ARGS(layout.root))

        assert ran == ["gen", "core", "reader", "executor"]
        manifest = run_manifest_from_dict(read_json(layout.manifest_path))
        assert manifest.spec_sha256 == file_sha256(spec_path)
        assert manifest.settings["optional_table_contract"]["expected_multiplier"] == 1


def test_resume_propagates_one_optional_contract_through_core_and_reader():
    with tempfile.TemporaryDirectory() as d:
        layout, spec_path = _build_run(d, executor_status=StageStatus.FAILED)
        spec_path.write_text("title = 'optional-modified'\n", encoding="utf-8")
        optional_spec = SimpleNamespace(
            slots=[SimpleNamespace(flags=("FW_Optional",), values=["a", "b"])],
            name="optional", constraints=[], spec_version="v1")
        seen = {}
        hs = layout.root / "handshake"

        def fake_core(*_a, **kwargs):
            seen["core"] = kwargs["optional_contract"]
            return 12

        def fake_reader(*_a, **kwargs):
            seen["reader"] = kwargs["optional_contract"]
            return layout.root / "src", hs, 36, 0, hs / "handoff" / "manifest.json"

        def fake_executor(*_a, **kwargs):
            _emit_executor_summary(kwargs, processed=36)
            return (36, 36, 0, 0, 36, 36, 0, 0,
                    {"attempted": 36, "inserted": 36, "already_present": 0,
                     "updated_selected": 0})

        with patch.object(cli, "_load_one_spec", lambda spec_dir: (optional_spec, spec_path)), \
             patch.object(cli.fg, "estimate_core_combos", lambda spec: 12), \
             patch.object(orch, "_optional_tables", lambda *_a, **_k: ["fw_opt1"]), \
             patch.object(orch, "psql", _resume_psql), \
             patch.object(orch, "stage_gen", lambda *_a, **_k: layout.root / "wb" / "demo.xlsx"), \
             patch.object(orch, "stage_core", side_effect=fake_core), \
             patch.object(orch, "stage_reader", side_effect=fake_reader), \
             patch.object(orch, "_record_handoff_manifest", lambda rec, *_a, **_k: object()), \
             patch.object(orch, "stage_executor", side_effect=fake_executor):
            cli.cmd_resume(_BLANK_ARGS(layout.root))

        assert seen["core"] is seen["reader"]
        assert seen["core"].expected_multiplier() == 3
        assert seen["core"].required_tables() == ("fw_opt1",)
        manifest = run_manifest_from_dict(read_json(layout.manifest_path))
        assert manifest.settings["optional_table_contract"] == seen["core"].to_dict()


def test_resume_refuses_optional_contract_drift_for_an_unchanged_spec():
    with tempfile.TemporaryDirectory() as d:
        layout, spec_path = _build_run(d)
        manifest = run_manifest_from_dict(read_json(layout.manifest_path))
        settings = dict(manifest.settings)
        settings["optional_table_contract"] = {
            **settings["optional_table_contract"], "expected_multiplier": 99}
        write_json_atomic(layout.manifest_path, dataclasses.replace(manifest, settings=settings))
        with patch.object(cli, "_load_one_spec", lambda spec_dir: (_FAKE_SPEC, spec_path)):
            with pytest.raises(ResumeError, match="optional-table contract"):
                cli.cmd_resume(_BLANK_ARGS(layout.root))


def test_resume_refuses_a_stress_run():
    with tempfile.TemporaryDirectory() as d:
        layout, _ = _build_run(d)
        manifest = run_manifest_from_dict(read_json(layout.manifest_path))
        write_json_atomic(layout.manifest_path, dataclasses.replace(manifest, mode="stress"))
        try:
            cli.cmd_resume(_BLANK_ARGS(layout.root))
        except ResumeError as exc:
            assert "stress" in str(exc)
        else:
            raise AssertionError("expected ResumeError for a stress run")


def test_resume_refuses_a_run_that_recorded_no_execution_authorization():
    """Audit F3. Resume never resolved a policy at all, so it could neither prove
    it was continuing the original decision nor verify the Executor honoured it.
    A run with no recorded authorization must be re-run, not retro-authorized."""
    with tempfile.TemporaryDirectory() as d:
        layout, spec_path = _build_run(d, authorization=None)
        with patch.object(cli, "_load_one_spec", lambda spec_dir: (_FAKE_SPEC, spec_path)):
            try:
                cli.cmd_resume(_BLANK_ARGS(layout.root))
            except PreflightError as exc:
                assert "no execution authorization" in str(exc)
            else:
                raise AssertionError("expected a refusal for an unauthorized run")


def test_resume_refuses_to_change_the_execution_policy():
    """Supplying a different profile on resume must be refused, not honoured --
    and a sandboxed-to-unsandboxed change is named as a downgrade."""
    with tempfile.TemporaryDirectory() as d:
        secure = resolve_policy("generated-default")
        layout, spec_path = _build_run(d, authorization={
            "profile": "generated-default", "origin": "generated", "acknowledgement": "",
            "sandboxed": True, "policy_id": policy_id(secure),
            "policy_hash": policy_hash(secure)})
        args = _BLANK_ARGS(layout.root)
        args.execution_policy_profile = "trusted-local"
        args.candidate_origin = "reviewed-checked-in"
        args.trusted_local_acknowledgement = "I would like the host back"
        with patch.object(cli, "_load_one_spec", lambda spec_dir: (_FAKE_SPEC, spec_path)):
            try:
                cli.cmd_resume(args)
            except PreflightError as exc:
                assert "downgrade" in str(exc)
            else:
                raise AssertionError("expected a refusal for a policy downgrade on resume")


def test_resume_rechecks_the_backend_of_a_reused_executor_summary():
    with tempfile.TemporaryDirectory() as d:
        secure = resolve_policy("generated-default")
        layout, spec_path = _build_run(d, executor_status=StageStatus.SUCCEEDED,
                                       authorization={
            "profile": "generated-default", "origin": "generated", "acknowledgement": "",
            "sandboxed": True, "policy_id": policy_id(secure),
            "policy_hash": policy_hash(secure)})
        # _build_run recorded this exact summary as an artifact. For a secure
        # authorization, its local backend is proof of the forbidden downgrade.
        with patch.object(cli, "_load_one_spec", lambda spec_dir: (_FAKE_SPEC, spec_path)), \
             patch.object(orch, "psql", _resume_psql):
            with pytest.raises(StageError, match="refusing a secure run"):
                cli.cmd_resume(_BLANK_ARGS(layout.root))


def test_rerun_executor_must_emit_a_summary_on_resume():
    with tempfile.TemporaryDirectory() as d:
        layout, spec_path = _build_run(d, executor_status=StageStatus.FAILED)

        def fake_executor_without_summary(*_a, **_k):
            return (3, 3, 0, 0, 3, 3, 0, 0,
                    {"attempted": 3, "inserted": 3, "already_present": 0,
                     "updated_selected": 0})

        with patch.object(cli, "_load_one_spec", lambda spec_dir: (_FAKE_SPEC, spec_path)), \
             patch.object(orch, "psql", _resume_psql), \
             patch.object(orch, "stage_executor", side_effect=fake_executor_without_summary):
            with pytest.raises(StageError, match="executor summary missing"):
                cli.cmd_resume(_BLANK_ARGS(layout.root))


def test_resume_refuses_a_stage_stuck_running_before_touching_the_spec():
    with tempfile.TemporaryDirectory() as d:
        layout, _ = _build_run(d)
        state = read_json(layout.state_path)
        state["stages"]["executor"] = {"status": "RUNNING"}
        write_json_atomic(layout.state_path, state)
        # `_load_one_spec` is deliberately NOT patched -- reconciliation must
        # fail before resume ever needs to look at the spec.
        try:
            cli.cmd_resume(_BLANK_ARGS(layout.root))
        except ResumeError as exc:
            assert "RUNNING" in str(exc)
        else:
            raise AssertionError("expected ResumeError for a stage stuck RUNNING")


# --------------------------------- reuse cascade ------------------------------ #
def test_resume_reuses_valid_stages_and_only_reruns_the_failed_executor():
    """Acceptance: 'Resume после Reader не повторяет Core при valid artifacts.'"""
    with tempfile.TemporaryDirectory() as d:
        layout, spec_path = _build_run(d, n_cands=3, executor_status=StageStatus.FAILED)
        ran = []

        def fake_executor(*_a, **_k):
            ran.append("executor")
            _emit_executor_summary(_k, processed=3)
            return (3, 3, 0, 0, 3, 3, 0, 0,
                    {"attempted": 3, "inserted": 3, "already_present": 0, "updated_selected": 0})

        with patch.object(cli, "_load_one_spec", lambda spec_dir: (_FAKE_SPEC, spec_path)), \
             patch.object(orch, "psql", _resume_psql), \
             patch.object(orch, "stage_gen", side_effect=AssertionError("'gen' must be reused, not rerun")), \
             patch.object(orch, "stage_core", side_effect=AssertionError("'core' must be reused, not rerun")), \
             patch.object(orch, "stage_reader", side_effect=AssertionError("'reader' must be reused, not rerun")), \
             patch.object(orch, "stage_executor", side_effect=fake_executor):
            cli.cmd_resume(_BLANK_ARGS(layout.root))

        assert ran == ["executor"], f"expected only the executor to rerun, got {ran}"
        state = read_json(layout.state_path)
        assert state["status"] == "SUCCEEDED"
        for name in ("gen", "core", "reader"):
            assert state["stages"][name]["status"] == "SKIPPED", state["stages"][name]
        assert state["stages"]["executor"]["status"] == "SUCCEEDED"
        # SKIPPED records carry the prior counts forward (acceptance: "inspect
        # stage timestamps/counts" -- the journal stays complete evidence).
        core_json = read_json(layout.stages_dir / "core.json")
        assert core_json["status"] == "SUCCEEDED"
        assert core_json["counts"][0]["name"] == "fw_final" and core_json["counts"][0]["actual"] == 12


def test_resume_reuses_reader_when_recorded_manifest_hash_matches_policy_stamped_file():
    """Regression for BUG-2: a secure run's reader stage must record the handoff
    manifest's sha256 AFTER _persist_handoff_policy stamps execution_policy_ref
    into it -- otherwise the recorded hash (pre-stamp) never matches the on-disk
    file a resume re-hashes, and reader+executor needlessly rerun on a no-op
    resume (and a networked rerun then fails for lack of TRYOUT_URL). Here the
    on-disk manifest carries the stamp and the reader stage recorded the
    POST-stamp hash (what _run now does): the reader (and executor) MUST be
    reused, leaving a clean no-op."""
    with tempfile.TemporaryDirectory() as d:
        layout, spec_path = _build_run(d, n_cands=3, executor_status=StageStatus.SUCCEEDED)
        handoff_path = layout.root / "handshake" / "handoff" / "manifest.json"
        # mimic _persist_handoff_policy: stamp execution_policy_ref into the manifest
        raw = read_json(handoff_path)
        raw["execution_policy_ref"] = "ep-deadbeef0000"
        write_json_atomic(handoff_path, raw)
        # mimic the FIX: reader stage recorded the manifest hash AFTER the stamp
        cfg = BundleConfig()
        _write_stage(layout, "reader", StageStatus.SUCCEEDED,
                     counts=(CountObservation(name="candidates", expected=12, actual=3),),
                     invariants=(_inv("reader.emitted_eq_expected"), _inv("reader.empty_zero"),
                                 _inv("handoff.run_id_matches"), _inv("handoff.candidate_count_matches")),
                     artifacts=(dir_artifact("output.candidates", layout.root / "src", "*.py"),
                                file_artifact("output.handoff_manifest", handoff_path),
                                *orch._stage_component_artifacts("reader", cfg)))

        with patch.object(cli, "_load_one_spec", lambda spec_dir: (_FAKE_SPEC, spec_path)), \
             patch.object(orch, "psql", _resume_psql), \
             patch.object(orch, "_results_v2_latest_attempt_candidates", lambda *a, **k: 3), \
             patch.object(orch, "stage_gen", side_effect=AssertionError("'gen' must be reused")), \
             patch.object(orch, "stage_core", side_effect=AssertionError("'core' must be reused")), \
             patch.object(orch, "stage_reader", side_effect=AssertionError("'reader' must be reused, not rerun")), \
             patch.object(orch, "stage_executor", side_effect=AssertionError("'executor' must be reused, not rerun")):
            cli.cmd_resume(_BLANK_ARGS(layout.root))

        state = read_json(layout.state_path)
        assert state["status"] == "SUCCEEDED"
        for name in ("gen", "core", "reader", "executor"):
            assert state["stages"][name]["status"] == "SKIPPED", (name, state["stages"][name])


def test_resume_reruns_reader_and_downstream_when_a_candidate_is_missing():
    """Acceptance: 'Missing candidate invalidates Reader/Executor.'"""
    with tempfile.TemporaryDirectory() as d:
        layout, spec_path = _build_run(d, n_cands=3, executor_status=StageStatus.SUCCEEDED)
        sorted((layout.root / "src").glob("*.py"))[0].unlink()   # 2 on disk now, 3 was recorded
        ran = []
        hs = layout.root / "handshake"

        def fake_reader(*_a, **_k):
            ran.append("reader")
            return layout.root / "src", hs, 12, 0, hs / "handoff" / "manifest.json"

        def fake_executor(*_a, **_k):
            ran.append("executor")
            _emit_executor_summary(_k, processed=12)
            return (12, 12, 0, 0, 12, 12, 0, 0,
                    {"attempted": 12, "inserted": 12, "already_present": 0, "updated_selected": 0})

        with patch.object(cli, "_load_one_spec", lambda spec_dir: (_FAKE_SPEC, spec_path)), \
             patch.object(cli.fg, "estimate_core_combos", lambda spec: 1), \
             patch.object(orch, "psql", _resume_psql), \
             patch.object(orch, "stage_gen", side_effect=AssertionError("'gen' must be reused, not rerun")), \
             patch.object(orch, "stage_core", side_effect=AssertionError("'core' must be reused, not rerun")), \
             patch.object(orch, "stage_reader", side_effect=fake_reader), \
             patch.object(orch, "_record_handoff_manifest", lambda rec, *_a, **_k: object()), \
             patch.object(orch, "stage_executor", side_effect=fake_executor):
            cli.cmd_resume(_BLANK_ARGS(layout.root))

        assert ran == ["reader", "executor"], f"expected reader+executor to rerun, got {ran}"
        state = read_json(layout.state_path)
        assert state["stages"]["core"]["status"] == "SKIPPED"
        assert state["stages"]["reader"]["status"] == "SUCCEEDED"
        assert state["stages"]["executor"]["status"] == "SUCCEEDED"


def test_resume_reruns_reader_when_candidate_content_changes_without_count_change():
    with tempfile.TemporaryDirectory() as d:
        layout, spec_path = _build_run(d, n_cands=3, executor_status=StageStatus.SUCCEEDED)
        sorted((layout.root / "src").glob("*.py"))[0].write_text("# changed, same file count\n", encoding="utf-8")
        ran = []
        hs = layout.root / "handshake"

        def fake_reader(*_a, **_k):
            ran.append("reader")
            return layout.root / "src", hs, 12, 0, hs / "handoff" / "manifest.json"

        def fake_executor(*_a, **_k):
            ran.append("executor")
            assert _k["attempt"] == 2
            _emit_executor_summary(_k, processed=12)
            return (12, 12, 0, 0, 12, 12, 0, 0,
                    {"attempted": 12, "inserted": 12, "already_present": 0, "updated_selected": 0})

        with patch.object(cli, "_load_one_spec", lambda spec_dir: (_FAKE_SPEC, spec_path)), \
             patch.object(cli.fg, "estimate_core_combos", lambda spec: 1), \
             patch.object(orch, "psql", _resume_psql), \
             patch.object(orch, "stage_gen", side_effect=AssertionError("gen must be reused")), \
             patch.object(orch, "stage_core", side_effect=AssertionError("core must be reused")), \
             patch.object(orch, "stage_reader", side_effect=fake_reader), \
             patch.object(orch, "_record_handoff_manifest", lambda rec, *_a, **_k: object()), \
             patch.object(orch, "stage_executor", side_effect=fake_executor):
            cli.cmd_resume(_BLANK_ARGS(layout.root))

        assert ran == ["reader", "executor"]


# ------------------------- sharded transport (STEP 32) ------------------------ #
def test_resume_detects_valid_finalized_shards_and_corruption():
    """STEP 32 review blocker #2: the launcher must DETECT valid finalized shards
    (the exact helpers resume's reuse gate calls) and detect a corrupt/partial one."""
    if not _java_shards_available():
        pytest.skip("java / compiled Reader (ShardSink) unavailable")
    from bundle import shards
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "src"
        _emit_shards(src, 12, max_records=5)                  # 3 shards: 5 + 5 + 2
        assert shards.has_shards(src)
        assert len(shards.list_finalized_shards(src)) == 3
        assert shards.all_shards_valid(src)                   # every shard passes CRC/trailer
        assert shards.count_candidates(src) == 12

        last = sorted(shards.list_finalized_shards(src))[-1]
        with open(last, "r+b") as f:                          # chop into the finalize trailer
            f.truncate(f.seek(0, 2) - 6)
        assert not shards.all_shards_valid(src)               # corruption detected
        assert shards.count_candidates(src) == 10             # the partial shard contributes 0


def test_resume_skips_valid_finalized_shards():
    """STEP 32 review blocker #2: a Reader whose candidates were written as compressed
    *.fwshard shards must be REUSED on resume (not rerun) when the shards are still valid
    and unchanged -- proven against real shards from the production Java ShardSink."""
    if not _java_shards_available():
        pytest.skip("java / compiled Reader (ShardSink) unavailable")
    with tempfile.TemporaryDirectory() as d:
        layout, spec_path = _build_run(d, n_cands=10, executor_status=StageStatus.FAILED, sharded=True)
        # sanity: the candidates really are in shards, not loose files
        assert sorted((layout.root / "src").glob("*.fwshard")) and not sorted((layout.root / "src").glob("*.py"))
        ran = []

        def fake_executor(*_a, **_k):
            ran.append("executor")
            _emit_executor_summary(_k, processed=10)
            return (10, 10, 0, 0, 10, 10, 0, 0,
                    {"attempted": 10, "inserted": 10, "already_present": 0, "updated_selected": 0})

        with patch.object(cli, "_load_one_spec", lambda spec_dir: (_FAKE_SPEC, spec_path)), \
             patch.object(orch, "psql", _resume_psql), \
             patch.object(orch, "stage_gen", side_effect=AssertionError("'gen' must be reused, not rerun")), \
             patch.object(orch, "stage_core", side_effect=AssertionError("'core' must be reused, not rerun")), \
             patch.object(orch, "stage_reader",
                          side_effect=AssertionError("'reader' must be reused -- valid finalized shards!")), \
             patch.object(orch, "stage_executor", side_effect=fake_executor):
            cli.cmd_resume(_BLANK_ARGS(layout.root))

        assert ran == ["executor"], f"expected only executor to rerun (shards reused), got {ran}"
        state = read_json(layout.state_path)
        assert state["stages"]["reader"]["status"] == "SKIPPED"   # valid finalized shards reused
        assert state["stages"]["executor"]["status"] == "SUCCEEDED"


def test_resume_reruns_reader_when_a_shard_is_corrupted():
    """STEP 32: a truncated/corrupt shard must INVALIDATE reuse (the candidate record
    count falls short and the shard-dir hash changes), so Reader + Executor rerun."""
    if not _java_shards_available():
        pytest.skip("java / compiled Reader (ShardSink) unavailable")
    with tempfile.TemporaryDirectory() as d:
        layout, spec_path = _build_run(d, n_cands=10, executor_status=StageStatus.SUCCEEDED, sharded=True)
        shard = sorted((layout.root / "src").glob("*.fwshard"))[-1]
        with open(shard, "r+b") as f:                  # chop into the finalize trailer
            f.truncate(f.seek(0, 2) - 6)
        ran = []
        hs = layout.root / "handshake"
        reader_kwargs = {}

        def fake_reader(*_a, **_k):
            ran.append("reader")
            reader_kwargs.update(_k)
            return layout.root / "src", hs, 12, 0, hs / "handoff" / "manifest.json"

        def fake_executor(*_a, **_k):
            ran.append("executor")
            _emit_executor_summary(_k, processed=12)
            return (12, 12, 0, 0, 12, 12, 0, 0,
                    {"attempted": 12, "inserted": 12, "already_present": 0, "updated_selected": 0})

        with patch.object(cli, "_load_one_spec", lambda spec_dir: (_FAKE_SPEC, spec_path)), \
             patch.object(cli.fg, "estimate_core_combos", lambda spec: 1), \
             patch.object(orch, "psql", _resume_psql), \
             patch.object(orch, "stage_gen", side_effect=AssertionError("gen must be reused")), \
             patch.object(orch, "stage_core", side_effect=AssertionError("core must be reused")), \
             patch.object(orch, "stage_reader", side_effect=fake_reader), \
             patch.object(orch, "_record_handoff_manifest", lambda rec, *_a, **_k: object()), \
             patch.object(orch, "stage_executor", side_effect=fake_executor):
            cli.cmd_resume(_BLANK_ARGS(layout.root))

        assert ran == ["reader", "executor"], f"a corrupt shard must rerun reader+executor, got {ran}"
        # the Reader rerun must be in resume mode (upstream trusted + sharded), so the ShardSink
        # reuses the surviving valid shards instead of rebuilding the whole corpus.
        assert reader_kwargs.get("resume") is True, f"sharded rerun must pass resume=True, got {reader_kwargs}"


def test_resume_reruns_executor_when_results_v2_rows_are_missing():
    with tempfile.TemporaryDirectory() as d:
        layout, spec_path = _build_run(d, n_cands=3, executor_status=StageStatus.SUCCEEDED)
        ran = []
        sql_seen = []

        def fake_psql(_port, _db, sql, **_kw):
            sql_seen.append(sql)
            # Phase 3b verdict count (DISTINCT ON the 5-col sample key) returns 0 == no verdicts
            # landed -> the resume must NOT trust prior results and reruns the executor.
            if "distinct on (candidate_id, repeat_idx, env_id)" in sql:
                return "0", 0
            if "coalesce(max(attempt),0)" in sql:
                return "1", 0
            if "truncate table" in sql:
                return "", 0
            return "12", 0

        def fake_executor(*_a, **_k):
            ran.append("executor")
            assert _k["attempt"] == 2
            _emit_executor_summary(_k, processed=3)
            return (3, 3, 0, 0, 3, 3, 0, 0,
                    {"attempted": 3, "inserted": 3, "already_present": 0, "updated_selected": 0})

        with patch.object(cli, "_load_one_spec", lambda spec_dir: (_FAKE_SPEC, spec_path)), \
             patch.object(orch, "psql", fake_psql), \
             patch.object(orch, "stage_gen", side_effect=AssertionError("gen must be reused")), \
             patch.object(orch, "stage_core", side_effect=AssertionError("core must be reused")), \
             patch.object(orch, "stage_reader", side_effect=AssertionError("reader must be reused")), \
             patch.object(orch, "stage_executor", side_effect=fake_executor):
            cli.cmd_resume(_BLANK_ARGS(layout.root))

        assert ran == ["executor"]
        assert any("truncate table" in sql for sql in sql_seen), sql_seen


def test_resume_of_an_already_succeeded_run_reuses_everything_and_stays_idempotent():
    """Milestone B: 'Resume completed run: stages не должны повториться.'"""
    with tempfile.TemporaryDirectory() as d:
        layout, spec_path = _build_run(d, n_cands=3, executor_status=StageStatus.SUCCEEDED)
        manifest = run_manifest_from_dict(read_json(layout.manifest_path))
        write_json_atomic(layout.manifest_path, dataclasses.replace(manifest, status=RunStatus.SUCCEEDED))
        write_json_atomic(layout.state_path, {**read_json(layout.state_path), "status": "SUCCEEDED"})

        with patch.object(cli, "_load_one_spec", lambda spec_dir: (_FAKE_SPEC, spec_path)), \
             patch.object(orch, "psql", _resume_psql), \
             patch.object(orch, "stage_gen", side_effect=AssertionError("nothing should rerun")), \
             patch.object(orch, "stage_core", side_effect=AssertionError("nothing should rerun")), \
             patch.object(orch, "stage_reader", side_effect=AssertionError("nothing should rerun")), \
             patch.object(orch, "stage_executor", side_effect=AssertionError("nothing should rerun")):
            cli.cmd_resume(_BLANK_ARGS(layout.root))
            cli.cmd_resume(_BLANK_ARGS(layout.root))

        state = read_json(layout.state_path)
        assert state["status"] == "SUCCEEDED"
        for name in ("gen", "core", "reader", "executor"):
            assert state["stages"][name]["status"] == "SKIPPED", state["stages"][name]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\nALL {len(fns)} TESTS PASSED")
