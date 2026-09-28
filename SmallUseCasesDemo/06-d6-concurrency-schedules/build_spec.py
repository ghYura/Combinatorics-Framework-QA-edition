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


"""Build D6 inputs: spec/<counter|queue>/{spec.toml, demo.xlsx, demo.constraints.json}.

    python build_spec.py            # (re)write spec/ from the audited sources
    python build_spec.py --check    # compare spec/ with a fresh build; exit 1 on drift

Atoms (impl("x"); cap(n); set_step(i,"T");) are whitespace-free; their newline is the FW_SheetNames
ending, so the workbook, params and bonds name the same strings. Each S1..S4 selects its thread
independently (FW_Combi(1) -> FW_Combi(size)); no complete schedule is listed anywhere. The bonds
follow CONTRACT.md: counter = two-each require-when, then the preemption expression <= CAP.n;
queue = two-P require-when, then a require-assert that S1 is the producer. HEAD inlines sut.py,
oracle.py and runtime.py, each checked against its SHA-256.
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
CAMPAIGNS = ("counter", "queue")
POLICIES = {"counter": ["atomic_commit", "split_rw"], "queue": ["actual_queue", "stale_empty"]}
THREADS = {"counter": ("A", "B"), "queue": ("P", "C")}
ATTR = {"counter": "a", "queue": "p"}          # 1 for A / P, 0 for B / C
STEPS = ("S1", "S2", "S3", "S4")
PREEMPTION_EXPR = ("int(S1.a != S2.a) + int(S2.a != S3.a and S1.a != S2.a) "
                   "+ int(S3.a != S4.a and S1.a != S3.a and S2.a != S3.a)")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def head_value(sources):
    digests = {m: sha256(s.encode("utf-8")) for m, s in sources.items()}
    lines = ["# D6 HEAD: audited sut.py, oracle.py, runtime.py inlined by build_spec.py.",
             "# Each source is checked against its SHA-256, then run in its own module namespace.",
             "import hashlib as _d6_hash, sys as _d6_sys, types as _d6_types",
             "_D6_SOURCES = {"]
    lines += [f"    {m!r}: {s!r}," for m, s in sources.items()]
    lines += ["}", "_D6_SHA256 = {"]
    lines += [f"    {m!r}: {d!r}," for m, d in digests.items()]
    lines += ["}",
              f"for _d6_name in {MODULES!r}:",
              "    _d6_src = _D6_SOURCES[_d6_name]",
              "    if _d6_hash.sha256(_d6_src.encode('utf-8')).hexdigest() != _D6_SHA256[_d6_name]:",
              "        raise RuntimeError('inlined %s.py does not match its recorded SHA-256' % _d6_name)",
              "    _d6_mod = _d6_types.ModuleType(_d6_name)",
              "    _d6_mod.__file__ = '<d6/%s.py>' % _d6_name",
              "    _d6_sys.modules[_d6_name] = _d6_mod",
              "    exec(compile(_d6_src, _d6_mod.__file__, 'exec'), _d6_mod.__dict__)",
              "d6 = _d6_sys.modules['runtime']",
              "d6.SOURCE_SHA256.update(_D6_SHA256)",
              "impl, cap, set_step, finish = d6.impl, d6.cap, d6.set_step, d6.finish      # the atoms the fragments call",
              "d6.begin()",
              ""]
    return "\n".join(lines), digests


def step_atom(i, t):
    return f'set_step({i},"{t}");'


def variant(name, head):
    """(slots, seq_extra); slot = (sheet, values, ending, verb, flags, comment)."""
    slots = [("HEAD", [head], "", "FW_Combi(1)", [], "runtime definitions: audited sources, inlined; 1 value"),
             ("IMPL", [f'impl("{p}");' for p in POLICIES[name]], "\n", "FW_Combi(1)", [], "implementation policy; 2 values")]
    if name == "counter":
        slots.append(("CAP", [f"cap({n});" for n in (0, 1, 2)], "\n", "FW_Combi(1)", [], "preemption bound; 3 values"))
    for i, s_ in enumerate(STEPS, start=1):
        slots.append((s_, [step_atom(i, t) for t in THREADS[name]], "\n", "FW_Combi(1)", [], f"thread of schedule step {i}; 2 values"))
    slots.append(("TAIL", [f'_verdict = finish("{name}")\nFW_VAR = _verdict\nFW_CUSTOM_VAR = FW_VAR\n'], "", "FW_Combi(1)", [],
                  "rebuild and check the schedule, run it, set the verdict; 1 value"))
    extra = [[s_[0], "FW_Combi(1)", "FW_Combi(size)"] for s_ in slots if s_[0] not in ("HEAD", "TAIL")]
    return slots, extra


def params(name):
    rows = [{"sheet": s_, "value": step_atom(i, t), ATTR[name]: int(t == THREADS[name][0])}
            for i, s_ in enumerate(STEPS, start=1) for t in THREADS[name]]
    if name == "counter":
        rows += [{"sheet": "CAP", "value": f"cap({n});", "n": n} for n in (0, 1, 2)]
    return rows


def constraints(name):
    if name == "counter":
        return [
            {"id": "two_each", "polarity": "require", "sheets": list(STEPS), "when": "S1.a + S2.a + S3.a + S4.a == 2",
             "desc": "each thread appears exactly twice (A has a=1, B has a=0)"},
            {"id": "preemption_cap", "polarity": "require", "sheets": ["CAP", *STEPS], "when": f"{PREEMPTION_EXPR} <= CAP.n",
             "desc": "preemptions (switches away from a thread with a step left) within the cap"},
        ]
    return [
        {"id": "two_each", "polarity": "require", "sheets": list(STEPS), "when": "S1.p + S2.p + S3.p + S4.p == 2",
         "desc": "producer and consumer each appear exactly twice (P has p=1, C has p=0)"},
        {"id": "producer_first", "polarity": "require", "assert": {"sheet": "S1", "eq": step_atom(1, "P")},
         "desc": "S1 is the producer (reference exploration: exactly the enabled schedules)"},
    ]


CUSTOM_VAR_MSG = ("D6: the observed state differs from the reference at one or more checkpoints (IMPL position 2 is "
                  "only the legacy carrier, not a cause). Read failing_checkpoints in the observation record rec=.")


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
    out = [LICENSE.rstrip(), "#", f"# D6 schedules, campaign {name}: GENERATED by build_spec.py; do not edit.",
           "# Inlined source SHA-256:"] + [f"#   {m}.py {d}" for m, d in digests.items()]
    out += ["", 'spec_version = "1"',
            f"title = {t_str(f'D6 bounded and enabled schedules, campaign {name}')}",
            f"note = {t_str('06-d6-concurrency-schedules/CONTRACT.md; 2 implementation policies.')}",
            'args = ["noargs"]',
            "# Multi-verb FW_Seq rows (the expert chain form); Core applies the last row for a sheet.",
            f"seq_extra = {t_val(extra)}", ""]
    for sheet, values, ending, verb, flags, comment in slots:
        out += [f"[[slots]]   # {comment}", f'sheet = "{sheet}"', f'key = "{sheet.lower()}"', f"verb = {t_str(verb)}", "raw = true"]
        out += [f"flags = {t_val(flags)}"] if flags else []
        out += [f"ending = {json.dumps(ending)}"] if ending else []
        out += [f"values = {t_val(values)}", ""]
    for row in params(name):
        out += ["[[params]]"] + [f"{k} = {t_val(v)}" for k, v in row.items()] + [""]
    for c in constraints(name):
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
    for name in CAMPAIGNS:
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
            if not companion.exists():
                raise SystemExit(f"{name}: constraints companion missing")
            shutil.copy2(out / "spec.xlsx", vdir / "demo.xlsx")
            shutil.copy2(companion, fg.workbook_sidecar_path(vdir / "demo.xlsx"))
        problems = fg.validate_workbook(vdir / "demo.xlsx")
        if problems:
            raise SystemExit(f"{name}: validate_workbook: {problems}")
        x, t = fg.load_spec(vdir / "demo.xlsx"), fg.load_spec(vdir / "spec.toml")
        if x.constraints != constraints(name) or t.constraints != constraints(name) or x.params != t.params:
            raise SystemExit(f"{name}: XLSX companion and TOML do not carry the same bonds and params")
        files = ("spec.toml", "demo.xlsx", "demo.constraints.json")
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
            diffs = [f"{v}/{f}" for v in CAMPAIGNS for f in ("spec.toml", "demo.constraints.json")
                     if (SPEC_DIR / v / f).exists() != (Path(tmp) / v / f).exists()
                     or ((SPEC_DIR / v / f).exists() and (SPEC_DIR / v / f).read_bytes() != (Path(tmp) / v / f).read_bytes())]
            diffs += [f"{v}/demo.xlsx" for v in CAMPAIGNS
                      if workbook_content(SPEC_DIR / v / "demo.xlsx") != workbook_content(Path(tmp) / v / "demo.xlsx")]
        print("spec/ matches a fresh build" if not diffs else f"DRIFT: {diffs}")
        raise SystemExit(1 if diffs else 0)
    record = build(SPEC_DIR)
    record.update({"schema": "d6.build/v1", "contract": "v1",
                   "note": "demo.xlsx bytes carry zip timestamps; compare cell content with build_spec.py --check"})
    (SPEC_DIR / "build.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"head_chars": record["head_chars"], "variants": record["variants"]}, indent=1))


if __name__ == "__main__":
    main()
