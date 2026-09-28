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

"""D3 system under test: a tiny billing service with a durable ledger and a balance cache.

CONTRACT.md v1 ("Frozen state machine"). The ledger (epoch, per-epoch captures and refunds)
is durable; the balance is a process cache. A restart builds a new process over the same
ledger. Two policies are deliberate fault variants:
  refund_unchecked  F always records a refund and subtracts 100 (no eligibility/duplicate check)
  restart_cache     S leaves the new process's cache at 0 instead of reloading it
Nothing here knows the reference, the expected traces or the oracle.
"""

POLICIES = ("correct", "refund_unchecked", "restart_cache")


class Ledger:
    """Durable state; survives a restart."""

    def __init__(self):
        self.epoch, self.captures, self.refunds = 0, [0], [0]

    def value(self):
        return 100 * (sum(self.captures) - sum(self.refunds))


class Service:
    def __init__(self, policy, ledger, *, reload_cache=True):
        if policy not in POLICIES:
            raise ValueError(f"unknown policy {policy!r}")
        self.policy, self.ledger = policy, ledger
        self.balance = ledger.value() if reload_cache else 0

    def apply(self, op):
        """Apply one operation; returns the (possibly new) service object."""
        led = self.ledger
        if op == "C":                        # literal rule: charge iff captures[epoch] is zero
            if led.captures[led.epoch] == 0:
                led.captures[led.epoch] = 1
                self.balance += 100
        elif op == "F":
            if self.policy == "refund_unchecked":
                led.refunds[led.epoch] += 1
                self.balance -= 100
            elif led.captures[led.epoch] == 1 and led.refunds[led.epoch] == 0:
                led.refunds[led.epoch] = 1
                self.balance -= 100
        elif op == "N":
            led.epoch += 1
            led.captures.append(0)
            led.refunds.append(0)
        elif op == "S":                      # new process over the same ledger
            return Service(self.policy, led, reload_cache=self.policy != "restart_cache")
        elif op == "Q":
            self.balance = led.value()
        else:
            raise ValueError(f"unknown operation {op!r}")
        return self

    def snapshot(self):
        led = self.ledger
        return {"epoch": led.epoch, "captures": list(led.captures), "refunds": list(led.refunds),
                "balance": self.balance}
