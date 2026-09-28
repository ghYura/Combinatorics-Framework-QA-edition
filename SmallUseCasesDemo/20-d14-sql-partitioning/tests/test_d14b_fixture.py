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

"""D14b fixture checks: all 72 cases (with a fake connection that evaluates the four SQL shapes over an
independent three-valued model) against the frozen predictions and the verifier's model; NULL truth
tables; duplicate projection and join rows; the missing unknown branch; deduplication; a falsely passing
set comparison; passing total predicates; a lost base filter; malformed SQL results; transaction and
role guards; the verifier's parser on a locally composed candidate (run with a pg8000 stub); policy
blindness; independence; the builder; the bootstrap rows; and the real sandbox probe against the retained
fixture (only when D14B_TEST_FIXTURE_STAMP names it, as run_demo.py does).

Run: python -m pytest -q -p no:cacheprovider tests
"""
import ast
import base64
import contextlib
import copy
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import adapter  # noqa: E402
import build_spec  # noqa: E402
import explore  # noqa: E402
import model  # noqa: E402
import oracle  # noqa: E402
import runtime  # noqa: E402
import verify  # noqa: E402

DERIVED = json.loads((HERE / "architect-derived.json").read_text())
FROZEN = {c["id"]: c for c in DERIVED["cases"]}
FX = DERIVED["fixture"]
FIXTURE = "as0927_d14b_sql_test"
SQL_RE = re.compile(r"^SELECT i\.val FROM fixture\.items AS i(?P<join>| JOIN fixture\.tags AS t ON t\.item_id=i\.id| LEFT JOIN fixture\.tags AS t ON "
                    r"t\.item_id=i\.id) WHERE (?P<cond>.*)$")
BRANCH_RE = re.compile(r"^\((?P<base>TRUE|i\.grp = 'a')\) AND (?:NOT \((?P<neg>.*)\)|\(\((?P<unk>.*)\) IS NULL\)|\((?P<pos>.*)\))$")
NAME = {v: k for k, v in verify.PTEXT.items()}


def fake_rows(sql):
    """A stand-in for PostgreSQL on exactly the contract's SQL shapes (independent verifier model)."""
    m = SQL_RE.match(sql)
    shape = {"": "scan", " JOIN fixture.tags AS t ON t.item_id=i.id": "inner_join"}.get(m["join"], "left_join")
    cond = m["cond"]
    if cond in ("TRUE", "i.grp = 'a'"):
        base, keep = cond, lambda item: True
    else:
        b = BRANCH_RE.match(cond)
        base = b["base"]
        if b["pos"] is not None:
            keep = lambda item: verify.truth(item, NAME[b["pos"]]) == "T"
        elif b["neg"] is not None:
            keep = lambda item: verify.tv_not(verify.truth(item, NAME[b["neg"]])) == "T"
        else:
            keep = lambda item: verify.truth(item, NAME[b["unk"]]) == "U"
    rows = [i for i in verify.scanned(FX, shape) if (base == "TRUE" or i["grp"] == "a") and keep(i)]
    return [(i["val"],) for i in rows]


class FakeConnection:
    prov = {}

    def __init__(self, fixture, app):
        self.fixture, self.app, self.log = fixture, app, []

    def run(self, text):
        self.log.append(text)
        if text.startswith("BEGIN") or text == "COMMIT":
            return None
        if text == runtime.PROVENANCE:
            p = {"database": self.fixture, "user": runtime.READER, "transaction_isolation": "repeatable read", "transaction_read_only": "on",
                 "backend_pid": 4242, "snapshot": "800:800:", "version": "PostgreSQL 16.9 (fake)", "application_name": self.app,
                 "statement_timeout": "5s", **self.prov}
            return [[p[k] for k in runtime.PROVENANCE_KEYS]]
        return fake_rows(text)

    def close(self):
        pass


@pytest.fixture(autouse=True)
def fake_db(monkeypatch):
    monkeypatch.setattr(runtime, "_connect", FakeConnection)
    monkeypatch.setenv("D14B_FIXTURE", FIXTURE)
    FakeConnection.prov = {}


def parse(cid):
    f = dict(p.split("=", 1) for p in cid.split("|"))
    return f["P"], f["Q"], f["F"]


def run_case(cid):
    p, q, f = parse(cid)
    runtime._state.clear()
    runtime.begin()
    runtime.impl(p), runtime.query(q), runtime.predicate(f)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fw = runtime.finish()
    lines = out.getvalue().splitlines()
    assert len(lines) == 1
    tokens = dict(t.split("=", 1) for t in lines[0].split() if "=" in t)
    return fw, json.loads(base64.urlsafe_b64decode(tokens["rec"]))


def test_all_72_match_frozen_and_the_verifier_model():
    for cid, fz in FROZEN.items():
        fw, rec = run_case(cid)
        own = verify.own_case(FX, *parse(cid))
        assert {k: rec[k] for k in verify.FROZEN_KEYS} == {k: fz[k] for k in verify.FROZEN_KEYS} == {k: own[k] for k in verify.FROZEN_KEYS}
        assert rec["verdict"] == fz["predicted_outcome"] and fw == (0 if rec["verdict"] == "PASS" else 2) and all(rec["query_checks"].values())
        assert [k for k, g, w in verify.compare_record(rec, own) if g != w] == []
        assert verify.provenance_problems(rec, FIXTURE, "PostgreSQL 16.9 (fake)") == []
        assert [s["kind"] for s in rec["provenance"]["statements"]] == ["begin", "provenance", "data:base", "data:true", "data:false", "data:unknown", "end"]


def test_null_truth_tables_do_not_map_unknown_to_false():
    t, f, u = True, False, None
    assert [model.k_not(x) for x in (t, f, u)] == [f, t, u]
    assert [[model.k_and(a, b) for b in (t, f, u)] for a in (t, f, u)] == [[t, f, u], [f, f, f], [u, f, u]]
    assert [[model.k_or(a, b) for b in (t, f, u)] for a in (t, f, u)] == [[t, t, t], [t, f, u], [t, u, u]]
    item3 = (3, "a", 1, None)                                                       # val 1, flag NULL
    assert model.truth(item3, "and") is None and model.truth(item3, "or") is True and model.truth(item3, "flag") is None
    assert model.truth((6, "b", None, None), "is_null") is True and model.truth((6, "b", None, None), "gt0") is None
    exp = model.expected("scan", "flag")
    assert [r[0] for r in exp["false"]] == [0, 2] and [r[0] for r in exp["unknown"]] == [None, 1]   # NOT UNKNOWN stays UNKNOWN


def test_duplicate_projection_and_join_rows_are_kept_and_dedup_destroys_them():
    _, rec = run_case("P=dedup_union|Q=inner_join|F=eq1")
    assert rec["query_bags"]["base"] == [{"row": [None], "count": 2}, {"row": [1], "count": 3}, {"row": [2], "count": 1}]
    assert [r[0] for r in rec["query_rows"]["true"]] == [1, 1, 1] and rec["combined_bag"] == [{"row": [None], "count": 1},
                                                                                              {"row": [1], "count": 1}, {"row": [2], "count": 1}]
    assert rec["set_equal"] and not rec["tlp_ok"] and rec["verdict"] == "DOMAIN_FAIL"
    _, left = run_case("P=union_all|Q=left_join|F=gt0")
    assert len(left["query_rows"]["base"]) == 8 and left["tlp_ok"]


def test_missing_unknown_branch_and_falsely_passing_set_comparison():
    _, rec = run_case("P=omit_unknown|Q=scan|F=flag")
    assert [r[0] for r in rec["query_rows"]["unknown"]] == [None, 1]            # executed and collected, then discarded
    assert [r[0] for r in rec["combined_rows"]] == [None, 0, 1, 2]
    assert rec["set_equal"] is True and rec["tlp_ok"] is False and rec["verdict"] == "DOMAIN_FAIL"
    _, good = run_case("P=union_all|Q=scan|F=flag")
    assert [r[0] for r in good["combined_rows"]] == [None, None, 0, 1, 1, 2] and good["verdict"] == "PASS"
    assert rec["provenance"]["statements"][5]["kind"] == "data:unknown"


def test_total_predicates_and_empty_unknown_let_omit_unknown_pass():
    for q in adapter.QUERIES:
        _, rec = run_case(f"P=omit_unknown|Q={q}|F=is_null")
        assert rec["query_rows"]["unknown"] == [] and rec["verdict"] == "PASS"
    for q in ("filtered", "inner_join"):
        assert run_case(f"P=omit_unknown|Q={q}|F=or")[1]["verdict"] == "PASS"
    assert run_case("P=omit_unknown|Q=scan|F=or")[1]["verdict"] == "DOMAIN_FAIL"
    assert run_case("P=dedup_union|Q=filtered|F=is_null")[1]["verdict"] == "PASS"       # distinct projected rows


def test_lost_base_filter_is_caught_by_the_model_check(monkeypatch):
    real = adapter.build_sql

    def lossy(query, predicate):
        sql = real(query, predicate)
        sql["true"] = sql["true"].replace("(i.grp = 'a') AND", "(TRUE) AND")
        return sql
    monkeypatch.setattr(adapter, "build_sql", lossy)
    _, rec = run_case("P=union_all|Q=filtered|F=gt0")
    assert rec["query_checks"]["true"] is False and rec["query_checks"]["base"] is True and rec["verdict"] == "DOMAIN_FAIL"
    assert [r[0] for r in rec["query_rows"]["true"]] == [1, 1, 2]                 # grp b rows leaked into the true branch


@pytest.mark.parametrize("bad", [[("x",)], [(1, 2)], [()], None, [(1.5,)], [(True,)]])
def test_malformed_sql_results_are_infrastructure_errors(monkeypatch, bad):
    monkeypatch.setattr(FakeConnection, "run", lambda self, text: None if text.startswith(("BEGIN", "COMMIT")) else
                        ([[FIXTURE, runtime.READER, "repeatable read", "on", 1, "1:1:", "v", self.app, "5s"]] if text == runtime.PROVENANCE else bad))
    with pytest.raises((ValueError, TypeError)):
        run_case("P=union_all|Q=scan|F=gt0")


@pytest.mark.parametrize("prov", [{"user": "postgres"}, {"transaction_isolation": "read committed"}, {"transaction_read_only": "off"},
                                  {"database": "postgres"}, {"backend_pid": "42"}, {"snapshot": "garbage"}, {"application_name": "other"}])
def test_transaction_and_role_guards(prov):
    FakeConnection.prov = prov
    with pytest.raises(RuntimeError):
        run_case("P=union_all|Q=scan|F=gt0")


@pytest.mark.parametrize("fixture", [None, "", "as0927_d14b_other", "postgres", "as0927_d14b_sql_X; DROP"])
def test_fixture_name_guard(monkeypatch, fixture):
    if fixture is None:
        monkeypatch.delenv("D14B_FIXTURE", raising=False)
    else:
        monkeypatch.setenv("D14B_FIXTURE", fixture)
    with pytest.raises(RuntimeError):
        run_case("P=union_all|Q=scan|F=gt0")


def test_tampered_records_are_detected():
    cid = "P=omit_unknown|Q=scan|F=flag"
    _, rec = run_case(cid)
    own = verify.own_case(FX, *parse(cid))
    for key, value in (("tlp_ok", True), ("verdict", "PASS"), ("combined_rows", rec["query_rows"]["base"])):
        t = copy.deepcopy(rec)
        t[key] = value
        assert [k for k, g, w in verify.compare_record(t, own) if g != w]
    t = copy.deepcopy(rec)
    t["provenance"]["statements"] = t["provenance"]["statements"][:5] + t["provenance"]["statements"][6:]   # unknown query omitted
    assert verify.provenance_problems(t, FIXTURE, "PostgreSQL 16.9 (fake)")


def test_setup_errors_raise():
    runtime._state.clear()
    for calls in (lambda r: (r.begin(), r.query("scan")), lambda r: (r.begin(), r.impl("set_union")),
                  lambda r: (r.begin(), r.impl("union_all"), r.query("cross_join")), lambda r: (r.begin(), r.impl("union_all"), r.query("scan"), r.finish()),
                  lambda r: (r.begin(), r.begin())):
        runtime._state.clear()
        with pytest.raises((RuntimeError, ValueError)):
            calls(runtime)


def test_verifier_parser_on_a_locally_composed_candidate(tmp_path):
    """Preflight: compose one candidate as the Reader renders it, parse it with the verifier, and run it
    in a fresh interpreter against a pg8000 stub that answers from the fake evaluator's rows."""
    sources = {m: (HERE / f"{m}.py").read_text(encoding="utf-8") for m in build_spec.MODULES}
    head, digests = build_spec.head_value(sources)
    slots, _ = build_spec.layout(head)
    pick = {"IMPL": 1, "QUERY": 0, "PREDICATE": 2}                                    # omit_unknown, scan, flag
    values = [s[1][pick.get(s[0], 0)] for s in slots]
    text = verify.join_row(values, [s[2] for s in slots])
    calls, inlined = verify.parse_candidate(text)
    cid = verify.case_of(calls[:-1])
    assert calls[-1] == ["finish"] and cid == "P=omit_unknown|Q=scan|F=flag"
    assert {k: verify.sha256(v.encode()) for k, v in inlined.items()} == digests
    answers = {s: [list(r) for r in fake_rows(s)] for s in adapter.build_sql("scan", "flag").values()}
    stub = tmp_path / "pg8000"
    stub.mkdir()
    (stub / "__init__.py").write_text("")
    (stub / "native.py").write_text(
        "import json\nANSWERS = json.loads(%r)\n" % json.dumps(answers) +
        "class Connection:\n"
        "    def __init__(self, **kw):\n        self.kw = kw\n"
        "    def run(self, text):\n"
        "        if text.startswith('BEGIN') or text == 'COMMIT':\n            return None\n"
        "        if text.startswith('SELECT current_database()'):\n"
        "            return [[self.kw['database'], self.kw['user'], 'repeatable read', 'on', 7, '9:9:', 'stub', self.kw['application_name'], '5s']]\n"
        "        return ANSWERS[text]\n"
        "    def close(self):\n        pass\n")
    env = dict(os.environ, PYTHONPATH=str(tmp_path), D14B_FIXTURE=FIXTURE)
    r = subprocess.run([sys.executable, "-c", text], capture_output=True, text=True, timeout=60, env=env)
    tokens = dict(t.split("=", 1) for t in r.stdout.split() if "=" in t)
    rec = json.loads(base64.urlsafe_b64decode(tokens["rec"]))
    assert r.returncode == 0 and rec["id"] == cid and rec["verdict"] == FROZEN[cid]["predicted_outcome"] == "DOMAIN_FAIL"
    assert {k: rec[k] for k in verify.FROZEN_KEYS} == {k: FROZEN[cid][k] for k in verify.FROZEN_KEYS} and rec["source_sha256"] == digests
    with pytest.raises(ValueError):
        verify.parse_candidate(text.replace("_verdict = finish()", "_verdict = 0"))


def test_precheck_and_bootstrap_rows():
    rep = explore.precheck()
    assert rep["cases_equal_frozen"] and rep["counts"] == {"cases": 72, "families": 24, "data_selects": 288}
    assert len(rep["failures_hidden_by_sets"]) == 23
    import fixture
    boot = fixture.bootstrap_sql("as0927_d14b_sql_x")
    assert "(3, 'a', 1, NULL)" in boot and "(6, 'b', NULL, NULL)" in boot and boot.count("CREATE INDEX") == 0 and "TRIGGER" not in boot
    items = "id,grp,val,flag\n1,a,NULL,t\n2,a,0,f\n3,a,1,NULL\n4,b,1,t\n5,b,2,f\n6,b,NULL,NULL\n"
    tags = "item_id,tag\n1,p\n1,q\n3,p\n4,p\n4,q\n5,p\n"
    assert fixture.fixture_rows_from_export(items, tags) == FX == verify.csv_fixture(items, tags)


def test_oracle_and_model_are_policy_blind_and_model_runs_no_sql():
    for f in ("oracle.py", "model.py"):
        tree = ast.parse((HERE / f).read_text())
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {a.arg for n in ast.walk(tree) if isinstance(n, ast.arguments) for a in n.args}
        literals = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        imports = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} | {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        assert not any("policy" in n for n in names) and not literals & set(adapter.POLICIES), f
        assert not imports & {"adapter", "runtime", "pg8000"} and not any("SELECT" in l for l in literals), f


def test_verifier_and_explorer_import_nothing_from_the_implementation():
    for f in ("verify.py", "explore.py"):
        mods = {n.names[0].name.split(".")[0] if isinstance(n, ast.Import) else (n.module or "").split(".")[0]
                for n in ast.walk(ast.parse((HERE / f).read_text())) if isinstance(n, (ast.Import, ast.ImportFrom))}
        assert not mods & {"adapter", "model", "oracle", "runtime", "fixture", "derive", "pg8000"}, (f, mods)


def test_spec_matches_fresh_build():
    r = subprocess.run([sys.executable, str(HERE / "build_spec.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.skipif(not os.environ.get("D14B_TEST_FIXTURE_STAMP"), reason="real probe runs only against a named retained fixture")
def test_real_sandbox_connectivity_probe(tmp_path, monkeypatch):
    import fixture
    n = fixture.names(os.environ["D14B_TEST_FIXTURE_STAMP"])
    probe = tmp_path / "probe.py"
    probe.write_text(fixture.PROBE)
    res = fixture.run_sandboxed(n["container"], n["image"], probe)
    line = next(l for l in res["stdout"].splitlines() if l.startswith("D14B_PROBE "))
    out = json.loads(line[len("D14B_PROBE "):])
    assert res["exit_code"] == 0 and res["attached_targets"] == 1 and out["counts"] == [6, 6]
    assert out["provenance"][:4] == [n["database"], runtime.READER, "repeatable read", "on"]
    assert "read-only transaction" in out["write_refused"] and out["external_dns"].startswith("blocked")
