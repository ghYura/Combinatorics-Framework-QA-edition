#!/usr/bin/env python3
r"""editor — the unified, single-file, zero-dependency constraint editor: the "draw the links"
face of the Bundle (the second of the three user-facing faces; see docs/26_PLAN3_THREE_FACES_UX.md).

ONE polished offline HTML page that merges the three earlier demos (bond-matrix, graph/threads,
Blockly `when`) into a single surface and adds what they lacked:

  * BOTH polarities — red "forbid" (never together) AND green "require"/искомый (only together);
  * GATES in the UI — any / adjacent / within N (positional);
  * n-ARY bonds — a link can join 3+ value-nodes (a hub), matching the n-ary sieve engine;
  * PARAMS + `when` formula bonds — the advanced predicate tier, in plain language;
  * ROUND-TRIP — it LOADS the spec's existing constraints back onto the canvas to edit;
  * a big SUBMIT — the running pipeline serves this page, the user draws, presses Submit, and the
    links POST straight back so the chain resumes (constraints/serve.py). Drawing nothing is fine —
    an empty sidecar means "as if --sieve was off".

Everything compiles to the SAME sidecar `{version, params, constraints}` (see sidecar_schema.md)
that constraints/sieve.py + `bundle_run --sieve` consume. The bonds<->sidecar mapping lives in BOTH
Python (here, headlessly tested) and JS (in the page), like graphspec.py/graphspec.js.

  python3 editor.py                         # demo: emit editor_demo.html
  python3 editor.py --spec <spec> [--out editor.html]   # from a REAL fwgen spec
  python3 editor.py --spec <spec> --serve   # emit + serve + open Firefox + wait for Submit
"""
from __future__ import annotations

import json
import sys
from collections import OrderedDict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sieve as sv  # noqa: E402


def _script_json(data: dict) -> str:
    """JSON for embedding inside a <script> raw-text element."""
    return (json.dumps(data, ensure_ascii=False)
            .replace("&", "\\u0026")
            .replace("<", "\\u003c")
            .replace(">", "\\u003e"))


# ----------------------------- bonds <-> sidecar ----------------------------- #
# A "bond" is the editor's uniform unit. Enumerated bonds carry concrete member VALUES; a `when`
# bond carries member SHEETS (value=None) plus a predicate. One sidecar constraint with many pairs
# expands to many enumerated bonds (one per tuple); on export they re-group by (sheets, gate,
# polarity) — exactly the grouping graphspec/bondmatrix already use.
class _BondList(list):
    pass


def sidecar_to_bonds(sidecar: dict) -> list:
    """A bond is ``{polarity, sides: {sheet: [values]}, gate, when, condition, mapping}``.

    `condition` and `mapping` are preserved as first-class GUI data: opening the editor on a
    contextual sidecar must not erase the flexible sieve tier. Enumerated constraints still draw as
    value links; a `mapping` is a sheet-level dependency bond shown in the advanced list.
    """
    bonds = _BondList()
    bonds.orders = sidecar.get("orders", {}) or {}
    for c in sidecar.get("constraints", []):
        mapping = c.get("mapping")
        assrt = c.get("assert")
        sheets = (c.get("sheets") or list(c.get("sets", {}).keys())
                  or ([mapping["source"], mapping["target"]] if mapping else [])
                  or (sv._condition_sheets(assrt) if assrt is not None else [])
                  or sorted({k for e in c.get("pairs", []) for k in e}))
        pol = c.get("polarity", "require" if assrt is not None else "forbid")
        gate = c.get("gate", {}) or {}
        cond = c.get("condition")
        if assrt is not None:                          # a relation/assert bond (condition-AST as body)
            bonds.append({"polarity": pol, "sides": {s: [] for s in sheets}, "gate": gate,
                          "when": None, "condition": cond, "mapping": None, "assert": assrt,
                          "desc": c.get("desc") or sv.describe(c)})
        elif mapping is not None:
            bonds.append({"polarity": pol, "sides": {s: [] for s in sheets}, "gate": gate,
                          "when": None, "condition": cond, "mapping": mapping,
                          "desc": c.get("desc") or sv.describe(c)})
        elif c.get("when") is not None:
            bonds.append({"polarity": pol, "sides": {s: [] for s in sheets}, "gate": gate,
                          "when": c["when"], "condition": cond, "mapping": None,
                          "desc": c.get("desc") or sv.describe(c)})
        elif c.get("sets") is not None:
            bonds.append({"polarity": pol, "sides": {s: list(v) for s, v in c["sets"].items()},
                          "gate": gate, "when": None, "condition": cond, "mapping": None, "desc": ""})
        else:
            for e in c.get("pairs", []):
                bonds.append({"polarity": pol, "sides": {s: [e[s]] for s in sheets if s in e},
                              "gate": gate, "when": None, "condition": cond, "mapping": None, "desc": ""})
    return bonds


def bonds_to_sidecar(bonds: list, params: dict | None = None, orders: dict | None = None) -> dict:
    """Export editor bonds to the canonical sidecar.

    Singleton-sided bonds re-group by (sorted sheets, gate, polarity, condition) into one `pairs`
    constraint; a multi-value side becomes `sets`; `when` and `mapping` bonds stay separate. Mirrors
    the JS `bondsToSidecar`.
    """
    if orders is None:
        orders = getattr(bonds, "orders", None)
    groups: "OrderedDict" = OrderedDict()
    sets_cons, whens, mappings, asserts = [], [], [], []
    for b in bonds:
        sides = b["sides"]
        sheets = list(sides.keys())
        gate = b.get("gate", {}) or {}
        pol = b.get("polarity", "forbid")
        cond = b.get("condition")
        if b.get("assert") is not None:
            asserts.append((sorted(sheets), pol, b["assert"], cond))
        elif b.get("mapping"):
            mappings.append((sorted(sheets), gate, pol, b["mapping"], cond))
        elif b.get("when"):
            whens.append((sorted(sheets), gate, pol, b["when"], cond))
        elif any(len(v) > 1 for v in sides.values()):
            sets_cons.append((sorted(sheets), gate, pol, {s: list(v) for s, v in sides.items()}, cond))
        else:
            key = (tuple(sorted(sheets)), json.dumps(gate, sort_keys=True), pol,
                   json.dumps(cond, ensure_ascii=False, sort_keys=True) if cond else "")
            g = groups.setdefault(key, {"sheets": sorted(set(sheets)), "gate": gate, "polarity": pol,
                                        "condition": cond, "pairs": []})
            g["pairs"].append({s: vals[0] for s, vals in sides.items()})
    cons = []
    for i, (_key, g) in enumerate(groups.items()):
        label = "×".join(g["sheets"])
        c = {"id": f"bond{i}_" + "_".join(g["sheets"]), "polarity": g["polarity"],
             "sheets": g["sheets"], "pairs": g["pairs"], "gate": g["gate"],
             "desc": f"{len(g['pairs'])} {g['polarity']} {label} bond(s)"}
        if g.get("condition"):
            c["condition"] = g["condition"]
        cons.append(c)
    for j, (sheets, gate, pol, sets, cond) in enumerate(sets_cons):
        body = " × ".join(f"{s}∈{{{','.join(map(str, v))}}}" for s, v in sets.items())
        c = {"id": f"mm{j}_" + "_".join(sheets), "polarity": pol, "sheets": sheets,
             "sets": sets, "gate": gate, "desc": f"{pol} {body}"}
        if cond:
            c["condition"] = cond
        cons.append(c)
    for k, (sheets, gate, pol, expr, cond) in enumerate(whens):
        c = {"id": f"when{k}_" + "_".join(sheets), "polarity": pol, "sheets": sheets,
             "when": expr, "gate": gate, "desc": f"{pol} {'/'.join(sheets)} when {expr}"}
        if cond:
            c["condition"] = cond
        cons.append(c)
    for m, (sheets, gate, pol, mapping, cond) in enumerate(mappings):
        c = {"id": f"map{m}_" + "_".join(sheets), "polarity": pol, "sheets": sheets,
             "mapping": mapping, "gate": gate, "desc": f"mapping {mapping.get('source')}->{mapping.get('target')}"}
        if cond:
            c["condition"] = cond
        cons.append(c)
    for n, (sheets, pol, asrt, cond) in enumerate(asserts):
        c = {"id": f"assert{n}_" + "_".join(sheets), "polarity": pol, "assert": asrt,
             "desc": sv.describe({"polarity": pol, "assert": asrt, "condition": cond})}
        if cond:
            c["condition"] = cond
        cons.append(c)
    out = {"version": 1, "params": params or {}, "constraints": cons}
    if orders:
        out["orders"] = orders
    return out


def _canon_gate(g) -> tuple:
    g = g or {}
    if g.get("adjacent"):
        return ("adjacent",)
    if "within" in g:
        return ("within", int(g["within"]))
    return ()


def find_contradictions(spec) -> list:
    """Enumerated bonds that contradict each other: the SAME referenced sheets + gate + value
    membership asserted with OPPOSITE polarity (one forbids exactly what the other requires — they
    can never both hold). Mirrors the page's JS `findConflicts`; the editor blocks drawing one and
    refuses to Submit while any remain. Accepts a sidecar dict or a bond list; `when` bonds are
    excluded (a free-form predicate has no canonical opposite). Returns the conflicting,
    polarity-agnostic keys ``(sheets, gate, sides)``."""
    bonds = sidecar_to_bonds(spec) if isinstance(spec, dict) else list(spec)
    seen: dict = {}
    out: list = []
    for b in bonds:
        if b.get("when") or b.get("mapping"):
            continue
        sheets = tuple(sorted(b["sides"]))
        sides = tuple((s, tuple(sorted(map(str, b["sides"][s])))) for s in sheets)
        cond = json.dumps(b.get("condition") or {}, ensure_ascii=False, sort_keys=True)
        key = (sheets, _canon_gate(b.get("gate")), sides, cond)
        pol = b.get("polarity", "forbid")
        if key in seen and seen[key] != pol:
            out.append(key)
        seen.setdefault(key, pol)
    return out


# ------------------------------- data + emit -------------------------------- #
def build_data(sheets: dict, sidecar: dict | None = None, *, post: str = "", lang: str = "ru",
               impact: str = "", optional_sheets=None) -> dict:
    sheets = OrderedDict((k, list(dict.fromkeys(v))) for k, v in sheets.items())
    sidecar = sidecar or {"version": 1, "params": {}, "constraints": []}
    full = 1
    for vs in sheets.values():
        full *= max(1, len(vs))
    optional_sheets = sorted(set(optional_sheets or ()))
    return {"sheets": [[s, vs] for s, vs in sheets.items()],
            "params": sidecar.get("params", {}) or {},
            "orders": sidecar.get("orders", {}) or {},
            "bonds": sidecar_to_bonds(sidecar),
            "optional_sheets": optional_sheets,
            "sheet_meta": {s: {"optional": s in optional_sheets} for s in sheets},
            "full": full, "post": post, "impact": impact, "lang": lang}


def render_html(sheets: dict, sidecar: dict | None = None, *, post: str = "",
                title: str | None = None, lang: str = "ru", impact: str = "",
                optional_sheets=None) -> str:
    """The editor page as a single self-contained HTML string (DATA injected, no external fetch).
    `impact` (a URL, optional) enables EXACT live impact from a live DB — the page POSTs the current
    sidecar there and shows the precise removed/kept over the whole assembled space; empty = the
    in-browser co-occurrence estimate (the default offline mode)."""
    data = build_data(sheets, sidecar, post=post, lang=lang, impact=impact,
                      optional_sheets=optional_sheets)
    return (_HTML.replace("/*__DATA__*/null", _script_json(data))
                 .replace("__TITLE__", title or "Bundle — связи между значениями / value links"))


def emit_html(path, sheets: dict, sidecar: dict | None = None, *, post: str = "",
              title: str | None = None, lang: str = "ru", impact: str = "",
              optional_sheets=None) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render_html(sheets, sidecar, post=post, title=title, lang=lang, impact=impact,
                             optional_sheets=optional_sheets),
                 encoding="utf-8")
    return p


# --------------------------------- the page --------------------------------- #
_HTML = r"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>__TITLE__</title>
<style>
 :root{
  --bg:#f6f7f9; --card:#fff; --ink:#1c2430; --muted:#6b7686; --line:#e3e7ee;
  --forbid:#e5484d; --forbid-soft:#fdecec; --require:#2f9e54; --require-soft:#e7f6ec;
  --accent:#3b6ef5; --accent-soft:#eaf0ff; --hub:#7b6cf6; --shadow:0 1px 3px rgba(20,30,50,.08),0 6px 16px rgba(20,30,50,.06);
 }
 *{box-sizing:border-box}
 body{margin:0;font:14px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:var(--ink);background:var(--bg)}
 header{position:sticky;top:0;z-index:30;display:flex;align-items:center;gap:14px;flex-wrap:wrap;
   padding:10px 16px;background:rgba(255,255,255,.92);backdrop-filter:blur(6px);border-bottom:1px solid var(--line)}
 header h1{font-size:15px;margin:0;font-weight:650;letter-spacing:.2px}
 header .grow{flex:1}
 .seg{display:inline-flex;border:1px solid var(--line);border-radius:9px;overflow:hidden;background:#fff}
 .seg button{border:0;background:#fff;padding:7px 12px;font:inherit;cursor:pointer;color:var(--muted);display:flex;gap:6px;align-items:center}
 .seg button.on[data-pol=forbid]{background:var(--forbid-soft);color:var(--forbid);font-weight:650}
 .seg button.on[data-pol=require]{background:var(--require-soft);color:var(--require);font-weight:650}
 .dot{width:9px;height:9px;border-radius:50%;display:inline-block}
 .dot.f{background:var(--forbid)} .dot.r{background:var(--require)}
 select,input[type=number],input[type=text]{font:inherit;padding:6px 8px;border:1px solid var(--line);border-radius:8px;background:#fff;color:var(--ink)}
 button.btn{font:inherit;padding:8px 14px;border-radius:9px;border:1px solid var(--line);background:#fff;cursor:pointer;color:var(--ink)}
 button.btn:hover{border-color:#c7cedb}
 button.primary{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:650;box-shadow:var(--shadow)}
 button.primary:hover{filter:brightness(1.05)}
 button.ghost{background:transparent;border-color:transparent;color:var(--muted)}
 .chip{display:inline-flex;align-items:center;gap:6px;padding:3px 8px;border-radius:999px;background:var(--accent-soft);color:var(--accent);font-size:12.5px}
 .toggle{display:inline-flex;align-items:center;gap:7px;color:var(--muted);cursor:pointer;user-select:none}
 main{display:flex;gap:0;height:calc(100vh - 53px)}
 #stagewrap{flex:1;overflow:hidden;position:relative;touch-action:none;cursor:grab;
   background:radial-gradient(circle,#e7ebf2 1px,transparent 1px) 0 0/22px 22px}
 #stagewrap.panning{cursor:grabbing}
 #viewport{position:absolute;left:0;top:0;transform-origin:0 0;will-change:transform}
 #canvas{position:relative}
 svg#edges{position:absolute;left:0;top:0;pointer-events:none;overflow:visible}
 #zoomctl{position:absolute;right:14px;bottom:14px;z-index:25;display:flex;flex-direction:column;gap:6px;align-items:center}
 #zoomctl button{width:34px;height:34px;border:1px solid var(--line);background:#fff;border-radius:9px;cursor:pointer;font-size:17px;line-height:1;box-shadow:var(--shadow);color:var(--ink)}
 #zoomctl button:hover{border-color:#c7cedb}
 #zoomctl .zlbl{font-size:11px;color:var(--muted);background:#fff;border:1px solid var(--line);border-radius:6px;padding:1px 5px}
 #arm-popover{position:absolute;z-index:55;display:none;width:min(320px,calc(100% - 24px));background:#fff;border:1px solid var(--accent);border-radius:8px;box-shadow:var(--shadow);padding:10px;transform:translate(-50%,calc(-100% - 12px))}
 #arm-popover.show{display:block}
 #arm-popover:after{content:"";position:absolute;left:50%;bottom:-8px;transform:translateX(-50%);border-left:8px solid transparent;border-right:8px solid transparent;border-top:8px solid #fff}
 #arm-popover .pop-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:6px}
 #arm-popover .pop-head b{font-size:13px}
 #arm-popover .pop-field{display:flex;flex-direction:column;gap:4px;margin:8px 0;font-size:12px;color:var(--muted)}
 #arm-popover .pop-field select{width:100%}
 #arm-popover .pop-actions{display:flex;justify-content:flex-end;gap:7px;margin-top:8px}
 .warnbar{background:var(--forbid-soft);color:var(--forbid);border:1px solid var(--forbid);border-radius:9px;padding:7px 10px;margin-bottom:10px;font-size:12.5px;font-weight:600;line-height:1.45}
 .warnbar:empty{display:none}
 .resolve-actions{display:grid;gap:6px;margin:8px 0 10px}
 .resolve-actions:empty{display:none}
 .resolve-btn{display:grid;gap:2px;text-align:left;border:1px solid #f1b7ba;background:#fff;border-radius:8px;padding:7px 9px;cursor:pointer;color:var(--ink)}
 .resolve-btn:hover{border-color:var(--forbid);background:#fff8f8}
 .resolve-btn .keep{font-weight:700;font-size:12.5px;color:#263044}
 .resolve-btn .drop{font-size:11.5px;color:var(--muted);line-height:1.35}
 .resolve-title{font-size:12px;font-weight:700;color:var(--forbid)}
 .col-h{position:absolute;transform:translateX(-50%);top:14px;font-weight:650;color:#41506a;font-size:13px;
   background:#fff;border:1px solid var(--line);padding:4px 12px;border-radius:999px;box-shadow:var(--shadow);white-space:nowrap}
 .opt-badge{display:inline-flex;margin-left:6px;padding:1px 5px;border-radius:999px;background:#fff7df;color:#8a5a00;border:1px solid #f1cf77;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.3px}
 .cond-build{margin:2px 0 6px;padding:3px 0 3px 8px;border-left:2px solid var(--accent-soft)}
 .ct-row select,.ct-row input{padding:3px 5px;font-size:12px}
 .ct-row .ct-del{margin-left:auto}
 .ct-multi{display:inline-flex;flex-wrap:wrap;gap:4px;align-items:center}
 .cj.on{background:var(--accent-soft);color:var(--accent);font-weight:650}
 .le-cond-json summary{cursor:pointer;font-size:11px;color:var(--muted);margin:3px 0}
 .node{position:absolute;transform:translate(-50%,-50%);padding:7px 13px;border:1px solid #c8d0de;border-radius:12px;
   background:#fff;cursor:grab;touch-action:none;white-space:nowrap;font-size:13px;user-select:none;box-shadow:var(--shadow);max-width:230px;overflow:hidden;text-overflow:ellipsis}
 .node:hover{border-color:var(--accent)}
 .node:focus{outline:2px solid var(--accent);outline-offset:1px}
 .node.sel{border-color:var(--accent);background:var(--accent-soft);box-shadow:0 0 0 3px var(--accent-soft)}
 .node.tray{border-color:var(--hub);background:#f1eefe}
 .node.dragging{cursor:grabbing;border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft);z-index:6}
 /* node-centric spotlight (additive — the value-LINES are preserved; this only highlights them) */
 .node.hl-self{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft),0 0 0 6px #dbe5ff;z-index:5}
 .node.hl-f{border-color:var(--forbid);box-shadow:0 0 0 3px var(--forbid-soft)}
 .node.hl-r{border-color:var(--require);box-shadow:0 0 0 3px var(--require-soft)}
 .node.hl-ctx{border-color:#d6960a;box-shadow:0 0 0 3px #fdf1d6}
 #canvas.spotlight .node:not(.hl-self):not(.hl-f):not(.hl-r):not(.hl-ctx){opacity:.4}
 .bdots{display:inline-flex;gap:2px;margin-left:7px;vertical-align:middle}
 .bdots i{width:6px;height:6px;border-radius:50%;display:inline-block}
 .bdots i.f{background:var(--forbid)} .bdots i.r{background:var(--require)} .bdots i.c{background:#d6960a}
 line.edge{stroke-width:2.6;pointer-events:stroke;cursor:pointer;stroke-linecap:round}
 line.edge:hover{stroke-width:5}
 .edge.f{stroke:var(--forbid)} .edge.r{stroke:var(--require)}
 .edge.dim{opacity:.35} .edge.hot{stroke-width:5}
 .edge.bad{stroke-dasharray:5 3;stroke-width:4;filter:drop-shadow(0 0 2px var(--forbid))}
 /* node inspector card — the side panel made descriptive PER NODE + per bond-line */
 #nodeinfo .ni-head{display:flex;align-items:center;gap:7px;justify-content:space-between;margin-bottom:6px}
 #nodeinfo .ni-val{font-weight:650}#nodeinfo .ni-col{color:var(--muted);font-size:12px}
 #nodeinfo .ni-row{display:flex;flex-direction:column;gap:2px;padding:6px 7px;border:1px solid var(--line);border-radius:9px;margin-bottom:6px;cursor:pointer;background:#fff}
 #nodeinfo .ni-row:hover{border-color:var(--accent);background:var(--accent-soft)}
 #nodeinfo .ni-row.sel{border-color:var(--accent);box-shadow:0 0 0 2px var(--accent-soft)}
 #nodeinfo .ni-line{display:flex;align-items:center;gap:6px;font-size:13px;flex-wrap:wrap}
 #nodeinfo .ni-chip{padding:2px 8px;border-radius:999px;border:1px solid var(--line);background:#fbfcfe;white-space:nowrap}
 #nodeinfo .ni-chip.self{border-color:var(--accent);background:var(--accent-soft);font-weight:600}
 #nodeinfo .ni-conn{font-weight:800;letter-spacing:-1px}
 #nodeinfo .ni-conn.f{color:var(--forbid)} #nodeinfo .ni-conn.r{color:var(--require)}
 #nodeinfo .ni-when{font-size:12px;color:#8a5a00;background:#fdf6e6;border:1px solid #f1cf77;border-radius:6px;padding:1px 7px;margin-top:2px;align-self:flex-start}
 #nodeinfo .ni-ctx{font-size:12.5px;color:var(--muted)}
 #nodeinfo .ni-x{margin-left:auto;border:0;background:transparent;color:var(--muted);cursor:pointer;font-size:13px}
 #nodeinfo .ni-empty{color:var(--muted);font-size:12.5px;padding:4px 0}
 .hub{cursor:pointer;pointer-events:all}
 .armctl{pointer-events:all;cursor:pointer;fill:#fff;stroke:var(--accent);stroke-width:2;filter:drop-shadow(0 1px 2px rgba(20,30,50,.18))}
 .armctl:hover,.armctl.arm-hot{fill:var(--accent-soft);stroke-width:3}
 .edge.arm-hot{stroke-width:5}
 aside{width:420px;min-width:420px;border-left:1px solid var(--line);background:var(--bg);overflow:auto;padding:14px}
 .card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px 13px;margin-bottom:12px;box-shadow:var(--shadow)}
 .card h2{font-size:12px;text-transform:uppercase;letter-spacing:.6px;color:var(--muted);margin:0 0 9px}
 .builder-grid{display:grid;gap:10px}
 .builder-section{border-top:1px solid var(--line);padding-top:10px}
 .builder-section:first-child{border-top:0;padding-top:0}
 .mini-title{font-size:13px;font-weight:700;color:#344054;margin-bottom:6px}
 .inline-fields{display:grid;grid-template-columns:1fr 1fr;gap:8px}
 .inline-fields.three{grid-template-columns:1fr 1fr auto}
 .field{display:flex;flex-direction:column;gap:3px;font-size:12px;color:var(--muted)}
 .field select,.field input{width:100%;min-width:0}
 .builder-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:4px}
 .builder-actions .btn{flex:1;min-width:132px}
 .btn.sm{padding:5px 9px;font-size:12.5px}
 .select-row{display:flex;align-items:flex-end;gap:8px}
 .select-row .field{flex:1}
 .type-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
 .type-card{display:flex;align-items:center;gap:8px;text-align:left;border:1px solid var(--line);background:#fff;border-radius:8px;padding:8px;cursor:pointer;color:var(--ink);min-height:44px}
 .type-card:hover{border-color:#c7cedb;background:#fbfcfe}
 .type-card.on{border-color:var(--accent);background:var(--accent-soft);box-shadow:0 0 0 2px var(--accent-soft)}
 .type-card .ico{width:24px;height:24px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-weight:800;color:#fff;flex:0 0 auto}
 .type-card .ico.f{background:var(--forbid)} .type-card .ico.r{background:var(--require)} .type-card .ico.a{background:var(--accent)} .type-card .ico.h{background:var(--hub)}
 .type-card .cap{display:block;font-size:12px;color:var(--muted);line-height:1.25}
 .visual-preview,.rule-preview{display:flex;align-items:center;gap:7px;flex-wrap:wrap;border:1px dashed #cbd3e1;background:#fbfcfe;border-radius:8px;padding:8px;margin:9px 0 4px;min-height:42px}
 .visual-chip,.rule-token{display:inline-flex;align-items:center;gap:4px;border:1px solid var(--line);background:#fff;border-radius:999px;padding:3px 8px;font-size:12.5px;white-space:nowrap}
 .visual-chip b,.rule-token b{font-size:12px;color:#344054}
 .visual-conn{height:3px;min-width:34px;border-radius:999px;background:var(--accent);position:relative}
 .visual-conn:after{content:"";position:absolute;right:-1px;top:-4px;border-left:8px solid var(--accent);border-top:5px solid transparent;border-bottom:5px solid transparent}
 .visual-conn.f{background:var(--forbid)} .visual-conn.f:after{border-left-color:var(--forbid)}
 .visual-conn.r{background:var(--require)} .visual-conn.r:after{border-left-color:var(--require)}
 .rule-op{display:inline-flex;align-items:center;justify-content:center;min-width:26px;height:24px;border-radius:7px;background:var(--accent-soft);color:var(--accent);font-weight:800}
 .logic-pill{display:inline-flex;align-items:center;border-radius:999px;background:#eef0f4;color:#344054;padding:2px 7px;font-size:11px;font-weight:700}
 .json-fallback{margin-top:8px}
 .impact b{font-size:22px;font-weight:700}
 .bar{height:8px;border-radius:5px;background:#eef0f4;overflow:hidden;margin:8px 0}
 .bar > i{display:block;height:100%;background:linear-gradient(90deg,var(--forbid),#f08)}
 .row{display:flex;align-items:center;gap:8px;padding:7px 6px;border-radius:9px}
 .row:hover{background:#f4f6f9}
 .row.sel{background:var(--accent-soft)}
 .row .txt{flex:1;font-size:13px}
 .row .txt small{color:var(--muted)}
 .row select{padding:3px 5px;font-size:12px}
 .pill{font-size:11px;font-weight:700;padding:2px 7px;border-radius:6px}
 .pill.f{background:var(--forbid-soft);color:var(--forbid)} .pill.r{background:var(--require-soft);color:var(--require)}
 .x{border:0;background:transparent;color:var(--muted);cursor:pointer;font-size:16px;line-height:1;padding:2px 6px;border-radius:6px}
 .x:hover{background:var(--forbid-soft);color:var(--forbid)}
 .empty{color:var(--muted);font-size:13px;padding:6px 2px}
 .hint{color:var(--muted);font-size:12.5px}
 details summary{cursor:pointer;font-size:12px;text-transform:uppercase;letter-spacing:.6px;color:var(--muted);margin-bottom:8px}
 table.params{width:100%;border-collapse:collapse;font-size:12.5px}
 table.params td{padding:3px 4px;border-bottom:1px solid var(--line);vertical-align:middle}
 table.params input{width:100%}
 #tray{position:fixed;left:50%;bottom:18px;transform:translateX(-50%);z-index:40;display:none;gap:10px;align-items:center;
   background:#fff;border:1px solid var(--line);border-radius:12px;padding:9px 12px;box-shadow:var(--shadow)}
 #tray.show{display:flex}
 #overlay{position:fixed;inset:0;background:rgba(246,247,249,.96);z-index:99;display:none;align-items:center;justify-content:center}
 #overlay.show{display:flex}
 #overlay .ok{text-align:center;background:#fff;border:1px solid var(--line);border-radius:16px;padding:34px 40px;box-shadow:var(--shadow);max-width:460px}
 #overlay .mark{width:64px;height:64px;border-radius:50%;background:var(--require-soft);color:var(--require);display:flex;
   align-items:center;justify-content:center;font-size:34px;margin:0 auto 14px}
 .toast{position:fixed;left:50%;bottom:18px;transform:translateX(-50%);background:#1c2430;color:#fff;padding:9px 16px;
   border-radius:10px;z-index:60;opacity:0;transition:opacity .2s;pointer-events:none;font-size:13px}
 .toast.show{opacity:1}
 dialog{border:1px solid var(--line);border-radius:14px;padding:0;box-shadow:var(--shadow);max-width:520px;width:92%}
 dialog.wide{max-width:760px}
 dialog .dlg{padding:18px 20px}
 dialog h3{margin:0 0 10px;font-size:15px}
 dialog label{display:block;font-size:12px;color:var(--muted);margin:10px 0 4px}
 dialog .multi{display:flex;flex-wrap:wrap;gap:6px}
 dialog .multi label{display:inline-flex;align-items:center;gap:5px;margin:0;color:var(--ink);background:#f4f6f9;padding:4px 9px;border-radius:8px;cursor:pointer}
 .dlg-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:16px}
 #linkedit,#edlg-body{border:1px solid var(--accent);background:var(--accent-soft);border-radius:10px;padding:9px 11px;margin-bottom:10px}
 #linkedit:empty{display:none}
 #edlg-body:empty{display:none}
 #edlg .dlg{max-height:82vh;overflow:auto}
 #linkedit .le-head,#edlg-body .le-head{display:flex;justify-content:space-between;align-items:center}
 #linkedit .le-txt,#edlg-body .le-txt{font-size:12.5px;margin:3px 0 7px}
 .le-row{display:flex;align-items:center;gap:8px;margin:6px 0;flex-wrap:wrap}
 .arm-list{display:grid;gap:5px;margin:6px 0}
 .arm-row{display:flex;align-items:center;gap:7px;border:1px solid var(--line);background:#fff;border-radius:8px;padding:5px 7px}
 .arm-row.sel{border-color:var(--accent);background:var(--accent-soft)}
 .arm-row .txt{flex:1;font-size:12.5px;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 .le-lbl{font-size:12px;color:var(--muted);min-width:60px}
 .le-chips{display:flex;gap:5px;flex-wrap:wrap}
 .seg.sm button{padding:4px 10px;font-size:12.5px}
 .chip .chx{border:0;background:transparent;color:var(--accent);cursor:pointer;font-size:12px;padding:0 0 0 4px}
 .le-add{font-size:12px;padding:3px 5px}
 .fpal{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin:5px 0}
 .btn.fp{padding:3px 9px;font-size:13px;min-width:30px}
 #fbuilt{background:#111;color:#7fdc7f;padding:2px 7px;border-radius:4px;font-size:12.5px;min-height:18px;display:inline-block}
 .ftree{padding:6px 2px;min-height:36px;line-height:2}
 .blk{display:inline-flex;align-items:center;gap:5px;border:1px solid #c8d0de;border-radius:9px;padding:3px 6px;margin:2px;background:#fff}
 .blk.leaf{background:#eef3ff;border-color:#aebde0}
 .slot{border:1px dashed #9aa6bd;background:#f6f7f9;color:#6b7686;border-radius:7px;padding:2px 9px;cursor:pointer;font-size:13px;margin:2px}
 .slot:hover{border-color:var(--accent);color:var(--accent)}
 .fmenu{display:inline-flex;gap:4px;flex-wrap:wrap;border:1px solid var(--accent);border-radius:8px;padding:3px;background:var(--accent-soft);margin:2px}
 .blk select,.blk input{font-size:12.5px;padding:1px 3px}
 .fpalette{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin:4px 0;padding:6px;border:1px dashed var(--line);border-radius:9px;background:#fbfcfe}
 .palitem{cursor:grab;border:1px solid #aebde0;background:#eef3ff;border-radius:8px;padding:3px 10px;font-size:12.5px;user-select:none}
 .palitem:active{cursor:grabbing}
 .blk[draggable]{cursor:grab}
 .drop-ok{outline:2px solid var(--require);outline-offset:1px;background:var(--require-soft)!important}
 .drop-no{outline:2px solid var(--forbid);outline-offset:1px}
</style></head><body>
<header>
 <h1 id="t-title">Bundle · связи между значениями</h1>
 <div class="seg" role="group" aria-label="link type">
   <button id="m-forbid" data-pol="forbid" class="on"><span class="dot f"></span><span id="t-forbid">Запрещать</span></button>
   <button id="m-require" data-pol="require"><span class="dot r"></span><span id="t-require">Требовать</span></button>
 </div>
 <label class="hint" style="display:flex;align-items:center;gap:6px">
   <span id="t-gate">Позиция</span>
   <select id="gate"><option value="any">любая</option><option value="adjacent">рядом</option><option value="within">в пределах…</option></select>
   <input id="within" type="number" min="1" value="2" style="width:58px;display:none">
 </label>
 <label class="toggle"><input type="checkbox" id="multi"><span id="t-multi">Связь 3+ листов</span></label>
 <div class="grow"></div>
 <span class="hint" id="srcinfo"></span>
 <button class="btn ghost" id="lang">EN</button>
 <button class="btn" id="dl" title="sidecar.json">⤓ sidecar.json</button>
 <button class="btn primary" id="submit"><span id="t-submit">Отправить</span> ⏎</button>
</header>
<main>
 <div id="stagewrap"><div id="viewport"><div id="canvas"></div></div>
   <div id="zoomctl"><button id="zin" title="приблизить · + · колесо вверх">＋</button><button id="zout" title="отдалить · − · колесо вниз">－</button><button id="zfit" title="вписать · 0">⤢</button><div class="zlbl" id="zpct">100%</div></div>
   <div id="arm-popover" role="dialog" aria-label="sub-bond editor"><div class="pop-head"><b id="ap-title">Sub-bond</b><button class="x" id="ap-close" title="close">✕</button></div><div class="hint" id="ap-summary"></div><label class="pop-field"><span id="t-apval">Value</span><select id="ap-value"></select></label><div class="pop-actions"><button class="btn ghost" id="ap-discard">Discard</button><button class="btn primary" id="ap-save">Save</button></div></div>
 </div>
 <aside>
  <div class="card impact"><h2 id="t-impact">Влияние (предпросмотр)</h2><div class="warnbar" id="warn"></div><div class="resolve-actions" id="resolve-actions"></div><div id="impact"></div><div class="bar"><i id="bar" style="width:0"></i></div><div class="hint" id="impacthint"></div></div>
  <div class="card builder" id="builder"><h2 id="t-build">Создать ограничение</h2>
    <div class="builder-grid">
      <div class="builder-section">
        <div class="mini-title" id="t-quicklink">Быстрая связь</div>
        <div class="type-grid" id="quick-typecards">
          <button class="type-card on" id="quick-forbid" type="button"><span class="ico f">×</span><span><b id="t-card-forbid">Нельзя вместе</b><span class="cap" id="t-card-forbid-cap">красная линия</span></span></button>
          <button class="type-card" id="quick-require" type="button"><span class="ico r">✓</span><span><b id="t-card-require">Должно быть вместе</b><span class="cap" id="t-card-require-cap">зелёная линия</span></span></button>
        </div>
        <select id="quick-pol" style="display:none"><option value="forbid">forbid</option><option value="require">require</option></select>
        <div class="inline-fields" style="margin-top:8px">
          <label class="field"><span id="t-qpos">Позиция</span><select id="quick-gate"><option value="any">any</option><option value="adjacent">adjacent</option><option value="within">within</option></select></label>
          <label class="field"><span>&nbsp;</span><input id="quick-within" type="number" min="1" value="2" style="display:none"></label>
        </div>
        <div class="select-row" style="margin-top:8px">
          <label class="field"><span id="t-qfrom">От</span><select id="quick-s1"></select><select id="quick-v1"></select></label>
          <label class="field"><span id="t-qto">К</span><select id="quick-s2"></select><select id="quick-v2"></select></label>
        </div>
        <div class="visual-preview" id="quick-preview"></div>
        <div class="builder-actions"><button class="btn primary" id="quick-add"><span id="t-qadd">Создать линию</span></button></div>
      </div>
      <div class="builder-section">
        <div class="mini-title" id="t-moretypes">Другие ограничения</div>
        <div class="type-grid">
          <button class="type-card" id="quick-map" type="button"><span class="ico a">→</span><span><b id="t-qmap">Зависимость</b><span class="cap" id="t-qmap-cap">A управляет B</span></span></button>
          <button class="type-card" id="quick-rule" type="button"><span class="ico h">∑</span><span><b id="t-qrule">Правило</b><span class="cap" id="t-qrule-cap">блоки условий</span></span></button>
        </div>
      </div>
    </div>
  </div>
  <div class="card"><h2 id="t-node">Значение и его связи</h2><div id="nodeinfo"></div></div>
  <div class="card"><h2 id="t-links">Связи</h2><div id="linkedit"></div><div id="links"></div></div>
  <div class="card"><details id="advanced"><summary id="t-adv">Формулы и параметры (продвинутое)</summary>
    <div style="margin:6px 0 12px"><button class="btn" id="addformula">＋ <span id="t-addf">формула-связь</span></button>
      <button class="btn" id="addmapping">＋ <span id="t-addm">зависимость</span></button></div>
    <div id="formulas"></div>
    <div style="margin-top:12px"><div class="hint" id="t-params" style="margin-bottom:6px">Параметры значений (для формул): <code>charge=2, n=1</code></div>
      <table class="params"><tbody id="params"></tbody></table></div>
  </details></div>
 </aside>
</main>
<div id="tray"><span class="hint" id="t-tray">Выбрано:</span><span id="traychips"></span>
  <button class="btn primary" id="makebond"><span id="t-make">Создать связь</span></button>
  <button class="btn ghost" id="cleartray">✕</button></div>
<div id="overlay"><div class="ok"><div class="mark">✓</div><h3 id="t-okh">Связи отправлены в конвейер</h3>
  <p class="hint" id="okmsg"></p><button class="btn" onclick="location.reload()" id="t-edit">Изменить ещё</button></div></div>
<div class="toast" id="toast"></div>
<dialog id="fdlg"><div class="dlg"><h3 id="t-fdlg">Формула-связь (when)</h3>
  <label id="t-fsheets">Листы (≥2):</label><div class="multi" id="fsheets"></div>
  <label id="t-fexpr">Формула над параметрами (булева):</label>
  <div class="seg sm" id="fmode" style="margin:4px 0">
    <button id="fmode-text" class="on"><span id="t-ftext">Текст</span></button>
    <button id="fmode-blocks"><span id="t-fblocks">Блоки</span></button></div>
  <input type="text" id="fexpr" placeholder="A.charge * C.charge > 0">
  <div id="fblocks" style="display:none">
    <div class="hint" id="t-fhint2" style="margin:2px 0 6px">Перетащите блок из палитры в слот ＋ (или кликните слот). Блоки вкладываются и переставляются.</div>
    <div id="fpalette" class="fpalette"></div>
    <div id="ftree" class="ftree"></div>
    <div class="fpal"><span class="le-lbl" id="t-fbuilt">формула:</span><code id="fbuilt"></code></div>
  </div>
  <div class="hint" id="fhint" style="margin-top:6px"></div>
  <div class="dlg-actions"><button class="btn ghost" id="fcancel">Отмена</button><button class="btn primary" id="fadd">Добавить</button></div>
</div></dialog>
<dialog id="mdlg"><div class="dlg"><h3 id="t-mdlg">Зависимость (mapping)</h3>
  <div class="le-row"><span id="t-mif">если</span> <select id="m-src"></select>
    <span id="t-mthen">то допустимо</span> <select id="m-tgt"></select></div>
  <div id="m-allow" style="margin:8px 0;max-height:50vh;overflow:auto"></div>
  <div class="hint" id="mhint"></div>
  <div class="dlg-actions"><button class="btn ghost" id="mcancel">Отмена</button><button class="btn primary" id="madd">Добавить</button></div>
</div></dialog>
<dialog id="rdlg"><div class="dlg"><h3 id="t-rdlg">Relation / assert rule</h3>
  <div class="type-grid" id="r-pol-cards">
    <button class="type-card" id="r-require" type="button"><span class="ico r">✓</span><span><b id="t-r-require">Должно быть правдой</b></span></button>
    <button class="type-card" id="r-forbid" type="button"><span class="ico f">×</span><span><b id="t-r-forbid">Нельзя, если правда</b></span></button>
  </div>
  <select id="r-pol" style="display:none"><option value="require">require</option><option value="forbid">forbid</option></select>
  <div class="rule-preview" id="r-preview"></div>
  <label id="t-rbody">Rule body</label><div id="r-builder"></div>
  <details class="le-cond-json json-fallback"><summary class="hint" id="t-rjson">JSON</summary><div class="le-row"><input id="r-json" type="text" style="flex:1;min-width:160px"><button class="btn" id="r-json-apply">OK</button></div></details>
  <div class="hint" id="rhint"></div>
  <div class="dlg-actions"><button class="btn ghost" id="rcancel">Отмена</button><button class="btn primary" id="radd">Добавить</button></div>
</div></dialog>
<dialog id="edlg" class="wide"><div class="dlg"><h3 id="t-edlg">Свойства связи</h3>
  <div id="edlg-body"></div>
  <div class="dlg-actions"><button class="btn primary" id="eclose">OK</button></div>
</div></dialog>
<dialog id="adlg"><div class="dlg"><h3 id="t-adlg">Ветка связи</h3>
  <div class="hint" id="a-summary"></div>
  <label id="t-aval">Значение</label><select id="a-value"></select>
  <div class="dlg-actions"><button class="btn ghost" id="acancel">Отмена</button><button class="btn" id="adel">Удалить ветку</button><button class="btn primary" id="aapply">OK</button></div>
</div></dialog>
<script>
const D=/*__DATA__*/null;
const COLW=210, ROWH=52, PADX=130, PADY=66;
const I18N={
 ru:{title:"Bundle · связи между значениями",forbid:"Запрещать",require:"Требовать",gate:"Позиция",
   buildTitle:"Создать ограничение",quickLink:"Быстрая связь",cardForbid:"Нельзя вместе",cardForbidCap:"красная линия",cardRequire:"Должно быть вместе",cardRequireCap:"зелёная линия",qFrom:"От",qTo:"К",qType:"Тип",qPosition:"Позиция",qPreview:"Получится",qAdd:"Создать линию",moreTypes:"Другие ограничения",qMap:"Зависимость",qMapCap:"A управляет B",qRule:"Правило",qRuleCap:"блоки условий",rDlg:"Правило relation/assert",eDlg:"Свойства связи",rPol:"Тип",rRequire:"Должно быть правдой",rForbid:"Нельзя, если правда",rBody:"Соберите условие",rJson:"JSON запасной режим",rNeed:"Добавьте хотя бы одно условие",rMade:"Правило создано",extendPick:"Связь выбрана: кликните значение, чтобы добавить его в эту же связь",addToLink:"Значение добавлено в выбранную связь",alreadyInLink:"Это значение уже есть в выбранной связи",cannotExtend:"Эта связь редактируется через окно свойств",undo:"Отменено",nothingUndo:"Нечего отменять",armDlg:"Ветка связи",armValue:"Значение",armDelete:"Удалить ветку",armEdit:"изменить ветку",armBranch:"ветка",armBranches:"ветки общего узла",armDeleted:"Ветка удалена",armChanged:"Ветка изменена",resolveTitle:"Разрешить противоречие",resolveInFavor:"Resolve in favor",resolveDeletes:"удалит проигравшие",resolveDone:"Противоречие разрешено",subBond:"Под-связь",save:"Save",discard:"Discard",close:"Закрыть",
   nodeTitle:"Значение и его связи",niMember:"связи-линии этого значения:",niCtx:"участвует как условие в:",niWhen:"только если",niEmpty:"у этого значения пока нет связей — кликните значение в другом столбце, чтобы связать",niPickHint:"наведите или выберите значение, чтобы увидеть его связи",niForbid:"никогда вместе с",niRequire:"требует/вместе с",
   multi:"Группа (M:M)",combosW:"комбинаций",submit:"Отправить",impact:"Влияние (предпросмотр)",links:"Связи",
   adv:"Формулы и параметры (продвинутое)",addf:"формула-связь",params:"Параметры значений (для формул):",
   tray:"Выбрано:",make:"Создать связь",okh:"Связи отправлены в конвейер",edit:"Изменить ещё",
   fdlg:"Формула-связь (when)",fsheets:"Листы (≥2):",fexpr:"Формула над параметрами (булева):",
   emptyLinks:"Пока нет связей. Кликните значение, затем значение в другом столбце — протянется линия.",
   emptyStage:"Нет листов с ≥2 значениями для связывания.",
   forbidW:"запрет",requireW:"нужно",together:"вместе",adjW:"рядом",withinW:"в пределах",
   pos:"любая позиция",hintDraw:"Кликните значение, затем — значение в ДРУГОМ столбце. Красная = запрет, зелёная = нужно. Для связи ГРУПП значений (Many:Many) включите «Группа». Нет связей? Просто «Отправить».",
   okmsg:n=>`${n} связь(ей) отправлено. Можно закрыть вкладку.`,
   removes:(n,m)=>`убирает ${n} из ${m}`,kept:k=>`${k} останется`,big:"Полный продукт слишком велик для точного подсчёта — точную цифру даст прогон --sieve.",
   nodraw:"эта формула-связь применяется к листам целиком (не к конкретным значениям)",saved:"Отправлено ✓",dlsaved:"sidecar.json скачан",
   editLink:"Условие связи",deselect:"снять",pol:"тип",apply:"OK",addVal:"добавить",badFormula:"недопустимая формула",gAny:"любая",gAdj:"рядом",gWithin:"в пределах",formulaLbl:"формула",
   fText:"Текст",fBlocks:"Блоки",fbuilt:"формула:",palLbl:"палитра:",mCmp:"сравнение",mLogic:"и / или",mNot:"не",mArith:"+ − ×",mParam:"лист.параметр",mNum:"число",
   exactBadge:"точно",exactNote:"точно по реальной БД (fw_final × fw_optX)",optionalW:"опц.",
   onlyWhen:"только когда",combine:"если",cAll:"всё",cAny:"любое",addCond:"＋ условие",condAdv:"сложное условие — правьте JSON",
   opIs:"равно",opIsNot:"не равно",opHas:"содержит",opIn:"любое из",opNin:"ни одно из",opGe:"кол-во ≥",opLe:"кол-во ≤",opEqS:"равно столбцу",
   opPresent:"задан?",opYes:"да",opNo:"нет",opGeC:"≥",opLeC:"≤",opGtC:">",opLtC:"<",opGeS:"≥ столбца",opLeS:"≤ столбца",opSub:"⊆ столбца",opSup:"⊇ столбца",
   mapAdd:"зависимость (mapping)",mapDlg:"Зависимость: значение одного столбца ограничивает другой",mapIf:"если",mapThen:"то допустимо",mapPick:"выберите два столбца",mapAddBtn:"Добавить зависимость",condLbl:"условие связи"},
 en:{title:"Bundle · value links",forbid:"Forbid",require:"Require",gate:"Position",
   buildTitle:"Create constraint",quickLink:"Quick link",cardForbid:"Never together",cardForbidCap:"red line",cardRequire:"Must be together",cardRequireCap:"green line",qFrom:"From",qTo:"To",qType:"Type",qPosition:"Position",qPreview:"Result",qAdd:"Create line",moreTypes:"Other constraints",qMap:"Dependency",qMapCap:"A controls B",qRule:"Rule",qRuleCap:"condition blocks",rDlg:"Relation / assert rule",eDlg:"Link properties",rPol:"Type",rRequire:"Must be true",rForbid:"Forbidden when true",rBody:"Build the condition",rJson:"JSON fallback",rNeed:"Add at least one condition",rMade:"Rule created",extendPick:"Link selected: click a value to add it to this same link",addToLink:"Value added to the selected link",alreadyInLink:"That value is already in the selected link",cannotExtend:"Edit this link in the properties dialog",undo:"Undone",nothingUndo:"Nothing to undo",armDlg:"Link branch",armValue:"Value",armDelete:"Delete branch",armEdit:"edit branch",armBranch:"branch",armBranches:"hub branches",armDeleted:"Branch deleted",armChanged:"Branch changed",resolveTitle:"Resolve contradiction",resolveInFavor:"Resolve in favor",resolveDeletes:"deletes loser",resolveDone:"Contradiction resolved",subBond:"Sub-bond",save:"Save",discard:"Discard",close:"Close",
   nodeTitle:"Value & its bonds",niMember:"this value's bond-lines:",niCtx:"used as a condition in:",niWhen:"only when",niEmpty:"this value has no bonds yet — click a value in another column to bond it",niPickHint:"hover or select a value to see its bonds",niForbid:"never with",niRequire:"requires / with",
   multi:"Group (M:M)",combosW:"combos",submit:"Submit",impact:"Impact (preview)",links:"Links",
   adv:"Formulas & parameters (advanced)",addf:"formula link",params:"Value parameters (for formulas):",
   tray:"Selected:",make:"Make link",okh:"Links sent to the pipeline",edit:"Edit again",
   fdlg:"Formula link (when)",fsheets:"Sheets (≥2):",fexpr:"Boolean formula over parameters:",
   emptyLinks:"No links yet. Click a value, then a value in another column — a line is drawn.",
   emptyStage:"No sheets with ≥2 values to bond.",
   forbidW:"forbid",requireW:"require",together:"together",adjW:"adjacent",withinW:"within",
   pos:"any position",hintDraw:"Click a value, then a value in a DIFFERENT column. Red = forbid, green = require. For GROUP (Many:Many) links turn on «Group». Nothing to link? Just press Submit.",
   okmsg:n=>`${n} link(s) sent. You can close this tab.`,
   removes:(n,m)=>`removes ${n} of ${m}`,kept:k=>`${k} kept`,big:"Full product too large to count live — run --sieve for the exact figure.",
   nodraw:"this formula link applies to whole sheets (not to specific values)",saved:"Submitted ✓",dlsaved:"sidecar.json downloaded",
   editLink:"Link condition",deselect:"clear",pol:"type",apply:"OK",addVal:"add",badFormula:"unsafe formula",gAny:"any",gAdj:"adjacent",gWithin:"within",formulaLbl:"formula",
   fText:"Text",fBlocks:"Blocks",fbuilt:"formula:",palLbl:"palette:",mCmp:"compare",mLogic:"and / or",mNot:"not",mArith:"+ − ×",mParam:"sheet.param",mNum:"number",
   exactBadge:"exact",exactNote:"exact over the real DB (fw_final × fw_optX)",optionalW:"optional",
   onlyWhen:"only when",combine:"if",cAll:"all",cAny:"any",addCond:"＋ condition",condAdv:"complex condition — edit JSON",
   opIs:"is",opIsNot:"is not",opHas:"contains",opIn:"any of",opNin:"none of",opGe:"count ≥",opLe:"count ≤",opEqS:"equals column",
   opPresent:"present?",opYes:"yes",opNo:"no",opGeC:"≥",opLeC:"≤",opGtC:">",opLtC:"<",opGeS:"≥ column",opLeS:"≤ column",opSub:"⊆ column",opSup:"⊇ column",
   mapAdd:"dependency (mapping)",mapDlg:"Dependency: one column's value constrains another",mapIf:"if",mapThen:"then allow",mapPick:"pick the two columns",mapAddBtn:"Add dependency",condLbl:"link condition"}
};
let lang=(D.lang in I18N)?D.lang:"ru";
const T=()=>I18N[lang];
const OPTIONAL=new Set(D.optional_sheets||[]);
let bonds=(D.bonds||[]).map(b=>({polarity:b.polarity||"forbid",sides:Object.fromEntries(Object.entries(b.sides||{}).map(([s,v])=>[s,(v||[]).slice()])),gate:b.gate||{},when:b.when||null,condition:b.condition||null,mapping:b.mapping||null,assert:b.assert||null,desc:b.desc||""}));
let params=JSON.parse(JSON.stringify(D.params||{}));
const ORDERS=D.orders||{};                               // {sheet:[v0,v1,…]|"numeric"|"date"} — ordinal ranks
let mode="forbid", gate={}, multi=false, sel=null, tray=[], selBond=null, selArm=null;   // multi = group / Many:Many mode
// vertical-drag overrides (node id -> world y), the pan/zoom viewport, transient drag/pan, contradiction state
let nodeY={}, view={scale:1,tx:0,ty:0}, drag=null, pan=null, suppressClick=false, emptyResult=false, conflictBonds=new Set(), didAutoFit=false;
let undoStack=[], restoring=false, armDraft=null, clickTimer=null;
const ZMIN=0.25, ZMAX=4, clampZ=z=>Math.max(ZMIN,Math.min(ZMAX,z));

const $=id=>document.getElementById(id);
const esc=s=>String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const attr=s=>esc(s).replace(/'/g,"&#39;");
const nid=(s,v)=>JSON.stringify([s,v]);
const SHEETS=D.sheets;                                   // [[sheet,[values]]...]
const SI={};SHEETS.forEach((s,i)=>SI[s[0]]=i);
function pos(si,vi){return {x:PADX+si*COLW,y:PADY+vi*ROWH};}
const NI={};SHEETS.forEach((s,si)=>s[1].forEach((v,vi)=>NI[nid(s[0],v)]={si,vi}));
function stageH(){const rows=Math.max(...SHEETS.map(s=>s[1].length),1);return PADY+rows*ROWH+24;}
function clampY(y){return y;}                    // no vertical drag bounds: users may spread dense nodes freely
// a node's LIVE position: x is LOCKED to its slot's column; y is the dragged override, else the default row.
function nodeXY(s,v){const i=NI[nid(s,v)];if(!i)return null;const k=nid(s,v);
 return {x:PADX+i.si*COLW, y:(k in nodeY)?nodeY[k]:PADY+i.vi*ROWH};}
// ---- contradiction guard (mirror of editor.py find_contradictions): same sheets+gate+members, opposite polarity ----
function canonGate(g){g=g||{};return g.adjacent?"a":("within"in g?"w"+(+g.within):"");}
function condKey(c){return JSON.stringify(c||{});}
function conflictKey(b){const sh=bondSheets(b).slice().sort();
 return JSON.stringify([sh, sh.map(s=>(b.sides[s]||[]).slice().sort()), canonGate(b.gate), condKey(b.condition)]);}   // polarity-agnostic
function setIntersection(a,b){const out=new Set();for(const v of a)if(b.has(v))out.add(v);return out;}
function setSubset(a,b){for(const v of a)if(!b.has(v))return false;return true;}
function findConflicts(){const seen={},bad=new Set(),req={};
 bonds.forEach((b,i)=>{if(b.when||b.mapping||b.assert)return;const k=conflictKey(b);(seen[k]=seen[k]||[]).push([i,b.polarity]);});
 Object.values(seen).forEach(g=>{if(new Set(g.map(x=>x[1])).size>1)g.forEach(([i])=>bad.add(i));});
 // Multiple green "require" links are conjunctive. If they demand different values for the same
 // sheet, no row can survive; mark the whole cluster, not only exact opposite red/green duplicates.
 bonds.forEach((b,i)=>{if(b.when||b.mapping||b.assert||b.polarity!=="require")return;
   for(const s of bondSheets(b)){const vals=new Set(b.sides[s]||[]);if(!vals.size)continue;
     if(!req[s])req[s]={vals:new Set(vals),idxs:new Set([i])};
     else{const next=setIntersection(req[s].vals,vals);req[s].idxs.add(i);req[s].vals=next;if(!next.size)req[s].idxs.forEach(j=>bad.add(j));}}});
 // A red link contradicts the green requirements when it covers every value still allowed by those
 // requirements on all of its sheets. This catches "must be A=a1" plus "forbid A=a1" and larger sets.
 bonds.forEach((b,i)=>{if(b.when||b.mapping||b.assert||b.polarity!=="forbid")return;const sh=bondSheets(b);if(!sh.length)return;
   const covered=sh.every(s=>req[s]&&req[s].vals.size&&setSubset(req[s].vals,new Set(b.sides[s]||[])));
   if(covered){bad.add(i);sh.forEach(s=>req[s].idxs.forEach(j=>bad.add(j)));}});
 return bad;}
function checkAdd(nb){const k=conflictKey(nb);                       // {ok} | {conflict} | {dup,at}
 for(let i=0;i<bonds.length;i++){const b=bonds[i];if(b.when||b.mapping||b.assert)continue;if(conflictKey(b)!==k)continue;
   if(b.polarity!==nb.polarity)return {conflict:true};return {dup:true,at:i};}
 return {ok:true};}
const bondSheets=b=>Object.keys(b.sides);
function bondNodes(b){const out=[];for(const s of bondSheets(b))for(const v of (b.sides[s]||[]))if(v!=null)out.push([s,v]);return out;}
function bondCombos(b){let n=1;for(const s of bondSheets(b))n*=Math.max(1,(b.sides[s]||[]).length);return n;}
function anyMulti(b){return bondSheets(b).some(s=>(b.sides[s]||[]).length>1);}
function stateSnapshot(){return JSON.stringify({bonds,params,nodeY});}
function pushUndo(){undoStack.push(stateSnapshot());if(undoStack.length>120)undoStack.shift();}
function restoreSnapshot(raw){const st=JSON.parse(raw);restoring=true;bonds=(st.bonds||[]);params=(st.params||{});nodeY=(st.nodeY||{});sel=null;selBond=null;selArm=null;armDraft=null;tray=[];["edlg","adlg"].forEach(id=>{const d=$(id);if(d&&d.open)d.close();});const ap=$("arm-popover");if(ap)ap.classList.remove("show");restoring=false;updateTray();render();}
function undoLast(){if(!undoStack.length){toast(T().nothingUndo);return;}restoreSnapshot(undoStack.pop());toast(T().undo);}
function scheduleSingleClick(fn){clearTimeout(clickTimer);clickTimer=setTimeout(()=>{clickTimer=null;fn();},220);}
function runDoubleClick(fn){clearTimeout(clickTimer);clickTimer=null;fn();}
const SHEETVALS={};SHEETS.forEach(s=>SHEETVALS[s[0]]=s[1]);
function gateSel(g){return g&&g.adjacent?"adjacent":(g&&"within"in g?"within":"any");}
function mkGate(kind,n){return kind==="adjacent"?{adjacent:true}:kind==="within"?{within:+n||2}:{};}
function setSelectOptions(sel,items,cur){sel.innerHTML=items.map(v=>`<option value="${attr(v)}"${v===cur?" selected":""}>${esc(v)}${OPTIONAL.has(v)?" ·opt":""}</option>`).join("");}
function updateQuickCards(){const pol=$("quick-pol").value;$("quick-forbid").classList.toggle("on",pol==="forbid");$("quick-require").classList.toggle("on",pol==="require");}
function renderQuickPreview(){const pol=$("quick-pol").value,s1=$("quick-s1").value,s2=$("quick-s2").value,v1=$("quick-v1").value,v2=$("quick-v2").value,cls=pol==="forbid"?"f":"r",sym=pol==="forbid"?"×":"✓";
 const box=$("quick-preview");if(!box)return;box.innerHTML=`<span class="hint">${esc(T().qPreview)}</span><span class="visual-chip"><b>${esc(s1)}</b>${esc(v1||"")}</span><span class="visual-conn ${cls}" title="${esc(gateWord(readQuickGate()))}"></span><span class="visual-chip"><b>${esc(s2)}</b>${esc(v2||"")}</span><span class="pill ${cls}">${sym}</span>`;}
function renderQuickValues(){const s1=$("quick-s1").value,s2=$("quick-s2").value;setSelectOptions($("quick-v1"),SHEETVALS[s1]||[],($("quick-v1").value||((SHEETVALS[s1]||[])[0])));setSelectOptions($("quick-v2"),SHEETVALS[s2]||[],($("quick-v2").value||((SHEETVALS[s2]||[])[0])));renderQuickPreview();}
function renderQuickBuilder(){const names=SHEETS.map(s=>s[0]);if(!names.length)return;const q1=$("quick-s1"),q2=$("quick-s2");let s1=q1.value||names[0],s2=q2.value||names.find(n=>n!==s1)||names[0];if(s1===s2&&names.length>1)s2=names.find(n=>n!==s1);setSelectOptions(q1,names,s1);setSelectOptions(q2,names,s2);renderQuickValues();updateQuickCards();$("quick-gate").options[0].text=T().gAny;$("quick-gate").options[1].text=T().gAdj;$("quick-gate").options[2].text=T().gWithin;}
function readQuickGate(){return mkGate($("quick-gate").value,$("quick-within").value);}
function setQuickPol(pol){$("quick-pol").value=pol;updateQuickCards();renderQuickPreview();}

// ---- bonds -> sidecar (mirror of editor.py bonds_to_sidecar) ----
function bondsToSidecar(){
 const groups={},setsCons=[],whens=[],mappings=[],asserts=[];
 for(const b of bonds){const sheets=bondSheets(b);const cond=b.condition||null;
  if(b.assert){asserts.push({sheets:[...sheets].sort(),polarity:b.polarity,assert:b.assert,condition:cond});continue;}
  if(b.mapping){mappings.push({sheets:[...sheets].sort(),gate:b.gate||{},polarity:b.polarity,mapping:b.mapping,condition:cond});continue;}
  if(b.when){whens.push({sheets:[...sheets].sort(),gate:b.gate||{},polarity:b.polarity,when:b.when,condition:cond});continue;}
  if(anyMulti(b)){setsCons.push({sheets:[...sheets].sort(),gate:b.gate||{},polarity:b.polarity,condition:cond,
    sets:Object.fromEntries(sheets.map(s=>[s,b.sides[s].slice()]))});continue;}
  const ss=[...new Set(sheets)].sort();const key=JSON.stringify([ss,b.gate||{},b.polarity,cond||{}]);
  (groups[key]=groups[key]||{sheets:ss,gate:b.gate||{},polarity:b.polarity,condition:cond,pairs:[]});
  const e={};sheets.forEach(s=>e[s]=b.sides[s][0]);groups[key].pairs.push(e);}
 const cons=[];let i=0;
 for(const k in groups){const g=groups[k];const c={id:"bond"+(i++)+"_"+g.sheets.join("_"),polarity:g.polarity,
   sheets:g.sheets,pairs:g.pairs,gate:g.gate,desc:g.pairs.length+" "+g.polarity+" "+g.sheets.join("×")+" bond(s)"};
   if(g.condition)c.condition=g.condition;cons.push(c);}
 setsCons.forEach((s,j)=>{const body=s.sheets.map(sh=>sh+"∈{"+s.sets[sh].join(",")+"}").join(" × ");
   const c={id:"mm"+j+"_"+s.sheets.join("_"),polarity:s.polarity,sheets:s.sheets,sets:s.sets,gate:s.gate,desc:s.polarity+" "+body};
   if(s.condition)c.condition=s.condition;cons.push(c);});
 whens.forEach((w,j)=>{const c={id:"when"+j+"_"+w.sheets.join("_"),polarity:w.polarity,sheets:w.sheets,
   when:w.when,gate:w.gate,desc:w.polarity+" "+w.sheets.join("/")+" when "+w.when};
   if(w.condition)c.condition=w.condition;cons.push(c);});
 mappings.forEach((m,j)=>{const c={id:"map"+j+"_"+m.sheets.join("_"),polarity:m.polarity,sheets:m.sheets,
   mapping:m.mapping,gate:m.gate,desc:"mapping "+m.mapping.source+"->"+m.mapping.target};
   if(m.condition)c.condition=m.condition;cons.push(c);});
 asserts.forEach((a,j)=>{const c={id:"assert"+j+"_"+a.sheets.join("_"),polarity:a.polarity,assert:a.assert,
   desc:(a.polarity==="forbid"?"forbid":"require")+": "+describeCond(a.assert)};
   if(a.condition)c.condition=a.condition;cons.push(c);});
 const out={version:1,params:cleanParams(),constraints:cons};
 if(Object.keys(ORDERS||{}).length)out.orders=ORDERS;
 return out;
}
function cleanParams(){const out={};for(const s in params){const vv={};for(const v in params[s]){if(Object.keys(params[s][v]||{}).length)vv[v]=params[s][v];}if(Object.keys(vv).length)out[s]=vv;}return out;}

// ---- plain language ----
function gateWord(g){if(!g||!Object.keys(g).length)return T().pos;if(g.adjacent)return T().adjW;if("within"in g)return T().withinW+" "+g.within;return T().pos;}
function describeCond(c){if(!c)return "";
 if(c.all)return c.all.map(x=>"("+describeCond(x)+")").join(" and ");
 if(c.any)return c.any.map(x=>"("+describeCond(x)+")").join(" or ");
 if(c.not)return "not ("+describeCond(c.not)+")";
 const s=c.sheet;
 if("present"in c)return c.present?`${s} present`:`${s} absent`;
 const SYM={eq:"=",ne:"≠",has:"∋",hasnt:"∌",eqSheet:"=",neSheet:"≠",ge:"≥",gt:">",le:"≤",lt:"<",
   geSheet:"≥",gtSheet:">",leSheet:"≤",ltSheet:"<",subOf:"⊆",supOf:"⊇"};
 for(const k in SYM)if(k in c)return `${s}${SYM[k]}${c[k]}`;
 for(const k of["in","nin","hasAny"])if(k in c)return `${s}${k==="in"?"∈":k==="nin"?"∉":"∩"}{${(c[k]||[]).join(", ")}}`;
 for(const k of["count","countGe","countLe"])if(k in c)return `|${s}|${k==="count"?"=":k==="countGe"?"≥":"≤"}${c[k]}`;
 return JSON.stringify(c);}
function bondText(b){const pol=b.polarity==="forbid"?T().forbidW:T().requireW;
 const cond=b.condition?` <small>only when ${esc(describeCond(b.condition))}</small>`:"";
 if(b.assert){return `<b>${pol}</b> ${esc(describeCond(b.assert))}${cond}`;}
 if(b.mapping){return `<b>mapping</b> ${esc(b.mapping.source)} → ${esc(b.mapping.target)}${cond}`;}
 if(b.when){return `<b>${esc(bondSheets(b).join(" · "))}</b> — ${esc(b.when)}${cond}`;}
 const mm=anyMulti(b);
 const parts=bondSheets(b).map(s=>{const vs=b.sides[s];return vs.length===1?`${esc(s)}:${esc(vs[0])}`:`${esc(s)}∈{${vs.map(esc).join(", ")}}`;});
 const cnt=mm?` <small>= ${bondCombos(b)} ${T().combosW}</small>`:"";
 return `<b>${pol}</b> ${parts.join(mm?" × ":" + ")}${cnt} <small>(${gateWord(b.gate)})</small>${cond}`;}

function shorten(vals,n=3){return vals.length<=n?vals.join(", "):vals.slice(0,n).join(", ")+" …";}
function plainBondText(b){if(!b)return "";const pol=b.polarity==="forbid"?T().forbidW:T().requireW;
 if(b.assert)return `${pol}: ${describeCond(b.assert)}`;
 if(b.mapping)return `mapping ${b.mapping.source} → ${b.mapping.target}`;
 if(b.when)return `${pol}: ${bondSheets(b).join(" · ")} when ${b.when}`;
 const parts=bondSheets(b).map(s=>{const vs=b.sides[s]||[];return vs.length===1?`${s}:${vs[0]}`:`${s}∈{${shorten(vs)}}`;});
 return `${pol}: ${parts.join(anyMulti(b)?" × ":" + ")}`;}


// ---- safe-ish when eval for preview only ----
const BAN=/__|import|lambda|:=|=>|;|\bexec\b|\beval\b|\bopen\b|\bglobals\b|\blocals\b|\bwhile\b|\bfor\b/;
const SAFE_FUNCS={abs:Math.abs,min:Math.min,max:Math.max,round:Math.round,len:x=>(x&&x.length)||0,
  int:x=>parseInt(x,10),float:x=>parseFloat(x),bool:x=>!!x,True:true,False:false,None:null};
function evalWhen(expr,ns){try{if(BAN.test(expr))return null;          // preview-only; sieve is the source of truth
  const js=expr.replace(/\band\b/g,"&&").replace(/\bor\b/g,"||").replace(/\bnot\b/g,"!");
  const scope=Object.assign({},SAFE_FUNCS,ns);const keys=Object.keys(scope);
  return !!Function(...keys,'"use strict";return ('+js+');')(...keys.map(k=>scope[k]));}catch(e){return null;}}
// rank a value for ordinal leaves (mirror of sieve._rank): list->index, "numeric"->float, "date"->ISO
function rank(sheet,value){const spec=ORDERS[sheet];
 if(spec==null)throw new Error("no order for "+sheet);
 if(Array.isArray(spec)){const i=spec.indexOf(value);if(i<0)throw new Error("value not in order");return i;}
 if(spec==="numeric"){const f=parseFloat(value);if(isNaN(f))throw new Error("not numeric");return f;}
 if(spec==="date"){const t=Date.parse(value);if(isNaN(t))throw new Error("not a date");return t;}
 throw new Error("bad order spec");}
function ranks(sheet,vals){return vals.map(v=>rank(sheet,v));}
function evalCondition(c,sel){
 if(!c||!Object.keys(c).length)return true;
 if(c.all)return c.all.every(x=>evalCondition(x,sel));
 if(c.any)return c.any.some(x=>evalCondition(x,sel));
 if(c.not)return !evalCondition(c.not,sel);
 const vals=sel[c.sheet]||[],set=new Set(vals);
 if("present" in c)return (vals.length>0)===!!c.present;
 if("eq" in c)return vals.length===1&&vals[0]===c.eq;
 if("ne" in c)return !(vals.length===1&&vals[0]===c.ne);
 if("has" in c)return set.has(c.has);
 if("hasnt" in c)return !set.has(c.hasnt);
 if("in" in c)return vals.every(v=>(c.in||[]).includes(v));
 if("nin" in c)return vals.every(v=>!(c.nin||[]).includes(v));
 if("hasAny" in c)return (c.hasAny||[]).some(v=>set.has(v));
 if("eqSheet" in c){const other=new Set(sel[c.eqSheet]||[]);return set.size===other.size&&[...set].every(v=>other.has(v));}
 if("neSheet" in c){const other=new Set(sel[c.neSheet]||[]);return !(set.size===other.size&&[...set].every(v=>other.has(v)));}
 if("subOf" in c){const other=new Set(sel[c.subOf]||[]);return [...set].every(v=>other.has(v));}
 if("supOf" in c){const other=new Set(sel[c.supOf]||[]);return [...other].every(v=>set.has(v));}
 for(const k of["ge","gt","le","lt"])if(k in c){if(!vals.length)return true;
   const cc=rank(c.sheet,c[k]),rs=ranks(c.sheet,vals);
   return k==="ge"?Math.min(...rs)>=cc:k==="gt"?Math.min(...rs)>cc:k==="le"?Math.max(...rs)<=cc:Math.max(...rs)<cc;}
 for(const k of["geSheet","gtSheet","leSheet","ltSheet"])if(k in c){const tv=sel[c[k]]||[];
   if(!vals.length||!tv.length)return true;const ls=ranks(c.sheet,vals),rr=ranks(c[k],tv);
   return k==="geSheet"?Math.min(...ls)>=Math.max(...rr):k==="gtSheet"?Math.min(...ls)>Math.max(...rr)
     :k==="leSheet"?Math.max(...ls)<=Math.min(...rr):Math.max(...ls)<Math.min(...rr);}
 if("count" in c)return vals.length===+c.count;
 if("countGe" in c)return vals.length>=+c.countGe;
 if("countLe" in c)return vals.length<=+c.countLe;
 return true;
}
function mappingViolated(m,sel){const tvals=new Set(sel[m.target]||[]),allow=m.allow||{};
 for(const sv of (sel[m.source]||[])){if(sv in allow){for(const tv of tvals){if(!allow[sv].includes(tv))return true;}}}
 return false;}



// ---- live impact over the sheets' cartesian (co-occurrence preview) ----
function fmtNum(n){if(!isFinite(n))return String(n);return Math.round(n).toLocaleString(lang==="ru"?"ru-RU":"en-US");}
function hash32(s){let h=2166136261>>>0;for(let i=0;i<s.length;i++){h^=s.charCodeAt(i);h=Math.imul(h,16777619);}return h>>>0;}
function rng32(seed){let a=seed>>>0;return ()=>{a+=0x6D2B79F5;let t=a;t=Math.imul(t^t>>>15,t|1);t^=t+Math.imul(t^t>>>7,t|61);return ((t^t>>>14)>>>0)/4294967296;};}
function comboFromIndexes(idx){const combo={};SHEETS.forEach((s,i)=>{if(OPTIONAL.has(s[0])){if(idx[i]>0)combo[s[0]]=s[1][idx[i]-1];}else combo[s[0]]=s[1][idx[i]];});return combo;}
function impact(){
 const sizes=SHEETS.map(s=>OPTIONAL.has(s[0])?s[1].length+1:s[1].length),prod=sizes.reduce((a,b)=>a*b,1);
 if(!prod)return {exact:false,full:prod,removed:0,kept:0,sampled:0};
 if(prod<=50000){let removed=0;const idx=SHEETS.map(()=>0);
   for(let n=0;n<prod;n++){if(rowViolated(comboFromIndexes(idx)))removed++;
     for(let i=SHEETS.length-1;i>=0;i--){if(++idx[i]<sizes[i])break;idx[i]=0;}}
   return {exact:true,removed,full:prod,kept:prod-removed};}
 const sample=Math.min(20000,Math.max(3000,Math.ceil(800*Math.sqrt(SHEETS.length||1))));
 const rnd=rng32(hash32(JSON.stringify(bondsToSidecar()))^hash32(String(prod)));let removed=0;
 for(let n=0;n<sample;n++){const idx=sizes.map(sz=>Math.floor(rnd()*sz));if(rowViolated(comboFromIndexes(idx)))removed++;}
 const estRemoved=Math.round((removed/sample)*prod);return {exact:false,full:prod,removed:estRemoved,kept:Math.max(0,prod-estRemoved),sampled:sample};
}
function gateOkMulti(g,P){if(!g||!Object.keys(g).length)return true;const span=Math.max(...P)-Math.min(...P);
 if(g.adjacent)return span===P.length-1;if("within"in g)return span<=+g.within;return true;}
function rowViolated(combo){            // combo: {sheet:value}; optional absent sheets are omitted
 const sel={};Object.keys(combo).forEach(s=>sel[s]=[combo[s]]);
 for(const b of bonds){const sheets=bondSheets(b);
   try{if(b.condition&&!evalCondition(b.condition,sel))continue;}catch(e){continue;}
   if(b.assert){let holds;try{holds=evalCondition(b.assert,sel);}catch(e){continue;}   // preview-only
     const forbid=b.polarity==="forbid";if((forbid&&holds)||(!forbid&&!holds))return true;continue;}
   if(b.mapping){if(mappingViolated(b.mapping,sel))return true;continue;}
   if(sheets.some(s=>!(s in combo)))continue;
   const P=sheets.map(s=>SI[s]);if(!gateOkMulti(b.gate,P))continue;
   let holds;
   if(b.when){const ns={};sheets.forEach(s=>{const v=combo[s];ns[s]=Object.assign({value:v,pos:SI[s]},(params[s]||{})[v]||{});});
     const r=evalWhen(b.when,ns);if(r===null)continue;holds=r;}
   else{holds=sheets.every(s=>b.sides[s].includes(combo[s]));}   // cross product membership
   const forbid=b.polarity==="forbid";
   if((forbid&&holds)||(!forbid&&!holds))return true;}
 return false;
}


// ---- render ----  (build = full DOM; edgesInner/layoutDrag = cheap re-layout while a node is dragged)
function render(){conflictBonds=findConflicts();renderCanvas();renderPanel();}
function sameArm(a,bi,sh,v){return !!a&&a.bi===bi&&a.s===sh&&a.v===v;}
function edgesInner(){let s="";
 bonds.forEach((b,bi)=>{if(b.when||b.mapping||b.assert)return;const pts=bondNodes(b).map(([sh,v])=>{const p=nodeXY(sh,v);return p?Object.assign({sh,v},p):null;}).filter(Boolean);
   if(pts.length<2)return;const cls=b.polarity==="forbid"?"f":"r";
   const bad=conflictBonds.has(bi)?" bad":"";const hot=(bi===selBond)?" hot":(selBond!==null?" dim":"");
   if(pts.length===2){s+=`<line class="edge ${cls}${hot}${bad}" data-bi="${bi}" x1="${pts[0].x}" y1="${pts[0].y}" x2="${pts[1].x}" y2="${pts[1].y}"></line>`;}
   else{const cx=pts.reduce((a,p)=>a+p.x,0)/pts.length,cy=pts.reduce((a,p)=>a+p.y,0)/pts.length;   // hub = n-ary tuple OR Many:Many cross product
     pts.forEach(p=>{const ah=sameArm(selArm,bi,p.sh,p.v)?" arm-hot":"";const mx=(p.x+cx)/2,my=(p.y+cy)/2;
       s+=`<line class="edge armseg ${cls}${hot}${bad}${ah}" data-bi="${bi}" data-s="${attr(p.sh)}" data-v="${attr(p.v)}" x1="${p.x}" y1="${p.y}" x2="${cx}" y2="${cy}"></line>`;
       s+=`<circle class="armctl${ah}" data-bi="${bi}" data-s="${attr(p.sh)}" data-v="${attr(p.v)}" cx="${mx}" cy="${my}" r="6"><title>${esc(T().armEdit)}: ${esc(p.sh)}=${esc(p.v)}</title></circle>`;});
     s+=`<rect class="hub" data-bi="${bi}" x="${cx-7}" y="${cy-7}" width="14" height="14" transform="rotate(45 ${cx} ${cy})" fill="var(--${b.polarity==='forbid'?'forbid':'require'})"></rect>`;}
 });
 return s;}
function bindEdges(cv){cv.querySelectorAll("#edges .armctl,#edges .armseg").forEach(el=>{
  el.onclick=e=>{e.preventDefault();e.stopPropagation();if(suppressClick){suppressClick=false;return;}
    const bi=+el.dataset.bi,sh=el.dataset.s,v=el.dataset.v;
    if(e.detail>=2){runDoubleClick(()=>openArmDialog(bi,sh,v,e));return;}
    scheduleSingleClick(()=>{selBond=bi;selArm={bi,s:sh,v};sel=null;render();});};
  el.ondblclick=e=>{e.preventDefault();e.stopPropagation();runDoubleClick(()=>openArmDialog(+el.dataset.bi,el.dataset.s,el.dataset.v,e));};
 });
 cv.querySelectorAll("#edges [data-bi]:not(.armctl):not(.armseg)").forEach(el=>{
  el.onclick=e=>{if(suppressClick){suppressClick=false;return;}const bi=+el.dataset.bi;
    if(e.detail>=2){runDoubleClick(()=>openBondDialog(bi));return;}
    scheduleSingleClick(()=>{selBond=bi;selArm=null;sel=null;render();if(canExtendBond(bonds[selBond]))toast(T().extendPick);});};
  el.ondblclick=e=>{e.preventDefault();e.stopPropagation();runDoubleClick(()=>openBondDialog(+el.dataset.bi));};
 });}
function renderCanvas(){
 const cv=$("canvas");
 if(!SHEETS.length){cv.innerHTML="<div class='empty' style='padding:40px'>"+T().emptyStage+"</div>";return;}
 const rows=Math.max(...SHEETS.map(s=>s[1].length),1);
 const W=PADX+(SHEETS.length-1)*COLW+PADX, H=Math.max(stageH(),PADY+rows*ROWH+24);
 let html=`<svg id="edges" width="${W}" height="${H}">`+edgesInner()+`</svg>`;
 SHEETS.forEach((s,si)=>{const opt=OPTIONAL.has(s[0]);html+=`<div class="col-h" style="left:${pos(si,0).x}px">${esc(s[0])}${opt?`<span class="opt-badge">${esc(T().optionalW)}</span>`:""}</div>`;
   s[1].forEach((v,vi)=>{const id=nid(s[0],v);const p=nodeXY(s[0],v);
     const c=(sel===id?" sel":"")+(tray.includes(id)?" tray":"");
     html+=`<div class="node${c}" tabindex="0" role="button" data-id='${attr(id)}' style="left:${p.x}px;top:${p.y}px" title="${attr(s[0])}: ${attr(v)}">${esc(v)}${nodeDots(id)}</div>`;});});
 cv.style.width=W+"px";cv.style.height=H+"px";cv.innerHTML=html;
 cv.querySelectorAll(".node").forEach(n=>{
   n.onpointerdown=e=>startNodeDrag(e,n);
   n.onclick=()=>{if(suppressClick){suppressClick=false;return;}clickNode(n.dataset.id);};
   n.onkeydown=e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();clickNode(n.dataset.id);}};
   n.onmouseenter=()=>{hoverNode=n.dataset.id;updateInspect();};            // hover a value → describe its bonds + spotlight its lines
   n.onmouseleave=()=>{if(hoverNode===n.dataset.id){hoverNode=null;updateInspect();}};
   n.onfocus=()=>{hoverNode=n.dataset.id;updateInspect();};                  // keyboard focus = same (a11y)
   n.onblur=()=>{if(hoverNode===n.dataset.id){hoverNode=null;updateInspect();}};});
 bindEdges(cv);
 spotlight();                                                               // persistent spotlight for the draw-start / selected node
 applyView();
}
// ---- visual "only when" builder: dropdown terms <-> the sieve's `condition` AST (the sub-list whose
// values come from another column). Simple shapes (one leaf, or all/any of leaves) edit visually;
// anything nested falls back to the JSON field. ----
const COND_OPS=[{k:"eq",t:"opIs"},{k:"ne",t:"opIsNot"},{k:"present",t:"opPresent"},{k:"has",t:"opHas"},
  {k:"in",t:"opIn"},{k:"nin",t:"opNin"},{k:"countGe",t:"opGe"},{k:"countLe",t:"opLe"},
  {k:"ge",t:"opGeC"},{k:"le",t:"opLeC"},{k:"gt",t:"opGtC"},{k:"lt",t:"opLtC"},
  {k:"eqSheet",t:"opEqS"},{k:"geSheet",t:"opGeS"},{k:"leSheet",t:"opLeS"},{k:"subOf",t:"opSub"},{k:"supOf",t:"opSup"}];
const COND_OP_KEYS=COND_OPS.map(o=>o.k);
const COND_MULTI=new Set(["in","nin"]),COND_COUNT=new Set(["countGe","countLe"]);
const COND_XCOL=new Set(["eqSheet","neSheet","geSheet","gtSheet","leSheet","ltSheet","subOf","supOf"]);  // value names a sheet
const COND_ORD=new Set(["ge","gt","le","lt"]);          // ordinal vs a constant (single value from the sheet)
const COND_PRESENT=new Set(["present"]);
function leafToTerm(l){if(!l||typeof l!=="object"||l.sheet==null)return null;for(const o of COND_OP_KEYS)if(o in l)return {sheet:l.sheet,op:o,val:l[o]};return null;}
function termToLeaf(t){if(!t||t.sheet==null)return null;const l={sheet:t.sheet};l[t.op]=t.val;return l;}
function condToTerms(cond){if(!cond)return {join:"all",terms:[]};
  if(cond.all||cond.any){const join=cond.all?"all":"any",arr=cond.all||cond.any,terms=arr.map(leafToTerm);return terms.some(t=>!t)?null:{join,terms};}
  if(cond.not)return null;const t=leafToTerm(cond);return t?{join:"all",terms:[t]}:null;}
function termsToCond(join,terms){const leaves=terms.map(termToLeaf).filter(Boolean);
  if(!leaves.length)return null;if(leaves.length===1)return leaves[0];const c={};c[join]=leaves;return c;}
function defaultVal(sheet,op){if(COND_COUNT.has(op))return 1;
  if(COND_PRESENT.has(op))return true;
  if(COND_XCOL.has(op))return (SHEETS.find(s=>s[0]!==sheet)||SHEETS[0]||[""])[0];
  const vs=SHEETVALS[sheet]||[];return COND_MULTI.has(op)?(vs.length?[vs[0]]:[]):(vs[0]||"");}
function condSubject(b){return b&&b._assertTarget?b._assertTarget.assert:b.condition;}
function setCondSubject(b,c){if(b&&b._assertTarget)b._assertTarget.assert=c;else b.condition=c;}
function setCondTerms(b,fn){const tt=condToTerms(condSubject(b))||{join:"all",terms:[]};if(!(b&&b._dialog==="relation"))pushUndo();fn(tt);setCondSubject(b,termsToCond(tt.join,tt.terms));if(b._dialog==="relation")renderRelationBuilder();else render();}
function condValControl(t,ti){
  if(COND_PRESENT.has(t.op))return `<select class="ct-val ct-bool" data-i="${ti}"><option value="true"${t.val?" selected":""}>${esc(T().opYes)}</option><option value="false"${t.val?"":" selected"}>${esc(T().opNo)}</option></select>`;
  if(COND_COUNT.has(t.op))return `<input class="ct-val" data-i="${ti}" type="number" min="0" value="${attr(t.val||0)}" style="width:58px">`;
  if(COND_XCOL.has(t.op))return `<select class="ct-val" data-i="${ti}">`+SHEETS.filter(s=>s[0]!==t.sheet).map(s=>`<option value="${attr(s[0])}"${s[0]===t.val?" selected":""}>${esc(s[0])}</option>`).join("")+`</select>`;
  const all=SHEETVALS[t.sheet]||[];
  if(COND_MULTI.has(t.op)){const cur=Array.isArray(t.val)?t.val:[],uns=all.filter(v=>!cur.includes(v));
    return `<span class="ct-multi le-chips" data-i="${ti}">`+cur.map(v=>`<span class="chip">${esc(v)}${cur.length>1?`<button class="ct-rm" data-i="${ti}" data-v="${attr(v)}">✕</button>`:""}</span>`).join("")
      +(uns.length?`<select class="ct-addv" data-i="${ti}"><option value="">＋</option>${uns.map(v=>`<option value="${attr(v)}">${esc(v)}</option>`).join("")}</select>`:"")+`</span>`;}
  return `<select class="ct-val" data-i="${ti}">`+all.map(v=>`<option value="${attr(v)}"${v===t.val?" selected":""}>${esc(v)}</option>`).join("")+`</select>`;}
function condTermRow(t,ti){const x=T();
  const sh=`<select class="ct-sheet" data-i="${ti}">`+SHEETS.map(s=>`<option value="${attr(s[0])}"${s[0]===t.sheet?" selected":""}>${esc(s[0])}${OPTIONAL.has(s[0])?" ·opt":""}</option>`).join("")+`</select>`;
  const op=`<select class="ct-op" data-i="${ti}">`+COND_OPS.map(o=>`<option value="${o.k}"${o.k===t.op?" selected":""}>${esc(x[o.t])}</option>`).join("")+`</select>`;
  return `<div class="le-row ct-row">${sh}${op}${condValControl(t,ti)}<button class="x ct-del" data-i="${ti}">✕</button></div>`;}
function condBuilderHTML(b){const x=T(),tt=condToTerms(condSubject(b));
  if(!tt)return `<div class="hint">${esc(x.condAdv)}</div>`;
  let h=`<div class="cond-build">`;
  if(tt.terms.length>=2)h+=`<div class="le-row"><span class="le-lbl">${esc(x.combine)}</span><span class="seg sm">`
    +`<button class="cj${tt.join==="all"?" on":""}" data-cj="all">${esc(x.cAll)}</button>`
    +`<button class="cj${tt.join==="any"?" on":""}" data-cj="any">${esc(x.cAny)}</button></span></div>`;
  h+=tt.terms.map((t,ti)=>condTermRow(t,ti)).join("");
  return h+`<div class="le-row"><button class="btn sm le-add-cond">${esc(x.addCond)}</button></div></div>`;}
function bindCondBuilder(box,b){
  box.querySelectorAll(".cj").forEach(btn=>btn.onclick=()=>setCondTerms(b,tt=>tt.join=btn.dataset.cj));
  const add=box.querySelector(".le-add-cond");if(add)add.onclick=()=>setCondTerms(b,tt=>{const s=SHEETS[0][0];tt.terms.push({sheet:s,op:"eq",val:defaultVal(s,"eq")});});
  box.querySelectorAll(".ct-del").forEach(btn=>btn.onclick=()=>setCondTerms(b,tt=>tt.terms.splice(+btn.dataset.i,1)));
  box.querySelectorAll(".ct-sheet").forEach(se=>se.onchange=()=>setCondTerms(b,tt=>{const t=tt.terms[+se.dataset.i];t.sheet=se.value;t.val=defaultVal(t.sheet,t.op);}));
  box.querySelectorAll(".ct-op").forEach(se=>se.onchange=()=>setCondTerms(b,tt=>{const t=tt.terms[+se.dataset.i];t.op=se.value;t.val=defaultVal(t.sheet,t.op);}));
  box.querySelectorAll("select.ct-val").forEach(se=>se.onchange=()=>setCondTerms(b,tt=>{const t=tt.terms[+se.dataset.i];t.val=se.classList.contains("ct-bool")?(se.value==="true"):se.value;}));
  box.querySelectorAll("input.ct-val").forEach(inp=>inp.onchange=()=>setCondTerms(b,tt=>{tt.terms[+inp.dataset.i].val=+inp.value||0;}));
  box.querySelectorAll(".ct-addv").forEach(se=>se.onchange=()=>{if(se.value)setCondTerms(b,tt=>{const t=tt.terms[+se.dataset.i];t.val=[...(t.val||[]),se.value];});});
  box.querySelectorAll(".ct-rm").forEach(btn=>btn.onclick=()=>setCondTerms(b,tt=>{const t=tt.terms[+btn.dataset.i];t.val=(t.val||[]).filter(v=>v!==btn.dataset.v);}));}
function conditionSheets(c){const out=[];const add=s=>{if(s&&!out.includes(s))out.push(s);};
 if(!c)return out;if(c.all)c.all.forEach(x=>conditionSheets(x).forEach(add));if(c.any)c.any.forEach(x=>conditionSheets(x).forEach(add));if(c.not)conditionSheets(c.not).forEach(add);
 add(c.sheet);["eqSheet","neSheet","geSheet","gtSheet","leSheet","ltSheet","subOf","supOf"].forEach(k=>{if(k in c)add(c[k]);});return out;}
let relDraft={_dialog:"relation",condition:null};
function opIcon(op){return {eq:"=",ne:"≠",present:"?",has:"∋",in:"∈",nin:"∉",countGe:"#≥",countLe:"#≤",ge:"≥",le:"≤",gt:">",lt:"<",eqSheet:"=",geSheet:"≥",leSheet:"≤",subOf:"⊆",supOf:"⊇"}[op]||op;}
function condVisual(c){if(!c)return `<span class="hint">${esc(T().rNeed)}</span>`;if(c.all||c.any){const arr=c.all||c.any,j=c.all?T().cAll:T().cAny;return arr.map(condVisual).join(`<span class="logic-pill">${esc(j)}</span>`);}if(c.not)return `<span class="logic-pill">not</span>`+condVisual(c.not);const t=leafToTerm(c);if(!t)return `<span class="rule-token">${esc(describeCond(c))}</span>`;const val=Array.isArray(t.val)?t.val.join(", "):String(t.val);return `<span class="rule-token"><b>${esc(t.sheet)}</b></span><span class="rule-op">${esc(opIcon(t.op))}</span><span class="rule-token">${esc(val)}</span>`;}
function updateRelationCards(){const pol=$("r-pol").value;$("r-require").classList.toggle("on",pol==="require");$("r-forbid").classList.toggle("on",pol==="forbid");}
function renderRelationBuilder(){updateRelationCards();const box=$("r-builder");box.innerHTML=condBuilderHTML(relDraft);bindCondBuilder(box,relDraft);$("r-preview").innerHTML=`<span class="pill ${$("r-pol").value==="forbid"?"f":"r"}">${esc($("r-pol").value==="forbid"?T().forbidW:T().requireW)}</span>`+condVisual(relDraft.condition);$("r-json").value=relDraft.condition?JSON.stringify(relDraft.condition):"";}
function openRelation(){if(!SHEETS.length){toast(lang==="ru"?"Нет листов":"No sheets");return;}const s=SHEETS[0][0];relDraft={_dialog:"relation",condition:{sheet:s,present:true}};$("r-pol").value=mode==="forbid"?"forbid":"require";$("rhint").textContent="";renderRelationBuilder();$("rdlg").showModal();}

// per-link condition editor: polarity, gate (any/adjacent/within N), the `when` formula, and the
// member value sets of the SELECTED link — edits bonds[selBond] in place, live impact recomputes.
function renderLinkEditor(){
 const dialogOpen=$("edlg")&&$("edlg").open,box=dialogOpen?$("edlg-body"):$("linkedit");
 if(dialogOpen)$("linkedit").innerHTML="";
 renderBondEditor(box,dialogOpen);
}
function renderBondEditor(box,inDialog){
 if(selBond===null||!bonds[selBond]){box.innerHTML="";if(inDialog&&$("edlg").open)$("edlg").close();return;}
 const b=bonds[selBond],x=T(),gk=gateSel(b.gate);
 let h=`<div class="le-head"><b>${x.editLink}</b><button class="x" id="le-x" title="${esc(x.deselect)}">✕</button></div>`;
 h+=`<div class="le-txt">${bondText(b)}</div>`;
 h+=`<div class="le-row"><span class="le-lbl">${esc(x.pol)}</span><span class="seg sm">`
   +`<button id="le-forbid" class="${b.polarity==='forbid'?'on':''}" data-pol="forbid"><span class="dot f"></span>${esc(x.forbidW)}</button>`
   +`<button id="le-require" class="${b.polarity==='require'?'on':''}" data-pol="require"><span class="dot r"></span>${esc(x.requireW)}</button></span></div>`;
 h+=`<div class="le-row"><span class="le-lbl">${esc(x.gate)}</span>`
   +`<select id="le-gate"><option value="any"${gk==='any'?' selected':''}>${esc(x.gAny)}</option>`
   +`<option value="adjacent"${gk==='adjacent'?' selected':''}>${esc(x.gAdj)}</option>`
   +`<option value="within"${gk==='within'?' selected':''}>${esc(x.gWithin)}…</option></select>`
   +`<input id="le-num" type="number" min="1" value="${(b.gate&&b.gate.within)||2}" style="width:54px;display:${gk==='within'?'':'none'}"></div>`;
 h+=`<div class="le-row"><span class="le-lbl">${esc(x.onlyWhen)}</span></div>`;
 h+=`<div id="le-cond-builder">${condBuilderHTML(b)}</div>`;
 h+=`<details class="le-cond-json"${condToTerms(b.condition)?"":" open"}><summary class="hint">JSON</summary><div class="le-row">`
   +`<input id="le-cond" type="text" value="${attr(b.condition?JSON.stringify(b.condition):'')}" placeholder='{"sheet":"DatasetFamily","eq":"Mobility"}' style="flex:1;min-width:120px">`
   +`<button class="btn" id="le-cond-apply">${esc(x.apply)}</button></div><div class="hint" id="le-condhint"></div></details>`;
 if(b.assert){
   const proxy={_assertTarget:b};
   h+=`<div class="le-row"><span class="le-lbl">${esc(x.rBody)}</span></div><div class="rule-preview">${condVisual(b.assert)}</div><div id="le-assert-builder">${condBuilderHTML(proxy)}</div>`;
   h+=`<details class="le-cond-json json-fallback"><summary class="hint">${esc(x.rJson)}</summary><div class="le-row"><input id="le-assert" type="text" value="${attr(JSON.stringify(b.assert))}" style="flex:1;min-width:120px"><button class="btn" id="le-assert-apply">${esc(x.apply)}</button></div><div class="hint" id="le-asserthint"></div></details>`;
 }else if(b.mapping){
   h+=`<details class="le-cond-json json-fallback" open><summary class="hint">mapping JSON</summary><div class="le-row"><input id="le-map" type="text" value="${attr(JSON.stringify(b.mapping))}" style="flex:1;min-width:120px"><button class="btn" id="le-map-apply">${esc(x.apply)}</button></div><div class="hint" id="le-maphint"></div></details>`;
 }else if(b.when!=null){
   h+=`<div class="le-row"><span class="le-lbl">${esc(x.formulaLbl)}</span>`
     +`<input id="le-when" type="text" value="${attr(b.when)}" style="flex:1;min-width:120px">`
     +`<button class="btn" id="le-apply">${esc(x.apply)}</button></div><div class="hint" id="le-whenhint"></div>`;
 }else{
   const members=bondNodes(b);
   if(members.length>2)h+=`<div class="le-row"><span class="le-lbl">${esc(x.armBranches)}</span></div><div class="arm-list">`
     +members.map(([sh,v])=>`<div class="arm-row ${sameArm(selArm,selBond,sh,v)?'sel':''}" data-arm-s="${attr(sh)}" data-arm-v="${attr(v)}"><span class="txt">${esc(sh)}: ${esc(v)}</span><button class="btn sm arm-edit" data-s="${attr(sh)}" data-v="${attr(v)}">↔</button><button class="x arm-del" data-s="${attr(sh)}" data-v="${attr(v)}">✕</button></div>`).join("")+`</div>`;
   h+=`<div>`;
   bondSheets(b).forEach(s=>{const sel=b.sides[s]||[],unsel=(SHEETVALS[s]||[]).filter(v=>!sel.includes(v));
     h+=`<div class="le-row"><span class="le-lbl">${esc(s)}</span><span class="le-chips">`
       +sel.map(v=>`<span class="chip">${esc(v)}${(bondNodes(b).length>2||sel.length>1)?`<button class="chx" data-s="${attr(s)}" data-v="${attr(v)}">✕</button>`:''}</span>`).join("")
       +`</span>`
       +(unsel.length?`<select class="le-add" data-s="${attr(s)}"><option value="">＋ ${esc(x.addVal)}</option>${unsel.map(v=>`<option value="${attr(v)}">${esc(v)}</option>`).join("")}</select>`:'')
       +`</div>`;});
   h+=`</div>`;
 }
 box.innerHTML=h;
 bindLinkEditorControls(box,b,inDialog);
}
function inBox(box,id){return box.querySelector("#"+id);}
function bindLinkEditorControls(box,b,inDialog){
 const x=T(),closeEditor=()=>{selBond=null;if(inDialog&&$("edlg").open)$("edlg").close();render();};
 const leX=inBox(box,"le-x");if(leX)leX.onclick=closeEditor;
 const leForbid=inBox(box,"le-forbid");if(leForbid)leForbid.onclick=()=>{pushUndo();b.polarity="forbid";render();};
 const leRequire=inBox(box,"le-require");if(leRequire)leRequire.onclick=()=>{pushUndo();b.polarity="require";render();};
 const leGate=inBox(box,"le-gate"),leNum=inBox(box,"le-num");
 if(leGate)leGate.onchange=e=>{pushUndo();b.gate=mkGate(e.target.value,leNum?leNum.value:2);render();};
 if(leNum)leNum.onchange=e=>{if(gateSel(b.gate)==="within"){pushUndo();b.gate={within:+e.target.value||2};render();}};
 const leCond=inBox(box,"le-cond"),leCondApply=inBox(box,"le-cond-apply"),leCondHint=inBox(box,"le-condhint");
 const applyCond=()=>{const raw=leCond.value.trim();pushUndo();if(!raw){b.condition=null;render();return;}
   try{const parsed=JSON.parse(raw);b.condition=parsed;render();}catch(e){undoStack.pop();if(leCondHint)leCondHint.textContent="bad JSON";}};
 if(leCondApply&&leCond){leCondApply.onclick=applyCond;leCond.onkeydown=e=>{if(e.key==="Enter")applyCond();};}
 const cb=inBox(box,"le-cond-builder");if(cb)bindCondBuilder(cb,b);
 const ab=inBox(box,"le-assert-builder");if(ab)bindCondBuilder(ab,{_assertTarget:b});
 if(b.assert){const leAssert=inBox(box,"le-assert"),leAssertApply=inBox(box,"le-assert-apply"),leAssertHint=inBox(box,"le-asserthint");
   const applyA=()=>{pushUndo();try{b.assert=JSON.parse(leAssert.value);render();}catch(e){undoStack.pop();if(leAssertHint)leAssertHint.textContent="bad JSON";}};
   if(leAssertApply&&leAssert){leAssertApply.onclick=applyA;leAssert.onkeydown=e=>{if(e.key==="Enter")applyA();};}}
 if(b.mapping){const leMap=inBox(box,"le-map"),leMapApply=inBox(box,"le-map-apply"),leMapHint=inBox(box,"le-maphint");
   const applyM=()=>{pushUndo();try{b.mapping=JSON.parse(leMap.value);render();}catch(e){undoStack.pop();if(leMapHint)leMapHint.textContent="bad JSON";}};
   if(leMapApply&&leMap){leMapApply.onclick=applyM;leMap.onkeydown=e=>{if(e.key==="Enter")applyM();};}}
 if(b.when!=null){const leWhen=inBox(box,"le-when"),leApply=inBox(box,"le-apply"),leWhenHint=inBox(box,"le-whenhint");
   const apply=()=>{const v=leWhen.value.trim();if(!v||BAN.test(v)){if(leWhenHint)leWhenHint.textContent=x.badFormula;return;}pushUndo();b.when=v;render();};
   if(leApply&&leWhen){leApply.onclick=apply;leWhen.onkeydown=e=>{if(e.key==="Enter")apply();};}}
 box.querySelectorAll(".chx").forEach(btn=>btn.onclick=()=>removeBondValue(selBond,btn.dataset.s,btn.dataset.v));
 box.querySelectorAll(".le-add").forEach(se=>se.onchange=()=>{if(se.value){pushUndo();b.sides[se.dataset.s].push(se.value);selArm={bi:selBond,s:se.dataset.s,v:se.value};render();}});
 box.querySelectorAll(".arm-edit").forEach(btn=>btn.onclick=()=>openArmDialog(selBond,btn.dataset.s,btn.dataset.v));
 box.querySelectorAll(".arm-del").forEach(btn=>btn.onclick=()=>removeBondValue(selBond,btn.dataset.s,btn.dataset.v));
}
function openBondDialog(i){if(!bonds[i])return;selBond=i;selArm=null;sel=null;if(!$("edlg").open)$("edlg").showModal();render();}
function closeBondDialog(){$("edlg").close();}
function armValid(i,sh,v){return bonds[i]&&canExtendBond(bonds[i])&&(bonds[i].sides[sh]||[]).includes(v);}
function armWorldPoint(i,sh,v){const b=bonds[i],p=nodeXY(sh,v);if(!b||!p)return null;const pts=bondNodes(b).map(([s,val])=>nodeXY(s,val)).filter(Boolean);if(pts.length<3)return p;const cx=pts.reduce((a,q)=>a+q.x,0)/pts.length,cy=pts.reduce((a,q)=>a+q.y,0)/pts.length;return {x:(p.x+cx)/2,y:(p.y+cy)/2};}
function placeArmPane(pt){const pane=$("arm-popover"),wrap=$("stagewrap").getBoundingClientRect();if(!pane||!pt)return;
 const w=pane.offsetWidth||320;const x=Math.max(12+w/2,Math.min(wrap.width-12-w/2,pt.x));const y=Math.max(82,Math.min(wrap.height-12,pt.y));
 pane.style.left=x+"px";pane.style.top=y+"px";}
function closeArmPane(clearSel=true){armDraft=null;const pane=$("arm-popover");if(pane)pane.classList.remove("show");if(clearSel){selArm=null;render();}}
function discardArmPane(){closeArmPane(true);}
function openArmDialog(i,sh,v,e){openArmPane(i,sh,v,e);}   // public name kept for existing handlers/tests
function openArmPane(i,sh,v,e){if(!armValid(i,sh,v))return;selBond=i;selArm={bi:i,s:sh,v};sel=null;if($("edlg").open){restoring=true;$("edlg").close();restoring=false;}render();
 const pane=$("arm-popover");armDraft={bi:i,s:sh,v};$("ap-title").textContent=T().subBond;$("ap-summary").textContent=`${T().armBranch}: ${sh} = ${v}`;setSelectOptions($("ap-value"),SHEETVALS[sh]||[],v);
 pane.classList.add("show");const wrap=$("stagewrap").getBoundingClientRect();if(e&&"clientX" in e)placeArmPane({x:e.clientX-wrap.left,y:e.clientY-wrap.top});else{const p=armWorldPoint(i,sh,v);placeArmPane(p?{x:view.tx+p.x*view.scale,y:view.ty+p.y*view.scale}:null);}}
function saveArmPane(){if(!armDraft)return;replaceArmValue(armDraft.bi,armDraft.s,armDraft.v,$("ap-value").value);}
function replaceArmValue(i,sh,oldv,newv){if(!armValid(i,sh,oldv)||oldv===newv){closeArmPane(false);if($("adlg").open)$("adlg").close();return;}const vals=bonds[i].sides[sh]||[];if(vals.includes(newv)){toast(T().alreadyInLink);return;}pushUndo();bonds[i].sides[sh]=vals.map(v=>v===oldv?newv:v);selBond=i;selArm={bi:i,s:sh,v:newv};armDraft=null;$("arm-popover").classList.remove("show");if($("adlg").open)$("adlg").close();render();toast(T().armChanged);}
function removeBondValue(i,sh,v){if(!armValid(i,sh,v))return;pushUndo();const b=bonds[i];b.sides[sh]=(b.sides[sh]||[]).filter(x=>x!==v);if(!b.sides[sh].length)delete b.sides[sh];if(bondNodes(b).length<2){bonds.splice(i,1);selBond=null;}else{selBond=Math.min(i,bonds.length-1);}selArm=null;armDraft=null;$("arm-popover").classList.remove("show");if($("adlg").open)$("adlg").close();render();toast(T().armDeleted);}

// the always-on warning banner: contradictory links and/or an over-constrained (empty) result
function conflictActions(){const actions=[],seenKeys=new Set();
 const add=(keep,drop,why)=>{drop=[...new Set(drop)].filter(i=>i!==keep&&bonds[i]);if(!bonds[keep]||!drop.length)return;
   const key=keep+"|"+drop.slice().sort((a,b)=>a-b).join(",");if(seenKeys.has(key))return;seenKeys.add(key);actions.push({keep,drop,why});};
 const exact={};
 bonds.forEach((b,i)=>{if(b.when||b.mapping||b.assert)return;(exact[conflictKey(b)]=exact[conflictKey(b)]||[]).push(i);});
 Object.values(exact).forEach(g=>{if(new Set(g.map(i=>bonds[i].polarity)).size>1)g.forEach(i=>add(i,g.filter(j=>j!==i),"opposite"));});
 const reqBySheet={};
 bonds.forEach((b,i)=>{if(b.when||b.mapping||b.assert||b.polarity!=="require")return;bondSheets(b).forEach(sh=>{const vals=b.sides[sh]||[];if(vals.length)(reqBySheet[sh]=reqBySheet[sh]||[]).push(i);});});
 Object.values(reqBySheet).forEach(idxs=>{const uniq=[...new Set(idxs)];if(uniq.length<2)return;
   for(const sh of bondSheets(bonds[uniq[0]])){let inter=null,allHave=true;uniq.forEach(i=>{const vals=new Set(bonds[i].sides[sh]||[]);if(!vals.size)allHave=false;else inter=inter===null?new Set(vals):setIntersection(inter,vals);});
     if(allHave&&inter&&inter.size===0){uniq.forEach(i=>add(i,uniq.filter(j=>j!==i),"require"));break;}}});
 const req={};
 bonds.forEach((b,i)=>{if(b.when||b.mapping||b.assert||b.polarity!=="require")return;
   for(const sh of bondSheets(b)){const vals=new Set(b.sides[sh]||[]);if(!vals.size)continue;
     if(!req[sh])req[sh]={vals:new Set(vals),idxs:new Set([i])};
     else{req[sh].vals=setIntersection(req[sh].vals,vals);req[sh].idxs.add(i);}}});
 bonds.forEach((b,i)=>{if(b.when||b.mapping||b.assert||b.polarity!=="forbid")return;const sh=bondSheets(b);if(!sh.length)return;
   const covered=sh.every(sh=>req[sh]&&req[sh].vals.size&&setSubset(req[sh].vals,new Set(b.sides[sh]||[])));
   if(covered){const greens=[...new Set(sh.flatMap(sh=>[...(req[sh].idxs||[])]))];add(i,greens,"red-covers-green");greens.forEach(g=>add(g,[i],"green-over-red"));}});
 return actions.slice(0,8);}
function renderResolveActions(){const box=$("resolve-actions");if(!box)return;const acts=(conflictBonds&&conflictBonds.size)?conflictActions():[];
 if(!acts.length){box.innerHTML="";return;}
 box.innerHTML=`<div class="resolve-title">${esc(T().resolveTitle)}</div>`+acts.map((a,ai)=>`<button class="resolve-btn" data-ai="${ai}" title="${esc(T().resolveInFavor)}"><span class="keep">${esc(T().resolveInFavor)}: ${esc(plainBondText(bonds[a.keep]))}</span><span class="drop">${esc(T().resolveDeletes)}: ${esc(a.drop.map(i=>plainBondText(bonds[i])).join("; "))}</span></button>`).join("");
 box.querySelectorAll(".resolve-btn").forEach(btn=>btn.onclick=()=>{const a=conflictActions()[+btn.dataset.ai];if(a)resolveConflict(a.keep,a.drop);});}
function resolveConflict(keep,drop){if(!bonds[keep])return;pushUndo();const keepBond=bonds[keep],dropSet=new Set(drop);bonds=bonds.filter((_,i)=>!dropSet.has(i));selBond=bonds.indexOf(keepBond);selArm=null;sel=null;render();toast(T().resolveDone);}
// the always-on warning banner: contradictory links and/or an over-constrained (empty) result
function refreshWarn(){const w=$("warn");if(!w)return;const m=[];
 if(conflictBonds&&conflictBonds.size)m.push(lang==="ru"
   ?`⚠ противоречие: ${conflictBonds.size} связь(и) конфликтуют — выберите ниже, что оставить`
   :`⚠ contradiction: ${conflictBonds.size} link(s) conflict — choose below what to keep`);
 if(emptyResult)m.push(lang==="ru"?"⚠ связи слишком строгие — не остаётся ни одной комбинации"
                                   :"⚠ links over-constrain — no combination survives");
 w.innerHTML=m.join("<br>");renderResolveActions();}
// impact: offline in-browser estimate, OR (opt-in) exact from the live DB via D.impact endpoint
function renderImpactLocal(){const im=impact();
 const kept=("kept" in im)?im.kept:(im.full-im.removed),pct=im.full?100*im.removed/im.full:0;
 if(im.exact){$("impact").innerHTML=`<b>${fmtNum(im.removed)}</b> / ${fmtNum(im.full)} · <span class="hint">${T().kept(fmtNum(kept))}</span>`;
   $("bar").style.width=pct+"%";$("impacthint").textContent="";emptyResult=(kept===0&&im.full>0&&bonds.length>0);}
 else{$("impact").innerHTML=`<b>≈${fmtNum(im.removed)}</b> / ${fmtNum(im.full)} · <span class="hint">${T().kept("≈"+fmtNum(kept))}</span>`;
   $("bar").style.width=pct+"%";$("impacthint").textContent=(lang==="ru"?`оценка по ${fmtNum(im.sampled)} пробам; точное число даст --sieve`:`sampled estimate over ${fmtNum(im.sampled)} rows; --sieve gives exact count`);emptyResult=(kept===0&&im.full>0&&bonds.length>0);}
 refreshWarn();}
function showImpactExact(d){$("impact").innerHTML=`<b>${fmtNum(d.removed)}</b> / ${fmtNum(d.total)} · <span class="hint">${T().kept(fmtNum(d.kept))}</span> <span class="pill r" style="font-size:10px;vertical-align:middle">${esc(T().exactBadge)}</span>`;
 $("bar").style.width=(d.total?100*d.removed/d.total:0)+"%";$("impacthint").textContent=T().exactNote;
 emptyResult=(d.kept===0&&d.total>0&&bonds.length>0);refreshWarn();}
let _impactTimer=null;
function updateImpact(){if(!D.impact){renderImpactLocal();return;}clearTimeout(_impactTimer);$("impacthint").textContent="…";
 _impactTimer=setTimeout(()=>fetch(D.impact,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(bondsToSidecar())})
   .then(r=>r.json()).then(d=>{if(d&&d.exact){showImpactExact(d);}else{renderImpactLocal();}}).catch(()=>renderImpactLocal()),300);}
// ---- node-centric inspector + spotlight (ADDITIVE — the value-LINES on the canvas are preserved;
//      this only highlights/dims them and DESCRIBES them per node in the side panel) ----
let hoverNode=null;
function inspectNode(){return hoverNode!=null?hoverNode:(sel!=null?sel:null);}   // hover wins, else the draw-start node
const VALUE_OPS=["eq","ne","has","hasnt","in","nin","hasAny"];
function valueInCond(c,sheet,value){if(!c)return false;
 if(c.all)return c.all.some(x=>valueInCond(x,sheet,value));
 if(c.any)return c.any.some(x=>valueInCond(x,sheet,value));
 if(c.not)return valueInCond(c.not,sheet,value);
 if(c.sheet!==sheet)return false;
 for(const op of VALUE_OPS)if(op in c){const v=c[op];return Array.isArray(v)?v.includes(value):v===value;}
 return false;}
function memberBonds(sheet,value){const out=[];                       // bonds where this value is a drawn LINE member
 bonds.forEach((b,bi)=>{if(b.when||b.mapping||b.assert)return;const sd=b.sides||{};
   if((sd[sheet]||[]).includes(value)){const others=[];
     Object.keys(sd).forEach(s=>{if(s===sheet)return;(sd[s]||[]).forEach(v=>others.push([s,v]));});
     out.push({bi,b,others});}});
 return out;}
function contextBonds(sheet,value){const out=[];                      // bonds where this value is a CONDITION/assert context
 bonds.forEach((b,bi)=>{const inSide=b.sides&&(b.sides[sheet]||[]).includes(value);
   if(inSide)return;
   if(valueInCond(b.condition,sheet,value)||(b.assert&&valueInCond(b.assert,sheet,value)))out.push({bi,b});});
 return out;}
function nodeDots(id){const[s,v]=JSON.parse(id);let f=false,r=false;
 memberBonds(s,v).forEach(m=>{if(m.b.polarity==="forbid")f=true;else r=true;});
 const c=contextBonds(s,v).length>0;let h="";
 if(f)h+='<i class="f"></i>';if(r)h+='<i class="r"></i>';if(c)h+='<i class="c"></i>';
 return h?`<span class="bdots">${h}</span>`:"";}
function renderNodeInfo(){const box=$("nodeinfo");if(!box)return;const id=inspectNode(),x=T();
 if(id==null){box.innerHTML=`<div class="ni-empty">${esc(x.niPickHint)}</div>`;return;}
 const[s,v]=JSON.parse(id),mem=memberBonds(s,v),ctx=contextBonds(s,v);
 let h=`<div class="ni-head"><span><span class="ni-val">${esc(v)}</span> <span class="ni-col">∈ ${esc(s)}</span></span></div>`;
 if(!mem.length&&!ctx.length)h+=`<div class="ni-empty">${esc(x.niEmpty)}</div>`;
 if(mem.length){h+=`<div class="hint" style="margin:2px 0 5px">${esc(x.niMember)}</div>`;
   mem.forEach(({bi,b,others})=>{const pol=b.polarity==="forbid",cl=pol?"f":"r",sym=pol?"╳":"✓";
     const conn=others.map(([os,ov])=>`<span class="ni-chip">${esc(ov)} <span class="ni-col">∈${esc(os)}</span></span>`).join(`<span class="ni-conn ${cl}">·</span>`);
     const when=b.condition?`<div class="ni-when">${esc(x.niWhen)} ${esc(describeCond(b.condition))}</div>`:"";
     h+=`<div class="ni-row ${bi===selBond?'sel':''}" data-bi="${bi}"><div class="ni-line">`
       +`<span class="ni-chip self">${esc(v)}</span><span class="ni-conn ${cl}" title="${esc(pol?x.niForbid:x.niRequire)}">${sym}</span>${conn}`
       +`<button class="ni-x" data-del="${bi}" title="✕">✕</button></div>${when}</div>`;});}
 if(ctx.length){h+=`<div class="hint" style="margin:6px 0 5px">${esc(x.niCtx)}</div>`;
   ctx.forEach(({bi,b})=>{h+=`<div class="ni-row ${bi===selBond?'sel':''}" data-bi="${bi}"><div class="ni-ctx">${bondText(b)}</div></div>`;});}
 box.innerHTML=h;
 box.querySelectorAll(".ni-row").forEach(rw=>{rw.onclick=e=>{if(e.target.closest("button"))return;const bi=+rw.dataset.bi;if(e.detail>=2){runDoubleClick(()=>openBondDialog(bi));return;}scheduleSingleClick(()=>{selBond=bi;selArm=null;hoverNode=null;render();});};rw.ondblclick=e=>{if(e.target.closest("button"))return;runDoubleClick(()=>openBondDialog(+rw.dataset.bi));};});
 box.querySelectorAll("[data-del]").forEach(btn=>btn.onclick=()=>{pushUndo();bonds.splice(+btn.dataset.del,1);selBond=null;selArm=null;render();});}
function spotlight(){const cv=$("canvas");if(!cv)return;const id=(selBond===null)?inspectNode():null;
 cv.classList.toggle("spotlight",id!=null);
 const memBi=new Set(),halo={};
 if(id!=null){const[s,v]=JSON.parse(id);
   memberBonds(s,v).forEach(({bi,b,others})=>{memBi.add(bi);others.forEach(([os,ov])=>{halo[nid(os,ov)]=b.polarity==="forbid"?"hl-f":"hl-r";});});
   contextBonds(s,v).forEach(({b})=>{const sd=b.sides||{};Object.keys(sd).forEach(os=>(sd[os]||[]).forEach(ov=>{if(!halo[nid(os,ov)])halo[nid(os,ov)]="hl-ctx";}));});
   halo[id]="hl-self";}
 cv.querySelectorAll(".node").forEach(n=>{n.classList.remove("hl-self","hl-f","hl-r","hl-ctx");const cls=halo[n.dataset.id];if(cls)n.classList.add(cls);});
 cv.querySelectorAll("#edges [data-bi]").forEach(el=>{const bi=+el.dataset.bi;
   if(id!=null){el.classList.toggle("hot",memBi.has(bi));el.classList.toggle("dim",!memBi.has(bi));}});}
function updateInspect(){renderNodeInfo();spotlight();}

function renderPanel(){
 const lt=$("links");
 updateImpact();refreshWarn();
 // links (drawable value-links only; `when`/`mapping` are sheet-level → the advanced list below)
 const enr=bonds.map((b,i)=>[b,i]).filter(([b])=>!b.when&&!b.mapping&&!b.assert);
 if(!enr.length)lt.innerHTML=`<div class="empty">${T().emptyLinks}</div>`;
 else lt.innerHTML=enr.map(([b,i])=>{const cls=b.polarity==="forbid"?"f":"r";const word=b.polarity==="forbid"?T().forbidW:T().requireW;
   return `<div class="row ${i===selBond?'sel':''}" data-bi="${i}"><span class="pill ${cls}">${esc(word)}</span>
     <span class="txt">${bondText(b)}</span>
     <button class="x" data-del="${i}" aria-label="delete">✕</button></div>`;}).join("");
 lt.querySelectorAll(".row").forEach(r=>{r.onclick=e=>{if(e.target.closest("button"))return;const bi=+r.dataset.bi;if(e.detail>=2){runDoubleClick(()=>openBondDialog(bi));return;}scheduleSingleClick(()=>{selBond=(selBond===bi?null:bi);selArm=null;sel=null;render();if(selBond!==null&&canExtendBond(bonds[selBond]))toast(T().extendPick);});};r.ondblclick=e=>{if(e.target.closest("button"))return;runDoubleClick(()=>openBondDialog(+r.dataset.bi));};});
 lt.querySelectorAll("[data-del]").forEach(b=>b.onclick=()=>{pushUndo();bonds.splice(+b.dataset.del,1);selBond=null;selArm=null;render();});
 // formulas + mappings (sheet-level advanced bonds)
 const fr=bonds.map((b,i)=>[b,i]).filter(([b])=>b.when||b.mapping||b.assert);
 $("formulas").innerHTML=fr.length?fr.map(([b,i])=>{const cls=b.polarity==="forbid"?"f":"r";
   return `<div class="row ${i===selBond?'sel':''}" data-bi="${i}"><span class="pill ${cls}">${b.polarity==='forbid'?T().forbidW:T().requireW}</span>
     <span class="txt">${bondText(b)}<br><small>${esc(bondSheets(b).join(", "))} · ${T().nodraw}</small></span>
     <button class="x" data-delf="${i}">✕</button></div>`;}).join(""):`<div class="empty">—</div>`;
 $("formulas").querySelectorAll(".row").forEach(r=>{r.onclick=e=>{if(e.target.closest("button"))return;const bi=+r.dataset.bi;if(e.detail>=2){runDoubleClick(()=>openBondDialog(bi));return;}scheduleSingleClick(()=>{selBond=(selBond===bi?null:bi);selArm=null;sel=null;render();});};r.ondblclick=e=>{if(e.target.closest("button"))return;runDoubleClick(()=>openBondDialog(+r.dataset.bi));};});
 $("formulas").querySelectorAll("[data-delf]").forEach(b=>b.onclick=()=>{pushUndo();bonds.splice(+b.dataset.delf,1);selBond=null;selArm=null;render();});
 renderLinkEditor();
 renderNodeInfo();
 renderParams();
}
function renderParams(){const tb=$("params");let rows="";
 SHEETS.forEach(s=>s[1].forEach(v=>{const cur=(params[s[0]]||{})[v]||{};const txt=Object.entries(cur).map(([k,x])=>k+"="+x).join(", ");
   rows+=`<tr><td style="color:var(--muted);white-space:nowrap">${esc(s[0])}:${esc(v)}</td><td><input data-s="${attr(s[0])}" data-v="${attr(v)}" value="${attr(txt)}" placeholder="charge=2, n=1"></td></tr>`;}));
 tb.innerHTML=rows;
 tb.querySelectorAll("input").forEach(inp=>inp.onchange=()=>{pushUndo();const d={};inp.value.split(",").forEach(p=>{const m=p.split("=");if(m.length===2){const k=m[0].trim(),x=m[1].trim();if(k)d[k]=isNaN(+x)?x:+x;}});
   params[inp.dataset.s]=params[inp.dataset.s]||{};params[inp.dataset.s][inp.dataset.v]=d;renderPanel();});}

// ---- interactions ----
function clickNode(id){
 if(multi){const i=tray.indexOf(id);if(i>=0)tray.splice(i,1);else tray.push(id);updateTray();render();return;}
 if(selBond!==null&&canExtendBond(bonds[selBond])){addNodeToBond(selBond,id);render();return;}
 if(sel===null){sel=id;}
 else if(sel===id){sel=null;}
 else{const a=JSON.parse(sel),b=JSON.parse(id);
   if(a[0]!==b[0]){addSingleton(a,b);}else{toast(lang==="ru"?"Нужны значения из РАЗНЫХ листов":"Pick values from DIFFERENT sheets");}
   sel=null;}
 render();
}
function canExtendBond(b){return b&&!b.when&&!b.mapping&&!b.assert;}
function addNodeToBond(i,id){const b=bonds[i];if(!canExtendBond(b)){toast(T().cannotExtend);return false;}
 const[s,v]=JSON.parse(id),vals=(b.sides[s]=b.sides[s]||[]);
 if(vals.includes(v)){toast(T().alreadyInLink);return false;}
 pushUndo();vals.push(v);sel=null;selBond=i;selArm={bi:i,s,v};toast(T().addToLink);return true;}
// a quick 2-click line = a singleton-sided bond {A:[a], C:[c]} — blocked if it contradicts/dupes one
function addSingleton(a,b){const sides={};sides[a[0]]=[a[1]];sides[b[0]]=[b[1]];
 const nb={polarity:mode,sides,gate:Object.assign({},gate),when:null,desc:""},c=checkAdd(nb);
 if(c.conflict){toast(lang==="ru"?"Противоречие: та же связь уже задана с противоположным типом":"Contradiction: the same link already exists with the opposite type");return;}
 if(c.dup){selBond=c.at;toast(lang==="ru"?"Такая связь уже есть":"That link already exists");return;}
 pushUndo();bonds.push(nb);selBond=bonds.length-1;selArm=null;}
// group / Many:Many = tray grouped by sheet -> one bond whose sides hold value SETS (cross product)
function makeGroupBond(){const sides={};tray.forEach(id=>{const[s,v]=JSON.parse(id);(sides[s]=sides[s]||[]).push(v);});
 if(Object.keys(sides).length<2){toast(lang==="ru"?"Нужны значения из ≥2 листов":"Need values from ≥2 sheets");return;}
 const nb={polarity:mode,sides,gate:Object.assign({},gate),when:null,desc:""},c=checkAdd(nb);
 if(c.conflict){toast(lang==="ru"?"Противоречие: та же группа-связь уже задана с противоположным типом":"Contradiction: the same group link already exists with the opposite type");return;}
 if(c.dup){selBond=c.at;tray=[];updateTray();render();toast(lang==="ru"?"Такая группа-связь уже есть":"That group link already exists");return;}
 pushUndo();bonds.push(nb);selBond=bonds.length-1;selArm=null;tray=[];updateTray();render();}
function updateTray(){const bySheet={};tray.forEach(id=>{const[s,v]=JSON.parse(id);(bySheet[s]=bySheet[s]||[]).push(v);});
 $("traychips").innerHTML=Object.keys(bySheet).map(s=>`<span class="chip">${esc(s)}∈{${bySheet[s].map(esc).join(", ")}}</span>`).join("")
   ||`<span class="hint">${lang==="ru"?"кликайте значения (можно несколько в листе)":"click values (several per sheet OK)"}</span>`;
 $("tray").classList.toggle("show",multi);
 $("makebond").disabled=!(Object.keys(bySheet).length>=2);}

// ---- gate control ----
function readGate(){const g=$("gate").value;if(g==="adjacent")return{adjacent:true};if(g==="within")return{within:+$("within").value||2};return{};}
$("gate").onchange=()=>{$("within").style.display=$("gate").value==="within"?"":"none";gate=readGate();};
$("within").onchange=()=>gate=readGate();

// ---- mode ----
function setMode(m){mode=m;$("m-forbid").classList.toggle("on",m==="forbid");$("m-require").classList.toggle("on",m==="require");}
$("m-forbid").onclick=()=>setMode("forbid");$("m-require").onclick=()=>setMode("require");
$("multi").onchange=e=>{multi=e.target.checked;tray=[];sel=null;updateTray();render();};
$("makebond").onclick=()=>makeGroupBond();
$("cleartray").onclick=()=>{tray=[];updateTray();render();};
$("quick-forbid").onclick=()=>setQuickPol("forbid");$("quick-require").onclick=()=>setQuickPol("require");
$("quick-s1").onchange=()=>{if($("quick-s1").value===$("quick-s2").value&&SHEETS.length>1)$("quick-s2").value=SHEETS.map(s=>s[0]).find(n=>n!==$("quick-s1").value);renderQuickValues();};
$("quick-s2").onchange=()=>{if($("quick-s1").value===$("quick-s2").value&&SHEETS.length>1)$("quick-s1").value=SHEETS.map(s=>s[0]).find(n=>n!==$("quick-s2").value);renderQuickValues();};
$("quick-v1").onchange=()=>renderQuickPreview();$("quick-v2").onchange=()=>renderQuickPreview();
$("quick-gate").onchange=()=>{$("quick-within").style.display=$("quick-gate").value==="within"?"":"none";renderQuickPreview();};$("quick-within").onchange=()=>renderQuickPreview();
$("quick-add").onclick=()=>{const a=[$("quick-s1").value,$("quick-v1").value],b=[$("quick-s2").value,$("quick-v2").value];if(!a[0]||!b[0]||a[0]===b[0]){toast(lang==="ru"?"Выберите разные листы":"Pick different sheets");return;}const sides={[a[0]]:[a[1]],[b[0]]:[b[1]]};const nb={polarity:$("quick-pol").value,sides,gate:readQuickGate(),when:null,condition:null,desc:""},c=checkAdd(nb);if(c.conflict){toast(lang==="ru"?"Противоречие: такая связь уже есть с другим типом":"Contradiction: same link exists with opposite type");return;}if(c.dup){selBond=c.at;toast(lang==="ru"?"Такая связь уже есть":"That link already exists");render();return;}pushUndo();bonds.push(nb);selBond=bonds.length-1;selArm=null;render();};
$("quick-rule").onclick=()=>openRelation();
$("rcancel").onclick=()=>$("rdlg").close();
$("r-require").onclick=()=>{$("r-pol").value="require";renderRelationBuilder();};$("r-forbid").onclick=()=>{$("r-pol").value="forbid";renderRelationBuilder();};
$("r-json-apply").onclick=()=>{try{relDraft.condition=JSON.parse($("r-json").value||"null");$("rhint").textContent="";renderRelationBuilder();}catch(e){$("rhint").textContent="bad JSON";}};
$("radd").onclick=()=>{const body=relDraft.condition,sh=conditionSheets(body);if(!body||!sh.length){$("rhint").textContent=T().rNeed;return;}pushUndo();bonds.push({polarity:$("r-pol").value,sides:Object.fromEntries(sh.map(s=>[s,[]])),gate:{},when:null,condition:null,mapping:null,assert:body,desc:""});selBond=bonds.length-1;selArm=null;$("rdlg").close();render();toast(T().rMade);};
$("eclose").onclick=()=>closeBondDialog();
$("acancel").onclick=()=>$("adlg").close();
$("adel").onclick=()=>{if(selArm)removeBondValue(selArm.bi,selArm.s,selArm.v);};
$("aapply").onclick=()=>{if(selArm)replaceArmValue(selArm.bi,selArm.s,selArm.v,$("a-value").value);};
$("ap-close").onclick=()=>closeArmPane(true);
$("ap-discard").onclick=()=>discardArmPane();
$("ap-save").onclick=()=>saveArmPane();
$("edlg").addEventListener("close",()=>{if(!restoring&&selBond!==null)render();});
$("adlg").addEventListener("close",()=>{if(!restoring&&selBond!==null)render();});

// ---- canvas: vertical node drag · background pan · wheel/keys zoom (mouse pointer events) ----
function applyView(){const vp=$("viewport");if(vp)vp.style.transform=`translate(${view.tx}px,${view.ty}px) scale(${view.scale})`;
 const z=$("zpct");if(z)z.textContent=Math.round(view.scale*100)+"%";}
let _raf=null;
function layoutDrag(){if(_raf)return;_raf=requestAnimationFrame(()=>{_raf=null;if(!drag)return;   // cheap: move the node + redraw edges
 const[s,v]=JSON.parse(drag.id),xy=nodeXY(s,v);if(drag.el&&xy)drag.el.style.top=xy.y+"px";
 const sv=$("edges");if(sv){sv.innerHTML=edgesInner();bindEdges($("canvas"));}});}
function startNodeDrag(e,el){if(e.button!==undefined&&e.button!==0)return;const id=el.dataset.id;
 drag={id,sy:e.clientY,y0:(id in nodeY)?nodeY[id]:nodeXY(...JSON.parse(id)).y,moved:false,el};
 el.classList.add("dragging");try{el.setPointerCapture(e.pointerId);}catch(_){}}
$("stagewrap").addEventListener("pointerdown",e=>{          // empty-canvas drag = pan the viewport
 if(e.target.closest(".node")||e.target.closest("#edges [data-bi]")||e.target.closest("#zoomctl")||e.target.closest("#arm-popover"))return;
 pan={sx:e.clientX,sy:e.clientY,tx:view.tx,ty:view.ty};$("stagewrap").classList.add("panning");});
document.addEventListener("pointermove",e=>{
 if(drag){if(Math.abs(e.clientY-drag.sy)>3)drag.moved=true;
   nodeY[drag.id]=clampY(drag.y0+(e.clientY-drag.sy)/view.scale);layoutDrag();return;}   // x stays in-column; y follows
 if(pan){view.tx=pan.tx+(e.clientX-pan.sx);view.ty=pan.ty+(e.clientY-pan.sy);applyView();}});
document.addEventListener("pointerup",()=>{
 if(drag){if(drag.el)drag.el.classList.remove("dragging");if(drag.moved){suppressClick=true;render();}drag=null;}
 if(pan){pan=null;$("stagewrap").classList.remove("panning");}});
function zoomAt(sx,sy,f){const wx=(sx-view.tx)/view.scale,wy=(sy-view.ty)/view.scale;   // zoom toward a screen point
 view.scale=clampZ(view.scale*f);view.tx=sx-wx*view.scale;view.ty=sy-wy*view.scale;applyView();}
function zoomCenter(f){const r=$("stagewrap").getBoundingClientRect();zoomAt(r.width/2,r.height/2,f);}
function fitView(){const r=$("stagewrap").getBoundingClientRect(),rows=Math.max(...SHEETS.map(s=>s[1].length),1);
 const W=PADX+(SHEETS.length-1)*COLW+PADX,H=Math.max(stageH(),PADY+rows*ROWH+24);
 view.scale=clampZ(Math.min(r.width/W,r.height/H,1.5)||1);view.tx=Math.max(8,(r.width-W*view.scale)/2);view.ty=10;applyView();}
$("stagewrap").addEventListener("wheel",e=>{e.preventDefault();const r=$("stagewrap").getBoundingClientRect();
 zoomAt(e.clientX-r.left,e.clientY-r.top,e.deltaY<0?1.12:1/1.12);},{passive:false});
$("zin").onclick=()=>zoomCenter(1.2);$("zout").onclick=()=>zoomCenter(1/1.2);$("zfit").onclick=()=>fitView();

// ---- formula dialog ----
// ── nested block formula builder (Blockly-grade): a typed AST of blocks plugged into slots; the
// "Блоки" mode (parallel to the text field). No deps; compiles the block tree to a `when` string. ──
let fmode="text", ftree=null, fmenu=null, dragData=null;
function paramsOf(sheet){const set=new Set(["value","pos"]);const sv=params[sheet]||{};for(const v in sv)for(const k in sv[v])set.add(k);return [...set];}
function produces(t){return (t==="cmp"||t==="logic"||t==="not")?"bool":"arith";}   // a block's result type
function clearDrop(){document.querySelectorAll(".drop-ok,.drop-no").forEach(e=>e.classList.remove("drop-ok","drop-no"));}
function dragProduces(){return !dragData?null:(dragData.kind==="new"?produces(dragData.t):produces(getAt(dragData.path).t));}
function dropOK(el){if(!dragData||dragProduces()!==el.dataset.droptype)return false;     // type must match the slot
 if(dragData.kind==="move"){const s=dragData.path,d=el.dataset.droppath;if(s===""||d===s||d.startsWith(s+".")||getAt(d)!==null)return false;} // no cycle; move only into empty slots
 return true;}
function doDrop(el){if(!dropOK(el))return;const d=el.dataset.droppath;
 if(dragData.kind==="new")setAt(d,newNode(dragData.t));                                  // palette block -> (replace) slot
 else{const sub=getAt(dragData.path);setAt(dragData.path,null);setAt(d,sub);}            // move an existing subtree
 dragData=null;renderFtree();}
function buildPalette(){const x=T();const items=[["cmp",x.mCmp],["logic",x.mLogic],["not",x.mNot],["arith",x.mArith],["param",x.mParam],["num",x.mNum]];
 $("fpalette").innerHTML=`<span class="le-lbl">${esc(x.palLbl)}</span>`+items.map(([t,l])=>`<span class="palitem" draggable="true" data-new="${t}">${esc(l)}</span>`).join("");
 $("fpalette").querySelectorAll(".palitem").forEach(p=>{p.ondragstart=e=>{dragData={kind:"new",t:p.dataset.new};try{e.dataTransfer.setData("text/plain",p.dataset.new);}catch(_){}e.dataTransfer.effectAllowed="copy";};p.ondragend=()=>{dragData=null;clearDrop();};});}
function setFmode(m){fmode=m;$("fmode-text").classList.toggle("on",m==="text");$("fmode-blocks").classList.toggle("on",m==="blocks");$("fexpr").style.display=m==="text"?"":"none";$("fblocks").style.display=m==="blocks"?"":"none";}
function getAt(p){if(!p)return ftree;let n=ftree;for(const k of p.split("."))n=n?n[k]:null;return n;}
function setAt(p,v){if(!p){ftree=v;return;}const ks=p.split(".");let n=ftree;for(let i=0;i<ks.length-1;i++)n=n[ks[i]];n[ks[ks.length-1]]=v;}
function newNode(t){const S=SHEETS.length?SHEETS[0][0]:"";return t==="cmp"?{t,op:">",a:null,b:null}:t==="logic"?{t,op:"and",a:null,b:null}:t==="not"?{t,x:null}:t==="arith"?{t,op:"*",a:null,b:null}:t==="param"?{t,sheet:S,param:(paramsOf(S)[0]||"value")}:{t:"num",val:"0"};}
function compileT(n){if(!n)return null;if(n.t==="param")return n.sheet+"."+n.param;if(n.t==="num")return String(n.val);
 if(n.t==="not"){const x=compileT(n.x);return x==null?null:"not ("+x+")";}
 const a=compileT(n.a),b=compileT(n.b);return (a==null||b==null)?null:"("+a+" "+n.op+" "+b+")";}
function opsOf(t){return t==="cmp"?[[">",">"],[">=","≥"],["<","<"],["<=","≤"],["==","="],["!=","≠"]]:t==="logic"?[["and","and"],["or","or"]]:[["+","+"],["-","−"],["*","×"]];}
function selH(cls,path,val,opts){return `<select class="${cls}" data-path="${attr(path)}">`+opts.map(([v,l])=>`<option value="${attr(v)}"${v==val?" selected":""}>${esc(l)}</option>`).join("")+`</select>`;}
function nodeH(n,path,slot){const x=T();
 if(!n){if(fmenu===path){const o=slot==="bool"?[["cmp",x.mCmp],["logic",x.mLogic],["not",x.mNot]]:[["arith",x.mArith],["param",x.mParam],["num",x.mNum]];
   return `<span class="fmenu">`+o.map(([t,l])=>`<button class="btn fp" data-ins="${attr(path)}" data-t="${t}">${esc(l)}</button>`).join("")+`<button class="btn fp" data-cancel="1">✕</button></span>`;}
   return `<button class="slot" data-open="${attr(path)}" data-droppath="${attr(path)}" data-droptype="${slot}">＋</button>`;}
 const rm=`<button class="chx" data-rm="${attr(path)}">✕</button>`,cp=k=>path?path+"."+k:k,
   da=`draggable="true" data-droppath="${attr(path)}" data-droptype="${produces(n.t)}"`;
 if(n.t==="param")return `<span class="blk leaf" ${da}>${selH("ssel",path,n.sheet,SHEETS.map(s=>[s[0],s[0]]))}.${selH("psel",path,n.param,paramsOf(n.sheet).map(p=>[p,p]))}${rm}</span>`;
 if(n.t==="num")return `<span class="blk leaf" ${da}><input class="bnum" data-path="${attr(path)}" type="number" value="${attr(n.val)}" style="width:58px">${rm}</span>`;
 if(n.t==="not")return `<span class="blk" ${da}>${esc(x.mNot)} ${nodeH(n.x,cp("x"),"bool")}${rm}</span>`;
 const cs=n.t==="logic"?"bool":"arith";
 return `<span class="blk" ${da}>${nodeH(n.a,cp("a"),cs)} ${selH("opsel",path,n.op,opsOf(n.t))} ${nodeH(n.b,cp("b"),cs)}${rm}</span>`;}
function renderFtree(){$("ftree").innerHTML=nodeH(ftree,"","bool");$("fbuilt").textContent=compileT(ftree)||"…";const t=$("ftree");
 t.querySelectorAll("[data-open]").forEach(b=>b.onclick=()=>{fmenu=b.dataset.open;renderFtree();});
 t.querySelectorAll("[data-cancel]").forEach(b=>b.onclick=()=>{fmenu=null;renderFtree();});
 t.querySelectorAll("[data-ins]").forEach(b=>b.onclick=()=>{setAt(b.dataset.ins,newNode(b.dataset.t));fmenu=null;renderFtree();});
 t.querySelectorAll("[data-rm]").forEach(b=>b.onclick=()=>{setAt(b.dataset.rm,null);fmenu=null;renderFtree();});
 t.querySelectorAll(".opsel").forEach(s=>s.onchange=()=>{getAt(s.dataset.path).op=s.value;renderFtree();});
 t.querySelectorAll(".ssel").forEach(s=>s.onchange=()=>{const n=getAt(s.dataset.path);n.sheet=s.value;n.param=paramsOf(s.value)[0]||"value";renderFtree();});
 t.querySelectorAll(".psel").forEach(s=>s.onchange=()=>{getAt(s.dataset.path).param=s.value;renderFtree();});
 t.querySelectorAll(".bnum").forEach(i=>i.oninput=()=>{getAt(i.dataset.path).val=i.value;$("fbuilt").textContent=compileT(ftree)||"…";});
 t.querySelectorAll("[data-droppath]").forEach(el=>{                                     // drop targets (slots + blocks)
   el.ondragover=e=>{e.preventDefault();e.stopPropagation();const ok=dropOK(el);el.classList.remove("drop-ok","drop-no");el.classList.add(ok?"drop-ok":"drop-no");e.dataTransfer.dropEffect=ok?(dragData&&dragData.kind==="move"?"move":"copy"):"none";};
   el.ondragleave=()=>el.classList.remove("drop-ok","drop-no");
   el.ondrop=e=>{e.preventDefault();e.stopPropagation();el.classList.remove("drop-ok","drop-no");doDrop(el);};});
 t.querySelectorAll(".blk[draggable]").forEach(b=>{b.ondragstart=e=>{e.stopPropagation();dragData={kind:"move",path:b.dataset.droppath};try{e.dataTransfer.setData("text/plain","m");}catch(_){}e.dataTransfer.effectAllowed="move";};b.ondragend=()=>{dragData=null;clearDrop();};});
 buildPalette();}
$("fmode-text").onclick=()=>setFmode("text");$("fmode-blocks").onclick=()=>{setFmode("blocks");renderFtree();};
$("addformula").onclick=()=>{const box=$("fsheets");box.innerHTML=SHEETS.map(s=>`<label><input type="checkbox" value="${esc(s[0])}">${esc(s[0])}</label>`).join("");
 $("fexpr").value="";$("fhint").textContent="";ftree=null;fmenu=null;setFmode("text");renderFtree();$("fdlg").showModal();};
$("fcancel").onclick=()=>$("fdlg").close();
$("fadd").onclick=()=>{const sh=[...$("fsheets").querySelectorAll("input:checked")].map(c=>c.value);const expr=(fmode==="blocks"?(compileT(ftree)||""):$("fexpr").value).trim();
 if(sh.length<2){$("fhint").textContent=lang==="ru"?"Выберите ≥2 листа":"Pick ≥2 sheets";return;}
 if(!expr){$("fhint").textContent=fmode==="blocks"?(lang==="ru"?"Достройте формулу (есть пустые слоты)":"Complete the formula (empty slots)"):(lang==="ru"?"Введите формулу":"Enter a formula");return;}
 if(BAN.test(expr)){$("fhint").textContent=lang==="ru"?"Недопустимая формула":"Unsafe formula";return;}
 pushUndo();bonds.push({polarity:mode,sides:Object.fromEntries(sh.map(s=>[s,[]])),gate:Object.assign({},gate),when:expr,condition:null,desc:""});
 selArm=null;$("fdlg").close();$("advanced").open=true;render();};

// ---- mapping (dependency) dialog: "if SOURCE=value then TARGET ∈ {allowed}" — a dependent allowed-set ----
let mapDraft={src:null,tgt:null,allow:{}};
function openMapping(){const names=SHEETS.map(s=>s[0]);
 if(names.length<2){toast(lang==="ru"?"Нужно ≥2 листа":"Need ≥2 sheets");return;}
 mapDraft={src:names[0],tgt:names[1],allow:{}};
 const opts=names.map(n=>`<option value="${attr(n)}">${esc(n)}${OPTIONAL.has(n)?" ·opt":""}</option>`).join("");
 $("m-src").innerHTML=opts;$("m-tgt").innerHTML=opts;$("m-src").value=mapDraft.src;$("m-tgt").value=mapDraft.tgt;
 $("mhint").textContent="";renderMAllow();$("mdlg").showModal();}
function renderMAllow(){const x=T(),src=mapDraft.src,tgt=mapDraft.tgt,tvals=SHEETVALS[tgt]||[];
 $("m-allow").innerHTML=(SHEETVALS[src]||[]).map(sv=>{const cur=mapDraft.allow[sv]||[],uns=tvals.filter(v=>!cur.includes(v));
   return `<div class="le-row"><span class="le-lbl">${esc(src)}=${esc(sv)} →</span><span class="le-chips">`
     +cur.map(v=>`<span class="chip">${esc(v)}<button class="m-rm" data-sv="${attr(sv)}" data-v="${attr(v)}">✕</button></span>`).join("")
     +`</span>`+(uns.length?`<select class="m-add" data-sv="${attr(sv)}"><option value="">＋ ${esc(x.addVal)}</option>${uns.map(v=>`<option value="${attr(v)}">${esc(v)}</option>`).join("")}</select>`:"")+`</div>`;}).join("")
   ||`<div class="hint">${esc(x.mapPick)}</div>`;
 $("m-allow").querySelectorAll(".m-add").forEach(se=>se.onchange=()=>{if(se.value){(mapDraft.allow[se.dataset.sv]=mapDraft.allow[se.dataset.sv]||[]).push(se.value);renderMAllow();}});
 $("m-allow").querySelectorAll(".m-rm").forEach(btn=>btn.onclick=()=>{mapDraft.allow[btn.dataset.sv]=(mapDraft.allow[btn.dataset.sv]||[]).filter(v=>v!==btn.dataset.v);renderMAllow();});}
$("addmapping").onclick=()=>openMapping();$("quick-map").onclick=()=>openMapping();
$("mcancel").onclick=()=>$("mdlg").close();
$("m-src").onchange=()=>{mapDraft.src=$("m-src").value;if(mapDraft.src===mapDraft.tgt){mapDraft.tgt=SHEETS.map(s=>s[0]).find(n=>n!==mapDraft.src);$("m-tgt").value=mapDraft.tgt;}mapDraft.allow={};renderMAllow();};
$("m-tgt").onchange=()=>{mapDraft.tgt=$("m-tgt").value;if(mapDraft.tgt===mapDraft.src){mapDraft.src=SHEETS.map(s=>s[0]).find(n=>n!==mapDraft.tgt);$("m-src").value=mapDraft.src;}mapDraft.allow={};renderMAllow();};
$("madd").onclick=()=>{const allow={};for(const k in mapDraft.allow){if((mapDraft.allow[k]||[]).length)allow[k]=mapDraft.allow[k].slice();}
 if(mapDraft.src===mapDraft.tgt){$("mhint").textContent=lang==="ru"?"Разные столбцы":"Pick different columns";return;}
 if(!Object.keys(allow).length){$("mhint").textContent=lang==="ru"?"Задайте хотя бы одну зависимость":"Set at least one allowed value";return;}
 pushUndo();bonds.push({polarity:"forbid",sides:{[mapDraft.src]:[],[mapDraft.tgt]:[]},gate:{},when:null,condition:null,
   mapping:{source:mapDraft.src,target:mapDraft.tgt,allow},desc:""});
 selBond=bonds.length-1;selArm=null;$("mdlg").close();$("advanced").open=true;render();};

// ---- submit / download ----
function sidecarJSON(){return JSON.stringify(bondsToSidecar(),null,2);}
function download(){const b=new Blob([sidecarJSON()],{type:"application/json"});const u=URL.createObjectURL(b);
 const a=document.createElement("a");a.href=u;a.download="sidecar.json";a.click();URL.revokeObjectURL(u);}
$("dl").onclick=()=>{download();toast(T().dlsaved);};
function showOK(){$("okmsg").textContent=T().okmsg(bondsToSidecar().constraints.length);$("overlay").classList.add("show");}
$("submit").onclick=()=>{
 if(conflictBonds&&conflictBonds.size){toast(lang==="ru"?"Сначала уберите противоречивые связи":"Resolve the contradictory links first");return;}
 const payload=sidecarJSON();
 if(D.post){fetch(D.post,{method:"POST",headers:{"Content-Type":"application/json"},body:payload})
   .then(r=>{if(!r.ok)throw 0;showOK();}).catch(()=>{download();showOK();});}
 else{download();showOK();}};

// ---- lang ----
function applyLang(){const x=T();$("lang").textContent=lang==="ru"?"EN":"RU";document.documentElement.lang=lang;
 $("t-title").textContent=x.title;$("t-forbid").textContent=x.forbid;$("t-require").textContent=x.require;
 $("t-gate").textContent=x.gate;$("t-multi").textContent=x.multi;$("t-submit").textContent=x.submit;
 $("t-impact").textContent=x.impact;$("t-links").textContent=x.links;$("t-adv").textContent=x.adv;$("t-node").textContent=x.nodeTitle;
 $("t-build").textContent=x.buildTitle;$("t-quicklink").textContent=x.quickLink;$("t-card-forbid").textContent=x.cardForbid;$("t-card-forbid-cap").textContent=x.cardForbidCap;$("t-card-require").textContent=x.cardRequire;$("t-card-require-cap").textContent=x.cardRequireCap;$("t-qfrom").textContent=x.qFrom;$("t-qto").textContent=x.qTo;$("t-qpos").textContent=x.qPosition;$("t-qadd").textContent=x.qAdd;$("t-moretypes").textContent=x.moreTypes;$("t-qmap").textContent=x.qMap;$("t-qmap-cap").textContent=x.qMapCap;$("t-qrule").textContent=x.qRule;$("t-qrule-cap").textContent=x.qRuleCap;
 $("t-rdlg").textContent=x.rDlg;$("t-edlg").textContent=x.eDlg;$("t-adlg").textContent=x.armDlg;$("t-aval").textContent=x.armValue;$("t-apval").textContent=x.armValue;$("ap-title").textContent=x.subBond;$("ap-save").textContent=x.save;$("ap-discard").textContent=x.discard;$("ap-close").title=x.close;$("adel").textContent=x.armDelete;$("aapply").textContent=x.apply;$("t-rbody").textContent=x.rBody;$("t-rjson").textContent=x.rJson;$("t-r-require").textContent=x.rRequire;$("t-r-forbid").textContent=x.rForbid;$("radd").textContent=x.apply;
 $("t-addf").textContent=x.addf;$("t-params").innerHTML=x.params+' <code>charge=2, n=1</code>';$("t-tray").textContent=x.tray;
 $("t-addm").textContent=x.mapAdd;$("t-mdlg").textContent=x.mapDlg;$("t-mif").textContent=x.mapIf;$("t-mthen").textContent=x.mapThen;$("madd").textContent=x.mapAddBtn;
 $("t-make").textContent=x.make;$("t-okh").textContent=x.okh;$("t-edit").textContent=x.edit;
 $("t-fdlg").textContent=x.fdlg;$("t-fsheets").textContent=x.fsheets;$("t-fexpr").textContent=x.fexpr;
 $("t-ftext").textContent=x.fText;$("t-fblocks").textContent=x.fBlocks;$("t-fbuilt").textContent=x.fbuilt;
 const g=$("gate");g.options[0].text=lang==="ru"?"любая":"any";g.options[1].text=lang==="ru"?"рядом":"adjacent";g.options[2].text=lang==="ru"?"в пределах…":"within…";
 $("srcinfo").textContent=(lang==="ru"?"листов: ":"sheets: ")+SHEETS.length+" · "+x.hintDraw;
 renderQuickBuilder();
 render();}
$("lang").onclick=()=>{lang=lang==="ru"?"en":"ru";applyLang();};

// ---- keyboard ----
document.addEventListener("keydown",e=>{
 if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==="z"&&!e.shiftKey){if(!e.target.matches("input,textarea")){e.preventDefault();undoLast();}return;}
 if(e.target.matches("input,select,textarea"))return;
 const PAN=60;
 if(e.key==="Escape"){if(armDraft){closeArmPane(true);return;}sel=null;selBond=null;selArm=null;tray=[];updateTray();render();}
 else if((e.key==="Delete"||e.key==="Backspace")&&selBond!==null){bonds.splice(selBond,1);selBond=null;render();}
 else if(e.key==="Enter"&&(e.ctrlKey||e.metaKey)){$("submit").click();}
 else if(e.ctrlKey&&/^Arrow/.test(e.key)){e.preventDefault();          // Ctrl+Arrows = pan the viewport
   if(e.key==="ArrowLeft")view.tx+=PAN;else if(e.key==="ArrowRight")view.tx-=PAN;
   else if(e.key==="ArrowUp")view.ty+=PAN;else view.ty-=PAN;applyView();}
 else if((e.key==="ArrowUp"||e.key==="ArrowDown")&&sel){e.preventDefault();   // Arrows = nudge the picked node along its slot
   const cur=(sel in nodeY)?nodeY[sel]:(nodeXY(...JSON.parse(sel))||{y:PADY}).y;
   nodeY[sel]=clampY(cur+(e.key==="ArrowUp"?-ROWH/2:ROWH/2));render();}
 else if(e.key==="+"||e.key==="="){e.preventDefault();zoomCenter(1.2);}
 else if(e.key==="-"||e.key==="_"){e.preventDefault();zoomCenter(1/1.2);}
 else if(e.key==="0"){e.preventDefault();view={scale:1,tx:0,ty:0};applyView();}});

let toastT;function toast(m){const el=$("toast");el.textContent=m;el.classList.add("show");clearTimeout(toastT);toastT=setTimeout(()=>el.classList.remove("show"),1600);}
applyLang();
setTimeout(()=>{fitView();didAutoFit=true;},0);
window.addEventListener("resize",()=>{if(didAutoFit&&!drag&&!pan)fitView();});
</script></body></html>"""


# ----------------------------------- CLI ------------------------------------ #
def _argval(flag, default=None):
    a = sys.argv[1:]
    return a[a.index(flag) + 1] if flag in a and a.index(flag) + 1 < len(a) else default


def main():
    here = Path(__file__).resolve().parent
    sys.path.insert(0, str(here.parent))
    from graphspec import spec_sheets  # reuse the real-spec loader
    spec = _argval("--spec")
    if spec:
        import fwgen as fg
        sheets = spec_sheets(spec)
        loaded = fg.load_spec(spec)
        sidecar = {"version": 1, "params": loaded.params, "constraints": loaded.constraints}
        optional_sheets = {s.sheet for s in loaded.slots if "FW_Optional" in s.flags}
        out = Path(_argval("--out") or (here / "editor.html"))
        if "--serve" in sys.argv:
            import serve
            result = serve.serve_editor(sheets, sidecar, title=f"Bundle — {Path(spec).stem}",
                                        optional_sheets=optional_sheets)
            print("submitted sidecar:", json.dumps(result, ensure_ascii=False) if result else "(none / empty)")
            return
        p = emit_html(out, sheets, sidecar, title=f"Bundle — связи ({Path(spec).stem})",
                      optional_sheets=optional_sheets)
        print(f"=== unified constraint editor from REAL spec: {Path(spec).name} ===")
        print("  sheets:", {s: len(v) for s, v in sheets.items()})
        print(f"  editor → {p}\n  (open in Firefox; draw links; Submit / Download sidecar.json → bundle_run --sieve)")
        return

    # demo / self-test
    sheets = OrderedDict([("A", ["a1", "a2", "a3"]), ("B", ["b1", "b2"]), ("C", ["c1", "c2", "c3"])])
    sidecar = {"version": 1, "params": {"A": {"a1": {"charge": 2}}, "C": {"c1": {"charge": 3}}},
               "constraints": [
                   {"id": "ban", "polarity": "forbid", "sheets": ["A", "C"],
                    "pairs": [{"A": "a1", "C": "c1"}], "gate": {}},
                   {"id": "mm", "polarity": "forbid", "sheets": ["A", "C"],          # Many:Many
                    "sets": {"A": ["a2", "a3"], "C": ["c2", "c3"]}, "gate": {}},
                   {"id": "need", "polarity": "require", "sheets": ["B", "C"],
                    "pairs": [{"B": "b2", "C": "c3"}], "gate": {"adjacent": True}}]}
    # round-trip parity check (Python side)
    back = bonds_to_sidecar(sidecar_to_bonds(sidecar), sidecar["params"])
    assert len(back["constraints"]) == 3, back              # pairs(ban) + sets(mm) + pairs(need)
    assert any("sets" in c for c in back["constraints"]), back   # Many:Many survives round-trip
    out = emit_html(here / "editor_demo.html", sheets, sidecar)
    print("=== unified constraint editor — demo ===")
    print("  round-trip sidecar→bonds→sidecar: OK (pairs + Many:Many sets + require)")
    print(f"  editor → {out}\n  (forbid=red, require=green, Many:Many via «Группа», Submit)")


if __name__ == "__main__":
    main()
