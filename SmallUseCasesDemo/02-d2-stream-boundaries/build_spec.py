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

"""Build D2's declarative input: spec/spec.toml, spec/demo.xlsx and its demo.constraints.json.

    python build_spec.py            # (re)write spec/ from the audited sources
    python build_spec.py --check    # compare spec/ with a fresh build; exit 1 on drift

The Framework does the enumeration. This script writes one catalogue per sheet
(CONTRACT.md "Framework input"), params (payload length n, cut bit) and five bonds. HEAD inlines sut.py, oracle.py and runtime.py as
string literals; each is checked against its SHA-256 before it runs in its own
module namespace, so candidates are self-contained for the `generated-default`
container profile. The TOML is compiled to XLSX by the repository's own fwgen
CLI, which also writes the workbook's constraint companion; this script never
writes workbook cells or the companion's rules itself, it only renames both.
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
MODULES = ("sut", "oracle", "runtime")        # load order: runtime imports the other two
EXCEL_CELL_LIMIT = 32767
LICENSE = (HERE / "sut.py").read_text(encoding="utf-8").split('\n"""', 1)[0].rstrip() + "\n"

ADAPTERS = ["incremental", "per_chunk", "no_final"]
PAYLOAD_LEN = {"ascii": 3, "euro": 5, "emoji": 4, "truncated_utf8": 3, "bom_utf16": 6, "truncated_utf16": 5}
ERRORS = ["strict", "replace"]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def module_sources():
    return {m: (HERE / f"{m}.py").read_text(encoding="utf-8") for m in MODULES}


def head_value(sources):
    digests = {m: sha256(s.encode("utf-8")) for m, s in sources.items()}
    lines = ["# D2 HEAD: audited sut.py, oracle.py, runtime.py inlined by build_spec.py.",
             "# Each source is checked against its SHA-256, then run in its own module namespace.",
             "import hashlib as _d2_hash, sys as _d2_sys, types as _d2_types",
             "_D2_SOURCES = {"]
    lines += [f"    {m!r}: {s!r}," for m, s in sources.items()]
    lines += ["}", "_D2_SHA256 = {"]
    lines += [f"    {m!r}: {d!r}," for m, d in digests.items()]
    lines += ["}",
              f"for _d2_name in {MODULES!r}:",
              "    _d2_src = _D2_SOURCES[_d2_name]",
              "    if _d2_hash.sha256(_d2_src.encode('utf-8')).hexdigest() != _D2_SHA256[_d2_name]:",
              "        raise RuntimeError('inlined %s.py does not match its recorded SHA-256' % _d2_name)",
              "    _d2_mod = _d2_types.ModuleType(_d2_name)",
              "    _d2_mod.__file__ = '<d2/%s.py>' % _d2_name",
              "    _d2_sys.modules[_d2_name] = _d2_mod",
              "    exec(compile(_d2_src, _d2_mod.__file__, 'exec'), _d2_mod.__dict__)",
              "d2 = _d2_sys.modules['runtime']",
              "d2.SOURCE_SHA256.update(_D2_SHA256)",
              ""]
    return "\n".join(lines), digests


TAIL = ("_verdict = d2.emit(IMPL, PAYLOAD, ERRORS, [CUT1, CUT2, CUT3, CUT4, CUT5])\n"
        "FW_VAR = _verdict\n"
        "FW_CUSTOM_VAR = FW_VAR\n")


def slots(head):
    """(sheet, values, ending, comment) in the contract's sheet order; every verb is FW_Combi(1).

    Bonded values carry no surrounding whitespace; their newline is the FW_SheetNames ending."""
    rows = [("HEAD", [head], "", "runtime definitions: audited sources, inlined; 1 value"),
            ("IMPL", [f'IMPL = "{a}"' for a in ADAPTERS], "\n", "decoding adapter under test; 3 values"),
            ("PAYLOAD", [f'PAYLOAD = "{p}"' for p in PAYLOAD_LEN], "\n", "frozen payload id; 6 values"),
            ("ERRORS", [f'ERRORS = "{e}"' for e in ERRORS], "\n", "error policy; 2 values")]
    rows += [(f"CUT{i}", [f"CUT{i} = 0", f"CUT{i} = 1"], "\n", f"cut after byte {i}: 0/1; 2 values")
             for i in range(1, 6)]
    rows.append(("TAIL", [TAIL], "", "segment, decode, judge, emit, set the verdict; 1 value"))
    return rows


def params():
    """Value metadata for the bonds: payload length n, and each cut's bit."""
    rows = [{"sheet": "PAYLOAD", "value": f'PAYLOAD = "{p}"', "n": n} for p, n in PAYLOAD_LEN.items()]
    rows += [{"sheet": f"CUT{i}", "value": f"CUT{i} = {b}", "bit": b} for i in range(1, 6) for b in (0, 1)]
    return rows


def constraints():
    """Five require bonds: a cut after byte i exists only when the payload is longer than i."""
    return [{"id": f"real_boundary_{i}", "polarity": "require", "sheets": ["PAYLOAD", f"CUT{i}"],
             "when": f"CUT{i}.bit == 0 or PAYLOAD.n > {i}",
             "desc": f"CUT{i}=1 (a cut after byte {i}) only when the payload has more than {i} bytes"}
            for i in range(1, 6)]


def bonded_values(_node):
    """Every value string the bonds depend on: the params keys (the `when` bodies use params)."""
    for row in params():
        yield row["value"]


CUSTOM_VAR_MSG = ("D2 contract violated for this case (IMPL position 2 is only the legacy carrier, "
                  "not a cause). Read failure_class in the observation record rec=.")


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
    out = [LICENSE.rstrip(), "#",
           "# D2 streaming boundaries: GENERATED by build_spec.py from sut.py, oracle.py and runtime.py.",
           "# Do not edit by hand; edit the sources and rebuild. Inlined source SHA-256:"]
    out += [f"#   {m}.py {d}" for m, d in digests.items()]
    out += ["", 'spec_version = "1"',
            f"title = {t_str('D2 streaming boundaries: 3 decoding adapters x 6 frozen payloads x 2 error policies x 5 cut bits')}",
            f"note = {t_str('Contract v1 (02-d2-stream-boundaries/CONTRACT.md). Raw 1152, 480 after the five real_boundary bonds.')}",
            'args = ["noargs"]', ""]
    for sheet, values, ending, comment in slots(head):
        out += [f"[[slots]]   # {comment}", f'sheet = "{sheet}"', f'key = "{sheet.lower()}"',
                'verb = "FW_Combi(1)"', "raw = true"]
        out += [f"ending = {json.dumps(ending)}"] if ending else []
        out += [f"values = {t_val(values)}", ""]
    for row in params():
        out += ["[[params]]"] + [f"{k} = {t_val(v)}" for k, v in row.items()] + [""]
    for c in constraints():
        out += ["[[constraints]]"] + [f"{k} = {t_val(v)}" for k, v in c.items()] + [""]
    out += ["[[custom_vars]]", "code = 2", f"msg = {t_str(CUSTOM_VAR_MSG)}", ""]
    return "\n".join(out)


def build(dest: Path):
    """Write spec.toml, the sidecar and demo.xlsx into `dest`; return the build record."""
    sources = module_sources()
    head, digests = head_value(sources)
    if len(head) > EXCEL_CELL_LIMIT:
        raise SystemExit(f"HEAD is {len(head)} characters; an XLSX cell holds at most {EXCEL_CELL_LIMIT}")
    toml_text = render_toml(head, digests)
    parsed = tomllib.loads(toml_text)
    expected = {s: (v, e) for s, v, e, _ in slots(head)}
    got = {s["sheet"]: (s["values"], s.get("ending", "")) for s in parsed["slots"]}
    if got != expected or parsed["constraints"] != constraints() or parsed["params"] != params():
        raise SystemExit("TOML round-trip changed a value")
    catalogue = {s: v for s, v, e, _ in slots(head)}
    for value in bonded_values(constraints()):
        if value != value.strip() or not any(value in vals for vals in catalogue.values()):
            raise SystemExit(f"bond value {value!r} is not an exact, whitespace-free sheet value")
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "spec.toml").write_text(toml_text, encoding="utf-8")
    sys.path.insert(0, str(GEN))
    import fwgen as fg
    fg.load_spec(dest / "spec.toml", strict=True)
    with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as tmp:
        specs, out = Path(tmp) / "specs", Path(tmp) / "wb"
        specs.mkdir()
        shutil.copy2(dest / "spec.toml", specs / "spec.toml")
        cmd = [sys.executable, str(GEN / "fwgen_cli.py"), "gen", "--specs", str(specs), "--out", str(out)]
        r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
        companion = fg.workbook_sidecar_path(out / "spec.xlsx")
        if r.returncode != 0 or not (out / "spec.xlsx").is_file() or not companion.is_file():
            raise SystemExit(f"fwgen gen failed or wrote no constraints companion:\n{r.stdout}\n{r.stderr}")
        # The workbook is renamed, so its companion takes the new stem with it (demo.constraints.json).
        shutil.copy2(out / "spec.xlsx", dest / "demo.xlsx")
        shutil.copy2(companion, fg.workbook_sidecar_path(dest / "demo.xlsx"))
    problems = fg.validate_workbook(dest / "demo.xlsx")
    if problems:
        raise SystemExit(f"fwgen validate_workbook: {problems}")
    loaded, toml_spec = fg.load_spec(dest / "demo.xlsx"), fg.load_spec(dest / "spec.toml")
    if loaded.constraints != constraints() or loaded.params != toml_spec.params or not loaded.params:
        raise SystemExit(f"demo.xlsx does not load the five bonds and params from its companion")
    return {"head_chars": len(head), "head_sha256": sha256(head.encode("utf-8")),
            "module_sha256": digests, "fwgen_command": ["python", "generator_trunk/fwgen_cli.py", "gen",
                                                        "--specs", "<dir holding spec.toml>", "--out", "<dir>"],
            "fwgen_stdout": r.stdout.strip().splitlines()}


def workbook_content(path: Path):
    """Sheet names and every cell, via fwgen's own lossless reader (ignores zip timestamps)."""
    sys.path.insert(0, str(GEN))
    import fwgen as fg
    return fg.workbook_to_json(path)["sheets"]


def compare(a: Path, b: Path):
    diffs = []
    for name in ("spec.toml", "demo.constraints.json"):
        if (a / name).read_bytes() != (b / name).read_bytes():
            diffs.append(name)
    if workbook_content(a / "demo.xlsx") != workbook_content(b / "demo.xlsx"):
        diffs.append("demo.xlsx (cell content)")
    return diffs


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="compare spec/ with a fresh build; write nothing")
    a = ap.parse_args()
    if a.check:
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as tmp:
            build(Path(tmp))
            diffs = compare(SPEC_DIR, Path(tmp))
        print("spec/ matches a fresh build" if not diffs else f"DRIFT: {diffs}")
        raise SystemExit(1 if diffs else 0)
    record = build(SPEC_DIR)
    files = {n: sha256((SPEC_DIR / n).read_bytes()) for n in ("spec.toml", "demo.constraints.json", "demo.xlsx")}
    record.update({"schema": "d2.build/v1", "contract": "v1", "files_sha256": files,
                   "note": "demo.xlsx bytes carry zip timestamps; compare cell content with build_spec.py --check"})
    (SPEC_DIR / "build.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: record[k] for k in ("head_chars", "files_sha256")}, indent=2))


if __name__ == "__main__":
    main()
