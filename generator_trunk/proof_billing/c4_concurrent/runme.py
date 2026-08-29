#!/usr/bin/env python3
"""RunMeFirstOnce - the run-scoped prologue (Bootstrap) for C4.

Three run-scoped jobs, none of them a combinatorial axis:

  1. PREREQUISITE - refuse the run unless the SUT is the exact sha256-frozen
     artifact the campaign was designed against. A drifted SUT would silently
     invalidate every verdict in the family.

  2. PRE-LOADED CONCURRENCY HARNESS - materialise, once, the multi-threaded
     executor that every candidate will drive. The harness IS the test case:
     it spawns real threads against one shared account, optionally behind a
     barrier for maximum contention and optionally behind a caller-supplied
     lock. Candidates do not re-implement it; they only declare WHICH
     concurrent scenario to run. This keeps threading out of the combinatorial
     space while making every point in that space a concurrent execution.

  3. GOLDEN REFERENCE - compute once the SERIALIZED outcome of each operation
     multiset, and publish it for the whole candidate family. A candidate is a
     differential test: concurrent outcome vs the serialized truth.

Idempotent by construction: everything is written once and reused, which is
what "Once" means at an Executor handoff.
"""
import hashlib, json, os, sys

SUT_DIR  = os.environ.get("PROOF_SUT_ROOT", "proof_billing/sut")
SUT_FILE = os.path.join(SUT_DIR, "billing_core.py")
FROZEN   = "72d9b505bbe785fded13b512582cc7e94aa6d7e86ea2fa435b6d3cf050892f45"
WORK     = "/tmp/fw_work"
GOLDEN   = os.path.join(WORK, "c4_golden.json")
HARNESS  = os.path.join(WORK, "c4_harness.py")

HARNESS_SRC = '''
"""Pre-loaded multi-threaded harness. Established by RunMeFirstOnce, driven by
every candidate. Runs  operations against ONE shared account spread over
 real threads."""
import sys, threading

def _apply(acct, op, mod):
    if op == "tick":
        acct.tick(1)
    elif op == "replay":
        acct.replay()
    elif op == "refund":
        acct.refund()
    elif op == "coupon":
        acct.apply_coupon("half")
    elif op == "change":
        acct.change_plan("team" if mod % 2 else "basic")

def run(sut_dir, op, nops, workers, use_lock=False, barrier=False, plan="pro"):
    if sut_dir not in sys.path:
        sys.path.insert(0, sut_dir)
    import billing_core as B

    acct = B.BillingAccount(plan=plan, cycle_days=30)
    lock = threading.Lock()
    bar  = threading.Barrier(workers) if barrier else None
    errors = []

    share = [nops // workers] * workers
    for i in range(nops % workers):
        share[i] += 1

    def work(w, k):
        if bar is not None:
            bar.wait()
        for i in range(k):
            try:
                if use_lock:
                    with lock:
                        _apply(acct, op, w + i)
                else:
                    _apply(acct, op, w + i)
            except B.BillingError:
                pass
            except Exception as exc:
                errors.append(type(exc).__name__)

    ts = [threading.Thread(target=work, args=(w, share[w])) for w in range(workers)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(30)

    return {
        "cash": acct.cash_collected,
        "invoices": len(acct.invoices),
        "ledger": len(acct.ledger),
        "audit": sorted(acct.audit()),
        "errors": sorted(set(errors)),
    }
'''


def main():
    h = hashlib.sha256(open(SUT_FILE, "rb").read()).hexdigest()
    if h != FROZEN:
        sys.stderr.write("RunMeFirstOnce: SUT hash drift %s != %s\n" % (h, FROZEN))
        raise SystemExit(2)

    os.makedirs(WORK, exist_ok=True)

    if not os.path.exists(HARNESS):
        tmp = HARNESS + ".tmp"
        open(tmp, "w").write(HARNESS_SRC)
        os.replace(tmp, HARNESS)

    if os.path.exists(GOLDEN):
        return

    sys.path.insert(0, SUT_DIR)
    import billing_core as B

    sys.path.insert(0, WORK)
    import c4_harness

    golden = {}
    for nops in (2, 4, 8):
        for op in ("replay", "tick", "refund", "coupon", "change"):
            acct = B.BillingAccount(plan="pro", cycle_days=30)
            for i in range(nops):
                try:
                    c4_harness._apply(acct, op, i)
                except B.BillingError:
                    pass
            golden["%s:%d" % (op, nops)] = {
                "cash": acct.cash_collected,
                "invoices": len(acct.invoices),
                "ledger": len(acct.ledger),
                "audit": sorted(acct.audit()),
            }
    tmp = GOLDEN + ".tmp"
    json.dump(golden, open(tmp, "w"))
    os.replace(tmp, GOLDEN)


main()
