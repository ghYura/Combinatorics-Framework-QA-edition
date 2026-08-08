#!/usr/bin/env python3
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
# (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
# Ukraine
#
# See LICENSE and NOTICE.md for the binding terms.

"""Re-probe the live pricing SUT over the SAME post-sieve 240-combo space and emit a
K=V corpus, so the Analyzer's Pareto front can be shown inside the allowed dirs
(the bundle_run corpus lands in /mnt/F scratch). Mirrors the spec's TAIL oracle."""
import itertools, json, os, time, urllib.request
from pathlib import Path

BASE = os.environ.get("PRICING_URL", "http://127.0.0.1:8027")
PCT, FIXED = {"SUMMER": 0.20}, {"LOYALTY": 10.00}
TAX, LEGACY_FLAT_TAX = {"us": 0.0825, "eu": 0.20}, 0.0825


def post(path, payload):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=8) as r:
        return r.status, json.loads(r.read().decode())


def discount(p, coupons):
    p -= sum(FIXED[c] for c in coupons if c in FIXED)
    for c in coupons:
        if c in PCT:
            p *= (1 - PCT[c])
    return p


def canonical(coupons, region):
    return round(discount(100.0, coupons) * (1 + TAX[region]), 2)


def literal(coupons, region, stages, mode):
    p, tax = 100.0, (LEGACY_FLAT_TAX if mode == "legacy" else TAX[region])
    for st in stages:
        p = discount(p, coupons) if st == "discount" else p * (1 + tax) if st == "tax" else round(p, 2)
    return round(p, 2)


MODES = ["strict", "fast", "legacy"]
COUPON_SUBSETS = [list(c) for r in range(3) for c in itertools.combinations(["SUMMER", "LOYALTY"], r)]
STAGE_PERMS = [list(p) for p in itertools.permutations(["discount", "tax", "round"])]
REGIONS = ["us", "eu"]

lines, n = [], 0
for mode in MODES:
    for coupons in COUPON_SUBSETS:
        for stages in STAGE_PERMS:
            for region in REGIONS:
                # the 'bonds' sieve: legacy is not EU-certified -> skip legacy x eu (never executed)
                if mode == "legacy" and region == "eu":
                    continue
                for retry in (0, 1):                       # FW_Optional: duplicate request OR absent
                    sid = "front-%d" % n
                    n += 1
                    canon = canonical(coupons, region)
                    t0 = time.monotonic()
                    status, body = post("/checkout", {"scenario_id": sid, "idem_key": "k1", "mode": mode,
                                                      "region": region, "coupons": coupons, "stages": stages})
                    if retry:
                        status, body = post("/checkout", {"scenario_id": sid, "idem_key": "k1", "mode": mode,
                                                          "region": region, "coupons": coupons, "stages": stages})
                    latency = (time.monotonic() - t0) * 1000.0
                    price = float(body.get("price", -1))
                    ledger = float(body.get("ledger_total", -1))
                    lit = literal(coupons, region, stages, mode)
                    price_bad = int(abs(price - canon) > 0.005)
                    order_defect = int(price_bad and abs(price - lit) <= 0.005)
                    idem_defect = int((not price_bad) and abs(ledger - canon) > 0.005)
                    fw = 5 if (status != 200 or not body.get("ok")) else (
                        (2 if order_defect else 5) if price_bad else (3 if idem_defect else 0))
                    severity = min(8 * idem_defect + 6 * order_defect + (10 if fw == 5 else 0), 10)
                    lines.append(
                        "app=pricing mode=%s region=%s coupons=%s stages=%s retry=%d severity=%d "
                        "correct=%d latency_ms=%.3f overcharge_cents=%d price_err_cents=%d FW_VAR=%d"
                        % (mode, region, "+".join(coupons) or "none", ">".join(stages), retry, severity,
                           int(fw == 0), latency, round((ledger - canon) * 100), round(abs(price - canon) * 100), fw))

out = Path(__file__).resolve().parent / "pricing_metrics.kv"
out.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("wrote %d K=V rows -> %s" % (len(lines), out))
