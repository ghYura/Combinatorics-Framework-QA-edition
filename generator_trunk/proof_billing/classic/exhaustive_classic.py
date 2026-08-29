#!/usr/bin/env python3
"""
The decisive control experiment.

Pairwise is a SAMPLING strategy over a parameter model. If a defect is missed
because the sample was too small, a bigger sample finds it. If a defect is
missed because the MODEL cannot express the test case, no sample of any size
finds it - not 2-way, not 6-way, not exhaustive.

So: run the classic model EXHAUSTIVELY. Every point in the cartesian product of
the same parameters the pairwise suite uses, with the same canonical operation
order that a covering array forces on you. Then check which of the findings
survive.

  full model = 4*4*3*3*3*2*4*3*2*2*2*2*4 = 663,552 cases
"""
import collections
import itertools
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sut"))
import billing_core as B  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_classic import MODEL, run_case  # noqa: E402  (the SAME model and driver)


def main():
    names = [m[0] for m in MODEL]
    vals = [m[1] for m in MODEL]
    total = 1
    for v in vals:
        total *= len(v)
    print("exhaustive classic model: %d cases over %d parameters" % (total, len(names)))

    found = collections.Counter()
    witness = {}
    rejected = 0
    crashed = collections.Counter()
    t0 = time.time()
    n = 0

    for row in itertools.product(*vals):
        n += 1
        cfg = dict(zip(names, row))
        try:
            a = run_case(cfg)
        except B.BillingError:
            rejected += 1
            continue
        except Exception as exc:                     # noqa: BLE001
            crashed[type(exc).__name__] += 1
            continue
        for inv in a.audit():
            found[inv] += 1
            witness.setdefault(inv, dict(cfg))
        if n % 100000 == 0:
            print("  %d/%d  (%.0fs)" % (n, total, time.time() - t0))

    print("\ncases executed      : %d" % (n - rejected))
    print("cases rejected      : %d  (an illegal op for that config)" % rejected)
    print("elapsed             : %.0fs" % (time.time() - t0))
    if crashed:
        print("unexpected crashes  : %s" % dict(crashed))

    print("\nINVARIANTS THE EXHAUSTIVE CLASSIC MODEL CAN REACH")
    for inv in sorted(found):
        print("  %-4s %8d cases   e.g. %s" % (inv, found[inv], witness[inv]))

    every = ["I1", "I2", "I3", "I4", "I5", "I6", "I7", "I8", "I9"]
    missed = [i for i in every if i not in found]
    print("\nNEVER REACHED, at any strength, by this model: %s"
          % (", ".join(missed) if missed else "(none)"))
    return found


if __name__ == "__main__":
    main()
