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

"""D13a inert tool stubs: a local read that streams one chunk and a local send that appends to a list.

Nothing here touches the network, a model, a real message or any persistent state. CANARY is a fixture
string, not a secret. read() delivers its chunk through the callback BEFORE it raises its controlled
error, so a caller can observe partial output from a failing tool.
"""

CANARY = "D13A_LOCAL_CANARY"


class ControlledReadError(Exception):
    """The expected, controlled failure of the read stub (raised after the chunk is delivered)."""


def read(on_chunk, fail):
    on_chunk(CANARY)
    if fail:
        raise ControlledReadError("read stub: controlled failure after delivering its chunk")


def send(outbox, message_id, payload):
    outbox.append({"message_id": message_id, "payload": payload})
