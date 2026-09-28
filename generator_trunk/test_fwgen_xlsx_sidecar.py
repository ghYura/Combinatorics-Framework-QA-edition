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

"""XLSX constraint companions: a workbook's bond layer lives in `<stem>.constraints.json`.

Covers: the workbook + companion plans and explains exactly what the TOML spec does (and
without the companion stays unconstrained); only the same-stem companion is read; malformed
or unsupported companions fail before any run or database work; params and ordinal orders
survive the load and are used by the rules; the compact generator writes a discoverable
companion that spec-directory discovery does not mistake for a spec; loading and planning
never touch the workbook bytes; and resume treats a changed companion as a changed spec.

Run: `python3 -m pytest test_fwgen_xlsx_sidecar.py -q` (no DB / no Bundle run).
"""
import dataclasses
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

pytest.importorskip("openpyxl")

import fwgen as fg                                             # noqa: E402
import fwgen_cli                                               # noqa: E402
from bundle.errors import PreflightError                       # noqa: E402
from bundle.stages import load_spec_input                      # noqa: E402

TOML = '''spec_version = "1"
title = "companion probe"
args = ["noargs"]

[[slots]]
sheet = "A"
key = "a"
raw = true
ending = "\\n"
values = ["A = 0", "A = 1"]

[[slots]]
sheet = "B"
key = "b"
raw = true
ending = "\\n"
values = ["B = 0", "B = 1"]

[[slots]]
sheet = "TAIL"
key = "tail"
raw = true
values = [\'\'\'_v = 0
FW_VAR = _v
FW_CUSTOM_VAR = FW_VAR
\'\'\']

[[constraints]]
id = "no_a1_b1"
polarity = "forbid"
sets = { A = ["A = 1"], B = ["B = 1"] }
'''


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _generate(tmp: Path, toml_text: str = TOML, name: str = "probe") -> Path:
    """Compile a TOML spec with the real `fwgen_cli gen`; return the compact workbook."""
    specs, out = tmp / "specs", tmp / "wb"
    specs.mkdir(parents=True, exist_ok=True)
    (specs / f"{name}.toml").write_text(toml_text, encoding="utf-8")
    r = subprocess.run([sys.executable, str(HERE / "fwgen_cli.py"), "gen", "--specs", str(specs),
                        "--out", str(out)], capture_output=True, text=True, cwd=HERE)
    assert r.returncode == 0, r.stdout + r.stderr
    return out / f"{name}.xlsx"


def _survivors(spec) -> tuple:
    plan = fg.spec_cardinality_plan(spec)
    return plan.mandatory.value, plan.post_sieve.value, plan.post_sieve.mode.value


def _plan_cli(path: Path, out: Path) -> dict:
    r = subprocess.run([sys.executable, str(HERE / "bundle_run.py"), "plan", str(path), "--out", str(out)],
                       capture_output=True, text=True, cwd=HERE.parent)
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads((out / "plan.json").read_text())


def _explain_cli(path: Path) -> str:
    r = subprocess.run([sys.executable, str(HERE / "bundle_run.py"), "constraints", "explain", str(path)],
                       capture_output=True, text=True, cwd=HERE.parent)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


def test_workbook_with_companion_plans_and_explains_like_the_toml(tmp_path):
    book = _generate(tmp_path)
    toml = tmp_path / "specs" / "probe.toml"
    companion = fg.workbook_sidecar_path(book)
    assert companion.name == "probe.constraints.json" and companion.is_file()

    t_spec, x_spec = fg.load_spec(toml), fg.load_spec(book)
    assert x_spec.constraints == t_spec.constraints and [c["id"] for c in x_spec.constraints] == ["no_a1_b1"]
    assert _survivors(t_spec) == _survivors(x_spec) == (4, 3, "EXACT")
    assert x_spec.sidecar_path == str(companion.resolve()) and x_spec.sidecar_sha256 == _sha(companion)

    t_plan, x_plan = _plan_cli(toml, tmp_path / "pt"), _plan_cli(book, tmp_path / "px")
    for plan in (t_plan, x_plan):
        assert plan["constraints_present"] == 1
        assert (plan["cardinality"]["mandatory"]["value"], plan["cardinality"]["final"]["value"]) == (4, 3)
    assert t_plan["constraints_source"] is None
    assert x_plan["constraints_source"] == {"path": str(companion.resolve()), "sha256": _sha(companion)}
    explained = _explain_cli(book)
    assert "no_a1_b1" in explained and "probe.constraints.json" in explained

    companion.unlink()                                  # the same workbook, no companion: unconstrained
    bare = fg.load_spec(book)
    assert bare.constraints == [] and bare.sidecar_path == "" and _survivors(bare)[:2] == (4, 4)
    assert "declares no constraints" in _explain_cli(book)


def test_only_the_same_stem_companion_is_read(tmp_path):
    book = _generate(tmp_path)
    companion = fg.workbook_sidecar_path(book)
    rules = companion.read_text()
    companion.unlink()
    (book.parent / "other.constraints.json").write_text(rules)       # another workbook's companion
    (book.parent / "sidecar.json").write_text(rules)                 # a generic sidecar
    (book.parent / "probe.json").write_text(rules)                   # a neighbour with the plain stem
    shutil.copy2(tmp_path / "specs" / "probe.toml", book.parent / "probe.toml")   # a neighbouring TOML
    assert fg.load_spec(book).constraints == []


@pytest.mark.parametrize("content, message", [
    ("{not json", "cannot read it as UTF-8 JSON"),
    (b"\xff\xfe\x00", "cannot read it as UTF-8 JSON"),
    ("[]", "top level must be a JSON object"),
    ('{"version": 2, "constraints": []}', "'version' must be the integer 1"),
    ('{"version": "1", "constraints": []}', "'version' must be the integer 1"),
    ('{"version": true, "constraints": []}', "'version' must be the integer 1"),
    ('{"version": 1, "constraints": {"id": "x"}}', "'constraints' must be a list of objects"),
    ('{"version": 1, "constraints": [], "params": []}', "'params' must map"),
    ('{"version": 1, "constraints": [], "orders": []}', "'orders' must be an object"),
    ('{"version": 1, "constraints": [], "rules": []}', "unsupported top-level key(s) ['rules']"),
    ('{"version": 1, "constraints": [{"id": "x", "polarity": "forbid", "sets": {"A": ["A = 1"], "B": ["B = 1"]}, '
     '"weight": 3}]}', "unknown field(s) ['weight']"),
    ('{"version": 1, "constraints": [{"id": "x", "polarity": "forbid", "assert": {"sheet": "A", "regex": "1"}}]}',
     "invalid assert"),
    ('{"version": 1, "constraints": [{"id": "x", "polarity": "forbid", "sets": {"A": ["A = 1"]}}]}',
     "a bond needs at least two referenced sheets"),
    ('{"version": 1, "constraints": [{"id": "x", "polarity": "forbid", "sets": {"A": ["A = 1"], "Z": ["z"]}}]}',
     "references undeclared sheet 'Z'"),
    ('{"version": 1, "constraints": [{"id": "x", "polarity": "forbid"}]}', "needs 'pairs', 'sets'"),
    ('{"version": 1, "constraints": [], "orders": {"A": "alphabetical"}}', "must be a list, 'numeric', or 'date'"),
    ('{"version": 1, "constraints": [], "params": {"Z": {"z": {"cost": 1}}}}', "params reference undeclared sheet 'Z'"),
    # constraint-body shapes (review R2): validated before anything traverses them
    ('{"version": 1, "constraints": [{"id": "bad", "sets": []}]}', "'sets' must be a non-empty {sheet: [values]} object"),
    ('{"version": 1, "constraints": [{"id": "bad", "sets": {}}]}', "'sets' must be a non-empty {sheet: [values]} object"),
    ('{"version": 1, "constraints": [{"id": "bad", "sets": {"A": "A = 1", "B": ["B = 1"]}}]}', "'sets.A' must be a non-empty list"),
    ('{"version": 1, "constraints": [{"id": "bad", "sets": {"A": [], "B": ["B = 1"]}}]}', "'sets.A' must be a non-empty list"),
    ('{"version": 1, "constraints": [{"id": "bad", "sets": {"A": [["A = 1"]], "B": ["B = 1"]}}]}', "'sets.A' values must be single values"),
    ('{"version": 1, "constraints": [{"id": "bad", "sheets": ["A", "B"], "when": true}]}', "'when' must be a non-empty predicate string"),
    ('{"version": 1, "constraints": [{"id": "bad", "sheets": ["A", "B"], "when": "  "}]}', "'when' must be a non-empty predicate string"),
    ('{"version": 1, "constraints": [{"id": "bad", "when": "A.cost > 1"}]}', "a 'when' bond needs 'sheets'"),
    ('{"version": 1, "constraints": [{"id": "bad", "sets": {"A": ["A = 1"], "B": ["B = 1"]}, '
     '"pairs": [{"A": "A = 0", "B": "B = 0"}]}]}', "needs exactly one body"),
    ('{"version": 1, "constraints": [{"id": "bad", "sheets": ["A", "B"], "when": "1", "assert": {"sheet": "A", "eq": "A = 1"}}]}',
     "needs exactly one body"),
    ('{"version": 1, "constraints": [{"id": "bad", "pairs": []}]}', "'pairs' must be a non-empty list"),
    ('{"version": 1, "constraints": [{"id": "bad", "pairs": {"A": "A = 1"}}]}', "'pairs' must be a non-empty list"),
    ('{"version": 1, "constraints": [{"id": "bad", "pairs": [{}]}]}', "each 'pairs' entry must be a non-empty"),
    ('{"version": 1, "constraints": [{"id": "bad", "pairs": [{"A": ["A = 1"], "B": "B = 1"}]}]}', "'pairs' values must be single values"),
    ('{"version": 1, "constraints": [{"id": "bad", "mapping": ["A", "B"]}]}', "invalid mapping"),
    ('{"version": 1, "constraints": [{"id": "bad", "assert": ["A"]}]}', "invalid assert"),
    ('{"version": 1, "constraints": [{"id": "bad", "sets": {"A": ["A = 1"], "B": ["B = 1"]}, "gate": []}]}', "'gate' must be an object"),
    ('{"version": 1, "constraints": [{"id": "bad", "sets": {"A": ["A = 1"], "B": ["B = 1"]}, "gate": {"near": 1}}]}', "'gate' must be an object"),
    ('{"version": 1, "constraints": [{"id": "bad", "sets": {"A": ["A = 1"], "B": ["B = 1"]}, "gate": {"adjacent": "yes"}}]}', "'gate.adjacent' must be true or false"),
    ('{"version": 1, "constraints": [{"id": "bad", "sets": {"A": ["A = 1"], "B": ["B = 1"]}, "gate": {"within": -1}}]}', "'gate.within' must be a non-negative integer"),
    ('{"version": 1, "constraints": [{"id": "bad", "sets": {"A": ["A = 1"], "B": ["B = 1"]}, "polarity": "maybe"}]}',
     "polarity 'maybe' is neither 'forbid' nor 'require' (strict mode)"),
    ('{"version": 1, "constraints": [{"id": "bad", "sheets": "A", "when": "1"}]}', "'sheets' must be a non-empty list"),
    ('{"version": 1, "constraints": [{"id": "bad", "sheets": ["A", "A"], "when": "1"}]}', "'sheets' names a sheet twice"),
    ('{"version": 1, "constraints": [{"id": 5, "sets": {"A": ["A = 1"], "B": ["B = 1"]}}]}', "'id' must be a non-empty string"),
    ('{"version": 1, "constraints": [{"id": "bad", "desc": 3, "sets": {"A": ["A = 1"], "B": ["B = 1"]}}]}', "'desc' must be a string"),
])
def test_a_malformed_or_unsupported_companion_fails_before_any_run(tmp_path, content, message):
    book = _generate(tmp_path)
    companion = fg.workbook_sidecar_path(book)
    if isinstance(content, bytes):
        companion.write_bytes(content)
    else:
        companion.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError) as exc:
        fg.load_spec(book)
    assert message in str(exc.value) and "probe.constraints.json" in str(exc.value)
    with pytest.raises(PreflightError) as pre:              # the Bundle's single entry point
        load_spec_input(book)
    assert "probe.constraints.json" in str(pre.value)


def test_params_and_orders_survive_and_the_rules_use_them(tmp_path):
    book = _generate(tmp_path)
    fg.workbook_sidecar_path(book).write_text(json.dumps({
        "version": 1,
        "params": {"A": {"A = 0": {"cost": 1}, "A = 1": {"cost": 5}},
                   "B": {"B = 0": {"cost": 1}, "B = 1": {"cost": 2}}},
        "constraints": [
            {"id": "cost_cap", "polarity": "forbid", "sheets": ["A", "B"], "when": "A.cost + B.cost > 5"},
            {"id": "b_rank", "polarity": "require", "assert": {"sheet": "B", "ge": "B = 0"},
             "condition": {"sheet": "A", "eq": "A = 0"}},
            {"id": "b_not_below_a", "polarity": "forbid", "assert": {"sheet": "B", "ltSheet": "A"}},
        ],
        "orders": {"A": ["A = 0", "A = 1"], "B": ["B = 0", "B = 1"]},
    }), encoding="utf-8")
    spec = fg.load_spec(book)
    assert list(spec.params) == ["A", "B"] and spec.params["A"]["A = 1"] == {"cost": 5}
    assert spec.orders == {"A": ["A = 0", "A = 1"], "B": ["B = 0", "B = 1"]}
    assert [c["id"] for c in spec.constraints] == ["cost_cap", "b_rank", "b_not_below_a"]
    # cost_cap drops (A=1,B=1): 5+2 > 5. b_not_below_a drops (A=1,B=0): rank(B) < rank(A).
    # Both need what the companion carries: without params `when` cannot be evaluated, and
    # without orders an ordinal leaf fails closed, so a fields-only load could not give 2.
    assert _survivors(spec) == (4, 2, "EXACT")
    stripped = dataclasses.replace(spec, params={}, orders={})
    assert _survivors(stripped)[1:] != (2, "EXACT")


def test_generator_companion_is_discoverable_and_not_a_spec(tmp_path):
    book = _generate(tmp_path)
    companion = fg.workbook_sidecar_path(book)
    written = json.loads(companion.read_text())
    assert written == {"version": 1, "params": {}, "constraints": fg.load_spec(tmp_path / "specs" / "probe.toml").constraints}
    # a companion that also carries `orders`, dropped into a TOML spec directory, is not a spec
    specs = tmp_path / "specs"
    (specs / "probe.constraints.json").write_text(json.dumps({**written, "orders": {"A": ["A = 0", "A = 1"]}}))
    assert [s.name for s in fg.load_specs_dir(specs)] == ["probe"]
    assert not fg._is_spec_dir_entry(companion) and not fg._is_spec_dir_entry(specs / "probe.constraints.json")
    # regenerating a spec WITHOUT constraints removes the stale companion instead of inheriting it
    bare = TOML[:TOML.index("[[constraints]]")]
    _generate(tmp_path, bare)
    assert not companion.exists() and fg.load_spec(book).constraints == []


def test_materialized_workbooks_get_no_factor_level_companion(tmp_path):
    spec = fg.load_spec(_generate(tmp_path).parent.parent / "specs" / "probe.toml")
    out = tmp_path / "mat"
    stale = out / "probe_k1_ablation.constraints.json"
    out.mkdir()
    stale.write_text("{}")
    info = fwgen_cli.generate_one(spec, out, "ablation", 0, False, 0, "dup")
    assert info["constraints_sidecar"] is None and "not attached" in info["constraints_note"]
    assert not stale.exists() and not list(out.glob("*.constraints.json"))


def test_unconstrained_workbook_and_toml_paths_are_unchanged(tmp_path):
    bare = TOML[:TOML.index("[[constraints]]")]
    book = _generate(tmp_path, bare)
    assert not fg.workbook_sidecar_path(book).exists()
    x_spec, t_spec = fg.load_spec(book), fg.load_spec(tmp_path / "specs" / "probe.toml")
    assert (x_spec.constraints, x_spec.params, x_spec.orders, x_spec.sidecar_path) == ([], {}, {}, "")
    assert (t_spec.sidecar_path, t_spec.sidecar_sha256) == ("", "")
    assert _survivors(x_spec)[:2] == _survivors(t_spec)[:2] == (4, 4)


def test_loading_and_planning_leave_the_workbook_bytes_unchanged(tmp_path):
    book = _generate(tmp_path)
    companion = fg.workbook_sidecar_path(book)
    before = (_sha(book), _sha(companion), book.stat().st_mtime_ns)
    fg.load_spec(book)
    load_spec_input(book)
    _plan_cli(book, tmp_path / "plan")
    _explain_cli(book)
    assert (_sha(book), _sha(companion), book.stat().st_mtime_ns) == before


def test_spec_input_artifacts_include_the_companion(tmp_path):
    from bundle import orchestrator as orch
    book = _generate(tmp_path)
    spec = fg.load_spec(book)
    kinds = {a.kind: a.sha256 for a in orch._spec_input_artifacts(spec, book)}
    assert kinds == {"input.spec": _sha(book), "input.constraints_sidecar": _sha(fg.workbook_sidecar_path(book))}
    toml_spec = fg.load_spec(tmp_path / "specs" / "probe.toml")
    assert [a.kind for a in orch._spec_input_artifacts(toml_spec, tmp_path / "specs" / "probe.toml")] == ["input.spec"]


# ---- resume: a changed companion invalidates gen even when the workbook bytes are identical ----
def _resume_fixture(d, companion_sha):
    import test_bundle_resume as tr
    from bundle.jsonio import read_json, write_json_atomic
    from bundle.models import run_manifest_from_dict
    layout, spec_path = tr._build_run(d)
    manifest = run_manifest_from_dict(read_json(layout.manifest_path))
    write_json_atomic(layout.manifest_path, dataclasses.replace(
        manifest, constraints_sidecar_path=str(Path(d) / "demo.constraints.json"),
        constraints_sidecar_sha256=companion_sha))
    return tr, layout, spec_path


def _run_resume(tr, layout, spec_path, spec, ran):
    from bundle import cli
    from bundle import orchestrator as orch
    hs = layout.root / "handshake"

    def fake_gen(*_a, **_k):
        ran.append("gen")
        return layout.root / "wb" / "demo.xlsx"

    def fake_core(*_a, **_k):
        ran.append("core")
        return 1

    def fake_reader(*_a, **_k):
        ran.append("reader")
        return layout.root / "src", hs, 1, 0, hs / "handoff" / "manifest.json"

    def fake_executor(*_a, **_k):
        ran.append("executor")
        tr._emit_executor_summary(_k)
        return (1, 1, 0, 0, 1, 1, 0, 0, {"attempted": 1, "inserted": 1, "already_present": 0, "updated_selected": 0})

    with patch.object(cli, "_load_one_spec", lambda spec_dir: (spec, spec_path)), \
         patch.object(orch, "psql", tr._resume_psql), \
         patch.object(orch, "stage_gen", side_effect=fake_gen), \
         patch.object(orch, "stage_core", side_effect=fake_core), \
         patch.object(orch, "stage_reader", side_effect=fake_reader), \
         patch.object(orch, "_record_handoff_manifest", lambda rec, *_a, **_k: object()), \
         patch.object(orch, "stage_executor", side_effect=fake_executor):
        cli.cmd_resume(tr._BLANK_ARGS(layout.root))


def test_resume_reruns_everything_when_only_the_companion_changed():
    from bundle.jsonio import read_json
    from bundle.models import run_manifest_from_dict
    from bundle.runs import file_sha256
    with tempfile.TemporaryDirectory() as d:
        tr, layout, spec_path = _resume_fixture(d, "a" * 64)
        spec = SimpleNamespace(**vars(tr._FAKE_SPEC), sidecar_path=str(Path(d) / "demo.constraints.json"),
                               sidecar_sha256="b" * 64)
        ran = []
        _run_resume(tr, layout, spec_path, spec, ran)
        assert ran == ["gen", "core", "reader", "executor"]
        manifest = run_manifest_from_dict(read_json(layout.manifest_path))
        assert manifest.spec_sha256 == file_sha256(spec_path)          # the workbook itself did not change
        assert manifest.constraints_sidecar_sha256 == "b" * 64


def test_resume_reuses_gen_when_the_companion_is_unchanged():
    from bundle import orchestrator as orch
    from bundle.config import BundleConfig
    from bundle.models import StageStatus
    from bundle.resume import file_artifact
    with tempfile.TemporaryDirectory() as d:
        companion = Path(d) / "demo.constraints.json"
        companion.write_text('{"version": 1, "params": {}, "constraints": []}')
        tr, layout, spec_path = _resume_fixture(d, _sha(companion))
        tr._write_stage(layout, "gen", StageStatus.SUCCEEDED,
                        artifacts=(file_artifact("input.spec", spec_path),
                                   file_artifact("input.constraints_sidecar", companion),
                                   file_artifact("output.workbook", layout.root / "wb" / "demo.xlsx"),
                                   *orch._stage_component_artifacts("gen", BundleConfig())))
        spec = SimpleNamespace(**vars(tr._FAKE_SPEC), sidecar_path=str(companion), sidecar_sha256=_sha(companion))
        ran = []
        _run_resume(tr, layout, spec_path, spec, ran)
        assert ran == ["executor"]


# ---- review R2: the TOML path shares the shape validation (one loaded meaning) ----
def test_a_malformed_toml_body_is_a_clear_error_not_a_crash(tmp_path):
    bad = TOML.replace('sets = { A = ["A = 1"], B = ["B = 1"] }', 'sets = []')
    (tmp_path / "bad.toml").write_text(bad, encoding="utf-8")
    with pytest.raises(ValueError, match="'sets' must be a non-empty"):
        fg.load_spec(tmp_path / "bad.toml")
    with pytest.raises(PreflightError, match="bad.toml"):
        load_spec_input(tmp_path / "bad.toml")


# ---- review R1: the run's copied companion follows the input's companion ----
def test_stage_gen_companion_copy_follows_removal_addition_and_no_change(tmp_path):
    from bundle.stages import stage_gen
    import contextlib
    import io
    book = _generate(tmp_path)
    src_book, companion = book, fg.workbook_sidecar_path(book)
    first_rules = companion.read_bytes()
    scratch = tmp_path / "scratch"

    def gen():
        with contextlib.redirect_stdout(io.StringIO()):
            return stage_gen(src_book, scratch)
    book_sha = _sha(src_book)

    copied = gen()                                              # present -> copied byte for byte
    copy = fg.workbook_sidecar_path(copied)
    assert copy.read_bytes() == first_rules
    gen()                                                       # unchanged -> identical
    assert copy.read_bytes() == first_rules and len(fg.load_spec(copied).constraints) == 1
    companion.unlink()                                          # removed -> the stale copy goes too
    gen()
    assert not copy.exists() and fg.load_spec(copied).constraints == []
    gen()                                                       # still absent -> nothing reappears
    assert not copy.exists()
    changed = json.loads(first_rules)
    changed["constraints"][0]["id"] = "renamed_rule"
    companion.write_text(json.dumps(changed), encoding="utf-8")  # added back, different rules
    gen()
    assert copy.read_bytes() == companion.read_bytes()
    assert [c["id"] for c in fg.load_spec(copied).constraints] == ["renamed_rule"]
    assert _sha(src_book) == book_sha and companion.is_file()   # the input is never touched


def test_resume_after_the_companion_was_removed_drops_the_stale_copy(tmp_path):
    """Real stage_gen inside a real resume: the input companion was removed since the run, so
    resume sees a changed spec, regenerates, and the run's wb/ no longer carries the old rules."""
    import test_bundle_resume as tr
    from bundle import cli
    from bundle import orchestrator as orch
    from bundle.jsonio import read_json, write_json_atomic
    from bundle.models import run_manifest_from_dict
    from bundle.runs import file_sha256
    d = tmp_path / "run"
    d.mkdir()
    layout, _toml = tr._build_run(str(d))
    book = _generate(tmp_path)
    shutil.copy2(book, d / "demo.xlsx")
    companion = fg.workbook_sidecar_path(d / "demo.xlsx")
    shutil.copy2(fg.workbook_sidecar_path(book), companion)
    stale = fg.workbook_sidecar_path(layout.root / "wb" / "demo.xlsx")
    shutil.copy2(companion, stale)                               # the copy the original gen made
    manifest = run_manifest_from_dict(read_json(layout.manifest_path))
    write_json_atomic(layout.manifest_path, dataclasses.replace(
        manifest, spec_path=str(d / "demo.xlsx"), spec_sha256=file_sha256(d / "demo.xlsx"),
        constraints_sidecar_path=str(companion), constraints_sidecar_sha256=_sha(companion)))
    companion.unlink()                                           # the author removes the rules
    spec = fg.load_spec(d / "demo.xlsx")
    assert spec.sidecar_sha256 == ""
    ran = []
    hs = layout.root / "handshake"

    def fake_core(*_a, **_k):
        ran.append("core")
        return 1

    def fake_reader(*_a, **_k):
        ran.append("reader")
        return layout.root / "src", hs, 1, 0, hs / "handoff" / "manifest.json"

    def fake_executor(*_a, **_k):
        ran.append("executor")
        tr._emit_executor_summary(_k)
        return (1, 1, 0, 0, 1, 1, 0, 0, {"attempted": 1, "inserted": 1, "already_present": 0, "updated_selected": 0})

    with patch.object(cli, "_load_one_spec", lambda spec_dir: (spec, d / "demo.xlsx")), \
         patch.object(orch, "psql", tr._resume_psql), \
         patch.object(orch, "stage_core", side_effect=fake_core), \
         patch.object(orch, "stage_reader", side_effect=fake_reader), \
         patch.object(orch, "_record_handoff_manifest", lambda rec, *_a, **_k: object()), \
         patch.object(orch, "stage_executor", side_effect=fake_executor):
        cli.cmd_resume(tr._BLANK_ARGS(layout.root))              # the REAL stage_gen runs
    assert ran == ["core", "reader", "executor"]                 # gen ran for real (not recorded here)
    assert not stale.exists(), "the regenerated run still carries the removed companion's rules"
    assert fg.load_spec(layout.root / "wb" / "demo.xlsx").constraints == []
    assert run_manifest_from_dict(read_json(layout.manifest_path)).constraints_sidecar_sha256 is None


def test_unknown_polarity_is_rejected_in_companions_and_warned_in_toml_compatibility(tmp_path, capsys):
    """The sieve reads any non-'forbid' polarity as 'require'. A companion (always strict) and a
    strict TOML load reject it; a compatibility-mode TOML load keeps legacy specs loadable and
    warns, exactly as it does for unknown fields."""
    toml = TOML.replace('polarity = "forbid"', 'polarity = "deny"')
    (tmp_path / "deny.toml").write_text(toml, encoding="utf-8")
    spec = fg.load_spec(tmp_path / "deny.toml")
    assert spec.constraints[0]["polarity"] == "deny"
    assert "treats it as 'require'" in capsys.readouterr().out
    with pytest.raises(ValueError, match="strict mode"):
        fg.load_spec(tmp_path / "deny.toml", strict=True)
