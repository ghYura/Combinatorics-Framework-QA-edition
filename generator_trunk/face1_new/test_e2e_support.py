from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path

import pytest

# Tier classification (Prompt 03 Part C): the browser-driven Face 1 E2E suite
# needs Selenium, which lives in the optional `test-full` extra. Without this
# guard a lean install produces a collection ERROR — which reads as a broken
# suite rather than an absent optional backend, and cannot be classified as a
# skip on a release gate.
pytest.importorskip(
    "selenium",
    reason="EXPECTED_OPTIONAL: browser E2E needs the test-full extra (pip install -e '.[browser]')")

import fwgen
from face1_new.e2e.actions import ADVANCED_FLOW_GROUPS, FLOW_NAMES, run_flow
from face1_new.e2e.candidate import FlowResult, endpoint_for, metric_line
from face1_new.e2e.orchestrator import (
    ServerPool,
    _lane_command,
    reserve_free_port,
    server_environment,
)
from face1_new.e2e.page_object import Face1Page, _matches, browser_session
from face1_new.e2e.selectors import DEFAULT_SELECTORS
from face1_new.e2e.spec import build_spec_text, cardinality, partition_flows
from face1_new.e2e.surface_contract import selector_contract_problems
from face1_new.grid_model import TEMPLATES
from face1_new.runtime_model import supported_control_fields


def test_selector_registry_covers_the_whole_current_nicegui_surface():
    assert selector_contract_problems() == []
    actions = (Path(__file__).parent / "e2e" / "actions.py").read_text(encoding="utf-8")
    assert "Balanced sandbox" not in actions and '"Trusted local"' not in actions
    assert len(DEFAULT_SELECTORS.tabs) == 10
    assert len(TEMPLATES) == 55


def test_every_bundle_control_and_dynamic_surface_has_a_locator_pattern():
    fields = supported_control_fields()
    assert len(fields) == len({flag for _key, flag, _kind in fields})
    assert DEFAULT_SELECTORS.value("patterns", "advanced_label_suffix") == " · {flag}"
    for required in ("template_css", "grid_css", "grid_cell_css", "stage_css", "result_table_css"):
        assert DEFAULT_SELECTORS.value("patterns", required)


def test_advanced_flow_slices_partition_the_real_nonessential_registry():
    from face1_new.run_ui import ESSENTIAL_KEYS

    expected = {key for key, _flag, _kind in supported_control_fields()} - ESSENTIAL_KEYS
    slices = [keys for _expansion, keys in ADVANCED_FLOW_GROUPS.values()]
    assert set().union(*slices) == expected
    assert sum(map(len, slices)) == len(expected)


def test_head_inner_tail_spec_has_honest_cardinality_and_order(tmp_path):
    text = build_spec_text()
    path = tmp_path / "face1_dogfood.toml"
    path.write_text(text, encoding="utf-8")
    spec = fwgen.load_spec(path)

    assert [slot.sheet for slot in spec.slots] == [
        "HEAD", "BROWSER", "VIEWPORT", "FLOW", "DATA_PROFILE", "TAIL",
    ]
    assert fwgen.estimate_core_combos(spec) == 52
    assert cardinality(FLOW_NAMES, ("chromium",), ("desktop", "compact"), ("compact", "expanded")) == 52
    assert "execute_candidate" in spec.slots[0].values[0]
    assert 'globals()[_FACE1_VERDICT_PREFIX + "CUSTOM_VAR"]' in spec.slots[-1].values[0]
    assert all("FW_" not in str(value) for slot in spec.slots for value in slot.values)


def test_partitioning_is_complete_balanced_and_deterministic():
    partitions = partition_flows(FLOW_NAMES, 3)
    assert tuple(item for partition in partitions for item in partition) != FLOW_NAMES  # round-robin, not chunks
    assert set(item for partition in partitions for item in partition) == set(FLOW_NAMES)
    assert max(map(len, partitions)) - min(map(len, partitions)) <= 1
    assert partitions == partition_flows(FLOW_NAMES, 3)


def test_candidate_endpoint_and_metric_are_stable_and_safe(monkeypatch):
    monkeypatch.setenv("FACE1_E2E_URLS", "http://127.0.0.1:8101;http://127.0.0.1:8102")
    first = endpoint_for("chromium", "desktop", "grid_data_sync", "compact")
    assert first == endpoint_for("chromium", "desktop", "grid_data_sync", "compact")
    assert first in {"http://127.0.0.1:8101", "http://127.0.0.1:8102"}

    line = metric_line(FlowResult("grid_data_sync", False, 7, 12.5, "secret-ish details"),
                       "chromium", "desktop", "compact")
    assert "correct=0" in line and "FW_VAR=2" in line and "checks=7" in line
    assert "error_type=unclassified" in line and "error_site=none" in line
    assert "secret-ish" not in line and "\n" not in line


def test_semantic_label_matching_survives_css_uppercase_rendering():
    assert _matches("FW_SEQ", "FW_Seq")
    assert _matches("PLAN & RUN", "Plan & run")
    assert _matches(
        "verified Verified scenario library keyboard_arrow_down",
        "Verified scenario library",
    )


def test_reserved_app_port_can_be_bound_immediately():
    import socket

    port = reserve_free_port()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", port))


def test_managed_server_does_not_inherit_nicegui_pytest_mode(monkeypatch):
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "outer test marker")
    monkeypatch.setenv("NICEGUI_SCREEN_TEST_PORT", "12345")
    env = server_environment()
    assert "PYTEST_CURRENT_TEST" not in env
    assert "NICEGUI_SCREEN_TEST_PORT" not in env


def test_bundle_lane_uses_current_direct_spec_cli(tmp_path):
    command, _run_dir, _log = _lane_command(
        0, tmp_path, "face1_e2e_test", "face1-e2e-test", ("http://127.0.0.1:8123",)
    )
    assert command[2] == str(tmp_path / "lane-0" / "spec")
    assert command[2] != "run"
    assert "--py-executor" in command


@pytest.mark.skipif(os.environ.get("FACE1_E2E_LIVE") != "1", reason="set FACE1_E2E_LIVE=1")
def test_two_face1_servers_accept_independent_pageobject_flows(tmp_path):
    def execute(url: str, flow: str):
        downloads = tmp_path / flow
        with browser_session("chromium", downloads, (1200, 900)) as driver:
            return run_flow(Face1Page(driver, url, download_dir=downloads, timeout=20), flow, "compact")

    with ServerPool(tmp_path, 2) as pool:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(execute, pool.urls[0], "grid_data_sync"),
                executor.submit(execute, pool.urls[1], "modal_guardrails"),
            ]
            results = [future.result() for future in futures]
    assert all(result.ok for result in results), results
