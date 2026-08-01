from __future__ import annotations

import calendar
import dataclasses
import os
import signal
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence

from .jsonio import read_json, write_json_atomic
from .models import (
    RUN_SCHEMA,
    RunStatus,
    STAGE_RESULT_SCHEMA,
    StageResult,
    StageStatus,
    run_manifest_from_dict,
)
from .resume import read_stage
from .runs import RunLayout

# Versioned like every other on-disk record (STEP 3) -- a registry entry is
# only ever read back by the same codebase that wrote it (no cross-process/
# cross-language consumer), but "no schema" has bitten this plan before.
PROCESS_REGISTRY_SCHEMA = "bundle.processes/v1"
CANCEL_REQUEST_SCHEMA = "bundle.cancel-request/v1"

CANCEL_NOTE = "cancelled by operator (bundle cancel)"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _parse_ts(ts: "str | None") -> "Optional[float]":
    if not ts:
        return None
    try:
        return float(calendar.timegm(time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")))
    except (TypeError, ValueError):
        return None


def _duration(start: "str | None", end: "str | None") -> "Optional[float]":
    s, e = _parse_ts(start), _parse_ts(end)
    return None if (s is None or e is None) else max(0.0, e - s)


# ------------------------------ /proc identity ------------------------------ #
def _proc_alive(pid: int) -> bool:
    """``True`` iff *pid* currently names a live process (owned or not).

    ``os.kill(pid, 0)`` sends no signal -- it only probes existence/visibility.
    A ``PermissionError`` still means "alive, just not ours to signal".
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _proc_start_ticks(pid: int) -> "Optional[int]":
    """Read /proc/<pid>/stat's ``starttime`` (jiffies since boot, field 22).

    This -- not the bare PID -- is what makes a recorded process identity
    durable: PIDs are recycled by the kernel, so "PID 12345 is still alive"
    can mean "an unrelated process now has PID 12345". Recording the start
    time at registration and re-checking it before signalling is the only way
    to fail closed on that ("does not kill unrelated processes", action 1/3 +
    "Unrelated process/DB не затрагиваются"). The comm field (2nd) may itself
    contain spaces/parens/`)`, hence the `rsplit(")", 1)` rather than a naive
    `split()`.
    """
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="ascii", errors="replace")
    except OSError:
        return None
    try:
        rest = raw.rsplit(")", 1)[1].split()
        return int(rest[19])  # state(0) ppid(1) ... starttime is field 22 -> index 19 here
    except (IndexError, ValueError):
        return None


def _wait_for_exit(pids: Sequence[int], timeout: float) -> "set[int]":
    """Poll until every pid in *pids* has exited or *timeout* elapses.

    Returns whichever pids are still alive when it gives up.
    """
    alive = {p for p in pids if _proc_alive(p)}
    deadline = time.monotonic() + timeout
    while alive and time.monotonic() < deadline:
        time.sleep(0.2)
        alive = {p for p in alive if _proc_alive(p)}
    return alive


# ------------------------------ process registry ---------------------------- #
def _registry_path(root: "Path | str") -> Path:
    return Path(root) / "processes.json"


def _read_registry(root: "Path | str") -> dict:
    try:
        data = dict(read_json(_registry_path(root)))
    except FileNotFoundError:
        return {"schema": PROCESS_REGISTRY_SCHEMA, "entries": []}
    data.setdefault("entries", [])
    return data


def _write_registry(root: "Path | str", entries: Sequence[dict]) -> None:
    write_json_atomic(_registry_path(root), {"schema": PROCESS_REGISTRY_SCHEMA, "entries": list(entries)})


def _argv_of(popen) -> tuple:
    args = getattr(popen, "args", ())
    return tuple(str(a) for a in args) if isinstance(args, (list, tuple)) else (str(args),)


def record_process(root: "Path | str", stage: str, popen) -> None:
    """Record one long-lived owned subprocess (e.g. the Reader JVM) so a
    *separate* ``bundle cancel`` invocation can find, identity-check, and
    terminate it later -- "owned child processes" only exist as a concept
    across process boundaries if something durable names them. Idempotent:
    re-recording the same pid replaces its entry rather than duplicating it.
    """
    pid = popen.pid
    entry = {
        "pid": pid,
        "stage": stage,
        "argv": list(_argv_of(popen)),
        "start_ticks": _proc_start_ticks(pid),
        "recorded_at": _now(),
    }
    data = _read_registry(root)
    entries = [e for e in data["entries"] if int(e.get("pid", -1)) != pid]
    entries.append(entry)
    _write_registry(root, entries)


def forget_process(root: "Path | str", pid: int) -> None:
    """Drop a registry entry once its process has exited normally.

    A no-op if the registry (or the entry) is already gone -- the launcher
    calls this from a ``finally``, and a half-finished/legacy run may have no
    registry file at all.
    """
    data = _read_registry(root)
    entries = [e for e in data["entries"] if int(e.get("pid", -1)) != pid]
    if len(entries) != len(data["entries"]):
        _write_registry(root, entries)


@dataclass(frozen=True)
class OwnedProcess:
    pid: int
    stage: str
    argv: tuple
    start_ticks: "Optional[int]"
    recorded_at: "Optional[str]"


def list_owned_processes(layout: RunLayout) -> List[OwnedProcess]:
    return [OwnedProcess(pid=int(e["pid"]), stage=e.get("stage", ""),
                         argv=tuple(e.get("argv", ())), start_ticks=e.get("start_ticks"),
                         recorded_at=e.get("recorded_at"))
            for e in _read_registry(layout.root).get("entries", [])]


# --------------------------------- termination ------------------------------- #
@dataclass(frozen=True)
class TerminationOutcome:
    pid: int
    stage: str
    argv: tuple
    action: str  # see _ACTIONS below

    # already_exited     -- the process was gone before we could signal it
    # skipped_pid_reused -- alive, but /proc start-time no longer matches: an
    #                       unrelated process now has this pid -- never signalled
    # permission_denied  -- alive and identity-matched, but we may not signal it
    # terminated         -- SIGTERM (or SIGKILL escalation) succeeded
    # still_alive        -- survived SIGTERM *and* SIGKILL (e.g. D-state/zombie)


_ACTIONS = ("already_exited", "skipped_pid_reused", "permission_denied", "terminated", "still_alive")


def _terminate_owned(layout: RunLayout, *, grace_seconds: float, kill_wait_seconds: float
                      ) -> List[TerminationOutcome]:
    """Identity-check, then SIGTERM->(grace)->SIGKILL every registry entry.

    Two independent fail-closed checks gate any `os.kill`: the process must
    still be alive, AND its `/proc` start-time must match what was recorded at
    registration -- otherwise the pid has been recycled and signalling it would
    hit an unrelated process (exactly what action 1's "does not kill unrelated
    processes" / "Unrelated process ... не затрагиваются" forbid). Registry
    entries are forgotten once resolved either way, so a second `cancel` on an
    already-cancelled run sees an empty registry and does nothing.
    """
    entries = _read_registry(layout.root).get("entries", [])
    resolved: dict = {}
    pending: List[OwnedProcess] = []
    for e in entries:
        proc = OwnedProcess(pid=int(e["pid"]), stage=e.get("stage", ""),
                            argv=tuple(e.get("argv", ())), start_ticks=e.get("start_ticks"),
                            recorded_at=e.get("recorded_at"))
        if not _proc_alive(proc.pid):
            resolved[proc.pid] = TerminationOutcome(proc.pid, proc.stage, proc.argv, "already_exited")
            continue
        current_ticks = _proc_start_ticks(proc.pid)
        if proc.start_ticks is None or current_ticks is None or current_ticks != proc.start_ticks:
            resolved[proc.pid] = TerminationOutcome(proc.pid, proc.stage, proc.argv, "skipped_pid_reused")
            continue
        try:
            os.kill(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            resolved[proc.pid] = TerminationOutcome(proc.pid, proc.stage, proc.argv, "already_exited")
            continue
        except PermissionError:
            resolved[proc.pid] = TerminationOutcome(proc.pid, proc.stage, proc.argv, "permission_denied")
            continue
        pending.append(proc)

    still_alive = _wait_for_exit([p.pid for p in pending], grace_seconds)
    for proc in pending:
        if proc.pid in still_alive:
            try:
                os.kill(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
    still_alive = _wait_for_exit(list(still_alive), kill_wait_seconds) if still_alive else set()
    for proc in pending:
        resolved[proc.pid] = TerminationOutcome(
            proc.pid, proc.stage, proc.argv, "still_alive" if proc.pid in still_alive else "terminated")

    outcomes = [resolved[int(e["pid"])] for e in entries if int(e["pid"]) in resolved]
    for outcome in outcomes:
        forget_process(layout.root, outcome.pid)
    return outcomes


# --------------------------------- intent marker ----------------------------- #
def _cancel_request_path(layout: RunLayout) -> Path:
    return layout.root / "cancel_request.json"


def _write_cancel_request(layout: RunLayout, requested_at: str) -> None:
    """Persist "an operator asked to cancel this run" *before* anything is
    signalled -- action 1's "marks intent" must survive even if the process
    issuing `bundle cancel` is itself interrupted mid-way (e.g. Ctrl-C right
    after this write): the next invocation can see a cancel was already
    requested rather than starting a fresh, possibly-conflicting one.
    """
    write_json_atomic(_cancel_request_path(layout), {
        "schema": CANCEL_REQUEST_SCHEMA, "run_id": layout.run_id, "requested_at": requested_at,
    })


def cancel_requested(layout: RunLayout) -> "Optional[str]":
    """Return the recorded `requested_at` timestamp, or ``None`` if no cancel
    has been requested for this run yet."""
    try:
        return dict(read_json(_cancel_request_path(layout))).get("requested_at")
    except FileNotFoundError:
        return None


# ------------------------------ status rewrite -------------------------------- #
def _mark_cancelled(layout: RunLayout, *, at: str) -> None:
    """Out-of-band terminal rewrite of every still-RUNNING stage plus the run
    itself to CANCELLED (action 1's "sets run/stage status").

    This intentionally bypasses `RunJournal` -- that class assumes it is the
    *only* writer of a live run's state (its constructor loads, its methods
    mutate-and-rewrite the same in-memory copy), which is exactly backwards
    for a tool whose entire point is to act on a run from a second process
    while the first might still be limping along. Instead this re-reads
    the authoritative on-disk `StageResult`/state/manifest fresh, replaces
    only the terminal fields (status/end/duration/errors), and preserves
    every count/warning/artifact/invariant the stage had already recorded --
    a CANCELLED stage's prior evidence remains inspectable, exactly like an
    INTERRUPTED one.
    """
    try:
        state = dict(read_json(layout.state_path))
    except FileNotFoundError:
        return
    state.setdefault("stages", {})
    for name, info in list(state["stages"].items()):
        if info.get("status") != StageStatus.RUNNING.value:
            continue
        prior = read_stage(layout, name)
        start = (prior.start if prior else info.get("start")) or at
        cancelled = StageResult(
            schema=STAGE_RESULT_SCHEMA, stage=name, status=StageStatus.CANCELLED,
            start=start, end=at, duration_seconds=_duration(start, at),
            exit_code=(prior.exit_code if prior else None),
            log_path=(prior.log_path if prior else None),
            counts=(prior.counts if prior else ()),
            warnings=(prior.warnings if prior else ()),
            errors=(*(prior.errors if prior else ()), CANCEL_NOTE),
            artifacts=(prior.artifacts if prior else ()),
            invariants=(prior.invariants if prior else ()),
        )
        write_json_atomic(layout.stages_dir / f"{name}.json", cancelled)
        state["stages"][name] = {"status": StageStatus.CANCELLED.value, "start": start, "end": at,
                                 "duration_seconds": cancelled.duration_seconds}
    state["status"] = RunStatus.CANCELLED.value
    state.setdefault("schema", RUN_SCHEMA)
    state.setdefault("run_id", layout.run_id)
    write_json_atomic(layout.state_path, state)
    try:
        manifest = run_manifest_from_dict(read_json(layout.manifest_path))
    except FileNotFoundError:
        return
    write_json_atomic(layout.manifest_path, dataclasses.replace(manifest, status=RunStatus.CANCELLED))


# ---------------------------------- orchestration ---------------------------- #
@dataclass(frozen=True)
class CancelReport:
    run_id: str
    requested_at: str
    outcomes: tuple
    final_status: str = field(default=RunStatus.CANCELLED.value)


def cancel_run(layout: RunLayout, *, grace_seconds: float = 5.0, kill_wait_seconds: float = 2.0) -> CancelReport:
    """Cancel *layout*'s run end to end (action 1):

    1. mark intent (durable, written first -- survives a crash mid-cancel);
    2. terminate every owned process whose identity still checks out, leaving
       anything else (including pid-recycled "impostors") strictly alone;
    3. rewrite the run and its still-RUNNING stage(s) to CANCELLED, out of
       band, since the original launcher process -- now terminated -- can
       never write its own terminal status.

    Idempotent: cancelling an already-cancelled run re-marks intent (a no-op
    status-wise), finds an empty/already-resolved registry, and rewrites
    nothing (no stage is RUNNING any more).
    """
    requested_at = cancel_requested(layout) or _now()
    _write_cancel_request(layout, requested_at)
    outcomes = _terminate_owned(layout, grace_seconds=grace_seconds, kill_wait_seconds=kill_wait_seconds)
    _mark_cancelled(layout, at=_now())
    return CancelReport(run_id=layout.run_id, requested_at=requested_at, outcomes=tuple(outcomes))
