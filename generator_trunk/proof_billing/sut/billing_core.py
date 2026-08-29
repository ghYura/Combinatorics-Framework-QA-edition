#!/usr/bin/env python3
"""
billing_core - subscription billing engine.

Written to spec, from experience, as a normal production component:
plans, proration on plan change, pause/resume, cancel/reactivate, trials,
coupons, renewals driven by a clock, refunds and chargebacks.

Money is integer minor units (cents). Everything is single-threaded and
deterministic: the clock only moves when tick() is called.

Public API (the operations a caller performs):
    subscribe(plan)         change_plan(plan)     pause()      resume()
    cancel()                reactivate()          tick(days)   apply_coupon(code)
    refund(invoice_id)      chargeback(invoice_id)
    replay(event_id)        # webhook redelivery (at-least-once upstream)

Invariants the engine promises (checked by audit(), not by the engine itself):
    I1  cash_collected == sum(charges) - sum(refunds) - sum(chargebacks)
    I2  credit_balance >= 0                       (we never owe the customer twice)
    I3  no charge is raised while paused/cancelled
    I4  refunds against an invoice never exceed what that invoice charged
    I5  a coupon is consumed at most max_uses times
    I6  every invoice total equals the sum of its line items
    I7  a subscription inside its trial is never charged
"""

# --------------------------------------------------------------------------
# catalogue
# --------------------------------------------------------------------------

PLANS = {
    "free":  {"price": 0,     "rank": 0},
    "basic": {"price": 1000,  "rank": 1},   # $10.00 / cycle
    "pro":   {"price": 3000,  "rank": 2},   # $30.00 / cycle
    "team":  {"price": 12000, "rank": 3},   # $120.00 / cycle
}

COUPONS = {
    "none":     {"pct": 0,  "max_uses": 0},
    "welcome":  {"pct": 20, "max_uses": 1},   # 20% off, first cycle only
    "loyal10":  {"pct": 10, "max_uses": 3},   # 10% off, three cycles
    "half":     {"pct": 50, "max_uses": 1},
}

DAY = 1


class BillingError(Exception):
    pass


# --------------------------------------------------------------------------
# rounding helpers
# --------------------------------------------------------------------------

def _round(amount, mode):
    """Round a computed amount to whole cents. amount arrives as a float when
    a percentage was applied."""
    if mode == "floor":
        return int(amount)
    if mode == "half_up":
        return int(amount + 0.5)
    if mode == "bankers":
        # round-half-to-even, the accounting default in several jurisdictions
        f = int(amount)
        rem = amount - f
        if rem > 0.5:
            return f + 1
        if rem < 0.5:
            return f
        return f if f % 2 == 0 else f + 1
    return int(amount)


# --------------------------------------------------------------------------
# the engine
# --------------------------------------------------------------------------

class BillingAccount(object):

    def __init__(self,
                 plan="basic",
                 cycle_days=30,
                 proration="credit",     # "credit" | "immediate" | "none"
                 rounding="half_up",     # "half_up" | "floor" | "bankers"
                 trial_days=0,
                 dunning=False):         # retry a failed charge next tick
        if plan not in PLANS:
            raise BillingError("unknown plan %s" % plan)

        self.plan = plan
        self.cycle_days = cycle_days
        self.proration = proration
        self.rounding = rounding
        self.trial_days = trial_days
        self.dunning = dunning

        self.now = 0
        self.state = "active"           # active | paused | cancelled
        self.cycle_start = 0
        self.trial_ends = trial_days
        self.paused_at = None

        self.coupon = None              # code currently attached
        self.coupon_uses = 0            # cycles the coupon has discounted

        self.credit_balance = 0         # unapplied credit owed to the customer
        self.cash_collected = 0         # what we actually took

        self.invoices = []              # list of dicts
        self.ledger = []                # audit trail of money events
        self._events = {}               # event_id -> already-processed marker
        self._next_invoice = 1
        self._next_event = 1

        self._charge_invoice(self.cycle_start, reason="signup")

    # ---------------------------------------------------------------- money

    def _event_id(self, kind):
        eid = "%s-%d" % (kind, self._next_event)
        self._next_event += 1
        return eid

    def _price_of(self, plan):
        return PLANS[plan]["price"]

    def _discount_lines(self, base):
        """Build the line items for one cycle at `base` cents, applying the
        coupon if it still has uses left."""
        lines = [{"desc": "plan", "amount": base}]
        if self.coupon:
            c = COUPONS[self.coupon]
            if self.coupon_uses < c["max_uses"]:
                disc = _round(base * c["pct"] / 100.0, self.rounding)
                lines.append({"desc": "coupon:%s" % self.coupon, "amount": -disc})
                self.coupon_uses += 1
        return lines

    def _charge_invoice(self, at, reason, extra_lines=None):
        """Raise and settle an invoice for the current plan."""
        if self.state != "active":
            return None
        if at < self.trial_ends:
            # inside the trial: nothing is owed
            return None

        base = self._price_of(self.plan)
        lines = self._discount_lines(base)
        if extra_lines:
            lines.extend(extra_lines)

        total = sum(l["amount"] for l in lines)

        # any outstanding credit is burned down before we take cash
        if self.credit_balance > 0 and total > 0:
            applied = min(self.credit_balance, total)
            lines.append({"desc": "credit", "amount": -applied})
            self.credit_balance -= applied
            total -= applied

        if total < 0:
            # a discount larger than the plan price becomes credit, not a payout
            self.credit_balance += -total
            total = 0

        inv = {
            "id": self._next_invoice,
            "at": at,
            "reason": reason,
            "plan": self.plan,
            "lines": lines,
            "total": total,
            "refunded": 0,
            "settled": False,
            "raised_while": self.state,
        }
        self._next_invoice += 1
        self.invoices.append(inv)

        eid = self._event_id("charge")
        self._events[eid] = {"kind": "charge", "invoice": inv["id"]}
        inv["event"] = eid

        self.cash_collected += total
        inv["settled"] = True
        self.ledger.append({"kind": "charge", "amount": total,
                            "at": at, "invoice": inv["id"], "event": eid})
        return inv

    # ------------------------------------------------------------ lifecycle

    def subscribe(self, plan):
        if plan not in PLANS:
            raise BillingError("unknown plan %s" % plan)
        if self.state == "cancelled":
            raise BillingError("cannot subscribe on a cancelled account")
        self.plan = plan
        self.cycle_start = self.now
        self._charge_invoice(self.now, reason="subscribe")

    def change_plan(self, plan):
        """Upgrade or downgrade. Proration policy decides what happens to the
        unused remainder of the current cycle."""
        if plan not in PLANS:
            raise BillingError("unknown plan %s" % plan)
        if self.state != "active":
            raise BillingError("cannot change plan while %s" % self.state)

        old = self.plan
        elapsed = self.now - self.cycle_start
        remaining = self.cycle_days - elapsed
        if remaining < 0:
            remaining = 0

        self.plan = plan

        if self.proration == "none":
            return

        frac = float(remaining) / float(self.cycle_days)
        unused = _round(self._price_of(self.plan) * frac, self.rounding)
        newpart = _round(self._price_of(plan) * frac, self.rounding)

        if self.proration == "credit":
            # give back the unused part of what they paid; charge nothing now,
            # the difference lands on the next renewal
            if unused > 0:
                self.credit_balance += unused
                self.ledger.append({"kind": "credit", "amount": unused,
                                    "at": self.now, "invoice": None,
                                    "event": self._event_id("credit")})
        elif self.proration == "immediate":
            delta = newpart - unused
            if delta > 0:
                self._charge_invoice(self.now, reason="proration",
                                     extra_lines=[{"desc": "prorated %s->%s" % (old, plan),
                                                   "amount": delta - self._price_of(plan)}])
            elif delta < 0:
                self.credit_balance += -delta
                self.ledger.append({"kind": "credit", "amount": -delta,
                                    "at": self.now, "invoice": None,
                                    "event": self._event_id("credit")})

    def pause(self):
        if self.state != "active":
            raise BillingError("cannot pause while %s" % self.state)
        self.state = "paused"
        self.paused_at = self.now

    def resume(self):
        if self.state != "paused":
            raise BillingError("cannot resume while %s" % self.state)
        self.state = "active"
        # push the cycle boundary out by however long we were paused, so the
        # customer does not lose the days they paid for
        held = self.now - self.paused_at
        self.cycle_start += held
        self.paused_at = None

    def cancel(self):
        if self.state == "cancelled":
            raise BillingError("already cancelled")
        self.state = "cancelled"

    def reactivate(self):
        if self.state != "cancelled":
            raise BillingError("not cancelled")
        self.state = "active"
        self.cycle_start = self.now
        self._charge_invoice(self.now, reason="reactivate")

    # ---------------------------------------------------------------- clock

    def tick(self, days=1):
        """Advance the clock. Renewals fire when a cycle boundary is crossed."""
        for _ in range(days):
            self.now += DAY
            if self.state != "active":
                continue
            if self.now - self.cycle_start >= self.cycle_days:
                self.cycle_start += self.cycle_days
                self._charge_invoice(self.now, reason="renewal")

    # --------------------------------------------------------------- coupon

    def apply_coupon(self, code):
        if code not in COUPONS:
            raise BillingError("unknown coupon %s" % code)
        if code == "none":
            return
        self.coupon = code
        self.coupon_uses = 0

    # ------------------------------------------------------- money reversal

    def _find_invoice(self, invoice_id):
        for inv in self.invoices:
            if inv["id"] == invoice_id:
                return inv
        raise BillingError("no such invoice %s" % invoice_id)

    def refund(self, invoice_id=None):
        """Refund an invoice. With no id, the most recent settled invoice."""
        if invoice_id is None:
            settled = [i for i in self.invoices if i["settled"]]
            if not settled:
                raise BillingError("nothing to refund")
            inv = settled[-1]
        else:
            inv = self._find_invoice(invoice_id)

        # refund what this subscription is worth today
        amount = self._price_of(self.plan)
        if amount > inv["total"]:
            amount = inv["total"]

        inv["refunded"] += amount
        self.cash_collected -= amount
        self.ledger.append({"kind": "refund", "amount": amount,
                            "at": self.now, "invoice": inv["id"],
                            "event": self._event_id("refund")})
        return amount

    def chargeback(self, invoice_id=None):
        """The bank pulled the money back. Always for the full invoice."""
        if invoice_id is None:
            settled = [i for i in self.invoices if i["settled"]]
            if not settled:
                raise BillingError("nothing to charge back")
            inv = settled[-1]
        else:
            inv = self._find_invoice(invoice_id)

        amount = inv["total"]
        inv["refunded"] += amount
        self.cash_collected -= amount
        self.ledger.append({"kind": "chargeback", "amount": amount,
                            "at": self.now, "invoice": inv["id"],
                            "event": self._event_id("chargeback")})
        return amount

    def replay(self, event_id=None):
        """Upstream redelivered a webhook. We are at-least-once, so we must be
        idempotent: an event we have already processed is a no-op."""
        if event_id is None:
            if not self.ledger:
                return
            event_id = self.ledger[-1]["event"]
        if event_id in self._events:
            return                      # already processed, ignore
        kind = event_id.split("-")[0]
        if kind == "charge":
            self._charge_invoice(self.now, reason="replay")
        elif kind == "refund":
            self.refund()
        elif kind == "chargeback":
            self.chargeback()

    # ---------------------------------------------------------------- audit

    def audit(self):
        """Return the list of invariant ids that are VIOLATED. Empty == healthy.
        This is the external checker; the engine never consults it."""
        bad = []

        charges = sum(e["amount"] for e in self.ledger if e["kind"] == "charge")
        refunds = sum(e["amount"] for e in self.ledger if e["kind"] == "refund")
        cbacks = sum(e["amount"] for e in self.ledger if e["kind"] == "chargeback")
        credits = sum(e["amount"] for e in self.ledger if e["kind"] == "credit")

        # I1  cash actually held == what we charged minus what we gave back
        if self.cash_collected != charges - refunds - cbacks:
            bad.append("I1")

        # I2  we never owe a negative credit
        if self.credit_balance < 0:
            bad.append("I2")

        # I3  no invoice was raised while not active
        for inv in self.invoices:
            if inv.get("raised_while") != "active":
                bad.append("I3")
                break

        # I4  refunds against an invoice never exceed what it charged
        for inv in self.invoices:
            if inv["refunded"] > inv["total"]:
                bad.append("I4")
                break

        # I5  a coupon discounts at most max_uses invoices, for the whole
        #     lifetime of the account (re-applying it is not a new allowance)
        used = {}
        for inv in self.invoices:
            for l in inv["lines"]:
                if l["desc"].startswith("coupon:"):
                    code = l["desc"].split(":", 1)[1]
                    used[code] = used.get(code, 0) + 1
        for code, n in used.items():
            if n > COUPONS[code]["max_uses"]:
                bad.append("I5")
                break

        # I6  an invoice total equals the sum of its line items
        for inv in self.invoices:
            if inv["total"] != sum(l["amount"] for l in inv["lines"]):
                bad.append("I6")
                break

        # I7  nothing is billed inside the trial
        for inv in self.invoices:
            if inv["at"] < self.trial_ends and inv["total"] > 0:
                bad.append("I7")
                break

        # I8  we can never hand back more than we ever took
        if credits + refunds + cbacks > charges:
            bad.append("I8")

        # I9  the billing period we are in has actually started
        if self.cycle_start > self.now:
            bad.append("I9")

        return bad
