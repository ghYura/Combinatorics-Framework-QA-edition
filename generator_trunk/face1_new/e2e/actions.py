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

"""Semantic action flows for combinatorial Face 1 new browser candidates.

Each flow owns HEAD-like setup and TAIL-like assertions while remaining small
enough to be selected as an independent Bundle variation. The static Bundle
spec composes these flows with browser, viewport and data-profile dimensions.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import time
from typing import Callable

from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from face1_new.grid_model import TEMPLATES
from face1_new.runtime_model import supported_control_fields

from .page_object import Face1Page, _displayed, _normalized


FLOW_NAMES = (
    "grid_data_sync",
    "grid_structure",
    "template_catalog",
    "control_sheets",
    "runtime_essentials",
    "runtime_advanced_budgets",
    "runtime_advanced_sandbox",
    "runtime_advanced_repeat",
    "runtime_advanced_infra_paths",
    "runtime_advanced_infra_commands",
    "runtime_advanced_stress",
    "modal_guardrails",
    "download_import",
)

NESTED_FLOW_NAMES = (
    "runtime_real_run",
    "runtime_cancel",
    "scenario_real_run",
)
ALL_FLOW_NAMES = FLOW_NAMES + NESTED_FLOW_NAMES

CANONICAL_RUN_ONCE_SOURCE = (
    "class RunMeFirstOnce { public static String FW_ARGS; "
    "public static void main(String[] args) { FW_ARGS = \"--face1-e2e\"; } }"
)


@dataclass(frozen=True)
class FlowResult:
    flow: str
    ok: bool
    checks: int
    latency_ms: float
    error: str = ""


class _Probe:
    def __init__(self) -> None:
        self.checks = 0

    def that(self, condition: object, message: str) -> None:
        self.checks += 1
        if not condition:
            raise AssertionError(message)


def _set_input(element, value: object) -> None:
    element.click()
    element.send_keys(Keys.CONTROL, "a")
    element.send_keys(Keys.BACKSPACE)
    if str(value):
        element.send_keys(str(value))
    element.send_keys(Keys.TAB)


def _reset(page: Face1Page, probe: _Probe) -> None:
    page.click_button("new")
    page.wait_notification("New minimal six-sheet Core workbook created")
    page.open_tab("seq")
    rows, columns = page.grid_dimensions()
    probe.that(rows >= 1 and columns >= 2, "new project did not render an editable FW_Seq grid")


def _grid_data_sync(page: Face1Page, profile: str, probe: _Probe) -> None:
    project_name = f"face1_e2e_{profile}"
    third_value = "third" if profile == "compact" else "third value with spaces"
    page.set_field("project", project_name)
    page.click_cell(1, 0, double=True)
    dialog = page.visible_dialog()
    page.click_button("dialog_cancel", scope=dialog)
    page.click_cell(1, 0, double=True)
    dialog = page.visible_dialog()
    page.set_field("target_name", "DATA_MAIN", scope=dialog)
    page.set_field("target_prefix", "pre_", scope=dialog)
    page.set_field("target_suffix", "_out", scope=dialog)
    delete_buttons = [
        button for button in _displayed(dialog.find_elements(By.CSS_SELECTOR, "button"))
        if "delete_outline" in _normalized(button.get_attribute("textContent") or button.text)
    ]
    probe.that(len(delete_buttons) == 2, "target editor did not expose one delete action per data row")
    delete_buttons[-1].click()
    page.click_button("target_add_data", scope=dialog)
    page.click_button("target_add_data", scope=dialog)
    dialog = page.visible_dialog()
    named = {
        page.field(name, scope=dialog).id
        for name in ("target_name", "target_prefix", "target_suffix")
    }
    data_inputs = [
        item for item in _displayed(dialog.find_elements(By.CSS_SELECTOR, "input"))
        if item.id not in named
    ]
    probe.that(len(data_inputs) == 3, f"expected three data inputs after delete/add, got {len(data_inputs)}")
    _set_input(data_inputs[1], "alternative")
    _set_input(data_inputs[-1], third_value)
    page.click_button("target_save", scope=dialog)
    page.wait_notification("Saved target and 3 data cells")

    page.open_tab("data")
    page.wait_text("DATA_MAIN")
    page.wait_text(third_value)
    probe.that("DATA_MAIN" in page.body_text and third_value in page.body_text,
               "Data sheets did not receive the target-editor state")

    page.open_tab("sheet_names")
    page.wait_text("pre_")
    page.wait_text("_out")
    probe.that("DATA_MAIN" in page.body_text, "FW_SheetNames did not receive the target state")

    page.open_tab("run")
    page.wait_text("3 exact · S")
    probe.that("3 exact · S" in page.body_text, "runtime plan did not see the third data value")
    page.open_tab("seq")
    probe.that(
        page.field_value("project") == project_name,
        "project name did not survive cross-tab refreshes",
    )


def _grid_structure(page: Face1Page, profile: str, probe: _Probe) -> None:
    rows0, columns0 = page.grid_dimensions()
    page.click_button("add_rows")
    page.click_button("add_column")
    rows1, columns1 = page.grid_dimensions()
    probe.that(rows1 == rows0 + 5, "+5 rows did not add five physical display rows")
    probe.that(columns1 == columns0 + 1, "+ column did not add one directive column")

    page.click_cell(rows1, 0, double=True)
    dialog = page.visible_dialog()
    page.click_button("target_delete_row", scope=dialog)
    rows1 -= 1
    probe.that(page.grid_dimensions() == (rows1, columns1),
               "Delete FW_Seq row did not remove exactly one physical row")

    page.click_row_icon(2, "row_up")
    page.click_row_icon(1, "row_down")
    probe.that(page.grid_dimensions() == (rows1, columns1), "row moves changed the grid shape")

    page.click_button("insert_brace_trio")
    page.wait_text("FW_(")
    probe.that("FW_Exclude" in page.body_text and "FW_(" in page.body_text,
               "brace-trio helper did not build the three-row positional pattern")
    page.click_button("validate")
    notification = page.wait.until(
        lambda d: next(
            (item for item in _displayed(d.find_elements(By.CSS_SELECTOR, ".q-notification"))
             if any(token in item.text for token in ("positional contract", "Valid with", "error(s)"))),
            False,
        )
    )
    probe.that(bool(notification.text), "validation action did not produce a classified result")


def _template_catalog(page: Face1Page, profile: str, probe: _Probe) -> None:
    tiles = _displayed(page.driver.find_elements(By.CSS_SELECTOR, page.selectors.value("patterns", "template_css")))
    probe.that(len(tiles) == len(TEMPLATES),
               f"template palette has {len(tiles)} tiles, expected {len(TEMPLATES)}")
    visible_titles = {
        _normalized(tile.find_element(By.CSS_SELECTOR, ".template-title").text)
        for tile in tiles
    }
    for template in TEMPLATES:
        probe.that(_normalized(template.label) in visible_titles,
                   f"template label {template.label!r} is absent or clipped from the DOM")

    page.click_cell(1, 1, double=True)
    dialog = page.visible_dialog()
    original = page.field("directive_value", scope=dialog).get_attribute("value") or ""
    page.click_button("dialog_cancel", scope=dialog)
    page.click_cell(1, 1, double=True)
    dialog = page.visible_dialog()
    page.click_button("directive_clear", scope=dialog)
    page.drag_template("Choose · one", 1, 1)
    probe.that("FW_Combi(1)" in page.grid_cell(1, 1).text,
               "HTML5 template drag/drop did not restore the cleared B1 directive")

    rows, columns = page.grid_dimensions()
    if columns < 5:
        for _ in range(5 - columns):
            page.click_button("add_column")
    for column, title, expected in (
        (2, "FW_Optional", "FW_Optional"),
        (3, "FW_Group", "FW_Group"),
        (4, "ReplaceRE", "FW_ReplaceRE"),
    ):
        page.drag_template(title, 1, column)
        probe.that(expected in page.grid_cell(1, column).text,
                   f"{title} did not land in its exact target cell")
    page.click_cell(1, 2, double=True)
    dialog = page.visible_dialog()
    page.set_field("directive_value", "FW_Optional", scope=dialog)
    page.click_button("directive_save", scope=dialog)
    page.click_cell(1, 2)
    page.set_css_field("formula", "FW_Optional")
    page.click_button("formula_save")
    page.wait_notification("Saved C1")
    probe.that("FW_Optional" in page.grid_cell(1, 2).text,
               "directive dialog/formula-bar save paths disagreed")
    probe.that(original.startswith("FW_Combi"), "unexpected blank-project B1 baseline")


def _control_sheets(page: Face1Page, profile: str, probe: _Probe) -> None:
    page.open_tab("run_once")
    page.click_button("run_once_edit")
    dialog = page.visible_dialog()
    page.click_button("dialog_cancel", scope=dialog)
    page.click_button("run_once_edit")
    dialog = page.visible_dialog()
    original = page.field_value("run_once_source", scope=dialog)
    probe.that(original == "", "new workbook bootstrap source should start empty")
    page.set_field("run_once_source", CANONICAL_RUN_ONCE_SOURCE, scope=dialog)
    page.click_button("run_once_save", scope=dialog)
    page.wait_notification("Saved FW_RunMeFirstOnce A1")
    page.click_button("run_once_edit")
    dialog = page.visible_dialog()
    page.click_button("run_once_clear", scope=dialog)
    page.wait_notification("Cleared FW_RunMeFirstOnce A1")
    page.click_button("run_once_edit")
    dialog = page.visible_dialog()
    page.set_field("run_once_source", CANONICAL_RUN_ONCE_SOURCE, scope=dialog)
    page.click_button("run_once_save", scope=dialog)
    page.wait_notification("Saved FW_RunMeFirstOnce A1")
    probe.that("FW_ARGS" in page.body_text, "bootstrap clear/save round trip did not refresh the tab")

    page.open_tab("arguments")
    page.click_button("argument_add")
    dialog = page.visible_dialog()
    page.click_button("dialog_cancel", scope=dialog)
    page.click_button("argument_add")
    dialog = page.visible_dialog()
    page.set_field("argument_value", "--face1-e2e", scope=dialog)
    page.click_button("argument_save", scope=dialog)
    page.wait_text("--face1-e2e")
    probe.that("--face1-e2e" in page.body_text, "FW_Arguments save did not refresh its sheet")
    page.double_click_control_text("--face1-e2e")
    dialog = page.visible_dialog()
    page.click_button("argument_delete", scope=dialog)
    page.wait_notification("Deleted FW_Arguments row")
    probe.that("--face1-e2e" not in page.body_text, "FW_Arguments delete did not refresh its sheet")

    page.open_tab("custom_var")
    page.click_button("verdict_add")
    dialog = page.visible_dialog()
    page.set_field("verdict_code", "not-an-int", scope=dialog)
    page.click_button("verdict_save", scope=dialog)
    page.wait_notification("Verdict code must be a Java integer")
    page.click_button("dialog_cancel", scope=dialog)
    page.click_button("verdict_add")
    dialog = page.visible_dialog()
    page.set_field("verdict_code", "9", scope=dialog)
    page.set_field("verdict_message", f"e2e-{profile}", scope=dialog)
    page.click_button("verdict_save", scope=dialog)
    page.wait_text(f"e2e-{profile}")
    probe.that(f"e2e-{profile}" in page.body_text, "FW_CUSTOM_VAR save did not refresh its sheet")
    page.double_click_control_text("9", exact=True)
    dialog = page.visible_dialog()
    page.click_button("verdict_delete", scope=dialog)
    page.wait_notification("Deleted FW_CUSTOM_VAR row")
    probe.that(f"e2e-{profile}" not in page.body_text, "FW_CUSTOM_VAR delete did not refresh its sheet")

    page.open_tab("info")
    probe.that("DIMENSION_1" in page.body_text and "FW_Combi(1)" in page.body_text,
               "FW_Info live mirror is disconnected from the composed sequence")


def _runtime_essentials(page: Face1Page, profile: str, probe: _Probe) -> None:
    page.open_tab("run")
    page.open_expansion("command")
    page.set_field("database", f"face1_e2e_{profile}")
    page.set_field("run_id", f"ui-{profile}")
    page.set_field("goals", "latency_ms:min")
    if profile == "expanded":
        page.select_option("candidate_language", "Java")
        page.select_option("analysis_contract", "Formal")
        page.select_option("execution_policy", "Generated / untrusted — sandboxed (recommended)")
        page.select_option("candidate_transport", "Loose files")
    else:
        page.select_option("candidate_language", "Python")
        page.select_option("analysis_contract", "Exploratory")
        page.select_option("execution_policy", "Trusted local — NO SANDBOX, host access")
        page.select_option("candidate_origin", "locally-authored")
        page.set_field("trusted_local_reason", "operator reviewed the local Face 1 E2E workbook")
    page.select_option("run_mode", "Verdict")
    probe.that("--analyzer latency_ms:min" in page.command_text(),
               "essential goal did not propagate into the launch command")

    main_port = page.field("main_db_port")
    original_port = main_port.get_attribute("value") or "5433"
    _set_input(main_port, int(float(original_port)) + 100)
    page.wait_text("recheck needed")
    probe.that("Configuration changed; run Check engine again." in page.body_text,
               "engine readiness did not invalidate after a port edit")
    page.set_field("main_db_port", original_port)
    page.click_button("check_engine")
    page.wait_text("engine ready")
    probe.that("engine ready" in page.body_text, "engine readiness did not recover after restoring the port")

    page.set_checkbox("draw", True)
    probe.that(page.checkbox_value("sieve") and not page.checkbox_value("draw_exact"),
               "pre-Core Face 2 did not enforce sieve/exclusive draw state")
    page.set_checkbox("draw_exact", True)
    probe.that(page.checkbox_value("sieve") and not page.checkbox_value("draw"),
               "exact Face 2 did not enforce sieve/exclusive draw state")
    page.set_checkbox("draw_exact", False)
    page.set_checkbox("allow_extreme", True)
    probe.that(page.checkbox_value("allow_extreme"), "Allow extreme did not update")
    page.set_checkbox("allow_extreme", False)

    page.click_button("plan_only")
    page.wait_notification("Plan:")
    page.click_button("run_workbook")
    dialog = page.visible_dialog()
    probe.that("exact validated workbook" in dialog.text, "real-run confirmation omits exact-XLSX semantics")
    page.click_button("dialog_cancel", scope=dialog)
    page.click_button("run_face2")
    dialog = page.visible_dialog()
    probe.that("Face 2 will pause" in dialog.text, "Face 2 confirmation omits the browser pause warning")
    page.click_button("dialog_cancel", scope=dialog)


_ADVANCED_SAMPLES = {
    "seedFrom": "/tmp/face1-seed.json",
    "explorationFloor": "0.25",
    "minWinnerSupport": "5",
    "sandboxNetworkAllowlist": "localhost:8080",
    "sandboxCandidateEnv": "FACE1_E2E_FLAG=1",
    "executorTolerateOutcomes": "BROKEN",
    "sandboxPolicy": "e2e",
    "executorCompiler": "adaptive",
    "coreTimeout": "30",
    "readerTimeout": "30",
    "executorTimeout": "60",
    "budgetMandatoryRows": "1000",
    "budgetFinalCandidates": "1000",
    "budgetDiskBytes": "1048576",
    "budgetInodes": "1000",
    "budgetWallTimeSeconds": "60",
    "budgetRequests": "100",
    "budgetMonetaryCost": "1.00",
    "budgetWarnFraction": "0.5",
    "costPerCandidate": "0.01",
    "overrideBudget": "e2e-reviewed",
    "repeat": "2",
    "repeatPolicy": "local",
    "repeatScope": "metrics",
    "repeatEnvironments": "2",
    "scratchRoot": "/tmp/face1-e2e",
    "coreJar": "/tmp/core.jar",
    "readerJar": "/tmp/reader.jar",
    "coreProps": "/tmp/core.properties",
    "readerProps": "/tmp/reader.properties",
    "pyExecutor": "/tmp/py_executor.py",
    "javaExecutorJar": "/tmp/executor.jar",
    "javaJarsDir": "/tmp/jars",
    "javaCmd": "java",
    "javacCmd": "javac",
    "pythonCmd": "python3",
    "configFile": "/tmp/bundle.json",
    "baseUrl": "http://127.0.0.1:8121",
    "workers": "2",
    "duration": "2",
    "ramp": "1",
    "sloP99": "1500",
    "errBudget": "0.01",
}


ADVANCED_FLOW_GROUPS = {
    "runtime_advanced_budgets": ("budgets", frozenset({
        "budgetMandatoryRows", "budgetFinalCandidates", "budgetDiskBytes", "budgetInodes",
        "budgetWallTimeSeconds", "budgetRequests", "budgetMonetaryCost", "budgetWarnFraction",
        "costPerCandidate", "overrideBudget", "unleash",
    })),
    "runtime_advanced_sandbox": ("sandbox", frozenset({
        "sandboxNetworkAllowlist", "sandboxCandidateEnv", "executorTolerateOutcomes",
        "sandboxPolicy", "executorCompiler", "seedFrom", "seedOutput", "explorationFloor",
        "minWinnerSupport",
    })),
    "runtime_advanced_repeat": ("repeat", frozenset({
        "repeat", "repeatPolicy", "repeatScope", "repeatEnvironments",
    })),
    "runtime_advanced_infra_paths": ("infrastructure", frozenset({
        "scratchRoot", "coreJar", "readerJar", "coreProps", "readerProps", "pyExecutor",
        "javaExecutorJar", "javaJarsDir", "configFile",
    })),
    "runtime_advanced_infra_commands": ("infrastructure", frozenset({
        "coreTimeout", "readerTimeout", "executorTimeout", "javaCmd", "javacCmd", "pythonCmd",
        "legacyScratch", "legacyHandoff", "debug",
    })),
    "runtime_advanced_stress": ("stress", frozenset({
        "baseUrl", "workers", "duration", "ramp", "sloP99", "errBudget",
    })),
}


def _runtime_advanced(
    page: Face1Page,
    profile: str,
    probe: _Probe,
    flow_name: str,
) -> None:
    expansion, selected_keys = ADVANCED_FLOW_GROUPS[flow_name]
    page.open_tab("run")
    page.select_option("run_mode", "Stress")
    page.open_expansion("advanced")
    page.open_expansion(expansion)
    page.open_expansion("command")

    for key, flag, kind in supported_control_fields():
        if key not in selected_keys:
            continue
        if kind == "bool":
            was_checked = page.advanced_checkbox_value(flag)
            if not was_checked:
                page.set_advanced_checkbox(flag, True)
            propagated = page.wait.until(lambda _d, token=flag: token in page.command_text())
            probe.that(propagated, f"advanced boolean {key} did not reach command preview")
            if not was_checked:
                page.set_advanced_checkbox(flag, False)
        else:
            sample = _ADVANCED_SAMPLES.get(key)
            probe.that(sample is not None, f"no safe E2E sample is defined for advanced field {key}")
            original = page.advanced_field_value(flag)
            page.set_advanced_field(flag, sample)
            propagated = page.wait.until(
                lambda _d, token=flag, value=sample:
                token in page.command_text() and value in page.command_text()
            )
            probe.that(propagated, f"advanced field {key} did not reach command preview")
            page.set_advanced_field(flag, original)
    probe.that("password" not in page.command_text().lower(),
               "launch preview exposed a password-shaped argument")


def _advanced_flow(flow_name: str):
    def execute(page: Face1Page, profile: str, probe: _Probe) -> None:
        _runtime_advanced(page, profile, probe, flow_name)
    return execute


def _modal_guardrails(page: Face1Page, profile: str, probe: _Probe) -> None:
    page.click_button("import_xlsx")
    dialog = page.visible_dialog()
    probe.that("reference-only" in dialog.text, "import dialog omits the example/reference boundary")
    page.click_button("upload_close", scope=dialog)

    page.open_tab("seq")
    page.click_button("helper_open")
    dialog = page.visible_dialog()
    page.click_button("dialog_cancel", scope=dialog)
    page.click_button("helper_open")
    dialog = page.visible_dialog()
    page.set_field("helper_name", "", scope=dialog)
    page.click_button("helper_save", scope=dialog)
    page.wait_notification("Helper sheet needs a name")
    page.set_field("helper_name", f"HELPER_{profile.upper()}", scope=dialog)
    page.set_field("helper_values", "alpha\nbeta", scope=dialog)
    page.click_button("helper_save", scope=dialog)
    page.open_tab("data")
    page.wait_text(f"HELPER_{profile.upper()}")
    probe.that("alpha" in page.body_text and "beta" in page.body_text,
               "helper dialog did not propagate values to Data sheets")

    page.open_tab("run")
    page.open_expansion("scenarios")
    page.click_button("scenario_inspect")
    dialog = page.visible_dialog()
    probe.that("mandatory Core product" in dialog.text,
               "scenario inspector did not show its computed plan")
    page.click_button("dialog_close", scope=dialog)
    page.click_button("scenario_run")
    dialog = page.visible_dialog()
    probe.that("not a simulation" in dialog.text, "scenario confirmation omits real-run disclosure")
    page.click_button("dialog_cancel", scope=dialog)


def _download_import(page: Face1Page, profile: str, probe: _Probe) -> None:
    started = time.time() - 0.1
    page.open_tab("seq")
    page.set_field("project", f"roundtrip_{profile}")
    page.click_button("download_xlsx")
    workbook = page.wait_download(".xlsx", since=started)
    probe.that(workbook.stat().st_size > 1000, "downloaded workbook is unexpectedly small")
    page.click_button("new")
    page.click_button("import_xlsx")
    page.upload(workbook)
    page.wait_notification("Imported")
    page.open_tab("seq")
    probe.that(f"roundtrip_{profile}" in page.body_text, "download/import did not restore project identity")
    page.open_tab("data")
    probe.that("DIMENSION_1" in page.body_text, "download/import did not restore the source data sheet")



def _runnable_default_workbook(page: Face1Page, probe: _Probe) -> None:
    page.open_tab("seq")
    page.click_cell(1, 0, double=True)
    dialog = page.visible_dialog()
    page.set_field("target_name", "BODY", scope=dialog)
    named = {
        page.field(name, scope=dialog).id
        for name in ("target_name", "target_prefix", "target_suffix")
    }
    data_inputs = [
        item for item in _displayed(dialog.find_elements(By.CSS_SELECTOR, "input"))
        if item.id not in named
    ]
    probe.that(len(data_inputs) == 2, "default runnable workbook must expose two source values")
    for index, element in enumerate(data_inputs, 1):
        source = (
            f'_p="F"+"W"+"_"; globals()[_p+"VAR"]=0; globals()[_p+"CUSTOM_VAR"]=0; '
            f'print("app=face1_nested candidate={index} correct=1 latency_ms={index} "+_p+"VAR=0")'
        )
        _set_input(element, source)
    page.click_button("target_save", scope=dialog)
    page.wait_notification("Saved target and 2 data cells")
    page.open_tab("run_once")
    page.click_button("run_once_edit")
    dialog = page.visible_dialog()
    page.set_field("run_once_source", CANONICAL_RUN_ONCE_SOURCE, scope=dialog)
    page.click_button("run_once_save", scope=dialog)
    page.wait_notification("Saved FW_RunMeFirstOnce A1")


def _wait_real_results(page: Face1Page, timeout: float = 240.0) -> str:
    from selenium.webdriver.support.ui import WebDriverWait

    def terminal(_driver):
        body = page.body_text
        if "Real run results" in body:
            return body
        if ("FAILED · exit" in body or "INTERRUPTED · exit" in body) and "running" not in body:
            raise AssertionError("inner Bundle did not succeed: " + _normalized(body)[-700:])
        return False

    return WebDriverWait(page.driver, timeout).until(terminal)


def _runtime_real_run(page: Face1Page, profile: str, probe: _Probe) -> None:
    import uuid
    from .orchestrator import DatabaseSet

    token = uuid.uuid4().hex[:10]
    db_name = f"face1_ui_{token}"
    with DatabaseSet(db_name):
        _runnable_default_workbook(page, probe)
        page.open_tab("run")
        page.open_expansion("command")
        page.set_field("database", db_name)
        page.set_field("run_id", f"ui-real-{token}")
        page.set_field("goals", "correct:max,latency_ms:min")
        page.select_option("analysis_contract", "Formal")
        page.click_button("check_engine")
        page.wait_text("engine ready")
        page.click_button("run_workbook")
        dialog = page.visible_dialog()
        page.click_button("dialog_start_run", scope=dialog)
        body = _wait_real_results(page)
        probe.that("SUCCEEDED · exit 0" in body, "real workbook run did not finish successfully")
        counts = page.result_counts()
        probe.that(
            counts == {
                "Processed": 2, "Pass": 2, "Domain fail": 0,
                "Broken": 0, "Timeout": 0, "Infra fail": 0,
            },
            f"real result strip did not reconcile both passing candidates: {counts}",
        )
        body_folded = body.casefold()
        probe.that(all(stage in body_folded for stage in ("core", "reader", "executor", "analyzer")),
                   "real run did not expose every stage")
        log_values = [
            str(item.get_attribute("value") or "")
            for item in _displayed(page.driver.find_elements(By.CSS_SELECTOR, "textarea[readonly]"))
        ]
        probe.that(any("process exited with code 0" in value for value in log_values),
                   "live log did not receive the worker's terminal state")

        started = time.time() - 0.1
        page.click_button("export_results_json")
        result_json = page.wait_download(".json", since=started)
        page.click_button("export_pareto_csv")
        result_csv = page.wait_download(".csv", since=started)
        probe.that(result_json.stat().st_size > 100 and result_csv.stat().st_size > 20,
                   "real result exports were empty")


def _runtime_cancel(page: Face1Page, profile: str, probe: _Probe) -> None:
    import uuid
    from selenium.webdriver.support.ui import WebDriverWait
    from .orchestrator import DatabaseSet

    token = uuid.uuid4().hex[:10]
    db_name = f"face1_cancel_{token}"
    with DatabaseSet(db_name):
        page.open_tab("run")
        page.set_field("database", db_name)
        page.set_field("run_id", f"ui-cancel-{token}")
        page.click_button("run_workbook")
        dialog = page.visible_dialog()
        page.click_button("dialog_start_run", scope=dialog)
        page.wait_text("running")
        page.click_button("run_cancel")
        page.wait_notification("Cancellation requested")
        WebDriverWait(page.driver, 60).until(
            lambda _d: re.search(r"exit -?\d+", page.body_text)
        )
        probe.that("running" not in page.body_text,
                   "cancelled inner Bundle remained in running state")


def _scenario_real_run(page: Face1Page, profile: str, probe: _Probe) -> None:
    import uuid
    from .orchestrator import DatabaseSet
    from face1_new.runtime_model import load_verified_examples

    example = next(item for item in load_verified_examples() if int(item.get("candidates", 0)) == 1)
    token = uuid.uuid4().hex[:10]
    db_name = f"face1_example_{token}"
    with DatabaseSet(db_name):
        page.open_tab("run")
        page.set_field("database", db_name)
        page.set_field("run_id", f"ui-example-{token}")
        page.open_expansion("scenarios")
        page.select_option("scenario", str(example["title"]))
        page.click_button("scenario_run")
        dialog = page.visible_dialog()
        probe.that("expected historical result 1/1 PASS" in dialog.text,
                   "one-candidate scenario confirmation lost its verified expectation")
        page.click_button("dialog_start_example", scope=dialog)
        body = _wait_real_results(page)
        probe.that("SUCCEEDED · exit 0" in body, "verified example did not finish successfully")
        counts = page.result_counts()
        probe.that(
            counts == {
                "Processed": 1, "Pass": 1, "Domain fail": 0,
                "Broken": 0, "Timeout": 0, "Infra fail": 0,
            },
            f"verified example result strip did not reconcile its one passing candidate: {counts}",
        )


_FLOW_FUNCTIONS: dict[str, Callable[[Face1Page, str, _Probe], None]] = {
    "grid_data_sync": _grid_data_sync,
    "grid_structure": _grid_structure,
    "template_catalog": _template_catalog,
    "control_sheets": _control_sheets,
    "runtime_essentials": _runtime_essentials,
    **{flow: _advanced_flow(flow) for flow in ADVANCED_FLOW_GROUPS},
    "modal_guardrails": _modal_guardrails,
    "download_import": _download_import,
    "runtime_real_run": _runtime_real_run,
    "runtime_cancel": _runtime_cancel,
    "scenario_real_run": _scenario_real_run,
}


def run_flow(page: Face1Page, flow: str, data_profile: str = "compact") -> FlowResult:
    """Run one independently composable action flow and return Bundle-friendly metrics."""
    started = time.perf_counter()
    probe = _Probe()
    try:
        if flow not in _FLOW_FUNCTIONS:
            raise ValueError(f"unknown Face 1 E2E flow {flow!r}; expected one of {FLOW_NAMES}")
        if data_profile not in {"compact", "expanded"}:
            raise ValueError("data_profile must be compact or expanded")
        page.open()
        _reset(page, probe)
        _FLOW_FUNCTIONS[flow](page, data_profile, probe)
        page.assert_no_browser_errors()
        return FlowResult(flow, True, probe.checks, (time.perf_counter() - started) * 1000)
    except Exception as exc:  # candidate result, not an unclassified Executor crash
        import traceback
        frames = traceback.extract_tb(exc.__traceback__)
        frame = next(
            (item for item in reversed(frames) if f"{chr(47)}face1_new{chr(47)}" in item.filename),
            frames[-1],
        )
        location = f"{frame.filename.rsplit(chr(47), 1)[-1]}:{frame.lineno}:{frame.name}"
        error = re.sub(r"\s+", " ", f"{type(exc).__name__} at {location}: {exc}").strip()[:500]
        return FlowResult(flow, False, probe.checks, (time.perf_counter() - started) * 1000, error)
