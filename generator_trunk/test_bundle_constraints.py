#!/usr/bin/env python3
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

"""STEP 35 — constraint dry-run + explain tests.

Covers the step's acceptance: the tryout rule removes 24 of 96 rows (→ 72 retained); the
dry-run report is non-destructive and exposes per-rule matches + overlap + unique removals +
retained; `bundle constraints explain` lists each rule with its referenced sheets/params and
bounded samples; and a REAL Postgres dry-run leaves the table untouched while the actual sieve
removes the same rows it reported (run: `python3 -m pytest test_bundle_constraints.py -q`)."""
import itertools
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "constraints"))
import sieve as sv  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
from bundle import config, stages  # noqa: E402
import fwgen as fg  # noqa: E402

_TRYOUT_SPEC_DIR = HERE / "tryout_own" / "spec"


# ───────────────────────── in-memory report logic (no DB) ──────────────────────────
_TRYOUT_MODE = {'MODE = "strict"': {"tier": 2}, 'MODE = "legacy"': {"tier": 1}}
_TRYOUT_PAY = {'PAYLOAD_KIND = "ascii"': {"unicode": 0}, 'PAYLOAD_KIND = "unicode"': {"unicode": 1}}
_TRYOUT_SIDECAR = {
    "version": 1, "params": {"MODE": _TRYOUT_MODE, "PAYLOAD": _TRYOUT_PAY},
    "constraints": [{"id": "strict_ascii_ingress_policy", "sheets": ["MODE", "PAYLOAD"],
                     "when": "MODE.tier == 2 and PAYLOAD.unicode == 1", "gate": {}}],
}


def _tryout_rows():
    """96 decoded mandatory rows = MODE(2) × PAYLOAD(2) × 24 other-dim combos (ORDER 6 × FEATURES 4)."""
    rows = []
    for _other in range(24):
        for m in _TRYOUT_MODE:
            for p in _TRYOUT_PAY:
                rows.append([{"sheet": "MODE", "value": m, "pos": 1},
                             {"sheet": "PAYLOAD", "value": p, "pos": 4}])
    return rows


def test_tryout_rule_removes_24_of_96_leaving_72():
    rep = sv.sieve(_tryout_rows(), _TRYOUT_SIDECAR)
    assert rep["scanned"] == 96
    assert rep["matched"]["strict_ascii_ingress_policy"] == 24      # the tryout rule: 24 removals
    assert rep["unique_removals"] == 24
    assert rep["retained"] == 72
    assert rep["overlap"] == 0


# A 2-rule sidecar where one row trips BOTH rules → explicit overlap semantics.
_OVERLAP_SIDECAR = {
    "version": 1,
    "params": {"A": {"a11": {"charge": 2}, "a12": {"charge": -1}},
               "C": {"c11": {"charge": -2}, "c12": {"charge": 3}}},
    "constraints": [
        {"id": "ban_a11_c11", "polarity": "forbid", "pairs": [{"A": "a11", "C": "c11"}], "gate": {}},
        {"id": "any_negative", "polarity": "forbid", "sheets": ["A", "C"],
         "when": "A.charge < 0 or C.charge < 0", "gate": {}},
    ],
}


def _pair(a, c):
    return [{"sheet": "A", "value": a, "pos": 0}, {"sheet": "C", "value": c, "pos": 1}]


def test_overlap_semantics_are_explicit():
    rows = [_pair("a11", "c11"),   # ban_a11_c11 (pair) AND any_negative (c11 charge<0) → BOTH
            _pair("a12", "c12"),   # any_negative only (a12 charge<0)
            _pair("a11", "c12")]   # neither (both charges > 0, no banned pair) → retained
    rep = sv.sieve(rows, _OVERLAP_SIDECAR)
    assert rep["matched"] == {"ban_a11_c11": 1, "any_negative": 2}
    assert rep["unique_removals"] == 2          # a row hit by both rules is ONE removal
    assert rep["overlap"] == 1                  # exactly the doubly-matched row
    assert rep["retained"] == 1
    # documented relationship for ≤2 rules: Σ per-rule − unique_removals == overlap
    assert rep["total_rule_matches"] - rep["unique_removals"] == rep["overlap"]


def test_format_explain_and_sample_output_bounded():
    rows = _tryout_rows()
    rep = sv.sieve(rows, _TRYOUT_SIDECAR, sample=3)
    text = sv.format_explain(_TRYOUT_SIDECAR, rep, sample=3)
    assert "strict_ascii_ingress_policy" in text
    assert "sheets=['MODE', 'PAYLOAD']" in text and "tier" in text and "unicode" in text
    assert "would remove 24 row(s)" in text
    assert "scanned 96" in text and "retained 72" in text
    assert text.count("✗  ") <= 3 and text.count("✓  ") <= 3   # samples are bounded


# n-ary: a bond may reference >=3 sheets (a forbidden/required tuple or a `when` over them).
_TERNARY_SIDECAR = {
    "version": 1,
    "params": {"A": {"a1": {}}, "B": {"b1": {}}, "C": {"c1": {}}},
    "constraints": [
        {"id": "ternary_bond", "sheets": ["A", "B", "C"],
         "when": "A.value == 'a1' and B.value == 'b1' and C.value == 'c1'", "gate": {}},
    ],
}

# arity < 2 is NOT a bond — still skipped (and strict-rejected).
_UNARY_SIDECAR = {
    "version": 1,
    "params": {"A": {"a1": {}}},
    "constraints": [
        {"id": "unary_not_a_bond", "sheets": ["A"], "pairs": [{"A": "a1"}], "gate": {}},
    ],
}


def _abc_row():
    return [[{"sheet": "A", "value": "a1", "pos": 0},
             {"sheet": "B", "value": "b1", "pos": 1},
             {"sheet": "C", "value": "c1", "pos": 2}]]


def test_ternary_bond_is_enforced_not_skipped():
    """n-ary bonds (>=3 sheets) are first-class now: the matching A/B/C row is removed."""
    rep = sv.sieve(_abc_row(), _TERNARY_SIDECAR)
    assert rep["scanned"] == 1
    assert rep["unique_removals"] == 1
    assert rep["retained"] == 0
    assert rep["matched"] == {"ternary_bond": 1}
    assert rep["unsupported_constraint_count"] == 0


def test_ternary_pairs_bond_matches_full_tuple_only():
    sc = {"version": 1, "params": {},
          "constraints": [{"id": "trio", "sheets": ["A", "B", "C"],
                           "pairs": [{"A": "a1", "B": "b1", "C": "c1"}], "gate": {}}]}
    hit = [[{"sheet": "A", "value": "a1", "pos": 0}, {"sheet": "B", "value": "b1", "pos": 1},
            {"sheet": "C", "value": "c1", "pos": 2}]]
    miss = [[{"sheet": "A", "value": "a1", "pos": 0}, {"sheet": "B", "value": "b2", "pos": 1},
             {"sheet": "C", "value": "c1", "pos": 2}]]
    assert sv.sieve(hit, sc)["unique_removals"] == 1
    assert sv.sieve(miss, sc)["unique_removals"] == 0


def test_require_polarity_removes_rows_missing_the_required_tuple():
    sc = {"version": 1, "params": {},
          "constraints": [{"id": "need_a1_b1", "sheets": ["A", "B"], "polarity": "require",
                           "pairs": [{"A": "a1", "B": "b1"}], "gate": {}}]}
    have = [[{"sheet": "A", "value": "a1", "pos": 0}, {"sheet": "B", "value": "b1", "pos": 1}]]
    lack = [[{"sheet": "A", "value": "a1", "pos": 0}, {"sheet": "B", "value": "b2", "pos": 1}]]
    assert sv.sieve(have, sc)["unique_removals"] == 0     # required tuple present -> kept
    assert sv.sieve(lack, sc)["unique_removals"] == 1     # required tuple absent -> removed


def test_gate_adjacent_and_within_generalize_to_three_sheets():
    base = {"id": "trio_adj", "sheets": ["A", "B", "C"],
            "pairs": [{"A": "a1", "B": "b1", "C": "c1"}], "gate": {"adjacent": True}}
    adj = {"version": 1, "params": {}, "constraints": [base]}
    contiguous = [[{"sheet": "A", "value": "a1", "pos": 2}, {"sheet": "B", "value": "b1", "pos": 3},
                   {"sheet": "C", "value": "c1", "pos": 4}]]
    spread = [[{"sheet": "A", "value": "a1", "pos": 0}, {"sheet": "B", "value": "b1", "pos": 3},
               {"sheet": "C", "value": "c1", "pos": 4}]]
    assert sv.sieve(contiguous, adj)["unique_removals"] == 1   # max-min == k-1 -> adjacent
    assert sv.sieve(spread, adj)["unique_removals"] == 0       # gap -> not adjacent
    within = {"version": 1, "params": {},
              "constraints": [{**base, "id": "trio_within", "gate": {"within": 4}}]}
    assert sv.sieve(spread, within)["unique_removals"] == 1    # span 4 <= 4 -> within


# ───────────────────────── Many:Many (`sets`) cross-product bonds ───────────────────
def _ac_rows():
    sheets = {"A": ["a1", "a2", "a3"], "C": ["c1", "c2", "c3"]}
    return [[{"sheet": s, "value": v, "pos": i} for i, (s, v) in enumerate(zip(sheets, combo))]
            for combo in itertools.product(*sheets.values())]      # 9 rows


def test_sets_is_cross_product_not_disjunction():
    """sets {a1,a3}×{c1,c2} forbids all 4 pairings; the same values as PAIRS forbid only 2."""
    mm = {"version": 1, "params": {}, "constraints": [
        {"id": "mm", "polarity": "forbid", "sheets": ["A", "C"],
         "sets": {"A": ["a1", "a3"], "C": ["c1", "c2"]}, "gate": {}}]}
    dj = {"version": 1, "params": {}, "constraints": [
        {"id": "dj", "polarity": "forbid", "sheets": ["A", "C"],
         "pairs": [{"A": "a1", "C": "c1"}, {"A": "a3", "C": "c2"}], "gate": {}}]}
    assert sv.sieve(_ac_rows(), mm)["unique_removals"] == 4     # 2×2 cross product
    assert sv.sieve(_ac_rows(), dj)["unique_removals"] == 2     # disjunction of 2 tuples
    assert sv.sieve(_ac_rows(), mm)["unique_removals"] != sv.sieve(_ac_rows(), dj)["unique_removals"]


def test_sets_require_keeps_only_the_cross_product():
    req = {"version": 1, "params": {}, "constraints": [
        {"id": "req", "polarity": "require", "sheets": ["A", "C"],
         "sets": {"A": ["a1", "a3"], "C": ["c1", "c2"]}, "gate": {}}]}
    assert sv.sieve(_ac_rows(), req)["unique_removals"] == 5    # 9 total − 4 kept


def test_sets_nary_three_sheets():
    sheets = {"A": ["a1", "a2"], "B": ["b1", "b2"], "C": ["c1", "c2"]}
    rows = [[{"sheet": s, "value": v, "pos": i} for i, (s, v) in enumerate(zip(sheets, combo))]
            for combo in itertools.product(*sheets.values())]
    sc = {"version": 1, "params": {}, "constraints": [
        {"id": "n3", "polarity": "forbid", "sheets": ["A", "B", "C"],
         "sets": {"A": ["a1"], "B": ["b1", "b2"], "C": ["c2"]}, "gate": {}}]}
    assert sv.sieve(rows, sc)["unique_removals"] == 2          # {a1}×{b1,b2}×{c2}


def test_sets_sheets_derived_and_arity_ok():
    rep = sv.sieve(_ac_rows(), {"version": 1, "params": {}, "constraints": [
        {"id": "x", "polarity": "forbid", "sets": {"A": ["a1"], "C": ["c1"]}, "gate": {}}]})
    assert rep["unsupported_constraint_count"] == 0            # sheets derived from sets keys
    assert rep["unique_removals"] == 1
    assert "A∈{a1}" in sv.describe({"polarity": "forbid", "sets": {"A": ["a1"], "C": ["c1"]}})


def test_unary_constraint_is_unsupported_and_reported():
    row = [[{"sheet": "A", "value": "a1", "pos": 0}]]
    rep = sv.sieve(row, _UNARY_SIDECAR)
    assert rep["unique_removals"] == 0                  # not a bond -> never enforced
    assert rep["unsupported_constraint_count"] == 1
    assert rep["unsupported_constraints"][0]["id"] == "unary_not_a_bond"
    assert rep["unsupported_constraints"][0]["arity"] == 1
    text = sv.format_explain(_UNARY_SIDECAR, rep)
    assert "WARNING: skipped" in text and "unary_not_a_bond" in text


def test_sieve_strict_rejects_unary_non_bond():
    row = [[{"sheet": "A", "value": "a1", "pos": 0}]]
    with pytest.raises(ValueError, match="unary_not_a_bond"):
        sv.sieve(row, _UNARY_SIDECAR, strict=True)


# ─────────────────────────── CLI: `bundle constraints explain` ─────────────────────
def test_cli_constraints_explain_lists_rules_without_a_db():
    r = subprocess.run([sys.executable, str(HERE / "bundle_run.py"),
                        "constraints", "explain", str(HERE / "tryout_own" / "spec")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "strict_ascii_ingress_policy" in r.stdout
    assert "sheets=['MODE', 'PAYLOAD']" in r.stdout and "tier" in r.stdout


def test_cli_constraints_strict_fails_on_non_bond_without_db():
    with tempfile.TemporaryDirectory() as spec_dir:
        (Path(spec_dir) / "unary.toml").write_text('''
[[slots]]
sheet = "A"
key = "a"
values = ["a1", "a2"]
[[slots]]
sheet = "B"
key = "b"
values = ["b1", "b2"]

[[constraints]]
id = "unary_not_a_bond"
sheets = ["A"]
pairs = [ { A = "a1" } ]
gate = {}
''', encoding="utf-8")
        loose = subprocess.run([sys.executable, str(HERE / "bundle_run.py"),
                                "constraints", "explain", spec_dir],
                               capture_output=True, text=True)
        assert loose.returncode == 0, loose.stdout + loose.stderr
        assert "WARNING: skipped" in loose.stdout

        strict = subprocess.run([sys.executable, str(HERE / "bundle_run.py"),
                                 "constraints", "explain", spec_dir, "--strict"],
                                capture_output=True, text=True)
        assert strict.returncode != 0
        assert "unary_not_a_bond" in (strict.stdout + strict.stderr)


# ─────────────────────────── real Postgres dry-run / actual ────────────────────────
def _main_db_password():
    try:
        return json.load(open(HERE / ".bundle-dev-defaults.json")).get("main_db_password", "")
    except (OSError, json.JSONDecodeError):
        return os.environ.get("BUNDLE_MAIN_DB_PASSWORD", "")


def _connect(dbname):
    import pg8000.dbapi
    return pg8000.dbapi.connect(host="127.0.0.1", port=5433, user="postgres",
                                password=_main_db_password(), database=dbname)


class _Slot:
    def __init__(self, sheet, values):
        self.sheet, self.values = sheet, values


def _populate_demo_fw_final(conn):
    """A real Core-shaped fw_final for sheets A/C (4 rows = A×C), delta-against-baseline a11/c11."""
    cur = conn.cursor()
    cur.execute('CREATE TABLE "NumberToValue1" (bigint bigint, value text);')
    cur.executemany('INSERT INTO "NumberToValue1" VALUES (%s,%s);',
                    [(1, "a11"), (2, "a12"), (3, "c11"), (4, "c12")])
    cur.execute('CREATE TABLE fw_final (combi_id bigint, "combos2_A" smallint[], "combos2_C" smallint[]);')
    cur.executemany('INSERT INTO fw_final VALUES (%s,%s,%s);',
                    [(1, None, None), (2, None, [4]), (3, [2], None), (4, [2], [4])])
    cur.execute('CREATE TABLE fw_final_base_copy ("combos2_A" smallint[], "combos2_C" smallint[]);')
    cur.execute('INSERT INTO fw_final_base_copy VALUES (%s,%s);', ([1], [3]))
    conn.commit()
    cur.close()


_DEMO_SPEC_TOML = """
[[slots]]
sheet = "A"
key = "a"
verb = "FW_Combi(1)"
raw = true
values = ["a11", "a12"]

[[slots]]
sheet = "C"
key = "c"
verb = "FW_Combi(1)"
raw = true
values = ["c11", "c12"]

[[params]]
sheet = "A"
value = "a11"
charge = 2
[[params]]
sheet = "A"
value = "a12"
charge = -1
[[params]]
sheet = "C"
value = "c11"
charge = -2
[[params]]
sheet = "C"
value = "c12"
charge = 3

[[constraints]]
id = "ban_a11_c11"
polarity = "forbid"
pairs = [{A = "a11", C = "c11"}]
gate = {}

[[constraints]]
id = "any_negative"
polarity = "forbid"
sheets = ["A", "C"]
when = "A.charge < 0 or C.charge < 0"
gate = {}
"""


def _drop_db(tmpdb):
    admin = _connect("postgres")
    admin.autocommit = True
    admin.cursor().execute(
        f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='{tmpdb}' AND pid<>pg_backend_pid();")
    admin.cursor().execute(f'DROP DATABASE IF EXISTS "{tmpdb}";')
    admin.close()


def test_db_dry_run_leaves_rows_then_actual_sieve_removes_them():
    try:
        admin = _connect("postgres")
    except Exception as exc:                       # noqa: BLE001 - any driver/auth error → skip
        pytest.skip(f"main Postgres (5433) not reachable: {exc}")
    tmpdb = "fw_step35_" + uuid.uuid4().hex[:12]
    admin.autocommit = True
    admin.cursor().execute(f'CREATE DATABASE "{tmpdb}";')
    admin.close()
    try:
        conn = _connect(tmpdb)
        _populate_demo_fw_final(conn)
        slots = [_Slot("A", ["a11", "a12"]), _Slot("C", ["c11", "c12"])]
        code2val, baseline, combos_col, order = sv.build_maps_from_db(conn, "fw_final", slots)

        def count():
            c = conn.cursor(); c.execute("SELECT count(*) FROM fw_final;"); n = c.fetchone()[0]; c.close(); return n

        assert count() == 4
        dry = sv.sieve_fw_final(conn, "fw_final", _OVERLAP_SIDECAR, code2val, order, combos_col,
                                id_col="combi_id", baseline=baseline, dry_run=True)
        # The 4 rows decode to a11+c11, a11+c12, a12+c11, a12+c12. any_negative hits the three with
        # a negative charge (a11+c11, a12+c11, a12+c12); ban_a11_c11 hits a11+c11 → that row trips
        # BOTH (the overlap). Only a11+c12 survives.
        # dry-run reports what WOULD be removed but deletes NOTHING:
        assert dry["scanned"] == 4 and dry["deleted"] == 0
        assert dry["matched"] == {"ban_a11_c11": 1, "any_negative": 3}
        assert dry["unique_removals"] == 3 and dry["overlap"] == 1 and dry["retained"] == 1
        assert dry["total_rule_matches"] - dry["unique_removals"] == dry["overlap"]
        assert count() == 4, "dry-run must NOT delete"

        actual = sv.sieve_fw_final(conn, "fw_final", _OVERLAP_SIDECAR, code2val, order, combos_col,
                                   id_col="combi_id", baseline=baseline, dry_run=False)
        # the actual sieve records the SAME statistics and removes exactly those rows
        assert actual["scanned"] == 4 and actual["deleted"] == 3
        assert actual["matched"] == dry["matched"] and actual["unique_removals"] == dry["unique_removals"]
        assert actual["retained"] == dry["retained"] and actual["overlap"] == dry["overlap"]
        assert count() == 1, "actual sieve must remove the 3 violators"
        conn.close()
    finally:
        _drop_db(tmpdb)


def test_cli_constraints_dry_run_reports_without_deleting():
    """End-to-end `bundle constraints dry-run <spec> --db <name>`: scans a real Core-filled
    fw_final, reports the per-rule/overlap impact, and leaves every row in place."""
    import tempfile
    try:
        admin = _connect("postgres")
    except Exception as exc:                       # noqa: BLE001
        pytest.skip(f"main Postgres (5433) not reachable: {exc}")
    tmpdb = "fw_step35cli_" + uuid.uuid4().hex[:12]
    admin.autocommit = True
    admin.cursor().execute(f'CREATE DATABASE "{tmpdb}";')
    admin.close()
    with tempfile.TemporaryDirectory() as spec_dir:
        (Path(spec_dir) / "demo.toml").write_text(_DEMO_SPEC_TOML, encoding="utf-8")
        try:
            conn = _connect(tmpdb)
            _populate_demo_fw_final(conn)
            conn.close()

            env = dict(os.environ)
            env["BUNDLE_MAIN_DB_PASSWORD"] = _main_db_password()
            r = subprocess.run([sys.executable, str(HERE / "bundle_run.py"),
                                "constraints", "dry-run", spec_dir, "--db", tmpdb, "--main-port", "5433"],
                               capture_output=True, text=True, env=env)
            assert r.returncode == 0, r.stdout + r.stderr
            assert "deletes nothing" in r.stdout
            assert "unique_removals 3" in r.stdout and "overlap 1" in r.stdout and "retained 1" in r.stdout

            conn = _connect(tmpdb)
            c = conn.cursor(); c.execute("SELECT count(*) FROM fw_final;"); n = c.fetchone()[0]; conn.close()
            assert n == 4, "the dry-run command must not delete any fw_final rows"
        finally:
            _drop_db(tmpdb)


def test_live_tryout_core_96_then_dry_run_96_then_actual_72():
    """STEP 35 acceptance on a REAL Generator→Core-produced fw_final (not synthetic): the tryout
    fills 96 mandatory rows; the dry-run reports 24 removals and LEAVES all 96; the actual sieve
    removes exactly those 24 → 72."""
    if shutil.which("java") is None or not stages.CORE_JAR.exists():
        pytest.skip("java / Core jar unavailable")
    try:
        admin = _connect("postgres")
    except Exception as exc:                       # noqa: BLE001
        pytest.skip(f"main Postgres (5433) not reachable: {exc}")
    cfg, _sources = config.resolve_config(cli={})
    spec = fg.load_spec(sorted(_TRYOUT_SPEC_DIR.glob("*.toml"))[0])
    assert fg.estimate_core_combos(spec) == 96       # tryout mandatory product

    tmpdb = "fw_live35_" + uuid.uuid4().hex[:12]
    admin.autocommit = True
    admin.cursor().execute(f'CREATE DATABASE "{tmpdb}";')
    admin.close()
    scratch = Path(tempfile.mkdtemp(prefix="fwlive35-"))
    try:
        # 1) Generator → workbook → Core fills the REAL fw_final.
        xlsx = stages.stage_gen(_TRYOUT_SPEC_DIR, scratch)
        n_core = stages.stage_core(spec, xlsx, scratch, tmpdb, 5433, n_opt=0, cfg=cfg)
        assert n_core == 96, f"Core should fill 96 mandatory rows, got {n_core}"

        sidecar = {"version": 1, "params": spec.params, "constraints": spec.constraints}
        conn = _connect(tmpdb)
        code2val, baseline, combos_col, order = sv.build_maps_from_db(conn, "fw_final", spec.slots)

        def count():
            c = conn.cursor(); c.execute("SELECT count(*) FROM fw_final;"); n = c.fetchone()[0]; c.close(); return n

        assert count() == 96
        # 2) DRY-RUN: reports 24 removals, deletes NOTHING (leaves 96).
        dry = sv.sieve_fw_final(conn, "fw_final", sidecar, code2val, order, combos_col,
                                id_col="combi_id", baseline=baseline, dry_run=True)
        assert dry["scanned"] == 96
        assert dry["matched"]["strict_ascii_ingress_policy"] == 24
        assert dry["unique_removals"] == 24 and dry["retained"] == 72 and dry["deleted"] == 0
        assert count() == 96, "dry-run on the live Core DB must leave all 96 rows"
        # 3) ACTUAL sieve: removes the same 24 → 72.
        actual = sv.sieve_fw_final(conn, "fw_final", sidecar, code2val, order, combos_col,
                                   id_col="combi_id", baseline=baseline, dry_run=False)
        assert actual["unique_removals"] == 24 and actual["deleted"] == 24 and actual["retained"] == 72
        assert actual["matched"] == dry["matched"]      # same statistics, dry-run vs actual
        assert count() == 72, "actual sieve must leave 72 rows"
        conn.close()
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        _drop_db(tmpdb)


# ───────── Face-2 end-to-end: EVERY link variation through the REAL Bundle, verb-rich ─────────
def _verb_rich_spec() -> str:
    """A spec that makes Core exercise MANY of its verbs (FW_Combi(1), FW_Combi(2), FW_Permut,
    FW_PermutR, FW_Subsets) so the sieve is proven on a rich fw_final — not just a flat cartesian.
    A/B/C are clean FW_Combi(1) (one value per row) so their bond removals stay closed-form; the
    rich-verb sheets multiply the table without disturbing those fractions."""
    def slot(sheet, key, verb, vals):
        return f'[[slots]]\nsheet="{sheet}"\nkey="{key}"\nverb="{verb}"\nraw=true\nvalues={json.dumps(vals)}\n'
    s = 'title="verb-rich link variations"\n[[goals]]\nkey="x"\ndir="max"\n'
    s += slot("HEAD", "head", "FW_Combi(1)", ["h"])
    s += slot("A", "a", "FW_Combi(1)", ["a1", "a2", "a3"])        # clean target (pos 1)
    s += slot("B", "b", "FW_Combi(1)", ["b1", "b2", "b3"])        # clean target (pos 2)
    s += slot("C", "c", "FW_Combi(1)", ["c1", "c2", "c3"])        # clean target (pos 3)
    s += slot("OPS", "ops", "FW_Permut", ["o1", "o2"])            # permutations
    s += slot("PR", "pr", "FW_PermutR(2)", ["p1", "p2"])          # permutations with repetition
    s += slot("HDRS", "hdrs", "FW_Subsets", ["x1", "x2"])         # powerset
    s += slot("K", "k", "FW_Combi(2)", ["k1", "k2", "k3"])        # C(3,2): two values per row
    s += slot("TAIL", "tail", "FW_Combi(1)", ["t"])
    return s


def test_face2_all_link_variations_through_real_bundle():
    """Drives Generator -> Core (real Java + Postgres) on a VERB-RICH spec, then proves EVERY link
    variation the editor can author removes exactly the right rows of the live fw_final: forbid &
    require, enumerated pairs (disjunction) & sets (Many:Many cross product), binary & n-ary, all
    three gates, a `when` predicate, and matching a value inside a multi-value FW_Combi(2) slot.
    Each variation is checked against BOTH a closed-form count and the independently unit-tested pure
    engine (`sv.sieve`) decoded over the real rows; then an actual delete + idempotency re-scan +
    survivor inspection proves the destructive path."""
    if shutil.which("java") is None or not stages.CORE_JAR.exists():
        pytest.skip("java / Core jar unavailable")
    try:
        admin = _connect("postgres")
    except Exception as exc:                       # noqa: BLE001
        pytest.skip(f"main Postgres (5433) not reachable: {exc}")

    cfg, _sources = config.resolve_config(cli={})
    tmpdb = "fw_face2_" + uuid.uuid4().hex[:12]
    admin.autocommit = True
    admin.cursor().execute(f'CREATE DATABASE "{tmpdb}";')
    admin.close()
    scratch = Path(tempfile.mkdtemp(prefix="fwface2-"))
    spec_dir = scratch / "spec"; spec_dir.mkdir()
    (spec_dir / "verbs.toml").write_text(_verb_rich_spec(), encoding="utf-8")
    try:
        spec = fg.load_spec(spec_dir / "verbs.toml")
        xlsx = stages.stage_gen(spec_dir, scratch)
        N = stages.stage_core(spec, xlsx, scratch, tmpdb, 5433, n_opt=0, cfg=cfg)
        assert N > 0 and N % 27 == 0, f"A/B/C are FW_Combi(1)x3 so the table must divide by 27 (got {N})"
        P, A1, TRI = N // 9, N // 3, N // 27     # one A×C pair-block, one A-block, one A×B×C triple

        conn = _connect(tmpdb)
        code2val, baseline, combos_col, order = sv.build_maps_from_db(conn, "fw_final", spec.slots)

        def count():
            c = conn.cursor(); c.execute("SELECT count(*) FROM fw_final;"); n = c.fetchone()[0]; c.close(); return n

        def decode_rows():                        # independent re-decode (mirrors sieve_fw_final)
            cur = conn.cursor()
            cols = [combos_col[s] for s in order]
            cur.execute('SELECT ' + ", ".join(f'"{c}"' for c in cols) + ' FROM fw_final;')
            rows = []
            for rec in cur.fetchall():
                row = []
                for pos, (s, arr) in enumerate(zip(order, rec)):
                    if arr:
                        for code in arr:
                            v = code2val.get(s, {}).get(int(code))
                            if v is not None:
                                row.append({"sheet": s, "value": v, "pos": pos})
                    elif s in baseline:
                        row.append({"sheet": s, "value": baseline[s], "pos": pos})
                rows.append(row)
            cur.close()
            return rows

        assert count() == N
        decoded = decode_rows()
        params = {"A": {"a1": {"n": 1}, "a2": {"n": 2}, "a3": {"n": 3}},
                  "C": {"c1": {"n": 1}, "c2": {"n": 2}, "c3": {"n": 3}}}

        def one(c, p=None):
            return {"version": 1, "params": p or {}, "constraints": [c]}

        # (label, constraint, params, closed-form expected | None=only cross-check the engine)
        cases = [
            ("forbid pairs (disjunction)",
             {"id": "fp", "polarity": "forbid", "sheets": ["A", "C"],
              "pairs": [{"A": "a1", "C": "c1"}, {"A": "a2", "C": "c2"}], "gate": {}}, None, 2 * P),
            ("require pairs",
             {"id": "rp", "polarity": "require", "sheets": ["A", "C"],
              "pairs": [{"A": "a1", "C": "c1"}], "gate": {}}, None, N - P),
            ("forbid sets (Many:Many cross product)",
             {"id": "fs", "polarity": "forbid", "sheets": ["A", "C"],
              "sets": {"A": ["a1", "a2"], "C": ["c1", "c2"]}, "gate": {}}, None, 4 * P),
            ("require sets (Many:Many, green/sought)",
             {"id": "rs", "polarity": "require", "sheets": ["A", "C"],
              "sets": {"A": ["a1", "a2"], "C": ["c1", "c2"]}, "gate": {}}, None, N - 4 * P),
            ("n-ary pairs (3 sheets)",
             {"id": "n3p", "polarity": "forbid", "sheets": ["A", "B", "C"],
              "pairs": [{"A": "a1", "B": "b1", "C": "c1"}], "gate": {}}, None, TRI),
            ("n-ary sets (3 sheets)",
             {"id": "n3s", "polarity": "forbid", "sheets": ["A", "B", "C"],
              "sets": {"A": ["a1"], "B": ["b1", "b2"], "C": ["c1"]}, "gate": {}}, None, 2 * TRI),
            ("n-ary gate adjacent (A,B,C contiguous pos 1,2,3)",
             {"id": "n3adj", "polarity": "forbid", "sheets": ["A", "B", "C"],
              "pairs": [{"A": "a1", "B": "b1", "C": "c1"}], "gate": {"adjacent": True}}, None, TRI),
            ("gate adjacent excludes the far (A,C) pair",
             {"id": "gadj", "polarity": "forbid", "sheets": ["A", "C"],
              "pairs": [{"A": "a1", "C": "c1"}], "gate": {"adjacent": True}}, None, 0),
            ("gate within 2 includes (A,C)",
             {"id": "gwin", "polarity": "forbid", "sheets": ["A", "C"],
              "pairs": [{"A": "a1", "C": "c1"}], "gate": {"within": 2}}, None, P),
            ("when predicate over params",
             {"id": "wp", "polarity": "forbid", "sheets": ["A", "C"],
              "when": "A.n + C.n > 4", "gate": {}}, params, 3 * P),
            ("match a value inside a multi-value FW_Combi(2) slot (K)",
             {"id": "kmv", "polarity": "forbid", "sheets": ["A", "K"],
              "pairs": [{"A": "a1", "K": "k1"}], "gate": {}}, None, None),
        ]

        for label, cons, p, cf in cases:
            sc = one(cons, p)
            expect_engine = sv.sieve(decoded, sc)["unique_removals"]          # pure engine on real rows
            rep = sv.sieve_fw_final(conn, "fw_final", sc, code2val, order, combos_col,
                                    id_col="combi_id", baseline=baseline, dry_run=True)
            assert rep["scanned"] == N, label
            assert rep["deleted"] == 0, f"{label}: dry-run must not delete"
            assert rep["unique_removals"] == expect_engine, \
                f"{label}: DB path {rep['unique_removals']} != pure engine {expect_engine}"
            if cf is not None:
                assert rep["unique_removals"] == cf, f"{label}: got {rep['unique_removals']}, closed-form {cf}"
            if expect_engine:                                                # the rule actually engaged
                assert rep["matched"][cons["id"]] == expect_engine, label
        assert count() == N, "no dry-run may delete a single row"

        # ── actual destructive sieve: forbid-only mix (pairs + Many:Many sets), then prove it ──
        combo = {"version": 1, "params": {}, "constraints": [
            {"id": "del_pair", "polarity": "forbid", "sheets": ["A", "C"],
             "pairs": [{"A": "a1", "C": "c1"}], "gate": {}},
            {"id": "del_sets", "polarity": "forbid", "sheets": ["A", "C"],
             "sets": {"A": ["a2", "a3"], "C": ["c3"]}, "gate": {}}]}        # disjoint: c1 vs c3
        expect_del = P + 2 * P                                              # (a1,c1)=P ; {a2,a3}×{c3}=2P
        act = sv.sieve_fw_final(conn, "fw_final", combo, code2val, order, combos_col,
                                id_col="combi_id", baseline=baseline, dry_run=False)
        assert act["deleted"] == expect_del and act["unique_removals"] == expect_del
        assert count() == N - expect_del
        # idempotent: nothing left for the same rules to remove -> every violator (and only those) is gone
        again = sv.sieve_fw_final(conn, "fw_final", combo, code2val, order, combos_col,
                                  id_col="combi_id", baseline=baseline, dry_run=True)
        assert again["unique_removals"] == 0, "survivors must contain no remaining violators"
        # survivor inspection: not one surviving row violates either rule
        for row in decode_rows():
            vals = {p["sheet"]: {q["value"] for q in row if q["sheet"] == p["sheet"]} for p in row}
            a, c = vals.get("A", set()), vals.get("C", set())
            assert not ("a1" in a and "c1" in c)
            assert not ((a & {"a2", "a3"}) and "c3" in c)
        conn.close()
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        _drop_db(tmpdb)


# ───────────── FW_Optional bonds: enforced on the ASSEMBLED candidate, deferred by the sieve ─────────────
def test_optional_final_bonds_enforce_on_the_assembled_candidate():
    """An FW_Optional value lives in fw_optX and is ASSEMBLED with the mandatory combo by the Reader.
    On the assembled candidate (mandatory placements + the chosen optional placement, or none) the
    bond engine enforces an optional↔final bond exactly — both forbid and require — including the
    'optional action absent → the bond simply does not apply' case."""
    def cand(a, opt):                                   # opt=None => the optional action is ABSENT
        row = [{"sheet": "A", "value": a, "pos": 1}]
        if opt is not None:
            row.append({"sheet": "OPT", "value": opt, "pos": 3})
        return row
    rows = [cand(a, o) for a in ("a1", "a2") for o in (None, "w1", "w2")]    # 6 assembled candidates

    forbid = {"version": 1, "params": {}, "constraints": [
        {"id": "f", "polarity": "forbid", "sheets": ["A", "OPT"],
         "pairs": [{"A": "a1", "OPT": "w1"}], "gate": {}}]}
    rep = sv.sieve(rows, forbid)
    assert rep["unique_removals"] == 1 and rep["retained"] == 5     # only (a1 + w1) is forbidden

    require = {"version": 1, "params": {}, "constraints": [
        {"id": "r", "polarity": "require", "sheets": ["A", "OPT"],
         "pairs": [{"A": "a1", "OPT": "w1"}], "gate": {}}]}
    rep2 = sv.sieve(rows, require)
    # candidates WITHOUT the optional action have no OPT placement → bond doesn't apply → kept;
    # of the 4 present-opt candidates only (a1+w1) satisfies require, the other 3 are removed.
    assert rep2["unique_removals"] == 3 and rep2["retained"] == 3


def test_optional_bonds_deferred_by_fw_final_sieve_not_misapplied_through_real_bundle():
    """REGRESSION + behaviour: FW_Optional sheets are factored into fw_optX (compact storage,
    assembled in the Reader), so an empty optional cell in fw_final means ABSENT — not the slot's
    first value. The sieve must NOT inherit a baseline there (the old bug deleted every a1 row for a
    bond on the optional baseline) and must DEFER any bond touching an optional sheet to assembly,
    while mandatory-only bonds still apply. Driven through real Generator→Core."""
    if shutil.which("java") is None or not stages.CORE_JAR.exists():
        pytest.skip("java / Core jar unavailable")
    try:
        admin = _connect("postgres")
    except Exception as exc:                       # noqa: BLE001
        pytest.skip(f"main Postgres (5433) not reachable: {exc}")

    spec_toml = ('title="optional bonds"\n[[goals]]\nkey="x"\ndir="max"\n'
                 '[[slots]]\nsheet="HEAD"\nkey="head"\nverb="FW_Combi(1)"\nraw=true\nvalues=["h"]\n'
                 '[[slots]]\nsheet="A"\nkey="a"\nverb="FW_Combi(1)"\nraw=true\nvalues=["a1","a2","a3"]\n'
                 '[[slots]]\nsheet="C"\nkey="c"\nverb="FW_Combi(1)"\nraw=true\nvalues=["c1","c2"]\n'
                 '[[slots]]\nsheet="OPT"\nkey="opt"\nverb="FW_Combi(1)"\nraw=true\nflags=["FW_Optional"]\nvalues=["w1","w2"]\n'
                 '[[slots]]\nsheet="TAIL"\nkey="tail"\nverb="FW_Combi(1)"\nraw=true\nvalues=["t"]\n')
    cfg, _sources = config.resolve_config(cli={})
    tmpdb = "fw_opt_" + uuid.uuid4().hex[:12]
    admin.autocommit = True
    admin.cursor().execute(f'CREATE DATABASE "{tmpdb}";')
    admin.close()
    scratch = Path(tempfile.mkdtemp(prefix="fwopt-"))
    spec_dir = scratch / "spec"; spec_dir.mkdir()
    (spec_dir / "opt.toml").write_text(spec_toml, encoding="utf-8")
    try:
        spec = fg.load_spec(spec_dir / "opt.toml")
        n_opt = sum(1 for s in spec.slots if "FW_Optional" in s.flags)
        assert n_opt == 1
        xlsx = stages.stage_gen(spec_dir, scratch)
        N = stages.stage_core(spec, xlsx, scratch, tmpdb, 5433, n_opt=n_opt, cfg=cfg)   # 3×2 = 6 mandatory
        assert N == 6

        conn = _connect(tmpdb)
        code2val, baseline, combos_col, order = sv.build_maps_from_db(conn, "fw_final", spec.slots)
        assert "OPT" not in baseline, "the fix: an FW_Optional slot must NOT inherit a baseline"
        optional_sheets = {s.sheet for s in spec.slots if "FW_Optional" in s.flags}

        def count():
            c = conn.cursor(); c.execute("SELECT count(*) FROM fw_final;"); n = c.fetchone()[0]; c.close(); return n

        # regression: an optional↔final bond, applied to fw_final, must remove NOTHING (old bug: 2)
        opt_only = {"version": 1, "params": {}, "constraints": [
            {"id": "opt_final", "polarity": "forbid", "sheets": ["A", "OPT"],
             "pairs": [{"A": "a1", "OPT": "w1"}], "gate": {}}]}
        r0 = sv.sieve_fw_final(conn, "fw_final", opt_only, code2val, order, combos_col,
                               id_col="combi_id", baseline=baseline, dry_run=True,
                               optional_sheets=optional_sheets)
        assert r0["unique_removals"] == 0                       # NOT 2 — the optional value isn't materialized here
        assert r0["deferred_count"] == 1 and r0["deferred"][0]["id"] == "opt_final"
        assert r0["deferred"][0]["optional_sheets"] == ["OPT"]
        assert any("opt_final" in w and "assembly" in w for w in r0["warnings"])

        # a mandatory-only bond still applies normally alongside the deferred optional one
        mixed = {"version": 1, "params": {}, "constraints": [
            opt_only["constraints"][0],
            {"id": "mand", "polarity": "forbid", "sheets": ["A", "C"],
             "pairs": [{"A": "a1", "C": "c1"}], "gate": {}}]}
        r1 = sv.sieve_fw_final(conn, "fw_final", mixed, code2val, order, combos_col,
                               id_col="combi_id", baseline=baseline, dry_run=False,
                               optional_sheets=optional_sheets)
        assert "opt_final" not in r1["matched"] and r1["deferred_count"] == 1   # optional deferred
        assert r1["matched"]["mand"] == 1 and r1["deleted"] == 1                # A=a1 & C=c1 -> 1 row
        assert count() == N - 1
        conn.close()
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        _drop_db(tmpdb)


def test_optional_optional_bond_fires_only_when_both_present():
    """An optional↔optional bond can fire only when BOTH optional actions are present in the SAME
    assembled candidate — true for a size>=2 optional combo (fw_opt2/fw_opt3), never for a size-1
    combo (fw_opt1: exactly one optional action present). Pure-engine, models the Reader's merge."""
    POS = {"O1": 3, "O2": 4, "O3": 5}                  # each optional sheet sits at a fixed column

    def cand(a, present):                              # present: {optional-sheet: value} that are ON
        row = [{"sheet": "A", "value": a, "pos": 1}]
        for s, v in present.items():
            row.append({"sheet": s, "value": v, "pos": POS[s]})
        return row

    bond = {"version": 1, "params": {}, "constraints": [
        {"id": "o1_o3", "polarity": "forbid", "sheets": ["O1", "O3"],
         "pairs": [{"O1": "x", "O3": "z"}], "gate": {}}]}
    # fw_opt1-style: exactly ONE optional present per candidate -> O1 and O3 never co-occur
    opt1 = [cand("a1", {"O1": "x"}), cand("a1", {"O2": "y"}), cand("a1", {"O3": "z"})]
    assert sv.sieve(opt1, bond)["unique_removals"] == 0
    # fw_opt3-style: all three present -> the (x, z) pairing fires
    assert sv.sieve([cand("a1", {"O1": "x", "O2": "y", "O3": "z"})], bond)["unique_removals"] == 1
    assert sv.sieve([cand("a1", {"O1": "x", "O2": "y", "O3": "zz"})], bond)["unique_removals"] == 0
    # require flavour: a size-1 candidate (no O1+O3 pair) is untouched; an all-present mismatch is removed
    req = {"version": 1, "params": {}, "constraints": [
        {"id": "need", "polarity": "require", "sheets": ["O1", "O3"],
         "pairs": [{"O1": "x", "O3": "z"}], "gate": {}}]}
    assert sv.sieve([cand("a1", {"O1": "x"})], req)["unique_removals"] == 0
    assert sv.sieve([cand("a1", {"O1": "x", "O2": "y", "O3": "zz"})], req)["unique_removals"] == 1


def test_multiple_optional_tables_through_real_bundle():
    """Several FW_Optional sheets make Core materialize MULTIPLE optional-combo tables at once
    (fw_opt1, fw_opt2, fw_opt3). Proves, on REAL Generator→Core output: (1) every optional sheet is
    excluded from the fw_final baseline and the base_copy optional columns are NULL (=absent);
    (2) the sieve DEFERS every bond touching an optional sheet — optional↔final AND optional↔optional
    — while a mandatory↔mandatory bond still applies; (3) on a REAL assembled candidate (mandatory ∪
    a size-3 optional combo from fw_opt3, exactly the Reader's base∪final∪opt merge) an
    optional↔optional bond fires, but never on a size-1 fw_opt1 candidate (only one optional present)."""
    if shutil.which("java") is None or not stages.CORE_JAR.exists():
        pytest.skip("java / Core jar unavailable")
    try:
        admin = _connect("postgres")
    except Exception as exc:                       # noqa: BLE001
        pytest.skip(f"main Postgres (5433) not reachable: {exc}")

    def sl(sheet, key, vals, opt=False):
        flags = 'flags=["FW_Optional"]\n' if opt else ''
        return f'[[slots]]\nsheet="{sheet}"\nkey="{key}"\nverb="FW_Combi(1)"\nraw=true\n{flags}values={json.dumps(vals)}\n'
    spec_toml = ('title="multi optional"\n[[goals]]\nkey="x"\ndir="max"\n'
                 + sl("HEAD", "head", ["h"]) + sl("A", "a", ["a1", "a2"]) + sl("B", "b", ["b1", "b2"])
                 + sl("O1", "o1", ["o1v1", "o1v2"], True) + sl("O2", "o2", ["o2v1", "o2v2"], True)
                 + sl("O3", "o3", ["o3v1", "o3v2"], True) + sl("TAIL", "tail", ["t"]))
    cfg, _sources = config.resolve_config(cli={})
    tmpdb = "fw_mopt_" + uuid.uuid4().hex[:12]
    admin.autocommit = True
    admin.cursor().execute(f'CREATE DATABASE "{tmpdb}";')
    admin.close()
    scratch = Path(tempfile.mkdtemp(prefix="fwmopt-"))
    spec_dir = scratch / "spec"; spec_dir.mkdir()
    (spec_dir / "m.toml").write_text(spec_toml, encoding="utf-8")
    try:
        spec = fg.load_spec(spec_dir / "m.toml")
        n_opt = sum(1 for s in spec.slots if "FW_Optional" in s.flags)
        assert n_opt == 3
        xlsx = stages.stage_gen(spec_dir, scratch)
        N = stages.stage_core(spec, xlsx, scratch, tmpdb, 5433, n_opt=n_opt, cfg=cfg)
        assert N == 4                                  # A×B mandatory product (2×2)

        conn = _connect(tmpdb); cur = conn.cursor()
        cur.execute("select table_name from information_schema.tables where table_name like 'fw_opt%';")
        opt_tables = {r[0] for r in cur.fetchall()}
        assert {"fw_opt1", "fw_opt2", "fw_opt3"} <= opt_tables    # multiple optional tables coexist

        code2val, baseline, combos_col, order = sv.build_maps_from_db(conn, "fw_final", spec.slots)
        opt_sheets = {s.sheet for s in spec.slots if "FW_Optional" in s.flags}
        assert opt_sheets.isdisjoint(baseline)                   # (1) no optional sheet inherits a baseline
        cur.execute("select " + ", ".join(f'"{combos_col[s]}"' for s in ("O1", "O2", "O3"))
                    + " from fw_final_base_copy limit 1;")
        assert all(v is None for v in cur.fetchone())            # base_copy optional cols = NULL (absent)

        # (2) sieve defers every optional-touching bond; the mandatory bond still applies
        sc = {"version": 1, "params": {}, "constraints": [
            {"id": "mand", "polarity": "forbid", "sheets": ["A", "B"], "pairs": [{"A": "a1", "B": "b1"}], "gate": {}},
            {"id": "opt_final", "polarity": "forbid", "sheets": ["A", "O1"], "pairs": [{"A": "a1", "O1": "o1v1"}], "gate": {}},
            {"id": "opt_opt", "polarity": "forbid", "sheets": ["O1", "O3"], "pairs": [{"O1": "o1v1", "O3": "o3v1"}], "gate": {}}]}
        rep = sv.sieve_fw_final(conn, "fw_final", sc, code2val, order, combos_col, id_col="combi_id",
                                baseline=baseline, dry_run=True, optional_sheets=opt_sheets)
        assert rep["deferred_count"] == 2
        assert {d["id"] for d in rep["deferred"]} == {"opt_final", "opt_opt"}
        assert rep["matched"].get("mand") == 1 and "opt_final" not in rep["matched"]

        # (3) REAL assembled candidate = base_copy ∪ mandatory(fw_final) ∪ optional(fw_optX), nulls dropped
        def rows_of(table):
            cur.execute("select " + ", ".join(f'"{combos_col[s]}"' for s in order) + f' from "{table}";')
            return cur.fetchall()
        final_arrays = rows_of("fw_final")[0]

        def assemble(opt_arrays):
            place = []
            for pos, s in enumerate(order):
                arr = opt_arrays[pos] if s in opt_sheets else final_arrays[pos]
                if arr:
                    for code in arr:
                        place.append({"sheet": s, "value": code2val[s][int(code)], "pos": pos})
                elif s not in opt_sheets and s in baseline:
                    place.append({"sheet": s, "value": baseline[s], "pos": pos})
            return place

        opt3, opt1 = rows_of("fw_opt3"), rows_of("fw_opt1")
        o1i, o3i = order.index("O1"), order.index("O3")
        r3 = opt3[0]                                              # both O1 and O3 present in a size-3 combo
        v_o1, v_o3 = code2val["O1"][int(r3[o1i][0])], code2val["O3"][int(r3[o3i][0])]
        bond = {"version": 1, "params": {}, "constraints": [
            {"id": "oo", "polarity": "forbid", "sheets": ["O1", "O3"], "pairs": [{"O1": v_o1, "O3": v_o3}], "gate": {}}]}
        assert sv.sieve([assemble(r3)], bond)["unique_removals"] == 1      # both present -> fires
        assert all(sv.sieve([assemble(r1)], bond)["unique_removals"] == 0 for r1 in opt1)  # only one present -> never
        conn.close()
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        _drop_db(tmpdb)


def test_optional_bonds_enforced_in_reader_at_assembly():
    """SCALABLE enforcement, end-to-end through the REAL Reader: the sieve compiles the deferred
    optional↔optional bond into a COMPACT per-bond spec (size O(bonds), NOT the candidate count), and
    the rebuilt Reader evaluates it per assembled candidate, skipping exactly the forbidden ones. The
    forbidden set is cross-checked against the engine's verdict on every real assembled candidate, and
    a control run (no bonds file) re-emits everything (proves the no-op / non-breaking path)."""
    if shutil.which("java") is None or not stages.CORE_JAR.exists() or not stages.READER_JAR.exists():
        pytest.skip("java / Core jar / Reader jar unavailable")
    try:
        admin = _connect("postgres")
    except Exception as exc:                       # noqa: BLE001
        pytest.skip(f"main Postgres (5433) not reachable: {exc}")

    def sl(sheet, key, vals, opt=False):
        flags = 'flags=["FW_Optional"]\n' if opt else ''
        return f'[[slots]]\nsheet="{sheet}"\nkey="{key}"\nverb="FW_Combi(1)"\nraw=true\n{flags}values={json.dumps(vals)}\n'
    spec_toml = ('title="optional reader bonds"\n[[goals]]\nkey="x"\ndir="max"\n'
                 + sl("HEAD", "head", ["h"]) + sl("A", "a", ["a1", "a2"]) + sl("B", "b", ["b1", "b2"])
                 + sl("O1", "o1", ["o1v1", "o1v2"], True) + sl("O2", "o2", ["o2v1", "o2v2"], True)
                 + sl("O3", "o3", ["o3v1", "o3v2"], True) + sl("TAIL", "tail", ["t"])
                 + '\n[[constraints]]\nid="oo"\nsheets=["O1","O3"]\n'
                   'pairs=[{O1="o1v1",O3="o3v1"}]\ngate={}\n')   # optional↔optional: fires only when both present
    cfg, _sources = config.resolve_config(cli={})
    tmpdb = "fw_rdrbond_" + uuid.uuid4().hex[:12]
    admin.autocommit = True
    admin.cursor().execute(f'CREATE DATABASE "{tmpdb}";')
    admin.close()
    scratch = Path(tempfile.mkdtemp(prefix="fwrdrbond-"))
    spec_dir = scratch / "spec"; spec_dir.mkdir()
    (spec_dir / "o.toml").write_text(spec_toml, encoding="utf-8")
    try:
        spec = fg.load_spec(spec_dir / "o.toml")
        n_opt = sum(1 for s in spec.slots if "FW_Optional" in s.flags)
        xlsx = stages.stage_gen(spec_dir, scratch)
        fw_final = stages.stage_core(spec, xlsx, scratch, tmpdb, 5433, n_opt=n_opt, cfg=cfg)
        stages.stage_sieve(spec, scratch, tmpdb, 5433, fw_final, cfg)

        # the compiled bond spec is COMPACT — one line for the one bond, independent of candidates
        bonds_path = scratch / "optional_bonds.txt"
        bond_lines = [ln for ln in bonds_path.read_text().splitlines() if ln.strip()]
        assert len(bond_lines) == 1, bond_lines               # O(bonds), not O(candidate space)

        # EXPECTED forbidden ids: assemble EVERY (final, opt) the Reader way, ask the engine.
        conn = _connect(tmpdb); cur = conn.cursor()
        code2val, baseline, combos_col, order = sv.build_maps_from_db(conn, "fw_final", spec.slots)
        opt_sheets = {s.sheet for s in spec.slots if "FW_Optional" in s.flags}
        sidecar = {"version": 1, "params": spec.params, "constraints": spec.constraints}

        def rows_of(table):
            cur.execute("select combi_id, " + ", ".join(f'"{combos_col[s]}"' for s in order) + f' from "{table}";')
            return cur.fetchall()

        def decode(arrays, want_opt):
            place = []
            for pos, (s, arr) in enumerate(zip(order, arrays)):
                is_opt = s in opt_sheets
                if want_opt != is_opt:
                    continue
                if arr:
                    for code in arr:
                        v = code2val.get(s, {}).get(int(code))
                        if v is not None:
                            place.append({"sheet": s, "value": v, "pos": pos})
                elif (not is_opt) and (s in baseline):
                    place.append({"sheet": s, "value": baseline[s], "pos": pos})
            return place

        finals = [(r[0], decode(r[1:], False)) for r in rows_of("fw_final")]
        expected_forbidden, size_counts = set(), {}
        for t in ("fw_opt1", "fw_opt2", "fw_opt3"):
            size = t[len("fw_opt"):]
            opts = [(r[0], decode(r[1:], True)) for r in rows_of(t)]
            size_counts[size] = len(opts)
            for fid, mp in finals:
                for oid, op in opts:
                    if sv.row_violations(mp + op, sidecar):
                        expected_forbidden.add(f"{fid}_{oid}_{size}")
        final_cnt = len(finals)
        conn.close()
        assert len(expected_forbidden) > 0

        # READER assembles candidates → loose files, enforcing the bond per candidate.
        stages.stage_reader(scratch, tmpdb, "py", 5433, cfg.results_db_port, fw_final, n_opt=n_opt, cfg=cfg)
        emitted = {p.stem for p in (scratch / "src").glob("*") if p.is_file()}
        assert emitted, "the Reader produced no candidate files"
        # (1) exactly the engine-forbidden candidates are absent; (2) the count matches
        assert expected_forbidden.isdisjoint(emitted), \
            f"forbidden candidates leaked: {sorted(expected_forbidden & emitted)[:5]}"
        expected_total = final_cnt + sum(final_cnt * c for c in size_counts.values())
        assert len(emitted) == expected_total - len(expected_forbidden)
        assert any("_" in e for e in emitted)                  # non-forbidden cartesian candidates present

        # NON-BREAKING control: remove the bonds file → the SAME rebuilt jar emits EVERY candidate.
        bonds_path.unlink()
        stages.stage_reader(scratch, tmpdb, "py", 5433, cfg.results_db_port, fw_final, n_opt=n_opt, cfg=cfg)
        emitted_all = {p.stem for p in (scratch / "src").glob("*") if p.is_file()}
        assert len(emitted_all) == expected_total              # full output restored
        assert expected_forbidden <= emitted_all               # the previously-forbidden ones reappear
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        _drop_db(tmpdb)


def test_exact_impact_counts_the_full_assembled_space():
    """`exact_impact` = the EXACT removed/kept over the WHOLE candidate space the Reader emits
    (|fw_final| × (1 + Σ|fw_optX|)) — mandatory bonds kill whole fw_final rows (× the optional
    multiplier), optional bonds kill assembled (final ∪ opt) candidates, no double-count. Verified
    against an independent enumeration of every assembled candidate on a real Core DB with fw_optX."""
    if shutil.which("java") is None or not stages.CORE_JAR.exists():
        pytest.skip("java / Core jar unavailable")
    try:
        admin = _connect("postgres")
    except Exception as exc:                       # noqa: BLE001
        pytest.skip(f"main Postgres (5433) not reachable: {exc}")

    def sl(sheet, key, vals, opt=False):
        flags = 'flags=["FW_Optional"]\n' if opt else ''
        return f'[[slots]]\nsheet="{sheet}"\nkey="{key}"\nverb="FW_Combi(1)"\nraw=true\n{flags}values={json.dumps(vals)}\n'
    spec_toml = ('title="exact impact"\n[[goals]]\nkey="x"\ndir="max"\n'
                 + sl("HEAD", "head", ["h"]) + sl("A", "a", ["a1", "a2"]) + sl("B", "b", ["b1", "b2"])
                 + sl("O1", "o1", ["o1v1", "o1v2"], True) + sl("O2", "o2", ["o2v1", "o2v2"], True)
                 + sl("O3", "o3", ["o3v1", "o3v2"], True) + sl("TAIL", "tail", ["t"]))
    cfg, _sources = config.resolve_config(cli={})
    tmpdb = "fw_exi_" + uuid.uuid4().hex[:12]
    admin.autocommit = True
    admin.cursor().execute(f'CREATE DATABASE "{tmpdb}";')
    admin.close()
    scratch = Path(tempfile.mkdtemp(prefix="fwexi-"))
    spec_dir = scratch / "spec"; spec_dir.mkdir()
    (spec_dir / "o.toml").write_text(spec_toml, encoding="utf-8")
    try:
        spec = fg.load_spec(spec_dir / "o.toml")
        xlsx = stages.stage_gen(spec_dir, scratch)
        stages.stage_core(spec, xlsx, scratch, tmpdb, 5433, n_opt=3, cfg=cfg)
        conn = _connect(tmpdb)
        code2val, baseline, combos_col, order = sv.build_maps_from_db(conn, "fw_final", spec.slots)
        opt_sheets = {s.sheet for s in spec.slots if "FW_Optional" in s.flags}
        cur = conn.cursor()
        cur.execute("select table_name from information_schema.tables where table_name like 'fw_opt%';")
        opt_tables = sorted(r[0] for r in cur.fetchall()); cur.close()
        sc = {"version": 1, "params": {}, "constraints": [
            {"id": "mand", "polarity": "forbid", "sheets": ["A", "B"], "pairs": [{"A": "a1", "B": "b1"}], "gate": {}},
            {"id": "oo", "polarity": "forbid", "sheets": ["O1", "O3"], "pairs": [{"O1": "o1v1", "O3": "o3v1"}], "gate": {}}]}
        res = sv.exact_impact(conn, "fw_final", sc, code2val, order, combos_col, baseline, opt_sheets, opt_tables)
        cached = sv.decode_assembly(conn, "fw_final", code2val, order, combos_col, baseline, opt_sheets, opt_tables)

        def decode(arrays, want_opt):                                  # the Reader's mandatory/optional split
            place = []
            for pos, (s, arr) in enumerate(zip(order, arrays)):
                is_opt = s in opt_sheets
                if want_opt != is_opt:
                    continue
                if arr:
                    for cd in arr:
                        v = code2val.get(s, {}).get(int(cd))
                        if v is not None:
                            place.append({"sheet": s, "value": v, "pos": pos})
                elif (not is_opt) and (s in baseline):
                    place.append({"sheet": s, "value": baseline[s], "pos": pos})
            return place

        cur = conn.cursor(); cols = ", ".join(f'"{combos_col[s]}"' for s in order)
        cur.execute(f"select {cols} from fw_final;"); finals = [decode(r, False) for r in cur.fetchall()]
        optrows = []
        for t in opt_tables:
            cur.execute(f'select {cols} from "{t}";'); optrows += [decode(r, True) for r in cur.fetchall()]
        cur.close(); conn.close()
        total = removed = 0
        for f in finals:                                               # ground truth: every assembled candidate
            total += 1
            if sv.row_violations(f, sc):
                removed += 1
            for o in optrows:
                total += 1
                if sv.row_violations(f + o, sc):
                    removed += 1
        assert res["exact"] and res["total"] == total
        assert res["removed"] == removed and res["kept"] == total - removed
        assert res["removed"] == 36 and res["kept"] == 72              # closed form: 27 mandatory + 9 optional
        # cached, DB-FREE path (decode once → reuse) matches the one-shot — conn is already closed here
        assert sv.impact_over_rows(cached[0], cached[1], sc, opt_sheets) == res
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        _drop_db(tmpdb)


if __name__ == "__main__":
    import pytest as _pt
    sys.exit(_pt.main([__file__, "-q"]))
