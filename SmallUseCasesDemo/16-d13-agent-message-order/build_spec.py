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


"""Build D13c inputs: spec/{spec.toml, demo.xlsx, demo.constraints.json}; the XLSX + companion is the run input.

    python build_spec.py            # (re)write spec/ from the audited sources
    python build_spec.py --check    # compare spec/ with a fresh build; exit 1 on drift

Sheets HEAD, IMPL (position 2), MODE, CAP, S1..S4, TAIL; every configuration slot uses the explicit
chain FW_Combi(1) -> FW_Combi(size). Atoms (impl("x"); mode("x"); cap(n); set_step(i,"A");) are
whitespace-free; their newline is the FW_SheetNames ending, so the workbook, params and bonds name
the same strings. Each S1..S4 selects its agent independently; no complete schedule is listed
anywhere. Raw product 3 x 2 x 3 x 2^4 = 288. Bonds, in order (CONTRACT.md): two_each, causal_ready,
preemption_cap (require-when). HEAD inlines sut.py, oracle.py and runtime.py, each checked against
its SHA-256.
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
POLICIES = ["compare_version", "trust_offer", "overwrite_owner"]
MODES = {"independent": 0, "after_A_offer": 1}      # MODE.wait
STEPS = ("S1", "S2", "S3", "S4")
PREEMPTION_EXPR = ("int(S1.a != S2.a) + int(S2.a != S3.a and S1.a != S2.a) "
                   "+ int(S3.a != S4.a and S1.a != S3.a and S2.a != S3.a)")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def head_value(sources):
    digests = {m: sha256(s.encode("utf-8")) for m, s in sources.items()}
    lines = ["# D13c HEAD: audited sut.py, oracle.py, runtime.py inlined by build_spec.py.",
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
              "    _d13_mod.__file__ = '<d13c/%s.py>' % _d13_name",
              "    _d13_sys.modules[_d13_name] = _d13_mod",
              "    exec(compile(_d13_src, _d13_mod.__file__, 'exec'), _d13_mod.__dict__)",
              "d13 = _d13_sys.modules['runtime']",
              "d13.SOURCE_SHA256.update(_D13_SHA256)",
              "impl, mode, cap, set_step, finish = d13.impl, d13.mode, d13.cap, d13.set_step, d13.finish      # the atoms the fragments call",
              "d13.begin()",
              ""]
    return "\n".join(lines), digests


def step_atom(i, t):
    return f'set_step({i},"{t}");'


def layout(head):
    """(slots, seq_extra); slot = (sheet, values, ending, verb, flags, comment)."""
    slots = [("HEAD", [head], "", "FW_Combi(1)", [], "runtime definitions: audited sources, inlined; 1 value"),
             ("IMPL", [f'impl("{p}");' for p in POLICIES], "\n", "FW_Combi(1)", [], "coordinator policy; 3 values (legacy verdict carrier)"),
             ("MODE", [f'mode("{m}");' for m in MODES], "\n", "FW_Combi(1)", [], "negotiation dependency; 2 values"),
             ("CAP", [f"cap({n});" for n in (0, 1, 2)], "\n", "FW_Combi(1)", [], "preemption bound; 3 values")]
    for i, s_ in enumerate(STEPS, start=1):
        slots.append((s_, [step_atom(i, t) for t in "AB"], "\n", "FW_Combi(1)", [], f"agent of delivery {i}; 2 values"))
    slots.append(("TAIL", ["_verdict = finish()\nFW_VAR = _verdict\nFW_CUSTOM_VAR = FW_VAR\n"], "", "FW_Combi(1)", [],
                  "deliver the schedule, judge it, set the verdict; 1 value"))
    extra = [[s_[0], "FW_Combi(1)", "FW_Combi(size)"] for s_ in slots]
    return slots, extra


def params():
    rows = [{"sheet": "MODE", "value": f'mode("{m}");', "wait": w} for m, w in MODES.items()]
    rows += [{"sheet": "CAP", "value": f"cap({n});", "n": n} for n in (0, 1, 2)]
    rows += [{"sheet": s_, "value": step_atom(i, t), "a": int(t == "A")} for i, s_ in enumerate(STEPS, start=1) for t in "AB"]
    return rows


def constraints():
    return [
        {"id": "two_each", "polarity": "require", "sheets": list(STEPS), "when": "S1.a + S2.a + S3.a + S4.a == 2",
         "desc": "each agent delivers exactly two messages (A has a=1, B has a=0)"},
        {"id": "causal_ready", "polarity": "require", "sheets": ["MODE", "S1"], "when": "MODE.wait == 0 or S1.a == 1",
         "desc": "after_A_offer: B.inspect only after A's offer, which for this fixture is exactly 'A delivers first'"},
        {"id": "preemption_cap", "polarity": "require", "sheets": ["CAP", *STEPS], "when": f"{PREEMPTION_EXPR} <= CAP.n",
         "desc": "preemptions (switches away from an agent whose commit is still undelivered) within the cap"},
    ]


CUSTOM_VAR_MSG = ("D13c: a reservation or promise check failed at one or more checkpoints (IMPL position 2 is only the "
                  "legacy carrier, not a cause). Read checks/failing_checkpoints in the observation record rec=.")


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
    out = [LICENSE.rstrip(), "#", "# D13c bounded agent-message interleavings: GENERATED by build_spec.py; do not edit.",
           "# Inlined source SHA-256:"] + [f"#   {m}.py {d}" for m, d in digests.items()]
    out += ["", 'spec_version = "1"',
            f"title = {t_str('D13c agent message interleavings: 3 coordinators x 2 modes x 3 caps x 2^4 position slots, sieved')}",
            f"note = {t_str('16-d13-agent-message-order/CONTRACT.md. Local stubs only; bonds two_each, causal_ready, preemption_cap.')}",
            'args = ["noargs"]',
            "# Multi-verb FW_Seq rows (the expert chain form); Core applies the last row for a sheet.",
            f"seq_extra = {t_val(extra)}", ""]
    for sheet, values, ending, verb, flags, comment in slots:
        out += [f"[[slots]]   # {comment}", f'sheet = "{sheet}"', f'key = "{sheet.lower()}"', f"verb = {t_str(verb)}", "raw = true"]
        out += [f"flags = {t_val(flags)}"] if flags else []
        out += [f"ending = {json.dumps(ending)}"] if ending else []
        out += [f"values = {t_val(values)}", ""]
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
        companion = fg.workbook_sidecar_path(out / "spec.xlsx")
        if not companion.exists():
            raise SystemExit("constraints companion missing")
        shutil.copy2(out / "spec.xlsx", dest / "demo.xlsx")
        shutil.copy2(companion, fg.workbook_sidecar_path(dest / "demo.xlsx"))
    problems = fg.validate_workbook(dest / "demo.xlsx")
    if problems:
        raise SystemExit(f"validate_workbook: {problems}")
    x, t = fg.load_spec(dest / "demo.xlsx"), fg.load_spec(dest / "spec.toml")
    if x.constraints != constraints() or t.constraints != constraints() or x.params != t.params:
        raise SystemExit("XLSX companion and TOML do not carry the same bonds and params")
    files = ("spec.toml", "demo.xlsx", "demo.constraints.json")
    return {"head_chars": len(head), "head_sha256": sha256(head.encode()), "module_sha256": digests,
            "files": {f: sha256((dest / f).read_bytes()) for f in files}}


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
            diffs = [f for f in ("spec.toml", "demo.constraints.json")
                     if not (SPEC_DIR / f).exists() or (SPEC_DIR / f).read_bytes() != (Path(tmp) / f).read_bytes()]
            diffs += ["demo.xlsx"] if workbook_content(SPEC_DIR / "demo.xlsx") != workbook_content(Path(tmp) / "demo.xlsx") else []
        print("spec/ matches a fresh build" if not diffs else f"DRIFT: {diffs}")
        raise SystemExit(1 if diffs else 0)
    record = build(SPEC_DIR)
    record.update({"schema": "d13c.build/v1", "contract": "v1",
                   "note": "demo.xlsx bytes carry zip timestamps; compare cell content with build_spec.py --check"})
    (SPEC_DIR / "build.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"head_chars": record["head_chars"], "files": record["files"]}, indent=1))


if __name__ == "__main__":
    main()
