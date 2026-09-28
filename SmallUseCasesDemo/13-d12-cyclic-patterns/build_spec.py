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


"""Build D12 inputs: spec/<words|classes>/{spec.toml, demo.xlsx}; the XLSX is the run input.

    python build_spec.py            # (re)write spec/ from the audited sources
    python build_spec.py --check    # compare spec/ with a fresh build; exit 1 on drift

words:   HEAD, six explicit position slots P0..P5 (place(i,"A"|"B"|"C")), TAIL  -> 3^6 = 729.
classes: HEAD, PATTERN (the 130 canonical rotation representatives), TAIL      -> 130.
Every slot uses FW_Combi(1) -> FW_Combi(size) (no auto-promoted PermutR). The PATTERN catalogue is
built HERE offline by canonicalizing all 729 words (least distinct rotation); the Framework crosses and
executes the catalogues and does not canonicalize. No constraints, sieve, optional axes or repeats.
HEAD inlines sut.py, oracle.py and runtime.py, each checked against its SHA-256.
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
CAMPAIGNS = ("words", "classes")


def representatives():
    import itertools
    words = ["".join(w) for w in itertools.product("ABC", repeat=6)]
    return sorted({min(w[k:] + w[:k] for k in range(6)) for w in words})


REPRESENTATIVES = representatives()
if len(REPRESENTATIVES) != 130:
    raise SystemExit("expected 130 rotation classes")
DERIVED = json.loads((HERE / "architect-derived.json").read_text())
IDENTITY = ["FW_Combi(1)", "FW_Combi(size)"]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def head_value(sources):
    digests = {m: sha256(s.encode("utf-8")) for m, s in sources.items()}
    lines = ["# D12 HEAD: audited sut.py, oracle.py, runtime.py inlined by build_spec.py.",
             "# Each source is checked against its SHA-256, then run in its own module namespace.",
             "import hashlib as _d12_hash, sys as _d12_sys, types as _d12_types",
             "_D12_SOURCES = {"]
    lines += [f"    {m!r}: {s!r}," for m, s in sources.items()]
    lines += ["}", "_D12_SHA256 = {"]
    lines += [f"    {m!r}: {d!r}," for m, d in digests.items()]
    lines += ["}",
              f"for _d12_name in {MODULES!r}:",
              "    _d12_src = _D12_SOURCES[_d12_name]",
              "    if _d12_hash.sha256(_d12_src.encode('utf-8')).hexdigest() != _D12_SHA256[_d12_name]:",
              "        raise RuntimeError('inlined %s.py does not match its recorded SHA-256' % _d12_name)",
              "    _d12_mod = _d12_types.ModuleType(_d12_name)",
              "    _d12_mod.__file__ = '<d12/%s.py>' % _d12_name",
              "    _d12_sys.modules[_d12_name] = _d12_mod",
              "    exec(compile(_d12_src, _d12_mod.__file__, 'exec'), _d12_mod.__dict__)",
              "d12 = _d12_sys.modules['runtime']",
              "d12.SOURCE_SHA256.update(_D12_SHA256)",
              "place, pattern, finish = d12.place, d12.pattern, d12.finish      # the names the fragments call",
              "d12.begin()",
              ""]
    return "\n".join(lines), digests


def layout(campaign, head):
    """(slots, seq_extra) in sheet order; each value is one statement with its newline."""
    slots = [("HEAD", [head], "FW_Combi(1)", [], "runtime definitions: audited sources, inlined")]
    if campaign == "words":
        slots += [(f"P{i}", [f'place({i},"{c}")\n' for c in "ABC"], "FW_Combi(1)", [], f"letter at position {i}") for i in range(6)]
    else:
        slots.append(("PATTERN", [f'pattern("{r}")\n' for r in REPRESENTATIVES], "FW_Combi(1)", [],
                      "the 130 canonical rotation representatives (offline catalogue)"))
    slots.append(("TAIL", [f'_verdict = finish("{campaign}")\nFW_VAR = _verdict\nFW_CUSTOM_VAR = FW_VAR\n'], "FW_Combi(1)", [],
                  "evaluate the cyclic word, compare with the reference, set the verdict"))
    extra = [[s_[0], *IDENTITY] for s_ in slots]
    return slots, extra


CUSTOM_VAR_MSG = ("D12: a cyclic score or rotation field differs from the reference (the second slot is only the legacy "
                  "carrier, not a cause). Read mismatched_fields in the observation record rec=.")


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


def render_toml(campaign, head, digests):
    slots, extra = layout(campaign, head)
    out = [LICENSE.rstrip(), "#", f"# D12 cyclic designs, campaign {campaign}: GENERATED by build_spec.py; do not edit.",
           "# Inlined source SHA-256:"] + [f"#   {m}.py {d}" for m, d in digests.items()]
    out += ["", 'spec_version = "1"',
            f"title = {t_str(f'D12 cyclic designs and rotation classes, campaign {campaign}')}",
            f"note = {t_str('13-d12-cyclic-patterns/CONTRACT.md. Catalogues crossed by the Framework; no sieve.')}",
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
    record = {"head_chars": len(head), "head_sha256": sha256(head.encode()), "module_sha256": digests, "campaigns": {}}
    for campaign in CAMPAIGNS:
        cdir = dest / campaign
        cdir.mkdir(parents=True, exist_ok=True)
        text = render_toml(campaign, head, digests)
        parsed = tomllib.loads(text)
        slots, extra = layout(campaign, head)
        if [x["values"] for x in parsed["slots"]] != [x[1] for x in slots] or parsed["seq_extra"] != extra:
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
            diffs = [f"{c}/spec.toml" for c in CAMPAIGNS if (SPEC_DIR / c / "spec.toml").read_bytes() != (Path(tmp) / c / "spec.toml").read_bytes()]
            diffs += [f"{c}/demo.xlsx" for c in CAMPAIGNS
                      if workbook_content(SPEC_DIR / c / "demo.xlsx") != workbook_content(Path(tmp) / c / "demo.xlsx")]
        print("spec/ matches a fresh build" if not diffs else f"DRIFT: {diffs}")
        raise SystemExit(1 if diffs else 0)
    record = build(SPEC_DIR)
    record.update({"schema": "d12.build/v1", "contract": "v1", "representatives": REPRESENTATIVES,
                   "note": "demo.xlsx bytes carry zip timestamps; compare cell content with build_spec.py --check"})
    (SPEC_DIR / "build.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: record[k] for k in ("head_chars", "campaigns")}, indent=1))


if __name__ == "__main__":
    main()
