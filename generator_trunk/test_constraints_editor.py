#!/usr/bin/env python3
"""Headless tests for the unified link editor + its auto-invoke server (no browser needed)."""
from __future__ import annotations

import itertools
import json
import sys
import threading
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "constraints"))
import editor as ed  # noqa: E402
import serve as srv  # noqa: E402
import sieve as sv  # noqa: E402

_SIDECAR = {
    "version": 1,
    "params": {"A": {"a1": {"charge": 2}, "a2": {"charge": -1}}},
    "constraints": [
        {"id": "b", "polarity": "forbid", "sheets": ["A", "C"],
         "pairs": [{"A": "a1", "C": "c1"}, {"A": "a2", "C": "c2"}], "gate": {}},
        {"id": "t", "polarity": "forbid", "sheets": ["A", "B", "C"],
         "pairs": [{"A": "a1", "B": "b1", "C": "c1"}], "gate": {"within": 3}},
        {"id": "r", "polarity": "require", "sheets": ["B", "C"],
         "pairs": [{"B": "b2", "C": "c3"}], "gate": {"adjacent": True}},
        {"id": "w", "polarity": "forbid", "sheets": ["A", "C"], "when": "A.charge > 0", "gate": {}},
    ],
}
_SHEETS = {"A": ["a1", "a2"], "B": ["b1", "b2"], "C": ["c1", "c2", "c3"]}


def _rows():
    return [[{"sheet": s, "value": v, "pos": i} for i, (s, v) in enumerate(zip(_SHEETS, combo))]
            for combo in itertools.product(*_SHEETS.values())]


def test_round_trip_preserves_structure_and_sieve_effect():
    bonds = ed.sidecar_to_bonds(_SIDECAR)
    back = ed.bonds_to_sidecar(bonds, _SIDECAR["params"])
    assert len(back["constraints"]) == len(_SIDECAR["constraints"])      # 4 in, 4 out
    kinds = {("when" in c) for c in back["constraints"]}
    assert kinds == {True, False}                                        # both enumerated + when survive
    # same number of rows removed (ids are re-minted on regroup, the EFFECT is what must match)
    assert sv.sieve(_rows(), back)["unique_removals"] == sv.sieve(_rows(), _SIDECAR)["unique_removals"]


def test_enumerated_pairs_regroup_by_sheets_gate_polarity():
    sc = {"version": 1, "params": {}, "constraints": [
        {"id": "x", "polarity": "forbid", "sheets": ["A", "C"],
         "pairs": [{"A": "a1", "C": "c1"}, {"A": "a2", "C": "c2"}], "gate": {}}]}
    back = ed.bonds_to_sidecar(ed.sidecar_to_bonds(sc))
    assert len(back["constraints"]) == 1                                 # two pairs -> one constraint
    assert len(back["constraints"][0]["pairs"]) == 2


def test_render_html_safely_embeds_code_like_values():
    html = ed.render_html({"A": ["a'</script><img src=x>"], "B": ["b"]}, {"version": 1, "params": {}, "constraints": []})
    assert "</script><img" not in html
    assert "\\u003c/script\\u003e" in html
    assert "const attr=" in html and "data-id='${attr(id)}'" in html


def test_render_html_is_self_contained_and_has_submit():
    html = ed.render_html(_SHEETS, _SIDECAR, post="/submit", lang="ru")
    assert "/*__DATA__*/null" not in html       # DATA injected
    assert '"bonds"' in html and 'id="submit"' in html
    assert 'data-pol="require"' in html and 'class="hub"' in html       # require + n-ary visuals
    assert '"sides"' in html and "makeGroupBond" in html                # Many:Many model + group mode
    assert "/submit" in html


def test_render_has_per_link_condition_editor():
    html = ed.render_html(_SHEETS, _SIDECAR, post="/submit", lang="ru")
    assert 'id="linkedit"' in html and "renderLinkEditor" in html       # the selected-link editor
    assert "le-gate" in html and "mkGate" in html                       # per-link gate (any/adjacent/within N)
    assert "le-forbid" in html and "le-require" in html                 # per-link polarity
    assert "le-when" in html                                            # inline `when`-formula edit
    assert "le-add" in html                                             # add a value to a link's set (Many:Many)


def test_render_has_block_formula_builder_option():
    html = ed.render_html(_SHEETS, _SIDECAR, post="/submit", lang="ru")
    assert 'id="fmode-blocks"' in html and 'id="ftree"' in html        # the nested (Blockly-grade) block builder
    assert "function compileT(" in html and "function renderFtree(" in html   # AST → `when` string
    assert "function nodeH(" in html and 'class="slot"' in html and "data-ins=" in html   # nested slots/insert
    assert 'id="fpalette"' in html and "buildPalette" in html and "function doDrop(" in html   # drag-and-drop palette
    assert "data-droppath=" in html and "function dropOK(" in html     # typed drop targets
    assert 'id="fexpr"' in html and 'id="fmode-text"' in html          # the text field stays (parallel option)


def test_many_to_many_sets_bond_round_trips_as_cross_product():
    sc = {"version": 1, "params": {}, "constraints": [
        {"id": "mm", "polarity": "forbid", "sheets": ["A", "C"],
         "sets": {"A": ["a1", "a2"], "C": ["c1", "c2"]}, "gate": {}}]}
    bonds = ed.sidecar_to_bonds(sc)
    assert len(bonds) == 1 and bonds[0]["sides"] == {"A": ["a1", "a2"], "C": ["c1", "c2"]}
    back = ed.bonds_to_sidecar(bonds)
    assert "sets" in back["constraints"][0] and "pairs" not in back["constraints"][0]
    assert back["constraints"][0]["sets"] == {"A": ["a1", "a2"], "C": ["c1", "c2"]}


def test_multivalue_side_becomes_sets_singletons_become_pairs():
    # one M:M bond (a side with 2 values) + two singleton bonds sharing sheets/gate/polarity
    bonds = [
        {"polarity": "forbid", "sides": {"A": ["a1", "a3"], "C": ["c1"]}, "gate": {}, "when": None},
        {"polarity": "forbid", "sides": {"A": ["a1"], "C": ["c1"]}, "gate": {}, "when": None},
        {"polarity": "forbid", "sides": {"A": ["a2"], "C": ["c2"]}, "gate": {}, "when": None},
    ]
    cons = ed.bonds_to_sidecar(bonds)["constraints"]
    sets_cons = [c for c in cons if "sets" in c]
    pairs_cons = [c for c in cons if "pairs" in c]
    assert len(sets_cons) == 1                              # the multi-value side -> one sets rule
    assert len(pairs_cons) == 1 and len(pairs_cons[0]["pairs"]) == 2   # two singletons -> one pairs rule (disjunction)




def test_condition_and_mapping_round_trip_without_loss():
    sc = {"version": 1, "params": {}, "constraints": [
        {"id": "cond", "polarity": "forbid", "sheets": ["C"], "sets": {"C": ["c1"]},
         "condition": {"sheet": "A", "eq": "a1"}},
        {"id": "map", "mapping": {"source": "A", "target": "C", "allow": {"a1": ["c1"], "a2": ["c2"]}}},
    ]}
    back = ed.bonds_to_sidecar(ed.sidecar_to_bonds(sc))
    assert back["constraints"][0]["condition"] == {"sheet": "A", "eq": "a1"}
    assert back["constraints"][1]["mapping"] == {"source": "A", "target": "C", "allow": {"a1": ["c1"], "a2": ["c2"]}}
    rows = _rows()
    assert sv.sieve(rows, back)["unique_removals"] == sv.sieve(rows, sc)["unique_removals"]


def test_render_marks_optional_sheets_and_exposes_condition_editor():
    html = ed.render_html(_SHEETS, _SIDECAR, post="/submit", lang="en", optional_sheets={"B", "C"})
    assert '"optional_sheets"' in html and '"B"' in html and '"C"' in html
    assert 'class="opt-badge"' in html and 'optionalW:"optional"' in html
    assert 'id="le-cond"' in html and "evalCondition" in html and "mappingViolated" in html


def test_render_has_visual_condition_builder():
    html = ed.render_html(_SHEETS, _SIDECAR, post="/submit", lang="en")
    # the dropdown "only when" builder (sheet / op / value sub-list) compiled to the condition AST
    assert "function condToTerms(" in html and "function termsToCond(" in html and "function condBuilderHTML(" in html
    assert "ct-sheet" in html and "ct-op" in html and "le-add-cond" in html and "COND_OPS" in html
    # the raw-JSON field stays as the advanced fallback
    assert 'id="le-cond"' in html and "condAdv" in html


def test_render_has_mapping_picker_and_mapping_bond_compiles():
    html = ed.render_html(_SHEETS, _SIDECAR, post="/submit", lang="en")
    assert 'id="addmapping"' in html and 'id="mdlg"' in html and 'id="m-src"' in html and 'id="m-tgt"' in html
    assert "function openMapping(" in html and "function renderMAllow(" in html
    # a mapping bond (what the picker pushes) compiles via the python mirror to a `mapping` constraint
    bonds = [{"polarity": "forbid", "sides": {"A": [], "C": []}, "gate": {}, "when": None,
              "condition": None, "mapping": {"source": "A", "target": "C", "allow": {"a1": ["c1"]}}}]
    sc = ed.bonds_to_sidecar(bonds)
    assert sc["constraints"][0]["mapping"] == {"source": "A", "target": "C", "allow": {"a1": ["c1"]}}

def test_serve_editor_fixed_port_submit_roundtrip():
    port = 8754
    captured = {}

    def run():
        captured["result"] = srv.serve_editor(_SHEETS, _SIDECAR, open_browser=False,
                                               port=port, timeout=10)

    t = threading.Thread(target=run); t.start()
    # wait for the page to be served
    base = f"http://127.0.0.1:{port}/"
    for _ in range(50):
        try:
            page = urllib.request.urlopen(base, timeout=1).read().decode("utf-8")
            if "id=\"submit\"" in page:
                break
        except Exception:
            time.sleep(0.1)
    else:
        raise AssertionError("editor page never came up")

    payload = json.dumps({"version": 1, "params": {}, "constraints": [
        {"id": "drawn", "polarity": "forbid", "sheets": ["A", "C"],
         "pairs": [{"A": "a1", "C": "c1"}], "gate": {}}]}).encode()
    req = urllib.request.Request(base + "submit", data=payload,
                                 headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, timeout=3).read()
    assert b'"ok"' in resp
    t.join(timeout=5)
    result = captured["result"]
    assert result is not None and result["constraints"][0]["id"] == "drawn"


def test_serve_editor_timeout_without_submit_returns_none():
    res = srv.serve_editor(_SHEETS, _SIDECAR, open_browser=False, port=8755, timeout=0.6)
    assert res is None                                                   # closed without Submit -> None


def test_serve_editor_exact_impact_endpoint_is_opt_in():
    """With an `impact_fn`, the page enables exact mode (D.impact='/impact') and POSTing the current
    sidecar to /impact returns the function's verdict. Without it, no endpoint (offline estimate)."""
    seen = {}

    def impact_fn(sidecar):
        seen["sidecar"] = sidecar
        return {"exact": True, "total": 12, "removed": 4, "kept": 8}

    port = 8757
    done = {}
    t = threading.Thread(target=lambda: done.update(
        r=srv.serve_editor(_SHEETS, _SIDECAR, open_browser=False, port=port, timeout=8, impact_fn=impact_fn)))
    t.start()
    base = f"http://127.0.0.1:{port}/"
    page = ""
    for _ in range(60):
        try:
            page = urllib.request.urlopen(base, timeout=1).read().decode("utf-8")
            if 'id="submit"' in page:
                break
        except Exception:
            time.sleep(0.1)
    assert "/impact" in page                                            # exact mode wired into the page DATA
    req = urllib.request.Request(base + "impact", data=json.dumps({"version": 1, "constraints": []}).encode(),
                                 headers={"Content-Type": "application/json"})
    out = json.loads(urllib.request.urlopen(req, timeout=3).read())
    assert out == {"exact": True, "total": 12, "removed": 4, "kept": 8}
    assert seen["sidecar"]["version"] == 1
    urllib.request.urlopen(urllib.request.Request(base + "submit", data=b"{}",
                           headers={"Content-Type": "application/json"}), timeout=3).read()
    t.join(timeout=5)
    # offline (no impact_fn): the page has no /impact endpoint reference
    assert "/impact" not in ed.render_html(_SHEETS, _SIDECAR, post="/submit")


def test_find_contradictions_flags_forbid_and_require_of_the_same_link():
    base = {"sheets": ["A", "C"], "pairs": [{"A": "a1", "C": "c1"}], "gate": {}}
    forbid = dict(base, id="f", polarity="forbid")
    require = dict(base, id="r", polarity="require")
    # forbidding and requiring the EXACT same link is the contradiction
    assert len(ed.find_contradictions({"version": 1, "params": {}, "constraints": [forbid, require]})) == 1
    # same polarity, or a differing gate, is NOT a contradiction
    assert ed.find_contradictions({"version": 1, "params": {}, "constraints": [forbid, dict(forbid, id="f2")]}) == []
    assert ed.find_contradictions({"version": 1, "params": {}, "constraints": [
        forbid, dict(require, gate={"adjacent": True})]}) == []
    # also works directly on bond lists, incl. a Many:Many cross-product link
    mm = [{"polarity": "forbid", "sides": {"A": ["a1", "a2"], "C": ["c1"]}, "gate": {}, "when": None},
          {"polarity": "require", "sides": {"A": ["a1", "a2"], "C": ["c1"]}, "gate": {}, "when": None}]
    assert len(ed.find_contradictions(mm)) == 1
    # a free-form `when` bond has no canonical opposite -> never a contradiction
    whens = [{"polarity": "forbid", "sides": {"A": [], "C": []}, "gate": {}, "when": "A.x>0"},
             {"polarity": "require", "sides": {"A": [], "C": []}, "gate": {}, "when": "A.x>0"}]
    assert ed.find_contradictions(whens) == []


def test_render_has_vertical_drag_zoom_and_contradiction_guard():
    html = ed.render_html(_SHEETS, _SIDECAR, post="/submit", lang="ru")
    # vertical node drag (x locked to the slot column) + live edge re-layout that never drops links
    assert "function startNodeDrag(" in html and "function nodeXY(" in html and "function layoutDrag(" in html
    assert 'id="viewport"' in html and "function applyView(" in html and "function edgesInner(" in html
    # mouse pointer events: wheel zoom-to-cursor + drag-to-pan + on-screen zoom controls
    assert 'addEventListener("wheel"' in html and "function zoomAt(" in html and 'id="zoomctl"' in html
    # the mandatory contradiction guard: blocks creation, flags live in a banner, gates Submit
    assert "function findConflicts(" in html and "function checkAdd(" in html
    assert 'id="warn"' in html and "conflictBonds" in html


# --------- nested-dependency tier (task 29062026): assert bonds + orders + new condition ops --------- #
def test_assert_bond_and_orders_round_trip():
    """An `assert` relation bond (condition-AST body) + a `condition` gate + `orders` survive the
    sidecar -> editor bonds -> sidecar mirror without loss, and `describe` renders it."""
    sc = {"version": 1, "params": {}, "orders": {"star": ["**", "***", "****"]},
          "constraints": [
              {"id": "uhd", "polarity": "require", "assert": {"sheet": "star", "ge": "***"},
               "condition": {"sheet": "fmt", "eq": "4K"}},
              {"id": "rng", "polarity": "require", "assert": {"sheet": "End", "geSheet": "Start"}},
              {"id": "axf", "polarity": "forbid",
               "assert": {"all": [{"sheet": "A", "present": True}, {"sheet": "B", "present": True}]}}]}
    bonds = ed.sidecar_to_bonds(sc)
    assert sum(1 for b in bonds if b.get("assert")) == 3
    back_sc = ed.bonds_to_sidecar(bonds)
    assert back_sc["orders"] == sc["orders"]
    back = back_sc["constraints"]
    by = {c["id"].split("_", 1)[0]: c for c in back}        # ids get a positional prefix
    asrt = [c for c in back if c.get("assert")]
    assert {tuple(sorted(c["assert"])) if not any(k in c["assert"] for k in ("all", "any")) else "node"
            for c in asrt}
    uhd = next(c for c in asrt if c["assert"].get("sheet") == "star")
    assert uhd["assert"] == {"sheet": "star", "ge": "***"} and uhd["polarity"] == "require"
    assert uhd["condition"] == {"sheet": "fmt", "eq": "4K"}
    # the GUI bonds compile to a sidecar the sieve validates and enforces identically
    assert sv.validate_sidecar({"version": 1, "orders": sc["orders"],
                                "constraints": back})["invalid_constraint_count"] == 0


def test_render_exposes_new_condition_ops_and_ordinal_rank():
    html = ed.render_html(_SHEETS, _SIDECAR, post="/submit", lang="en")
    # the visual builder offers the new ops, and the JS mirror has the rank() helper + ORDERS
    for needle in ('k:"present"', 'k:"ge"', 'k:"geSheet"', 'k:"subOf"',
                   "function rank(", "const ORDERS=", "out.orders=ORDERS",
                   '"subOf" in c', '"present" in c'):
        assert needle in html, needle


def test_render_has_visual_school_friendly_constraint_builder():
    html = ed.render_html(_SHEETS, _SIDECAR, post="/submit", lang="en")
    for needle in (
        'id="builder"', 'id="quick-typecards"', 'id="quick-forbid"', 'id="quick-require"',
        'id="quick-preview"', 'class="visual-conn', 'class="type-card',
        'id="quick-map"', 'id="quick-rule"', 'id="rdlg"', 'id="r-preview"',
        "function renderQuickPreview(", "function condVisual(", "function openRelation(",
        'id="le-assert-builder"', 'id="edlg"', 'id="edlg-body"', 'id="adlg"',
        "function condSubject(", "function openBondDialog(", "function openArmDialog(",
        'id="arm-popover"', "function saveArmPane(", "function discardArmPane(",
        "function removeBondValue(", "function undoLast(", "function addNodeToBond(",
        "function canExtendBond(", "function scheduleSingleClick(", "bindLinkEditorControls",
        "ondblclick", "armctl", "armseg",
        "le-map", 'id="resolve-actions"', "function conflictActions(",
        "function resolveConflict(", "Resolve in favor", "fitView();didAutoFit=true",
        "sampled estimate", "function rng32(", "function setIntersection(",
    ):
        assert needle in html, needle
    # JSON is still available, but it is visibly demoted to a fallback path.
    assert "json-fallback" in html


# --------- node-centric bond inspector (2026-06-29 UX): side panel describes a node's bond-lines --------- #
def test_node_inspector_present_and_lines_preserved():
    html = ed.render_html(_SHEETS, _SIDECAR, post="/submit", lang="en")
    # the value-LINES on the canvas are preserved (Yuri: lines-bonds must be preserved)
    assert "function edgesInner(" in html and 'class="edge' in html and "function bondNodes(" in html
    # the node-centric inspector + spotlight + at-a-glance dots are wired into the side panel
    for needle in ('id="nodeinfo"', "function renderNodeInfo(", "function memberBonds(",
                   "function contextBonds(", "function valueInCond(", "function spotlight(",
                   "function nodeDots(", "onmouseenter", "function inspectNode("):
        assert needle in html, needle
    # the panel renders the node card every render, and a node's row selects its bond
    assert "renderNodeInfo();" in html and 'class="ni-row' in html
