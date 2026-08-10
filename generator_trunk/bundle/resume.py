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

import hashlib
from pathlib import Path
from typing import Optional, Sequence

from .errors import BundleError
from .jsonio import read_json
from .models import ArtifactRef, InvariantSeverity, StageResult, StageStatus, stage_result_from_dict
from .runs import file_sha256, RunLayout

# Fixed pipeline order (STEP 24 acts on the same five/six stages `_run` already
# journals) -- a stage can only be trusted if every stage before it in this
# order was itself trusted; nothing here is a generic graph, because Bundle's
# stage sequence isn't one.
STAGE_ORDER = ("gen", "core", "sieve", "reader", "executor", "analyzer")


class ResumeError(BundleError):
    """A run cannot be safely resumed as-is (crash mid-stage, unsupported mode, missing run, ...)."""


def file_artifact(kind: str, path: "Path | str") -> ArtifactRef:
    p = Path(path)
    if not p.is_file():
        return ArtifactRef(kind=kind, path=str(p), bytes=None, sha256=None)
    try:
        return ArtifactRef(kind=kind, path=str(p), bytes=p.stat().st_size, sha256=file_sha256(p))
    except OSError:
        return ArtifactRef(kind=kind, path=str(p), bytes=None, sha256=None)


def dir_artifact(kind: str, path: "Path | str", pattern: str = "*") -> ArtifactRef:
    root = Path(path)
    h = hashlib.sha256()
    total = 0
    if not root.is_dir():
        return ArtifactRef(kind=kind, path=str(root), bytes=None, sha256=None)
    try:
        files = sorted(p for p in root.rglob(pattern) if p.is_file())
        for f in files:
            rel = f.relative_to(root).as_posix()
            digest = file_sha256(f)
            size = f.stat().st_size
            total += size
            h.update(rel.encode("utf-8") + b"\0" + str(size).encode("ascii")
                     + b"\0" + digest.encode("ascii") + b"\n")
    except OSError:
        return ArtifactRef(kind=kind, path=str(root), bytes=None, sha256=None)
    return ArtifactRef(kind=kind, path=str(root), bytes=total, sha256=h.hexdigest())

def artifact_by_kind(result: "Optional[StageResult]", kind: str) -> "Optional[ArtifactRef]":
    if result is None:
        return None
    for artifact in result.artifacts:
        if artifact.kind == kind:
            return artifact
    return None


def artifact_matches(result: "Optional[StageResult]", current: ArtifactRef) -> bool:
    prior = artifact_by_kind(result, current.kind)
    return (prior is not None and prior.sha256 is not None and current.sha256 is not None
            and prior.sha256 == current.sha256 and prior.bytes == current.bytes)


def artifacts_match(result: "Optional[StageResult]", current: Sequence[ArtifactRef]) -> bool:
    return all(artifact_matches(result, artifact) for artifact in current)


def layout_from_dir(root: "Path | str") -> RunLayout:
    root = Path(root)
    return RunLayout(run_id=root.name, root=root, manifest_path=root / "run.json", state_path=root / "state.json")


def resolve_run_layout(ref: str, *, runs_root: "str | None" = None,
                       scratch_root: "str | None" = None) -> RunLayout:
    """Accept either a run directory path or a bare run ID (STEP 24: ``bundle
    resume <run-dir|run-id>``).

    A path is recognised by the presence of ``run.json`` directly inside it.
    Otherwise *ref* is treated as a run ID and looked up under ``runs_root``
    (if given) and under ``<scratch_root or /tmp/fw_work>/*/runs/<ref>`` --
    the default layout `_create_run_directory` uses. Fails closed (never
    guesses) if the ID resolves to zero or more than one directory.
    """
    direct = Path(ref)
    if (direct / "run.json").is_file():
        return layout_from_dir(direct)
    candidates = []
    if runs_root:
        candidates.append(Path(runs_root) / ref)
    base = Path(scratch_root or "/tmp/fw_work")
    candidates.extend(sorted(base.glob(f"*/runs/{ref}")))
    found = [c for c in candidates if (c / "run.json").is_file()]
    if not found:
        raise ResumeError(
            f"could not locate run {ref!r} -- looked for a run directory at that path, "
            f"then for a run ID under {(runs_root + ' and ') if runs_root else ''}"
            f"{base}/*/runs/ (pass the full run directory path, or --runs-root, if it lives elsewhere)")
    if len(found) > 1:
        raise ResumeError(
            f"run ID {ref!r} is ambiguous -- found at: {', '.join(str(f) for f in found)} "
            f"(pass the full run directory path instead)")
    return layout_from_dir(found[0])


def reconcile_interrupted(layout: RunLayout) -> None:
    """Refuse to resume a run with a stage still marked RUNNING (action 4).

    A RUNNING record with no terminal transition means the process died
    mid-stage (e.g. ``kill -9``, host crash) -- its on-disk/DB outputs are of
    unknown completeness (a half-written candidate directory? a partially
    filled ``fw_final``?). Bundle does not attempt to guess; it fails closed
    and tells the operator what to inspect, exactly as the action requires
    ("без reconciliation").
    """
    state = read_json(layout.state_path)
    running = sorted(name for name, s in state.get("stages", {}).items()
                     if s.get("status") == StageStatus.RUNNING.value)
    if running:
        raise ResumeError(
            f"run '{layout.run_id}' has stage(s) still marked RUNNING -- the process that ran "
            f"them appears to have crashed without recording a terminal status: {', '.join(running)}. "
            f"Their outputs cannot be trusted without manual reconciliation: inspect "
            f"{layout.stages_dir}/<stage>.json and its log, then either fix up state.json by hand "
            f"once you've confirmed the artifacts are intact, or start a fresh run.")


def read_stage(layout: RunLayout, name: str) -> "Optional[StageResult]":
    try:
        return stage_result_from_dict(read_json(layout.stages_dir / f"{name}.json"))
    except FileNotFoundError:
        return None


def critical_invariants_ok(result: "Optional[StageResult]") -> bool:
    if result is None:
        return False
    return all(inv.passed for inv in result.invariants if inv.severity == InvariantSeverity.CRITICAL)


def count_actual(result: "Optional[StageResult]", name: str):
    if result is None:
        return None
    for c in result.counts:
        if c.name == name:
            return c.actual
    return None


def succeeded_with_invariants(result: "Optional[StageResult]") -> bool:
    return result is not None and result.status == StageStatus.SUCCEEDED and critical_invariants_ok(result)
