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

r"""End-to-end acceptance for the CONTEXTUAL constraint tier over a real-shaped object: the telemetry catalog
`/api/catalog/lookup` request. The SUT (`usecases/telemetry_catalog_e2e/telemetry_lookup.toml`) carries a
`TelemetryLookup` validity engine whose four interdependency rules ARE the conditional sieve constraints:

  • a `mapping`   — SignalClass must belong to DatasetFamily
  • a `condition` — AccessTier=restricted forbidden when DatasetFamily=OpenData
  • a `condition` — AccessTier=restricted forbidden when ExcludeRestricted=enabled
  • a `condition` — Geometry=volumetric forbidden when DatasetFamily=OpenData

The five URL dimensions are FW_Optional, so the same classifier must also handle absent parameters.
The conditional sieve is proven a PERFECT CLASSIFIER of valid vs invalid lookups (the engine itself
is the oracle), then the real Core→Sieve→Reader→Executor pipeline runs only the valid lookups (each
assembles a well-formed URL, FW_VAR=0), with the invalid ones provably never executed.

Run: ``python3 -m pytest test_telemetry_catalog_e2e.py -v``  (the pipeline test needs the dev Postgres
on :5433 / results port + the Core+Reader jars + the Python executor; it self-skips otherwise).
"""
from __future__ import annotations

import itertools
import re
import shutil
import sys
import tempfile
import uuid
from collections import OrderedDict
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "constraints"))

import fwgen as fg          # noqa: E402
import sieve as sv          # noqa: E402
from bundle import config, stages  # noqa: E402
from sut_paths import project_path  # noqa: E402

_SPEC = HERE / "usecases" / "telemetry_catalog_e2e" / "telemetry_lookup.toml"
_DIMS = ("DatasetFamily", "SignalClass", "ExcludeRestricted", "AccessTier", "Geometry")


# --------------------------------------------------------------------------- #
# SUT helpers
# --------------------------------------------------------------------------- #
def _engine(spec):
    ns: dict = {}
    exec(spec.slots[0].values[0], ns)        # HEAD carries the `TelemetryLookup` validity engine
    return ns["TelemetryLookup"]


def _cell_token(cell, sheet):
    ns: dict = {}
    exec(cell, ns)
    return ns[sheet]


def _dimension_maps(spec):
    dims: "OrderedDict[str, list]" = OrderedDict()
    stmt2tok: dict = {}
    for s in spec.slots:
        if s.sheet in _DIMS:
            dims[s.sheet] = [_cell_token(c, s.sheet) for c in s.values]
            stmt2tok[s.sheet] = {str(c).strip(): _cell_token(c, s.sheet) for c in s.values}
    return dims, stmt2tok


def _sidecar(spec):
    """The four conditional constraints, keyed on the EXACT cell strings the sieve decodes."""
    val = {s.sheet: [str(v).strip() for v in s.values] for s in spec.slots if s.sheet in _DIMS}
    f_mobility, f_climate, f_open_data = val["DatasetFamily"]
    s_trajectory, s_radar, s_air_quality = val["SignalClass"]
    exclude_enabled, _exclude_disabled = val["ExcludeRestricted"]
    _access_public, _access_community, access_restricted = val["AccessTier"]
    _geometry_tabular, geometry_volumetric = val["Geometry"]
    return {"version": 1, "params": {}, "constraints": [
        {"id": "r1_signal_by_family",
         "mapping": {"source": "DatasetFamily", "target": "SignalClass",
                     "allow": {f_mobility: [s_trajectory], f_climate: [s_radar], f_open_data: [s_air_quality]}}},
        {"id": "r2_no_restricted_for_open_data", "polarity": "forbid", "sheets": ["AccessTier"], "sets": {"AccessTier": [access_restricted]},
         "condition": {"sheet": "DatasetFamily", "eq": f_open_data}},
        {"id": "r3_restricted_exclusion_conflict", "polarity": "forbid", "sheets": ["AccessTier"], "sets": {"AccessTier": [access_restricted]},
         "condition": {"sheet": "ExcludeRestricted", "eq": exclude_enabled}},
        {"id": "r4_no_volumetric_for_open_data", "polarity": "forbid", "sheets": ["Geometry"], "sets": {"Geometry": [geometry_volumetric]},
         "condition": {"sheet": "DatasetFamily", "eq": f_open_data}},
    ]}


def _domain_with_absent(dims, d):
    return [None] + list(dims[d])


def _ground_truth(TelemetryLookup, dims):
    valid, invalid = set(), set()
    for combo in itertools.product(*(_domain_with_absent(dims, d) for d in _DIMS)):
        (invalid if TelemetryLookup.validate(*combo) else valid).add(combo)
    return valid, invalid


def _cartesian_rows(spec):
    val = {s.sheet: [None] + [str(v).strip() for v in s.values] for s in spec.slots if s.sheet in _DIMS}
    rows = []
    for combo in itertools.product(*(val[d] for d in _DIMS)):
        rows.append([{"sheet": d, "value": v, "pos": i} for i, (d, v) in enumerate(zip(_DIMS, combo))
                     if v is not None])
    return rows


def _combo_of(row, stmt2tok):
    by = {p["sheet"]: stmt2tok[p["sheet"]][p["value"]] for p in row if p["sheet"] in stmt2tok}
    return tuple(by.get(d) for d in _DIMS)


def _tokens_from_text(text):
    out = []
    for d in _DIMS:
        matches = list(re.finditer(rf'{d}\s*=\s*(?:"(\w+)"|None)', text))
        out.append(matches[-1].group(1) if matches and matches[-1].group(1) is not None else None)
    return tuple(out)


# --------------------------------------------------------------------------- #
# DB / runtime helpers (same proven invocation as the reactor e2e)
# --------------------------------------------------------------------------- #
def _connect(host, port, user, password, database):
    import pg8000.dbapi
    return pg8000.dbapi.connect(host=host, port=int(port), user=user, password=password, database=database)


def _endpoints(cfg):
    return [(cfg.main_db_host, int(cfg.main_db_port), cfg.main_db_user, cfg.main_db_password),
            (cfg.results_db_host, int(cfg.results_db_port), cfg.results_db_user, cfg.results_db_password)]


def _create_db(endpoint, name):
    host, port, user, password = endpoint
    admin = _connect(host, port, user, password, "postgres")
    admin.autocommit = True
    cur = admin.cursor()
    cur.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s AND pid<>pg_backend_pid();", (name,))
    cur.execute(f'DROP DATABASE IF EXISTS "{name}";')
    cur.execute(f'CREATE DATABASE "{name}";')
    cur.close(); admin.close()


def _drop_db(endpoint, name):
    host, port, user, password = endpoint
    try:
        admin = _connect(host, port, user, password, "postgres")
    except Exception:
        return
    admin.autocommit = True
    cur = admin.cursor()
    cur.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s AND pid<>pg_backend_pid();", (name,))
    cur.execute(f'DROP DATABASE IF EXISTS "{name}";')
    cur.close(); admin.close()


def _require_runtime(cfg):
    if shutil.which("java") is None:
        pytest.skip("java unavailable")
    if not stages.CORE_JAR.exists():
        pytest.skip(f"Core jar unavailable: {stages.CORE_JAR}")
    if not stages.READER_JAR.exists():
        pytest.skip(f"Reader jar unavailable: {stages.READER_JAR}")
    py_executor = Path(cfg.py_executor) if cfg.py_executor else stages.PY_EXECUTOR
    if not py_executor.exists():
        pytest.skip(f"Python executor unavailable: {py_executor}")
    if not (cfg.main_db_password and cfg.results_db_password):
        pytest.skip("dev DB passwords not configured")


# =========================================================================== #
# A. the conditional constraints are a PERFECT CLASSIFIER (pure, DB-free)
# =========================================================================== #
def test_conditional_constraints_classify_valid_lookups_exactly():
    spec = fg.load_spec(_SPEC)
    assert fg.estimate_core_combos(spec) == 1
    assert fg.optional_multiplier_cardinality(spec).value == 576
    TelemetryLookup = _engine(spec)
    dims, stmt2tok = _dimension_maps(spec)
    valid, invalid = _ground_truth(TelemetryLookup, dims)
    assert (len(valid), len(invalid)) == (300, 276)

    sidecar = _sidecar(spec)
    assert sv.validate_sidecar(sidecar)["unsupported_constraint_count"] == 0

    rows = _cartesian_rows(spec)
    removed = {_combo_of(r, stmt2tok) for r in rows if sv.row_violations(r, sidecar)}
    retained = {_combo_of(r, stmt2tok) for r in rows if not sv.row_violations(r, sidecar)}
    assert removed == invalid, "the conditional sieve removed a different set than the engine flags invalid"
    assert retained == valid, "a valid lookup would be dropped (over-filtering)"

    rep = sv.sieve(rows, sidecar)
    assert (rep["scanned"], rep["unique_removals"], rep["retained"]) == (576, 276, 300)
    # the `mapping` and EACH `condition` rule actually fire (per-rule match counts; overlaps included)
    assert rep["matched"] == {"r1_signal_by_family": 216, "r2_no_restricted_for_open_data": 36,
                              "r3_restricted_exclusion_conflict": 48, "r4_no_volumetric_for_open_data": 48}
    # the live exact preview matches final × optional rows, including the all-absent URL.
    prev = sv.impact_over_rows([[]], [r for r in rows if r], sidecar, set(_DIMS))
    assert prev == {"exact": True, "total": 576, "removed": 276, "kept": 300,
                    "mandatory_rows": 1, "optional_multiplier": 576}


# =========================================================================== #
# B. the conditional sieve drives the WHOLE pipeline; only valid lookups execute
# =========================================================================== #
def test_conditional_sieve_drives_full_telemetry_pipeline():
    cfg, _sources = config.resolve_config(cli={})
    _require_runtime(cfg)

    spec0 = fg.load_spec(_SPEC)
    TelemetryLookup = _engine(spec0)
    dims, stmt2tok = _dimension_maps(spec0)
    valid, invalid = _ground_truth(TelemetryLookup, dims)
    assert (len(valid), len(invalid)) == (300, 276)
    sidecar = _sidecar(spec0)

    tmpdb = "fw_telemetry_" + uuid.uuid4().hex[:12]
    endpoints = []
    for ep in _endpoints(cfg):
        if ep in endpoints:
            continue
        try:
            _create_db(ep, tmpdb)
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"Postgres endpoint {ep[0]}:{ep[1]} not usable: {exc}")
        endpoints.append(ep)

    scratch = Path(tempfile.mkdtemp(prefix="fw-telemetry-"))
    spec_dir = scratch / "spec"; spec_dir.mkdir()
    shutil.copy2(_SPEC, spec_dir / _SPEC.name)
    try:
        spec = fg.load_spec(spec_dir / _SPEC.name)
        assert fg.estimate_core_combos(spec) == 1
        assert fg.optional_multiplier_cardinality(spec).value == 576
        # the authored lookup rules (a GUI Submit would do the same): enforce the conditional bonds
        spec.constraints = sidecar["constraints"]
        spec.params = sidecar["params"]

        xlsx = stages.stage_gen(spec_dir, scratch)
        n_core = stages.stage_core(spec, xlsx, scratch, tmpdb, cfg.main_db_port, n_opt=len(_DIMS), cfg=cfg)
        assert n_core == 1

        conn = _connect(cfg.main_db_host, cfg.main_db_port, cfg.main_db_user, cfg.main_db_password, tmpdb)
        code2val, baseline, combos_col, order = sv.build_maps_from_db(conn, "fw_final", spec.slots)
        rows, _opts = sv.decode_assembly(conn, "fw_final", code2val, order, combos_col, baseline, set(), [])
        assert len(rows) == 1

        cur = conn.cursor()
        cur.execute("select table_name from information_schema.tables where table_name like 'fw_opt%';")
        opt_tables = sorted(r[0] for r in cur.fetchall())
        finals, opts = sv.decode_assembly(conn, "fw_final", code2val, order, combos_col,
                                          baseline, set(_DIMS), opt_tables)
        assembled_rows = finals + [f + o for f in finals for o in opts]
        assert len(assembled_rows) == 576
        # CLASSIFIER over live fw_final × fw_optX: removed == engine-invalid, retained == engine-valid
        removed = {_combo_of(r, stmt2tok) for r in assembled_rows if sv.row_violations(r, sidecar)}
        retained = {_combo_of(r, stmt2tok) for r in assembled_rows if not sv.row_violations(r, sidecar)}
        assert removed == invalid and retained == valid

        preview = sv.impact_over_rows(finals, opts, sidecar, set(_DIMS))
        assert preview["removed"] == 276 and preview["kept"] == 300

        dry = sv.sieve_fw_final(conn, "fw_final", sidecar, code2val, order, combos_col,
                                id_col="combi_id", baseline=baseline, dry_run=True,
                                optional_sheets=set(_DIMS))
        assert (dry["unique_removals"], dry["retained"], dry["deleted"], dry["deferred_count"]) == (0, 1, 0, 4)
        cur.execute("SELECT count(*) FROM fw_final;")
        assert cur.fetchone()[0] == 1
        cur.close(); conn.close()

        n_after = stages.stage_sieve(spec, scratch, tmpdb, cfg.main_db_port, n_core, cfg=cfg)
        assert n_after == 1
        assert (scratch / "optional_bonds.txt").is_file()

        src, hs, n_cands, empty, _mp = stages.stage_reader(
            scratch, tmpdb, "py", cfg.main_db_port, cfg.results_db_port, n_after,
            n_opt=len(_DIMS), full=576, cfg=cfg, run_id="telemetry-e2e", legacy_handoff=True)
        assert (empty, n_cands) == (0, 300)
        assembled = {_tokens_from_text(p.read_text(encoding="utf-8")) for p in Path(src).glob("*.py")}
        assert assembled == valid                          # the surviving candidate sources ARE the valid lookups

        metrics_path = scratch / "metrics.kv"
        processed, passed, failed, broken, inserted, db_total, timeout, infra, _v2 = stages.stage_executor(
            src, hs, tmpdb, cfg.results_db_port, cfg=cfg, manifest_path=None,
            run_id="telemetry-e2e", metrics_path=metrics_path, language="python")
        assert (processed, passed, failed, broken, infra, timeout) == (300, 300, 0, 0, 0, 0)

        lines = [ln for ln in metrics_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert len(lines) == 300
        assert all("app=telemetry_catalog" in ln for ln in lines)
        assert all("valid=1" in ln and "broken=none" in ln and "FW_VAR=0" in ln for ln in lines)
        # no invalid lookup reached execution, and each URL carries its chosen params
        assert not any("FW_VAR=2" in ln or "broken=SIGNAL" in ln or "RESTRICTED_OPEN_DATA" in ln for ln in lines)
        executed = set()
        for ln in lines:
            m = re.search(r"family=(\w+) signal=(\w+) exclude=(\w+) access=(\w+) geometry=(\w+) valid=(\d).* url=(\S+) FW_VAR", ln)
            quad = tuple(None if m.group(i) == "None" else m.group(i) for i in range(1, 6))
            executed.add(quad)
            assert m.group(6) == "1" and TelemetryLookup.validate(*quad) == []          # candidate ↔ engine agree
            url = m.group(7)
            assert "accessKey=key-orbit" in url
            assert "encoding=parquet" in url
            assert url.startswith("http://localhost:8080/api/catalog/lookup/grid-sample")
            if quad[0] is None:
                assert "DatasetFamily=" not in url
            else:
                assert f"DatasetFamily={quad[0]}" in url
        assert executed == valid

        stages.stage_analyzer(src, scratch, spec.goals_property(), cfg=cfg, mode="exploratory",
                              corpus_count=300, run_id="telemetry-e2e", harvested_metrics=metrics_path)
        assert len([ln for ln in (scratch / "metrics.kv").read_text(encoding="utf-8").splitlines()
                    if ln.strip()]) == 300
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        for ep in endpoints:
            _drop_db(ep, tmpdb)

# =========================================================================== #
# C. every unsieved spec form is a well-formed live telemetry request
# =========================================================================== #
def test_unsieved_conditional_spec_is_live_http_interoperable():
    service_dir = project_path("telemetry_catalog")
    if not service_dir.is_dir():
        pytest.skip(f"standalone SUT not found at {service_dir}")
    sys.path.insert(0, str(service_dir))
    try:
        from telemetry_catalog_service import start_server
    except Exception:  # noqa: BLE001
        pytest.skip("standalone service module not importable")
    import json
    import urllib.error
    import urllib.request

    spec = fg.load_spec(_SPEC)
    TelemetryLookup = _engine(spec)
    dims, _stmt2tok = _dimension_maps(spec)
    combos = list(itertools.product(*(_domain_with_absent(dims, d) for d in _DIMS)))
    assert len(combos) == 576

    httpd, port, _thread = start_server()
    live_base = f"http://127.0.0.1:{port}"
    statuses = {200: 0, 400: 0}
    model_valid = 0
    try:
        for combo in combos:
            embedded_url = TelemetryLookup.url("grid-sample", *combo)
            assert "accessKey=key-orbit" in embedded_url
            assert "encoding=parquet" in embedded_url
            live_url = embedded_url.replace("http://localhost:8080", live_base, 1)
            try:
                with urllib.request.urlopen(live_url, timeout=5) as response:  # noqa: S310 (localhost)
                    status = response.status
                    content_type = response.headers.get("Content-Type", "")
                    raw = response.read().decode("utf-8")
            except urllib.error.HTTPError as exc:
                status = exc.code
                content_type = exc.headers.get("Content-Type", "")
                raw = exc.read().decode("utf-8")

            assert status in statuses, f"unexpected HTTP {status} for {embedded_url}"
            statuses[status] += 1
            if status == 400:
                assert content_type.startswith("application/json")
                payload = json.loads(raw)
                assert payload.get("valid") is False
                assert isinstance(payload.get("broken"), list) and payload["broken"]
                assert set(payload.get("detail", {})) == set(payload["broken"])
            else:
                assert content_type.startswith("application/json")
                assert json.loads(raw).get("valid") is True

            if not TelemetryLookup.validate(*combo):
                model_valid += 1
                assert status == 200, f"embedded-valid lookup rejected: {embedded_url}"

        assert model_valid == 300
        assert statuses[200] + statuses[400] == 576
        assert statuses[200] >= model_valid and statuses[400] > 0
    finally:
        httpd.shutdown()
        httpd.server_close()
