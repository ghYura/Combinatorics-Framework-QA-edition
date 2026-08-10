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

"""run_sweep.py — full 288 "end-to-last-end" sweep driver: synth -> structural oracle -> cheap proxy
-> PRE-TRAIN on a fixed shared corpus -> fp & int8 held-out quality, for every architecture.

Robust by design (weak PC, long unattended run):
  * per-candidate hard cap via SIGALRM (default 110s < the 2-min ceiling) -> hangs become TIMEOUT;
  * results written incrementally to sweep_out/results.jsonl  -> RESUMABLE (skips done idx);
  * heartbeat sweep_out/heartbeat.json (ts/done/total/current) -> cheap stale detection;
  * one-shot `--status` reads heartbeat+results and flags STALE without re-running anything.

Usage:
  python3 run_sweep.py --fresh           # start the full 288 sweep (run in background)
  python3 run_sweep.py --status          # cheap progress + stale check (for pinging)
  python3 run_sweep.py --limit N         # only first N candidates (smoke)
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import signal
import time

import mix_arch as M

NORM = ["rmsnorm", "layernorm"]
TOKENMIX = ["lin_cumsum", "lin_fused_qkvg", "lin_decay"]
CHANMIX = ["dense", "moe_top2", "moe_shared_top1"]
NORMPOS = ["pre", "post"]
MEDUSA = ["separate", "vectorized"]
OPTIONALS = ["jitter", "convq"]

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "sweep_out")
RESULTS = os.path.join(OUT, "results.jsonl")
HEART = os.path.join(OUT, "heartbeat.json")
SUMMARY = os.path.join(OUT, "summary.json")
STALE_AFTER = 240  # seconds since last heartbeat update while not done -> consider stuck


class SweepTimeout(BaseException):
    """Raised by SIGALRM; a BaseException so candidate-level `except Exception` cannot swallow it."""


def _alarm(_sig, _frm):
    raise SweepTimeout()


def all_candidates():
    grid = list(itertools.product(NORM, TOKENMIX, CHANMIX, NORMPOS, MEDUSA))
    opt_subsets = []
    for r in range(len(OPTIONALS) + 1):
        opt_subsets += [list(c) for c in itertools.combinations(OPTIONALS, r)]
    out = []
    for cell in grid:
        for opts in opt_subsets:
            out.append((*cell, opts))
    return out


def make_geno(norm, tok, chan, pos, med, opts):
    return M.default_geno(norm=norm, token_mixer=tok, channel_mixer=chan, normpos=pos, medusa=med,
                          conv_q=("convq" in opts), router_jitter=(0.02 if "jitter" in opts else 0.0),
                          load_balance=(chan != "dense"))


def label(i, c):
    n, t, ch, p, me, o = c
    return "%03d norm=%s tok=%s chan=%s pos=%s med=%s opt=%s" % (
        i, n, t, ch, p, me, ("+".join(o) if o else "none"))


def _rank(vals):
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    r = [0] * len(vals)
    for pos, i in enumerate(order):
        r[i] = pos
    return r


def spearman(xs, ys):
    n = len(xs)
    if n < 3:
        return 0.0
    rx, ry = _rank(xs), _rank(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx) ** 0.5
    vy = sum((b - my) ** 2 for b in ry) ** 0.5
    return round(cov / (vx * vy), 3) if vx > 0 and vy > 0 else 0.0


def status():
    if not os.path.exists(HEART):
        print("STATUS: no heartbeat yet (sweep not started).")
        return 3
    hb = json.load(open(HEART))
    age = time.time() - hb["ts"]
    done, total = hb["done"], hb["total"]
    finished = done >= total
    stale = (age > STALE_AFTER) and not finished
    tag = "*** STALE/STUCK ***" if stale else ("DONE" if finished else "running")
    print("STATUS: %d/%d (%.0f%%)  last_update=%.0fs ago  elapsed=%.0fs  current=[%s]  %s"
          % (done, total, 100 * done / max(1, total), age, hb.get("elapsed", 0), hb.get("current", "?"), tag))
    return 2 if stale else (0 if finished else 1)


def _hb(done, total, current, t_start):
    json.dump({"ts": time.time(), "done": done, "total": total, "current": current,
               "elapsed": round(time.time() - t_start, 1)}, open(HEART, "w"))


def summarize(total):
    rows = [json.loads(l) for l in open(RESULTS)] if os.path.exists(RESULTS) else []
    hist = {}
    for r in rows:
        hist[r.get("code", -1)] = hist.get(r.get("code", -1), 0) + 1
    valid = [r for r in rows if r.get("code") == 0]
    print("=" * 104)
    print("SWEEP SUMMARY — %d/%d candidates recorded ; fully valid (FW_VAR=0)=%d ; timeouts=%d"
          % (len(rows), total, len(valid), hist.get(10, 0)))
    print("  verdict histogram: " + "  ".join("code%d:%d" % (c, n) for c, n in sorted(hist.items())))

    def axis_means(key, vals):
        line = []
        for v in vals:
            sub = [r for r in valid if r.get(key) == v]
            if sub:
                line.append("%s(int8_acc=%.3f final_ce=%.3f gain=%+.3f train_s=%.1f n=%d)" % (
                    v, sum(x["int8_acc"] for x in sub) / len(sub),
                    sum(x["final_ce"] for x in sub) / len(sub),
                    sum(x["quality_gain"] for x in sub) / len(sub),
                    sum(x["train_s"] for x in sub) / len(sub), len(sub)))
        print("  %-13s: %s" % (key, "  ".join(line)))

    print("  per-axis means over valid (deployed int8_acc / final fp CE / quality_gain / train_s):")
    for key, vals in (("tok", TOKENMIX), ("chan", CHANMIX), ("norm", NORM), ("pos", NORMPOS), ("med", MEDUSA), ("opt", None)):
        if key == "opt":
            axis_means("opt", sorted({r["opt"] for r in valid}))
        else:
            axis_means(key, vals)

    if valid:
        print("  uniform_ce baseline = %.3f  (lower CE / higher acc = better quality)" % valid[0]["uniform_ce"])
        top = sorted(valid, key=lambda r: r["int8_ce"])[:10]
        print("  TOP 10 by DEPLOYED (int8) quality:")
        for r in top:
            print("    int8_ppl=%6.2f int8_acc=%.3f fp_ce=%.3f qgap=%+.3f params=%d lat=%.2fms | tok=%s chan=%s norm=%s pos=%s med=%s opt=%s"
                  % (r["int8_ppl"], r["int8_acc"], r["final_ce"], r["quant_gap"], r["params"], r["latency_ms"],
                     r["tok"], r["chan"], r["norm"], r["pos"], r["med"], r["opt"]))

        # do the cheap proxies predict trained quality?  (Spearman over valid candidates)
        q = [-r["int8_ce"] for r in valid]                  # higher = better quality
        print("  PROXY vs TRAINED-QUALITY rank-correlation (Spearman, n=%d):" % len(valid))
        print("    proxy_gradnorm -> quality : %+0.3f   (cheap NAS proxy predictiveness)" % spearman([r["proxy_gradnorm"] for r in valid], q))
        print("    params         -> quality : %+0.3f   (does bigger help?)" % spearman([r["params"] for r in valid], q))
        print("    latency_ms     -> quality : %+0.3f" % spearman([r["latency_ms"] for r in valid], q))

        # Pareto front: deployed quality vs size vs speed
        def dominates(a, b):
            ge = (a["int8_ce"] <= b["int8_ce"] and a["params"] <= b["params"] and a["latency_ms"] <= b["latency_ms"])
            gt = (a["int8_ce"] < b["int8_ce"] or a["params"] < b["params"] or a["latency_ms"] < b["latency_ms"])
            return ge and gt
        front = [r for r in valid if not any(dominates(o, r) for o in valid if o is not r)]
        print("  PARETO FRONT (int8_ce:min x params:min x latency_ms:min) — %d non-dominated:" % len(front))
        for r in sorted(front, key=lambda r: (r["int8_ce"])):
            print("    * int8_ppl=%6.2f int8_acc=%.3f params=%d lat=%.2fms | tok=%s chan=%s norm=%s pos=%s med=%s opt=%s"
                  % (r["int8_ppl"], r["int8_acc"], r["params"], r["latency_ms"],
                     r["tok"], r["chan"], r["norm"], r["pos"], r["med"], r["opt"]))
        best = min(valid, key=lambda r: r["int8_ce"])
        json.dump({"recorded": len(rows), "valid": len(valid), "hist": hist,
                   "best_deployed": best, "pareto": front}, open(SUMMARY, "w"), indent=1)
        print("  BEST DEPLOYED MODEL: tok=%s chan=%s norm=%s pos=%s med=%s opt=%s -> int8_ppl=%.2f int8_acc=%.3f"
              % (best["tok"], best["chan"], best["norm"], best["pos"], best["med"], best["opt"],
                 best["int8_ppl"], best["int8_acc"]))
    print("=" * 104)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--steps", type=int, default=120)
    ap.add_argument("--cap", type=int, default=110)
    ap.add_argument("--fresh", action="store_true")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    if a.status:
        return status()
    if a.fresh:
        for f in (RESULTS, HEART, SUMMARY):
            if os.path.exists(f):
                os.remove(f)

    boot = M.bootstrap(threads=4, compile_kernel=True)
    print("FW_RunMeFirstOnce[BOOTSTRAP] kernel_backend=%s smoke_code=%d" % (boot["kernel_backend"], boot["smoke_code"]), flush=True)
    data = M.make_dataset(steps=a.steps)
    print("DATA fixed corpus: uniform_ce=%.3f train_windows=%d heldout_windows=%d steps=%d cap=%ds"
          % (data["uniform_ce"], data["xtr"].size(0), data["xho"].size(0), a.steps, a.cap), flush=True)

    cands = all_candidates()
    if a.limit:
        cands = cands[:a.limit]
    done = set()
    if os.path.exists(RESULTS):
        for line in open(RESULTS):
            try:
                done.add(json.loads(line)["idx"])
            except Exception:  # noqa: BLE001
                pass
    print("PLAN: %d candidates (%d already done -> resuming)" % (len(cands), len(done)), flush=True)

    signal.signal(signal.SIGALRM, _alarm)
    t_start = time.time()
    with open(RESULTS, "a") as rf:
        for i, c in enumerate(cands):
            if i in done:
                continue
            lab = label(i, c)
            _hb(len(done), len(cands), lab, t_start)
            geno = make_geno(*c)
            ts = time.time()
            signal.alarm(a.cap)
            try:
                met = M.evaluate_full(geno, data)
            except SweepTimeout:
                met = {"code": 10, "err": "TIMEOUT_%ds" % a.cap, "train_s": round(time.time() - ts, 2)}
            except BaseException as exc:  # noqa: BLE001 - never let one candidate kill the sweep
                met = {"code": 9, "err": (type(exc).__name__ + ":" + str(exc)[:60]).replace(" ", "_"),
                       "train_s": round(time.time() - ts, 2)}
            finally:
                signal.alarm(0)
            n, t, ch, p, me, o = c
            rec = {"idx": i, "norm": n, "tok": t, "chan": ch, "pos": p, "med": me,
                   "opt": ("+".join(o) if o else "none"), "fw_var": (0 if met.get("code") == 0 else 1), **met}
            rf.write(json.dumps(rec) + "\n"); rf.flush()
            done.add(i)
            _hb(len(done), len(cands), lab, t_start)
            print("[%3d/%3d] %s -> code=%d(%s) int8_ppl=%s int8_acc=%s gain=%s qgap=%s lat=%sms train_s=%s"
                  % (len(done), len(cands), lab, met.get("code", -1), met.get("err", "?"),
                     met.get("int8_ppl", "-"), met.get("int8_acc", "-"), met.get("quality_gain", "-"),
                     met.get("quant_gap", "-"), met.get("latency_ms", "-"), met.get("train_s", "-")), flush=True)

    summarize(len(cands))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
