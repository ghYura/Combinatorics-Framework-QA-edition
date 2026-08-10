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

"""Keep the CLI's documentation from drifting away from the CLI.

Written after an audit found the reference doc's subcommand list seven verbs
behind the implementation -- `architecture`, `coverage`, `capabilities`,
`sut-manifests`, `release` and `provenance` had all shipped undocumented, and
`report` would have been the seventh.

The failure mode this guards is specific and recurring in this project: a
hand-written sentence about a machine-checkable fact. The fix is not to write the
sentence more carefully, it is to make the sentence checked
(run: ``python3 -m pytest test_bundle_cli_docs.py -q``).
"""
import re
from pathlib import Path

import pytest

from bundle import cli

HERE = Path(__file__).resolve().parent
CLI_DOC = HERE.parent / "docs/04_CLI_AND_LIFECYCLE_REFERENCE.md"


def _documented_verbs(text: str) -> set:
    """The verb list from the doc's own '**A subcommand** — ...' bullet."""
    marker = "**A subcommand**"
    start = text.index(marker)
    # the bullet runs to the blank line that ends it
    block = text[start:text.index("\n\n", start)]
    inline = re.findall(r"`([^`]+)`", block)
    verbs = set()
    for chunk in inline:
        for part in chunk.split("|"):
            part = part.strip()
            if re.fullmatch(r"[a-z][a-z-]*", part):
                verbs.add(part)
    return verbs


@pytest.mark.skipif(not CLI_DOC.exists(),
                    reason="EXPECTED_OPTIONAL: docs/04_CLI_AND_LIFECYCLE_REFERENCE.md not present")
def test_documented_verbs_match_the_cli_exactly():
    documented = _documented_verbs(CLI_DOC.read_text(encoding="utf-8"))
    actual = {verb for verb, _blurb in cli._VERBS}

    undocumented = actual - documented
    assert not undocumented, (
        f"these subcommands exist but doc 04 does not list them: {sorted(undocumented)}")

    phantom = documented - actual
    assert not phantom, (
        f"doc 04 lists subcommands the CLI does not expose: {sorted(phantom)}")


@pytest.mark.skipif(not CLI_DOC.exists(), reason="EXPECTED_OPTIONAL: doc 04 not present")
def test_every_verb_the_doc_lists_has_a_section_or_is_grouped():
    """A verb in the list should be findable in the body, not just the header.

    Grouped headings (`inventory` / `hygiene`) count -- the check is that a
    reader who sees a verb in the list can find out what it does.
    """
    text = CLI_DOC.read_text(encoding="utf-8")
    body = text[text.index("## Lifecycle at a glance"):]
    missing = [verb for verb, _ in cli._VERBS if f"`{verb}" not in body]
    assert not missing, f"verbs listed but never described in doc 04: {missing}"


def test_verb_blurbs_are_non_empty_and_distinct():
    """`--help` prints these; an empty or duplicated blurb is a silent regression."""
    blurbs = [blurb for _verb, blurb in cli._VERBS]
    assert all(b and b.strip() for b in blurbs)
    assert len(set(blurbs)) == len(blurbs), "duplicate verb descriptions in _VERBS"
