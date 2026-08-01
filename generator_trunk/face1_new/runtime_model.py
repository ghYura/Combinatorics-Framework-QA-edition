"""Planning and real Bundle-run integration for the Face 1 new workbook UI.

This module deliberately has no NiceGUI dependency.  It translates the current
``GridProject`` into metadata for the existing Bundle launcher while the worker
feeds the launcher's Core stage the *exact* workbook authored in the grid.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Iterable, Mapping

import fwgen as fg
from bundle import capabilities as capability_registry
from bundle.policy import PolicyError, authorize_execution
from bundle.resources import ResourceThresholds
from intake.scenario_library import (
    REPOSITORY_LAUNCH_PROFILES,
    load_scenarios,
    scenario_environment,
    scenario_run_config,
    scenario_spec_document,
)

from .grid_model import GridProject, GridRow


ROOT = Path(__file__).resolve().parents[1]
STAGE_ORDER = ("gen", "core", "seed_bias", "sieve", "reader", "executor", "analyzer")
ANALYZER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?::(?:min|max|target))?$")
BRACE_RE = re.compile(r"^FW_\(.*\)$", re.DOTALL)


@dataclass(frozen=True)
class PlanView:
    raw_values: dict[str, int]
    per_slot: dict[str, dict[str, Any]]
    mandatory: dict[str, Any]
    post_sieve: dict[str, Any]
    optional_multiplier: dict[str, Any]
    final: dict[str, Any]
    run_class: str
    issues: tuple[str, ...] = ()

    @property
    def final_text(self) -> str:
        return format_estimate(self.final)

    @property
    def mandatory_text(self) -> str:
        return format_estimate(self.mandatory)


@dataclass(frozen=True)
class RuntimeProblem:
    severity: str
    message: str


@dataclass(frozen=True)
class EngineCheck:
    ok: bool
    label: str
    detail: str


@dataclass(frozen=True)
class RunSnapshot:
    done: bool
    exit_code: int | None
    run_status: str
    stages: dict[str, dict[str, Any]]
    log: tuple[str, ...]
    results: dict[str, Any] | None
    run_dir: str


def default_run_config(project_name: str = "my_fw_sequence") -> dict[str, Any]:
    """Defaults mirror the old Face 1 control panel and Bundle CLI defaults."""
    return {
        "backend": "local",
        "db": slug_db(project_name, "task"),
        "runId": "r1",
        "lang": "py",
        "runMode": "verdict",
        "mode": "exploratory",
        "analyzer": "",
        # Audit F1: deliberately empty — the operator chooses, the launcher refuses
        # until they do. A pre-filled unsandboxed profile is a decision nobody made.
        "profile": "",
        "candidateOrigin": "",
        "trustedLocalAcknowledgement": "",
        "transport": "loose-files",
        "executorPool": 1,
        "iterations": 1,
        "sieve": False,
        "draw": False,
        "drawExact": False,
        "allowExtreme": False,
    }


def slug_id(value: str, default: str = "r1") -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]", "-", str(value or "").strip()).strip("-.") or default
    if not re.match(r"^[A-Za-z0-9]", value):
        value = "r-" + value
    return value[:120]


def slug_db(value: str, default: str = "task") -> str:
    value = re.sub(r"[^a-z0-9_]", "_", str(value or "").strip().lower()).strip("_") or default
    if value[0].isdigit():
        value = "d_" + value
    return value[:48]


def _row_lines(row: GridRow) -> list[str]:
    return [line.strip() for cell in row.directives for line in str(cell).splitlines() if line.strip()]


def _row_metadata(row: GridRow) -> tuple[str, tuple[str, ...], list[str], list[str]]:
    lines = _row_lines(row)
    flags = tuple(dict.fromkeys(line for line in lines if fg.is_core_flag(line)))
    braces = [line for line in lines if BRACE_RE.fullmatch(line)]
    verbs = [line for line in lines if fg.is_core_verb(line) and not BRACE_RE.fullmatch(line)]
    # Group is second-order and is the most honest representative when it shares
    # a row with a first-order generator.  Otherwise preserve the first actual verb.
    primary = next((line for line in verbs if line.startswith("FW_Group")), "")
    if not primary:
        primary = verbs[0] if verbs else fg.DEFAULT_VERB
    return primary, flags, braces, verbs


def project_spec(project: GridProject, analyzer: str = "") -> fg.Spec:
    """Build launcher metadata for an exact workbook.

    The Bundle uses this object for planning, Face-2 sheet/value labels and run
    provenance.  The worker bypasses fwgen output and supplies the authored XLSX
    unchanged, so this translation never rewrites or compacts directive cells.
    """
    slots: list[fg.Slot] = []
    seq_extra: list[list[str]] = []
    for row in project.sequence_rows:
        primary, flags, braces, _verbs = _row_metadata(row)
        slots.append(fg.Slot(
            sheet=row.target.strip(),
            key=re.sub(r"[^A-Za-z0-9_]", "_", row.target.strip()).lower() or "value",
            values=[str(value) for value in row.values],
            verb=primary,
            flags=flags,
            raw=True,
            prefix=row.prefix,
            ending=row.suffix,
        ))
        # Normal brace syntax is understood by fwgen's confidence planner.  Nested
        # FW_()/FW_()G variants are retained by the workbook but represented by an
        # explicit UNKNOWN issue in plan_project because the spec parser cannot model
        # those markers without rewriting them.
        for brace in braces:
            if fg.is_core_verb(brace):
                seq_extra.append([row.target.strip(), brace])
    goals = []
    for token in analyzer_tokens(analyzer):
        key, _, direction = token.partition(":")
        goals.append(fg.Goal(key, direction or fg.infer_direction(key)))
    custom_vars = []
    for code, message in project.custom_verdicts:
        try:
            custom_vars.append(fg.CustomVar(int(str(code).strip()), str(message)))
        except ValueError:
            continue
    return fg.Spec(
        name=slug_db(project.name, "task"),
        title=project.name or "Face 1 workbook",
        slots=slots,
        goals=goals,
        custom_vars=custom_vars,
        args=[str(value) for value in project.arguments] or ["noargs"],
        runme=project.run_once_source,
        seq_extra=seq_extra,
        spec_version="1",
    )


def _unknown(reason: str) -> dict[str, Any]:
    return {
        "mode": "UNKNOWN", "value": None, "lower": None, "upper": None,
        "formula": "requires the actual Core result tables", "reasons": [reason], "assumptions": [],
    }


def plan_project(project: GridProject, analyzer: str = "") -> PlanView:
    issues = tuple(issue.message for issue in project.validate())
    if not project.sequence_rows:
        unknown = _unknown("FW_Seq has no used rows")
        return PlanView({}, {}, unknown, unknown, {"mode": "EXACT", "value": 1, "lower": 1,
                        "upper": 1, "formula": "no optional rows", "reasons": [], "assumptions": []},
                        unknown, "X", issues)

    spec = project_spec(project, analyzer)
    raw_plan = fg.cardinality_plan_to_dict(fg.spec_cardinality_plan(spec))
    extra_unknown: list[str] = []
    for index, row in enumerate(project.sequence_rows, 1):
        _primary, _flags, braces, verbs = _row_metadata(row)
        nested = [brace for brace in braces if not fg.is_core_verb(brace)]
        if nested:
            extra_unknown.append(
                f"row {index} uses nested/grouped brace markers; its joined result-table size is known only after Core"
            )
        # Multiple algorithm verbs on one physical row are order-sensitive.  A
        # single representative verb must never be advertised as an exact plan.
        cardinality_verbs = [verb for verb in verbs if not verb.startswith("FW_Separator")]
        if len(cardinality_verbs) > 1:
            extra_unknown.append(
                f"row {index} contains {len(cardinality_verbs)} ordered algorithm verbs; their combined row count is runtime-dependent"
            )
    if extra_unknown:
        raw_plan["mandatory"] = _unknown("; ".join(extra_unknown))
        raw_plan["post_sieve"] = _unknown("mandatory count is unknown before Core")
        raw_plan["final"] = _unknown("post-sieve count is unknown; optional factor remains shown separately")
    final_count = raw_plan["final"].get("value") if raw_plan["final"].get("mode") != "UNKNOWN" else None
    run_class = ResourceThresholds().classify(final_count).value
    return PlanView(
        raw_values=raw_plan["raw_values"],
        per_slot=raw_plan["per_slot"],
        mandatory=raw_plan["mandatory"],
        post_sieve=raw_plan["post_sieve"],
        optional_multiplier=raw_plan["optional_multiplier"],
        final=raw_plan["final"],
        run_class=run_class,
        issues=issues,
    )


def format_estimate(estimate: dict[str, Any]) -> str:
    mode = str(estimate.get("mode") or "UNKNOWN")
    if mode == "EXACT":
        return f"{int(estimate.get('value') or 0):,} exact"
    if mode == "BOUNDED":
        return f"{int(estimate.get('lower') or 0):,}…{int(estimate.get('upper') or 0):,} bounded"
    if mode == "ESTIMATED" and estimate.get("value") is not None:
        return f"≈{int(estimate['value']):,} estimated"
    return "unknown until Core"


def analyzer_tokens(value: str) -> list[str]:
    return [token.strip() for token in re.split(r"[,;]", str(value or "")) if token.strip()]


def runtime_capability_selection(config: Mapping[str, Any]) -> dict[str, str]:
    """Translate Face 1's field names into canonical capability coordinates."""
    def positive_int(key: str, default: int) -> int:
        try:
            return int(config.get(key) or default)
        except (TypeError, ValueError):
            return default

    language = str(config.get("lang") or "py")
    raw = {
        "language": "python" if language in ("py", "python") else language,
        "candidate_sink": str(config.get("transport") or "loose-files"),
        "handoff": "legacy" if config.get("legacyHandoff") else "v2",
        "run_mode": str(config.get("runMode") or "verdict"),
        "execution_policy": str(config.get("profile") or ""),
        "executor_pool": "multi" if positive_int("executorPool", 1) > 1 else "single",
        "repeat": "k_gt_1" if positive_int("repeat", 1) > 1 else "k1",
        "repeat_policy": str(config.get("repeatPolicy") or "local"),
        "repeat_scope": str(config.get("repeatScope") or "metrics"),
        "repeat_environments": ("configured" if positive_int("repeatEnvironments", 0) > 0
                                else "inactive"),
        "analyzer": (str(config.get("mode") or "exploratory")
                     if str(config.get("analyzer") or "").strip() else "none"),
        "lifecycle": "run",
        "entrypoint": ("gateway" if str(config.get("backend") or "local") == "gateway"
                       else "direct"),
    }
    return capability_registry.normalize(raw)


def validate_runtime(project: GridProject, config: dict[str, Any]) -> list[RuntimeProblem]:
    problems = [RuntimeProblem(issue.severity, issue.message) for issue in project.validate()]
    analyzer = str(config.get("analyzer") or "").strip()
    invalid_goals = [token for token in analyzer_tokens(analyzer) if not ANALYZER_RE.fullmatch(token)]
    if invalid_goals:
        problems.append(RuntimeProblem("error", f"Invalid Analyzer goal(s): {', '.join(invalid_goals)}"))
    if str(config.get("mode") or "") == "formal" and not analyzer:
        problems.append(RuntimeProblem("error", "Formal analysis needs at least one explicit metric goal."))
    if int(config.get("iterations") or 1) > 1 and not analyzer:
        problems.append(RuntimeProblem("error", "Iterative BundleSeed runs need Analyzer goals."))
    if config.get("draw") and config.get("drawExact"):
        problems.append(RuntimeProblem("error", "Choose either pre-Core Face 2 or exact post-Core Face 2, not both."))
    if str(config.get("backend") or "local") != "local":
        problems.append(RuntimeProblem("error", "A locally authored workbook currently runs through the local engine only."))
    try:
        capability = capability_registry.classify(runtime_capability_selection(config))
        if capability.blocking_code:
            rule = capability_registry.RULES_BY_CODE[capability.blocking_code]
            problems.append(RuntimeProblem(
                "error", f"{capability.blocking_code}: {rule.reason}"))
        else:
            for code in capability.codes:
                rule = capability_registry.RULES_BY_CODE[code]
                if rule.level == capability_registry.EXPERIMENTAL:
                    problems.append(RuntimeProblem("warning", f"{code}: {rule.reason}"))
    except capability_registry.UnknownDimensionValue as exc:
        problems.append(RuntimeProblem("error", f"UNKNOWN_CAPABILITY_VALUE: {exc}"))
    try:
        authorize_execution(
            str(config.get("profile") or ""),
            origin=str(config.get("candidateOrigin") or ""),
            acknowledgement=str(config.get("trustedLocalAcknowledgement") or ""),
        )
    except PolicyError as exc:
        problems.append(RuntimeProblem("error", str(exc)))
    plan = plan_project(project, analyzer)
    if plan.run_class == "X" and not config.get("allowExtreme"):
        problems.append(RuntimeProblem(
            "warning",
            "The count is extreme or unknown. Bundle will apply its own budget gate; enable Allow extreme only after reviewing the reason.",
        ))
    if not project.run_once_source.strip():
        problems.append(RuntimeProblem(
            "warning",
            "FW_RunMeFirstOnce is empty. Core can materialize the structure, but candidates may be non-runnable until bootstrap/oracle code is supplied.",
        ))
    return problems


def spec_toml(project: GridProject, analyzer: str = "") -> str:
    """Serialize the launcher's metadata spec using TOML-compatible JSON strings."""
    spec = project_spec(project, analyzer)
    q = lambda value: json.dumps(str(value), ensure_ascii=False)
    arr = lambda values: "[" + ", ".join(q(value) for value in values) + "]"
    lines = [
        'spec_version = "1"',
        f"title = {q(spec.title)}",
        f"note = {q('Authored as an exact XLSX workbook in Face 1 new; worker bypasses workbook regeneration.')}",
        f"runme = {q(spec.runme)}",
        f"args = {arr(spec.args)}",
    ]
    if spec.seq_extra:
        lines.append("seq_extra = [")
        for row in spec.seq_extra:
            lines.append("  " + arr(row) + ",")
        lines.append("]")
    for slot in spec.slots:
        lines += [
            "", "[[slots]]",
            f"sheet = {q(slot.sheet)}",
            f"key = {q(slot.key)}",
            f"values = {arr(slot.values)}",
            f"verb = {q(slot.verb)}",
            f"flags = {arr(slot.flags)}",
            "raw = true",
            f"prefix = {q(slot.prefix)}",
            f"ending = {q(slot.ending)}",
        ]
    for goal in spec.goals:
        lines += ["", "[[goals]]", f"key = {q(goal.key)}", f"dir = {q(goal.direction)}"]
    for custom in spec.custom_vars:
        lines += ["", "[[custom_vars]]", f"code = {custom.code}", f"msg = {q(custom.msg)}"]
    return "\n".join(lines) + "\n"


def supported_control_fields() -> tuple[tuple[str, str, str], ...]:
    """Return the tested old control registry; imported lazily to keep planning light."""
    from intake.serve_face1 import _RUN_FLAG_SPECS, _STRESS_FLAG_SPECS
    return tuple(_RUN_FLAG_SPECS) + tuple((key, flag, "value") for key, flag in _STRESS_FLAG_SPECS)


def build_bundle_command(config: dict[str, Any], spec_dir: Path, runs_root: Path) -> list[str]:
    from intake.serve_face1 import _direct_command
    db = slug_db(str(config.get("db") or ""), "task")
    run_id = slug_id(str(config.get("runId") or ""), "r1")
    return _direct_command(config, spec_dir, db, run_id, runs_root)


def build_worker_command(config: dict[str, Any], workbook: Path, spec_dir: Path, runs_root: Path) -> list[str]:
    direct = build_bundle_command(config, spec_dir, runs_root)
    # direct[0:2] is ``python bundle_run.py``.  The worker invokes bundle.cli in
    # process so its exact-workbook stage patch remains active.
    return [sys.executable, "-m", "face1_new.workbook_runner", "--workbook", str(workbook), "--", *direct[2:]]


def command_preview(config: dict[str, Any]) -> str:
    cmd = build_worker_command(
        config,
        Path("<validated-face1-workbook.xlsx>"),
        Path("<generated-metadata-spec>"),
        Path("<face1-run-root>"),
    )
    import shlex
    return shlex.join(cmd)


def engine_checks(config: dict[str, Any]) -> list[EngineCheck]:
    """Read-only readiness probe. Password values are never returned."""
    from bundle.config import resolve_config
    from bundle.stages import CORE_JAR, READER_JAR, PY_EXECUTOR, JAVA_EXECUTOR_JAR, JAVA_JARS_DIR

    cli: dict[str, Any] = {}
    config_map = (
        ("mainPort", "main_db_port"), ("resultsPort", "results_db_port"),
        ("coreJar", "core_jar"), ("readerJar", "reader_jar"),
        ("coreProps", "core_props"), ("readerProps", "reader_props"),
        ("pyExecutor", "py_executor"), ("javaExecutorJar", "java_executor_jar"),
        ("javaJarsDir", "java_jars_dir"), ("javaCmd", "java_cmd"),
        ("javacCmd", "javac_cmd"), ("pythonCmd", "python_cmd"),
    )
    for key, attr in config_map:
        if config.get(key) not in (None, ""):
            cli[attr] = int(config[key]) if key in {"mainPort", "resultsPort"} else config[key]
    cfg, _ = resolve_config(cli=cli, config_file=(config.get("configFile") or None))
    core = Path(cfg.core_jar) if cfg.core_jar else CORE_JAR
    reader = Path(cfg.reader_jar) if cfg.reader_jar else READER_JAR
    py_executor = Path(cfg.py_executor) if cfg.py_executor else PY_EXECUTOR
    checks = [
        EngineCheck(core.is_file(), "Core", str(core)),
        EngineCheck(reader.is_file(), "Reader", str(reader)),
        EngineCheck(py_executor.is_file(), "Python Executor", str(py_executor)),
    ]
    if str(config.get("lang") or "py") == "java":
        java_executor = Path(cfg.java_executor_jar) if cfg.java_executor_jar else JAVA_EXECUTOR_JAR
        java_jars = Path(cfg.java_jars_dir) if cfg.java_jars_dir else JAVA_JARS_DIR
        checks += [
            EngineCheck(java_executor.is_file(), "Java Executor", str(java_executor)),
            EngineCheck(java_jars.is_dir(), "Java dependencies", str(java_jars)),
        ]
    checks += [
        EngineCheck(bool(os.environ.get("BUNDLE_MAIN_DB_PASSWORD") or cfg.main_db_password),
                    "Main DB credentials", "configured in server environment" if (os.environ.get("BUNDLE_MAIN_DB_PASSWORD") or cfg.main_db_password) else "set BUNDLE_MAIN_DB_PASSWORD"),
        EngineCheck(bool(os.environ.get("BUNDLE_RESULTS_DB_PASSWORD") or cfg.results_db_password),
                    "Results DB credentials", "configured in server environment" if (os.environ.get("BUNDLE_RESULTS_DB_PASSWORD") or cfg.results_db_password) else "set BUNDLE_RESULTS_DB_PASSWORD"),
    ]
    for label, host, port in (("Main PostgreSQL", cfg.main_db_host, cfg.main_db_port),
                              ("Results PostgreSQL", cfg.results_db_host, cfg.results_db_port)):
        try:
            result = subprocess.run(["pg_isready", "-h", host, "-p", str(port)], capture_output=True,
                                    text=True, timeout=4)
            checks.append(EngineCheck(result.returncode == 0, label, f"{host}:{port}"))
        except (OSError, subprocess.SubprocessError) as exc:
            checks.append(EngineCheck(False, label, str(exc)))
    return checks


def load_verified_examples() -> list[dict[str, Any]]:
    return load_scenarios(ROOT)


def example_run_config(
    example: Mapping[str, Any],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """Resolve and authorize a catalog launch before creating run artifacts.

    Repository launch profiles replace most workbook controls, so validating the
    raw UI config is insufficient: the selected scenario may switch to
    ``trusted-local``. Keep this boundary shared by the confirmation UI and the
    programmatic launcher so neither can create a temporary run directory before
    the effective policy decision has passed the same fail-closed gate as the
    CLI.
    """
    merged = scenario_run_config(example, ROOT, config)
    authorize_execution(
        str(merged.get("profile") or ""),
        origin=str(merged.get("candidateOrigin") or ""),
        acknowledgement=str(merged.get("trustedLocalAcknowledgement") or ""),
    )
    return merged


def plan_verified_example(example: Mapping[str, Any]) -> fg.SpecCardinalityPlan:
    """Plan the exact static or freshly materialized catalog document."""
    text, filename = scenario_spec_document(example, ROOT)
    with tempfile.TemporaryDirectory(prefix="face1_new_example_plan_") as temporary:
        path = Path(temporary) / filename
        path.write_text(text, encoding="utf-8")
        spec = fg.load_spec(path, strict=True)
        return fg.spec_cardinality_plan(spec)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _stage_counts(run_dir: Path, stage: str) -> dict[str, Any]:
    data = _read_json(run_dir / "stages" / f"{stage}.json") or {}
    result = {}
    for count in data.get("counts", []) or []:
        if isinstance(count, dict) and count.get("name") is not None:
            result[str(count["name"])] = count.get("actual")
    if data.get("errors"):
        result["_errors"] = data["errors"]
    return result


def collect_progress(run_dir: Path) -> tuple[str, dict[str, dict[str, Any]]]:
    state = _read_json(run_dir / "state.json") or {}
    stage_states = state.get("stages", {}) if isinstance(state.get("stages", {}), dict) else {}
    stages = {}
    for name in STAGE_ORDER:
        stage = stage_states.get(name)
        if isinstance(stage, dict):
            stages[name] = {"status": stage.get("status"), "counts": _stage_counts(run_dir, name)}
    return str(state.get("status") or "PENDING"), stages


def collect_results(run_dir: Path) -> dict[str, Any]:
    summary = _read_json(run_dir / "executor-summary.json") or {}
    provenance = _read_json(run_dir / "provenance.json") or {}
    status, stages = collect_progress(run_dir)

    def count(stage: str, key: str) -> Any:
        return (stages.get(stage, {}).get("counts", {}) or {}).get(key)

    goals = []
    for goal in provenance.get("goals", []) or []:
        mode = str(goal.get("mode") or "").upper()
        goals.append({"metric": goal.get("key"), "dir": "min" if mode == "MINIMIZE" else "max"})
    front = [{
        "id": candidate.get("candidate_id"),
        "source_ref": candidate.get("source_ref"),
        "objectives": candidate.get("objectives") or {},
        "outcome": candidate.get("outcome"),
        "reason": candidate.get("reason_non_dominated") or "",
        "dimensions": candidate.get("dimensions") or {},
    } for candidate in provenance.get("candidates", []) or []]
    return {
        "real": True,
        "run_status": status,
        "outcomes": summary.get("outcomes") or {},
        "processed": summary.get("processed", count("executor", "processed")),
        "pass": summary.get("pass", count("executor", "pass")),
        "fail": summary.get("fail", count("executor", "fail")),
        "broken": summary.get("broken", count("executor", "broken")),
        "timeout": summary.get("timeout", count("executor", "timeout")),
        "infra_fail": summary.get("infra_fail", count("executor", "infra_fail")),
        "inserted": summary.get("inserted"),
        "counts": {"mandatory": count("core", "fw_final"),
                   "post_sieve": count("sieve", "post_sieve"),
                   "candidates": count("reader", "candidates")},
        "goals": goals,
        "front": front,
        "provenance_ok": provenance.get("provenance_ok"),
        "analysis_mode": provenance.get("mode"),
    }


@dataclass
class RunSession:
    token: str
    process: subprocess.Popen[str]
    run_dir: Path
    work_dir: Path
    command: tuple[str, ...]
    log: list[str] = field(default_factory=list)
    done: bool = False
    exit_code: int | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @classmethod
    def start_project(cls, project: GridProject, config: dict[str, Any]) -> "RunSession":
        errors = [problem.message for problem in validate_runtime(project, config) if problem.severity == "error"]
        if errors:
            raise ValueError("Cannot run invalid workbook: " + "; ".join(errors[:6]))
        root = Path(tempfile.mkdtemp(prefix="face1_new_run_"))
        spec_dir, runs_root = root / "spec", root / "runs"
        spec_dir.mkdir()
        runs_root.mkdir()
        db = slug_db(str(config.get("db") or project.name), "task")
        workbook = root / f"{db}.xlsx"
        workbook.write_bytes(project.to_xlsx_bytes())
        (spec_dir / f"{db}.toml").write_text(spec_toml(project, str(config.get("analyzer") or "")), encoding="utf-8")
        command = build_worker_command(config, workbook, spec_dir, runs_root)
        return cls._spawn(command, runs_root / slug_id(str(config.get("runId") or "r1")), root)

    @classmethod
    def start_example(cls, example: dict[str, Any], config: dict[str, Any]) -> "RunSession":
        toml_text, filename = scenario_spec_document(example, ROOT)
        merged = example_run_config(example, config)
        root = Path(tempfile.mkdtemp(prefix="face1_new_example_"))
        spec_dir, runs_root = root / "spec", root / "runs"
        spec_dir.mkdir()
        runs_root.mkdir()
        (spec_dir / filename).write_text(toml_text, encoding="utf-8")
        merged["db"] = slug_db(
            str(merged.get("db") or example.get("id") or "example"),
            "example",
        )
        command = build_bundle_command(merged, spec_dir, runs_root)
        environment = scenario_environment(example, ROOT.parent)
        launch_cwd = ROOT.parent if example.get("run_profile") in REPOSITORY_LAUNCH_PROFILES else None
        return cls._spawn(
            command,
            runs_root / slug_id(str(merged.get("runId") or "r1")),
            root,
            environment,
            launch_cwd,
        )

    @classmethod
    def _spawn(
        cls,
        command: Iterable[str],
        run_dir: Path,
        work_dir: Path,
        environment: Mapping[str, str] | None = None,
        launch_cwd: Path | None = None,
    ) -> "RunSession":
        cmd = tuple(str(part) for part in command)
        process = subprocess.Popen(
            cmd,
            cwd=str(launch_cwd or ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=dict(os.environ if environment is None else environment),
            start_new_session=True,
        )
        session = cls(os.urandom(6).hex(), process, run_dir, work_dir, cmd, log=["$ " + " ".join(cmd)])

        def reader() -> None:
            try:
                if process.stdout is not None:
                    for line in process.stdout:
                        with session._lock:
                            session.log.append(line.rstrip("\n"))
            finally:
                process.wait()
                with session._lock:
                    session.exit_code = process.returncode
                    session.done = True
                    session.log.append(f"[Face 1 new] process exited with code {process.returncode}")

        threading.Thread(target=reader, name=f"face1-new-{session.token}", daemon=True).start()
        return session

    def snapshot(self) -> RunSnapshot:
        with self._lock:
            done, exit_code, lines = self.done, self.exit_code, tuple(self.log)
        actual_run_dir = self._resolved_run_dir()
        run_status, stages = collect_progress(actual_run_dir)
        results = collect_results(actual_run_dir) if done and actual_run_dir.is_dir() else None
        return RunSnapshot(done, exit_code, run_status, stages, lines, results, str(actual_run_dir))

    def _resolved_run_dir(self) -> Path:
        """Follow an iterate campaign to its latest numbered run journal."""
        if self.run_dir.is_dir():
            return self.run_dir
        pattern = re.compile(re.escape(self.run_dir.name) + r"-it(\d+)$")
        candidates = []
        if self.run_dir.parent.is_dir():
            for path in self.run_dir.parent.glob(self.run_dir.name + "-it*"):
                match = pattern.fullmatch(path.name)
                if match and path.is_dir():
                    candidates.append((int(match.group(1)), path))
        return max(candidates, default=(0, self.run_dir))[1]

    def cancel(self) -> None:
        if self.done:
            return
        try:
            os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
        except (OSError, ProcessLookupError):
            try:
                self.process.terminate()
            except OSError:
                pass
        with self._lock:
            self.log.append("[Face 1 new] cancel requested (SIGTERM)")


def results_csv(results: dict[str, Any]) -> str:
    import csv
    from io import StringIO
    goals = [str(goal.get("metric") or "") for goal in results.get("goals", [])]
    out = StringIO()
    writer = csv.writer(out)
    writer.writerow(["candidate", "outcome", *goals, "source_ref", "reason"])
    for item in results.get("front", []) or []:
        objectives = item.get("objectives") or {}
        writer.writerow([item.get("id"), item.get("outcome"), *[objectives.get(goal) for goal in goals],
                         item.get("source_ref"), item.get("reason")])
    return out.getvalue()
