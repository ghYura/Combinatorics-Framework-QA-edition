from __future__ import annotations

import hashlib
import re
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

from .errors import BundleError
from .jsonio import write_json_atomic
from .models import RUN_SCHEMA, RunManifest, RunStatus

# Filesystem- and shell-safe: ASCII letters/digits/._- only, alnum first char,
# bounded length — this string ends up as a directory name (and may end up
# adjacent to DB names / log paths), so no separators or whitespace allowed.
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")

# The run directory layout fixed by the execution plan. Subdirectories are
# created up front so later steps (stage journal, handoff v2, sinks, reports)
# have a stable place to write into — this step does not populate them yet.
_LAYOUT_DIRS = ("stages", "logs", "workbooks", "candidates", "handoff", "metrics", "reports")


class RunCollisionError(BundleError):
    """An existing run directory must not be silently reused or overwritten."""


@dataclass(frozen=True)
class RunLayout:
    run_id: str
    root: Path
    manifest_path: Path
    state_path: Path

    @property
    def stages_dir(self) -> Path:
        return self.root / "stages"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    @property
    def workbooks_dir(self) -> Path:
        return self.root / "workbooks"

    @property
    def candidates_dir(self) -> Path:
        return self.root / "candidates"

    @property
    def handoff_dir(self) -> Path:
        return self.root / "handoff"

    @property
    def metrics_dir(self) -> Path:
        return self.root / "metrics"

    @property
    def reports_dir(self) -> Path:
        return self.root / "reports"


def generate_run_id(requested: Optional[str] = None) -> str:
    """Validate a user-supplied run ID, or mint a deterministic-safe one.

    A user-provided ID must match ``_RUN_ID_RE`` (alnum start, then
    letters/digits/``._-``, <=128 chars) — anything else is rejected up front
    rather than risking a malformed/escaping directory name. Otherwise mint
    ``<UTC timestamp>-<8 hex chars>``: monotonically sortable, collision-safe
    in practice, and still matches the same charset.
    """
    if requested:
        if not _RUN_ID_RE.match(requested):
            raise BundleError(f"invalid run ID {requested!r}: must match {_RUN_ID_RE.pattern!r}")
        return requested
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return f"{stamp}-{secrets.token_hex(4)}"


def file_sha256(path: "Path | str") -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _layout_for(runs_root: Path, run_id: str) -> RunLayout:
    root = runs_root / run_id
    return RunLayout(run_id=run_id, root=root, manifest_path=root / "run.json",
                     state_path=root / "state.json")


def create_run(*, runs_root: "Path | str", db_name: str, spec_path: "Path | str",
               spec_sha256: str, mode: str, goals: str, scratch_root: "Path | str",
               settings: Mapping[str, object], run_id: Optional[str] = None,
               spec_version: Optional[str] = None,
               analysis: Optional[Mapping[str, object]] = None,
               component_inventory: Optional[Mapping[str, object]] = None) -> RunLayout:
    """Create a fresh run directory with ``run.json``/``state.json`` before stage 1.

    Fails closed with :class:`RunCollisionError` if a directory for this run ID
    already exists — an existing run's identity and manifest are never reused
    or silently overwritten. ``settings`` is redacted by the atomic writer
    (see :mod:`bundle.jsonio`) before it ever reaches disk.
    """
    rid = generate_run_id(run_id)
    layout = _layout_for(Path(runs_root), rid)
    if layout.root.exists():
        raise RunCollisionError(f"run '{rid}' already exists at {layout.root}")
    layout.root.mkdir(parents=True)
    for name in _LAYOUT_DIRS:
        (layout.root / name).mkdir()
    manifest = RunManifest(
        schema=RUN_SCHEMA,
        run_id=rid,
        status=RunStatus.PENDING,
        db_name=db_name,
        spec_path=str(spec_path),
        spec_sha256=spec_sha256,
        spec_version=spec_version,
        mode=mode,
        goals=goals,
        start=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        scratch_root=str(scratch_root),
        settings=dict(settings),
        analysis=dict(analysis or {}),
        component_inventory=dict(component_inventory or {}),
    )
    write_json_atomic(layout.manifest_path, manifest)
    write_json_atomic(layout.state_path, {
        "schema": RUN_SCHEMA, "run_id": rid, "status": RunStatus.PENDING.value, "stages": {},
    })
    return layout
