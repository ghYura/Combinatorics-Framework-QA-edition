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

"""D3 phase C system under test: the billing service with a refund-attempt flag and a view.

phase-c/CONTRACT.md. Durable state: epoch, per-epoch captures/refunds and refund_attempted;
the balance is a process cache. V reads without changing anything. Policy late_restart has a
faulty recovery branch in S only: after a renewal and an unsuccessful refund attempt (epoch 1,
captures [1,0], refunds [0,0], refund_attempted) the new process starts with balance 0.
Nothing here knows the reference or the expected results.
"""

POLICIES = ("correct", "late_restart")


class Durable:
    def __init__(self):
        self.epoch, self.captures, self.refunds, self.refund_attempted = 0, [0], [0], False

    def value(self):
        return 100 * (sum(self.captures) - sum(self.refunds))


class Service:
    def __init__(self, policy, durable, balance=None):
        if policy not in POLICIES:
            raise ValueError(f"unknown policy {policy!r}")
        self.policy, self.d = policy, durable
        self.balance = durable.value() if balance is None else balance

    def apply(self, op):
        d = self.d
        if op == "C":
            if d.captures[d.epoch] == 0:
                d.captures[d.epoch] = 1
                self.balance += 100
        elif op == "F":
            d.refund_attempted = True
            if d.captures[d.epoch] == 1 and d.refunds[d.epoch] == 0:
                d.refunds[d.epoch] = 1
                self.balance -= 100
        elif op == "N":
            d.epoch += 1
            d.captures.append(0)
            d.refunds.append(0)
            d.refund_attempted = False
        elif op == "S":
            faulty = (self.policy == "late_restart" and d.epoch == 1 and d.captures == [1, 0]
                      and d.refunds == [0, 0] and d.refund_attempted)
            return Service(self.policy, d, 0 if faulty else None)
        elif op == "Q":
            self.balance = d.value()
        elif op != "V":
            raise ValueError(f"unknown operation {op!r}")
        return self

    def snapshot(self):
        d = self.d
        return {"epoch": d.epoch, "captures": list(d.captures), "refunds": list(d.refunds),
                "balance": self.balance, "refund_attempted": d.refund_attempted}
