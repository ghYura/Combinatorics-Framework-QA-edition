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

"""_selfcheck — run the architecture-mix synthesis WITHOUT the Postgres/Java pipeline.

It enumerates exactly the combinatorial space the Bundle spec (arch_mix/arch_mix.toml) declares and
executes the same HEAD -> slots -> TAIL flow for every candidate, so the candidate logic is proven
independently of the DB transport (the methodology the prior llm_arch_search used). Structure:

  FW_RunMeFirstOnce  -> mix_arch.bootstrap()  (compile kernel once, seed, one smoke)   [run-level]
  HEAD               -> MetricsBook init       (counters + Pareto tracker)              [per run]
  FW_Combi(1) axes   -> one variant chosen per axis                                     [per candidate]
  FW_Optional        -> jitter / conv_q present (+) absent                              [per candidate]
  TAIL               -> evaluate() -> FW_VAR + a printed metric line                    [per candidate]
  TAIL (run)         -> aggregate, per-axis effect, Pareto front, recommended pick      [per run]

Weak-PC default: 72-cell mandatory grid + a 3-cell FW_Optional ablation (~25 s on this host).
  --full   run the true mandatory x 2^optional product (288)
  --limit N  cap the number of candidates
"""
from __future__ import annotations

import argparse
import itertools
import time

import mix_arch as M

# ---- the axes (single source of truth; arch_mix.toml mirrors these) ----
NORM = ["rmsnorm", "layernorm"]
TOKENMIX = ["lin_cumsum", "lin_fused_qkvg", "lin_decay"]
CHANMIX = ["dense", "moe_top2", "moe_shared_top1"]
NORMPOS = ["pre", "post"]
MEDUSA = ["separate", "vectorized"]
OPTIONALS = ["jitter", "convq"]          # FW_Optional sudden actions (present (+) absent)

GOALS = [("params", "min"), ("latency_ms", "min"), ("proxy_gradnorm", "max")]
CODE_MSG = {
    0: "valid/runnable/trainable", 1: "wrong shape", 2: "non-finite", 3: "untrainable grad",
    4: "causal leak", 5: "non-deterministic", 6: "no loss reduction", 7: "recurrence inexact",
    8: "incompatible genotype (sieve)", 9: "crash",
}
SEQ, BATCH = 10, 2


def make_geno(norm, tok, chan, pos, med, opts):
    return M.default_geno(
        norm=norm, token_mixer=tok, channel_mixer=chan, normpos=pos, medusa=med,
        conv_q=("convq" in opts), router_jitter=(0.02 if "jitter" in opts else 0.0),
        load_balance=(chan != "dense"),
    )


def desc(norm, tok, chan, pos, med, opts):
    return "norm=%s tok=%s chan=%s pos=%s med=%s opt=%s" % (
        norm, tok, chan, pos, med, ("+".join(opts) if opts else "none"))


def candidates(full: bool):
    grid = list(itertools.product(NORM, TOKENMIX, CHANMIX, NORMPOS, MEDUSA))
    if full:                                                    # true mandatory x 2^optional product
        opt_subsets = []
        for r in range(len(OPTIONALS) + 1):
            opt_subsets += [list(c) for c in itertools.combinations(OPTIONALS, r)]
        for cell in grid:
            for opts in opt_subsets:
                yield (*cell, opts)
        return
    for cell in grid:                                          # weak-PC: mandatory grid, optionals off
        yield (*cell, [])
    base = ("rmsnorm", "lin_fused_qkvg", "moe_shared_top1", "pre", "vectorized")  # FW_Optional ablation
    for opts in (["jitter"], ["convq"], ["jitter", "convq"]):
        yield (*base, opts)


class MetricsBook:
    """HEAD: metrics initialization — counters across correctness/trainability/efficiency axes."""
    def __init__(self):
        self.rows = []
        self.code_hist = {}
        self.valid = 0
        self.total = 0

    def add(self, d, met):
        self.total += 1
        self.code_hist[met["code"]] = self.code_hist.get(met["code"], 0) + 1
        if met["code"] == 0:
            self.valid += 1
        self.rows.append((d, met))

    def pareto(self):
        valid = [(d, m) for (d, m) in self.rows if m["code"] == 0]

        def dominates(a, b):
            better = False
            for key, direction in GOALS:
                av, bv = a[key], b[key]
                if direction == "min":
                    if av > bv:
                        return False
                    if av < bv:
                        better = True
                else:
                    if av < bv:
                        return False
                    if av > bv:
                        better = True
            return better

        front = []
        for d, m in valid:
            if not any(dominates(o, m) for _, o in valid if o is not m):
                front.append((d, m))
        return front


def axis_effect(rows, axis_key, values):
    """Mean trainability/latency/params per variant of one axis (valid candidates only)."""
    out = {}
    for v in values:
        sub = [m for (d, m) in rows if m["code"] == 0 and d[axis_key] == v]
        if sub:
            out[v] = (
                sum(x["loss_improvement"] for x in sub) / len(sub),
                sum(x["latency_ms"] for x in sub) / len(sub),
                sum(x["params"] for x in sub) / len(sub),
                len(sub),
            )
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="run the true mandatory x 2^optional product (288)")
    ap.add_argument("--limit", type=int, default=0, help="cap number of candidates")
    ap.add_argument("--no-kernel", action="store_true", help="skip the one-time C++ kernel compile in bootstrap")
    args = ap.parse_args()

    # ---------- FW_RunMeFirstOnce : bootstrap (one-time, run-level) ----------
    print("=" * 96)
    print("FW_RunMeFirstOnce  [BOOTSTRAP]")
    boot = M.bootstrap(threads=4, compile_kernel=not args.no_kernel)
    print("  torch=%s threads=%s kernel_backend=%s smoke_code=%d smoke_loss_improvement=%.5f"
          % (boot["torch"], boot["threads"], boot["kernel_backend"],
             boot["smoke_code"], boot["smoke_loss_improvement"]))

    # ---------- HEAD : metrics initialization ----------
    book = MetricsBook()
    declared = len(NORM) * len(TOKENMIX) * len(CHANMIX) * len(NORMPOS) * len(MEDUSA) * (2 ** len(OPTIONALS))
    cand = list(candidates(args.full))
    if args.limit:
        cand = cand[:args.limit]
    print("HEAD  [METRICS INIT]")
    print("  Bundle space (declared) = 2*3*3*2*2 mandatory x 2^2 optional = %d candidates" % declared)
    print("  this run = %d candidates  (goals: %s)  tiny model: vocab=%d d_model=%d L=%d seq=%d batch=%d"
          % (len(cand), ", ".join("%s:%s" % g for g in GOALS),
             M.default_geno()["vocab"], M.default_geno()["d_model"], M.default_geno()["n_layers"], SEQ, BATCH))
    print("=" * 96)

    t0 = time.perf_counter()
    for norm, tok, chan, pos, med, opts in cand:
        geno = make_geno(norm, tok, chan, pos, med, opts)
        met = M.evaluate(geno, batch=BATCH, seq=SEQ)
        fw_var = 0 if met["code"] == 0 else 1
        d = dict(norm=norm, token_mixer=tok, channel_mixer=chan, normpos=pos, medusa=med,
                 opt=("+".join(opts) if opts else "none"))
        book.add(d, met)
        # ---------- TAIL : metrics gathering + stdout ----------
        print("[%-58s] params=%-6d lat=%6.2fms tok/s=%-8.1f loss_impr=%+.5f gradnorm=%7.3f "
              "recurΔ=%.1e det=%d causal=%d/%d int8=%d aux=%.3f code=%d(%s) FW_VAR=%d"
              % (desc(norm, tok, chan, pos, med, opts), met["params"], met["latency_ms"],
                 met["tokens_per_s"], met["loss_improvement"], met["proxy_gradnorm"],
                 max(met["recur_delta"], 0.0), met["deterministic_ok"], met["causal_ok"],
                 met["causal_checks"], met["int8_ok"], met["aux"], met["code"],
                 CODE_MSG.get(met["code"], "?"), fw_var))
    elapsed = time.perf_counter() - t0

    # ---------- TAIL (run-level) : aggregate + Pareto front ----------
    print("=" * 96)
    print("TAIL  [RUN SUMMARY]   %d candidates in %.1fs (%.0f ms/candidate)"
          % (book.total, elapsed, 1000 * elapsed / max(1, book.total)))
    print("  valid (FW_VAR=0): %d/%d  (%.1f%%)" % (book.valid, book.total, 100.0 * book.valid / max(1, book.total)))
    print("  verdict histogram: " + "  ".join(
        "code%d:%d(%s)" % (c, n, CODE_MSG.get(c, "?")) for c, n in sorted(book.code_hist.items())))

    print("  per-axis mean over valid candidates  (loss_improvement / latency_ms / params):")
    for key, vals in (("token_mixer", TOKENMIX), ("channel_mixer", CHANMIX),
                      ("norm", NORM), ("normpos", NORMPOS), ("medusa", MEDUSA)):
        eff = axis_effect(book.rows, key, vals)
        cells = ["%s(loss_impr=%+.4f lat=%.2f p=%d n=%d)" % (v, a, b, int(c), n)
                 for v, (a, b, c, n) in eff.items()]
        print("    %-14s: %s" % (key, "  ".join(cells)))

    front = book.pareto()
    print("  PARETO FRONT (params:min x latency_ms:min x proxy_gradnorm:max) — %d non-dominated:" % len(front))
    for d, m in sorted(front, key=lambda r: (r[1]["params"], r[1]["latency_ms"])):
        print("    * params=%-6d lat=%6.2fms gradnorm=%7.3f loss_impr=%+.5f | %s opt=%s"
              % (m["params"], m["latency_ms"], m["proxy_gradnorm"], m["loss_improvement"],
                 "norm=%s tok=%s chan=%s pos=%s med=%s" % (d["norm"], d["token_mixer"],
                  d["channel_mixer"], d["normpos"], d["medusa"]), d["opt"]))

    valid_rows = [(d, m) for (d, m) in book.rows if m["code"] == 0]
    if valid_rows:
        rec = max(valid_rows, key=lambda r: r[1]["loss_improvement"] / max(r[1]["latency_ms"], 1e-6))
        d, m = rec
        print("  RECOMMENDED (best trainability-per-latency): %s opt=%s "
              "[params=%d lat=%.2fms loss_impr=%+.5f recurΔ=%.1e]"
              % ("norm=%s tok=%s chan=%s pos=%s med=%s" % (d["norm"], d["token_mixer"],
                 d["channel_mixer"], d["normpos"], d["medusa"]), d["opt"],
                 m["params"], m["latency_ms"], m["loss_improvement"], max(m["recur_delta"], 0.0)))
    # FRAMEWORK integrity != architecture quality. Soft verdicts (code 4/5/6) are legitimate oracle
    # findings about a mix; only crashes (9), unexpected sieve hits (8), or a recurrence-cache drift
    # (recur_ok==0) would mean the synthesis machinery itself is broken.
    crashes = book.code_hist.get(9, 0)
    sieve = book.code_hist.get(8, 0)
    recur_broken = sum(1 for _, m in book.rows if m["recur_ok"] == 0)
    framework_ok = (crashes == 0 and sieve == 0 and recur_broken == 0)
    print("=" * 96)
    print("FRAMEWORK INTEGRITY: %s  (crashes=%d, sieve-surprises=%d, recurrence-drift=%d)"
          % ("PASSED" if framework_ok else "FAILED", crashes, sieve, recur_broken))
    print("  architectures fully valid (FW_VAR=0): %d/%d ; oracle-flagged (marginal mixes): %d"
          % (book.valid, book.total, book.total - book.valid))
    return 0 if framework_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
