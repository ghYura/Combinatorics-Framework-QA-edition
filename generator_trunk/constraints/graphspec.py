#!/usr/bin/env python3
r"""graphspec — Phase-2 "threads + graph-view" authoring for the constraint sidecar.

NOTE: superseded as a UI by the unified `editor.py` (forbid+require, gates, n-ary, round-trip,
Submit/auto-invoke). Kept as a tested headless core (graph<->sidecar) + standalone demo.

The graph generalises the bond-matrix to MANY sheets at once: nodes = value-cells grouped by
sheet, a "thread" (edge) between two value-nodes = a forbidden bond. CROSS-SHEET is first-class —
an edge just references two entity IDs `[sheet, value]`, never pixels (the principle from the
architecture). The graph compiles to the SAME sidecar `constraints/sieve.py` + `bundle_run --sieve`
consume, so the whole loop is:

    graph (draw threads)  →  sidecar.json  →  bundle_run --sieve   (Core → SIEVE → Reader → …)

Headless, tested CORE (graph ↔ sidecar round-trip, cross-sheet grouping, live impact via the real
sieve) + a self-contained, OFFLINE, dependency-free HTML editor (HTML node-divs + a transparent SVG
thread overlay — the two-layer design). The polished React Flow version lives in `react_flow/`
(same compile model). This file runs and is verified with zero build step.

  python3 graphspec.py        # demo: build a cross-sheet thread graph, impact, emit the editor
"""
from __future__ import annotations

import itertools
import json
import sys
from collections import OrderedDict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sieve as sv  # noqa: E402


def _nid(sheet, value):
    return json.dumps([sheet, value], separators=(",", ":"))


def _script_json(data: dict) -> str:
    """JSON for embedding inside a <script> raw-text element."""
    return (json.dumps(data, ensure_ascii=False)
            .replace("&", "\\u0026")
            .replace("<", "\\u003c")
            .replace(">", "\\u003e"))


class ConstraintGraph:
    """Nodes = (sheet, value); edges = forbid/require bonds (threads). Cross-sheet by construction."""

    def __init__(self, sheets):                              # sheets: {sheet: [values]} (ordered)
        self.sheets = OrderedDict((k, list(dict.fromkeys(v))) for k, v in sheets.items())
        self.edges = []                                      # {a:[s,v], b:[s,v], gate:{}, polarity}

    def add(self, a_sheet, a_val, b_sheet, b_val, gate=None, polarity="forbid"):
        self.edges.append({"a": [a_sheet, a_val], "b": [b_sheet, b_val],
                           "gate": gate or {}, "polarity": polarity})
        return self

    def to_sidecar(self, params=None) -> dict:
        """Group edges by (unordered sheet-pair, gate, polarity) → one constraint each."""
        groups = OrderedDict()
        for e in self.edges:
            sa, va = e["a"]
            sb, vb = e["b"]
            if sa == sb:
                continue                                     # a bond is between two different sheets
            ps = tuple(sorted((sa, sb)))
            gk = (ps, json.dumps(e["gate"], sort_keys=True), e["polarity"])
            groups.setdefault(gk, []).append({sa: va, sb: vb})
        cons = []
        for i, ((ps, gj, pol), pairs) in enumerate(groups.items()):
            cons.append({"id": f"bond{i}_{ps[0]}_{ps[1]}", "polarity": pol, "sheets": list(ps),
                         "pairs": pairs, "gate": json.loads(gj),
                         "desc": f"{len(pairs)} {pol} {ps[0]}x{ps[1]} bond(s)"})
        return {"version": 1, "params": params or {}, "constraints": cons}

    @classmethod
    def from_sidecar(cls, sidecar, sheets):
        g = cls(sheets)
        for c in sidecar.get("constraints", []):
            sh = c.get("sheets", [])
            if len(sh) != 2:
                continue
            sa, sb = sh
            for e in c.get("pairs", []):
                if sa in e and sb in e:
                    g.add(sa, e[sa], sb, e[sb], gate=c.get("gate", {}), polarity=c.get("polarity", "forbid"))
        return g

    def edge_keys(self) -> set:
        """Canonical edge set (for round-trip comparison), independent of a/b order."""
        out = set()
        for e in self.edges:
            out.add(frozenset((tuple(e["a"]), tuple(e["b"]))))
        return out

    def impact(self, product=None) -> dict:
        rows = product or [
            [{"sheet": s, "value": v, "pos": i} for i, (s, v) in enumerate(combo)]
            for combo in itertools.product(*[[(s, v) for v in vs] for s, vs in self.sheets.items()])]
        return sv.sieve(rows, self.to_sidecar())

    def emit_html(self, path, title=None) -> Path:
        full = 1
        for vs in self.sheets.values():
            full *= max(1, len(vs))
        data = {"sheets": [[s, vs] for s, vs in self.sheets.items()],
                "edges": [[_nid(*e["a"]), _nid(*e["b"])] for e in self.edges
                          if e["a"][0] != e["b"][0]],
                "full": full}
        html = _HTML.replace("/*__DATA__*/null", _script_json(data)) \
                    .replace("__TITLE__", title or "Constraint graph — threads & cross-sheet bonds")
        p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(html, encoding="utf-8")
        return p


_HTML = r"""<!doctype html><html lang="en"><meta charset="utf-8"><title>__TITLE__</title>
<style>
 body{font:14px/1.5 system-ui,sans-serif;margin:20px;color:#1a1a1a;background:#fafafa}
 h1{font-size:18px} .sub{color:#666;max-width:780px}
 #stage{position:relative;border:1px solid #ddd;background:#fff;border-radius:8px;margin:12px 0;overflow:auto}
 svg{position:absolute;left:0;top:0;pointer-events:none}
 .node{position:absolute;transform:translate(-50%,-50%);padding:5px 9px;border:1px solid #888;
   border-radius:14px;background:#eef3ff;cursor:pointer;white-space:nowrap;font-size:13px;user-select:none}
 .node:hover{outline:2px solid #69f} .node.sel{background:#ffe9a8;border-color:#c90}
 .col{position:absolute;top:6px;transform:translateX(-50%);color:#555;font-weight:600}
 line.edge{stroke:#d33;stroke-width:2.5;pointer-events:stroke;cursor:pointer}
 line.edge:hover{stroke:#f66;stroke-width:4}
 .panel{margin:10px 0;padding:10px 12px;background:#fff;border:1px solid #ddd;border-radius:6px;max-width:780px}
 .rule{color:#a00} button{font:14px system-ui;padding:7px 12px;cursor:pointer} code{background:#f0f0f0;padding:1px 4px}
</style>
<h1>__TITLE__</h1>
<div class="sub">Click one value-node, then another in a <b>different sheet</b>, to draw a forbidden
<b>thread</b> (red). Click a thread to remove it. Cross-sheet bonds are first-class. Then
<b>Download sidecar.json</b> → <code>bundle_run.py &lt;spec&gt; --sieve</code>.</div>
<div id="stage"></div>
<div class="panel"><b>Impact (co-occurrence):</b> <span id="impact"></span></div>
<div class="panel"><b>Threads (plain language):</b><div id="rules"></div></div>
<button id="dl">Download sidecar.json</button>
<script>
const D=/*__DATA__*/null;
const COLW=190, ROWH=44, PADX=110, PADY=42;
const E=new Set(D.edges.map(e=>JSON.stringify([e[0],e[1]].sort())));   // canonical thread set
let sel=null;
const stage=document.getElementById("stage");
function pos(si,vi){return {x:PADX+si*COLW, y:PADY+vi*ROWH};}
function nodeIndex(){const m={};D.sheets.forEach((sv,si)=>sv[1].forEach((v,vi)=>{m[JSON.stringify([sv[0],v])]={si,vi};}));return m;}
const NI=nodeIndex();
function esc(s){return String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));}
function attr(s){return esc(s).replace(/'/g,"&#39;");}
function render(){
 const rows=Math.max(...D.sheets.map(s=>s[1].length));
 const W=PADX+ (D.sheets.length-1)*COLW + PADX, H=PADY+rows*ROWH+10;
 let svg="<svg width='"+W+"' height='"+H+"'>";
 E.forEach(k=>{const[n1,n2]=JSON.parse(k);const a=NI[n1],b=NI[n2];if(!a||!b)return;
   const p=pos(a.si,a.vi),q=pos(b.si,b.vi);
   svg+="<line class='edge' data-k='"+attr(k)+"' x1='"+p.x+"' y1='"+p.y+"' x2='"+q.x+"' y2='"+q.y+"'></line>";});
 svg+="</svg>";
 let nodes="";
 D.sheets.forEach((s,si)=>{nodes+="<div class='col' style='left:"+pos(si,0).x+"px'>"+esc(s[0])+"</div>";
   s[1].forEach((v,vi)=>{const id=JSON.stringify([s[0],v]);const p=pos(si,vi);
     nodes+="<div class='node"+(sel===id?" sel":"")+"' style='left:"+p.x+"px;top:"+p.y+"px' data-id='"+attr(id)+"'>"+esc(v)+"</div>";});});
 stage.style.width=W+"px"; stage.style.height=H+"px"; stage.innerHTML=svg+nodes;
 stage.querySelectorAll(".node").forEach(n=>n.onclick=()=>clickNode(n.dataset.id));
 stage.querySelectorAll("line.edge").forEach(l=>l.onclick=()=>{E.delete(l.dataset.k);sel=null;render();});
 updatePanels();
}
function clickNode(id){
 if(sel===null){sel=id;}
 else if(sel===id){sel=null;}
 else{const a=JSON.parse(sel),b=JSON.parse(id);
   if(a[0]!==b[0]){E.add(JSON.stringify([sel,id].sort()));} sel=null;}
 render();
}
function violates(combo){ // combo: map sheet->value
 for(const k of E){const[n1,n2]=JSON.parse(k);const[s1,v1]=JSON.parse(n1),[s2,v2]=JSON.parse(n2);
   if(combo[s1]===v1 && combo[s2]===v2) return true;} return false;}
function impact(){ // exact via cartesian if small, else per-thread estimate
 const sizes=D.sheets.map(s=>s[1].length), prod=sizes.reduce((a,b)=>a*b,1);
 if(prod<=50000){let rem=0;const idx=D.sheets.map(()=>0);
   for(let n=0;n<prod;n++){const combo={};D.sheets.forEach((s,i)=>combo[s[0]]=s[1][idx[i]]);
     if(violates(combo))rem++; for(let i=D.sheets.length-1;i>=0;i--){if(++idx[i]<sizes[i])break;idx[i]=0;}}
   return {exact:true,removed:rem,full:prod};}
 return {exact:false,removed:null,full:D.full};
}
function updatePanels(){
 const im=impact();
 document.getElementById("impact").textContent = im.exact
   ? (E.size+" thread(s) → removes "+im.removed+" of "+im.full+" combinations ("+(im.full-im.removed)+" kept).")
   : (E.size+" thread(s); full product "+im.full+" too large to count live — run --sieve for the exact figure.");
 document.getElementById("rules").innerHTML=[...E].sort().map(k=>{const[n1,n2]=JSON.parse(k);
   const[s1,v1]=JSON.parse(n1),[s2,v2]=JSON.parse(n2);
   return "<div class='rule'>x  "+esc(s1)+":"+esc(v1)+"  +  "+esc(s2)+":"+esc(v2)+"</div>";}).join("")
   ||"<i>no threads yet — click two nodes in different sheets</i>";
}
function sidecar(){
 const groups={};
 E.forEach(k=>{const[n1,n2]=JSON.parse(k);const[s1,v1]=JSON.parse(n1),[s2,v2]=JSON.parse(n2);
   const ps=[s1,s2].sort(),gk=ps.join("");(groups[gk]=groups[gk]||{sheets:ps,pairs:[]});
   const o={};o[s1]=v1;o[s2]=v2;groups[gk].pairs.push(o);});
 const cons=Object.values(groups).map((g,i)=>({id:"bond"+i+"_"+g.sheets[0]+"_"+g.sheets[1],
   polarity:"forbid",sheets:g.sheets,pairs:g.pairs,gate:{},
   desc:g.pairs.length+" forbid "+g.sheets[0]+"x"+g.sheets[1]+" bond(s)"}));
 return {version:1,params:{},constraints:cons};
}
document.getElementById("dl").onclick=()=>{const b=new Blob([JSON.stringify(sidecar(),null,2)],{type:"application/json"});
 const u=URL.createObjectURL(b),a=document.createElement("a");a.href=u;a.download="sidecar.json";a.click();URL.revokeObjectURL(u);};
render();
</script></html>"""


# --------------------- load sheets/values from a REAL fwgen spec ------------- #
def spec_sheets(spec_path, min_values=2):
    """Return {sheet: [values]} from a real fwgen spec (TOML/JSON/YAML). Values are
    whitespace-stripped to match the sieve's decoded form (so the authored value in the editor
    == what --sieve sees). Slots with < min_values are skipped (HEAD/TAIL harness slots aren't
    useful dimensions for bonds); pass min_values=1 to include them."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import fwgen as fg
    spec = fg.load_spec(spec_path)
    out = OrderedDict()
    for s in spec.slots:
        vals = [str(v).strip() for v in s.values]
        if len(vals) >= min_values:
            out[s.sheet] = vals
    return out


def emit_sheets_json(spec_path, out_path, min_values=2):
    """Write the spec's sheets+values as `[[sheet,[values]]...]` JSON — the file the React Flow
    and Blockly apps fetch at runtime to populate their nodes / dropdowns from a real spec."""
    sheets = spec_sheets(spec_path, min_values)
    p = Path(out_path); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps([[s, v] for s, v in sheets.items()], ensure_ascii=False, indent=2),
                 encoding="utf-8")
    return p


def _argval(flag, default=None):
    a = sys.argv[1:]
    return a[a.index(flag) + 1] if flag in a and a.index(flag) + 1 < len(a) else default


# ----------------------------------- demo ----------------------------------- #
def main():
    args = sys.argv[1:]
    skip = {args.index(f) + 1 for f in ("--spec", "--sheets-json", "--out")
            if f in args and args.index(f) + 1 < len(args)}
    positional = [a for i, a in enumerate(args) if not a.startswith("--") and i not in skip]
    spec, sj = _argval("--spec"), _argval("--sheets-json")

    if spec:  # ---- load sheets/values from a REAL spec ----
        sheets = spec_sheets(spec)
        out = Path(_argval("--out") or (positional[0] if positional else
                   str(Path(__file__).resolve().parent / "graph_editor.html")))
        print(f"=== constraint graph from REAL spec: {Path(spec).name} ===\n")
        print("  sheets loaded:", {s: len(v) for s, v in sheets.items()})
        g = ConstraintGraph(sheets)
        if sj:
            emit_sheets_json(spec, sj)
            print(f"  sheets.json → {sj}")
        p = g.emit_html(out, title=f"Constraint graph — {Path(spec).stem}")
        print(f"  interactive editor → {p}")
        print("  (real spec sheets; thread nodes across sheets → Download sidecar.json → bundle_run --sieve)")
        return

    # ---- demo / self-test (no --spec) ----
    out = Path(positional[0] if positional else
               str(Path(__file__).resolve().parent / "graph_editor_demo.html"))
    print("=== constraint graph — threads + cross-sheet bonds (Phase-2) ===\n")
    g = ConstraintGraph(OrderedDict([("A", ["a1", "a2"]), ("B", ["b1", "b2"]), ("C", ["c1", "c2", "c3"])]))
    g.add("A", "a1", "C", "c1").add("B", "b2", "C", "c3")   # two CROSS-SHEET threads
    sc = g.to_sidecar()
    print(f"threads: {len(g.edges)}  →  {len(sc['constraints'])} constraint(s) (grouped by sheet-pair):")
    for c in sc["constraints"]:
        print("   ", sv.describe(c), " sheets=", c["sheets"], "pairs=", c["pairs"])
    rep = g.impact()
    print(f"\nimpact over the full {rep['total']}-combination product: kept {rep['kept']}, removed {rep['removed']}")
    print("  removed:", [r for r, _ in rep["removed_examples"]])

    back = ConstraintGraph.from_sidecar(sc, g.sheets)        # round-trip
    assert back.edge_keys() == g.edge_keys(), "round-trip mismatch"
    print("\nround-trip graph→sidecar→graph: OK")

    p = g.emit_html(out)
    print(f"interactive editor → {p}")
    print("  (open in a browser; click two nodes in different sheets to thread; Download sidecar.json → --sieve)")


if __name__ == "__main__":
    main()
