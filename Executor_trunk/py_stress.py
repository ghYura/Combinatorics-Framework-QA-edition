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

r"""py_stress — combinatorial STORM mode for the Bundle's Executor stage.

Same materialized candidates as py_executor (Core→Reader output), but instead of
running each once for a correctness verdict, it turns them into a *load mix*:

    ACCUMULATE  load every candidate's `fw_fire(client)` "shot"  (the cloud saturates)
    BURST       a pool of W workers fires them CONCURRENTLY at --base-url for a
                duration, ramped up                              (the downpour)
    OBSERVE     latency percentiles + error-rate vs an SLO       (the flood gauge)

The load is *combinatorially diverse* (each shot's shape comes from its slots —
valid/bad/missing/expired auth, intra vs proxy), which is a harsher, more
realistic stress profile than a uniform RPS flood. Collapse the slots to one
value and you get the classic uniform-URL load test as a special case.

Verdict here is SLO-based (no 5xx / conn-error, p99 within budget) — NOT exact
correctness; correctness needs the isolated py_executor run instead.

Handshake-compatible with py_executor: -srcDirList DIR [-dirResultsDbURL DIR].
"""
from __future__ import annotations

import argparse
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx


def load_fires(srcdir: str) -> list[tuple[str, object]]:
    """Exec each candidate in stress mode (heavy flow skipped) and collect its fw_fire."""
    fires = []
    for p in sorted(Path(srcdir).glob("*.py")):
        ns = {"__name__": "__candidate__"}
        try:
            exec(compile(p.read_text(encoding="utf-8"), str(p), "exec"), ns)
        except Exception:
            continue
        fire = ns.get("fw_fire")
        if callable(fire):
            fires.append((p.name, fire))
    return fires


def worker(idx: int, fires, stop_at: float, ramp_gap: float):
    time.sleep(idx * ramp_gap)  # staggered ramp-up
    lat: list[float] = []
    n5xx = nconn = n = 0
    limits = httpx.Limits(max_connections=2, max_keepalive_connections=2)
    with httpx.Client(timeout=10.0, limits=limits) as client:
        while time.monotonic() < stop_at:
            _name, fire = random.choice(fires)
            t0 = time.monotonic()
            try:
                status = fire(client)
                lat.append((time.monotonic() - t0) * 1000.0)
                n += 1
                if status >= 500:
                    n5xx += 1
            except Exception:
                nconn += 1
                n += 1
    return lat, n5xx, nconn, n


def write_summary(results_db_dir: str, m: dict) -> None:
    try:
        import pg8000.dbapi

        from py_executor import parse_jdbc

        url_file = next(Path(results_db_dir).glob("*.properties"), None)
        if url_file is None:
            return
        url = next((ln for ln in url_file.read_text().splitlines() if ln.startswith("jdbc:")), "")
        db = parse_jdbc(url)
        conn = pg8000.dbapi.connect(**db)
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS stress_summary ("
                    "ts timestamptz default now(), workers int, requests bigint, rps double precision,"
                    "p50 double precision, p95 double precision, p99 double precision,"
                    "err_rate double precision, n5xx bigint, conn_err bigint, fw_var int)")
        cur.execute("INSERT INTO stress_summary (workers,requests,rps,p50,p95,p99,err_rate,n5xx,conn_err,fw_var)"
                    " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (m["workers"], m["requests"], m["rps"], m["p50"], m["p95"], m["p99"],
                     m["err_rate"], m["n5xx"], m["nconn"], m["verdict"]))
        conn.commit()
        cur.close()
        conn.close()
        print(f"  → wrote stress_summary row to Results DB :{db['port']}/{db['database']}")
    except Exception as e:  # never let DB issues fail the run
        print(f"  (stress_summary not written: {type(e).__name__}: {e})")


def parse_args(argv):
    a, i = {}, 0
    while i < len(argv):
        tok = argv[i]
        if tok.startswith("-") and i + 1 < len(argv) and not argv[i + 1].startswith("-"):
            a[tok.lstrip("-")] = argv[i + 1]
            i += 2
        else:
            i += 1
    return a


def main():
    a = parse_args(sys.argv[1:])
    srcdir = a.get("srcDirList") or a.get("src")
    if not srcdir:
        raise SystemExit("py_stress: -srcDirList DIR required")
    base_url = a.get("base-url", "http://127.0.0.1:8121")
    secret = a.get("secret", "oot-secret")
    workers = int(a.get("workers", "16"))
    duration = float(a.get("duration", "10"))
    ramp = float(a.get("ramp", "3"))
    slo_p99 = float(a.get("slo-p99", "1500"))
    err_budget = float(a.get("err-budget", "0.01"))
    write_db = str(a.get("writeToDB", "false")).lower() == "true"

    os.environ["OOT_MODE"] = "stress"
    os.environ["OOT_TARGET1"] = base_url
    os.environ["OOT_TARGET2"] = a.get("base-url2", base_url.replace("8121", "8122"))
    os.environ["OOT_SECRET"] = secret

    fires = load_fires(srcdir)
    if not fires:
        raise SystemExit("py_stress: no fw_fire candidates found in " + srcdir)
    print(f"py_stress: ACCUMULATE — {len(fires)} fire-shapes loaded (the cloud)")
    print(f"py_stress: BURST — {workers} workers, ramp {ramp}s + sustain {duration}s → {base_url}")

    ramp_gap = ramp / max(1, workers)
    stop_at = time.monotonic() + ramp + duration
    t0 = time.monotonic()
    lat_all, n5xx, nconn, n_total = [], 0, 0, 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for lat, e5, ec, n in ex.map(lambda i: worker(i, fires, stop_at, ramp_gap), range(workers)):
            lat_all += lat
            n5xx += e5
            nconn += ec
            n_total += n
    wall = time.monotonic() - t0
    lat_all.sort()

    def pct(p):
        return lat_all[min(len(lat_all) - 1, int(len(lat_all) * p / 100))] if lat_all else 0.0

    p50, p95, p99 = pct(50), pct(95), pct(99)
    err = (n5xx + nconn) / max(1, n_total)
    rps = n_total / max(1e-9, wall)
    verdict = 0 if (p99 <= slo_p99 and err <= err_budget) else 3

    print(f"py_stress: OBSERVE")
    print(f"  requests={n_total}  rps={rps:.0f}  5xx={n5xx}  conn_err={nconn}  err_rate={err:.4f}")
    print(f"  latency_ms  p50={p50:.1f}  p95={p95:.1f}  p99={p99:.1f}   (SLO p99={slo_p99})")
    print(f"  VERDICT FW_VAR={verdict}  ({'within SLO' if verdict == 0 else 'SLO/error breach'})")
    # analyzer-ingestible K=V
    print(f"FW_STRESS rps={rps:.0f} p50={p50:.1f} p95={p95:.1f} p99={p99:.1f} "
          f"err_rate={err:.4f} requests={n_total} workers={workers} FW_VAR={verdict}")

    if write_db and a.get("dirResultsDbURL"):
        write_summary(a["dirResultsDbURL"],
                      dict(workers=workers, requests=n_total, rps=rps, p50=p50, p95=p95, p99=p99,
                           err_rate=err, n5xx=n5xx, nconn=nconn, verdict=verdict))


if __name__ == "__main__":
    main()
