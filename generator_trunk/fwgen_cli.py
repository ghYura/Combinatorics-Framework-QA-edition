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

r"""fwgen CLI — generate Core input-test workbooks from external specs.

Strategies (exhaustive by default; reduction is always opt-in):

  full       compact 'cartesian-leaves' workbook; the CORE expands the product.
             Small file, scales to any product size. (default)
  ablation   k=1 directed ablation: baseline + every single-slot deviation,
             pre-enumerated into one CANDIDATE sheet.
  reduce     full product, then OPT-IN N-wise covering-array reduction
             (--n 2 = pairwise, --optimal for minimum set-cover).
  auto       pick the MOST thorough coverage that fits --budget: full if it
             fits, else the tightest N-wise that does. 'Self-limit with the
             exponential wall in mind.'

Chunking & parallelism (ported from v25): materialized output (ablation/reduce/
auto, or 'full --materialize') can be split into many workbooks and built across
processes — openpyxl is CPU-bound, so processes beat the GIL.
  --materialize     pre-expand the product into rows (instead of compact)
  --chunk-rows N    split rows into workbooks of <= N rows (chunk_000.xlsx, ...)
  --workers K       build chunks in K parallel processes

Examples:
  python fwgen_cli.py list   --specs specs
  python fwgen_cli.py gen    --specs specs --out out --strategy full --json
  python fwgen_cli.py gen    --specs specs --out out --strategy reduce --n 2 --optimal
  python fwgen_cli.py gen    --specs specs --out out --strategy auto --budget 50
  python fwgen_cli.py gen    --specs specs --out out --strategy full --materialize \
                             --chunk-rows 50 --workers 4
  python fwgen_cli.py validate --out out
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import fwgen as fg
import fwseq_graph as fwg


# --------------------------------------------------------------------------
# strategy -> (rows or compact) for one spec
# --------------------------------------------------------------------------

def _ablation_rows(spec: fg.Spec) -> list[str]:
    rows = [fg.assemble(spec, spec.baseline, prefix="ablation=baseline")]
    for i, slot in enumerate(spec.slots):
        for v in slot.values[1:]:
            combo = list(spec.baseline)
            combo[i] = v
            rows.append(fg.assemble(spec, combo, prefix=f"ablation={slot.sheet}:{v}"))
    return rows


def generate_one(spec: fg.Spec, out: Path, strategy: str, n: int, optimal: bool,
                 budget: int, fw_info: str, clone_path: str | None = None,
                 emit_json: bool = False, materialize: bool = False,
                 chunk_rows: int = 0, workers: int = 1, autofit: float = 0.0) -> dict:
    """Resolve a strategy to either a compact workbook or a list of materialized
    rows, then write (chunked + parallel for the materialized case)."""
    out.mkdir(parents=True, exist_ok=True)
    info = {"spec": spec.name, "strategy": strategy, "full_combos": spec.combos}
    rows: list[str] | None = None        # None => compact (Core expands)
    base = spec.name
    mode = ""

    if strategy == "full":
        if materialize:
            rows = [fg.assemble(spec, c) for c in fg.cartesian(spec)]
            mode = "materialized full product"
        else:
            mode = "compact (Core expands)"
    elif strategy == "ablation":
        rows = _ablation_rows(spec)
        base = f"{spec.name}_k1_ablation"
        mode = f"materialized (baseline + {len(rows)-1} single deviations)"
    elif strategy == "reduce":
        if n <= 0:
            raise SystemExit("reduce strategy needs --n >= 1")
        rows = [fg.assemble(spec, c) for c in fg.reduce_combos(list(fg.cartesian(spec)), n, optimal)]
        base = f"{spec.name}_{n}wise{'_opt' if optimal else ''}"
        mode = f"materialized ({n}-wise{' optimal' if optimal else ' greedy'})"
    elif strategy == "auto":
        chosen_n, combos = fg.pick_n_for_budget(spec, budget, optimal)
        if chosen_n == 0 and not materialize:
            mode = f"compact full (≤ budget {budget})"
        elif chosen_n == 0:
            rows = [fg.assemble(spec, c) for c in fg.cartesian(spec)]
            mode = f"materialized full (≤ budget {budget})"
        else:
            rows = [fg.assemble(spec, c) for c in combos]
            base = f"{spec.name}_auto{chosen_n}wise"
            mode = f"materialized {chosen_n}-wise (full {spec.combos} > budget {budget})"
    else:
        raise SystemExit(f"unknown strategy {strategy!r}")

    if rows is None:                                   # compact: one small workbook
        path = out / f"{base}.xlsx"
        fg.build_compact(spec, fw_info, clone_path, autofit).save(path)
        if emit_json:
            fg.write_json_sibling(path)
        paths = [str(path)]
        info["rows"] = spec.combos
    else:                                              # materialized: chunk + parallel
        paths = fg.write_chunked(spec, rows, out, base, chunk_rows,
                                 fw_info, clone_path, workers, emit_json, autofit=autofit)
        info["rows"] = len(rows)

    info["chunks"] = len(paths)
    info["base"] = base
    info["mode"] = mode + (f" → {len(paths)} chunks" if len(paths) > 1 else "")
    errs: list[str] = []
    for p in paths:
        errs += fg.validate_workbook(p)
    info["valid"] = errs or "OK"
    info["paths"] = paths
    # STEP 36: persist the normalized (alias-compiled) advanced spec next to the
    # workbook so the run artifacts always carry the inspectable expert form.
    norm_path = out / f"{spec.name}.normalized.json"
    fg.emit_normalized_spec(spec, norm_path)
    info["normalized_spec"] = str(norm_path)
    return info


# --------------------------------------------------------------------------
# subcommands
# --------------------------------------------------------------------------

def cmd_list(a):
    for spec in fg.load_specs_dir(a.specs):
        slotdesc = ", ".join(f"{s.sheet}({len(s.values)})" + ("" if s.verb == fg.DEFAULT_VERB else f"·{s.verb}")
                             for s in spec.slots)
        goals = spec.goals_property() or "(none)"
        est = fg.estimate_core_combos(spec)
        warn = "   ⚠ LARGE — use --strategy reduce or smaller value sets" if est > 1_000_000 else ""
        print(f"\n{spec.name}: {spec.title}")
        print(f"  slots: {slotdesc}" + (f"  +{len(spec.seq_extra)} extra row(s)" if spec.seq_extra else ""))
        print(f"  est. Core fw_final rows ≈ {est:,}{warn}")
        print(f"  goals (auto-inferred dir): {goals}")
        print(f"  custom_vars: {len(spec.custom_vars)}  args: {len(spec.args)}")
        rep = fg.handshake_report(spec)
        print(f"  results table: {rep['n_columns']} cols ({rep['n_combos']} combos) → {rep['mode']} mode; fwVar.shift={rep['fwvar_shift']}")
        for w in rep["warnings"]:
            print(f"  ⚠ handshake: {w}")


def cmd_gen(a):
    specs = fg.load_specs_dir(a.specs)
    out = Path(a.out)
    fw_info = a.fw_info
    clone_path = None
    if fw_info.startswith("clone:"):
        fw_info, clone_path = "clone", fw_info.split(":", 1)[1]
    results = []
    for spec in specs:
        r = generate_one(spec, out, a.strategy, a.n, a.optimal, a.budget,
                          fw_info, clone_path, a.json,
                          materialize=a.materialize, chunk_rows=a.chunk_rows,
                          workers=a.workers, autofit=a.autofit)
        results.append(r)
        status = "OK" if r["valid"] == "OK" else f"INVALID: {r['valid']}"
        print(f"{r['base']:<40} rows={r['rows']:<6} chunks={r['chunks']:<4} {r['mode']:<46} {status}")
    _write_readme(out, specs, results, a)
    bad = [r for r in results if r["valid"] != "OK"]
    print(f"\n{len(results)} workbooks → {out}    {'ALL VALID' if not bad else f'{len(bad)} INVALID'}")
    return 1 if bad else 0


def cmd_graph(a):
    """STEP 37: emit the FW_Seq dependency graph (JSON and/or DOT) for each spec,
    and report any structural issues (errors are also a non-zero exit)."""
    import json as _json
    rc = 0
    out = Path(a.out) if a.out else None
    if out:
        out.mkdir(parents=True, exist_ok=True)
    for spec in fg.load_specs_dir(a.specs):
        g = fwg.build_graph(spec)
        issues = g.validate()
        errs = [i for i in issues if i.level == fwg.ERROR]
        print(f"\n{spec.name}: {len(g.nodes)} nodes, {len(g.edges)} edges   {g.graph_hash()}")
        for i in issues:
            print(f"  {'✗' if i.level == fwg.ERROR else '⚠'} [{i.code}] {i.message}")
        if a.dot:
            if out:
                (out / f"{spec.name}.dot").write_text(g.to_dot(), encoding="utf-8")
            else:
                print(g.to_dot())
        else:
            doc = _json.dumps(g.to_json(), indent=2, ensure_ascii=False)
            if out:
                (out / f"{spec.name}.graph.json").write_text(doc, encoding="utf-8")
            else:
                print(doc)
        if errs:
            rc = 1
    return rc


def cmd_validate(a):
    out = Path(a.out)
    bad = 0
    for p in sorted(out.glob("*.xlsx")):
        errs = fg.validate_workbook(p)
        print(f"{p.name:<46} {'OK' if not errs else '; '.join(errs)}")
        bad += bool(errs)
    print(f"\n{'ALL VALID' if not bad else f'{bad} INVALID'}")
    return 1 if bad else 0


def cmd_json(a):
    out = fg.xlsx_dir_to_json_dir(a.indir, a.out or None, workers=a.workers)
    n = len(list(Path(out).glob("*.json")))
    print(f"{n} JSON files → {out}")
    return 0


def cmd_coverage(a):
    """Emit one tiny ISOLATED workbook per Core verb + a 10+-row mixed-verb interop
    workbook — all with bounded inner product (no cartesian explosion)."""
    man = fg.build_verb_coverage(a.out, fw_info=a.fw_info, autofit=a.autofit, emit_json=a.json)
    bad = 0
    for m in man:
        status = "OK" if m["valid"] == "OK" else f"INVALID: {m['valid']}"
        print(f"{m['name']:<22} FW_Seq_rows={m['fw_seq_rows']:<3} est_core_rows={m['est_core_rows']:<6} "
              f"verbs={m['verbs']:<56} {status}")
        bad += m["valid"] != "OK"
    biggest = max((m["est_core_rows"] for m in man), default=0)
    print(f"\n{len(man)} coverage workbooks → {a.out}   "
          f"(largest inner product ≈ {biggest} rows — bounded, no explosion)   "
          f"{'ALL VALID' if not bad else f'{bad} INVALID'}")
    return 1 if bad else 0


def cmd_handshake(a):
    """Emit a ready-to-run Reader→Executor handshake (resultsDbURL.properties /
    insert.sql / args / fwVar.shift / runmefirstonce.first) for one or all specs —
    fixing, at GENERATION time, the bits the Reader emits wrong (empty fwVar.shift)
    and validating the verdict code against the predicted #combos columns."""
    specs = fg.load_specs_dir(a.specs)
    if a.spec:
        specs = [s for s in specs if s.name == a.spec]
        if not specs:
            raise SystemExit(f"spec '{a.spec}' not found in {a.specs}")
    for spec in specs:
        db = a.db or spec.name
        table = a.table or db
        url = a.db_url or (f"jdbc:postgresql://{a.host}:{a.port}/{db}"
                           f"?user={a.user}&password={a.password}")
        out = Path(a.out) / spec.name
        rep = fg.emit_handshake(spec, out, db_url=url, table_name=table, fwvar_shift=a.shift)
        print(f"\n{spec.name}: handshake → {rep['out_dir']}")
        print(f"  Results table: {rep['n_columns']} cols ({rep['n_combos']} combos) → "
              f"{rep['mode']} mode; fwVar.shift={rep['fwvar_shift']}")
        for w in rep["warnings"]:
            print(f"  ⚠ {w}")
        print(f"  wrote: {', '.join(rep['written'])}")
        print(f"  run Executor with:  -dirResultsDbURL {out}/resultsDbURL/  -dirSqlTemplate {out}/sqlTemplate/  "
              f"-dirArguments {out}/arguments/  -dirRunFirstOnce {out}/runFirstOnce/  -dirJars {out}/jars/")
    return 0


# --- domain-facing: preview examples + author a spec from listed parameters ---

def cmd_preview(a):
    specs = fg.load_specs_dir(a.specs)
    if a.spec:
        specs = [s for s in specs if s.name == a.spec]
        if not specs:
            raise SystemExit(f"spec '{a.spec}' not found in {a.specs}")
    if a.html:
        Path(a.html).write_text(fg.render_preview_html(specs), encoding="utf-8")
        print(f"HTML landing ({len(specs)} scenario(s)) → {a.html}")
        return 0
    for s in specs:
        print(fg.render_preview(s, a.k)); print()
    return 0


def _find_example(specs_dir, name):
    if not name:
        return None
    frm = next((s for s in fg.load_specs_dir(specs_dir) if s.name == name), None)
    if frm is None:
        raise SystemExit(f"--from '{name}' not found in {specs_dir}")
    return frm


def cmd_scaffold(a):
    frm = _find_example(a.specs, a.frm)
    out = Path(a.out) / f"{a.name}.toml"
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and not a.force:
        raise SystemExit(f"{out} exists (use --force to overwrite)")
    out.write_text(fg.scaffold_template(a.name, frm), encoding="utf-8")
    print(f"template → {out}\nFill in YOUR slots/values, then:\n"
          f"  python3 fwgen_cli.py preview --specs {a.out} --spec {a.name}")
    return 0


def cmd_new(a):
    """Interactive wizard — the specialist lists slots+values; everything else
    (baseline, goal direction, FW_ machinery) is auto-derived. Empty slot finishes."""
    frm = _find_example(a.specs, a.frm)
    print("=== fwgen: new scenario — list YOUR parameters (Ctrl-C aborts) ===")
    name = a.name or input("scenario name (file stem)> ").strip()
    if not name:
        raise SystemExit("name required")
    title = input(f"title [{name}]> ").strip() or name
    if frm:
        print(f"\n(reference example '{frm.name}' — its slots are suggestions to edit/replace:)")
        for s in frm.slots:
            print(f"   {s.sheet}: {', '.join(s.values)}")
    print("\nEnter slots (parameter axes). Empty name finishes.")
    slots = []
    while True:
        sheet = input("  slot name (e.g. MODEL; no FW_)> ").strip()
        if not sheet:
            break
        key = input(f"    key [{sheet.lower()}]> ").strip() or None
        vals = [v.strip() for v in input("    values, comma-sep (1st = baseline)> ").split(",") if v.strip()]
        if not vals:
            print("    need ≥1 value — slot skipped"); continue
        slots.append((sheet, key, vals))
    if not slots:
        raise SystemExit("no slots given")
    goals = [g.strip() for g in input("\ngoals/metrics, comma-sep (optional)> ").split(",") if g.strip()]
    data = fg.build_spec_dict(name, slots, title=title, goals=goals or None)
    fg.parse_spec(data, name)                      # validate (raises on bad input)
    out = Path(a.out) / f"{name}.toml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(fg.dump_spec_toml(data), encoding="utf-8")
    print(f"\nwrote {out}\n")
    print(fg.render_preview(fg.load_spec(out)))
    print(f"\nGenerate input files:  python3 fwgen_cli.py gen --specs {a.out} --out out")
    return 0


def _write_readme(out: Path, specs, results, a):
    lines = [f"# Generated Core input-test workbooks (strategy: {a.strategy})", "",
             "Produced by `fwgen` from external specs — no scenario data is hardcoded in the",
             "generator. Goal directions are auto-inferred from metric names; baseline = row 0",
             "of each slot. Analyzer goals go in the Reader's `fw.properties`.", ""]
    for spec, r in zip(specs, results):
        lines += [f"## {r['base']}  ({r['chunks']} workbook{'s' if r['chunks'] != 1 else ''})",
                  f"- scenario: {spec.title}",
                  f"- slots: {', '.join(f'{s.sheet}({len(s.values)})' for s in spec.slots)} → full product {spec.combos}",
                  f"- emitted: {r['rows']} rows — {r['mode']}",
                  f"- `fw.analyzer.goals={spec.goals_property()}`"]
        if spec.note:
            lines.append(f"- note: {spec.note}")
        lines.append("")
    (out / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv=None):
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="fwgen", description="Generate Core input-test workbooks from specs.")
    sub = p.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("list", help="list scenarios + inferred goals")
    pl.add_argument("--specs", default="specs")
    pl.set_defaults(func=cmd_list)

    pg = sub.add_parser("gen", help="generate workbooks")
    pg.add_argument("--specs", default="specs")
    pg.add_argument("--out", default="out")
    pg.add_argument("--strategy", choices=["full", "ablation", "reduce", "auto"], default="full")
    pg.add_argument("--n", type=int, default=0, help="N for --strategy reduce (2=pairwise)")
    pg.add_argument("--optimal", action="store_true", help="optimal set-cover reduction")
    pg.add_argument("--budget", type=int, default=64, help="max rows for --strategy auto")
    pg.add_argument("--fw-info", default="dup", help="dup | skip | clone:<ref.xlsx>")
    pg.add_argument("--json", action="store_true", help="also write a sibling .json per workbook")
    pg.add_argument("--materialize", action="store_true",
                    help="for 'full'/'auto': pre-expand the product into rows (chunkable) instead of compact")
    pg.add_argument("--chunk-rows", type=int, default=0, dest="chunk_rows",
                    help="split materialized output into workbooks of <= N rows each (0 = single)")
    pg.add_argument("--workers", type=int, default=1, help="build chunks in N parallel processes")
    pg.add_argument("--autofit", type=float, default=0.0,
                    help="cell-autofit %% on every sheet (0=off; 130≈1.3 line spacing)")
    pg.set_defaults(func=cmd_gen)

    pv = sub.add_parser("validate", help="validate generated workbooks")
    pv.add_argument("--out", default="out")
    pv.set_defaults(func=cmd_validate)

    pj = sub.add_parser("json", help="batch-serialise a dir of .xlsx to .json (parallel)")
    pj.add_argument("--in", dest="indir", default="out", help="dir of .xlsx")
    pj.add_argument("--out", default="", help="json dir (default: sibling <in>_json)")
    pj.add_argument("--workers", type=int, default=1)
    pj.set_defaults(func=cmd_json)

    pc = sub.add_parser("coverage", help="emit one tiny workbook per Core verb (isolated; no explosion)")
    pc.add_argument("--out", default="coverage_out")
    pc.add_argument("--fw-info", default="skip", help="dup | skip | clone:<ref.xlsx>")
    pc.add_argument("--json", action="store_true", help="also write a sibling .json")
    pc.add_argument("--autofit", type=float, default=0.0)
    pc.set_defaults(func=cmd_coverage)

    ph = sub.add_parser("handshake", help="emit a ready-to-run Reader→Executor handshake for a spec "
                                          "(fixes empty fwVar.shift; validates verdict code vs #combos columns)")
    ph.add_argument("--specs", default="specs")
    ph.add_argument("--spec", default="", help="one scenario by name (default: all)")
    ph.add_argument("--out", default="handshake_out")
    ph.add_argument("--db-url", dest="db_url", default="", help="full JDBC URL (else built from --host/--port/--db)")
    ph.add_argument("--host", default="localhost")
    ph.add_argument("--port", default="5432")
    ph.add_argument("--db", default="", help="Results DB name (== Core db.name; default: spec name)")
    ph.add_argument("--table", default="", help="Results table name (default: --db)")
    ph.add_argument("--user", default="postgres")
    ph.add_argument("--password", default="pass")
    ph.add_argument("--shift", type=int, default=fg.RECOMMENDED_FWVAR_SHIFT)
    ph.set_defaults(func=cmd_handshake)

    pp = sub.add_parser("preview", help="show a domain example (no FW_); --html for a landing page")
    pp.add_argument("--specs", default="specs")
    pp.add_argument("--spec", default="", help="one scenario by name (default: all)")
    pp.add_argument("--k", type=int, default=6, help="example candidates to show")
    pp.add_argument("--html", default="", help="write an HTML landing page instead of printing")
    pp.set_defaults(func=cmd_preview)

    pn = sub.add_parser("new", help="interactive wizard: list YOUR parameters → spec")
    pn.add_argument("--specs", default="specs", help="dir to resolve --from examples")
    pn.add_argument("--from", dest="frm", default="", help="example scenario to start from")
    pn.add_argument("--name", default="", help="scenario name (else prompted)")
    pn.add_argument("--out", default="specs", help="dir to write the new spec into")
    pn.set_defaults(func=cmd_new)

    ps = sub.add_parser("scaffold", help="write a commented TOML template to fill in")
    ps.add_argument("--name", required=True)
    ps.add_argument("--from", dest="frm", default="", help="example scenario to pre-fill from")
    ps.add_argument("--specs", default="specs", help="dir to resolve --from examples")
    ps.add_argument("--out", default="specs", help="dir to write the template into")
    ps.add_argument("--force", action="store_true")
    ps.set_defaults(func=cmd_scaffold)

    pgr = sub.add_parser("graph", help="emit the FW_Seq dependency graph (JSON/DOT) + structural checks")
    pgr.add_argument("--specs", default="specs", help="spec dir")
    pgr.add_argument("--dot", action="store_true", help="emit Graphviz DOT instead of JSON")
    pgr.add_argument("--out", default="", help="dir to write <spec>.graph.json/<spec>.dot into (default: stdout)")
    pgr.set_defaults(func=cmd_graph)

    a = p.parse_args(argv)
    rc = a.func(a)
    sys.exit(rc or 0)


if __name__ == "__main__":
    main()
