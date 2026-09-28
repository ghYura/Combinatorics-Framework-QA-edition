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

"""D2 systems under test: three ways to decode a byte stream delivered in chunks.

CONTRACT.md v1. A UnicodeError propagates to the caller (the runtime records it as
a rejection); nothing here knows the expected text or the oracle.
"""
import codecs

ADAPTERS = ("incremental", "per_chunk", "no_final")


def incremental(chunks, encoding, errors):
    """One decoder per stream: every chunk with final=False, then an empty final flush."""
    dec = codecs.getincrementaldecoder(encoding)(errors=errors)
    text = "".join(dec.decode(c, final=False) for c in chunks)
    return text + dec.decode(b"", final=True)


def per_chunk(chunks, encoding, errors):
    """Each chunk decoded on its own with bytes.decode (boundaries are not carried over)."""
    return "".join(c.decode(encoding, errors) for c in chunks)


def no_final(chunks, encoding, errors):
    """One decoder per stream, final=False for every chunk, and no final flush."""
    dec = codecs.getincrementaldecoder(encoding)(errors=errors)
    return "".join(dec.decode(c, final=False) for c in chunks)


def decode(adapter, chunks, encoding, errors):
    if adapter not in ADAPTERS:
        raise ValueError(f"unknown adapter {adapter!r}")
    return {"incremental": incremental, "per_chunk": per_chunk, "no_final": no_final}[adapter](
        chunks, encoding, errors)
