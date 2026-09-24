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
"""Two spec-authoring traps met while writing a real campaign (DBeaver PoC).

1. A raw value written as a TOML single-quoted string keeps ``\\n`` literally, so
   every candidate carried a backslash and an ``n`` -- 3456 of 3456 BROKEN, and
   nothing pointed back at the spec. It is now refused where the spec is read.
2. A raw fragment opening with ``FW_VAR = ...`` was rejected with "data cell ...
   starts with FW_" and no hint of the cause or the way around it.
"""
from __future__ import annotations

import pytest

import fwgen as fg

_TEMPLATE = """
spec_version = "1"
title = "authoring trap"

[[slots]]
sheet = "HEAD"
key = "head"
verb = "FW_Combi(1)"
raw = {raw}
values = [{values}]
"""


def _load(tmp_path, values: str, raw: str = "true"):
    path = tmp_path / "trap.toml"
    path.write_text(_TEMPLATE.format(raw=raw, values=values), encoding="utf-8")
    return fg.load_spec(path)


def test_a_literal_backslash_n_in_a_raw_value_is_refused_at_load(tmp_path) -> None:
    with pytest.raises(ValueError, match="literal backslash-n") as excinfo:
        _load(tmp_path, r"""'x = 1\n', 'y = 2'""")
    assert "slot 'HEAD'" in str(excinfo.value) and "[0]" in str(excinfo.value)


def test_a_real_newline_is_fine(tmp_path) -> None:
    assert _load(tmp_path, '"x = 1\\n", "y = 2"').slots[0].values == ["x = 1\n", "y = 2"]


def test_an_escaped_backslash_before_n_is_not_a_trap(tmp_path) -> None:
    # ends in backslash, backslash, n: an escaped backslash followed by a letter
    spec = _load(tmp_path, r"""'marker = 1  # \\n'""")
    assert spec.slots[0].values[0].endswith("\\\\n")


def test_non_raw_values_are_not_code_and_are_left_alone(tmp_path) -> None:
    _load(tmp_path, r"""'label\n'""", raw="false")


def test_the_fw_prefix_error_names_the_way_around_it(tmp_path) -> None:
    spec = _load(tmp_path, '"FW_VAR = compute()\\n"')
    workbook = tmp_path / "trap.xlsx"
    fg.build_compact(spec).save(workbook)
    errors = [e for e in fg.validate_workbook(workbook) if "starts with FW_" in e]
    assert errors and "reads a cell that starts with FW_ as a verb" in errors[0]
    assert "FW_VAR = _v" in errors[0]
