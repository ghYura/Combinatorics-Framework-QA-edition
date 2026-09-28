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

"""D13c system under test: a local reservation coordinator for one resource R with capacity one.

CONTRACT.md v1. Messages arrive atomically, one at a time:
  inspect  -> {available: no current allocation, version}
  commit   -> echoes the agent's own offer (offer_version, offer_available); BUSY if that offer was
              unavailable, otherwise per policy:
    compare_version  grant only if nothing is allocated and the version is unchanged, else STALE
    trust_offer      grant on the cached availability alone; keep existing allocations
    overwrite_owner  grant on the cached availability alone; replace all existing allocations
A grant returns GRANTED with ticket R:<agent>, records agent -> ticket in issued_grants (an audit
ledger of outstanding promises; there is no revocation) and increments the version. Refusals
change nothing. A malformed message raises: it is a harness error, never a coordinator decision.
Nothing here knows the reference, the oracle or the verdict.
"""
POLICIES = ("compare_version", "trust_offer", "overwrite_owner")
AGENTS = ("A", "B")
RESOURCE = "R"


class Coordinator:
    def __init__(self, policy):
        if policy not in POLICIES:
            raise ValueError(f"unknown policy {policy!r}")
        self.policy = policy
        self.version = 0
        self.allocations = {}
        self.issued_grants = {}

    def deliver(self, request):
        agent, kind = request.get("agent"), request.get("kind")
        if agent not in AGENTS or request.get("resource") != RESOURCE or request.get("id") != f"{agent}:{kind}":
            raise ValueError(f"malformed message {request!r}")
        if kind == "inspect":
            if set(request) != {"id", "agent", "kind", "resource"}:
                raise ValueError(f"malformed inspect {request!r}")
            return {"available": not self.allocations, "version": self.version}
        if kind != "commit" or set(request) != {"id", "agent", "kind", "resource", "offer_version", "offer_available"} \
                or type(request["offer_version"]) is not int or type(request["offer_available"]) is not bool:
            raise ValueError(f"malformed commit {request!r}")
        if not request["offer_available"]:
            return {"status": "BUSY", "ticket": None}
        if self.policy == "compare_version" and (self.allocations or self.version != request["offer_version"]):
            return {"status": "STALE", "ticket": None}
        ticket = f"{RESOURCE}:{agent}"
        if self.policy == "overwrite_owner":
            self.allocations.clear()
        self.allocations[agent] = ticket
        self.issued_grants[agent] = ticket
        self.version += 1
        return {"status": "GRANTED", "ticket": ticket}

    def snapshot(self):
        return {"version": self.version, "allocations": dict(self.allocations), "issued_grants": dict(self.issued_grants)}
