#!/usr/bin/env python3
"""Minimal reproducers for every finding, each reduced by hand from the
combinatorial witness, plus the code line that causes it."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "sut"))
import billing_core as B

def show(title, fn, cause):
    print("=" * 78)
    print(title)
    print("-" * 78)
    fn()
    print("  cause: %s" % cause)
    print()

def f1_coupon_reset():
    a = B.BillingAccount(plan="basic", cycle_days=30)
    a.apply_coupon("half")        # max_uses = 1
    a.tick(30)                    # renewal -> 1st discount
    a.apply_coupon("half")        # SAME coupon applied again
    a.tick(30)                    # renewal -> 2nd discount
    lines = [l["desc"] for i in a.invoices for l in i["lines"] if l["desc"].startswith("coupon:")]
    print("  coupon 'half' max_uses=1, discounts actually granted: %d %s" % (len(lines), lines))
    print("  audit: %s" % a.audit())

def f2_refund_twice():
    a = B.BillingAccount(plan="pro", cycle_days=30)     # one $30.00 invoice
    inv = a.invoices[0]
    a.refund(inv["id"])
    a.refund(inv["id"])
    print("  invoice total=%d refunded=%d  cash_collected=%d" % (inv["total"], inv["refunded"], a.cash_collected))
    print("  audit: %s" % a.audit())

def f3_refund_replay():
    a = B.BillingAccount(plan="pro", cycle_days=30)
    inv = a.invoices[0]
    a.refund(inv["id"])
    a.replay()                    # webhook redelivery of the refund event
    print("  invoice total=%d refunded=%d  cash_collected=%d" % (inv["total"], inv["refunded"], a.cash_collected))
    print("  audit: %s" % a.audit())

def f4_upgrade_credit():
    a = B.BillingAccount(plan="basic", cycle_days=30, proration="credit")
    print("  paid so far: %d" % a.cash_collected)
    a.change_plan("team")
    print("  credit granted for the unused remainder: %d" % a.credit_balance)
    print("  audit: %s" % a.audit())

def f5_transient():
    a = B.BillingAccount(plan="basic", cycle_days=30, proration="credit")
    snaps = []
    a.change_plan("pro");  snaps.append(("after upgrade", a.audit(), a.credit_balance))
    a.tick(30);            snaps.append(("after renewal 1", a.audit(), a.credit_balance))
    a.tick(30);            snaps.append(("after renewal 2", a.audit(), a.credit_balance))
    a.tick(30);            snaps.append(("after renewal 3", a.audit(), a.credit_balance))
    for label, bad, cb in snaps:
        print("  %-18s audit=%-8s credit_balance=%d" % (label, bad or "clean", cb))
    print("  FINAL audit: %s   <- an end-of-test assertion sees nothing" % (a.audit() or "clean"))

show("F1  coupon allowance resets when the SAME coupon is re-applied  [I5]",
     f1_coupon_reset,
     "apply_coupon() sets self.coupon_uses = 0 unconditionally (billing_core.py:apply_coupon)")

show("F2  refunding one invoice twice exceeds it  [I4]",
     f2_refund_twice,
     "refund() caps each CALL at inv['total'] but accumulates into inv['refunded'] "
     "without subtracting what was already refunded")

show("F3  webhook redelivery re-executes a refund  [I4]",
     f3_refund_replay,
     "_charge_invoice registers its event in self._events; refund()/chargeback() mint an "
     "event id but never register it, so replay() treats it as unseen")

show("F4  mid-cycle upgrade credits at the NEW plan's price  [I8]",
     f4_upgrade_credit,
     "change_plan() assigns self.plan = plan BEFORE computing "
     "unused = _price_of(self.plan) * frac")

show("F5  TRANSIENT: the invariant breaks, then heals before the end",
     f5_transient,
     "the over-credit from F4 is burned down by later renewals; only an oracle that "
     "looks DURING the run can see it")

def f6_restart_dupe_ids():
    a = B.BillingAccount(plan="pro", cycle_days=7)
    a.tick(28)
    print("  before restart: ids=%s cash=%d audit=%s" % ([i["id"] for i in a.invoices], a.cash_collected, a.audit() or "clean"))
    keep = dict((k, v) for k, v in a.__dict__.items() if not k.startswith("_"))
    fresh = B.BillingAccount(plan=a.plan, cycle_days=a.cycle_days,
                             proration=a.proration, rounding=a.rounding)
    fresh.__dict__.update(keep)
    a = fresh
    a.tick(14)
    ids = [i["id"] for i in a.invoices]
    print("  after  restart: ids=%s" % ids)
    print("  duplicate invoice numbers: %s      SUT audit: %s" % (len(ids) != len(set(ids)), a.audit() or "clean"))

show("F6  a process restart resets the invoice counter -> DUPLICATE invoice numbers",
     f6_restart_dupe_ids,
     "_next_invoice / _next_event / _events are private bookkeeping. A store persists "
     "the declared columns; private state does not survive the restart, so numbering "
     "begins again at 1 and the webhook idempotency set is empty")
