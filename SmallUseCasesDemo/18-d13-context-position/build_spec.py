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


"""Build D13e inputs: spec/{spec.toml, demo.xlsx}; the XLSX is the run input (no rules, no companion).

    python build_spec.py            # (re)write spec/ from the audited sources
    python build_spec.py --check    # compare spec/ with a fresh build; exit 1 on drift

Sheets HEAD, IMPL (position 2), TASK, ORDER, TAIL; every slot uses the explicit chain
FW_Combi(1) -> FW_Combi(size). Atoms (impl("p"); task("t"); set_order("XXXXXX");) are
whitespace-free; their newline is the FW_SheetNames ending. ORDER is the certified catalogue: the
eight SCA3 orders of coverage.json, in its order, then the preregistered position control ABGCDE
(nine atoms; no 54 prebuilt programs). Product 1 x 3 x 2 x 9 x 1 = 54; no sieve, no optional axis.
HEAD inlines processor.py, judge.py, oracle.py and runtime.py, each checked against its SHA-256.
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
MODULES = ("processor", "judge", "oracle", "runtime")
EXCEL_CELL_LIMIT = 32767
LICENSE = (HERE / "processor.py").read_text(encoding="utf-8").split('\n"""', 1)[0].rstrip() + "\n"
POLICIES = ["stable", "last_marker", "third_position"]
TASKS = ["public", "secret"]
SUPPLEMENT = "ABGCDE"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def catalogue():
    """The nine orders: the frozen SCA3 cover (coverage.json order), then the position control."""
    cover = json.loads((HERE / "coverage.json").read_text(encoding="utf-8"))["orders"]
    if len(cover) != 8 or SUPPLEMENT in cover:
        raise SystemExit("coverage.json does not hold the eight-order cover without the supplement")
    return cover + [SUPPLEMENT]


def head_value(sources):
    digests = {m: sha256(s.encode("utf-8")) for m, s in sources.items()}
    lines = ["# D13e HEAD: audited processor.py, judge.py, oracle.py, runtime.py inlined by build_spec.py.",
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
              "    _d13_mod.__file__ = '<d13e/%s.py>' % _d13_name",
              "    _d13_sys.modules[_d13_name] = _d13_mod",
              "    exec(compile(_d13_src, _d13_mod.__file__, 'exec'), _d13_mod.__dict__)",
              "d13 = _d13_sys.modules['runtime']",
              "d13.SOURCE_SHA256.update(_D13_SHA256)",
              "impl, task, set_order, finish = d13.impl, d13.task, d13.set_order, d13.finish      # the atoms the fragments call",
              "d13.begin()",
              ""]
    return "\n".join(lines), digests


def layout(head):
    """(slots, seq_extra); slot = (sheet, values, ending, verb, flags, comment)."""
    slots = [("HEAD", [head], "", "FW_Combi(1)", [], "runtime definitions: audited sources, inlined; 1 value"),
             ("IMPL", [f'impl("{p}");' for p in POLICIES], "\n", "FW_Combi(1)", [], "context processor policy; 3 values (legacy verdict carrier)"),
             ("TASK", [f'task("{t}");' for t in TASKS], "\n", "FW_Combi(1)", [], "labelled task; public requires ALLOW, secret DENY; 2 values"),
             ("ORDER", [f'set_order("{o}");' for o in catalogue()], "\n", "FW_Combi(1)", [],
              "certified catalogue: 8 SCA3 orders (coverage.json) + position control ABGCDE; 9 values"),
             ("TAIL", ["_verdict = finish()\nFW_VAR = _verdict\nFW_CUSTOM_VAR = FW_VAR\n"], "", "FW_Combi(1)", [],
              "run the 20 internal trials, judge mechanically, set the verdict; 1 value")]
    extra = [[s_[0], "FW_Combi(1)", "FW_Combi(size)"] for s_ in slots]
    return slots, extra


CUSTOM_VAR_MSG = ("D13e: at least one of the 20 internal processor decisions violates the task truth (IMPL position 2 "
                  "is only the legacy carrier, not a cause). Read failing_trials and trials[] in the observation record rec=.")


# ---- minimal TOML emitter (no third-party writer); tomllib round-trip checks it ----
def t_str(s):
    if "'''" not in s and "\r" not in s and not s.startswith("\n") and all(
            c == "\n" or c == "\t" or ord(c) >= 0x20 for c in s) and "\x7f" not in s:
        return "'''" + s + "'''" if "\n" in s else "'" + s + "'" if "'" not in s else json.dumps(s, ensure_ascii=False)
    return json.dumps(s, ensure_ascii=False)       # a JSON string is a valid TOML basic string


def t_val(v):
    if isinstance(v, str):
        return t_str(v)
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, list):
        return "[" + ", ".join(t_val(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{json.dumps(k)} = {t_val(x)}" for k, x in v.items()) + " }"
    raise TypeError(type(v))


def render_toml(head, digests):
    slots, extra = layout(head)
    out = [LICENSE.rstrip(), "#", "# D13e context order and noisy judges: GENERATED by build_spec.py; do not edit.",
           "# Inlined source SHA-256:"] + [f"#   {m}.py {d}" for m, d in digests.items()]
    out += ["", 'spec_version = "1"',
            f"title = {t_str('D13e context position: 3 processors x 2 tasks x 9 certified orders, 20 internal trials each')}",
            f"note = {t_str('18-d13-context-position/CONTRACT.md. Local deterministic fixture; no rules, no optional axis.')}",
            'args = ["noargs"]',
            "# Multi-verb FW_Seq rows (the expert chain form); Core applies the last row for a sheet.",
            f"seq_extra = {t_val(extra)}", ""]
    for sheet, values, ending, verb, flags, comment in slots:
        out += [f"[[slots]]   # {comment}", f'sheet = "{sheet}"', f'key = "{sheet.lower()}"', f"verb = {t_str(verb)}", "raw = true"]
        out += [f"flags = {t_val(flags)}"] if flags else []
        out += [f"ending = {json.dumps(ending)}"] if ending else []
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
    x, t = fg.load_spec(dest / "demo.xlsx"), fg.load_spec(dest / "spec.toml")
    if x.constraints or t.constraints or x.params or t.params or x.sidecar_path:
        raise SystemExit("D13e carries no bonds, params or companion")
    files = ("spec.toml", "demo.xlsx")
    return {"head_chars": len(head), "head_sha256": sha256(head.encode()), "module_sha256": digests,
            "orders": catalogue(), "files": {f: sha256((dest / f).read_bytes()) for f in files}}


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
            diffs = [f for f in ("spec.toml",) if not (SPEC_DIR / f).exists() or (SPEC_DIR / f).read_bytes() != (Path(tmp) / f).read_bytes()]
            diffs += ["demo.xlsx"] if workbook_content(SPEC_DIR / "demo.xlsx") != workbook_content(Path(tmp) / "demo.xlsx") else []
        print("spec/ matches a fresh build" if not diffs else f"DRIFT: {diffs}")
        raise SystemExit(1 if diffs else 0)
    record = build(SPEC_DIR)
    record.update({"schema": "d13e.build/v1", "contract": "v1",
                   "note": "demo.xlsx bytes carry zip timestamps; compare cell content with build_spec.py --check"})
    (SPEC_DIR / "build.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"head_chars": record["head_chars"], "files": record["files"]}, indent=1))


if __name__ == "__main__":
    main()
