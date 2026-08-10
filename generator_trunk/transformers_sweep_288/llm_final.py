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

"""llm_final — SERIOUS, SEQUENTIAL end-to-final-end LLM test of every candidate architecture.

Per the operator: candidates run as a SEQUENTIAL QUEUE (one at a time), but each candidate uses ALL
CPU cores (torch threads = nproc) so the box runs ~100% — the earlier 50% was 4 threads on a toy that
could not saturate. Each candidate is a REAL two-phase LLM:

  1. BASE TEACHING (pretrain) on a broad K=4-mode synthetic corpus  -> base_acc / base_ppl
  2. FINE-TUNE (continue, lower lr) on a 2-mode specialization       -> ft_acc / ft_ppl / ft_gain
     + CATASTROPHIC-FORGETTING probe: re-measure the held-out (non-fine-tuned) modes {2,3}
       -> forgetting / base_retention  (a real LLM quality concern)

Then the full real-quality battery on the DEPLOYED int8 model: acc_vs_oracle, ppl, top5, ECE, entropy,
Medusa T+2/T+3 -> spec_tokens, quant_kl/quant_gap, and FX-8320 cost (params/active_kb/cold_ffn_kb).
ALL metrics are emitted to llm_out/corpus.kv and analyzed through Analyzer_trunk/AnalyzeKv (NSGA-II
Pareto + Welford stats + balanced optima + provenance) over declared GOALS.

Dedicated data is fixed & shared across every candidate (fair comparison). Run:
  python3 llm_final.py            # 18-cell balanced subset (tok x chan x normpos)
  python3 llm_final.py --all      # full 288   --status   --cap S   --no-analyze   --fresh
"""
from __future__ import annotations

import argparse
import json
import math
import os
import signal
import time

import torch

import mix_arch as M
import final_probe as FP

VOCAB = 64
CONT_LO, CONT_C = 8, 40
NMODES_BASE = 4
FT_MODES = (0, 1)               # fine-tune specializes here; modes {2,3} measure forgetting
S = 24
PRE_STEPS, FT_STEPS = 130, 60
BATCH = 16
THREADS = min(8, os.cpu_count() or 4)
# "serious" model (saturates 8 threads, unlike the d_model=24 toy)
DIMS = dict(d_model=96, n_heads=4, d_ffn=192, n_layers=3, num_experts=3, vocab=VOCAB)

HERE = FP.HERE
OUT = os.path.join(HERE, "llm_out")
RESULTS = os.path.join(OUT, "results.jsonl")
HEART = os.path.join(OUT, "heartbeat.json")
CORPUS = os.path.join(OUT, "corpus.kv")
ANALYZER = FP.ANALYZER
GOALS = ("ft_acc_vs_oracle:max,base_ppl:min,ece:min,forgetting:min,quant_kl:min,"
         "spec_tokens:max,cold_ffn_kb:min,params:min")
_D = {}


class SweepTimeout(BaseException):
    pass


class _stop(Exception):
    pass


def _alarm(_s, _f):
    raise SweepTimeout()


# ------------------------------------------------------------------ dedicated LLM-quality data
def _mats(seed, nm):
    return [torch.softmax(torch.randn(CONT_C, CONT_C, generator=torch.Generator().manual_seed(seed + i)) / 0.35, -1)
            for i in range(nm)]


def _gen(n_blocks, s, mats, seed):
    g = torch.Generator().manual_seed(seed)
    rows, modes = [], []
    nm = len(mats)
    for b in range(n_blocks):
        m = b % nm
        c = int(torch.randint(0, CONT_C, (1,), generator=g))
        content = [m]
        for _ in range(s - 1):
            c = int(torch.multinomial(mats[m][c], 1, generator=g))
            content.append(CONT_LO + c)
        content += [CONT_LO] * 4
        rows.append(content); modes.append(m)
    t = torch.tensor(rows, dtype=torch.long)
    x, yw = t[:, :s], t[:, 1:s + 4]
    cmask = torch.zeros(n_blocks, s, dtype=torch.bool)
    cmask[:, 1:s - 1] = True
    return x, yw, cmask, torch.tensor(modes)


def _oracle(x, modes, mats):
    ok = tot = 0
    for i in range(x.size(0)):
        mm = int(modes[i])
        for t in range(1, x.size(1) - 1):
            c = int(x[i, t]) - CONT_LO
            if 0 <= c < CONT_C:
                ok += int(int(mats[mm][c].argmax()) == int(x[i, t + 1]) - CONT_LO); tot += 1
    return round(ok / max(1, tot), 3)


def dataset(seed=4242):
    if "d" in _D:
        return _D["d"]
    mats = _mats(seed + 10, NMODES_BASE)
    ftmats = [mats[i] for i in FT_MODES]
    d = {"mats": mats}
    d["bx"], d["by"], d["bcmask"], d["bmodes"] = _gen(256, S, mats, seed + 1)        # base teaching (4 modes)
    d["bhx"], d["bhy"], d["bhcmask"], d["bhmodes"] = _gen(96, S, mats, seed + 2)     # base heldout (4 modes)
    d["fx"], d["fy"], d["fcmask"], d["fmodes"] = _gen(128, S, ftmats, seed + 3)      # fine-tune (modes 0,1)
    d["fhx"], d["fhy"], d["fhcmask"], d["fhmodes"] = _gen(64, S, ftmats, seed + 4)   # fine-tune heldout
    d["oracle_base"] = _oracle(d["bhx"], d["bhmodes"], mats)
    d["oracle_ft"] = _oracle(d["fhx"], d["fhmodes"], ftmats)
    _D["d"] = d
    return d


def _acc_modes(model, d, modeset):
    sel = torch.tensor([int(mm) in modeset for mm in d["bhmodes"].tolist()])
    if not bool(sel.any()):
        return 0.0
    return FP._acc(model, d["bhx"][sel], d["bhy"][sel], d["bhcmask"][sel])


# ------------------------------------------------------------------ build + two-phase evaluate
def make_geno(norm, tok, chan, pos, med, opts):
    return M.default_geno(norm=norm, token_mixer=tok, channel_mixer=chan, normpos=pos, medusa=med,
                          conv_q=("convq" in opts), router_jitter=(0.02 if "jitter" in opts else 0.0),
                          load_balance=(chan != "dense"), **DIMS)


def evaluate_llm(geno, d, seed=0):
    m = dict(code=0, err="none", params=0, active_kb=0.0, cold_ffn_kb=0.0, latency_ms=0.0,
             causal_ok=-1, deterministic_ok=-1, recur_ok=-1, recur_delta=-1.0,
             base_acc=0.0, base_ppl=0.0, ft_acc=0.0, ft_ppl=0.0, ft_acc_vs_oracle=0.0,
             ft_gain=0.0, forgetting=0.0, base_retention=0.0,
             acc_vs_oracle=0.0, ppl=0.0, top5=0.0, ece=1.0, entropy=0.0,
             medusa_t2=0.0, medusa_t3=0.0, spec_tokens=1.0,
             int8_acc=0.0, quant_gap=0.0, quant_kl=0.0, capability=0.0, train_s=0.0)
    t0 = time.perf_counter()
    try:
        torch.manual_seed(seed)
        model = M.build_model(geno)
        m["params"] = sum(p.numel() for p in model.parameters())
        m["active_kb"], m["cold_ffn_kb"] = FP._costs(geno)
        xb0 = d["bhx"][:8]
        model.eval()
        with torch.no_grad():
            ref = model(xb0)[0]
        if tuple(ref.shape) != (8, S, VOCAB) or not bool(torch.isfinite(ref).all()):
            m["code"], m["err"] = 1, "shape/finite"; raise _stop()
        with torch.no_grad():
            m["deterministic_ok"] = int(torch.equal(ref, model(xb0)[0]))
            ok, _ = M._causal_audit(model, xb0, ref, VOCAB, max_checks=3)
            m["causal_ok"] = int(ok)
            m["recur_delta"] = round(M._recurrence_delta(model, xb0), 9)
            m["recur_ok"] = int(m["recur_delta"] <= 5e-3)
            ts = time.perf_counter()
            for _ in range(3):
                model(xb0)
            m["latency_ms"] = round((time.perf_counter() - ts) * 1000.0 / 3, 3)
        if not (m["deterministic_ok"] and m["causal_ok"] and m["recur_ok"]):
            m["code"], m["err"] = (5 if not m["deterministic_ok"] else 4 if not m["causal_ok"] else 7), "structural"; raise _stop()

        # ---- Phase 1: BASE TEACHING (pretrain) ----
        torch.manual_seed(seed)
        model = M.build_model(geno)
        FP._train(model, d["bx"], d["by"], PRE_STEPS, lr=3e-3)
        bq, _, _ = FP._quality(model, d["bhx"], d["bhy"], d["bhcmask"])
        m["base_acc"], m["base_ppl"] = round(bq["acc"], 4), round(math.exp(min(bq["ce"], 20)), 3)
        other_pre = _acc_modes(model, d, {2, 3})
        ft_pre = _acc_modes(model, d, {0, 1})

        # ---- Phase 2: FINE-TUNE (modes 0,1, lower lr) + forgetting probe ----
        FP._train(model, d["fx"], d["fy"], FT_STEPS, lr=1e-3)
        fq, _, _ = FP._quality(model, d["fhx"], d["fhy"], d["fhcmask"])
        m["ft_acc"], m["ft_ppl"] = round(fq["acc"], 4), round(math.exp(min(fq["ce"], 20)), 3)
        m["ft_acc_vs_oracle"] = round(fq["acc"] / d["oracle_ft"], 4) if d["oracle_ft"] > 1e-6 else 0.0
        other_post = _acc_modes(model, d, {2, 3})
        m["forgetting"] = round(max(other_pre - other_post, 0.0), 4)
        m["base_retention"] = round(other_post / other_pre, 4) if other_pre > 1e-6 else 0.0
        m["ft_gain"] = round(fq["acc"] - ft_pre, 4)

        # ---- final general quality on the DEPLOYED model (base heldout, all modes) ----
        fb, fb_probs, _ = FP._quality(model, d["bhx"], d["bhy"], d["bhcmask"])
        m["acc_vs_oracle"] = round(fb["acc"] / d["oracle_base"], 4) if d["oracle_base"] > 1e-6 else 0.0
        m["ppl"], m["top5"], m["ece"], m["entropy"] = round(math.exp(min(fb["ce"], 20)), 3), round(fb["top5"], 4), round(fb["ece"], 4), round(fb["ent"], 4)
        m["medusa_t2"], m["medusa_t3"] = [round(a, 4) for a in FP._medusa(model, d["bhx"], d["bhy"], d["bhcmask"])]
        m["spec_tokens"] = round(1.0 + m["medusa_t2"] + m["medusa_t2"] * m["medusa_t3"], 4)

        model.eval(); model.export_for_inference()
        ib, ib_probs, _ = FP._quality(model, d["bhx"], d["bhy"], d["bhcmask"])
        m["int8_acc"] = round(ib["acc"], 4)
        m["quant_gap"] = round(fb["acc"] - ib["acc"], 4)
        m["quant_kl"] = round(float((fb_probs * (fb_probs.clamp_min(1e-9).log() - ib_probs.clamp_min(1e-9).log())).sum(-1).mean()), 6)
        m["capability"] = round(0.4 * m["ft_acc_vs_oracle"] + 0.2 * m["base_retention"]
                                + 0.2 * (1.0 - min(m["ece"], 1.0)) + 0.2 * min(m["spec_tokens"] - 1.0, 1.0), 4)
    except _stop:
        pass
    except M.GenotypeError as exc:
        m["code"], m["err"] = 8, str(exc)[:40]
    except Exception as exc:  # noqa: BLE001
        m["code"], m["err"] = 9, (type(exc).__name__ + ":" + str(exc)[:50]).replace(" ", "_")
    m["train_s"] = round(time.perf_counter() - t0, 2)
    return m


# ------------------------------------------------------------------ corpus + Analyzer
_KV = ["ft_acc_vs_oracle", "base_ppl", "ece", "forgetting", "quant_kl", "spec_tokens", "cold_ffn_kb",
       "params", "active_kb", "latency_ms", "base_acc", "ft_acc", "ft_gain", "base_retention",
       "acc_vs_oracle", "ppl", "top5", "entropy", "int8_acc", "quant_gap", "medusa_t2", "capability",
       "recur_ok", "causal_ok", "deterministic_ok"]


def write_corpus(rows):
    run_id = "llm288-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    n = 0
    with open(CORPUS, "w") as f:
        f.write("# llm_final — serious 2-phase LLM final-quality corpus for Analyzer_trunk/AnalyzeKv\n# goals: " + GOALS + "\n")
        for r in rows:
            if r.get("code") != 0:
                continue
            cid = "c%03d_%s_%s_%s_%s" % (r["idx"], r["tok"].replace("lin_", ""), r["chan"], r["pos"], r["med"])
            kv = ["candidate_id=" + cid, "run_id=" + run_id, "tok=" + r["tok"], "chan=" + r["chan"], "pos=" + r["pos"], "FW_VAR=0"]
            kv += ["%s=%s" % (k, r.get(k, 0)) for k in _KV]
            f.write(" ".join(kv) + "\n"); n += 1
    return run_id, n


def run_analyzer(n, topk=12):
    cls = os.path.join(ANALYZER, "target/analyzekv/AnalyzeKv.class")
    if not (os.path.exists(cls) and os.path.exists(os.path.join(ANALYZER, "analyzer_cp.txt"))):
        print("ANALYZER: not built — corpus.kv ready; run AnalyzeKv manually with GOALS=" + GOALS)
        return -1
    import subprocess
    cp = '%s/target/analyzekv:%s/target/classes:$(cat %s/analyzer_cp.txt)' % (ANALYZER, ANALYZER, ANALYZER)
    cmd = ('java -cp "%s" AnalyzeKv "%s" %d "%s" --mode formal --corpus-count %d --provenance-out "%s"'
           % (cp, CORPUS, topk, GOALS, n, os.path.join(OUT, "provenance.json")))
    print("=" * 100 + "\nANALYZER_TRUNK (AnalyzeKv, FORMAL):\n  " + cmd)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    print(r.stdout)
    if r.returncode != 0:
        print("ANALYZER stderr:\n" + r.stderr[-1500:])
    return r.returncode


# ------------------------------------------------------------------ sequential driver
def status():
    if not os.path.exists(HEART):
        print("STATUS: no heartbeat yet."); return
    hb = json.load(open(HEART)); age = time.time() - hb["ts"]
    done, total = hb["done"], hb["total"]
    fin = done >= total
    print("STATUS: %d/%d (%.0f%%)  last_update=%.0fs ago  elapsed=%.0fs  %s"
          % (done, total, 100 * done / max(1, total), age, hb.get("elapsed", 0),
             "*** STALE ***" if (age > 360 and not fin) else ("DONE" if fin else "running")))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--cap", type=int, default=150)
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--no-analyze", action="store_true")
    ap.add_argument("--topk", type=int, default=12)
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    if a.status:
        status(); return 0
    if a.fresh and os.path.exists(RESULTS):
        os.remove(RESULTS)

    torch.manual_seed(0)
    torch.set_num_threads(THREADS)
    print("FW_RunMeFirstOnce[BOOTSTRAP] threads=%d (all cores -> ~100%% CPU) model=%s seq=%d pre=%d ft=%d"
          % (THREADS, DIMS, S, PRE_STEPS, FT_STEPS), flush=True)
    d = dataset()
    print("DATA base(4-mode teach): train=%d heldout=%d | finetune(2-mode): train=%d heldout=%d | oracle_base=%.3f oracle_ft=%.3f"
          % (d["bx"].size(0), d["bhx"].size(0), d["fx"].size(0), d["fhx"].size(0), d["oracle_base"], d["oracle_ft"]), flush=True)

    cands = FP.subset(a.all)
    if a.limit:
        cands = cands[:a.limit]
    done = set()
    if os.path.exists(RESULTS):
        for l in open(RESULTS):
            try:
                done.add(json.loads(l)["idx"])
            except Exception:
                pass
    print("PLAN: %d candidates SEQUENTIAL queue, cap=%ds (%d done -> resume)" % (len(cands), a.cap, len(done)), flush=True)

    signal.signal(signal.SIGALRM, _alarm)
    t_start = time.time()
    with open(RESULTS, "a") as rf:
        for i, c in enumerate(cands):
            if i in done:
                continue
            json.dump({"ts": time.time(), "done": len(done), "total": len(cands), "elapsed": round(time.time() - t_start, 1)}, open(HEART, "w"))
            ts = time.time()
            signal.alarm(a.cap)
            try:
                met = evaluate_llm(make_geno(*c), d)
            except SweepTimeout:
                met = {"code": 10, "err": "TIMEOUT_%ds" % a.cap, "train_s": round(time.time() - ts, 2)}
            except BaseException as e:  # noqa: BLE001
                met = {"code": 9, "err": (type(e).__name__ + ":" + str(e)[:40]).replace(" ", "_"), "train_s": round(time.time() - ts, 2)}
            finally:
                signal.alarm(0)
            n, t, ch, p, me, o = c
            rec = {"idx": i, "norm": n, "tok": t, "chan": ch, "pos": p, "med": me, "opt": ("+".join(o) if o else "none"), **met}
            rf.write(json.dumps(rec) + "\n"); rf.flush()
            done.add(i)
            json.dump({"ts": time.time(), "done": len(done), "total": len(cands), "elapsed": round(time.time() - t_start, 1)}, open(HEART, "w"))
            print("[%3d/%3d] %-14s %-15s %-4s | base=%.3f ft=%.3f ft_oracle=%.3f gain=%+.3f forget=%.3f | acc/or=%.3f ppl=%.1f ece=%.3f spec=%.3f int8=%.3f kl=%.4f CAP=%.3f code=%d %s t=%.1fs"
                  % (len(done), len(cands), t, ch, p, met.get("base_acc", 0), met.get("ft_acc", 0),
                     met.get("ft_acc_vs_oracle", 0), met.get("ft_gain", 0), met.get("forgetting", 0),
                     met.get("acc_vs_oracle", 0), met.get("ppl", 0), met.get("ece", 0), met.get("spec_tokens", 0),
                     met.get("int8_acc", 0), met.get("quant_kl", 0), met.get("capability", 0),
                     met.get("code", -1), met.get("err", "?"), met.get("train_s", 0)), flush=True)

    json.dump({"ts": time.time(), "done": len(done), "total": len(cands), "elapsed": round(time.time() - t_start, 1)}, open(HEART, "w"))
    allrows = [json.loads(l) for l in open(RESULTS)]
    run_id, nvalid = write_corpus(allrows)
    print("Wrote %d valid candidate K=V line(s) -> %s (run_id=%s)" % (nvalid, CORPUS, run_id), flush=True)
    if nvalid and not a.no_analyze:
        run_analyzer(nvalid, a.topk)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
