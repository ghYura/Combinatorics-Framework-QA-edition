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

r"""End-to-end acceptance for the NESTED value-dependency sieve (task 29062026) over the full telemetry catalog
`/api/catalog/lookup` System-Under-Test.

Three layers, strongest first (see docs/28 §B.5):

  A. PURE CLASSIFIER (DB-free) — a sieve sidecar that mirrors the standalone service's full rule set
     (`telemetry_rules.validate`, the oracle) is proven to remove EXACTLY the invalid lookups over a large
     curated+randomized sample. Every new primitive (presence, ordinal vs constant, ordinal
     cross-field, subset cross-field, mapping, value×value) provably fires.

  B. LIVE HTTP SERVICE — boot the real standalone service
     ($BUNDLE_SUT_ROOT/telemetry_catalog_service) on a random port and assert, over the
     same sample, that sieve-kept ⟺ HTTP 200 and sieve-removed ⟺ HTTP 400 with the SAME broken rule
     ids. This is the literal "verify the constraints layer against the System-under-test."

  C. FULL BUNDLE PIPELINE (needs dev Postgres :5433 + Core/Reader jars + py executor) — the
     first-class input spec `usecases/telemetry_catalog_full/telemetry_lookup_full.toml` (with its
     authored `orders` + nested `assert`/`mapping` bonds) is run through real Core→Sieve→Reader→
     Executor; the sieve deletes exactly the fw_final rows its HEAD engine flags invalid, and only
     valid lookups execute (FW_VAR=0).

Run:  python3 -m pytest test_telemetry_catalog_full_e2e.py -v
"""
from __future__ import annotations

import itertools
import random
import re
import shutil
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "constraints"))

import fwgen as fg          # noqa: E402
import sieve as sv          # noqa: E402
from sut_paths import project_path  # noqa: E402

_SERVICE_DIR = project_path("telemetry_catalog")
if _SERVICE_DIR.is_dir():
    sys.path.insert(0, str(_SERVICE_DIR))


def _telemetry_rules():
    try:
        import telemetry_rules            # noqa: E402
        return telemetry_rules
    except Exception:               # noqa: BLE001
        pytest.skip(f"standalone SUT not found at {_SERVICE_DIR}")


# =========================================================================== #
# The sieve sidecar that MIRRORS telemetry_rules.validate (raw tokens; absent == omitted from the row).
# =========================================================================== #
def _service_sidecar(R) -> dict:
    G = lambda s, **kw: dict(sheet=s, **kw)               # noqa: E731  leaf helper
    cons = [
        {"id": "R_OBLIGATORY_ACCESS_KEY", "polarity": "require", "assert": G("accessKey", present=True)},
        {"id": "R_SIGNAL_BY_FAMILY",
         "mapping": {"source": "DatasetFamily", "target": "SignalClassList",
                     "allow": {m: subs for m, subs in R.FAMILIES.items()}}},
        {"id": "R_SORT_SIGNAL_SUBSET", "polarity": "require",
         "condition": G("SignalClassList", present=True),     # unconstrained if no SignalClassList
         "assert": G("sortKeys", subOf="SignalClassList")},
        {"id": "R_INDEXED_XOR_PROVISIONAL", "polarity": "forbid",
         "assert": {"all": [G("IndexedTimestamp", present=True), G("provisional", present=True)]}},
        {"id": "R_CAPTURE_RANGE", "polarity": "require",
         "assert": G("CaptureTimeEnd", geSheet="CaptureTimeStart")},
        {"id": "R_OFFSET_RANGE", "polarity": "require",
         "assert": G("offsetEnd", geSheet="offsetStart")},
        {"id": "R_ZARR_QUALITY", "polarity": "require", "condition": G("encoding", eq="zarr"),
         "assert": {"all": [{"any": [G("QualityTier", present=False), G("QualityTier", ge="gold")]},
                            G("geometry", present=True)]}},
        {"id": "R_VOLUME_MIN_ENCODING", "polarity": "require", "condition": G("geometry", eq="volumetric"),
         "assert": {"all": [G("encoding", present=True), G("encoding", ge="parquet")]}},
        {"id": "R_MARKUP_NO_ARCHIVE", "polarity": "forbid",
         "assert": {"all": [G("responseFormat", eq="markup"), G("scanScope", eq="archive")]}},
        {"id": "R_EXACT_NO_APPROXIMATE", "polarity": "forbid",
         "assert": {"all": [G("exactMatch", eq="enabled"),
                            {"any": [G("contributorTag", present=True), G("notesPattern", present=True)]}]}},
        {"id": "R_PROVISIONAL_PREVIEW", "polarity": "require", "condition": G("provisional", eq="enabled"),
         "assert": G("AssetKind", eq="preview")},
        {"id": "R_QUALITY_NEEDS_ACCESS", "polarity": "require", "condition": G("QualityTier", present=True),
         "assert": G("AccessTier", present=True)},
        {"id": "R_RESTRICTED_CUSTODIAN", "polarity": "forbid",
         "assert": {"all": [G("custodianId", hasAny=[str(R.RESTRICTED_CUSTODIAN_MIN + 1)]),
                            G("ExcludeRestricted", eq="enabled")]}},
        {"id": "R_COMPLIANCE_LOCK", "polarity": "forbid",
         "assert": {"all": [G("complianceLock", eq="enabled"),
                            {"any": [G("custodianId", hasAny=[str(R.RESTRICTED_CUSTODIAN_MIN + 1)]),
                                     G("ExcludeRestricted", eq="disabled")]}]}},
        {"id": "R_OPEN_ACCESS", "polarity": "require", "condition": G("DatasetFamily", eq="OpenData"),
         "assert": {"all": [{"sheet": "AccessTier", "in": list(R.OPEN_SAFE_ACCESS_TIERS)},
                            {"not": G("geometry", eq="volumetric")}]}},
    ]
    orders = {"QualityTier": R.QUALITY_ORDER, "encoding": R.ENCODING_ORDER,
              "CaptureTimeStart": "numeric", "CaptureTimeEnd": "numeric",
              "offsetStart": "numeric", "offsetEnd": "numeric"}
    return {"version": 1, "params": {}, "orders": orders, "constraints": cons}

# the bounded per-parameter domains for the sample (None == absent/omitted)
def _domains(R):
    restricted = str(R.RESTRICTED_CUSTODIAN_MIN + 1)
    return {
        "locator": ["grid-sample"],
        "accessKey": [None, "permit-alpha"],
        "DatasetFamily": [None, "Climate", "OpenData", "Mobility"],
        "SignalClassList": [None, ["Radar"], ["Radar", "WeatherStation"], ["Trajectory"], ["AirQuality"]],
        "AccessTier": [None, ["public"], ["restricted"], ["public", "partner"]],
        "QualityTier": [None, "bronze", "gold", "diamond"],
        "encoding": [None, "csv", "parquet", "zarr"],
        "geometry": [None, "tabular", "volumetric"],
        "responseFormat": [None, "structured", "markup"],
        "scanScope": [None, "window", "archive"],
        "IndexedTimestamp": [None, "600"],
        "provisional": [None, "enabled"],
        "AssetKind": [None, "preview", "dataset"],
        "exactMatch": [None, "enabled"],
        "contributorTag": [None, "ops-team"],
        "CaptureTimeStart": [None, "1200", "2400"],
        "CaptureTimeEnd": [None, "1200", "2400"],
        "offsetStart": [None, "20", "60"],
        "offsetEnd": [None, "20", "60"],
        "custodianId": [None, "42", restricted],
        "complianceLock": [None, "enabled"],
        "ExcludeRestricted": [None, "enabled", "disabled"],
        "sortBy": [None, ["Radar=DOWN"], ["Satellite=UP"], ["Radar=DOWN", "WeatherStation=UP"]],
    }


def _curated(R):
    """One lookup per rule that triggers it, plus a clean valid baseline — guarantees coverage that a
    random sample only reaches statistically."""
    base = dict(locator="grid-sample", accessKey="permit-alpha", DatasetFamily="Climate", SignalClassList=["Radar"])
    return [
        ("valid", base),
        ("accessKey", {**base, "accessKey": None}),
        ("signal", {**base, "SignalClassList": ["Trajectory"]}),
        ("sortBy", {**base, "sortBy": ["Satellite=UP"]}),
        ("indexed_provisional", {**base, "IndexedTimestamp": "600", "provisional": "enabled", "AssetKind": "preview"}),
        ("capture_range", {**base, "CaptureTimeStart": "2400", "CaptureTimeEnd": "1200"}),
        ("offset_range", {**base, "offsetStart": "60", "offsetEnd": "20"}),
        ("zarr_quality", {**base, "encoding": "zarr", "geometry": "tabular", "QualityTier": "bronze", "AccessTier": ["restricted"]}),
        ("zarr_geometry", {**base, "encoding": "zarr", "QualityTier": "diamond", "AccessTier": ["restricted"]}),
        ("volume_encoding", {**base, "geometry": "volumetric", "encoding": "csv"}),
        ("markup_archive", {**base, "responseFormat": "markup", "scanScope": "archive"}),
        ("exact_approximate", {**base, "exactMatch": "enabled", "contributorTag": "x"}),
        ("provisional_preview", {**base, "provisional": "enabled", "AssetKind": "dataset"}),
        ("quality_access", {**base, "QualityTier": "gold"}),
        ("restricted_custodian", {**base, "custodianId": str(R.RESTRICTED_CUSTODIAN_MIN + 1), "ExcludeRestricted": "enabled"}),
        ("compliance_lock", {**base, "complianceLock": "enabled", "ExcludeRestricted": "disabled"}),
        ("open_access", dict(locator="grid-alt", accessKey="permit-beta", DatasetFamily="OpenData", SignalClassList=["AirQuality"],
                      AccessTier=["restricted"])),
    ]


def _random_lookups(R, n: int, seed: int = 29062026, present_p: float = 0.45):
    """Sparse random lookups: each parameter is absent with probability (1-present_p), else a random
    value. Sparser lookups trip fewer rules, giving a healthy valid/invalid mix."""
    rng = random.Random(seed)
    dom = _domains(R)
    out = []
    for _ in range(n):
        q = {"locator": "grid-sample", "accessKey": "permit-alpha"}   # keep these mostly present so other rules surface
        for k, vals in dom.items():
            if k in ("locator", "accessKey"):
                continue
            present = [v for v in vals if v is not None]
            if rng.random() < present_p and present:
                q[k] = rng.choice(present)
        if rng.random() < 0.1:                        # occasionally drop accessKey to fire its rule
            q.pop("accessKey", None)
        out.append(q)
    return out


def _row(q):
    """A sieve row from a params dict. Multi-select params expand to one placement per value; the
    sortBy terms also project to `sortKeys` placements (the selected signal classes, for the subset bond)."""
    row, pos = [], 0
    for k, v in q.items():
        if v is None or v == "" or v == []:
            continue                                 # absent parameter == omitted from the row
        if isinstance(v, (list, tuple)):
            for item in v:
                row.append({"sheet": k, "value": item, "pos": pos}); pos += 1
            if k == "sortBy":
                for item in v:
                    row.append({"sheet": "sortKeys", "value": str(item).split("=", 1)[0], "pos": pos})
                    pos += 1
        else:
            row.append({"sheet": k, "value": v, "pos": pos}); pos += 1
    return row


# =========================================================================== #
# A. pure classifier == oracle
# =========================================================================== #
def test_sieve_mirrors_service_oracle_exactly():
    R = _telemetry_rules()
    sidecar = _service_sidecar(R)
    assert sv.validate_sidecar(sidecar)["invalid_constraint_count"] == 0

    lookups = [q for _n, q in _curated(R)] + _random_lookups(R, 4000)
    fired = set()
    n_invalid = 0
    for q in lookups:
        oracle = set(R.validate(q))
        hits = set(sv.row_violations(_row(q), sidecar))
        assert hits == oracle, f"sieve {sorted(hits)} != oracle {sorted(oracle)} for {q}"
        fired |= hits
        n_invalid += 1 if oracle else 0
    # every rule in the oracle must have fired at least once over the sample (real coverage)
    assert fired == set(R.RULES_DOC) - {"R_OBLIGATORY_LOCATOR"}, f"unfired rules: {set(R.RULES_DOC) - fired}"
    assert 0 < n_invalid < len(lookups)              # a non-trivial mix of valid/invalid


# =========================================================================== #
# B. live HTTP service: sieve-kept ⟺ 200, sieve-removed ⟺ 400 (same broken ids)
# =========================================================================== #
def test_sieve_matches_live_http_service():
    R = _telemetry_rules()
    try:
        from telemetry_catalog_service import start_server
    except Exception:                                # noqa: BLE001
        pytest.skip("standalone service module not importable")
    import json
    import urllib.error
    import urllib.request

    sidecar = _service_sidecar(R)
    httpd, port, _thr = start_server()
    base = "http://127.0.0.1:%d" % port

    def http_get(url):
        try:
            with urllib.request.urlopen(url, timeout=5) as r:   # noqa: S310 (localhost)
                return r.status, json.loads(r.read().decode("utf-8")) if r.headers.get(
                    "Content-Type", "").startswith("application/json") else {"_": r.read()}
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    try:
        lookups = [q for _n, q in _curated(R)] + _random_lookups(R, 900, seed=777)
        checked_200 = checked_400 = 0
        for q in lookups:
            hits = set(sv.row_violations(_row(q), sidecar))
            url = base + R.assemble_url("", q.get("locator", "grid-sample"),
                                        {k: v for k, v in q.items() if k != "locator"})
            code, body = http_get(url)
            if hits:
                assert code == 400, f"sieve removed but service kept: {q} -> {code}"
                assert set(body.get("broken", [])) == hits, \
                    f"broken mismatch for {q}: service {body.get('broken')} vs sieve {sorted(hits)}"
                checked_400 += 1
            else:
                assert code == 200, \
                    f"sieve kept but service rejected: {q} -> {code} {body.get('broken')}"
                if q.get("responseFormat") != "markup":
                    assert body.get("valid") is True
                checked_200 += 1
        assert checked_200 > 20 and checked_400 > 20
    finally:
        httpd.shutdown()


# =========================================================================== #
# C. full Bundle pipeline on the first-class input spec
# =========================================================================== #
_PIPELINE_SPEC = HERE / "usecases" / "telemetry_catalog_full" / "telemetry_lookup_full.toml"
_DIMS = ("DatasetFamily", "SignalClass", "Encoding", "QualityTier", "CaptureStart", "CaptureEnd")


def _engine(spec):
    ns: dict = {}
    exec(spec.slots[0].values[0], ns)
    return ns["TelemetryLookup"]


def _cell_token(cell):
    ns: dict = {}
    exec(cell, ns)
    return ns[cell.split("=", 1)[0].strip()]


def _connect(host, port, user, password, database):
    import pg8000.dbapi
    return pg8000.dbapi.connect(host=host, port=int(port), user=user, password=password, database=database)


def _endpoints(cfg):
    return [(cfg.main_db_host, int(cfg.main_db_port), cfg.main_db_user, cfg.main_db_password),
            (cfg.results_db_host, int(cfg.results_db_port), cfg.results_db_user, cfg.results_db_password)]


def _create_db(ep, name):
    host, port, user, password = ep
    admin = _connect(host, port, user, password, "postgres"); admin.autocommit = True
    cur = admin.cursor()
    cur.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s AND pid<>pg_backend_pid();", (name,))
    cur.execute(f'DROP DATABASE IF EXISTS "{name}";'); cur.execute(f'CREATE DATABASE "{name}";')
    cur.close(); admin.close()


def _drop_db(ep, name):
    host, port, user, password = ep
    try:
        admin = _connect(host, port, user, password, "postgres"); admin.autocommit = True
    except Exception:                                # noqa: BLE001
        return
    cur = admin.cursor()
    cur.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s AND pid<>pg_backend_pid();", (name,))
    cur.execute(f'DROP DATABASE IF EXISTS "{name}";'); cur.close(); admin.close()


def _require_runtime(cfg, stages):
    if shutil.which("java") is None:
        pytest.skip("java unavailable")
    if not stages.CORE_JAR.exists() or not stages.READER_JAR.exists():
        pytest.skip("Core/Reader jars unavailable")
    py_executor = Path(cfg.py_executor) if cfg.py_executor else stages.PY_EXECUTOR
    if not py_executor.exists():
        pytest.skip("python executor unavailable")
    if not (cfg.main_db_password and cfg.results_db_password):
        pytest.skip("dev DB passwords not configured")


def test_full_pipeline_enforces_authored_nested_bonds():
    from bundle import config, stages
    cfg, _sources = config.resolve_config(cli={})
    _require_runtime(cfg, stages)

    spec0 = fg.load_spec(_PIPELINE_SPEC)
    TelemetryLookup = _engine(spec0)
    slots = {s.sheet: [str(v).strip() for v in s.values] for s in spec0.slots if s.sheet in _DIMS}
    tokmap = {d: {c: _cell_token(c) for c in slots[d]} for d in _DIMS}
    sidecar = {"version": 1, "params": {}, "orders": spec0.orders, "constraints": spec0.constraints}

    # ground truth from the spec's own HEAD engine
    valid, invalid = set(), set()
    for combo in itertools.product(*(slots[d] for d in _DIMS)):
        toks = tuple(tokmap[d][c] for d, c in zip(_DIMS, combo))
        (invalid if TelemetryLookup.validate(*toks) else valid).add(combo)
    assert (len(valid), len(invalid)) == (312, 417)

    tmpdb = "fw_telemetryfull_" + uuid.uuid4().hex[:10]
    endpoints = []
    for ep in _endpoints(cfg):
        if ep in endpoints:
            continue
        try:
            _create_db(ep, tmpdb)
        except Exception as exc:                     # noqa: BLE001
            pytest.skip(f"Postgres endpoint {ep[0]}:{ep[1]} not usable: {exc}")
        endpoints.append(ep)

    scratch = Path(tempfile.mkdtemp(prefix="fw-telemetryfull-"))
    spec_dir = scratch / "spec"; spec_dir.mkdir()
    shutil.copy2(_PIPELINE_SPEC, spec_dir / _PIPELINE_SPEC.name)
    try:
        spec = fg.load_spec(spec_dir / _PIPELINE_SPEC.name)
        assert fg.estimate_core_combos(spec) == 729

        xlsx = stages.stage_gen(spec_dir, scratch)
        n_core = stages.stage_core(spec, xlsx, scratch, tmpdb, cfg.main_db_port, n_opt=0, cfg=cfg)
        assert n_core == 729

        conn = _connect(cfg.main_db_host, cfg.main_db_port, cfg.main_db_user, cfg.main_db_password, tmpdb)
        code2val, baseline, combos_col, order = sv.build_maps_from_db(conn, "fw_final", spec.slots)
        finals, _opts = sv.decode_assembly(conn, "fw_final", code2val, order, combos_col, baseline, set(), [])
        assert len(finals) == 729
        # the live fw_final classifier == the spec's HEAD engine
        def quad(row):
            by = {p["sheet"]: p["value"] for p in row}
            return tuple(tokmap[d].get(by.get(d)) for d in _DIMS)
        removed = {quad(r) for r in finals if sv.row_violations(r, sidecar)}
        kept = {quad(r) for r in finals if not sv.row_violations(r, sidecar)}
        engine_invalid = {tuple(tokmap[d][c] for d, c in zip(_DIMS, combo)) for combo in invalid}
        engine_valid = {tuple(tokmap[d][c] for d, c in zip(_DIMS, combo)) for combo in valid}
        assert removed == engine_invalid and kept == engine_valid
        dry = sv.sieve_fw_final(conn, "fw_final", sidecar, code2val, order, combos_col,
                                id_col="combi_id", baseline=baseline, dry_run=True)
        assert (dry["unique_removals"], dry["retained"]) == (417, 312)
        conn.close()

        n_after = stages.stage_sieve(spec, scratch, tmpdb, cfg.main_db_port, n_core, cfg=cfg)
        assert n_after == 312

        src, hs, n_cands, empty, _mp = stages.stage_reader(
            scratch, tmpdb, "py", cfg.main_db_port, cfg.results_db_port, n_after,
            n_opt=0, full=312, cfg=cfg, run_id="telemetryfull-e2e", legacy_handoff=True)
        assert (empty, n_cands) == (0, 312)

        metrics_path = scratch / "metrics.kv"
        processed, passed, failed, broken, inserted, db_total, timeout, infra, _v2 = stages.stage_executor(
            src, hs, tmpdb, cfg.results_db_port, cfg=cfg, manifest_path=None,
            run_id="telemetryfull-e2e", metrics_path=metrics_path, language="python")
        assert (processed, passed, failed, broken, infra, timeout) == (312, 312, 0, 0, 0, 0)
        lines = [ln for ln in metrics_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert len(lines) == 312
        assert all("app=telemetry_catalog" in ln and "valid=1" in ln and "FW_VAR=0" in ln for ln in lines)
        assert not any("FW_VAR=2" in ln for ln in lines)
        for ln in lines:
            m = re.search(r"url=(\S+) FW_VAR", ln)
            assert m and m.group(1).startswith("http://localhost:8080/api/catalog/lookup/grid-sample")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        for ep in endpoints:
            _drop_db(ep, tmpdb)

# =========================================================================== #
# D. every unsieved full-spec form is a well-formed live telemetry request
# =========================================================================== #
def test_unsieved_full_spec_is_live_http_interoperable():
    if not _SERVICE_DIR.is_dir():
        pytest.skip(f"standalone SUT not found at {_SERVICE_DIR}")
    try:
        from telemetry_catalog_service import start_server
    except Exception:  # noqa: BLE001
        pytest.skip("standalone service module not importable")
    import json
    import urllib.error
    import urllib.request

    spec = fg.load_spec(_PIPELINE_SPEC)
    TelemetryLookup = _engine(spec)
    slots = {s.sheet: [str(v).strip() for v in s.values] for s in spec.slots if s.sheet in _DIMS}
    values = {d: [_cell_token(cell) for cell in slots[d]] for d in _DIMS}
    combos = list(itertools.product(*(values[d] for d in _DIMS)))
    assert len(combos) == 729

    httpd, port, _thread = start_server()
    live_base = f"http://127.0.0.1:{port}"
    statuses = {200: 0, 400: 0}
    model_valid = model_invalid = 0
    try:
        for combo in combos:
            embedded_url = TelemetryLookup.url("grid-sample", *combo)
            assert "accessKey=key-orbit" in embedded_url
            assert "AccessTier=public" in embedded_url
            assert "geometry=tabular" in embedded_url
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

            if TelemetryLookup.validate(*combo):
                model_invalid += 1
            else:
                model_valid += 1
                assert status == 200, f"embedded-valid lookup rejected: {embedded_url}"

        assert (model_valid, model_invalid) == (312, 417)
        assert statuses[200] + statuses[400] == 729
        assert statuses[200] >= model_valid and statuses[400] > 0
    finally:
        httpd.shutdown()
        httpd.server_close()
