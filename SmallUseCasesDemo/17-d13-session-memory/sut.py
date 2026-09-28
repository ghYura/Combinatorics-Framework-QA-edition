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

"""D13d system under test: a deterministic agent-memory adapter with one storage map.

CONTRACT.md v1. The harness supplies each request's user, session and logical epoch.
  write(user, session, epoch, index, value)  replace the entry under this policy's key
  read(user, session)                          the entry's value under this policy's key, or None
  reset()                                      a required memory clear before a request
Policies:
  scoped         key (user, session); reset clears all entries
  user_only      key (user,);         reset clears all entries
  session_only   key (session,);      reset clears all entries
  ignores_reset  key (user, session); reset keeps every entry
Stored entries keep write_user, write_session, write_epoch and write_index as diagnostic provenance
only: a read just looks up its declared key. Nothing here knows the reference, oracle or verdict.
"""
POLICIES = ("scoped", "user_only", "session_only", "ignores_reset")


class MemoryAdapter:
    def __init__(self, policy):
        if policy not in POLICIES:
            raise ValueError(f"unknown policy {policy!r}")
        self.policy = policy
        self.entries = {}

    def key(self, user, session):
        if self.policy == "user_only":
            return (user,)
        if self.policy == "session_only":
            return (session,)
        return (user, session)

    def reset(self):
        if self.policy != "ignores_reset":
            self.entries.clear()

    def write(self, user, session, epoch, index, value):
        self.entries[self.key(user, session)] = {"value": value, "write_user": user, "write_session": session,
                                                 "write_epoch": epoch, "write_index": index}

    def read(self, user, session):
        entry = self.entries.get(self.key(user, session))
        return None if entry is None else entry["value"]

    def snapshot(self):
        return [{"key": list(k), **v} for k, v in sorted(self.entries.items())]
