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

"""Build D5 phase A's declarative inputs: spec/{spec.toml, demo.xlsx}; the XLSX is the run input.

    python build_spec.py            # (re)write spec/ from the audited sources
    python build_spec.py --check    # compare spec/ with a fresh build; exit 1 on drift

The Framework constructs the trees; nothing here enumerates them. One catalogue per sheet:
OPS holds the four push_op fragments, FIELD (FW_Exclude) the two bind fragments. The OPS chain
FW_Combi(2) -> FW_Permut() -> FW_Group -> FW_Cartes(FIELD) is a multi-verb FW_Seq row (seq_extra;
Core applies the LAST row for a sheet), and FIELD gets the explicit identity chain
FW_Combi(1) -> FW_Combi(size). The bare FW_Group has no FW_ReplaceRE lines: Core strips every
bracket when it parses a grouped result back, so [[op1, op2], [field]] becomes three codes.
HEAD inlines sut.py, oracle.py and runtime.py, each checked against its SHA-256 before it runs in
its own module namespace. The TOML is compiled to XLSX by the repository's fwgen CLI. No sieve.
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
REPO = Path(__file__).resolve().parents[3]
GEN = REPO / "generator_trunk"
MODULES = ("sut", "oracle", "runtime")
EXCEL_CELL_LIMIT = 32767
LICENSE = (HERE / "sut.py").read_text(encoding="utf-8").split('\n"""', 1)[0].rstrip() + "\n"
POLICIES = ["correct", "reverse_pair", "wrong_field"]
OPS = ["A", "M", "S", "N"]
FIELDS = ["x", "y"]
OPS_CHAIN = ["FW_Combi(2)", "FW_Permut()", "FW_Group", "FW_Cartes(FIELD)"]
FIELD_CHAIN = ["FW_Exclude", "FW_Combi(1)", "FW_Combi(size)"]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def head_value(sources):
    digests = {m: sha256(s.encode("utf-8")) for m, s in sources.items()}
    lines = ["# D5 phase A HEAD: audited sut.py, oracle.py, runtime.py inlined by build_spec.py.",
             "# Each source is checked against its SHA-256, then run in its own module namespace.",
             "import hashlib as _d5_hash, sys as _d5_sys, types as _d5_types",
             "_D5_SOURCES = {"]
    lines += [f"    {m!r}: {s!r}," for m, s in sources.items()]
    lines += ["}", "_D5_SHA256 = {"]
    lines += [f"    {m!r}: {d!r}," for m, d in digests.items()]
    lines += ["}",
              f"for _d5_name in {MODULES!r}:",
              "    _d5_src = _D5_SOURCES[_d5_name]",
              "    if _d5_hash.sha256(_d5_src.encode('utf-8')).hexdigest() != _D5_SHA256[_d5_name]:",
              "        raise RuntimeError('inlined %s.py does not match its recorded SHA-256' % _d5_name)",
              "    _d5_mod = _d5_types.ModuleType(_d5_name)",
              "    _d5_mod.__file__ = '<d5a/%s.py>' % _d5_name",
              "    _d5_sys.modules[_d5_name] = _d5_mod",
              "    exec(compile(_d5_src, _d5_mod.__file__, 'exec'), _d5_mod.__dict__)",
              "d5 = _d5_sys.modules['runtime']",
              "d5.SOURCE_SHA256.update(_D5_SHA256)",
              "impl, push_op, bind, finish = d5.impl, d5.push_op, d5.bind, d5.finish      # the names the fragments call",
              "d5.begin()                                                                # a fresh tree builder",
              ""]
    return "\n".join(lines), digests


def layout(head):
    """(slots, seq_extra) in the contract's sheet order. Every fragment is a complete statement ending
    in its own newline: an OPS row places three codes in one cell, and an FW_SheetNames ending would
    wrap the cell, not each fragment. FIELD comes last and is FW_Exclude: it reaches the candidates
    only through OPS's grouped Cartes, never as a column of fw_final."""
    slots = [("HEAD", [head], "FW_Combi(1)", [], "runtime definitions: audited sources, inlined; begins a fresh tree"),
             ("IMPL", [f'impl("{p}")\n' for p in POLICIES], "FW_Combi(1)", [], "adapter policy under test; 3 values"),
             ("OPS", [f'push_op("{o}")\n' for o in OPS], OPS_CHAIN[0], [], f"operations: {' -> '.join(OPS_CHAIN)}"),
             ("TAIL", ['_verdict = finish("A")\nFW_VAR = _verdict\nFW_CUSTOM_VAR = FW_VAR\n'], "FW_Combi(1)", [],
              "validate the tree, run SUT and reference, set the verdict; 1 value"),
             ("FIELD", [f'bind("{f}")\n' for f in FIELDS], "FW_Combi(1)", ["FW_Exclude"],
              "field binding, FW_Exclude: contributes through OPS only; explicit identity chain")]
    extra = [["OPS", *OPS_CHAIN], ["FIELD", *FIELD_CHAIN]]
    return slots, extra


CUSTOM_VAR_MSG = ("D5 phase A: the final record differs from the reference fold (IMPL position 2 is only the "
                  "legacy carrier, not a cause). Read expected/observed in the observation record rec=.")


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
    out = [LICENSE.rstrip(), "#", "# D5 phase A, ordered pipeline bound to a field: GENERATED by build_spec.py; do not edit.",
           "# Inlined source SHA-256:"] + [f"#   {m}.py {d}" for m, d in digests.items()]
    out += ["", 'spec_version = "1"',
            f"title = {t_str('D5 phase A: ordered two-operation pipeline x field binding, 3 adapter policies')}",
            f"note = {t_str('CONTRACT-A.md. OPS: ' + ' -> '.join(OPS_CHAIN) + '; FIELD is FW_Exclude.')}",
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
    record.update({"schema": "d5a.build/v1", "contract": "A",
                   "note": "demo.xlsx bytes carry zip timestamps; compare cell content with build_spec.py --check"})
    (SPEC_DIR / "build.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: record[k] for k in ("head_chars", "files")}, indent=1))


if __name__ == "__main__":
    main()
