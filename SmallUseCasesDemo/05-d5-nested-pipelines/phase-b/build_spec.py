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

"""Build D5 phase B's inputs: spec/<B1|B2>/{spec.toml, demo.xlsx} and config/core-b.fw.properties.

    python build_spec.py            # (re)write spec/ and config/ from the audited sources
    python build_spec.py --check    # compare them with a fresh build; exit 1 on drift

The Framework constructs every tree: nothing here lists a complete tree. Token sheets hold one
fragment each and are FW_Exclude (they reach candidates only as brace tokens or `+ SHEET +`
rewrite splices, which Core resolves from all source values). E1 builds [OPEN_X, op, CLOSE] rows
by Combi(1) -> Combi(1) -> FW_Group + three ordered FW_ReplaceRE lines -> Combi(1). E2 is
FW_Subsets -> FW_Combi(size) over OPEN_Y, op(N), CLOSE; E3 is op(N)/op(S). Braces:
  JZIP = FW_(,,E1,,E2,,,,1:1)   JCAT = FW_(,,E1,,E3,,,,M:N)
  ROOT = FW_(PIPE_OPEN,,JZIP,REL_S,FW_(),,PIPE_CLOSE,,M:N)
  BUNDLE (B2 only) = FW_(BUNDLE_OPEN,,FW_()G,,SEAL,,BUNDLE_CLOSE,,M:N)
E1 is FW_Exclude + FW_Reuse (two consumers); single-consumer operands are FW_ReuseTableOnly;
JCAT and B2's ROOT (nested consumers) are FW_Reuse. B1's only mandatory structural result is ROOT,
B2's is BUNDLE. HEAD inlines sut.py, oracle.py and runtime.py, each checked against its SHA-256.
The Core properties differ from the shipped template only in two observation-only keys.
"""
import argparse
import difflib
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
CORE_TEMPLATE = GEN / "config" / "core.fw.properties"
CORE_PROPS = HERE / "config" / "core-b.fw.properties"
CORE_EDITS = {"core.replace.patternPolicy": "warn", "core.replace.diagnostics": "summary"}   # observation only
MODULES = ("sut", "oracle", "runtime")
EXCEL_CELL_LIMIT = 32767
LICENSE = (HERE / "sut.py").read_text(encoding="utf-8").split('\n"""', 1)[0].rstrip() + "\n"
POLICIES = ["correct", "flatten_scope", "leak_scope"]
# The three ordered rewrites of E1's grouped string [[opcode]] (Java regex, Core `+ SHEET +` splices).
REWRITES = [(r"^\[\[", '[[" + TMP + ", '), (r"^\[\[\d+, ", '[[" + OPEN_X + ", '), (r"\]\]$", ', " + CLOSE + "]]')]
GROUP_CELL = "\n".join(["FW_Group"] + [f'FW_ReplaceRE("{p}", "{r}")' for p, r in REWRITES])
BRACES = {"JZIP": "FW_(,,E1,,E2,,,,1:1)", "JCAT": "FW_(,,E1,,E3,,,,M:N)",
          "ROOT": "FW_(PIPE_OPEN,,JZIP,REL_S,FW_(),,PIPE_CLOSE,,M:N)",
          "BUNDLE": "FW_(BUNDLE_OPEN,,FW_()G,,SEAL,,BUNDLE_CLOSE,,M:N)"}
IDENTITY = ["FW_Combi(1)", "FW_Combi(size)"]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def head_value(sources):
    digests = {m: sha256(s.encode("utf-8")) for m, s in sources.items()}
    names = ("impl", "op", "open_scope", "close_scope", "begin_pipeline", "end_pipeline",
             "begin_bundle", "seal_bundle", "end_bundle", "poison_tmp", "finish")
    lines = ["# D5 phase B HEAD: audited sut.py, oracle.py, runtime.py inlined by build_spec.py.",
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
              "    _d5_mod.__file__ = '<d5b/%s.py>' % _d5_name",
              "    _d5_sys.modules[_d5_name] = _d5_mod",
              "    exec(compile(_d5_src, _d5_mod.__file__, 'exec'), _d5_mod.__dict__)",
              "d5 = _d5_sys.modules['runtime']",
              "d5.SOURCE_SHA256.update(_D5_SHA256)",
              f"{', '.join(names)} = ({', '.join('d5.' + n for n in names)})",
              "d5.begin()                                        # a fresh tree builder",
              ""]
    return "\n".join(lines), digests


def token(sheet, fragment, comment):
    return (sheet, [fragment], "FW_Combi(1)", ["FW_Exclude"], comment)


def layout(campaign, head):
    """(slots, seq_extra) in sheet order. Every fragment ends in its own newline (a ROOT row puts 13
    codes in one cell). Brace targets carry a placeholder that the brace replaces."""
    b2 = campaign == "B2"
    slots = [("HEAD", [head], "FW_Combi(1)", [], "runtime definitions: audited sources, inlined"),
             ("IMPL", [f'impl("{p}");\n' for p in POLICIES], "FW_Combi(1)", [], "interpreter policy; 3 values"),
             token("TMP", "poison_tmp();\n", "rewrite marker: must never reach a candidate"),
             token("OPEN_X", 'open_scope("x");\n', "token: opens an x scope (E1 rewrite splice)"),
             token("CLOSE", "close_scope();\n", "token: closes a scope (E1 rewrite splice)"),
             ("E1", ['op("A");\n', 'op("M");\n'], "FW_Combi(1)", ["FW_Exclude", "FW_Reuse"],
              "A/M leaves -> [OPEN_X, op, CLOSE]; two consumers (JZIP, JCAT)"),
             ("E2", ['open_scope("y");\n', 'op("N");\n', "close_scope();\n"], "FW_Subsets", ["FW_Exclude", "FW_ReuseTableOnly"],
              "OPEN_Y, op(N), CLOSE in order: FW_Subsets -> FW_Combi(size)"),
             ("E3", ['op("N");\n', 'op("S");\n'], "FW_Combi(1)", ["FW_Exclude", "FW_ReuseTableOnly"], "tail operations N/S"),
             token("PIPE_OPEN", "begin_pipeline();\n", "token: ROOT start"),
             token("REL_S", 'op("S");\n', "token: ROOT relation, S between JZIP and JCAT"),
             token("PIPE_CLOSE", "end_pipeline();\n", "token: ROOT end"),
             ("JZIP", ["# JZIP placeholder: its rows are written by the brace\n"], "FW_Combi(1)", ["FW_Exclude", "FW_ReuseTableOnly"],
              "brace target: E1 1:1 E2 (equal-length rows, alternated)"),
             ("JCAT", ["# JCAT placeholder: its rows are written by the brace\n"], "FW_Combi(1)", ["FW_Exclude", "FW_Reuse"],
              "brace target: E1 M:N E3 (row concatenation); nested operand of ROOT"),
             ("ROOT", ["# ROOT placeholder: its rows are written by the brace\n"], "FW_Combi(1)",
              ["FW_Exclude", "FW_Reuse"] if b2 else [], "brace target: PIPE_OPEN, JZIP, REL_S, FW_()=JCAT, PIPE_CLOSE")]
    if b2:
        slots += [token("BUNDLE_OPEN", "begin_bundle();\n", "token: BUNDLE start"),
                  ("SEAL", ["seal_bundle();\n"], "FW_Combi(1)", ["FW_Exclude", "FW_ReuseTableOnly"], "no-op validation fragment (operand)"),
                  token("BUNDLE_CLOSE", "end_bundle();\n", "token: BUNDLE end"),
                  ("BUNDLE", ["# BUNDLE placeholder: its row is written by the brace\n"], "FW_Combi(1)", [],
                   "brace target: BUNDLE_OPEN, FW_()G = all ROOT rows, SEAL, BUNDLE_CLOSE")]
    slots.append(("TAIL", [f'_verdict = finish("{campaign}")\nFW_VAR = _verdict\nFW_CUSTOM_VAR = FW_VAR\n'], "FW_Combi(1)", [],
                  "evaluate every tree, set the verdict"))
    tokens = ["TMP", "OPEN_X", "CLOSE", "PIPE_OPEN", "REL_S", "PIPE_CLOSE"] + (["BUNDLE_OPEN", "BUNDLE_CLOSE"] if b2 else [])
    extra = [["E1", "FW_Exclude", "FW_Reuse", "FW_Combi(1)", "FW_Combi(1)", GROUP_CELL, "FW_Combi(1)"],
             ["E2", "FW_Exclude", "FW_ReuseTableOnly", "FW_Subsets", "FW_Combi(size)"],
             ["E3", "FW_Exclude", "FW_ReuseTableOnly", *IDENTITY]]
    extra += [[t, "FW_Exclude", *IDENTITY] for t in tokens]
    extra += [["SEAL", "FW_Exclude", "FW_ReuseTableOnly", *IDENTITY]] if b2 else []
    extra += [["JZIP", "FW_Exclude", "FW_ReuseTableOnly", BRACES["JZIP"]],
              ["JCAT", "FW_Exclude", "FW_Reuse", BRACES["JCAT"]],
              ["ROOT", *(["FW_Exclude", "FW_Reuse"] if b2 else []), BRACES["ROOT"]]]
    extra += [["BUNDLE", BRACES["BUNDLE"]]] if b2 else []
    return slots, extra


CUSTOM_VAR_MSG = ("D5 phase B: a final record differs from the reference (IMPL position 2 is only the legacy carrier, "
                  "not a cause). Read expected/observed per tree in the observation record rec=.")


# ---- minimal TOML emitter (no third-party writer); tomllib round-trip checks it ----
def t_str(s):
    if "'''" not in s and "\r" not in s and not s.startswith("\n") and all(
            c == "\n" or c == "\t" or ord(c) >= 0x20 for c in s) and "\x7f" not in s:
        return "'''" + s + "'''" if "\n" in s else "'" + s + "'" if "'" not in s else json.dumps(s, ensure_ascii=False)
    return json.dumps(s, ensure_ascii=False)


def t_val(v):
    if isinstance(v, str):
        return t_str(v)
    if isinstance(v, list):
        return "[" + ", ".join(t_val(x) for x in v) + "]"
    raise TypeError(type(v))


def render_toml(campaign, head, digests):
    slots, extra = layout(campaign, head)
    out = [LICENSE.rstrip(), "#", f"# D5 phase B, campaign {campaign}: GENERATED by build_spec.py; do not edit.",
           "# Inlined source SHA-256:"] + [f"#   {m}.py {d}" for m, d in digests.items()]
    out += ["", 'spec_version = "1"',
            f"title = {t_str(f'D5 phase B {campaign}: rewrites, reuse, joins and nested scopes, 3 interpreter policies')}",
            f"note = {t_str('phase-b/CONTRACT.md. Structural mandatory result: ' + ('ROOT' if campaign == 'B1' else 'BUNDLE') + '.')}",
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
    record = {"head_chars": len(head), "head_sha256": sha256(head.encode()), "module_sha256": digests, "campaigns": {}}
    for campaign in ("B1", "B2"):
        cdir = dest / campaign
        cdir.mkdir(parents=True, exist_ok=True)
        text = render_toml(campaign, head, digests)
        parsed = tomllib.loads(text)
        slots, extra = layout(campaign, head)
        if [s["values"] for s in parsed["slots"]] != [s[1] for s in slots] or parsed["seq_extra"] != extra:
            raise SystemExit(f"{campaign}: TOML round-trip changed a value")
        (cdir / "spec.toml").write_text(text, encoding="utf-8")
        fg.load_spec(cdir / "spec.toml", strict=True)
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as tmp:
            specs, out = Path(tmp) / "specs", Path(tmp) / "wb"
            specs.mkdir()
            shutil.copy2(cdir / "spec.toml", specs / "spec.toml")
            r = subprocess.run([sys.executable, str(GEN / "fwgen_cli.py"), "gen", "--specs", str(specs), "--out", str(out)],
                               cwd=REPO, capture_output=True, text=True)
            if r.returncode != 0 or not (out / "spec.xlsx").is_file():
                raise SystemExit(f"{campaign}: fwgen gen failed:\n{r.stdout}\n{r.stderr}")
            if fg.workbook_sidecar_path(out / "spec.xlsx").exists():
                raise SystemExit(f"{campaign}: unexpected constraints companion")
            shutil.copy2(out / "spec.xlsx", cdir / "demo.xlsx")
        problems = fg.validate_workbook(cdir / "demo.xlsx")
        if problems:
            raise SystemExit(f"{campaign}: validate_workbook: {problems}")
        record["campaigns"][campaign] = {f: sha256((cdir / f).read_bytes()) for f in ("spec.toml", "demo.xlsx")}
    props_dest.parent.mkdir(parents=True, exist_ok=True)
    props_dest.write_text(core_props_text(), encoding="utf-8")
    record["core_props"] = {"template": str(CORE_TEMPLATE), "template_sha256": sha256(CORE_TEMPLATE.read_bytes()),
                            "edits": CORE_EDITS, "sha256": sha256(props_dest.read_bytes())}
    return record


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
            build(Path(tmp) / "spec", Path(tmp) / "core-b.fw.properties")
            diffs = [f"{c}/spec.toml" for c in ("B1", "B2")
                     if (SPEC_DIR / c / "spec.toml").read_bytes() != (Path(tmp) / "spec" / c / "spec.toml").read_bytes()]
            diffs += [f"{c}/demo.xlsx" for c in ("B1", "B2")
                      if workbook_content(SPEC_DIR / c / "demo.xlsx") != workbook_content(Path(tmp) / "spec" / c / "demo.xlsx")]
            diffs += ["config/core-b.fw.properties"] if CORE_PROPS.read_bytes() != (Path(tmp) / "core-b.fw.properties").read_bytes() else []
        print("spec/ and config/ match a fresh build" if not diffs else f"DRIFT: {diffs}")
        raise SystemExit(1 if diffs else 0)
    record = build(SPEC_DIR, CORE_PROPS)
    record.update({"schema": "d5b.build/v1", "contract": "B",
                   "core_props_diff": "".join(difflib.unified_diff(CORE_TEMPLATE.read_text().splitlines(True), CORE_PROPS.read_text().splitlines(True),
                                                                   "template", "core-b.fw.properties")),
                   "note": "demo.xlsx bytes carry zip timestamps; compare cell content with build_spec.py --check"})
    (SPEC_DIR / "build.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: record[k] for k in ("head_chars", "campaigns")}, indent=1))
    print(record["core_props_diff"])


if __name__ == "__main__":
    main()
