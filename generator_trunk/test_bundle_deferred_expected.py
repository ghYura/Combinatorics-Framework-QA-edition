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

"""Deferred optional bonds and the Reader's expected candidate count (exact, not loosened).

When the sieve defers a bond that touches an FW_Optional sheet, the Reader enforces it per
assembled candidate and emits fewer than post-sieve fw_final x the optional multiplier. The run
used to keep the unfiltered product as the Reader's expected count, so the critical
reader.emitted_eq_expected invariant failed for any bond that actually removed an assembly. The
run now counts the kept assemblies exactly with the sieve's own engine and expects that number.

Run: `python3 -m pytest test_bundle_deferred_expected.py -q` (no DB / no Bundle run).
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import fwgen as fg                                            # noqa: E402
from bundle import orchestrator as orch                       # noqa: E402
from bundle import stages                                     # noqa: E402
from bundle.errors import StageError                          # noqa: E402

SPEC = fg.parse_spec({
    "slots": [{"sheet": "ENV", "key": "env", "raw": True, "values": ['env("dev");', 'env("prod");']},
              {"sheet": "W", "key": "w", "raw": True, "values": ["w(1);", "w(2);"]},
              {"sheet": "DEBUG", "key": "debug", "raw": True, "flags": ["FW_Optional"], "values": ["debug();"]}],
    "constraints": [{"id": "R6", "polarity": "forbid", "sheets": ["ENV", "DEBUG"],
                     "pairs": [{"ENV": 'env("prod");', "DEBUG": "debug();"}]}]}, "deferred")


def _contract(active=True, sizes=(1,)):
    return SimpleNamespace(active=active, consumed_sizes=sizes)


def test_expected_count_uses_the_exact_kept_assemblies():
    table = SimpleNamespace(deferred_assembly_expected=lambda *a: {"total": 8, "removed": 2, "kept": 6})
    assert orch._expected_after_deferred_bonds(table, SPEC, "w", "db", 5433, None, _contract(), 4, 2) == (6, {"total": 8, "removed": 2, "kept": 6})


def test_without_deferred_bonds_the_product_is_kept():
    for table in (SimpleNamespace(deferred_assembly_expected=lambda *a: None), SimpleNamespace()):
        assert orch._expected_after_deferred_bonds(table, SPEC, "w", "db", 5433, None, _contract(), 4, 2) == (8, None)
    busy = SimpleNamespace(deferred_assembly_expected=lambda *a: pytest.fail("must not be called"))
    assert orch._expected_after_deferred_bonds(busy, SPEC, "w", "db", 5433, None, _contract(active=False), 4, 1) == (4, None)


def test_an_inconsistent_assembled_space_is_refused():
    table = SimpleNamespace(deferred_assembly_expected=lambda *a: {"total": 7, "removed": 1, "kept": 6})
    with pytest.raises(StageError, match="assembled space 7"):
        orch._expected_after_deferred_bonds(table, SPEC, "w", "db", 5433, None, _contract(), 4, 2)


def test_stage_counts_the_filtered_assemblies_with_the_sieve_engine(tmp_path, monkeypatch):
    assert stages.deferred_assembly_expected(SPEC, tmp_path, "db", 5433) is None      # no compiled bonds file
    (tmp_path / "optional_bonds.txt").write_text("compiled\n")
    import pg8000.dbapi
    monkeypatch.setattr(pg8000.dbapi, "connect", lambda **kw: SimpleNamespace(close=lambda: None))
    sys.path.insert(0, str(HERE / "constraints"))
    import sieve as sv
    finals = [[{"sheet": "ENV", "value": v, "pos": 0}, {"sheet": "W", "value": w, "pos": 1}]
              for v in ('env("dev");', 'env("prod");') for w in ("w(1);", "w(2);")]
    opts = [[{"sheet": "DEBUG", "value": "debug();", "pos": 2}]]
    monkeypatch.setattr(sv, "build_maps_from_db", lambda conn, table, slots: ({}, {}, {}, ["ENV", "W", "DEBUG"]))
    seen = {}
    def decode(conn, table, code2val, order, cols, baseline, optional_sheets, opt_tables):
        seen["opt_tables"] = opt_tables
        return finals, opts
    monkeypatch.setattr(sv, "decode_assembly", decode)
    got = stages.deferred_assembly_expected(SPEC, tmp_path, "db", 5433, consumed_sizes=(1,))
    assert got == {"total": 8, "removed": 2, "kept": 6}             # 4 rows x {absent, DEBUG}; prod+DEBUG x2 filtered
    assert seen["opt_tables"] == ["fw_opt1"]                         # only the consumed optional sizes


def test_the_default_stage_table_wires_it():
    assert orch.default_stage_table().deferred_assembly_expected is stages.deferred_assembly_expected
