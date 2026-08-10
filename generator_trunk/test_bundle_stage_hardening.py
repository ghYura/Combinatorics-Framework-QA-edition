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

"""Regression tests for two defects found by an independent review of b5f4657.

Both were latent rather than live — the documented workflow supplies operator
controlled values, and the only password source today is ``secrets.token_hex``,
which can produce neither an embedded newline nor a leading comment marker. They
are pinned here because "not reachable today" is a property of the current
callers, not of these functions, and the next caller does not inherit it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from bundle.database import sql_identifier          # noqa: E402
from bundle.errors import StageError                # noqa: E402
from bundle.stages import _check_prop_value, _props  # noqa: E402


class TestPropertiesValueIsOneValue:
    """``.properties`` is line-oriented: a value must not become a second line."""

    @pytest.mark.parametrize("bad", ["pw\nfw.injected=owned", "pw\r\nfw.x=1", "pw\rx"])
    def test_line_break_is_rejected(self, bad):
        with pytest.raises(StageError) as exc:
            _check_prop_value("main_db_password", bad)
        assert "line break" in str(exc.value)

    @pytest.mark.parametrize("bad", ["#pw", "!pw"])
    def test_leading_comment_marker_is_rejected(self, bad):
        with pytest.raises(StageError) as exc:
            _check_prop_value("main_db_password", bad)
        assert "comment marker" in str(exc.value)

    def test_ordinary_values_pass_through_unchanged(self):
        for good in ["abc123", "p#ssw0rd", "a=b", "value with spaces", ""]:
            assert _check_prop_value("k", good) == good

    def test_props_refuses_to_write_an_injected_file(self, tmp_path):
        template = tmp_path / "fw.properties"
        template.write_text("fw.a=1\n", encoding="utf-8")
        out = tmp_path / "out.properties"

        with pytest.raises(StageError):
            _props(template, {"fw.a": "x\nfw.injected=owned"}, out)

        # Fail closed: a rejected edit must leave no partially written file
        # behind for a later stage to read as though it were valid.
        assert not out.exists()

    def test_props_still_writes_valid_edits(self, tmp_path):
        template = tmp_path / "fw.properties"
        template.write_text("fw.a=1\nfw.b=2\n", encoding="utf-8")
        out = tmp_path / "out.properties"

        _props(template, {"fw.a": "changed", "fw.new": "added"}, out)

        written = out.read_text(encoding="utf-8").splitlines()
        assert "fw.a=changed" in written
        assert "fw.b=2" in written
        assert "fw.new=added" in written


class TestResultsCountQueryEscapesItsIdentifier:
    """The results-count query must quote its table name the way its sibling in
    ``orchestrator._reset_owned_legacy_results`` does."""

    def test_finish_executor_stage_uses_sql_identifier(self):
        source = (HERE / "bundle" / "stages.py").read_text(encoding="utf-8")
        assert "from {sql_identifier(db)};" in source, (
            "the results-count query must route the table name through "
            "sql_identifier(); plain f-string interpolation regressed")
        assert 'from "{db}";' not in source

    def test_sql_identifier_neutralises_an_embedded_quote(self):
        # The divergence the two approaches showed: a name containing a double
        # quote. Escaped, it stays one identifier; interpolated, it terminates
        # the quoted name early.
        assert sql_identifier('a"b') == '"a""b"'
