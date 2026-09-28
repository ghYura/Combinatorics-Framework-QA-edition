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

"""D13a system under test: a local orchestrator running an approve / read / send plan under a policy.

CONTRACT.md v1. State: approved, tainted, sent_once, buffer (initially PUBLIC). Policies:
  guarded             revocation clears approval; taint on read_chunk; deduplicate
  sticky_approval     ignores revocation in its approval flag; otherwise guarded
  success_only_taint  buffers the chunk at once but taints only on read_ok; otherwise guarded
  no_dedup            ignores sent_once when deciding; otherwise guarded
A send decides: no approval -> block(no_approval); tainted -> block(tainted); already sent -> dedup
(duplicate), except no_dedup; otherwise emit(allowed) through the send tool and set sent_once.
Every step appends an event with a snapshot of the state and the outbox size. Nothing here knows
the oracle, the reference responses or the verdict.
"""
import tools

POLICIES = ("guarded", "sticky_approval", "success_only_taint", "no_dedup")
MESSAGE_ID = "notice-1"


class Orchestrator:
    def __init__(self, policy):
        if policy not in POLICIES:
            raise ValueError(f"unknown policy {policy!r}")
        self.policy = policy
        self.state = {"approved": False, "tainted": False, "sent_once": False, "buffer": "PUBLIC"}
        self.trace, self.send_results, self.outbox = [], [], []

    def _event(self, name, **fields):
        self.trace.append({"event": name, **fields, "state": dict(self.state), "outbox_size": len(self.outbox)})

    def approve(self):
        self.state["approved"] = True
        self._event("approve")

    def revoke(self, cut):
        if self.policy != "sticky_approval":
            self.state["approved"] = False
        self._event("revoke", cut=cut)

    def _on_chunk(self, chunk):
        self.state["buffer"] = chunk
        if self.policy != "success_only_taint":
            self.state["tainted"] = True
        self._event("read_chunk", payload=chunk)

    def read(self, fail):
        self._event("read_start")
        try:
            tools.read(self._on_chunk, fail)
        except tools.ControlledReadError:
            self._event("read_error")
            return
        self.state["tainted"] = True
        self._event("read_ok")

    def send(self, request):
        self._event("send_request", request=request, message_id=MESSAGE_ID)
        s = self.state
        if not s["approved"]:
            action, reason = "block", "no_approval"
        elif s["tainted"]:
            action, reason = "block", "tainted"
        elif s["sent_once"] and self.policy != "no_dedup":
            action, reason = "dedup", "duplicate"
        else:
            action, reason = "emit", "allowed"
        payload = s["buffer"] if action == "emit" else None
        if action == "emit":
            tools.send(self.outbox, MESSAGE_ID, payload)
            s["sent_once"] = True
        result = {"request": request, "action": action, "reason": reason, "payload": payload}
        self.send_results.append(result)
        self._event("send_result", **result, message_id=MESSAGE_ID)

    def run(self, order, repetitions, fail_read, revoke_cut):
        if revoke_cut == 0:
            self.revoke(0)
        for k, op in enumerate(order, start=1):
            if op == "A":
                self.approve()
            elif op == "R":
                self.read(fail_read)
            else:
                for request in range(1, repetitions + 1):   # the repeated pair stays together
                    self.send(request)
            if revoke_cut == k:
                self.revoke(k)
