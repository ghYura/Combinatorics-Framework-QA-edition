from __future__ import annotations

import dataclasses
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List, Optional

from .jsonio import read_json, write_json_atomic
from .errors import BundleError
from .models import (
    RUN_SCHEMA,
    STAGE_RESULT_SCHEMA,
    ArtifactRef,
    CountObservation,
    InvariantResult,
    RunStatus,
    StageResult,
    StageStatus,
    run_manifest_from_dict,
)
from .runs import RunLayout


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class StageRecorder:
    """Mutable scratch a running stage can attach counts/warnings to (STEP 5).

    Stage bodies stay untouched; call sites in the launcher opt in to recording
    whichever input/output counts they already have to hand (e.g. Core's
    ``fw_final`` row count) without the stage functions themselves needing to
    know about the journal.
    """

    def __init__(self) -> None:
        self.counts: List[CountObservation] = []
        self.warnings: List[str] = []
        self.invariants: List[InvariantResult] = []
        self.artifacts: List[ArtifactRef] = []

    def count(self, name: str, *, actual: "int | None" = None,
              expected: "int | None" = None, note: str = "") -> None:
        self.counts.append(CountObservation(name=name, expected=expected, actual=actual, note=note))

    def warn(self, msg: str) -> None:
        self.warnings.append(str(msg))

    def invariant(self, result: InvariantResult) -> InvariantResult:
        """Record an evaluated :class:`InvariantResult` (STEP 6) and hand it back.

        Returning the result lets the caller pass it straight to
        :func:`bundle.invariants.enforce` without storing it twice.
        """
        self.invariants.append(result)
        return result

    def artifact(self, artifact: ArtifactRef) -> ArtifactRef:
        """Record an input/output/component fingerprint used by resume (STEP 24)."""
        self.artifacts.append(artifact)
        return artifact


class NullJournal:
    """No-op stand-in used for ``--legacy-scratch`` (no run directory to write into).

    Same surface as :class:`RunJournal` so the launcher can wrap every stage
    uniformly regardless of mode — legacy mode simply records nothing.
    """

    @contextmanager
    def stage(self, name: str, *, log_path=None) -> Iterator[StageRecorder]:
        yield StageRecorder()

    def mark_run(self, status: RunStatus) -> None:
        pass

    def skip_stage(self, name: str, *, note: str = "", carry_counts=()) -> None:
        pass


class RunJournal:
    """Per-run stage lifecycle journal: RUNNING -> SUCCEEDED/FAILED/INTERRUPTED.

    Each transition is written atomically both as ``stages/<name>.json`` (a
    versioned :class:`StageResult`) and mirrored into ``state.json`` — the
    machine-readable record the execution plan calls the "stage journal". A
    failed or interrupted stage always leaves the run non-``SUCCEEDED``, so a
    crashed run can never be mistaken for a clean one.
    """

    def __init__(self, layout: RunLayout) -> None:
        self.layout = layout
        try:
            self._state = dict(read_json(layout.state_path))
        except FileNotFoundError:
            self._state = {"schema": RUN_SCHEMA, "run_id": layout.run_id,
                           "status": RunStatus.PENDING.value, "stages": {}}
        self._state.setdefault("stages", {})
        # Track the run manifest too — mark_run() must keep run.json's own
        # `status` field in lockstep with state.json, otherwise the manifest
        # is stuck at PENDING forever even after a SUCCEEDED run (the defect
        # this constructor-side load fixes).
        self._manifest = run_manifest_from_dict(read_json(layout.manifest_path))

    # ------------------------------- persistence --------------------------- #
    def _write_state(self) -> None:
        write_json_atomic(self.layout.state_path, self._state)

    def _write_manifest(self) -> None:
        write_json_atomic(self.layout.manifest_path, self._manifest)

    def _write_stage(self, result: StageResult) -> None:
        write_json_atomic(self.layout.stages_dir / f"{result.stage}.json", result)
        self._state["stages"][result.stage] = {
            "status": result.status.value,
            "start": result.start,
            "end": result.end,
            "duration_seconds": result.duration_seconds,
        }
        self._write_state()

    def _cancel_requested(self) -> bool:
        try:
            request = dict(read_json(self.layout.root / "cancel_request.json"))
        except FileNotFoundError:
            return False
        return request.get("run_id") == self.layout.run_id

    def mark_run(self, status: RunStatus) -> None:
        self._state["status"] = status.value
        self._write_state()
        self._manifest = dataclasses.replace(self._manifest, status=status)
        self._write_manifest()

    # ------------------------------ resume (STEP 24) ----------------------- #
    def skip_stage(self, name: str, *, note: str = "", carry_counts=()) -> None:
        """Record a reused stage on resume without destroying its evidence.

        The canonical ``stages/<name>.json`` must remain the prior SUCCEEDED
        result, including its invariants and artifact fingerprints; otherwise a
        second no-op resume would see SKIPPED instead of SUCCEEDED and rerun the
        stage. The resume transition itself is written atomically to state.json.
        """
        now = _now()
        self._state["stages"][name] = {
            "status": StageStatus.SKIPPED.value,
            "start": now,
            "end": now,
            "duration_seconds": 0.0,
            "reused": True,
            "note": note,
        }
        self._state.setdefault("resume_history", []).append({
            "stage": name,
            "status": StageStatus.SKIPPED.value,
            "time": now,
            "note": note,
        })
        self._write_state()

    # ------------------------------ stage lifecycle ------------------------ #
    @contextmanager
    def stage(self, name: str, *, log_path: "Path | str | None" = None) -> Iterator[StageRecorder]:
        """Wrap one stage: write RUNNING, run the body, write the final status.

        On success -> SUCCEEDED. On :class:`KeyboardInterrupt` -> the stage and
        the run are both marked INTERRUPTED, then the interrupt is re-raised
        (the launcher decides how the process exits). On any other exception
        -> the stage and run are marked FAILED, the exception message is
        recorded, and the exception is re-raised unchanged so existing error
        reporting/exit semantics are preserved.
        """
        rec = StageRecorder()
        start = _now()
        t0 = time.monotonic()
        log = str(log_path) if log_path else None
        self._write_stage(StageResult(schema=STAGE_RESULT_SCHEMA, stage=name,
                                       status=StageStatus.RUNNING, start=start, log_path=log))

        def _finish(status: StageStatus, errors=()):
            self._write_stage(StageResult(
                schema=STAGE_RESULT_SCHEMA, stage=name, status=status,
                start=start, end=_now(), duration_seconds=time.monotonic() - t0,
                log_path=log, counts=tuple(rec.counts), warnings=tuple(rec.warnings),
                errors=tuple(errors), artifacts=tuple(rec.artifacts),
                invariants=tuple(rec.invariants)))

        try:
            yield rec
        except KeyboardInterrupt:
            if self._cancel_requested():
                raise BundleError(f"run {self.layout.run_id!r} was cancelled")
            _finish(StageStatus.INTERRUPTED)
            self.mark_run(RunStatus.INTERRUPTED)
            raise
        except BaseException as exc:
            if self._cancel_requested():
                raise BundleError(f"run {self.layout.run_id!r} was cancelled") from exc
            _finish(StageStatus.FAILED, errors=(str(exc),))
            self.mark_run(RunStatus.FAILED)
            raise
        else:
            if self._cancel_requested():
                raise BundleError(f"run {self.layout.run_id!r} was cancelled")
            _finish(StageStatus.SUCCEEDED)
