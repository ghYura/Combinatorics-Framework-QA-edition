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
"""Keep only a spec's t-wise covering array in a Core-filled fw_final.

`plan` has always stated the size of the covering array a spec asks for
(`coverage_strength` / `coverage_budget`), but the run executed the full product
anyway. The sieve stage now applies the array: every fw_final row is decoded to
its mandatory-slot values and kept iff that tuple is in
``fwgen.coverage_allowlist(spec)`` -- the same list `plan` counted, so the planned
and the executed suite cannot differ.

Decoding follows fw_final's delta encoding (see constraints/sieve.py): an empty
``combos*`` cell is the slot's baseline value, a non-empty one holds the code of
the value Core chose. Eligible specs are single-pick, so a cell holds at most one
code; anything else is refused rather than guessed.

This module is pure -- the stage feeds it rows and deletes what it returns.
"""
from __future__ import annotations

from typing import Iterable, Mapping, Sequence


def decode_row(cells: "Mapping[str, Sequence[int] | None]", sheets: "Sequence[str]",
               code2val: "Mapping[str, Mapping[int, str]]",
               baseline: "Mapping[str, str]") -> "tuple[str, ...]":
    """One fw_final row as its tuple of mandatory-slot values, in slot order."""
    values = []
    for sheet in sheets:
        codes = cells.get(sheet)
        if codes:
            if len(codes) != 1:
                raise ValueError(f"sheet {sheet!r} holds {len(codes)} codes in one row; "
                                 f"a single-pick slot holds at most one")
            value = code2val.get(sheet, {}).get(int(codes[0]))
            if value is None:
                raise ValueError(f"sheet {sheet!r}: code {codes[0]} has no NumberToValue1 entry")
            values.append(value)
        elif sheet in baseline:
            values.append(baseline[sheet])
        else:
            raise ValueError(f"sheet {sheet!r}: empty cell and no baseline value")
    return tuple(values)


def partition(records: "Iterable[tuple[int, Mapping[str, Sequence[int] | None]]]",
              sheets: "Sequence[str]", code2val: "Mapping[str, Mapping[int, str]]",
              baseline: "Mapping[str, str]",
              allow: "set[tuple[str, ...]]") -> "tuple[list[int], list[int], set[tuple[str, ...]]]":
    """Split row ids into (keep, drop) against `allow`; also return the allowed
    tuples no row carried. A faithful fw_final holds every allowed tuple exactly
    once, so the caller refuses to continue unless ``missing`` is empty and
    ``len(keep) == len(allow)``."""
    keep, drop, seen = [], [], set()
    for row_id, cells in records:
        values = decode_row(cells, sheets, code2val, baseline)
        if values in allow:
            keep.append(row_id)
            seen.add(values)
        else:
            drop.append(row_id)
    return keep, drop, set(allow) - seen
