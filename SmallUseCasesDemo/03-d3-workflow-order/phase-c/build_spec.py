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

"""Build D3 phase C inputs: spec/full (the 1440-case benchmark) and spec/catalogue-SCA3 (planned only).

    python build_spec.py            # (re)write spec/ from the audited sources
    python build_spec.py --check    # compare spec/ with a fresh build; exit 1 on drift

full: OPS holds the six step() statements and the chain FW_Permut() -> FW_Combi(size) (a seq_extra
row; Core applies the last row for a sheet), IMPL the two policies: 720 x 2 = 1440 candidates.
catalogue-SCA3: the ten ordinary SCA3 rows of architect-derived.json as an explicit schedule sheet
(each value is one complete six-step schedule), x 2 policies = 20 candidates; planned, never run.
HEAD inlines sut.py, oracle.py and runtime.py (SHA-256 checked, own module namespaces).
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
POLICIES = ["correct", "late_restart"]
DERIVED = json.loads((HERE / "architect-derived.json").read_text())
VARIANTS = ("full", "catalogue-SCA3")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def module_sources():
    return {m: (HERE / f"{m}.py").read_text(encoding="utf-8") for m in MODULES}


def head_value(sources):
    digests = {m: sha256(s.encode("utf-8")) for m, s in sources.items()}
    lines = ["# D3 HEAD: audited sut.py, oracle.py, runtime.py inlined by build_spec.py.",
             "# Each source is checked against its SHA-256, then run in its own module namespace.",
             "import hashlib as _d3_hash, sys as _d3_sys, types as _d3_types",
             "_D3_SOURCES = {"]
    lines += [f"    {m!r}: {s!r}," for m, s in sources.items()]
    lines += ["}", "_D3_SHA256 = {"]
    lines += [f"    {m!r}: {d!r}," for m, d in digests.items()]
    lines += ["}",
              f"for _d3_name in {MODULES!r}:",
              "    _d3_src = _D3_SOURCES[_d3_name]",
              "    if _d3_hash.sha256(_d3_src.encode('utf-8')).hexdigest() != _D3_SHA256[_d3_name]:",
              "        raise RuntimeError('inlined %s.py does not match its recorded SHA-256' % _d3_name)",
              "    _d3_mod = _d3_types.ModuleType(_d3_name)",
              "    _d3_mod.__file__ = '<d3/%s.py>' % _d3_name",
              "    _d3_sys.modules[_d3_name] = _d3_mod",
              "    exec(compile(_d3_src, _d3_mod.__file__, 'exec'), _d3_mod.__dict__)",
              "d3 = _d3_sys.modules['runtime']",
              "d3.SOURCE_SHA256.update(_D3_SHA256)",
              "start, step, finish = d3.start, d3.step, d3.finish      # the names the fragments call",
              ""]
    return "\n".join(lines), digests


def variant(name, head):
    """(slots, seq_extra) for one spec. Every step value is a complete statement with its own newline."""
    slots = [("HEAD", [head], "", "FW_Combi(1)", [], "runtime definitions: audited sources, inlined; 1 value"),
             ("IMPL", [f'start("{p}")\n' for p in POLICIES], "", "FW_Combi(1)", [], "policy under test; 2 values")]
    if name == "full":
        slots.append(("OPS", [f'step("{o}")\n' for o in DERIVED["events"]], "", "FW_Permut()", [],
                      "the six events; FW_Permut() -> FW_Combi(size): all 720 orders"))
        extra = [["OPS", "FW_Permut()", "FW_Combi(size)"]]
    else:
        rows = DERIVED["suites"]["SCA3"]["rows"]
        slots.append(("SCHEDULE", ["".join(f'step("{o}")\n' for o in row) for row in rows], "", "FW_Combi(1)", [],
                      f"explicit catalogue: the {len(rows)} ordinary SCA3 schedules, one per value"))
        extra = [["SCHEDULE", "FW_Combi(1)", "FW_Combi(size)"]]
    tail = '_verdict = finish("C")\nFW_VAR = _verdict\nFW_CUSTOM_VAR = FW_VAR\n'
    slots.append(("TAIL", [tail], "", "FW_Combi(1)", [], "finalize observations, set the verdict; 1 value"))
    return slots, extra


CUSTOM_VAR_MSG = ("D3 phase-C contract violated at one or more checkpoints (IMPL position 2 is only the legacy "
                  "carrier, not a cause). Read failing_checkpoints in the observation record rec=.")


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


def render_toml(name, head, digests):
    slots, extra = variant(name, head)
    out = [LICENSE.rstrip(), "#", f"# D3 phase C, variant {name}: GENERATED by build_spec.py; do not edit.",
           "# Inlined source SHA-256:"] + [f"#   {m}.py {d}" for m, d in digests.items()]
    out += ["", 'spec_version = "1"',
            f"title = {t_str(f'D3 phase C, variant {name}: 2 billing policies x six-event orders')}",
            f"note = {t_str('03-d3-workflow-order/phase-c/CONTRACT.md. ' + ' -> '.join(extra[0][1:]) + ' on ' + extra[0][0] + '.')}",
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
    record = {"head_chars": len(head), "head_sha256": sha256(head.encode()), "module_sha256": digests, "variants": {}}
    for name in VARIANTS:
        vdir = dest / name
        vdir.mkdir(parents=True, exist_ok=True)
        text = render_toml(name, head, digests)
        parsed = tomllib.loads(text)
        slots, extra = variant(name, head)
        if [s["values"] for s in parsed["slots"]] != [s[1] for s in slots] or parsed["seq_extra"] != extra:
            raise SystemExit(f"{name}: TOML round-trip changed a value")
        (vdir / "spec.toml").write_text(text, encoding="utf-8")
        fg.load_spec(vdir / "spec.toml", strict=True)
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as tmp:
            specs, out = Path(tmp) / "specs", Path(tmp) / "wb"
            specs.mkdir()
            shutil.copy2(vdir / "spec.toml", specs / "spec.toml")
            r = subprocess.run([sys.executable, str(GEN / "fwgen_cli.py"), "gen", "--specs", str(specs), "--out", str(out)],
                               cwd=REPO, capture_output=True, text=True)
            if r.returncode != 0 or not (out / "spec.xlsx").is_file():
                raise SystemExit(f"{name}: fwgen gen failed:\n{r.stdout}\n{r.stderr}")
            if fg.workbook_sidecar_path(out / "spec.xlsx").exists():
                raise SystemExit(f"{name}: unexpected constraints companion")
            shutil.copy2(out / "spec.xlsx", vdir / "demo.xlsx")
        problems = fg.validate_workbook(vdir / "demo.xlsx")
        if problems:
            raise SystemExit(f"{name}: validate_workbook: {problems}")
        record["variants"][name] = {f: sha256((vdir / f).read_bytes()) for f in ("spec.toml", "demo.xlsx")}
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
            build(Path(tmp))
            diffs = [f"{v}/{f}" for v in VARIANTS for f in ("spec.toml",)
                     if (SPEC_DIR / v / f).read_bytes() != (Path(tmp) / v / f).read_bytes()]
            diffs += [f"{v}/demo.xlsx" for v in VARIANTS
                      if workbook_content(SPEC_DIR / v / "demo.xlsx") != workbook_content(Path(tmp) / v / "demo.xlsx")]
        print("spec/ matches a fresh build" if not diffs else f"DRIFT: {diffs}")
        raise SystemExit(1 if diffs else 0)
    record = build(SPEC_DIR)
    record.update({"schema": "d3c.build/v1", "contract": "phase-c",
                   "note": "demo.xlsx bytes carry zip timestamps; compare cell content with build_spec.py --check"})
    (SPEC_DIR / "build.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"head_chars": record["head_chars"], "variants": record["variants"]}, indent=1))


if __name__ == "__main__":
    main()
