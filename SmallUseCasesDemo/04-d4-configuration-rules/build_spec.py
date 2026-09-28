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

"""Build D4 inputs: spec/main (sieved, XLSX + native companion) and spec/controls (unsieved catalogue).

    python build_spec.py            # (re)write spec/ from the audited sources
    python build_spec.py --check    # compare spec/ with a fresh build; exit 1 on drift

Atoms (impl("x"); env("x"); ...) are whitespace-free; their newline is the FW_SheetNames ending, so
the workbook, params and bonds all name the same strings. FEATURES is FW_Combi(2) -> FW_Combi(size);
every other sheet uses an explicit FW_Combi(1) -> FW_Combi(size) identity chain (seq_extra rows);
DEBUG is FW_Optional. The six legality bonds R1-R6 follow CONTRACT.md in order (R6 is deferred to
the Reader because it touches the optional DEBUG sheet). controls: an explicit CONFIG catalogue of
the six preregistered invalid configurations, no bonds. HEAD inlines sut.py, oracle.py, runtime.py.
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
POLICIES = ["correct", "drops_gzip", "ignores_debug_rule"]
DERIVED = json.loads((HERE / "architect-derived.json").read_text())
VARIANTS = ("main", "controls")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def module_sources():
    return {m: (HERE / f"{m}.py").read_text(encoding="utf-8") for m in MODULES}


def head_value(sources):
    digests = {m: sha256(s.encode("utf-8")) for m, s in sources.items()}
    lines = ["# D4 HEAD: audited sut.py, oracle.py, runtime.py inlined by build_spec.py.",
             "# Each source is checked against its SHA-256, then run in its own module namespace.",
             "import hashlib as _d4_hash, sys as _d4_sys, types as _d4_types",
             "_D4_SOURCES = {"]
    lines += [f"    {m!r}: {s!r}," for m, s in sources.items()]
    lines += ["}", "_D4_SHA256 = {"]
    lines += [f"    {m!r}: {d!r}," for m, d in digests.items()]
    lines += ["}",
              f"for _d4_name in {MODULES!r}:",
              "    _d4_src = _D4_SOURCES[_d4_name]",
              "    if _d4_hash.sha256(_d4_src.encode('utf-8')).hexdigest() != _D4_SHA256[_d4_name]:",
              "        raise RuntimeError('inlined %s.py does not match its recorded SHA-256' % _d4_name)",
              "    _d4_mod = _d4_types.ModuleType(_d4_name)",
              "    _d4_mod.__file__ = '<d4/%s.py>' % _d4_name",
              "    _d4_sys.modules[_d4_name] = _d4_mod",
              "    exec(compile(_d4_src, _d4_mod.__file__, 'exec'), _d4_mod.__dict__)",
              "d4 = _d4_sys.modules['runtime']",
              "d4.SOURCE_SHA256.update(_D4_SHA256)",
              "impl, env, mode, transport, feature, workers, debug, finish = (d4.impl, d4.env, d4.mode, d4.transport, "
              "d4.feature, d4.workers, d4.debug, d4.finish)      # the atoms the fragments call",
              ""]
    return "\n".join(lines), digests


def atom(fn, arg):
    return f"{fn}({json.dumps(arg) if isinstance(arg, str) else arg});"


def variant(name, head):
    """(slots, seq_extra) for one spec; slot = (sheet, values, ending, verb, flags, comment)."""
    slots = [("HEAD", [head], "", "FW_Combi(1)", [], "runtime definitions: audited sources, inlined; 1 value"),
             ("IMPL", [atom("impl", p) for p in POLICIES], "\n", "FW_Combi(1)", [], "adapter policy; 3 values")]
    if name == "main":
        slots += [("ENV", [atom("env", v) for v in ("dev", "prod")], "\n", "FW_Combi(1)", [], "environment; 2 values"),
                  ("MODE", [atom("mode", v) for v in ("batch", "live")], "\n", "FW_Combi(1)", [], "mode; 2 values"),
                  ("TRANSPORT", [atom("transport", v) for v in ("http", "https")], "\n", "FW_Combi(1)", [], "transport; 2 values"),
                  ("FEATURES", [atom("feature", v) for v in ("audit", "cache", "gzip")], "\n", "FW_Combi(2)", [],
                   "exactly two distinct features: FW_Combi(2) -> FW_Combi(size), 3 unordered pairs"),
                  ("WORKERS", [atom("workers", n) for n in (1, 2)], "\n", "FW_Combi(1)", [], "workers; 2 values"),
                  ("DEBUG", ["debug();"], "\n", "FW_Combi(1)", ["FW_Optional"], "optional DEBUG; absent = false")]
        extra = [[s_, "FW_Combi(1)", "FW_Combi(size)"] for s_ in ("IMPL", "ENV", "MODE", "TRANSPORT", "WORKERS")]
        extra += [["FEATURES", "FW_Combi(2)", "FW_Combi(size)"], ["DEBUG", "FW_Optional", "FW_Combi(1)", "FW_Combi(size)"]]
    else:
        rows = []
        for c in DERIVED["invalid_controls"]:
            parts = [atom("env", c["env"]), atom("mode", c["mode"]), atom("transport", c["transport"]),
                     *(atom("feature", f) for f in c["features"]), atom("workers", c["workers"])]
            rows.append("".join(parts + (["debug();"] if c["debug"] else [])))
        slots.append(("CONFIG", rows, "\n", "FW_Combi(1)", [], "the six preregistered invalid configurations (controls only)"))
        extra = [[s_, "FW_Combi(1)", "FW_Combi(size)"] for s_ in ("IMPL", "CONFIG")]
    tail = f'_verdict = finish("{name}")\nFW_VAR = _verdict\nFW_CUSTOM_VAR = FW_VAR\n'
    slots.append(("TAIL", [tail], "", "FW_Combi(1)", [], "adapt, judge, emit, set the verdict; 1 value"))
    return slots, extra


def params():
    return ([{"sheet": "MODE", "value": atom("mode", v), "live": int(v == "live")} for v in ("batch", "live")]
            + [{"sheet": "WORKERS", "value": atom("workers", n), "n": n} for n in (1, 2)])


ORDERS = {"WORKERS": ["workers(1);", "workers(2);"]}


def constraints():
    return [
        {"id": "R1", "polarity": "forbid", "sheets": ["ENV", "TRANSPORT"],
         "pairs": [{"ENV": 'env("prod");', "TRANSPORT": 'transport("http");'}], "desc": "prod with http"},
        {"id": "R2", "polarity": "forbid", "sets": {"MODE": ['mode("live");'], "FEATURES": ['feature("cache");']},
         "desc": "live with cache selected"},
        {"id": "R3", "polarity": "require", "sheets": ["MODE", "WORKERS"], "when": "MODE.live == 0 or WORKERS.n >= 2",
         "desc": "live needs workers >= 2"},
        {"id": "R4", "polarity": "require", "mapping": {"source": "ENV", "target": "FEATURES",
                                                        "allow": {'env("prod");': ['feature("audit");', 'feature("gzip");']}},
         "desc": "prod allows only audit and gzip; dev unconstrained"},
        {"id": "R5", "polarity": "require", "assert": {"sheet": "WORKERS", "ge": "workers(2);"},
         "condition": {"all": [{"sheet": "MODE", "eq": 'mode("batch");'}, {"sheet": "FEATURES", "has": 'feature("audit");'}]},
         "desc": "batch with audit needs workers >= 2 (ordinal)"},
        {"id": "R6", "polarity": "forbid", "sheets": ["ENV", "DEBUG"], "pairs": [{"ENV": 'env("prod");', "DEBUG": "debug();"}],
         "desc": "prod with DEBUG present (deferred to the Reader)"},
    ]


CUSTOM_VAR_MSG = ("D4 contract violated at one or more checkpoints (IMPL position 2 is only the legacy "
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
    out = [LICENSE.rstrip(), "#", f"# D4 configuration rules, variant {name}: GENERATED by build_spec.py; do not edit.",
           "# Inlined source SHA-256:"] + [f"#   {m}.py {d}" for m, d in digests.items()]
    out += ["", 'spec_version = "1"',
            f"title = {t_str(f'D4 configuration legality, variant {name}')}",
            f"note = {t_str('04-d4-configuration-rules/CONTRACT.md; 3 adapter policies.')}",
            'args = ["noargs"]',
            "# Multi-verb FW_Seq rows (the expert chain form); Core applies the last row for a sheet.",
            f"seq_extra = {t_val(extra)}"] + ([f"orders = {t_val(ORDERS)}"] if name == "main" else []) + [""]
    for sheet, values, ending, verb, flags, comment in slots:
        out += [f"[[slots]]   # {comment}", f'sheet = "{sheet}"', f'key = "{sheet.lower()}"', f"verb = {t_str(verb)}", "raw = true"]
        out += [f"flags = {t_val(flags)}"] if flags else []
        out += [f"ending = {json.dumps(ending)}"] if ending else []
        out += [f"values = {t_val(values)}", ""]
    if name == "main":
        for row in params():
            out += ["[[params]]"] + [f"{k} = {t_val(v)}" for k, v in row.items()] + [""]
        for c in constraints():
            out += ["[[constraints]]"] + [f"{k} = {t_val(v)}" for k, v in c.items()] + [""]
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
            companion = fg.workbook_sidecar_path(out / "spec.xlsx")
            if companion.exists() != (name == "main"):
                raise SystemExit(f"{name}: constraints companion {'missing' if name == 'main' else 'unexpected'}")
            shutil.copy2(out / "spec.xlsx", vdir / "demo.xlsx")
            if name == "main":
                shutil.copy2(companion, fg.workbook_sidecar_path(vdir / "demo.xlsx"))
        problems = fg.validate_workbook(vdir / "demo.xlsx")
        if problems:
            raise SystemExit(f"{name}: validate_workbook: {problems}")
        if name == "main":
            x, t = fg.load_spec(vdir / "demo.xlsx"), fg.load_spec(vdir / "spec.toml")
            if x.constraints != constraints() or x.params != t.params or x.orders != ORDERS or t.orders != ORDERS:
                raise SystemExit("main: XLSX companion and TOML do not carry the same six bonds, params and orders")
        files = ("spec.toml", "demo.xlsx") + (("demo.constraints.json",) if name == "main" else ())
        record["variants"][name] = {f: sha256((vdir / f).read_bytes()) for f in files}
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
            diffs = [f"{v}/{f}" for v in VARIANTS for f in ("spec.toml", "demo.constraints.json")
                     if (SPEC_DIR / v / f).exists() != (Path(tmp) / v / f).exists()
                     or ((SPEC_DIR / v / f).exists() and (SPEC_DIR / v / f).read_bytes() != (Path(tmp) / v / f).read_bytes())]
            diffs += [f"{v}/demo.xlsx" for v in VARIANTS
                      if workbook_content(SPEC_DIR / v / "demo.xlsx") != workbook_content(Path(tmp) / v / "demo.xlsx")]
        print("spec/ matches a fresh build" if not diffs else f"DRIFT: {diffs}")
        raise SystemExit(1 if diffs else 0)
    record = build(SPEC_DIR)
    record.update({"schema": "d4.build/v1", "contract": "v1",
                   "note": "demo.xlsx bytes carry zip timestamps; compare cell content with build_spec.py --check"})
    (SPEC_DIR / "build.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"head_chars": record["head_chars"], "variants": record["variants"]}, indent=1))


if __name__ == "__main__":
    main()
