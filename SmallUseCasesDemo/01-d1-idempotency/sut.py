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

"""D1 service under test: one request handler, five deduplication policies.

Implements CONTRACT.md v1 §2. `DurableState` is the backing storage a
process restart keeps: the effect ledger (durable for every policy) and the
durable receipt cache. `Service` is the process-facing object. A restart
discards it, and with it any volatile cache, then builds a new one over the
same `DurableState`. This module knows nothing about expected verdicts, the
oracle or the case being run.
"""

POLICIES = ("volatile_transport", "durable_transport", "durable_order",
            "durable_payload", "durable_operation")


def canonical_payload(payload):
    """The complete payload value as a hashable key: every field, no digest."""
    return tuple(sorted(payload.items()))


# Cache key per policy, computed from the request only.
_KEYS = {
    "volatile_transport": lambda r: ("transport", r["transport_id"]),
    "durable_transport": lambda r: ("transport", r["transport_id"]),
    "durable_order": lambda r: ("order", r["order_id"]),
    "durable_payload": lambda r: ("payload", canonical_payload(r["payload"])),
    "durable_operation": lambda r: ("operation", r["order_id"], r["operation_id"]),
}
_VOLATILE = frozenset({"volatile_transport"})


class DurableState:
    """Storage that survives a restart. A fresh case starts with a new one."""

    def __init__(self):
        self.ledger = []   # effects in append order; receipt_id == 1-based position
        self.cache = {}    # durable receipt cache: key -> stored receipt entry


class Service:
    """One process lifetime of the order service under a selected policy."""

    def __init__(self, policy, durable):
        if policy not in _KEYS:
            raise ValueError(f"unknown policy {policy!r}")
        self.policy = policy
        self.durable = durable
        # A volatile cache belongs to this process object; a durable one to the backing state.
        self._cache = {} if policy in _VOLATILE else durable.cache

    def handle(self, request):
        """Apply, replay or reject one request (atomic in this model)."""
        key = _KEYS[self.policy](request)
        payload = dict(request["payload"])
        entry = self._cache.get(key)
        if entry is None:
            receipt_id = len(self.durable.ledger) + 1
            self.durable.ledger.append({"receipt_id": receipt_id,
                                        "order_id": request["order_id"],
                                        "operation_id": request["operation_id"],
                                        "payload": payload})
            self._cache[key] = {"receipt_id": receipt_id,
                                "order_id": request["order_id"],
                                "operation_id": request["operation_id"],
                                "payload": dict(payload)}
            return {"status": "APPLIED", "receipt_id": receipt_id,
                    "order_id": request["order_id"], "operation_id": request["operation_id"]}
        if entry["payload"] != payload:
            # The stored entry and the ledger stay untouched.
            return {"status": "CONFLICT", "receipt_id": None,
                    "order_id": request["order_id"], "operation_id": request["operation_id"]}
        # Replay the stored receipt with its stored identity; it is not repaired.
        return {"status": "REPLAY", "receipt_id": entry["receipt_id"],
                "order_id": entry["order_id"], "operation_id": entry["operation_id"]}

    def ledger_view(self):
        """A deep copy of the durable ledger, safe to hand to an observer."""
        return [dict(e, payload=dict(e["payload"])) for e in self.durable.ledger]
