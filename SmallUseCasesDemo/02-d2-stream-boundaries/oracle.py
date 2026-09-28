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

"""D2 oracle: the whole-stream reference and the adapter-blind comparison.

CONTRACT.md v1. The reference decodes the unsegmented payload once and must equal the
frozen literal expectation (a truncated payload rejects under strict and gives the
listed replacement text under replace) before it is used. An outcome is either
("accept", text) or ("reject", error class); only completed text or rejection is
compared. The adapter name is never read.
"""
import codecs


def outcome(fn):
    """Run fn(); a UnicodeError is a rejection, any other exception propagates."""
    try:
        return {"accepted": True, "text": fn(), "error": None}
    except UnicodeError as exc:
        return {"accepted": False, "text": None, "error": type(exc).__name__}


def reference(payload, errors):
    """Whole-stream decode, checked against the frozen literal before use."""
    data = bytes.fromhex(payload["hex"])
    ref = outcome(lambda: codecs.decode(data, payload["encoding"], errors))
    literal_rejects = payload["truncated"] and errors == "strict"
    literal_ok = (not ref["accepted"]) if literal_rejects else (
        ref["accepted"] and ref["text"] == payload["literal_text"])
    if not literal_ok:
        raise RuntimeError(f"whole-stream decode of {payload['hex']} ({errors}) disagrees with the frozen literal")
    return ref


def classify(ref, observed):
    """none | unexpected_rejection | unexpected_acceptance | wrong_text."""
    if not ref["accepted"]:
        return "none" if not observed["accepted"] else "unexpected_acceptance"
    if not observed["accepted"]:
        return "unexpected_rejection"
    return "none" if observed["text"] == ref["text"] else "wrong_text"
