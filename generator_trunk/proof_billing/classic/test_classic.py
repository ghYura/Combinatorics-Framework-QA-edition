#!/usr/bin/env python3
"""
Classic test suite for billing_core, written the standard way:

  A. Equivalence partitioning        - one representative per input class
  B. Boundary value analysis         - on/off/around each boundary
  C. State transition testing        - 0-switch and 1-switch coverage of the
                                       active/paused/cancelled machine
  D. Use-case / scenario tests       - the documented happy paths
  E. Pairwise (2-way covering array) - IPOG over the full parameter model,
                                       verified to 100% pair coverage

The oracle is the engine's documented invariant set (audit()) plus explicit
expected values where the spec fixes them.

Run:  python3 test_classic.py

Note on pytest: the test_* functions here record findings through `check()` rather
than asserting, because this suite is a measuring instrument for the SUT, not a
gate on it. Collected by pytest they therefore pass whatever they find; the
verdict is the failure list `main()` prints when you run the file directly.
"""

import itertools
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sut"))
import billing_core as B  # noqa: E402


FAILURES = []
RUN = [0]
PAIRWISE_CASES = [0]


def check(name, cond, detail=""):
    RUN[0] += 1
    if not cond:
        FAILURES.append((name, detail))


def audit_clean(name, acct):
    bad = acct.audit()
    check(name, not bad, "invariants violated: %s" % bad)


# ==========================================================================
# A. Equivalence partitioning
# ==========================================================================

def test_partitions():
    # plan classes: zero-price, low, mid, high
    for plan in ("free", "basic", "pro", "team"):
        a = B.BillingAccount(plan=plan)
        check("EP.signup.%s" % plan,
              a.cash_collected == B.PLANS[plan]["price"],
              "cash=%d" % a.cash_collected)
        audit_clean("EP.audit.%s" % plan, a)

    # proration classes
    for pr in ("credit", "immediate", "none"):
        a = B.BillingAccount(plan="pro", proration=pr)
        a.tick(10)
        a.change_plan("basic")
        audit_clean("EP.proration.%s" % pr, a)

    # rounding classes
    for rd in ("half_up", "floor", "bankers"):
        a = B.BillingAccount(plan="pro", rounding=rd)
        a.apply_coupon("loyal10")
        a.tick(30)
        audit_clean("EP.rounding.%s" % rd, a)

    # coupon classes
    for c in ("none", "welcome", "loyal10", "half"):
        a = B.BillingAccount(plan="basic")
        a.apply_coupon(c)
        a.tick(30)
        audit_clean("EP.coupon.%s" % c, a)

    # invalid inputs are rejected
    for bad in ("gold", "", "BASIC"):
        try:
            B.BillingAccount(plan=bad)
            check("EP.reject.%s" % bad, False, "accepted an unknown plan")
        except B.BillingError:
            check("EP.reject.%s" % bad, True)


# ==========================================================================
# B. Boundary value analysis
# ==========================================================================

def test_boundaries():
    # renewal boundary: day cycle-1 (no charge), day cycle (charge)
    a = B.BillingAccount(plan="basic", cycle_days=30)
    a.tick(29)
    check("BVA.renew.before", len(a.invoices) == 1, "invoices=%d" % len(a.invoices))
    a.tick(1)
    check("BVA.renew.on", len(a.invoices) == 2, "invoices=%d" % len(a.invoices))
    audit_clean("BVA.renew.audit", a)

    # trial boundary: last trial day free, first post-trial day billed
    a = B.BillingAccount(plan="basic", cycle_days=10, trial_days=10)
    check("BVA.trial.signup", a.cash_collected == 0, "cash=%d" % a.cash_collected)
    a.tick(9)
    check("BVA.trial.inside", a.cash_collected == 0, "cash=%d" % a.cash_collected)
    a.tick(1)
    check("BVA.trial.after", a.cash_collected > 0, "cash=%d" % a.cash_collected)
    audit_clean("BVA.trial.audit", a)

    # coupon use limits: exactly max_uses discounted cycles, then none
    a = B.BillingAccount(plan="basic", cycle_days=10)
    a.apply_coupon("loyal10")          # max_uses = 3
    a.tick(50)
    n = sum(1 for inv in a.invoices for l in inv["lines"]
            if l["desc"].startswith("coupon:"))
    check("BVA.coupon.limit", n == 3, "discounted %d cycles, expected 3" % n)
    audit_clean("BVA.coupon.audit", a)

    # proration boundaries: change on day 0 (full remainder) and on the last day
    for day in (0, 29):
        a = B.BillingAccount(plan="pro", cycle_days=30, proration="credit")
        a.tick(day)
        a.change_plan("basic")
        audit_clean("BVA.prorate.day%d" % day, a)

    # refund boundary: a full refund of an invoice, never more
    a = B.BillingAccount(plan="basic")
    a.refund()
    inv = a.invoices[0]
    check("BVA.refund.cap", inv["refunded"] <= inv["total"],
          "refunded=%d total=%d" % (inv["refunded"], inv["total"]))
    audit_clean("BVA.refund.audit", a)

    # cycle length extremes
    for cd in (1, 7, 30, 365):
        a = B.BillingAccount(plan="basic", cycle_days=cd)
        a.tick(cd)
        check("BVA.cycle.%d" % cd, len(a.invoices) == 2, "invoices=%d" % len(a.invoices))
        audit_clean("BVA.cycle.audit.%d" % cd, a)


# ==========================================================================
# C. State transition testing (0-switch and 1-switch coverage)
# ==========================================================================

TRANSITIONS = {
    "active":    [("pause", "paused"), ("cancel", "cancelled")],
    "paused":    [("resume", "active"), ("cancel", "cancelled")],
    "cancelled": [("reactivate", "active")],
}


def _drive(acct, op):
    getattr(acct, op)()


def test_state_transitions():
    # 0-switch: every single legal transition from every state
    for src, arcs in TRANSITIONS.items():
        for op, dst in arcs:
            a = B.BillingAccount(plan="basic")
            _reach(a, src)
            _drive(a, op)
            check("ST.0switch.%s-%s" % (src, op), a.state == dst,
                  "state=%s expected=%s" % (a.state, dst))
            audit_clean("ST.0switch.audit.%s-%s" % (src, op), a)

    # 1-switch: every legal pair of consecutive transitions
    for src, arcs in TRANSITIONS.items():
        for op1, mid in arcs:
            for op2, dst in TRANSITIONS[mid]:
                a = B.BillingAccount(plan="basic")
                _reach(a, src)
                _drive(a, op1)
                a.tick(1)
                _drive(a, op2)
                check("ST.1switch.%s-%s-%s" % (src, op1, op2), a.state == dst,
                      "state=%s expected=%s" % (a.state, dst))
                audit_clean("ST.1switch.audit.%s-%s-%s" % (src, op1, op2), a)

    # illegal transitions are rejected
    a = B.BillingAccount(plan="basic")
    for op in ("resume", "reactivate"):
        try:
            _drive(a, op)
            check("ST.illegal.active.%s" % op, False, "accepted an illegal transition")
        except B.BillingError:
            check("ST.illegal.active.%s" % op, True)


def _reach(acct, state):
    if state == "paused":
        acct.pause()
    elif state == "cancelled":
        acct.cancel()


# ==========================================================================
# D. Use-case / scenario tests (documented happy paths)
# ==========================================================================

def test_scenarios():
    # UC1 sign up, run three cycles, cancel
    a = B.BillingAccount(plan="pro", cycle_days=30)
    a.tick(90)
    check("UC1.invoices", len(a.invoices) == 4, "invoices=%d" % len(a.invoices))
    check("UC1.cash", a.cash_collected == 4 * 3000, "cash=%d" % a.cash_collected)
    a.cancel()
    audit_clean("UC1.audit", a)

    # UC2 trial, then convert
    a = B.BillingAccount(plan="basic", cycle_days=30, trial_days=14)
    a.tick(30)
    check("UC2.billed_once", a.cash_collected == 1000, "cash=%d" % a.cash_collected)
    audit_clean("UC2.audit", a)

    # UC3 upgrade mid-cycle with credit proration
    a = B.BillingAccount(plan="basic", cycle_days=30, proration="credit")
    a.tick(15)
    a.change_plan("pro")
    a.tick(15)
    audit_clean("UC3.audit", a)

    # UC4 pause for a month, resume, keep the paid-for days
    a = B.BillingAccount(plan="basic", cycle_days=30)
    a.tick(10)
    a.pause()
    a.tick(30)
    a.resume()
    check("UC4.no_charge_while_paused", len(a.invoices) == 1,
          "invoices=%d" % len(a.invoices))
    a.tick(20)
    check("UC4.renews_after", len(a.invoices) == 2, "invoices=%d" % len(a.invoices))
    audit_clean("UC4.audit", a)

    # UC5 cancel then reactivate
    a = B.BillingAccount(plan="basic", cycle_days=30)
    a.tick(10)
    a.cancel()
    a.tick(60)
    a.reactivate()
    check("UC5.reactivated", a.state == "active", "state=%s" % a.state)
    audit_clean("UC5.audit", a)

    # UC6 coupon on signup and first renewal
    a = B.BillingAccount(plan="basic", cycle_days=30)
    a.apply_coupon("welcome")
    a.tick(60)
    audit_clean("UC6.audit", a)

    # UC7 refund the last invoice
    a = B.BillingAccount(plan="pro", cycle_days=30)
    a.tick(30)
    a.refund()
    audit_clean("UC7.audit", a)

    # UC8 chargeback
    a = B.BillingAccount(plan="pro", cycle_days=30)
    a.chargeback()
    audit_clean("UC8.audit", a)

    # UC9 webhook redelivery is a no-op
    a = B.BillingAccount(plan="pro", cycle_days=30)
    before = a.cash_collected
    a.replay()
    check("UC9.idempotent", a.cash_collected == before,
          "cash %d -> %d" % (before, a.cash_collected))
    audit_clean("UC9.audit", a)


# ==========================================================================
# E. Pairwise: IPOG covering array over the parameter model
# ==========================================================================

MODEL = [
    ("plan",        ["free", "basic", "pro", "team"]),
    ("cycle_days",  [1, 7, 30, 365]),
    ("proration",   ["credit", "immediate", "none"]),
    ("rounding",    ["half_up", "floor", "bankers"]),
    ("trial_days",  [0, 7, 14]),
    ("dunning",     [False, True]),
    ("coupon",      ["none", "welcome", "loyal10", "half"]),
    ("do_change",   ["no", "up", "down"]),
    ("do_pause",    [False, True]),
    ("do_cancel",   [False, True]),
    ("do_refund",   [False, True]),
    ("do_replay",   [False, True]),
    ("ticks",       [0, 1, 30, 90]),
]


def ipog(model, t=2):
    """Standard IPOG horizontal+vertical growth. Returns a t-way covering array."""
    names = [m[0] for m in model]
    vals = [m[1] for m in model]

    rows = [list(c) for c in itertools.product(*vals[:t])]

    for k in range(t, len(names)):
        # every t-way combination that involves parameter k
        pis = set()
        for idxs in itertools.combinations(range(k), t - 1):
            for combo in itertools.product(*[vals[i] for i in idxs]):
                for v in vals[k]:
                    pis.add((idxs + (k,), combo + (v,)))

        # horizontal growth: extend existing rows
        for row in rows:
            best, best_cov = None, -1
            for v in vals[k]:
                cov = sum(1 for (idxs, combo) in pis
                          if combo[-1] == v
                          and all(row[i] == combo[j] for j, i in enumerate(idxs[:-1])))
                if cov > best_cov:
                    best, best_cov = v, cov
            row.append(best)
            for (idxs, combo) in list(pis):
                if combo[-1] == best and all(row[i] == combo[j]
                                             for j, i in enumerate(idxs[:-1])):
                    pis.discard((idxs, combo))

        # vertical growth: new rows for whatever is left
        for (idxs, combo) in sorted(pis, key=lambda x: str(x)):
            placed = False
            for row in rows:
                if all(row[i] is None or row[i] == combo[j]
                       for j, i in enumerate(idxs)):
                    for j, i in enumerate(idxs):
                        row[i] = combo[j]
                    placed = True
                    break
            if not placed:
                row = [None] * (k + 1)
                for j, i in enumerate(idxs):
                    row[i] = combo[j]
                rows.append(row)

    # fill any remaining holes with the first value
    for row in rows:
        for i, v in enumerate(row):
            if v is None:
                row[i] = vals[i][0]
    return names, rows


def verify_coverage(names, rows, model, t=2):
    """Prove the array really is t-way complete."""
    vals = [m[1] for m in model]
    missing = 0
    total = 0
    for idxs in itertools.combinations(range(len(names)), t):
        for combo in itertools.product(*[vals[i] for i in idxs]):
            total += 1
            if not any(all(row[i] == combo[j] for j, i in enumerate(idxs))
                       for row in rows):
                missing += 1
    return total, missing


def run_case(cfg):
    """Execute one pairwise case. Operations run in the canonical documented
    order - pairwise has no ordering semantics, so this is the standard way."""
    a = B.BillingAccount(plan=cfg["plan"],
                         cycle_days=cfg["cycle_days"],
                         proration=cfg["proration"],
                         rounding=cfg["rounding"],
                         trial_days=cfg["trial_days"],
                         dunning=cfg["dunning"])
    if cfg["coupon"] != "none":
        a.apply_coupon(cfg["coupon"])
    if cfg["do_change"] != "no":
        rank = B.PLANS[cfg["plan"]]["rank"]
        target = None
        order = sorted(B.PLANS, key=lambda p: B.PLANS[p]["rank"])
        if cfg["do_change"] == "up" and rank < 3:
            target = order[rank + 1]
        elif cfg["do_change"] == "down" and rank > 0:
            target = order[rank - 1]
        if target:
            a.change_plan(target)
    if cfg["do_pause"]:
        a.pause()
        a.resume()
    if cfg["ticks"]:
        a.tick(cfg["ticks"])
    if cfg["do_refund"]:
        a.refund()
    if cfg["do_replay"]:
        a.replay()
    if cfg["do_cancel"]:
        a.cancel()
    return a


def test_pairwise():
    names, rows = ipog(MODEL, t=2)
    total, missing = verify_coverage(names, rows, MODEL, t=2)
    check("PW.coverage", missing == 0,
          "%d of %d pairs uncovered" % (missing, total))
    print("    pairwise array: %d cases, %d pairs, %d uncovered"
          % (len(rows), total, missing))

    errors = 0
    for n, row in enumerate(rows):
        cfg = dict(zip(names, row))
        try:
            a = run_case(cfg)
        except B.BillingError:
            continue                       # a rejected illegal op is not a defect
        bad = a.audit()
        if bad:
            errors += 1
            check("PW.case%03d" % n, False, "%s :: %s" % (bad, cfg))
    print("    pairwise cases with invariant violations: %d" % errors)
    PAIRWISE_CASES[0] = len(rows)


# ==========================================================================

def main():
    print("classic suite on billing_core")
    print("  A. equivalence partitioning");  test_partitions()
    print("  B. boundary value analysis");   test_boundaries()
    print("  C. state transition testing");  test_state_transitions()
    print("  D. use-case scenarios");        test_scenarios()
    print("  E. pairwise (2-way)")
    test_pairwise()

    print("")
    print("checks run : %d" % RUN[0])
    print("failures   : %d" % len(FAILURES))
    for name, detail in FAILURES:
        print("  FAIL %-34s %s" % (name, detail))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
