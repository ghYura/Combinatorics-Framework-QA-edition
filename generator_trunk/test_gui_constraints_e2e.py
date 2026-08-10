#!/usr/bin/env python3
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

"""End-to-end acceptance for the GUI constraints/sieve layer.

The test simulates the user's GUI submit without opening a browser: Bundle's
`stage_draw` still receives the exact sidecar shape produced by the editor, saves
`sidecar.json`, and the normal Core -> Sieve -> Reader -> Executor -> Analyzer
metric path consumes it.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "constraints"))

import fwgen as fg  # noqa: E402
import editor as ed  # noqa: E402
import serve as editor_serve  # noqa: E402
import sieve as sv  # noqa: E402
from bundle import config, stages  # noqa: E402

_FIXTURE_SPEC = HERE / "usecases" / "gui_constraints_e2e" / "gui_checkout.toml"


def _db_connect(host, port, user, password, database):
    import pg8000.dbapi
    return pg8000.dbapi.connect(
        host=host,
        port=int(port),
        user=user,
        password=password,
        database=database,
    )


def _database_endpoints(cfg):
    return [
        (cfg.main_db_host, int(cfg.main_db_port), cfg.main_db_user, cfg.main_db_password),
        (cfg.results_db_host, int(cfg.results_db_port), cfg.results_db_user, cfg.results_db_password),
    ]


def _create_database(endpoint, name):
    host, port, user, password = endpoint
    admin = _db_connect(host, port, user, password, "postgres")
    admin.autocommit = True
    cur = admin.cursor()
    cur.execute(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        "WHERE datname=%s AND pid<>pg_backend_pid();",
        (name,),
    )
    cur.execute(f'DROP DATABASE IF EXISTS "{name}";')
    cur.execute(f'CREATE DATABASE "{name}";')
    cur.close()
    admin.close()


def _drop_database(endpoint, name):
    host, port, user, password = endpoint
    try:
        admin = _db_connect(host, port, user, password, "postgres")
    except Exception:
        return
    admin.autocommit = True
    cur = admin.cursor()
    cur.execute(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        "WHERE datname=%s AND pid<>pg_backend_pid();",
        (name,),
    )
    cur.execute(f'DROP DATABASE IF EXISTS "{name}";')
    cur.close()
    admin.close()


def _require_bundle_runtime(cfg):
    if shutil.which("java") is None:
        pytest.skip("java unavailable")
    if not stages.CORE_JAR.exists():
        pytest.skip(f"Core jar unavailable: {stages.CORE_JAR}")
    if not stages.READER_JAR.exists():
        pytest.skip(f"Reader jar unavailable: {stages.READER_JAR}")
    py_executor = Path(cfg.py_executor) if cfg.py_executor else stages.PY_EXECUTOR
    if not py_executor.exists():
        pytest.skip(f"Python executor unavailable: {py_executor}")
    for label, password in (
        ("main DB", cfg.main_db_password),
        ("results DB", cfg.results_db_password),
    ):
        if not password:
            pytest.skip(f"{label} password not configured")


def _gui_sidecar_for(spec):
    values = {slot.sheet: [str(value).strip() for value in slot.values] for slot in spec.slots}
    channel_web, channel_ivr, channel_partner = values["CHANNEL"]
    payment_card, payment_invoice, payment_wire = values["PAYMENT"]
    _region_us, region_eu = values["REGION"]
    _shipping_standard, shipping_express = values["SHIPPING"]
    _review_none, review_auto, review_manual = values["REVIEW"]

    params = {
        "PAYMENT": {
            payment_card: {"risk": 0},
            payment_invoice: {"risk": 1},
            payment_wire: {"risk": 2},
        },
        "REVIEW": {
            values["REVIEW"][0]: {"risk": 0},
            review_auto: {"risk": 1},
            review_manual: {"risk": 2},
        },
        "CHANNEL": {
            channel_web: {"tier": 0},
            channel_ivr: {"tier": 1},
            channel_partner: {"tier": 2},
        },
    }
    bonds = [
        {
            "polarity": "forbid",
            "sides": {"CHANNEL": [channel_partner], "PAYMENT": [payment_invoice]},
            "gate": {},
            "when": None,
        },
        {
            "polarity": "forbid",
            "sides": {
                "PAYMENT": [payment_invoice, payment_wire],
                "REGION": [region_eu],
                "SHIPPING": [shipping_express],
            },
            "gate": {},
            "when": None,
        },
        {
            "polarity": "forbid",
            "sides": {"CHANNEL": [channel_ivr], "PAYMENT": [payment_wire], "REVIEW": [review_auto]},
            "gate": {},
            "when": None,
        },
        {
            "polarity": "forbid",
            "sides": {"PAYMENT": [], "REVIEW": []},
            "gate": {},
            "when": "PAYMENT.risk + REVIEW.risk > 3",
        },
    ]
    sidecar = ed.bonds_to_sidecar(bonds, params)
    assert sv.validate_sidecar(sidecar)["unsupported_constraint_count"] == 0
    return sidecar


def _decode_fw_final(conn, spec):
    code2val, baseline, combos_col, order = sv.build_maps_from_db(conn, "fw_final", spec.slots)
    rows, _opts = sv.decode_assembly(conn, "fw_final", code2val, order, combos_col, baseline, set(), [])
    return rows, code2val, baseline, combos_col, order


def _assert_runtime_metrics(metrics_path: Path, expected_count: int):
    lines = [line.strip() for line in metrics_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == expected_count
    assert all("app=gui_constraints_checkout" in line for line in lines)
    assert all("pruned_violation=0" in line for line in lines)
    assert all("FW_VAR=0" in line for line in lines)
    assert not any("channel=partner payment=invoice" in line for line in lines)
    assert not any("payment=wire" in line and "review=manual" in line for line in lines)
    assert not any(
        "payment=invoice" in line and "region=eu shipping=express" in line
        for line in lines
    )
    assert not any(
        "payment=wire" in line and "region=eu shipping=express" in line
        for line in lines
    )
    assert not any("channel=ivr payment=wire" in line and "review=auto" in line for line in lines)


def test_gui_drawn_constraints_drive_full_bundle_workflow(monkeypatch):
    cfg, _sources = config.resolve_config(cli={})
    _require_bundle_runtime(cfg)

    tmpdb = "fw_gui_e2e_" + uuid.uuid4().hex[:12]
    endpoints = []
    for endpoint in _database_endpoints(cfg):
        if endpoint in endpoints:
            continue
        try:
            _create_database(endpoint, tmpdb)
        except Exception as exc:  # noqa: BLE001 - any local DB/auth issue should skip this acceptance test
            pytest.skip(f"Postgres endpoint {endpoint[0]}:{endpoint[1]} not usable: {exc}")
        endpoints.append(endpoint)

    scratch = Path(tempfile.mkdtemp(prefix="fw-gui-e2e-"))
    spec_dir = scratch / "spec"
    spec_dir.mkdir()
    shutil.copy2(_FIXTURE_SPEC, spec_dir / _FIXTURE_SPEC.name)

    try:
        spec = fg.load_spec(spec_dir / _FIXTURE_SPEC.name)
        assert fg.estimate_core_combos(spec) == 108
        gui_sidecar = _gui_sidecar_for(spec)

        captured = {}

        def fake_serve_editor(sheets, initial, **kwargs):
            captured["sheets"] = sheets
            captured["initial"] = initial
            captured["kwargs"] = kwargs
            return gui_sidecar

        monkeypatch.setattr(editor_serve, "serve_editor", fake_serve_editor)
        constraints, params = stages.stage_draw(spec, scratch, cfg=cfg)
        spec.constraints = constraints
        spec.params = params

        assert set(captured["sheets"]) == {"CHANNEL", "PAYMENT", "REGION", "SHIPPING", "REVIEW"}
        assert captured["initial"] == {"version": 1, "params": {}, "constraints": []}
        saved_sidecar = json.loads((scratch / "sidecar.json").read_text(encoding="utf-8"))
        assert saved_sidecar["constraints"] == gui_sidecar["constraints"]
        assert saved_sidecar["params"] == gui_sidecar["params"]

        xlsx = stages.stage_gen(spec_dir, scratch)
        n_core = stages.stage_core(spec, xlsx, scratch, tmpdb, cfg.main_db_port, n_opt=0, cfg=cfg)
        assert n_core == 108

        conn = _db_connect(cfg.main_db_host, cfg.main_db_port, cfg.main_db_user, cfg.main_db_password, tmpdb)
        rows, code2val, baseline, combos_col, order = _decode_fw_final(conn, spec)
        pure = sv.sieve(rows, gui_sidecar)
        assert pure["scanned"] == 108
        assert pure["matched"] == {
            "bond0_CHANNEL_PAYMENT": 12,
            "bond1_CHANNEL_PAYMENT_REVIEW": 4,
            "mm0_PAYMENT_REGION_SHIPPING": 18,
            "when0_PAYMENT_REVIEW": 12,
        }
        assert pure["total_rule_matches"] == 46
        assert pure["unique_removals"] == 39
        assert pure["overlap"] == 7
        assert pure["retained"] == 69

        dry = sv.sieve_fw_final(
            conn,
            "fw_final",
            gui_sidecar,
            code2val,
            order,
            combos_col,
            id_col="combi_id",
            baseline=baseline,
            dry_run=True,
        )
        assert dry["matched"] == pure["matched"]
        assert dry["unique_removals"] == pure["unique_removals"]
        assert dry["retained"] == pure["retained"]
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM fw_final;")
        assert cur.fetchone()[0] == 108
        cur.close()
        conn.close()

        n_after_sieve = stages.stage_sieve(spec, scratch, tmpdb, cfg.main_db_port, n_core, cfg=cfg)
        assert n_after_sieve == 69

        src, hs, n_cands, empty, _manifest_path = stages.stage_reader(
            scratch,
            tmpdb,
            "py",
            cfg.main_db_port,
            cfg.results_db_port,
            n_after_sieve,
            n_opt=0,
            full=n_after_sieve,
            cfg=cfg,
            run_id="gui-e2e",
            legacy_handoff=True,
        )
        assert empty == 0
        assert n_cands == 69
        reader_props = (scratch / "reader_cwd" / "fw.properties").read_text(encoding="utf-8")
        assert "reader.core.concatenator=\\n\n" in reader_props

        metrics_path = scratch / "metrics.kv"
        processed, passed, failed, broken, inserted, db_total, timeout, infra_fail, _v2 = stages.stage_executor(
            src,
            hs,
            tmpdb,
            cfg.results_db_port,
            cfg=cfg,
            manifest_path=None,
            run_id="gui-e2e",
            metrics_path=metrics_path,
            language="python",
        )
        assert (processed, passed, failed, broken, inserted, db_total, timeout, infra_fail) == (
            69,
            69,
            0,
            0,
            69,
            69,
            0,
            0,
        )
        _assert_runtime_metrics(metrics_path, 69)

        stages.stage_analyzer(
            src,
            scratch,
            spec.goals_property(),
            cfg=cfg,
            mode="exploratory",
            corpus_count=69,
            run_id="gui-e2e",
            harvested_metrics=metrics_path,
        )
        _assert_runtime_metrics(scratch / "metrics.kv", 69)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        for endpoint in endpoints:
            _drop_database(endpoint, tmpdb)
