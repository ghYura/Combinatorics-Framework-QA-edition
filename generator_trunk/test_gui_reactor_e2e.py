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
# (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
# Ukraine
#
# See LICENSE and NOTICE.md for the binding terms.

r"""Showcase acceptance for the GUI constraints/sieve layer over the WHOLE Bundle workflow.

The system-under-test is a purpose-built *reactor-commissioning* object
(``usecases/gui_reactor_e2e/reactor.toml``): each candidate commissions a reaction from a chosen
quadruple (BASE, OXIDIZER, SOLVENT, ADDITIVE) and its HEAD carries a real ``Reactor.assess`` engine
that flags a combination as HAZARDOUS iff it trips one of three chemistry rules. Those three rules
are EXACTLY the value-bonds drawn in the GUI — a forbidden pair, a ``when`` formula over a
per-reagent ``charge`` param, and a Many:Many family ban — so the layer can be proven a perfect
classifier of the object's own safe/unsafe space.

This is deliberately complementary to ``test_gui_constraints_e2e.py`` (which monkeypatches the editor
server and asserts only that forbidden rows are absent). Here we add the things that make the layer
*demonstrably* trustworthy end to end:

  A. NEGATIVE CONTROL + CLASSIFIER, then the real Core→Sieve→Reader→Executor→Analyzer pipeline:
     the engine itself decides which of the 36 reagent quadruples are hazardous; the GUI-drawn
     forbid-bonds are proven to delete *precisely* that set (no over- and no under-filtering — the
     documented over-filtering risk, made into an assertion), the live ``/impact`` preview equals
     reality, and the pipeline then executes ONLY the safe quadruples (every one green, FW_VAR=0,
     every hazardous signature absent), with a candidate↔engine consistency check and a round-trip.
  B. The ``require`` (искомый / only-together) polarity and the positional ``gate`` — both omitted by
     the existing e2e — over the same object, headless and exact.
  C. The REAL editor HTTP seam (a socket, not a monkeypatch): the served page embeds the real
     reagents and the live exact ``/impact`` preview equals the engine's own verdict.

Run: ``python3 -m pytest test_gui_reactor_e2e.py -v``  (the pipeline test needs the dev Postgres on
:5433 / results port plus the Core+Reader jars and the Python executor; it self-skips otherwise).
"""
from __future__ import annotations

import itertools
import json
import re
import shutil
import socket
import sys
import tempfile
import threading
import time
import urllib.request
import uuid
from collections import OrderedDict
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "constraints"))

import editor as ed          # noqa: E402  the GUI's bonds<->sidecar compiler (mirror of the page JS)
import fwgen as fg           # noqa: E402
import graphspec as gs       # noqa: E402  spec_sheets: the real reagents the editor renders
import serve as srv          # noqa: E402  the editor's auto-invoke HTTP host
import sieve as sv           # noqa: E402
from bundle import config, stages  # noqa: E402

_SPEC = HERE / "usecases" / "gui_reactor_e2e" / "reactor.toml"
_REAGENTS = ("BASE", "OXIDIZER", "SOLVENT", "ADDITIVE")


# --------------------------------------------------------------------------- #
# SUT helpers: load the object, its engine, and the GUI drawing as one sidecar
# --------------------------------------------------------------------------- #
def _engine(spec):
    """Exec the spec's HEAD slot to recover the very `Reactor` class each candidate runs — the
    single source of truth for which quadruples are hazardous."""
    ns: dict = {}
    exec(spec.slots[0].values[0], ns)
    return ns["Reactor"]


def _cell_token(cell: str, sheet: str):
    ns: dict = {}
    exec(cell, ns)
    return ns[sheet]


def _dimension_maps(spec):
    """Return (dims, stmt2tok): the runtime tokens per reagent sheet, and the map from the EXACT
    cell string the sieve decodes (`BASE = "amine"`) back to its token (`amine`)."""
    dims: "OrderedDict[str, list]" = OrderedDict()
    stmt2tok: dict = {}
    for s in spec.slots:
        if s.sheet in _REAGENTS:
            toks, m = [], {}
            for cell in s.values:
                t = _cell_token(cell, s.sheet)
                toks.append(t)
                m[str(cell).strip()] = t
            dims[s.sheet] = toks
            stmt2tok[s.sheet] = m
    return dims, stmt2tok


def _gui_drawing(spec):
    """The bonds a user draws on the canvas, in the editor's own bond shape, compiled to a sidecar by
    the same `bonds_to_sidecar` the page JS mirrors. Three links, one per bond kind:
      • a 2-click forbidden pair  metal —|— nitrate           -> a `pairs` constraint
      • a formula link over BASE,OXIDIZER (like-charge repels) -> a `when` constraint
      • a Group/Many:Many link {amine,alkali} —|— {ether}      -> a `sets` constraint
    Values are the exact cell strings (what the sieve sees); params carry the per-reagent charge."""
    val = {s.sheet: [str(v).strip() for v in s.values] for s in spec.slots}
    b_amine, b_alkali, b_metal = val["BASE"]
    o_peroxide, o_nitrate = val["OXIDIZER"]
    _s_water, s_ether = val["SOLVENT"]
    params = {
        "BASE": {b_amine: {"charge": 1}, b_alkali: {"charge": 2}, b_metal: {"charge": -1}},
        "OXIDIZER": {o_peroxide: {"charge": -2}, o_nitrate: {"charge": 1}},
    }
    bonds = [
        {"polarity": "forbid", "sides": {"BASE": [b_metal], "OXIDIZER": [o_nitrate]},
         "gate": {}, "when": None},
        {"polarity": "forbid", "sides": {"BASE": [], "OXIDIZER": []},
         "gate": {}, "when": "BASE.charge * OXIDIZER.charge > 0"},
        {"polarity": "forbid", "sides": {"BASE": [b_amine, b_alkali], "SOLVENT": [s_ether]},
         "gate": {}, "when": None},
    ]
    sidecar = ed.bonds_to_sidecar(bonds, params)
    return params, bonds, sidecar


def _ground_truth(Reactor, dims):
    """The object's OWN verdict: split every quadruple into hazardous / safe via Reactor.assess."""
    hazardous, safe = set(), set()
    for combo in itertools.product(*(dims[s] for s in _REAGENTS)):
        (hazardous if Reactor.assess(*combo)["hazards"] else safe).add(combo)
    return hazardous, safe


def _cartesian_rows(values_by_sheet):
    """Ordered placement-rows over the sheets' full cartesian (DB-free, what the editor previews)."""
    sheets = list(values_by_sheet)
    rows = []
    for combo in itertools.product(*values_by_sheet.values()):
        rows.append([{"sheet": s, "value": v, "pos": i} for i, (s, v) in enumerate(zip(sheets, combo))])
    return rows


def _combo_of(row, stmt2tok):
    """Map a decoded fw_final row -> the (BASE,OXIDIZER,SOLVENT,ADDITIVE) token quadruple."""
    by = {p["sheet"]: stmt2tok[p["sheet"]][p["value"]] for p in row if p["sheet"] in stmt2tok}
    return tuple(by[s] for s in _REAGENTS)


def _tokens_from_text(text):
    return tuple(re.search(rf'{s} = "(\w+)"', text).group(1) for s in _REAGENTS)


# --------------------------------------------------------------------------- #
# DB / runtime helpers (independent of the existing e2e; same proven invocation)
# --------------------------------------------------------------------------- #
def _connect(host, port, user, password, database):
    import pg8000.dbapi
    return pg8000.dbapi.connect(host=host, port=int(port), user=user,
                                password=password, database=database)


def _endpoints(cfg):
    return [(cfg.main_db_host, int(cfg.main_db_port), cfg.main_db_user, cfg.main_db_password),
            (cfg.results_db_host, int(cfg.results_db_port), cfg.results_db_user, cfg.results_db_password)]


def _create_db(endpoint, name):
    host, port, user, password = endpoint
    admin = _connect(host, port, user, password, "postgres")
    admin.autocommit = True
    cur = admin.cursor()
    cur.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname=%s AND pid<>pg_backend_pid();", (name,))
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
    cur.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname=%s AND pid<>pg_backend_pid();", (name,))
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


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# =========================================================================== #
# A. negative control + classifier, then the real full pipeline
# =========================================================================== #
def test_gui_safety_bonds_classify_and_drive_full_pipeline():
    cfg, _sources = config.resolve_config(cli={})
    _require_runtime(cfg)

    spec0 = fg.load_spec(_SPEC)
    Reactor = _engine(spec0)
    dims, stmt2tok = _dimension_maps(spec0)
    hazardous, safe = _ground_truth(Reactor, dims)
    # the object decides this, independent of the constraint layer:
    assert (len(hazardous), len(safe)) == (30, 6)

    params, bonds, sidecar = _gui_drawing(spec0)
    assert sv.validate_sidecar(sidecar)["unsupported_constraint_count"] == 0
    assert [(("when" in c) and "when") or ("sets" in c and "sets") or "pairs"
            for c in sidecar["constraints"]] == ["pairs", "sets", "when"]

    tmpdb = "fw_reactor_" + uuid.uuid4().hex[:12]
    endpoints = []
    for ep in _endpoints(cfg):
        if ep in endpoints:
            continue
        try:
            _create_db(ep, tmpdb)
        except Exception as exc:  # noqa: BLE001 - any local DB/auth issue skips this acceptance test
            pytest.skip(f"Postgres endpoint {ep[0]}:{ep[1]} not usable: {exc}")
        endpoints.append(ep)

    scratch = Path(tempfile.mkdtemp(prefix="fw-reactor-"))
    spec_dir = scratch / "spec"; spec_dir.mkdir()
    shutil.copy2(_SPEC, spec_dir / _SPEC.name)
    try:
        spec = fg.load_spec(spec_dir / _SPEC.name)
        assert fg.estimate_core_combos(spec) == 36
        # the GUI Submit REPLACES the spec's constraints/params (exactly what stage_draw does when
        # the user presses Submit); Test C drives that over the live HTTP seam, here we inject the
        # drawn sidecar directly so the sieve stage enforces the hand-drawn bonds.
        spec.constraints = sidecar["constraints"]
        spec.params = sidecar["params"]

        xlsx = stages.stage_gen(spec_dir, scratch)
        n_core = stages.stage_core(spec, xlsx, scratch, tmpdb, cfg.main_db_port, n_opt=0, cfg=cfg)
        assert n_core == 36

        conn = _connect(cfg.main_db_host, cfg.main_db_port, cfg.main_db_user, cfg.main_db_password, tmpdb)
        code2val, baseline, combos_col, order = sv.build_maps_from_db(conn, "fw_final", spec.slots)
        rows, _opts = sv.decode_assembly(conn, "fw_final", code2val, order, combos_col, baseline, set(), [])
        assert len(rows) == 36

        # ---- THE CLASSIFIER PROOF: the GUI bonds delete exactly the object's hazardous set ----
        removed = {_combo_of(r, stmt2tok) for r in rows if sv.row_violations(r, sidecar)}
        retained = {_combo_of(r, stmt2tok) for r in rows if not sv.row_violations(r, sidecar)}
        assert removed == hazardous, "sieve removed a different set than the engine flags hazardous"
        assert retained == safe, "sieve would drop a safe quadruple (over-filtering)"

        pure = sv.sieve(rows, sidecar)
        assert (pure["scanned"], pure["unique_removals"], pure["retained"]) == (36, 30, 6)
        assert pure["matched"] == {"bond0_BASE_OXIDIZER": 6, "mm0_BASE_SOLVENT": 12,
                                   "when0_BASE_OXIDIZER": 18}
        assert pure["overlap"] == 6                       # 6 rows tripped by >1 rule

        # ---- the GUI's live exact preview equals what the pipeline will do ----
        preview = sv.impact_over_rows(rows, [], sidecar, set())
        assert preview == {"exact": True, "total": 36, "removed": 30, "kept": 6,
                           "mandatory_rows": 36, "optional_multiplier": 1}

        # ---- dry-run on the live DB matches, and changes nothing ----
        dry = sv.sieve_fw_final(conn, "fw_final", sidecar, code2val, order, combos_col,
                                id_col="combi_id", baseline=baseline, dry_run=True)
        assert dry["matched"] == pure["matched"]
        assert (dry["unique_removals"], dry["retained"], dry["deleted"]) == (30, 6, 0)
        cur = conn.cursor(); cur.execute("SELECT count(*) FROM fw_final;")
        assert cur.fetchone()[0] == 36
        cur.close(); conn.close()

        # ---- the real destructive sieve, then reader assembles ONLY the safe quadruples ----
        n_after = stages.stage_sieve(spec, scratch, tmpdb, cfg.main_db_port, n_core, cfg=cfg)
        assert n_after == 6

        src, hs, n_cands, empty, _mp = stages.stage_reader(
            scratch, tmpdb, "py", cfg.main_db_port, cfg.results_db_port, n_after,
            n_opt=0, full=n_after, cfg=cfg, run_id="reactor-e2e", legacy_handoff=True)
        assert (empty, n_cands) == (0, 6)
        assembled = {_tokens_from_text(p.read_text(encoding="utf-8")) for p in Path(src).glob("*.py")}
        assert assembled == safe                          # the surviving candidate sources ARE the safe set

        # ---- execute: only the safe reactions run, and every one is green ----
        metrics_path = scratch / "metrics.kv"
        processed, passed, failed, broken, inserted, db_total, timeout, infra, _v2 = stages.stage_executor(
            src, hs, tmpdb, cfg.results_db_port, cfg=cfg, manifest_path=None,
            run_id="reactor-e2e", metrics_path=metrics_path, language="python")
        assert (processed, passed, failed, broken, infra, timeout) == (6, 6, 0, 0, 0, 0)

        lines = [ln for ln in metrics_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert len(lines) == 6
        assert all("app=gui_reactor" in ln for ln in lines)
        assert all("FW_VAR=0" in ln and "outcome=STABLE" in ln for ln in lines)
        # not one hazardous signature reached execution:
        assert not any("outcome=EXPLOSION" in ln or "outcome=LIKE_CHARGE" in ln
                       or "ETHER_FLASH" in ln or "FW_VAR=2" in ln for ln in lines)
        # candidate <-> engine consistency: each executed line agrees with Reactor.assess
        executed = set()
        for ln in lines:
            m = re.search(r"base=(\w+) oxidizer=(\w+) solvent=(\w+) additive=(\w+) outcome=(\w+)", ln)
            quad = (m.group(1), m.group(2), m.group(3), m.group(4))
            executed.add(quad)
            assert m.group(5) == Reactor.assess(*quad)["outcome"] == "STABLE"
        assert executed == safe

        # ---- round-trip: the editor can re-edit its own drawing with identical effect ----
        back = ed.bonds_to_sidecar(ed.sidecar_to_bonds(sidecar), params)
        assert sv.sieve(rows, back)["unique_removals"] == 30

        # ---- 5/5: the Analyzer ingests the harvested corpus (whole-workflow close-out) ----
        stages.stage_analyzer(src, scratch, spec.goals_property(), cfg=cfg, mode="exploratory",
                              corpus_count=6, run_id="reactor-e2e", harvested_metrics=metrics_path)
        assert len([ln for ln in (scratch / "metrics.kv").read_text(encoding="utf-8").splitlines()
                    if ln.strip()]) == 6
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        for ep in endpoints:
            _drop_db(ep, tmpdb)


# =========================================================================== #
# B. require (искомый) + positional gate — exact, headless
# =========================================================================== #
def test_gui_required_recipe_and_positional_gate_are_exact():
    spec = fg.load_spec(_SPEC)
    dims, _ = _dimension_maps(spec)
    val = OrderedDict((s.sheet, [str(v).strip() for v in s.values])
                      for s in spec.slots if s.sheet in _REAGENTS)
    b_amine, b_alkali, b_metal = val["BASE"]
    o_peroxide, o_nitrate = val["OXIDIZER"]
    _s_water, s_ether = val["SOLVENT"]
    _a_none, _a_inh, a_accel = val["ADDITIVE"]
    rows = _cartesian_rows(val)                            # 36 ordered rows; pos = sheet index

    # --- require / искомый: a green "Require" link keeps ONLY the sought recipe family ---
    req_bond = [{"polarity": "require", "sides": {"BASE": [b_alkali], "OXIDIZER": [o_peroxide]},
                 "gate": {}, "when": None}]
    req = ed.bonds_to_sidecar(req_bond)
    assert req["constraints"][0]["polarity"] == "require"
    rep = sv.sieve(rows, req)
    assert rep["retained"] == 6 and rep["unique_removals"] == 30   # only alkali+peroxide (×2 solvent ×3 additive)
    kept = [r for r in rows if not sv.row_violations(r, req)]
    assert all(any(p["sheet"] == "BASE" and p["value"] == b_alkali for p in r)
               and any(p["sheet"] == "OXIDIZER" and p["value"] == o_peroxide for p in r) for r in kept)

    # --- positional gate: same value-pair, but the gate decides by slot distance ---
    # OXIDIZER (pos 1) and SOLVENT (pos 2) are ADJACENT; BASE (pos 0) and ADDITIVE (pos 3) are far.
    def removed(sides, gate):
        sc = ed.bonds_to_sidecar([{"polarity": "forbid", "sides": sides, "gate": gate, "when": None}])
        return sv.sieve(rows, sc)["unique_removals"]

    near = {"OXIDIZER": [o_peroxide], "SOLVENT": [s_ether]}
    far = {"BASE": [b_metal], "ADDITIVE": [a_accel]}
    assert removed(near, {}) == 9                          # peroxide+ether over free BASE×ADDITIVE
    assert removed(near, {"adjacent": True}) == 9          # adjacent slots -> the gate fires
    assert removed(far, {}) == 4                           # metal+accelerant over free OXIDIZER×SOLVENT
    assert removed(far, {"adjacent": True}) == 0           # non-adjacent slots -> gate suppresses it
    assert removed(far, {"within": 3}) == 4                # ...but a window of 3 spans pos 0..3 again


# =========================================================================== #
# C. the REAL editor HTTP seam: served page + live exact /impact == the truth
# =========================================================================== #
def test_gui_editor_http_seam_serves_real_reagents_and_previews_exact_impact():
    spec = fg.load_spec(_SPEC)
    _params, _bonds, sidecar = _gui_drawing(spec)
    sheets = gs.spec_sheets(_SPEC)                         # the real reagents the editor renders
    assert set(sheets) == set(_REAGENTS)
    rows = _cartesian_rows(OrderedDict(sheets))

    # the exact-impact callback the running pipeline wires to /impact (here DB-free over the cartesian)
    seen = {}

    def impact_fn(posted):
        seen["sidecar"] = posted
        rep = sv.sieve(rows, posted)
        return {"exact": True, "total": rep["scanned"], "removed": rep["unique_removals"],
                "kept": rep["retained"]}

    port = _free_port()
    captured = {}
    t = threading.Thread(target=lambda: captured.update(
        result=srv.serve_editor(sheets, {"version": 1, "params": {}, "constraints": []},
                                open_browser=False, port=port, timeout=15, impact_fn=impact_fn)))
    t.start()
    try:
        base = f"http://127.0.0.1:{port}/"
        page = ""
        for _ in range(80):
            try:
                page = urllib.request.urlopen(base, timeout=1).read().decode("utf-8")
                if 'id="submit"' in page:
                    break
            except Exception:
                time.sleep(0.1)
        assert 'id="submit"' in page, "editor never came up"
        # the served page is built from the REAL spec's reagents and wires exact-impact mode
        # (values embed as JSON, so the cell `OXIDIZER = "peroxide"` carries the bare token)
        assert "peroxide" in page and "nitrate" in page and "ether" in page
        assert "/impact" in page and 'class="hub"' in page and 'data-pol="require"' in page

        # the live preview the user sees while drawing == the object's own hazardous count
        req = urllib.request.Request(base + "impact", data=json.dumps(sidecar).encode(),
                                     headers={"Content-Type": "application/json"})
        out = json.loads(urllib.request.urlopen(req, timeout=3).read())
        assert out == {"exact": True, "total": 36, "removed": 30, "kept": 6}
        assert seen["sidecar"]["constraints"] == sidecar["constraints"]

        # pressing Submit returns that exact sidecar to the pipeline, and it sieves identically
        sub = urllib.request.Request(base + "submit", data=json.dumps(sidecar).encode(),
                                     headers={"Content-Type": "application/json"})
        assert b'"ok"' in urllib.request.urlopen(sub, timeout=3).read()
        t.join(timeout=5)
    finally:
        t.join(timeout=5)
    submitted = captured["result"]
    assert submitted is not None and submitted["constraints"] == sidecar["constraints"]
    assert sv.sieve(rows, submitted)["unique_removals"] == 30
