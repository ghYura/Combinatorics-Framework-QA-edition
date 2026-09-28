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

"""Build D1's declarative input: spec/spec.toml, spec/demo.xlsx and its demo.constraints.json.

    python build_spec.py            # (re)write spec/ from the audited sources
    python build_spec.py --check    # compare spec/ with a fresh build; exit 1 on drift

The Framework does the enumeration. This script writes one catalogue per sheet
(CONTRACT.md §3) and two bonds. HEAD inlines sut.py, oracle.py and runtime.py as
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

POLICIES = ["volatile_transport", "durable_transport", "durable_order",
            "durable_payload", "durable_operation"]
CONTROLS = ["none", "retry_fresh_transport", "new_order_equal_payload",
            "new_operation_same_order", "conflicting_retry"]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def module_sources():
    return {m: (HERE / f"{m}.py").read_text(encoding="utf-8") for m in MODULES}


def head_value(sources):
    digests = {m: sha256(s.encode("utf-8")) for m, s in sources.items()}
    lines = ["# D1 HEAD: audited sut.py, oracle.py, runtime.py inlined by build_spec.py.",
             "# Each source is checked against its SHA-256, then run in its own module namespace.",
             "import hashlib as _d1_hash, sys as _d1_sys, types as _d1_types",
             "_D1_SOURCES = {"]
    lines += [f"    {m!r}: {s!r}," for m, s in sources.items()]
    lines += ["}", "_D1_SHA256 = {"]
    lines += [f"    {m!r}: {d!r}," for m, d in digests.items()]
    lines += ["}",
              f"for _d1_name in {MODULES!r}:",
              "    _d1_src = _D1_SOURCES[_d1_name]",
              "    if _d1_hash.sha256(_d1_src.encode('utf-8')).hexdigest() != _D1_SHA256[_d1_name]:",
              "        raise RuntimeError('inlined %s.py does not match its recorded SHA-256' % _d1_name)",
              "    _d1_mod = _d1_types.ModuleType(_d1_name)",
              "    _d1_mod.__file__ = '<d1/%s.py>' % _d1_name",
              "    _d1_sys.modules[_d1_name] = _d1_mod",
              "    exec(compile(_d1_src, _d1_mod.__file__, 'exec'), _d1_mod.__dict__)",
              "d1 = _d1_sys.modules['runtime']",
              "d1.SOURCE_SHA256.update(_D1_SHA256)",
              ""]
    return "\n".join(lines), digests


TAIL = ("_verdict = d1.emit(IMPL, L, [CUT1, CUT2], CONTROL)\n"
        "FW_VAR = _verdict\n"
        "FW_CUSTOM_VAR = FW_VAR\n")


def slots(head):
    """(sheet, values, ending, comment) in the contract's sheet order; every verb is FW_Combi(1).

    Catalogue values carry no surrounding whitespace; their newline is the FW_SheetNames
    ending that Core appends. The sieve strips database values but compares bond values
    verbatim, so a bonded value with a trailing newline would never match (see
    blockers/sieve-whitespace/). HEAD and TAIL are unbonded multi-line fragments."""
    return [
        ("HEAD", [head], "", "runtime definitions: audited sources, inlined; 1 value"),
        ("IMPL", [f'IMPL = "{p}"' for p in POLICIES], "\n", "policy under test; 5 values"),
        ("L1", ["L = [0]"], "\n", "delivery 1 always opens identity class 0; 1 value"),
        ("L2", ["L.append(0)", "L.append(1)"], "\n", "delivery 2 reuses class 0 or opens class 1; 2 values"),
        ("L3", ["L.append(0)", "L.append(1)", "L.append(2)"], "\n",
         "delivery 3 joins class 0 or 1, or opens class 2; 3 values"),
        ("CUT1", ["CUT1 = 0", "CUT1 = 1"], "\n", "restart before delivery 2; 2 values"),
        ("CUT2", ["CUT2 = 0", "CUT2 = 1"], "\n", "restart before delivery 3; 2 values"),
        ("CONTROL", [f'CONTROL = "{c}"' for c in CONTROLS], "\n", "peer control after the core; 5 values"),
        ("TAIL", [TAIL], "", "execute the case, emit the record, set the verdict; 1 value"),
    ]


def constraints():
    """The two bonds, in the contract's order. Values are the exact (whitespace-free) sheet values."""
    peers = [f'CONTROL = "{c}"' for c in CONTROLS[1:]]
    return [
        {"id": "canonical_identity", "polarity": "forbid",
         "desc": "Restricted-growth labels: delivery 3 cannot open class 2 unless delivery 2 opened class 1. "
                 "Keeps exactly 000, 001, 010, 011, 012 (Bell(3) = 5 partitions).",
         "sets": {"L2": ["L.append(0)"], "L3": ["L.append(2)"]}},
        {"id": "peer_baseline", "polarity": "forbid",
         "desc": "A peer control (CONTROL != none) is allowed only on labels=000 with no restart.",
         "assert": {"all": [
             {"sheet": "CONTROL", "in": peers},
             {"any": [{"sheet": "L2", "ne": "L.append(0)"},
                      {"sheet": "L3", "ne": "L.append(0)"},
                      {"sheet": "CUT1", "ne": "CUT1 = 0"},
                      {"sheet": "CUT2", "ne": "CUT2 = 0"}]}]}},
    ]


def bonded_values(node):
    """Every value string a bond compares against (sets members, in/ne/eq leaves)."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k in ("in", "ne", "eq") and isinstance(v, (str, list)):
                yield from ([v] if isinstance(v, str) else v)
            elif k == "sets":
                for vals in v.values():
                    yield from vals
            else:
                yield from bonded_values(v)
    elif isinstance(node, list):
        for x in node:
            yield from bonded_values(x)


CUSTOM_VAR_MSG = ("D1 contract violated for this case (IMPL position 2 is only the legacy carrier, "
                  "not a cause). Read the observation record rec= in the metrics line.")


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
           "# D1 durable idempotency: GENERATED by build_spec.py from sut.py, oracle.py and runtime.py.",
           "# Do not edit by hand; edit the sources and rebuild. Inlined source SHA-256:"]
    out += [f"#   {m}.py {d}" for m, d in digests.items()]
    out += ["", 'spec_version = "1"',
            f"title = {t_str('D1 durable idempotency: five dedup policies x identity partitions x restarts x peer controls')}",
            f"note = {t_str('Contract v1 (01-d1-idempotency/CONTRACT.md). Raw 600, 500 after canonical_identity, 120 after peer_baseline.')}",
            'args = ["noargs"]', ""]
    for sheet, values, ending, comment in slots(head):
        out += [f"[[slots]]   # {comment}", f'sheet = "{sheet}"', f'key = "{sheet.lower()}"',
                'verb = "FW_Combi(1)"', "raw = true"]
        out += [f"ending = {json.dumps(ending)}"] if ending else []
        out += [f"values = {t_val(values)}", ""]
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
    if got != expected or parsed["constraints"] != constraints():
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
    loaded = fg.load_spec(dest / "demo.xlsx")
    if [c["id"] for c in loaded.constraints] != [c["id"] for c in constraints()] or loaded.constraints != constraints():
        raise SystemExit(f"demo.xlsx does not load the two bonds from its companion: {loaded.constraints}")
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
    record.update({"schema": "d1.build/v1", "contract": "v1", "files_sha256": files,
                   "note": "demo.xlsx bytes carry zip timestamps; compare cell content with build_spec.py --check"})
    (SPEC_DIR / "build.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: record[k] for k in ("head_chars", "files_sha256")}, indent=2))


if __name__ == "__main__":
    main()
