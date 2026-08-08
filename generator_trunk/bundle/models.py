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

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

# Schema identifiers are versioned as "<name>/v<major>" — only the major part
# is meaningful for compatibility (no minor/patch granularity yet). A reader
# must reject any value whose name or major differs from what it expects.
RUN_SCHEMA = "bundle.run/v1"
STAGE_RESULT_SCHEMA = "bundle.stage-result/v1"

_SCHEMA_RE = re.compile(r"^(?P<name>[a-z0-9_.\-]+)/v(?P<major>\d+)$")


class SchemaError(ValueError):
    """Raised when a JSON document carries an unknown/incompatible schema version."""


def _parse_schema(value: str):
    m = _SCHEMA_RE.match(value or "")
    if not m:
        raise SchemaError(f"malformed schema identifier: {value!r}")
    return m.group("name"), int(m.group("major"))


def require_schema(value: str, expected: str) -> str:
    """Fail closed unless *value* names the same schema and major version as *expected*."""
    name, major = _parse_schema(value)
    exp_name, exp_major = _parse_schema(expected)
    if name != exp_name or major != exp_major:
        raise SchemaError(f"unsupported schema {value!r} (expected {expected!r})")
    return value


# ------------------------------------ enums ---------------------------------- #
class RunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"
    # STEP 25: an *intentional*, operator-requested stop -- distinct from
    # INTERRUPTED (process death/Ctrl-C with no clear intent behind it). Set
    # out-of-band by `bundle cancel` once it has terminated every owned
    # process it could verify, never by the in-process journal.
    CANCELLED = "CANCELLED"


class StageStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"
    SKIPPED = "SKIPPED"
    # STEP 25: mirrors `RunStatus.CANCELLED` at stage granularity -- the stage
    # that was RUNNING when `bundle cancel` acted is rewritten to this status.
    CANCELLED = "CANCELLED"


class Outcome(str, Enum):
    """Canonical per-candidate outcome (STEP 21).

    Separates the DOMAIN verdict -- a property of the candidate under test --
    from INFRASTRUCTURE outcomes -- properties of the run/environment. Before
    this model existed, "broken" was overloaded to mean both "candidate failed
    its domain check" and "the Executor could not even produce a verdict",
    which hid timeouts and infrastructure errors inside an undifferentiated
    bucket. Mirrored by the standalone ``Outcome`` class in
    ``Executor_trunk/py_executor.py`` (which cannot import this package, see
    that module's ``_write_json_atomic``) and by the Java Executor's mapping.

    Mapping (Python/Java Executor):
      * no verdict marker / crashed before producing one -> BROKEN
      * exceeded the per-candidate timeout                -> TIMEOUT
      * subprocess/DB/compile infrastructure error         -> INFRA_FAIL
      * non-zero domain verdict                           -> DOMAIN_FAIL
      * zero domain verdict                               -> PASS
      * never attempted (resume/cancel paths, STEP 24/25) -> SKIPPED / CANCELLED

    The boolean ``status`` column in the Results DB remains a compatibility
    projection: ``True`` for PASS, ``False`` for DOMAIN_FAIL. BROKEN/TIMEOUT/
    INFRA_FAIL/SKIPPED/CANCELLED candidates are not domain verdicts and are
    counted separately, never folded into that boolean.
    """

    PASS = "PASS"
    DOMAIN_FAIL = "DOMAIN_FAIL"
    BROKEN = "BROKEN"
    TIMEOUT = "TIMEOUT"
    INFRA_FAIL = "INFRA_FAIL"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"


class InvariantSeverity(str, Enum):
    """How an invariant failure should be treated (STEP 6).

    CRITICAL failures fail the stage/run closed; WARNING failures are recorded
    for visibility but do not by themselves stop the run (e.g. a heuristic
    cross-check whose inputs aren't fully authoritative yet).
    """

    CRITICAL = "CRITICAL"
    WARNING = "WARNING"


# ---------------------------------- value types ------------------------------ #
@dataclass(frozen=True)
class ArtifactRef:
    kind: str
    path: str
    bytes: "int | None" = None
    sha256: "str | None" = None


@dataclass(frozen=True)
class CountObservation:
    name: str
    expected: "int | None" = None
    actual: "int | None" = None
    note: str = ""


@dataclass(frozen=True)
class InvariantResult:
    """One evaluated cross-stage invariant (STEP 6): ID, expected, actual, result, severity."""

    id: str
    description: str
    expected: Any
    actual: Any
    passed: bool
    severity: InvariantSeverity = InvariantSeverity.CRITICAL


@dataclass(frozen=True)
class StageResult:
    schema: str
    stage: str
    status: StageStatus
    start: "str | None" = None
    end: "str | None" = None
    duration_seconds: "float | None" = None
    exit_code: "int | None" = None
    log_path: "str | None" = None
    counts: Sequence[CountObservation] = field(default_factory=tuple)
    warnings: Sequence[str] = field(default_factory=tuple)
    errors: Sequence[str] = field(default_factory=tuple)
    artifacts: Sequence[ArtifactRef] = field(default_factory=tuple)
    invariants: Sequence[InvariantResult] = field(default_factory=tuple)


@dataclass(frozen=True)
class RunManifest:
    schema: str
    run_id: str
    status: RunStatus
    db_name: str
    spec_path: str
    spec_sha256: "str | None" = None
    spec_version: "str | None" = None
    mode: str = "verdict"
    goals: str = ""
    start: "str | None" = None
    scratch_root: "str | None" = None
    settings: Mapping[str, Any] = field(default_factory=dict)
    # STEP 38: the Analyzer's formal-vs-exploratory analysis contract for this run
    # — {mode, goals:[{key,dir,weight}], weights, normalization}. Recorded so a
    # formal Pareto study's objectives are auditable and never implicitly changed.
    analysis: Mapping[str, Any] = field(default_factory=dict)
    # STEP 42: the component version/hash inventory this run was produced with
    # (bundle.inventory/v1 — toolchain + per-component declared version + artifact
    # sha256). Recorded so a run is reproducible/traceable to exact build artifacts.
    component_inventory: Mapping[str, Any] = field(default_factory=dict)


# ------------------------------- JSON (de)serialization ---------------------- #
def to_dict(obj: Any) -> Any:
    """Recursively turn dataclasses/enums/paths/mappings into plain JSON-able values."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: to_dict(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, Mapping):
        return {str(k): to_dict(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_dict(v) for v in obj]
    return obj


def stage_result_from_dict(data: Mapping[str, Any]) -> StageResult:
    schema = require_schema(data.get("schema", ""), STAGE_RESULT_SCHEMA)
    return StageResult(
        schema=schema,
        stage=data["stage"],
        status=StageStatus(data["status"]),
        start=data.get("start"),
        end=data.get("end"),
        duration_seconds=data.get("duration_seconds"),
        exit_code=data.get("exit_code"),
        log_path=data.get("log_path"),
        counts=tuple(CountObservation(**c) for c in data.get("counts", ())),
        warnings=tuple(data.get("warnings", ())),
        errors=tuple(data.get("errors", ())),
        artifacts=tuple(ArtifactRef(**a) for a in data.get("artifacts", ())),
        invariants=tuple(
            InvariantResult(**{**i, "severity": InvariantSeverity(i["severity"])})
            for i in data.get("invariants", ())
        ),
    )


def run_manifest_from_dict(data: Mapping[str, Any]) -> RunManifest:
    schema = require_schema(data.get("schema", ""), RUN_SCHEMA)
    return RunManifest(
        schema=schema,
        run_id=data["run_id"],
        status=RunStatus(data["status"]),
        db_name=data["db_name"],
        spec_path=data["spec_path"],
        spec_sha256=data.get("spec_sha256"),
        spec_version=data.get("spec_version"),
        mode=data.get("mode", "verdict"),
        goals=data.get("goals", ""),
        start=data.get("start"),
        scratch_root=data.get("scratch_root"),
        settings=dict(data.get("settings", {})),
        analysis=dict(data.get("analysis", {})),
        component_inventory=dict(data.get("component_inventory", {})),
    )


def analysis_block(mode: str, goals_str: str, *, normalization: str = "none") -> dict:
    """STEP 38: the analysis contract recorded in the run manifest —
    ``{mode, goals:[{key,dir,weight}], weights, normalization}``. Parses the
    ``key:dir,...`` goals string AnalyzeKv consumes (bare ``key`` → ``min``), so
    the manifest's objectives are exactly what the Analyzer was driven with.
    Formal mode keeps the explicit directions verbatim (never inferred)."""
    goals: list = []
    for tok in (goals_str or "").split(","):
        tok = tok.strip()
        if not tok:
            continue
        if ":" in tok:
            key, raw_dir = tok.split(":", 1)
            key, d = key.strip(), raw_dir.strip().lower()
        else:
            key, d = tok, "min"
        direction = "max" if d.startswith("max") else "target" if d.startswith("target") else "min"
        goals.append({"key": key, "dir": direction, "weight": 1.0})
    return {
        "mode": mode,
        "goals": goals,
        "weights": {g["key"]: g["weight"] for g in goals},
        "normalization": normalization,
    }
