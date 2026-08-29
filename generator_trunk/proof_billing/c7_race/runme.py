#!/usr/bin/env python3
"""RunMeFirstOnce - Bootstrap for C7.

Two run-scoped jobs: a sha256 gate that refuses a drifted SUT, and a
pre-loaded high-contention multi-threaded harness that every candidate drives.
No golden file is needed here: the oracle is the component's OWN accounting
identity, which no legal interleaving of correct code may ever break."""
import hashlib, os, sys

SUT_DIR  = os.environ.get("PROOF_SUT_ROOT", "proof_billing/sut")
SUT_FILE = os.path.join(SUT_DIR, "billing_core.py")
FROZEN   = '72d9b505bbe785fded13b512582cc7e94aa6d7e86ea2fa435b6d3cf050892f45'
WORK     = "/tmp/fw_work"
HARNESS  = os.path.join(WORK, "c7_harness.py")

HARNESS_SRC = '\n"""C7 high-contention harness, pre-loaded by RunMeFirstOnce.\n\nEvery worker drives the SAME account. cycle_days=1 means every tick raises and\nsettles an invoice, so each operation spends a long time inside _charge_invoice:\na read-modify-write of cash_collected, two list appends and two counter bumps.\nThat is the widest race window the component has.\n"""\nimport sys, threading\n\ndef run(sut_dir, mode, nops, workers, use_lock=False, barrier=False):\n    if sut_dir not in sys.path:\n        sys.path.insert(0, sut_dir)\n    import billing_core as B\n\n    acct = B.BillingAccount(plan="pro", cycle_days=1)\n    lock = threading.Lock()\n    bar  = threading.Barrier(workers) if barrier else None\n    errors = []\n\n    share = [nops // workers] * workers\n    for i in range(nops % workers):\n        share[i] += 1\n\n    def one(w, i):\n        if mode == "tick":\n            acct.tick(1)\n        elif mode == "mixed":\n            k = (w + i) % 3\n            if k == 0:\n                acct.tick(1)\n            elif k == 1:\n                acct.replay()\n            else:\n                acct.apply_coupon("loyal10")\n        else:\n            acct.tick(1)\n            acct.replay()\n\n    def work(w, k):\n        if bar is not None:\n            bar.wait()\n        for i in range(k):\n            try:\n                if use_lock:\n                    with lock:\n                        one(w, i)\n                else:\n                    one(w, i)\n            except B.BillingError:\n                pass\n            except Exception as exc:\n                errors.append(type(exc).__name__)\n\n    ts = [threading.Thread(target=work, args=(w, share[w])) for w in range(workers)]\n    for t in ts:\n        t.start()\n    for t in ts:\n        t.join(60)\n\n    ch = sum(e["amount"] for e in acct.ledger if e["kind"] == "charge")\n    rf = sum(e["amount"] for e in acct.ledger if e["kind"] == "refund")\n    cb = sum(e["amount"] for e in acct.ledger if e["kind"] == "chargeback")\n    return {\n        "cash": acct.cash_collected,\n        "expected_cash": ch - rf - cb,\n        "invoices": len(acct.invoices),\n        "ledger": len(acct.ledger),\n        "uniqids": len(set(i["id"] for i in acct.invoices)),\n        "audit": sorted(acct.audit()),\n        "errors": sorted(set(errors)),\n    }\n'

def main():
    h = hashlib.sha256(open(SUT_FILE, "rb").read()).hexdigest()
    if h != FROZEN:
        sys.stderr.write("RunMeFirstOnce: SUT hash drift" + chr(10))
        raise SystemExit(2)
    os.makedirs(WORK, exist_ok=True)
    if not os.path.exists(HARNESS):
        tmp = HARNESS + ".tmp"
        open(tmp, "w").write(HARNESS_SRC)
        os.replace(tmp, HARNESS)

main()
