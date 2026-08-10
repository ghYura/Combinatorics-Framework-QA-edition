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

"""Compact NiceGUI planning, run-control, progress, and results surface."""

from __future__ import annotations

from functools import partial
import json
from pathlib import Path
import re
from typing import Any, Callable

import fwgen
from bundle import capabilities as capability_registry
from bundle.policy import ORIGINS, PolicyError, profile_choices
from intake.scenario_library import (
    scenario_source_label,
    scenarios_in_suite,
    suite_catalog,
)
from nicegui import events, ui

from .grid_model import GridProject
from .runtime_model import (
    RunSession,
    command_preview,
    default_run_config,
    engine_checks,
    example_run_config,
    format_estimate,
    load_verified_examples,
    plan_project,
    plan_verified_example,
    results_csv,
    supported_control_fields,
    validate_runtime,
    runtime_capability_selection,
)


RUN_CSS = r"""
.run-page { width:100%; gap:7px; }
.plan-strip { width:100%; display:grid; grid-template-columns:1.2fr repeat(4,minmax(130px,1fr)); border:1px solid var(--line); background:#fff; overflow:hidden; }
.plan-cell { min-height:54px; padding:7px 10px; border-right:1px solid var(--grid); display:flex; flex-direction:column; justify-content:center; gap:2px; }
.plan-cell:last-child { border-right:0; }
.plan-key { color:#667085; font-size:9px; font-weight:800; text-transform:uppercase; letter-spacing:.08em; }
.plan-value { color:#1f2937; font-size:14px; line-height:1.1; font-weight:780; }
.plan-formula { color:#667085; font:9px/1.2 ui-monospace,SFMono-Regular,Menlo,monospace; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.run-layout { width:100%; display:grid; grid-template-columns:minmax(0,2fr) minmax(280px,.8fr); gap:8px; align-items:start; }
.run-card { border:1px solid var(--line); background:#fff; min-width:0; overflow:hidden; }
.run-card-head { min-height:34px; padding:5px 8px; border-bottom:1px solid var(--line); background:#f7f8f9; display:flex; align-items:center; justify-content:space-between; gap:6px; }
.run-card-body { padding:7px; }
.run-fields { display:grid; grid-template-columns:repeat(4,minmax(150px,1fr)); gap:6px; }
.run-field-wide { grid-column:span 2; }
.run-checks { display:grid; grid-template-columns:repeat(3,minmax(150px,1fr)); gap:2px 10px; padding:4px 0; }
.honesty-note { border-left:4px solid #d97706; background:#fff8eb; color:#713f12; padding:7px 9px; font-size:10px; line-height:1.35; }
.engine-row { display:grid; grid-template-columns:20px 115px minmax(0,1fr); align-items:center; gap:5px; min-height:25px; border-bottom:1px solid #edf0f2; font-size:10px; }
.engine-ok { color:#107c41; font-weight:800; }
.engine-bad { color:#b42318; font-weight:800; }
.stage-strip { width:100%; display:grid; grid-template-columns:repeat(7,minmax(90px,1fr)); border:1px solid var(--line); background:#fff; overflow:auto; }
.stage-cell { min-height:48px; padding:6px; border-right:1px solid var(--grid); }
.stage-cell:last-child { border-right:0; }
.stage-name { font-size:9px; text-transform:uppercase; letter-spacing:.06em; font-weight:800; color:#667085; }
.stage-state { font-size:10px; font-weight:750; color:#344054; }
.stage-count { font:9px/1.2 ui-monospace,monospace; color:#667085; }
.stage-SUCCEEDED { background:#edf8f1; }
.stage-RUNNING { background:#fff7df; }
.stage-FAILED,.stage-INTERRUPTED { background:#fff0ee; }
.result-strip { display:grid; grid-template-columns:repeat(6,minmax(95px,1fr)); border:1px solid var(--line); }
.result-cell { padding:7px 9px; border-right:1px solid var(--grid); background:#fff; }
.result-cell:last-child { border-right:0; }
.problem-error { color:#8f1d18; background:#fff1f0; border-left:3px solid #d92d20; padding:5px 7px; }
.problem-warning { color:#7a4510; background:#fff8e8; border-left:3px solid #d97706; padding:5px 7px; }
.advanced-grid { display:grid; grid-template-columns:repeat(3,minmax(180px,1fr)); gap:5px; padding:6px; }
.command-preview textarea { font:10px/1.35 ui-monospace,SFMono-Regular,Menlo,monospace!important; }
@media (max-width:1100px) { .run-layout { grid-template-columns:1fr; } .run-fields { grid-template-columns:repeat(2,minmax(150px,1fr)); } .plan-strip { grid-template-columns:repeat(2,1fr); } .run-fields .run-field-wide { grid-column:span 2; } }
@media (max-width:650px) { .run-fields,.advanced-grid { grid-template-columns:1fr; } .run-fields .run-field-wide { grid-column:span 1; } .plan-strip { grid-template-columns:1fr; } .run-checks { grid-template-columns:1fr; } }
"""


ESSENTIAL_KEYS = {
    "runMode", "sieve", "draw", "drawExact", "profile", "mainPort", "resultsPort",
    "allowExtreme", "candidateOrigin", "trustedLocalAcknowledgement",
}
READINESS_KEYS = {
    "lang", "mainPort", "resultsPort", "coreJar", "readerJar", "coreProps",
    "readerProps", "pyExecutor", "javaExecutorJar", "javaJarsDir", "javaCmd",
    "javacCmd", "pythonCmd", "configFile",
}

BOOL_LABELS = {
    "seedOutput": "Write BundleSeed", "overrideBudget": "Budget override reason",
    "allowExtreme": "Allow extreme", "unleash": "Unleash initial power",
    "legacyScratch": "Legacy scratch", "legacyHandoff": "Legacy handoff", "debug": "Debug",
}
GROUP_KEYS = {
    "Budgets & safety": {
        "budgetMandatoryRows", "budgetFinalCandidates", "budgetDiskBytes", "budgetInodes",
        "budgetWallTimeSeconds", "budgetRequests", "budgetMonetaryCost", "budgetWarnFraction",
        "costPerCandidate", "overrideBudget", "allowExtreme", "unleash",
    },
    "Execution & sandbox": {
        "sandboxNetworkAllowlist", "sandboxCandidateEnv", "executorTolerateOutcomes",
        "sandboxPolicy", "executorCompiler", "seedFrom", "seedOutput", "explorationFloor",
        "minWinnerSupport",
    },
    "Repeat policy": {"repeat", "repeatPolicy", "repeatScope", "repeatEnvironments"},
    "Timeouts & infrastructure": {
        "coreTimeout", "readerTimeout", "executorTimeout", "scratchRoot", "coreJar", "readerJar",
        "coreProps", "readerProps", "pyExecutor", "javaExecutorJar", "javaJarsDir", "javaCmd",
        "javacCmd", "pythonCmd", "configFile", "legacyScratch", "legacyHandoff", "debug",
    },
    "Stress mode": {"baseUrl", "workers", "duration", "ramp", "sloP99", "errBudget"},
}


def _human_key(key: str) -> str:
    if key in BOOL_LABELS:
        return BOOL_LABELS[key]
    return re.sub(r"(?<!^)(?=[A-Z])", " ", key).replace("Db", "DB").replace("Grpc", "gRPC").title()


def _short_formula(estimate: dict[str, Any]) -> str:
    return str(estimate.get("formula") or "")


def _count_text(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


def _dimension_choices(dimension_id: str, *, encode=None, exclude=(), selection=None,
                       label_overrides=None):
    """Options sourced from the engine registry, including contextual disables."""
    dimension = capability_registry.DIMENSIONS_BY_ID[dimension_id]
    encode = encode or (lambda value: value)
    labels = {
        "python": "Python", "java": "Java", "verdict": "Verdict", "stress": "Stress",
        "formal": "Formal", "exploratory": "Exploratory", "loose-files": "Loose files",
        "sharded": "Sharded", "grpc": "gRPC live",
    }
    labels.update(label_overrides or {})
    if selection is None:
        return {encode(value): labels.get(value, value) for value in dimension.values
                if value not in set(exclude)}
    options = []
    for entry in capability_registry.available_values(dimension_id, selection):
        value = entry["value"]
        if value in set(exclude):
            continue
        suffix = f" — {entry['code']}" if not entry["enabled"] and entry["code"] else ""
        options.append({"label": labels.get(value, value) + suffix,
                        "value": encode(value), "disable": not entry["enabled"]})
    return options


def render_run_center(state: dict[str, Any]) -> None:
    """Render one live run center and register its project-refresh callback in state."""
    config = state.setdefault("runtime_config", default_run_config(state["project"].name))
    examples = load_verified_examples()
    controls: dict[str, Any] = {}
    capability_selection = runtime_capability_selection(config)
    profile_labels = {choice["profile"]: choice["label"] for choice in profile_choices()}
    results_token = {"value": ""}
    log_cursor = {"value": 0}

    with ui.column().classes("run-page"):
        with ui.element("div").classes("plan-strip"):
            with ui.element("div").classes("plan-cell"):
                ui.label("Workbook health").classes("plan-key")
                health_value = ui.label().classes("plan-value")
                health_formula = ui.label().classes("plan-formula")
            with ui.element("div").classes("plan-cell"):
                ui.label("Mandatory Core rows").classes("plan-key")
                mandatory_value = ui.label().classes("plan-value")
                mandatory_formula = ui.label().classes("plan-formula")
            with ui.element("div").classes("plan-cell"):
                ui.label("Post-sieve").classes("plan-key")
                sieve_value = ui.label().classes("plan-value")
                sieve_formula = ui.label().classes("plan-formula")
            with ui.element("div").classes("plan-cell"):
                ui.label("Optional multiplier").classes("plan-key")
                optional_value = ui.label().classes("plan-value")
                optional_formula = ui.label().classes("plan-formula")
            with ui.element("div").classes("plan-cell"):
                ui.label("Final candidates · class").classes("plan-key")
                final_value = ui.label().classes("plan-value")
                final_formula = ui.label().classes("plan-formula")

        with ui.element("div").classes("run-layout"):
            with ui.column().classes("run-card gap-0"):
                with ui.element("div").classes("run-card-head"):
                    ui.label("Plan & run configuration").classes("font-bold text-xs")
                    ui.label("exact XLSX → real Bundle journal").classes("pill")
                with ui.column().classes("run-card-body gap-2"):
                    with ui.element("div").classes("run-fields"):
                        db_input = ui.input("Database", value=config.get("db", "")).props("outlined dense").classes("w-full")
                        run_id_input = ui.input("Run id", value=config.get("runId", "r1")).props("outlined dense").classes("w-full")
                        language = ui.select(_dimension_choices("language", encode=lambda value: "py" if value == "python" else value, selection=capability_selection), value=config.get("lang", "py"), label="Candidate language").props("outlined dense options-dense").classes("w-full")
                        run_mode = ui.select(_dimension_choices("run_mode", selection=capability_selection), value=config.get("runMode", "verdict"), label="Run mode").props("outlined dense options-dense").classes("w-full")
                        goals = ui.input("Goals · metric:min|max", value=config.get("analyzer", ""), placeholder="latency_ms:min, throughput:max").props("outlined dense").classes("w-full run-field-wide")
                        analysis_mode = ui.select(_dimension_choices("analyzer", exclude=("none",)), value=config.get("mode", "exploratory"), label="Analysis contract").props("outlined dense options-dense").classes("w-full")
                        # Audit F2: this list used to be hand-written and offered
                        # 'balanced'/'strict', which policy.PROFILES cannot resolve,
                        # while omitting 'generated-default' — the only secure
                        # profile there is. It now renders the canonical registry,
                        # and there is no pre-selected value: choosing an execution
                        # policy is the operator's explicit decision.
                        _profile_choices = _dimension_choices("execution_policy", selection=capability_selection, label_overrides=profile_labels)
                        profile = ui.select(_profile_choices, value=(config.get("profile") or None), label="Execution policy · required").props("outlined dense options-dense").classes("w-full")
                        origin = ui.select(
                            {name: name for name in ORIGINS},
                            value=(config.get("candidateOrigin") or None),
                            label="Candidate origin · required for trusted-local",
                        ).props("outlined dense options-dense").classes("w-full")
                        acknowledgement = ui.input(
                            "Trusted-local reason · required for NO SANDBOX",
                            value=config.get("trustedLocalAcknowledgement", ""),
                            placeholder="why this code is reviewed and trusted",
                        ).props("outlined dense").classes("w-full run-field-wide")
                        ui.label(
                            "Trusted-local warning (applies only when selected): "
                            + next(c["warning"] for c in profile_choices() if c["warning"])
                        ).classes("text-[10px] text-red-600 px-1 run-field-wide")
                        transport = ui.select(_dimension_choices("candidate_sink", selection=capability_selection), value=config.get("transport", "loose-files"), label="Candidate transport").props("outlined dense options-dense").classes("w-full")
                        pool = ui.number("Executor pool", value=int(config.get("executorPool") or 1), min=1, step=1).props("outlined dense").classes("w-full")
                        iterations = ui.number("Iterations", value=int(config.get("iterations") or 1), min=1, max=50, step=1).props("outlined dense").classes("w-full")
                        main_port = ui.number("Main DB port", value=config.get("mainPort") or 5433, min=1, max=65535, step=1).props("outlined dense").classes("w-full")
                        results_port = ui.number("Results DB port", value=config.get("resultsPort") or 5432, min=1, max=65535, step=1).props("outlined dense").classes("w-full")
                    with ui.element("div").classes("run-checks"):
                        sieve = ui.checkbox("Apply existing sieve", value=bool(config.get("sieve"))).props("dense")
                        draw = ui.checkbox("Open Face 2 before Core", value=bool(config.get("draw"))).props("dense")
                        draw_exact = ui.checkbox("Open Face 2 after Core · exact", value=bool(config.get("drawExact"))).props("dense")
                        allow_extreme = ui.checkbox("Allow extreme after review", value=bool(config.get("allowExtreme"))).props("dense")
                    problem_host = ui.column().classes("w-full gap-1")

                with ui.expansion("Advanced · complete Bundle control surface", icon="tune").classes("w-full border-t"):
                    ui.label("DB hosts/users/passwords are inherited from the server environment and never placed in browser fields.").classes("text-[10px] muted px-2")
                    registry = supported_control_fields()
                    for group, keys in GROUP_KEYS.items():
                        fields = [entry for entry in registry if entry[0] in keys and entry[0] not in ESSENTIAL_KEYS]
                        if not fields:
                            continue
                        with ui.expansion(group).classes("w-full border-t"):
                            with ui.element("div").classes("advanced-grid"):
                                for key, flag, kind in fields:
                                    label = f"{_human_key(key)} · {flag}"
                                    if kind == "bool":
                                        control = ui.checkbox(label, value=bool(config.get(key))).props("dense")
                                    else:
                                        control = ui.input(label, value=config.get(key, "")).props("outlined dense").classes("w-full")
                                    controls[key] = control

                with ui.expansion("Exact launch command", icon="terminal").classes("w-full border-t"):
                    command_box = ui.textarea(value="", label="Server-side command · passwords remain environment-only").props("outlined readonly autogrow").classes("command-preview w-full p-2")

            with ui.column().classes("run-card gap-0"):
                with ui.element("div").classes("run-card-head"):
                    ui.label("Engine & actions").classes("font-bold text-xs")
                    backend_badge = ui.label("not checked").classes("pill")
                with ui.column().classes("run-card-body gap-2"):
                    ui.label("Planning is read-only. Run writes to both configured PostgreSQL instances and executes generated candidates under the selected policy.").classes("honesty-note w-full")
                    readiness_host = ui.column().classes("w-full gap-0")
                    with ui.row().classes("w-full gap-1 flex-wrap"):
                        ui.button("Plan only", icon="calculate", on_click=lambda: refresh_plan(True)).props("outline dense no-caps color=green-8")
                        ui.button("Check engine", icon="health_and_safety", on_click=lambda: refresh_readiness(True)).props("outline dense no-caps color=green-8")
                    with ui.row().classes("w-full gap-1 flex-wrap"):
                        ui.button("Run workbook", icon="play_arrow", on_click=lambda: confirm_run(False)).props("unelevated dense no-caps color=green-8")
                        ui.button("Run + Face 2", icon="account_tree", on_click=lambda: confirm_run(True)).props("unelevated dense no-caps color=deep-purple-7")
                        cancel_button = ui.button("Cancel", icon="stop", on_click=lambda: cancel_run()).props("outline dense no-caps color=red-7")
                        cancel_button.disable()
                    run_status = ui.label("No run started").classes("text-xs font-bold")
                    run_path = ui.label("").classes("text-[9px] muted font-mono break-all")

                with ui.expansion("Verified scenario library", icon="verified").classes("w-full border-t"):
                    if examples:
                        suites = suite_catalog(examples)
                        suite_options = {suite_id: title for suite_id, title in suites}
                        suite_id = suites[0][0]
                        suite_select = ui.select(
                            suite_options,
                            value=suite_id,
                            label="Test suite",
                        ).props("outlined dense options-dense").classes("w-full px-2 pt-2")
                        suite_examples = scenarios_in_suite(examples, suite_id)
                        options = {
                            str(item["id"]): str(item.get("title") or item["id"])
                            for item in suite_examples
                        }
                        example_select = ui.select(
                            options,
                            value=str(suite_examples[0]["id"]),
                            label="Scenario",
                        ).props("outlined dense options-dense").classes("w-full px-2")
                        example_detail = ui.label().classes("text-[10px] muted px-2")
                        with ui.row().classes("w-full gap-1 px-2 pb-2"):
                            ui.button("Inspect plan", on_click=lambda: inspect_example()).props("flat dense no-caps color=green-8")
                            ui.button("Run example", on_click=lambda: confirm_example()).props("flat dense no-caps color=green-8")
                    else:
                        suite_select = None
                        example_select = None
                        example_detail = ui.label("No verified example manifest found.").classes("text-xs muted p-2")

        with ui.element("div").classes("stage-strip"):
            stage_elements: dict[str, tuple[Any, Any, Any]] = {}
            for stage_name in ("gen", "core", "seed_bias", "sieve", "reader", "executor", "analyzer"):
                cell = ui.element("div").classes("stage-cell")
                with cell:
                    ui.label(stage_name.replace("_", " ")).classes("stage-name")
                    status_label = ui.label("pending").classes("stage-state")
                    count_label = ui.label("").classes("stage-count")
                stage_elements[stage_name] = (cell, status_label, count_label)

        with ui.expansion("Live run log", icon="article").classes("w-full run-card") as log_expansion:
            log_box = ui.textarea(value="").props("outlined readonly autogrow input-class=font-mono").classes("w-full p-2 command-preview")

        results_host = ui.column().classes("w-full gap-2")

    def mark_readiness_stale() -> None:
        backend_badge.set_text("recheck needed")
        readiness_host.clear()
        with readiness_host:
            ui.label("Configuration changed; run Check engine again.").classes("text-[10px] muted")

    def refresh_capability_options() -> None:
        """Recompute disabled choices after any interdependent field changes."""
        try:
            selection = runtime_capability_selection(config)
        except capability_registry.UnknownDimensionValue:
            return
        language.options = _dimension_choices(
            "language", encode=lambda value: "py" if value == "python" else value,
            selection=selection)
        run_mode.options = _dimension_choices("run_mode", selection=selection)
        transport.options = _dimension_choices("candidate_sink", selection=selection)
        profile.options = _dimension_choices(
            "execution_policy", selection=selection, label_overrides=profile_labels)
        for control in (language, run_mode, transport, profile):
            control.update()

    def set_config(key: str, value: Any) -> None:
        config[key] = value
        if key in READINESS_KEYS:
            mark_readiness_stale()
        refresh_capability_options()
        refresh_plan(False)

    def set_int_config(key: str, value: Any) -> None:
        try:
            config[key] = int(value)
        except (TypeError, ValueError):
            config[key] = value
        if key in READINESS_KEYS:
            mark_readiness_stale()
        refresh_capability_options()
        refresh_plan(False)

    db_input.on_value_change(lambda e: set_config("db", str(e.value or "")))
    run_id_input.on_value_change(lambda e: set_config("runId", str(e.value or "")))
    language.on_value_change(lambda e: set_config("lang", e.value))
    run_mode.on_value_change(lambda e: set_config("runMode", e.value))
    goals.on_value_change(lambda e: set_config("analyzer", str(e.value or "")))
    analysis_mode.on_value_change(lambda e: set_config("mode", e.value))
    profile.on_value_change(lambda e: set_config("profile", e.value))
    origin.on_value_change(lambda e: set_config("candidateOrigin", e.value))
    acknowledgement.on_value_change(
        lambda e: set_config("trustedLocalAcknowledgement", str(e.value or "")))
    transport.on_value_change(lambda e: set_config("transport", e.value))
    pool.on_value_change(lambda e: set_int_config("executorPool", e.value))
    iterations.on_value_change(lambda e: set_int_config("iterations", e.value))
    main_port.on_value_change(lambda e: set_int_config("mainPort", e.value))
    results_port.on_value_change(lambda e: set_int_config("resultsPort", e.value))
    sieve.on_value_change(lambda e: set_config("sieve", bool(e.value)))
    allow_extreme.on_value_change(lambda e: set_config("allowExtreme", bool(e.value)))

    def set_draw(exact: bool, value: bool) -> None:
        key, other_key = ("drawExact", "draw") if exact else ("draw", "drawExact")
        config[key] = value
        if value:
            config[other_key] = False
            config["sieve"] = True
            sieve.set_value(True)
            (draw if exact else draw_exact).set_value(False)
        refresh_plan(False)

    draw.on_value_change(lambda e: set_draw(False, bool(e.value)))
    draw_exact.on_value_change(lambda e: set_draw(True, bool(e.value)))
    for key, control in controls.items():
        control.on_value_change(lambda e, field=key: set_config(field, e.value))

    def refresh_plan(notify: bool = False) -> None:
        project: GridProject = state["project"]
        plan = plan_project(project, str(config.get("analyzer") or ""))
        project_issues = project.validate()
        errors = sum(issue.severity == "error" for issue in project_issues)
        warnings = sum(issue.severity == "warning" for issue in project_issues)
        health_value.set_text("Ready" if not errors else f"{errors} error(s)")
        health_formula.set_text(f"{len(project.sequence_rows)} FW_Seq rows · {warnings} warning(s)")
        mandatory_value.set_text(format_estimate(plan.mandatory))
        mandatory_formula.set_text(_short_formula(plan.mandatory))
        sieve_value.set_text(format_estimate(plan.post_sieve))
        sieve_formula.set_text(_short_formula(plan.post_sieve))
        optional_value.set_text("×" + _count_text(plan.optional_multiplier.get("value")))
        optional_formula.set_text(_short_formula(plan.optional_multiplier))
        final_value.set_text(f"{format_estimate(plan.final)} · {plan.run_class}")
        final_formula.set_text(_short_formula(plan.final))
        try:
            command_box.set_value(command_preview(config))
        except Exception as exc:
            command_box.set_value(f"Command unavailable: {exc}")
        problem_host.clear()
        with problem_host:
            for problem in validate_runtime(project, config)[:12]:
                ui.label(problem.message).classes(f"problem-{problem.severity} text-[10px] w-full")
        if notify:
            if errors:
                ui.notify(f"Plan blocked by {errors} workbook error(s)", type="negative")
            else:
                ui.notify(f"Plan: {format_estimate(plan.final)} · run class {plan.run_class}", type="positive")

    def refresh_readiness(notify: bool = False) -> bool:
        checks = engine_checks(config)
        readiness_host.clear()
        with readiness_host:
            for check in checks:
                with ui.element("div").classes("engine-row"):
                    ui.label("✓" if check.ok else "×").classes("engine-ok" if check.ok else "engine-bad")
                    ui.label(check.label).classes("font-semibold")
                    ui.label(check.detail).classes("muted font-mono break-all")
        okay = all(check.ok for check in checks)
        backend_badge.set_text("engine ready" if okay else "engine incomplete")
        if notify:
            ui.notify("Local engine is ready" if okay else "Engine check found missing prerequisites",
                      type="positive" if okay else "warning")
        return okay

    def run_busy() -> bool:
        session: RunSession | None = state.get("session")
        return bool(session and not session.done)

    def begin_project_run() -> None:
        if run_busy():
            ui.notify("A run is already active", type="warning")
            return
        try:
            session = RunSession.start_project(state["project"], config)
        except Exception as exc:
            ui.notify(str(exc), type="negative", multi_line=True)
            return
        state["session"] = session
        results_token["value"] = ""
        log_cursor["value"] = 0
        cancel_button.enable()
        log_expansion.open()
        poll_run()
        ui.notify(f"Run {config.get('runId') or 'r1'} started", type="positive")

    def confirm_run(with_face2: bool) -> None:
        if with_face2:
            config.update({"draw": True, "drawExact": False, "sieve": True})
            draw.set_value(True)
            draw_exact.set_value(False)
            sieve.set_value(True)
        problems = validate_runtime(state["project"], config)
        errors = [problem.message for problem in problems if problem.severity == "error"]
        if errors:
            ui.notify("Cannot run: " + "; ".join(errors[:4]), type="negative", multi_line=True)
            return
        plan = plan_project(state["project"], str(config.get("analyzer") or ""))
        with ui.dialog() as dialog, ui.card().classes("w-[680px] max-w-[96vw] p-4 gap-3"):
            ui.label("Start the real Bundle pipeline?").classes("font-bold text-base")
            ui.label(
                f"The exact validated workbook will run as DB {config.get('db') or state['project'].name!r}, "
                f"run {config.get('runId') or 'r1'!r}. Plan: {format_estimate(plan.final)}, class {plan.run_class}."
            ).classes("text-xs")
            ui.label("This writes Core and Results databases and executes generated candidate code. Face 2 will pause the run in a browser when selected.").classes("honesty-note w-full")
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Cancel", on_click=dialog.close).props("flat")
                ui.button("Start real run", icon="play_arrow", on_click=lambda: (dialog.close(), begin_project_run())).props("unelevated color=green-8")
        dialog.open()

    def cancel_run() -> None:
        session: RunSession | None = state.get("session")
        if session and not session.done:
            session.cancel()
            ui.notify("Cancellation requested", type="warning")

    def selected_example() -> dict[str, Any] | None:
        if example_select is None:
            return None
        return next(
            (
                item
                for item in examples
                if str(item["id"]) == str(example_select.value)
            ),
            None,
        )

    def update_suite() -> None:
        if suite_select is None or example_select is None:
            return
        selected = scenarios_in_suite(examples, str(suite_select.value))
        options = {
            str(item["id"]): str(item.get("title") or item["id"])
            for item in selected
        }
        example_select.options = options
        example_select.value = next(iter(options), None)
        example_select.update()
        update_example_detail()

    def update_example_detail() -> None:
        selected = selected_example()
        if selected is None:
            return
        profile = str(selected.get("run_profile") or "standard")
        example_detail.set_text(
            f"{selected.get('pass', '?')}/{selected.get('candidates', '?')} PASS · "
            f"profile {profile} · {scenario_source_label(selected)} · {selected.get('blurb', '')}"
        )

    def inspect_example() -> None:
        selected = selected_example()
        if selected is None:
            return
        plan = plan_verified_example(selected)
        with ui.dialog() as dialog, ui.card().classes("w-[760px] max-w-[96vw] p-4 gap-3"):
            ui.label(str(selected.get("title") or selected["id"])).classes("font-bold text-base")
            ui.label(str(selected.get("blurb") or "")).classes("text-xs muted")
            ui.code(fwgen.format_cardinality_plan(plan), language="text").classes("w-full text-[10px]")
            with ui.row().classes("w-full justify-end"):
                ui.button("Close", on_click=dialog.close).props("flat")
        dialog.open()

    def begin_example_run(selected: dict[str, Any]) -> None:
        if run_busy():
            ui.notify("A run is already active", type="warning")
            return
        try:
            session = RunSession.start_example(selected, config)
        except Exception as exc:
            ui.notify(str(exc), type="negative", multi_line=True)
            return
        state["session"] = session
        results_token["value"] = ""
        log_cursor["value"] = 0
        cancel_button.enable()
        log_expansion.open()
        poll_run()

    def confirm_example() -> None:
        selected = selected_example()
        if selected is None:
            return
        try:
            # A repository scenario may replace the visible profile with its
            # immutable launch profile. Validate that *effective* configuration
            # before showing a start confirmation or creating temporary files.
            example_run_config(selected, config)
        except (PolicyError, ValueError) as exc:
            ui.notify(
                "Cannot run example: " + str(exc),
                type="negative",
                multi_line=True,
            )
            return
        with ui.dialog() as dialog, ui.card().classes("w-[650px] max-w-[96vw] p-4 gap-3"):
            ui.label("Run verified scenario (current workbook stays unchanged)?").classes("font-bold text-base")
            expectation = (
                "expected local control result"
                if selected.get("spec_materializer")
                else "expected historical result"
            )
            ui.label(f"{selected.get('title')} · {expectation} {selected.get('pass')}/{selected.get('candidates')} PASS").classes("text-xs")
            if selected.get("spec_materializer"):
                profile_note = (
                    "A fresh held-out spec is created for this launch. The immutable profile "
                    "uses generated-default, zero external cost, and local oracle controls only."
                )
            elif selected.get("run_profile"):
                profile_note = (
                    "The suite's checked-in launch profile safely overrides workbook controls."
                )
            else:
                profile_note = "This is a real run of the repository spec, not a simulation."
            ui.label(profile_note).classes("honesty-note w-full")
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Cancel", on_click=dialog.close).props("flat")
                ui.button("Start example", on_click=lambda: (dialog.close(), begin_example_run(selected))).props("unelevated color=green-8")
        dialog.open()

    def render_results(results: dict[str, Any], token: str) -> None:
        if results_token["value"] == token:
            return
        results_token["value"] = token
        results_host.clear()
        with results_host:
            with ui.element("div").classes("run-card w-full"):
                with ui.element("div").classes("run-card-head"):
                    ui.label("Real run results").classes("font-bold text-xs")
                    ui.label(str(results.get("run_status") or "finished")).classes("pill")
                with ui.element("div").classes("result-strip"):
                    values = [
                        ("Processed", results.get("processed")), ("Pass", results.get("pass")),
                        ("Domain fail", results.get("fail")), ("Broken", results.get("broken")),
                        ("Timeout", results.get("timeout")), ("Infra fail", results.get("infra_fail")),
                    ]
                    for label, value in values:
                        with ui.element("div").classes("result-cell"):
                            ui.label(label).classes("plan-key")
                            ui.label(_count_text(value)).classes("plan-value")
                counts = results.get("counts") or {}
                ui.label(
                    f"Core {_count_text(counts.get('mandatory'))} → sieve {_count_text(counts.get('post_sieve'))} → Reader {_count_text(counts.get('candidates'))}. "
                    f"Analyzer mode: {results.get('analysis_mode') or 'not used'}; provenance: {results.get('provenance_ok')}."
                ).classes("text-[10px] muted p-2")
                front = results.get("front") or []
                if front:
                    goal_keys = [str(goal.get("metric") or "") for goal in results.get("goals", [])]
                    columns = [{"name": "id", "label": "Candidate", "field": "id", "align": "left"},
                               {"name": "outcome", "label": "Outcome", "field": "outcome", "align": "left"}]
                    columns += [{"name": key, "label": key, "field": key, "align": "right"} for key in goal_keys]
                    rows = [{"id": item.get("id"), "outcome": item.get("outcome"),
                             **{key: (item.get("objectives") or {}).get(key) for key in goal_keys}}
                            for item in front]
                    ui.table(columns=columns, rows=rows, row_key="id", pagination=10).props("dense flat bordered").classes("w-full")
                with ui.row().classes("w-full justify-end gap-1 p-2"):
                    ui.button("Export result JSON", icon="download", on_click=lambda: ui.download(
                        json.dumps(results, ensure_ascii=False, indent=2).encode(), "face1-results.json", "application/json"
                    )).props("flat dense no-caps color=green-8")
                    ui.button("Export Pareto CSV", icon="download", on_click=lambda: ui.download(
                        results_csv(results).encode(), "face1-pareto.csv", "text/csv"
                    )).props("flat dense no-caps color=green-8")

    def poll_run() -> None:
        session: RunSession | None = state.get("session")
        if session is None:
            return
        snapshot = session.snapshot()
        run_status.set_text(
            f"{snapshot.run_status} · exit {snapshot.exit_code}" if snapshot.done else f"{snapshot.run_status} · running"
        )
        run_path.set_text(snapshot.run_dir)
        log_box.set_value("\n".join(snapshot.log[-700:]))
        for name, (cell, status_label, count_label) in stage_elements.items():
            data = snapshot.stages.get(name, {})
            status = str(data.get("status") or "pending")
            cell.classes(remove="stage-SUCCEEDED stage-RUNNING stage-FAILED stage-INTERRUPTED")
            if status in {"SUCCEEDED", "RUNNING", "FAILED", "INTERRUPTED"}:
                cell.classes(add=f"stage-{status}")
            status_label.set_text(status.lower())
            counts = data.get("counts") or {}
            count_label.set_text(" · ".join(f"{key}={value}" for key, value in counts.items() if key != "_errors"))
        if snapshot.done:
            cancel_button.disable()
            if snapshot.results:
                render_results(snapshot.results, session.token)

    if example_select is not None:
        example_select.on_value_change(lambda _e: update_example_detail())
        update_example_detail()
    if suite_select is not None:
        suite_select.on_value_change(lambda _e: update_suite())
    refresh_plan(False)
    refresh_readiness(False)
    state["refresh_runtime"] = lambda: refresh_plan(False)
    state["poll_runtime"] = poll_run
