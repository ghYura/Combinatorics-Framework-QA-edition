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


"""Build D8b inputs: spec/{spec.toml, demo.xlsx}; the XLSX is the run input.

    python build_spec.py            # (re)write spec/ from the audited sources
    python build_spec.py --check    # compare spec/ with a fresh build; exit 1 on drift

Sheets HEAD, IMPL, EDGE_AB, EDGE_AC, EDGE_AD, EDGE_BC, EDGE_BD, EDGE_CD, EDIT, TAIL, each through an
explicit FW_Combi(1) -> FW_Combi(size) row. Every EDGE slot has two explicit values, edge(u,v,0)
and edge(u,v,1), so the empty graph is a real selection (no empty fragment is dropped by a later
pass). The Framework crosses the six binary choices and the edit; reachability, fresh evaluation
and path counts belong to the harness. No constraints, sieve or optional axes. HEAD inlines
sut.py, oracle.py and runtime.py, each checked against its SHA-256.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC_DIR = HERE / "spec"
REPO = Path(__file__).resolve().parents[2]
GEN = REPO / "generator_trunk"
MODULES = ("sut", "oracle", "runtime")
EXCEL_CELL_LIMIT = 32767
LICENSE = (HERE / "sut.py").read_text(encoding="utf-8").split('\n"""', 1)[0].rstrip() + "\n"
POLICIES = ["closure_forward", "direct_only", "closure_reverse"]
EDGE_SLOTS = ["AB", "AC", "AD", "BC", "BD", "CD"]
DERIVED = json.loads((HERE / "architect-derived.json").read_text())
IDENTITY = ["FW_Combi(1)", "FW_Combi(size)"]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def head_value(sources):
    digests = {m: sha256(s.encode("utf-8")) for m, s in sources.items()}
    lines = ["# D8b HEAD: audited sut.py, oracle.py, runtime.py inlined by build_spec.py.",
             "# Each source is checked against its SHA-256, then run in its own module namespace.",
             "import hashlib as _d8_hash, sys as _d8_sys, types as _d8_types",
             "_D8_SOURCES = {"]
    lines += [f"    {m!r}: {s!r}," for m, s in sources.items()]
    lines += ["}", "_D8_SHA256 = {"]
    lines += [f"    {m!r}: {d!r}," for m, d in digests.items()]
    lines += ["}",
              f"for _d8_name in {MODULES!r}:",
              "    _d8_src = _D8_SOURCES[_d8_name]",
              "    if _d8_hash.sha256(_d8_src.encode('utf-8')).hexdigest() != _D8_SHA256[_d8_name]:",
              "        raise RuntimeError('inlined %s.py does not match its recorded SHA-256' % _d8_name)",
              "    _d8_mod = _d8_types.ModuleType(_d8_name)",
              "    _d8_mod.__file__ = '<d8b/%s.py>' % _d8_name",
              "    _d8_sys.modules[_d8_name] = _d8_mod",
              "    exec(compile(_d8_src, _d8_mod.__file__, 'exec'), _d8_mod.__dict__)",
              "d8 = _d8_sys.modules['runtime']",
              "d8.SOURCE_SHA256.update(_D8_SHA256)",
              "impl, edge, edit, finish = d8.impl, d8.edge, d8.edit, d8.finish      # the names the fragments call",
              "d8.begin()",
              ""]
    return "\n".join(lines), digests


def layout(head):
    """(slots, seq_extra) in the contract's sheet order; each value is one statement with its newline."""
    slots = [("HEAD", [head], "FW_Combi(1)", [], "runtime definitions: audited sources, inlined"),
             ("IMPL", [f'impl("{p}")\n' for p in POLICIES], "FW_Combi(1)", [], "update policy; 3 values")]
    slots += [(f"EDGE_{e}", [f'edge("{e[0]}","{e[1]}",{b})\n' for b in (0, 1)], "FW_Combi(1)", [],
               f"edge {e[0]}->{e[1]} absent (0) or present (1)") for e in EDGE_SLOTS]
    slots += [("EDIT", [f'edit("{n}")\n' for n in "ABCD"], "FW_Combi(1)", [], "the node whose base input increases by 10"),
              ("TAIL", ["_verdict = finish()\nFW_VAR = _verdict\nFW_CUSTOM_VAR = FW_VAR\n"], "FW_Combi(1)", [],
               "build the cache, edit, update, judge against fresh evaluation, set the verdict")]
    extra = [[s_[0], *IDENTITY] for s_ in slots]
    return slots, extra


CUSTOM_VAR_MSG = ("D8b: the cache after the update differs from fresh evaluation (IMPL position 2 is only the legacy "
                  "carrier, not a cause). Read mismatched_nodes and updates in the observation record rec=.")


# ---- minimal TOML emitter (no third-party writer); tomllib round-trip checks it ----
def t_str(s):
    if "'''" not in s and "\r" not in s and not s.startswith("\n") and all(
            c == "\n" or c == "\t" or ord(c) >= 0x20 for c in s) and "\x7f" not in s:
        return "'''" + s + "'''" if "\n" in s else "'" + s + "'" if "'" not in s else json.dumps(s, ensure_ascii=False)
    return json.dumps(s, ensure_ascii=False)       # a JSON string is a valid TOML basic string


def t_val(v):
    if isinstance(v, str):
        return t_str(v)
    if isinstance(v, list):
        return "[" + ", ".join(t_val(x) for x in v) + "]"
    raise TypeError(type(v))


def render_toml(head, digests):
    slots, extra = layout(head)
    out = [LICENSE.rstrip(), "#", "# D8b incremental DAG evaluation: GENERATED by build_spec.py; do not edit.",
           "# Inlined source SHA-256:"] + [f"#   {m}.py {d}" for m, d in digests.items()]
    out += ["", 'spec_version = "1"',
            f"title = {t_str('D8b incremental DAG evaluation: 64 forward DAGs x 4 edits x 3 policies')}",
            f"note = {t_str('09-d8-dependency-dags/CONTRACT.md. Six binary edge slots crossed by the Framework; no sieve.')}",
            'args = ["noargs"]',
            "# Multi-verb FW_Seq rows (the expert chain form); Core applies the last row for a sheet.",
            f"seq_extra = {t_val(extra)}", ""]
    for sheet, values, verb, flags, comment in slots:
        out += [f"[[slots]]   # {comment}", f'sheet = "{sheet}"', f'key = "{sheet.lower()}"', f"verb = {t_str(verb)}", "raw = true"]
        out += [f"flags = {t_val(flags)}"] if flags else []
        out += [f"values = {t_val(values)}", ""]
    out += ["[[custom_vars]]", "code = 2", f"msg = {t_str(CUSTOM_VAR_MSG)}", ""]
    return "\n".join(out)


def build(dest: Path):
    sources = {m: (HERE / f"{m}.py").read_text(encoding="utf-8") for m in MODULES}
    head, digests = head_value(sources)
    if len(head) > EXCEL_CELL_LIMIT:
        raise SystemExit(f"HEAD is {len(head)} characters; an XLSX cell holds at most {EXCEL_CELL_LIMIT}")
    sys.path.insert(0, str(GEN))
    import fwgen as fg
    dest.mkdir(parents=True, exist_ok=True)
    text = render_toml(head, digests)
    parsed = tomllib.loads(text)
    slots, extra = layout(head)
    if [s["values"] for s in parsed["slots"]] != [s[1] for s in slots] or parsed["seq_extra"] != extra:
        raise SystemExit("TOML round-trip changed a value")
    (dest / "spec.toml").write_text(text, encoding="utf-8")
    fg.load_spec(dest / "spec.toml", strict=True)
    with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as tmp:
        specs, out = Path(tmp) / "specs", Path(tmp) / "wb"
        specs.mkdir()
        shutil.copy2(dest / "spec.toml", specs / "spec.toml")
        r = subprocess.run([sys.executable, str(GEN / "fwgen_cli.py"), "gen", "--specs", str(specs), "--out", str(out)],
                           cwd=REPO, capture_output=True, text=True)
        if r.returncode != 0 or not (out / "spec.xlsx").is_file():
            raise SystemExit(f"fwgen gen failed:\n{r.stdout}\n{r.stderr}")
        if fg.workbook_sidecar_path(out / "spec.xlsx").exists():
            raise SystemExit("unexpected constraints companion")
        shutil.copy2(out / "spec.xlsx", dest / "demo.xlsx")
    problems = fg.validate_workbook(dest / "demo.xlsx")
    if problems:
        raise SystemExit(f"validate_workbook: {problems}")
    return {"head_chars": len(head), "head_sha256": sha256(head.encode()), "module_sha256": digests,
            "files": {f: sha256((dest / f).read_bytes()) for f in ("spec.toml", "demo.xlsx")}}


def workbook_content(path: Path):
    sys.path.insert(0, str(GEN))
    import fwgen as fg
    return fg.workbook_to_json(path)["sheets"]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as tmp:
            build(Path(tmp))
            diffs = ["spec.toml"] if (SPEC_DIR / "spec.toml").read_bytes() != (Path(tmp) / "spec.toml").read_bytes() else []
            diffs += ["demo.xlsx"] if workbook_content(SPEC_DIR / "demo.xlsx") != workbook_content(Path(tmp) / "demo.xlsx") else []
        print("spec/ matches a fresh build" if not diffs else f"DRIFT: {diffs}")
        raise SystemExit(1 if diffs else 0)
    record = build(SPEC_DIR)
    record.update({"schema": "d8b.build/v1", "contract": "v1",
                   "note": "demo.xlsx bytes carry zip timestamps; compare cell content with build_spec.py --check"})
    (SPEC_DIR / "build.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: record[k] for k in ("head_chars", "files")}, indent=1))


if __name__ == "__main__":
    main()
