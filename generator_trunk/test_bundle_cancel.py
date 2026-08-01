#!/usr/bin/env python3
"""Targeted tests for `bundle cancel` (STEP 25): the owned-process registry,
identity-verified termination (an unrelated process must never be touched,
even if it recycles a recorded pid), and the out-of-band run/stage status
rewrite to CANCELLED (run: `python3 -m pytest test_bundle_cancel.py -q`)."""
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

from bundle.cancel import (
    cancel_requested,
    cancel_run,
    forget_process,
    list_owned_processes,
    record_process,
    _proc_alive,
    _proc_start_ticks,
)
from bundle.jsonio import read_json, write_json_atomic
from bundle.journal import RunJournal
from bundle.models import (
    RUN_SCHEMA,
    RunManifest,
    RunStatus,
    STAGE_RESULT_SCHEMA,
    StageResult,
    StageStatus,
)
from bundle.runs import RunLayout


def _build_run(d, *, run_id="demo-run", running_stage="reader"):
    root = Path(d) / "scratch" / "demo" / "runs" / run_id
    for sub in ("stages", "logs", "workbooks", "candidates", "handoff", "metrics", "reports"):
        (root / sub).mkdir(parents=True)
    layout = RunLayout(run_id=run_id, root=root, manifest_path=root / "run.json", state_path=root / "state.json")

    manifest = RunManifest(
        schema=RUN_SCHEMA, run_id=run_id, status=RunStatus.RUNNING, db_name="demo",
        spec_path=str(Path(d) / "spec.toml"), spec_sha256="x" * 64, spec_version="v1",
        mode="verdict", goals="", start="2026-06-08T00:00:00Z",
        scratch_root=str(Path(d) / "scratch" / "demo"), settings={})
    write_json_atomic(layout.manifest_path, manifest)

    write_json_atomic(layout.stages_dir / "gen.json", StageResult(
        schema=STAGE_RESULT_SCHEMA, stage="gen", status=StageStatus.SUCCEEDED,
        start="2026-06-08T00:00:00Z", end="2026-06-08T00:00:01Z", duration_seconds=1.0))
    write_json_atomic(layout.stages_dir / f"{running_stage}.json", StageResult(
        schema=STAGE_RESULT_SCHEMA, stage=running_stage, status=StageStatus.RUNNING,
        start="2026-06-08T00:01:00Z", counts=(), warnings=("heads up",)))
    write_json_atomic(layout.state_path, {
        "schema": RUN_SCHEMA, "run_id": run_id, "status": RunStatus.RUNNING.value,
        "stages": {
            "gen": {"status": StageStatus.SUCCEEDED.value, "start": "2026-06-08T00:00:00Z",
                    "end": "2026-06-08T00:00:01Z", "duration_seconds": 1.0},
            running_stage: {"status": StageStatus.RUNNING.value, "start": "2026-06-08T00:01:00Z",
                            "end": None, "duration_seconds": None},
        },
    })
    return layout


def _spawn_sleep(seconds=60):
    """Spawn `sleep` and reap it the moment it exits (a background `wait()`,
    exactly like the launcher's own `proc.wait(timeout=...)` on the Reader
    Popen) -- otherwise a SIGTERM'd child sits as a zombie that `os.kill(pid,
    0)` still reports as "alive" until its parent (this test process) reaps
    it, which would make `_proc_alive` lie about whether `cancel` worked."""
    p = subprocess.Popen(["sleep", str(seconds)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    threading.Thread(target=p.wait, daemon=True).start()
    return p


def _wait_gone(pid, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _proc_alive(pid):
            return True
        time.sleep(0.1)
    return False


# --------------------------------- registry ---------------------------------- #
def test_record_and_forget_process_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        layout = _build_run(d)
        owned = _spawn_sleep()
        try:
            record_process(layout.root, "reader", owned)
            entries = list_owned_processes(layout)
            assert len(entries) == 1
            assert entries[0].pid == owned.pid
            assert entries[0].stage == "reader"
            assert entries[0].start_ticks == _proc_start_ticks(owned.pid)

            # Re-recording the same pid replaces, never duplicates, its entry.
            record_process(layout.root, "reader", owned)
            assert len(list_owned_processes(layout)) == 1

            forget_process(layout.root, owned.pid)
            assert list_owned_processes(layout) == []
            # Forgetting an absent entry is a no-op, not an error.
            forget_process(layout.root, owned.pid)
        finally:
            owned.kill()


# ------------------------------- cancellation --------------------------------- #
def test_cancel_terminates_owned_sleep_but_not_unrelated_process():
    with tempfile.TemporaryDirectory() as d:
        layout = _build_run(d)
        owned = _spawn_sleep()
        unrelated = _spawn_sleep()
        try:
            record_process(layout.root, "reader", owned)
            # `unrelated` is a real, currently-alive process that just never
            # got recorded -- the minimal "one owned sleep child cancellation"
            # check from the execution plan, plus its mirror image: an
            # unrecorded process must survive `cancel` untouched.
            report = cancel_run(layout, grace_seconds=3.0, kill_wait_seconds=2.0)

            assert _wait_gone(owned.pid), "owned sleep child should have been terminated"
            assert _proc_alive(unrelated.pid), "unrelated process must not be touched"

            assert len(report.outcomes) == 1
            outcome = report.outcomes[0]
            assert outcome.pid == owned.pid
            assert outcome.stage == "reader"
            assert outcome.action == "terminated"
            assert report.final_status == RunStatus.CANCELLED.value

            # The registry is drained once every entry is resolved.
            assert list_owned_processes(layout) == []
            # Intent was marked durably (action 1: "marks intent").
            assert cancel_requested(layout) == report.requested_at

            state = read_json(layout.state_path)
            assert state["status"] == RunStatus.CANCELLED.value
            assert state["stages"]["reader"]["status"] == StageStatus.CANCELLED.value
            assert state["stages"]["gen"]["status"] == StageStatus.SUCCEEDED.value, \
                "a stage that had already finished must not be rewritten"

            manifest = read_json(layout.manifest_path)
            assert manifest["status"] == RunStatus.CANCELLED.value

            stage_doc = read_json(layout.stages_dir / "reader.json")
            assert stage_doc["status"] == StageStatus.CANCELLED.value
            assert stage_doc["start"] == "2026-06-08T00:01:00Z"
            assert stage_doc["end"] is not None
            assert stage_doc["warnings"] == ["heads up"], "prior recorded evidence must survive the rewrite"
            assert any("cancel" in e.lower() for e in stage_doc["errors"])
        finally:
            for proc in (owned, unrelated):
                if _proc_alive(proc.pid):
                    proc.kill()


def test_cancel_does_not_signal_a_process_whose_pid_was_recycled():
    with tempfile.TemporaryDirectory() as d:
        layout = _build_run(d)
        impostor = _spawn_sleep()
        try:
            record_process(layout.root, "reader", impostor)
            # Tamper with the just-written entry as if the *original* owned
            # process had since exited and the kernel handed its pid to
            # something else entirely -- the recorded start-time no longer
            # matches the (still alive) process now sitting at that pid.
            data = dict(read_json(layout.root / "processes.json"))
            data["entries"][0]["start_ticks"] = (data["entries"][0]["start_ticks"] or 0) + 999_999
            write_json_atomic(layout.root / "processes.json", data)

            report = cancel_run(layout, grace_seconds=1.0, kill_wait_seconds=0.5)

            assert len(report.outcomes) == 1
            assert report.outcomes[0].action == "skipped_pid_reused"
            assert _proc_alive(impostor.pid), "a pid-recycled process must be left running, not killed"
        finally:
            impostor.kill()


def test_cancel_reports_already_exited_entry_without_error():
    with tempfile.TemporaryDirectory() as d:
        layout = _build_run(d)
        gone = _spawn_sleep(seconds=1)
        record_process(layout.root, "reader", gone)
        assert _wait_gone(gone.pid, timeout=10)

        report = cancel_run(layout, grace_seconds=1.0, kill_wait_seconds=0.5)
        assert len(report.outcomes) == 1
        assert report.outcomes[0].action == "already_exited"
        assert report.final_status == RunStatus.CANCELLED.value


def test_cancel_is_idempotent():
    with tempfile.TemporaryDirectory() as d:
        layout = _build_run(d)
        owned = _spawn_sleep()
        try:
            record_process(layout.root, "reader", owned)
            first = cancel_run(layout, grace_seconds=3.0, kill_wait_seconds=2.0)
            assert _wait_gone(owned.pid)

            second = cancel_run(layout, grace_seconds=1.0, kill_wait_seconds=0.5)
            assert second.outcomes == ()
            assert second.requested_at == first.requested_at, \
                "re-cancelling must not stomp the original intent timestamp"
            assert second.final_status == RunStatus.CANCELLED.value

            state = read_json(layout.state_path)
            assert state["status"] == RunStatus.CANCELLED.value
        finally:
            if _proc_alive(owned.pid):
                owned.kill()


def test_cmd_cancel_skips_a_run_that_is_not_running():
    from bundle import cli
    with tempfile.TemporaryDirectory() as d:
        layout = _build_run(d)
        manifest = dict(read_json(layout.manifest_path))
        manifest["status"] = RunStatus.SUCCEEDED.value
        write_json_atomic(layout.manifest_path, manifest)
        from types import SimpleNamespace
        a = SimpleNamespace(run=str(layout.root), runs_root="", config_file="",
                            **{k: cli._UNSET for k in cli._CLI_ARG_TO_CONFIG_KEY})
        with patch.object(cli, "cancel_run") as fake_cancel:
            cli.cmd_cancel(a)
            fake_cancel.assert_not_called()


def test_live_journal_cannot_overwrite_external_cancellation():
    with tempfile.TemporaryDirectory() as d:
        layout = _build_run(d, running_stage="old")
        journal = RunJournal(layout)

        try:
            with journal.stage("reader"):
                cancel_run(layout, grace_seconds=0.0, kill_wait_seconds=0.0)
        except Exception as exc:
            assert "cancelled" in str(exc)
        else:
            assert False, "the launcher must stop after an external cancellation"

        assert read_json(layout.state_path)["status"] == RunStatus.CANCELLED.value
        assert read_json(layout.manifest_path)["status"] == RunStatus.CANCELLED.value
        assert read_json(layout.stages_dir / "reader.json")["status"] == StageStatus.CANCELLED.value
