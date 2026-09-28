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

"""Build D13b inputs: spec/{spec.toml, demo.xlsx} and config/core-d13b.fw.properties; the XLSX is the run input.

    python build_spec.py            # (re)write spec/ and config/ from the audited sources
    python build_spec.py --check    # compare them with a fresh build; exit 1 on drift

The Framework composes every context expression; nothing here lists a complete program. Sheet order
and FW_Seq chains follow the AI architect's sizing probe planning/shape.toml, with the real fragment values:
  CHUNKS  source_item("marker" / source_item("filler": FW_Cartes(LEAF_END) pairs each with `),\n`,
          FW_Group + two bracket-removal FW_ReplaceRE lines, FW_Permut() over the two complete rows,
          then explicit FW_Combi(size)                                      -> 2 rows x 4 codes (MF, FM)
  INNER   FW_(,,PREFIX,LIST_OPEN,CHUNKS,,LIST_END,,M:N): retrieved_page( / tool_result( [ ... ])
                                                                            -> 4 rows x 7 codes
  ROOT    FW_(CONTEXT_OPEN,,FW_(),COMMA,NOTE,,CONTEXT_CLOSE,,M:N), FW_() = INNER (latest brace):
          consume(context([trusted_task(), <carrier>, trusted_note()]))    -> 4 rows x 11 codes
Mandatory final factors: HEAD, IMPL (position 2), ENCODING, MARKER, ROOT, TAIL = 1 x 3 x 3 x 3 x 4 x 1.
Operand and token sheets are FW_Exclude + FW_Reuse; configuration slots use FW_Combi(1) -> FW_Combi(size).
HEAD inlines sut.py, oracle.py and runtime.py, each checked against its SHA-256. The Core properties
differ from the shipped template only in two observation-only FW_ReplaceRE keys.
"""
import argparse
import contextlib
import difflib
import hashlib
import io
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
CORE_TEMPLATE = GEN / "config" / "core.fw.properties"
CORE_PROPS = HERE / "config" / "core-d13b.fw.properties"
CORE_EDITS = {"core.replace.patternPolicy": "warn", "core.replace.diagnostics": "summary"}   # observation only
MODULES = ("sut", "oracle", "runtime")
EXCEL_CELL_LIMIT = 32767
LICENSE = (HERE / "sut.py").read_text(encoding="utf-8").split('\n"""', 1)[0].rstrip() + "\n"
POLICIES = ["preserve_origin", "wrapper_trust", "decode_trust"]
ENCODINGS = ["plain", "json", "base64"]
MARKERS = ["reference", "emit_canary", "set_flag"]
IDENTITY = ["FW_Combi(1)", "FW_Combi(size)"]
OPERAND = ["FW_Exclude", "FW_Reuse"]
GROUP_CELL = "\n".join(["FW_Group", r'FW_ReplaceRE("\[", "")', r'FW_ReplaceRE("\]", "")'])
CHUNKS_CHAIN = ["FW_Cartes(LEAF_END)", GROUP_CELL, "FW_Permut()", "FW_Combi(size)"]
BRACES = {"INNER": "FW_(,,PREFIX,LIST_OPEN,CHUNKS,,LIST_END,,M:N)",
          "ROOT": "FW_(CONTEXT_OPEN,,FW_(),COMMA,NOTE,,CONTEXT_CLOSE,,M:N)"}
RUNTIME_NAMES = ("impl", "encoding", "marker", "source_item", "retrieved_page", "tool_result",
                 "trusted_task", "trusted_note", "context", "consume", "finish")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def head_value(sources):
    digests = {m: sha256(s.encode("utf-8")) for m, s in sources.items()}
    lines = ["# D13b HEAD: audited sut.py, oracle.py, runtime.py inlined by build_spec.py.",
             "# Each source is checked against its SHA-256, then run in its own module namespace.",
             "import hashlib as _d13_hash, sys as _d13_sys, types as _d13_types",
             "_D13_SOURCES = {"]
    lines += [f"    {m!r}: {s!r}," for m, s in sources.items()]
    lines += ["}", "_D13_SHA256 = {"]
    lines += [f"    {m!r}: {d!r}," for m, d in digests.items()]
    lines += ["}",
              f"for _d13_name in {MODULES!r}:",
              "    _d13_src = _D13_SOURCES[_d13_name]",
              "    if _d13_hash.sha256(_d13_src.encode('utf-8')).hexdigest() != _D13_SHA256[_d13_name]:",
              "        raise RuntimeError('inlined %s.py does not match its recorded SHA-256' % _d13_name)",
              "    _d13_mod = _d13_types.ModuleType(_d13_name)",
              "    _d13_mod.__file__ = '<d13b/%s.py>' % _d13_name",
              "    _d13_sys.modules[_d13_name] = _d13_mod",
              "    exec(compile(_d13_src, _d13_mod.__file__, 'exec'), _d13_mod.__dict__)",
              "d13 = _d13_sys.modules['runtime']",
              "d13.SOURCE_SHA256.update(_D13_SHA256)",
              f"{', '.join(RUNTIME_NAMES)} = ({', '.join('d13.' + n for n in RUNTIME_NAMES)})   # the names the fragments call",
              "d13.begin()",
              ""]
    return "\n".join(lines), digests


def layout(head):
    """(slots, seq_extra) in the probe's sheet order. Operand fragments are unterminated code pieces that
    the group and braces concatenate into one expression; configuration values are whole statements."""
    slots = [("HEAD", [head], "FW_Combi(1)", [], "runtime definitions: audited sources, inlined"),
             ("IMPL", [f'impl("{p}")\n' for p in POLICIES], "FW_Combi(1)", [], "processor policy; 3 values (legacy verdict carrier)"),
             ("ENCODING", [f'encoding("{e}")\n' for e in ENCODINGS], "FW_Combi(1)", [], "marker leaf encoding"),
             ("MARKER", [f'marker("{m}")\n' for m in MARKERS], "FW_Combi(1)", [], "marker class"),
             ("PREFIX", ["retrieved_page(", "tool_result("], "FW_Combi(1)", OPERAND, "operand: the two carrier constructors"),
             ("LEAF_END", ["),\n"], "FW_Combi(1)", OPERAND, "operand: closes one source_item call"),
             ("CHUNKS", ['source_item("marker"', 'source_item("filler"'], "FW_Cartes(LEAF_END)", OPERAND,
              "operand: leaf opens; Cartes(LEAF_END) -> Group(bracket removal) -> Permut() -> Combi(size)"),
             ("LIST_OPEN", ["["], "FW_Combi(1)", OPERAND, "token: opens the carrier's item list (INNER relation)"),
             ("LIST_END", ["])"], "FW_Combi(1)", OPERAND, "token: closes the list and the carrier call (INNER end)"),
             ("NOTE", ["trusted_note()"], "FW_Combi(1)", OPERAND, "operand: the trusted note leaf (ROOT second operand)"),
             ("CONTEXT_OPEN", ["consume(context([trusted_task(),"], "FW_Combi(1)", OPERAND, "token: ROOT start with the trusted task"),
             ("COMMA", [","], "FW_Combi(1)", OPERAND, "token: ROOT relation"),
             ("CONTEXT_CLOSE", ["]))\n"], "FW_Combi(1)", OPERAND, "token: ROOT end"),
             ("INNER", ["# INNER placeholder: its rows are written by the brace\n"], "FW_Combi(1)", OPERAND,
              "brace target: PREFIX M:N CHUNKS with [ and ]); nested operand of ROOT"),
             ("ROOT", ["# ROOT placeholder: its rows are written by the brace\n"], "FW_Combi(1)", [],
              "brace target: CONTEXT_OPEN, FW_()=INNER, COMMA, NOTE, CONTEXT_CLOSE"),
             ("TAIL", ["_verdict = finish()\nFW_VAR = _verdict\nFW_CUSTOM_VAR = FW_VAR\n"], "FW_Combi(1)", [],
              "process the consumed tree, judge it, set the verdict")]
    extra = []
    for sheet, _values, _verb, flags, _c in slots:
        chain = CHUNKS_CHAIN if sheet == "CHUNKS" else [BRACES[sheet]] if sheet in BRACES else IDENTITY
        extra.append([sheet, *flags, *chain])
    return slots, extra


CUSTOM_VAR_MSG = ("D13b: wrong content or effects (a promoted untrusted leaf, lost content or missing trusted work; IMPL "
                  "position 2 is only the legacy carrier, not a cause). Read trace/actions/outbox in the record rec=.")


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
    out = [LICENSE.rstrip(), "#", "# D13b composed untrusted-content boundaries: GENERATED by build_spec.py; do not edit.",
           "# Inlined source SHA-256:"] + [f"#   {m}.py {d}" for m, d in digests.items()]
    out += ["", 'spec_version = "1"',
            f"title = {t_str('D13b composed carriers: 3 policies x 3 encodings x 3 markers x 4 Framework-composed contexts')}",
            f"note = {t_str('15-d13-composed-carriers/CONTRACT.md. Local stubs only; ROOT is composed by FW_Group and two braces.')}",
            'args = ["noargs"]',
            "# Multi-verb, rewrite and brace FW_Seq rows (expert form); Core applies the last row for a sheet.",
            f"seq_extra = {t_val(extra)}", ""]
    for sheet, values, verb, flags, comment in slots:
        out += [f"[[slots]]   # {comment}", f'sheet = "{sheet}"', f'key = "{sheet.lower()}"', f"verb = {t_str(verb)}", "raw = true"]
        out += [f"flags = {t_val(flags)}"] if flags else []
        out += [f"values = {t_val(values)}", ""]
    out += ["[[custom_vars]]", "code = 2", f"msg = {t_str(CUSTOM_VAR_MSG)}", ""]
    return "\n".join(out)


def core_props_text():
    lines, seen = [], set()
    for ln in CORE_TEMPLATE.read_text(encoding="utf-8").splitlines():
        key = ln.split("=", 1)[0].strip() if "=" in ln and not ln.lstrip().startswith("#") else None
        if key in CORE_EDITS:
            lines.append(f"{key}={CORE_EDITS[key]}")
            seen.add(key)
        else:
            lines.append(ln)
    if seen != set(CORE_EDITS):
        raise SystemExit(f"template lacks {set(CORE_EDITS) - seen}")
    return "\n".join(lines) + "\n"


def build(dest: Path, props_dest: Path):
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
    # Compatibility posture: CHUNKS' fragments are unterminated ON PURPOSE (they compose one expression),
    # which strict mode refuses as the concatenator trap. Every other loader warning is still fatal.
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fg.load_spec(dest / "spec.toml", strict=False)
    warnings = [ln.strip() for ln in buf.getvalue().splitlines() if ln.strip()]
    if len(warnings) != 1 or "slot 'CHUNKS': verb FW_Cartes(LEAF_END) places up to 2 values" not in warnings[0]:
        raise SystemExit(f"unexpected spec loader messages: {warnings}")
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
    props_dest.parent.mkdir(parents=True, exist_ok=True)
    props_dest.write_text(core_props_text(), encoding="utf-8")
    return {"head_chars": len(head), "head_sha256": sha256(head.encode()), "module_sha256": digests,
            "loader_warnings": {"messages": warnings, "why_accepted": "CHUNKS fragments are deliberately unterminated "
                                "code pieces; the group and braces concatenate them into one Python expression"},
            "files": {f: sha256((dest / f).read_bytes()) for f in ("spec.toml", "demo.xlsx")},
            "core_props": {"template": str(CORE_TEMPLATE), "template_sha256": sha256(CORE_TEMPLATE.read_bytes()),
                           "edits": CORE_EDITS, "sha256": sha256(props_dest.read_bytes())}}


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
            build(Path(tmp) / "spec", Path(tmp) / "core.properties")
            diffs = ["spec.toml"] if (SPEC_DIR / "spec.toml").read_bytes() != (Path(tmp) / "spec" / "spec.toml").read_bytes() else []
            diffs += ["demo.xlsx"] if workbook_content(SPEC_DIR / "demo.xlsx") != workbook_content(Path(tmp) / "spec" / "demo.xlsx") else []
            diffs += ["config/core-d13b.fw.properties"] if CORE_PROPS.read_bytes() != (Path(tmp) / "core.properties").read_bytes() else []
        print("spec/ and config/ match a fresh build" if not diffs else f"DRIFT: {diffs}")
        raise SystemExit(1 if diffs else 0)
    record = build(SPEC_DIR, CORE_PROPS)
    record.update({"schema": "d13b.build/v1", "contract": "v1",
                   "core_props_diff": "".join(difflib.unified_diff(CORE_TEMPLATE.read_text().splitlines(True),
                                                                   CORE_PROPS.read_text().splitlines(True),
                                                                   "template", "core-d13b.fw.properties")),
                   "note": "demo.xlsx bytes carry zip timestamps; compare cell content with build_spec.py --check"})
    (SPEC_DIR / "build.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: record[k] for k in ("head_chars", "files")}, indent=1))
    print(record["core_props_diff"])


if __name__ == "__main__":
    main()
