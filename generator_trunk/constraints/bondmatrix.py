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

r"""bondmatrix — Phase-2 authoring UI for the constraint sidecar: the chemistry-style
"valence / bond matrix". Rows = values of sheet A, columns = sheet B; click a cell to FORBID
that value-pair (the "bond").

NOTE: superseded as a UI by the unified `editor.py` (forbid+require, gates, n-ary, round-trip,
Submit/auto-invoke). Kept as a tested headless core (matrix<->sidecar) + standalone demo. It compiles to the SAME sidecar that constraints/sieve.py
enforces, so the whole loop is:

    bond-matrix  →  sidecar.json  →  bundle_run --sieve   (Core → SIEVE → Reader → …)

Headless, tested CORE (model + compile + round-trip + live impact via sieve.sieve) PLUS a
self-contained interactive HTML editor (`emit_html`), mirroring the repo's `fwgen preview --html`
pattern. The cheapest, most intuitive authoring surface — no code — with always-on plain language
and a live "removes N of M" impact. (Threads / Blockly-`when` predicates are the later tiers; this
matrix authors the enumerated-pairs level, which is the common case.)

  python3 bondmatrix.py        # demo: build a matrix, show ASCII + impact, emit the HTML editor
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sieve as sv  # noqa: E402  (the same evaluator the sieve uses → impact is exact)

_SEP = json.dumps([0, 0], separators=(",", ":"))  # marker only; pair keys use compact JSON


def _script_json(data: dict) -> str:
    """JSON for embedding inside a <script> raw-text element."""
    return (json.dumps(data, ensure_ascii=False)
            .replace("&", "\\u0026")
            .replace("<", "\\u003c")
            .replace(">", "\\u003e"))


def _pkey(a: str, b: str) -> str:
    return json.dumps([a, b], separators=(",", ":"))   # matches JS JSON.stringify([a,b])


class BondMatrix:
    """A forbid/allow matrix between two sheets' values. Default = all allowed; mark forbidden cells."""

    def __init__(self, sheet_a, values_a, sheet_b, values_b, forbidden=None):
        self.a, self.va = sheet_a, list(dict.fromkeys(values_a))
        self.b, self.vb = sheet_b, list(dict.fromkeys(values_b))
        self.forbidden = set(forbidden or [])               # {(a_value, b_value), ...}

    def toggle(self, a, b):
        k = (a, b)
        self.forbidden.discard(k) if k in self.forbidden else self.forbidden.add(k)
        return self

    def forbid(self, a, b):
        self.forbidden.add((a, b)); return self

    # --- compile to / from the sidecar (the artifact sieve.py + bundle_run --sieve consume) ---
    def to_constraint(self, cid=None) -> dict:
        return {"id": cid or f"bond_{self.a}_{self.b}", "polarity": "forbid",
                "sheets": [self.a, self.b],
                "pairs": [{self.a: a, self.b: b} for (a, b) in sorted(self.forbidden)],
                "gate": {},
                "desc": f"{len(self.forbidden)} forbidden {self.a}x{self.b} value-pair(s)"}

    def to_sidecar(self, params=None) -> dict:
        return {"version": 1, "params": params or {},
                "constraints": [self.to_constraint()] if self.forbidden else []}

    @classmethod
    def from_sidecar(cls, sidecar, sheet_a, values_a, sheet_b, values_b):
        forb = set()
        for c in sidecar.get("constraints", []):
            if set(c.get("sheets", [])) == {sheet_a, sheet_b}:
                for e in c.get("pairs", []):
                    if sheet_a in e and sheet_b in e:
                        forb.add((e[sheet_a], e[sheet_b]))
        return cls(sheet_a, values_a, sheet_b, values_b, forb)

    # --- views ---
    def ascii(self) -> str:
        w = max([len(str(v)) for v in self.va] + [len(self.a)])
        cw = max([len(str(v)) for v in self.vb] + [1])
        out = [f"{self.a} (rows) \\ {self.b} (cols)   [x = forbidden bond]",
               "".ljust(w + 2) + "  ".join(str(v).center(cw) for v in self.vb)]
        for a in self.va:
            cells = ["x".center(cw) if (a, b) in self.forbidden else ".".center(cw) for b in self.vb]
            out.append(str(a).ljust(w) + "  " + "  ".join(cells))
        return "\n".join(out)

    def impact(self, product=None) -> dict:
        """Live preview via the real sieve. `product` = list of ordered rows; default = the A×B grid."""
        rows = product or [[{"sheet": self.a, "value": a, "pos": 0},
                            {"sheet": self.b, "value": b, "pos": 1}]
                           for a in self.va for b in self.vb]
        return sv.sieve(rows, self.to_sidecar())

    # --- the interactive HTML editor (self-contained, no deps; downloads sidecar.json) ---
    def emit_html(self, path, full_product=None, title=None) -> Path:
        data = {"a": self.a, "b": self.b, "va": self.va, "vb": self.vb,
                "forbidden": [_pkey(a, b) for (a, b) in sorted(self.forbidden)],
                "full": full_product or (len(self.va) * len(self.vb))}
        html = _HTML.replace("/*__DATA__*/null", _script_json(data)) \
                    .replace("__TITLE__", title or f"Bond matrix: {self.a} x {self.b}")
        p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(html, encoding="utf-8")
        return p


_HTML = r"""<!doctype html><html lang="en"><meta charset="utf-8"><title>__TITLE__</title>
<style>
 body{font:14px/1.5 system-ui,sans-serif;margin:24px;color:#1a1a1a;background:#fafafa}
 h1{font-size:18px} .sub{color:#666}
 table{border-collapse:collapse;margin:14px 0}
 th,td{border:1px solid #ccc;padding:7px 10px;text-align:center}
 th{background:#eee} td.cell{cursor:pointer;min-width:34px;user-select:none}
 td.allow{background:#e9f7ee} td.forbid{background:#fde2e2;color:#a00;font-weight:700}
 td.cell:hover{outline:2px solid #888}
 .panel{margin:12px 0;padding:10px 12px;background:#fff;border:1px solid #ddd;border-radius:6px}
 .rule{color:#a00} button{font:14px system-ui;padding:7px 12px;cursor:pointer}
 code{background:#f0f0f0;padding:1px 4px;border-radius:3px}
</style>
<h1>__TITLE__</h1>
<div class="sub">Click a cell to toggle a <b>forbidden bond</b> (red) between a row value and a column value.
Then <b>Download sidecar.json</b> and run <code>bundle_run.py &lt;spec&gt; --sieve</code>.</div>
<div id="grid"></div>
<div class="panel"><b>Impact (co-occurrence):</b> <span id="impact"></span></div>
<div class="panel"><b>Rules (plain language):</b><div id="rules"></div></div>
<button id="dl">Download sidecar.json</button>
<script>
const D=/*__DATA__*/null;
const F=new Set(D.forbidden);
const key=(a,b)=>JSON.stringify([a,b]);
function esc(s){return String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));}
function attr(s){return esc(s).replace(/'/g,"&#39;");}
function render(){
 let h="<table><tr><th>"+esc(D.a)+" \\ "+esc(D.b)+"</th>"+D.vb.map(v=>"<th>"+esc(v)+"</th>").join("")+"</tr>";
 for(const a of D.va){h+="<tr><th>"+esc(a)+"</th>";
  for(const b of D.vb){const f=F.has(key(a,b));
   h+="<td class='cell "+(f?"forbid":"allow")+"' data-a='"+attr(a)+"' data-b='"+attr(b)+"'>"+(f?"x":".")+"</td>";}
  h+="</tr>";}
 h+="</table>"; document.getElementById("grid").innerHTML=h;
 document.querySelectorAll("td.cell").forEach(td=>td.onclick=()=>{
   const k=key(td.dataset.a,td.dataset.b); F.has(k)?F.delete(k):F.add(k); render();});
 const perCell=D.full/(D.va.length*D.vb.length), removed=Math.round(F.size*perCell);
 document.getElementById("impact").textContent=
   F.size+" forbidden pair(s) -> removes "+removed+" of "+D.full+" combinations ("+(D.full-removed)+" kept).";
 document.getElementById("rules").innerHTML=[...F].sort().map(k=>{const p=JSON.parse(k);
   return "<div class='rule'>x  "+esc(D.a)+":"+esc(p[0])+"  +  "+esc(D.b)+":"+esc(p[1])+"</div>";}).join("")
   ||"<i>none yet - all bonds allowed</i>";
}
function sidecar(){const pairs=[...F].sort().map(k=>{const p=JSON.parse(k);const o={};o[D.a]=p[0];o[D.b]=p[1];return o;});
 return {version:1,params:{},constraints:pairs.length?[{id:"bond_"+D.a+"_"+D.b,polarity:"forbid",
  sheets:[D.a,D.b],pairs:pairs,gate:{},desc:pairs.length+" forbidden "+D.a+"x"+D.b+" value-pair(s)"}]:[]};}
document.getElementById("dl").onclick=()=>{const blob=new Blob([JSON.stringify(sidecar(),null,2)],{type:"application/json"});
 const u=URL.createObjectURL(blob),a=document.createElement("a");a.href=u;a.download="sidecar.json";a.click();URL.revokeObjectURL(u);};
render();
</script></html>"""


# ----------------------------------- demo ----------------------------------- #
def main():
    from graphspec import spec_sheets, _argval  # reuse the real-spec loader
    args = sys.argv[1:]
    skip = {args.index(f) + 1 for f in ("--spec", "--a", "--b", "--out")
            if f in args and args.index(f) + 1 < len(args)}
    positional = [a for i, a in enumerate(args) if not a.startswith("--") and i not in skip]
    spec = _argval("--spec")

    if spec:  # ---- load sheets/values from a REAL spec ----
        sheets = spec_sheets(spec)
        names = list(sheets.keys())
        a = _argval("--a") or (names[0] if names else None)
        b = _argval("--b") or (names[1] if len(names) > 1 else None)
        if a not in sheets or b not in sheets or a == b:
            raise SystemExit(f"--a/--b must be two distinct sheets of {Path(spec).name}: {names}")
        out = Path(_argval("--out") or (positional[0] if positional else
                   str(Path(__file__).resolve().parent / "bondmatrix.html")))
        full = 1
        for v in sheets.values():
            full *= max(1, len(v))
        print(f"=== bond matrix from REAL spec: {Path(spec).name}  ({a} x {b}) ===\n")
        print("  sheets:", {s: len(v) for s, v in sheets.items()})
        m = BondMatrix(a, sheets[a], b, sheets[b])
        p = m.emit_html(out, full_product=full, title=f"Bond matrix: {a} x {b} ({Path(spec).stem})")
        print(f"  interactive editor → {p}")
        print("  (real spec values; click cells to forbid bonds → Download sidecar.json → bundle_run --sieve)")
        return

    # ---- demo / self-test (no --spec) ----
    out = Path(positional[0] if positional else
               str(Path(__file__).resolve().parent / "bondmatrix_demo.html"))
    print("=== bond matrix - Phase-2 authoring UI (chemistry valence grid) ===\n")
    m = BondMatrix("A", ["a11", "a12", "a13"], "C", ["c11", "c12", "c13"])
    m.forbid("a11", "c11").forbid("a12", "c13")            # two forbidden bonds
    print(m.ascii())
    rep = m.impact()
    print(f"\nimpact over the {rep['total']} A x C pairs: kept {rep['kept']}, removed {rep['removed']}")
    print("  removed:", [r for r, _ in rep["removed_examples"]])
    print("  rule:", sv.describe(m.to_constraint()))

    # round-trip: matrix -> sidecar -> matrix
    sc = m.to_sidecar()
    back = BondMatrix.from_sidecar(sc, "A", ["a11", "a12", "a13"], "C", ["c11", "c12", "c13"])
    assert back.forbidden == m.forbidden, "round-trip mismatch"
    print("\nround-trip matrix->sidecar->matrix: OK")

    p = m.emit_html(out, full_product=9 * 4)               # pretend the full spec product is 36
    print(f"interactive editor -> {p}")
    print("  (open in a browser; click cells; Download sidecar.json -> bundle_run --sieve)")


if __name__ == "__main__":
    main()
