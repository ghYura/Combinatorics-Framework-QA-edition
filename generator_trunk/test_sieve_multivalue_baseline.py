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

"""A multi-value slot's baseline combination must be decoded with ALL its values by the sieve.

fw_final stores each sheet as "deviation from the base row": an empty cell inherits the base row.
For a multi-value slot (FW_Combi(2): two codes per row) the base row holds two codes, but
build_maps_from_db kept only the first, so bonds on the baseline pair's second value never fired
(found live in D4: R2/R4 over FEATURES matched 24 rows instead of 48 and 18 illegal candidates ran).
These tests drive build_maps_from_db + sieve_fw_final + decode_assembly on a fake connection.

Run: `python3 -m pytest test_sieve_multivalue_baseline.py -q` (no DB).
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "constraints"))

import sieve as sv                                            # noqa: E402

# codes: 1 mode(batch) 2 mode(live) 3 feature(audit) 4 feature(cache) 5 feature(gzip)
VALUES = {1: 'mode("batch");', 2: 'mode("live");', 3: 'feature("audit");', 4: 'feature("cache");', 5: 'feature("gzip");'}
BASE = {"combos1_MODE": [1], "combos2_FEATURES": [3, 4]}          # base row: batch + {audit, cache}
# fw_final rows: (id, MODE cell, FEATURES cell); an empty cell = the base row's value(s)
ROWS = [(1, None, None), (2, [2], None), (3, None, [4, 5]), (4, [2], [4, 5]), (5, None, [3, 5]), (6, [2], [3, 5])]
SLOTS = [SimpleNamespace(sheet="MODE", values=[VALUES[1], VALUES[2]], flags=()),
         SimpleNamespace(sheet="FEATURES", values=[VALUES[3], VALUES[4], VALUES[5]], flags=())]


class FakeConn:
    def __init__(self):
        self.deleted = []

    def cursor(self):
        return self

    def execute(self, sql, args=()):
        self.sql = sql
        if "information_schema.columns" in sql:
            self.rows = [("combos1_MODE",), ("combos2_FEATURES",)]
        elif '"NumberToValue1"' in sql:
            self.rows = list(VALUES.items())
        elif "information_schema.tables" in sql:
            self.rows = [(1,)] if args and args[0] == "fw_final_base" else []
        elif '"fw_final_base"' in sql:
            self.rows = [(BASE["combos1_MODE"], BASE["combos2_FEATURES"])]
        elif sql.startswith("DELETE"):
            self.deleted = list(args[0]); self.rows = []
        elif 'FROM "fw_final"' in sql:
            self.rows = [r for r in ROWS] if sql.startswith("SELECT combi_id") else [r[1:] for r in ROWS]
        else:
            self.rows = []

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def commit(self):
        pass

    def close(self):
        pass


LIVE_CACHE = {"version": 1, "params": {}, "constraints": [
    {"id": "R2", "polarity": "forbid", "sets": {"MODE": [VALUES[2]], "FEATURES": [VALUES[4]]}}]}


def test_the_base_combination_keeps_all_its_values():
    code2val, baseline, combos_col, order = sv.build_maps_from_db(FakeConn(), "fw_final", SLOTS)
    assert baseline == {"MODE": VALUES[1], "FEATURES": (VALUES[3], VALUES[4])}
    assert sv.baseline_values(baseline, "MODE") == [VALUES[1]]


def test_a_bond_on_the_base_pairs_second_value_fires():
    conn = FakeConn()
    code2val, baseline, combos_col, order = sv.build_maps_from_db(conn, "fw_final", SLOTS)
    rep = sv.sieve_fw_final(conn, "fw_final", LIVE_CACHE, code2val, order, combos_col, id_col="combi_id",
                            baseline=baseline, dry_run=True)
    # live + cache: row 2 (live, base {audit,cache}) and row 4 (live, {cache,gzip}); row 6 has no cache
    assert rep["matched"] == {"R2": 2} and rep["retained"] == 4


def test_decode_assembly_inherits_every_base_value():
    conn = FakeConn()
    code2val, baseline, combos_col, order = sv.build_maps_from_db(conn, "fw_final", SLOTS)
    finals, _ = sv.decode_assembly(conn, "fw_final", code2val, order, combos_col, baseline, set(), [])
    assert sorted(p["value"] for p in finals[0] if p["sheet"] == "FEATURES") == [VALUES[3], VALUES[4]]


def test_twise_refuses_a_multi_value_baseline():
    from bundle import twise
    with pytest.raises(ValueError, match="multi-value baseline"):
        twise.decode_row({"FEATURES": None}, ["FEATURES"], {}, {"FEATURES": (VALUES[3], VALUES[4])})
