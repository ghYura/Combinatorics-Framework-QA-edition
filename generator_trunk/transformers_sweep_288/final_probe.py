#!/usr/bin/env python3
"""final_probe — the "end to final end" battery: discriminative data + capability checks.

The order-2 Markov sweep (run_sweep.py) was a falsifier: every architecture tied, so it could not
*choose*. This module uses one minimal-but-sufficient task engineered so the axes that matter SEPARATE,
with capability-specific metrics wired in from the start, fp AND int8-deployed. Tiny for the FX-8320.

TASK = MODE-SWITCHED MARKOV MIXTURE. K modes, each a FIXED shared peaked order-1 source. Every block
starts with a mode token; the model must (a) carry that mode across the block and (b) apply that mode's
rule. Two pressures, two discriminators:
  * per-mode accuracy (mean / min / spread)  -> CHANMIX: an MoE can route to per-mode specialists;
    a dense FFN must cram all K conflicting rules into shared weights (lower min / wider spread).
  * LENGTH GENERALIZATION (train chain S, test longer S): the mode token sits ever further back, so a
    forgetting `decay` state fades it -> mode_acc_long drops -> TOKENMIX (decay vs cumsum/fused).
Plus Medusa T+2/T+3 accuracy (speculative quality) and int8-deployed versions + quant gaps.

Run:  python3 final_probe.py            # balanced 18-cell subset (tok x chan x normpos)
      python3 final_probe.py --all      # full 288 (slow)   --limit N   --cap SECONDS   --fresh
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import signal
import time

import torch

import mix_arch as M

VOCAB = 64
NMODES = 3                 # mode tokens 0..2  (= num_experts, so an MoE *can* dedicate one expert/mode)
CONT_LO, CONT_C = 8, 40    # content tokens 8..47
S_TRAIN, S_LONG = 20, 40   # chain lengths: train/heldout vs length-generalization heldout (2x)
STEPS, BATCH = 90, 16

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "final_out")
RESULTS = os.path.join(OUT, "results.jsonl")
HEART = os.path.join(OUT, "heartbeat.json")
CORPUS = os.path.join(OUT, "corpus.kv")
ANALYZER = os.environ.get("BUNDLE_ANALYZER_ROOT", os.path.abspath(os.path.join(HERE, "..", "..", "Analyzer_trunk")))
# Real-final-quality objectives handed to Analyzer_trunk/AnalyzeKv (FORMAL, declared-only Pareto):
GOALS = ("acc_vs_oracle:max,ppl:min,ece:min,quant_kl:min,spec_tokens:max,"
         "cold_ffn_kb:min,active_kb:min,params:min")

NORM = ["rmsnorm", "layernorm"]
TOKENMIX = ["lin_cumsum", "lin_fused_qkvg", "lin_decay"]
CHANMIX = ["dense", "moe_top2", "moe_shared_top1"]
NORMPOS = ["pre", "post"]
OPTIONALS = ["jitter", "convq"]
_CACHE = {}


class SweepTimeout(BaseException):
    pass


class _stop(Exception):
    pass


def _alarm(_s, _f):
    raise SweepTimeout()


# -------------------------------------------------------------------------------- data (shared, fixed)
def _mats(seed):
    g = torch.Generator().manual_seed(seed)
    return [torch.softmax(torch.randn(CONT_C, CONT_C, generator=g) / 0.35, dim=-1) for _ in range(NMODES)]


def make_mode(n_blocks, S, mats, seed):
    """Each block: [mode m] + an order-1 chain from the SHARED source mats[m]. +4 pad for medusa wide.
    Returns x[N,S], yw[N,S+3] (next-token wide), content_mask[N,S], mode_ids[N]."""
    g = torch.Generator().manual_seed(seed)
    rows, modes = [], []
    for b in range(n_blocks):
        m = b % NMODES
        c = int(torch.randint(0, CONT_C, (1,), generator=g))
        content = [m]
        for _ in range(S - 1):
            c = int(torch.multinomial(mats[m][c], 1, generator=g))
            content.append(CONT_LO + c)
        content += [CONT_LO] * 4                                   # pad (ignored by masks)
        rows.append(content); modes.append(m)
    t = torch.tensor(rows, dtype=torch.long)
    x, yw = t[:, :S], t[:, 1:S + 4]
    cmask = torch.zeros(n_blocks, S, dtype=torch.bool)
    cmask[:, 1:S - 1] = True                                       # predict next content token
    return x, yw, cmask, torch.tensor(modes)


def dataset(seed=2024):
    if "d" in _CACHE:
        return _CACHE["d"]
    mats = _mats(seed)                                             # ONE shared rule-set for train+test
    d = {"mats": mats}
    d["x"], d["y"], d["cmask"], d["modes"] = make_mode(256, S_TRAIN, mats, seed + 1)
    d["hx"], d["hy"], d["hcmask"], d["hmodes"] = make_mode(96, S_TRAIN, mats, seed + 2)
    d["lx"], d["ly"], d["lcmask"], d["lmodes"] = make_mode(96, S_LONG, mats, seed + 3)
    # oracle (argmax of the true row) accuracy gives the achievable ceiling for context
    d["oracle"] = _oracle_acc(d["hx"], d["hmodes"], mats)
    _CACHE["d"] = d
    return d


def _oracle_acc(x, modes, mats):
    ok = tot = 0
    for i in range(x.size(0)):
        m = int(modes[i])
        for t in range(1, x.size(1) - 1):
            c = int(x[i, t]) - CONT_LO
            if 0 <= c < CONT_C:
                pred = int(mats[m][c].argmax())
                ok += int(pred == int(x[i, t + 1]) - CONT_LO); tot += 1
    return round(ok / max(1, tot), 3)


# -------------------------------------------------------------------------------- train / eval
def _sched(n, steps, seed=777):
    g = torch.Generator().manual_seed(seed)
    perm = torch.randperm(n, generator=g)
    return [perm[[(s * BATCH + j) % n for j in range(BATCH)]] for s in range(steps)]


def _train(model, x, yw, steps, lr=3e-3):
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    model.train()
    sched = _sched(x.size(0), steps)
    for s in range(steps):
        sel = sched[s]
        loss, _ = M._objective(model, x[sel], yw[sel], VOCAB)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step()


@torch.no_grad()
def _acc(model, x, yw, mask, batch=96):
    model.eval()
    ok = tot = 0
    for i in range(0, x.size(0), batch):
        pred = model(x[i:i + batch])[0].argmax(-1)
        tgt = yw[i:i + batch, :x.size(1)]
        mb = mask[i:i + batch]
        ok += int(((pred == tgt) & mb).sum()); tot += int(mb.sum())
    return ok / max(1, tot)


@torch.no_grad()
def _per_mode(model, x, yw, cmask, modes):
    accs = []
    for m in range(NMODES):
        sel = (modes == m)
        if bool(sel.any()):
            accs.append(_acc(model, x[sel], yw[sel], cmask[sel]))
    return accs


@torch.no_grad()
def _medusa(model, x, yw, cmask, batch=96):
    model.eval()
    ok = [0, 0]; tot = [0, 0]
    S = x.size(1)
    for i in range(0, x.size(0), batch):
        _, med = model(x[i:i + batch])
        mb = cmask[i:i + batch]
        for h in (0, 1):
            pred = med[h].argmax(-1)
            tgt = yw[i:i + batch, h + 1:h + 1 + S]
            ok[h] += int(((pred == tgt) & mb).sum()); tot[h] += int(mb.sum())
    return ok[0] / max(1, tot[0]), ok[1] / max(1, tot[1])


def _costs(geno):
    """FX-8320 deployment cost proxies (int8 -> 1 byte/param): total weights read per token, and the
    COLD (input-dependent / routed) FFN bytes that thrash DDR3 — the bandwidth axis the toy missed."""
    d, dff, V, L = geno["d_model"], geno["d_ffn"], geno["vocab"], geno["n_layers"]
    attn, pffn = 5 * d * d, 2 * d * dff
    cm = geno["channel_mixer"]
    active_ffn = pffn if cm == "dense" else 2 * pffn               # dense:1 FFN ; top2 / shared+1:2 FFN
    cold_ffn = 0 if cm == "dense" else (2 * pffn if cm == "moe_top2" else pffn)  # routed (cold) reads
    heads = (d * d + d * 3 * V) if geno["medusa"] == "vectorized" else 3 * (d * d + d * V)
    active = L * (attn + active_ffn) + d * V + heads
    return round(active / 1024.0, 2), round(cold_ffn * L / 1024.0, 2)


@torch.no_grad()
def _quality(model, x, yw, cmask, batch=96):
    """Distributional quality at masked positions: CE, acc, top5, ECE(10-bin), entropy + the softmax
    probs (for the fp-vs-int8 KL). Returns (metrics, probs[Nmask,V], tgt[Nmask])."""
    model.eval()
    P, T = [], []
    for i in range(0, x.size(0), batch):
        logits = model(x[i:i + batch])[0]
        mb = cmask[i:i + batch]
        P.append(torch.softmax(logits[mb], -1))
        T.append(yw[i:i + batch, :x.size(1)][mb])
    probs, tgt = torch.cat(P), torch.cat(T)
    idx = torch.arange(probs.size(0))
    ce = float(-probs[idx, tgt].clamp_min(1e-9).log().mean())
    conf, pred = probs.max(-1)
    correct = (pred == tgt).float()
    top5 = float((probs.topk(5, -1).indices == tgt.unsqueeze(-1)).any(-1).float().mean())
    ece = 0.0
    for b in range(10):
        lo, hi = b / 10.0, (b + 1) / 10.0
        sel = (conf >= lo) & ((conf < hi) if b < 9 else (conf <= hi))
        if bool(sel.any()):
            ece += abs(float(correct[sel].mean()) - float(conf[sel].mean())) * float(sel.float().mean())
    ent = float((-(probs * probs.clamp_min(1e-9).log()).sum(-1)).mean())
    return dict(ce=ce, acc=float(correct.mean()), top5=top5, ece=ece, ent=ent), probs, tgt


def evaluate_final(geno, d, *, steps=STEPS, seed=0):
    m = dict(code=0, err="none", params=0, latency_ms=0.0, tokens_per_s=0.0,
             causal_ok=-1, deterministic_ok=-1, recur_ok=-1, recur_delta=-1.0,
             mode_acc=0.0, mode_min=0.0, mode_spread=0.0, mode_acc_long=0.0, len_ret=0.0,
             acc_vs_oracle=0.0, ppl=0.0, top5=0.0, ece=1.0, entropy=0.0,
             medusa_t2=0.0, medusa_t3=0.0, spec_tokens=1.0,
             int8_mode_acc=0.0, quant_gap=0.0, quant_kl=0.0,
             active_kb=0.0, cold_ffn_kb=0.0, oracle=d["oracle"], capability=0.0, train_s=0.0)
    t0 = time.perf_counter()
    try:
        torch.manual_seed(seed)
        model = M.build_model(geno)
        m["params"] = sum(p.numel() for p in model.parameters())
        m["active_kb"], m["cold_ffn_kb"] = _costs(geno)
        xb0 = d["hx"][:8]
        model.eval()
        with torch.no_grad():
            ref = model(xb0)[0]
        if tuple(ref.shape) != (8, S_TRAIN, VOCAB) or not bool(torch.isfinite(ref).all()):
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
            if m["latency_ms"] > 0:
                m["tokens_per_s"] = round(xb0.numel() * 1000.0 / m["latency_ms"], 1)
        if not (m["deterministic_ok"] and m["causal_ok"] and m["recur_ok"]):
            m["code"], m["err"] = (5 if not m["deterministic_ok"] else 4 if not m["causal_ok"] else 7), "structural"; raise _stop()

        torch.manual_seed(seed)
        model = M.build_model(geno)
        _train(model, d["x"], d["y"], steps)

        accs = _per_mode(model, d["hx"], d["hy"], d["hcmask"], d["hmodes"])
        m["mode_acc"], m["mode_min"], m["mode_spread"] = round(sum(accs) / len(accs), 4), round(min(accs), 4), round(max(accs) - min(accs), 4)
        m["mode_acc_long"] = round(_acc(model, d["lx"], d["ly"], d["lcmask"]), 4)
        m["len_ret"] = round(m["mode_acc_long"] / m["mode_acc"], 3) if m["mode_acc"] > 1e-6 else 0.0
        fp, fp_probs, _ = _quality(model, d["hx"], d["hy"], d["hcmask"])
        m["ppl"] = round(math.exp(min(fp["ce"], 20)), 3)
        m["top5"], m["ece"], m["entropy"] = round(fp["top5"], 4), round(fp["ece"], 4), round(fp["ent"], 4)
        m["acc_vs_oracle"] = round(fp["acc"] / d["oracle"], 4) if d["oracle"] > 1e-6 else 0.0
        m["medusa_t2"], m["medusa_t3"] = [round(a, 4) for a in _medusa(model, d["hx"], d["hy"], d["hcmask"])]
        m["spec_tokens"] = round(1.0 + m["medusa_t2"] + m["medusa_t2"] * m["medusa_t3"], 4)   # exp. accepted draft len

        model.eval(); model.export_for_inference()
        i8 = _per_mode(model, d["hx"], d["hy"], d["hcmask"], d["hmodes"])
        m["int8_mode_acc"] = round(sum(i8) / len(i8), 4)
        m["quant_gap"] = round(m["mode_acc"] - m["int8_mode_acc"], 4)
        _, i8_probs, _ = _quality(model, d["hx"], d["hy"], d["hcmask"])
        m["quant_kl"] = round(float((fp_probs * (fp_probs.clamp_min(1e-9).log() - i8_probs.clamp_min(1e-9).log())).sum(-1).mean()), 6)
        m["capability"] = round(0.45 * m["acc_vs_oracle"] + 0.20 * m["len_ret"]
                                + 0.20 * (1.0 - min(m["ece"], 1.0)) + 0.15 * min(m["spec_tokens"] - 1.0, 1.0), 4)
    except _stop:
        pass
    except M.GenotypeError as exc:
        m["code"], m["err"] = 8, str(exc)[:40]
    except Exception as exc:  # noqa: BLE001
        m["code"], m["err"] = 9, (type(exc).__name__ + ":" + str(exc)[:50]).replace(" ", "_")
    m["train_s"] = round(time.perf_counter() - t0, 2)
    return m


# -------------------------------------------------------------------------------- driver
def subset(all_cands):
    if all_cands:
        grid = list(itertools.product(NORM, TOKENMIX, CHANMIX, NORMPOS, ["separate", "vectorized"]))
        opt = [[]] + [[o] for o in OPTIONALS] + [list(OPTIONALS)]
        return [(*c, o) for c in grid for o in opt]
    return [("rmsnorm", t, c, p, "vectorized", []) for t in TOKENMIX for c in CHANMIX for p in NORMPOS]


def make_geno(norm, tok, chan, pos, med, opts):
    return M.default_geno(vocab=VOCAB, norm=norm, token_mixer=tok, channel_mixer=chan, normpos=pos,
                          medusa=med, conv_q=("convq" in opts),
                          router_jitter=(0.02 if "jitter" in opts else 0.0), load_balance=(chan != "dense"))


def status():
    if not os.path.exists(HEART):
        print("STATUS: no heartbeat yet (battery not started)."); return 3
    hb = json.load(open(HEART))
    age = time.time() - hb["ts"]
    done, total = hb["done"], hb["total"]
    finished = done >= total
    stale = age > 240 and not finished
    print("STATUS: %d/%d (%.0f%%)  last_update=%.0fs ago  elapsed=%.0fs  %s"
          % (done, total, 100 * done / max(1, total), age, hb.get("elapsed", 0),
             "*** STALE/STUCK ***" if stale else ("DONE" if finished else "running")))
    return 2 if stale else (0 if finished else 1)


_KV_KEYS = ["acc_vs_oracle", "ppl", "ece", "quant_kl", "spec_tokens", "cold_ffn_kb", "active_kb",
            "params", "latency_ms", "tokens_per_s", "top5", "entropy", "mode_acc", "mode_min",
            "len_ret", "quant_gap", "int8_mode_acc", "medusa_t2", "capability",
            "recur_ok", "causal_ok", "deterministic_ok"]


def write_corpus(rows):
    """Emit one K=V line per VALID candidate for Analyzer_trunk/AnalyzeKv (with candidate_id/run_id
    so the Analyzer's provenance report can trace each Pareto pick back to its source row)."""
    run_id = "tsweep288-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    n = 0
    with open(CORPUS, "w") as f:
        f.write("# transformers_sweep_288 — final-quality corpus for Analyzer_trunk/AnalyzeKv\n")
        f.write("# goals: " + GOALS + "\n")
        for r in rows:
            if r.get("code") != 0:
                continue
            cid = "c%03d_%s_%s_%s_%s" % (r["idx"], r["tok"].replace("lin_", ""), r["chan"], r["pos"], r["med"])
            kv = ["candidate_id=" + cid, "run_id=" + run_id, "tok=" + r["tok"], "chan=" + r["chan"],
                  "pos=" + r["pos"], "FW_VAR=0"]
            kv += ["%s=%s" % (k, r.get(k, 0)) for k in _KV_KEYS]
            f.write(" ".join(kv) + "\n")
            n += 1
    return run_id, n


def run_analyzer(n, topk=12):
    if not (os.path.exists(os.path.join(ANALYZER, "target/analyzekv/AnalyzeKv.class"))
            and os.path.exists(os.path.join(ANALYZER, "analyzer_cp.txt"))):
        print("ANALYZER: Analyzer_trunk not built (target/analyzekv/AnalyzeKv.class + analyzer_cp.txt) — skipped.")
        print("          corpus.kv is ready; analyze later with:")
        print('          java -cp "%s/target/analyzekv:%s/target/classes:$(cat %s/analyzer_cp.txt)" \\\n'
              '               AnalyzeKv "%s" %d "%s" --mode formal --corpus-count %d' % (ANALYZER, ANALYZER, ANALYZER, CORPUS, topk, GOALS, n))
        return -1
    import subprocess
    cp = '%s/target/analyzekv:%s/target/classes:$(cat %s/analyzer_cp.txt)' % (ANALYZER, ANALYZER, ANALYZER)
    cmd = ('java -cp "%s" AnalyzeKv "%s" %d "%s" --mode formal --corpus-count %d --provenance-out "%s"'
           % (cp, CORPUS, topk, GOALS, n, os.path.join(OUT, "provenance.json")))
    print("=" * 112 + "\nANALYZER_TRUNK (AnalyzeKv, FORMAL, NSGA-II Pareto over real-quality goals):\n  " + cmd)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    print(r.stdout)
    if r.returncode != 0:
        print("ANALYZER stderr:\n" + r.stderr[-2000:])
    return r.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--cap", type=int, default=90)
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--status", action="store_true", help="cheap progress + stale check (for pinging)")
    ap.add_argument("--no-analyze", action="store_true", help="skip the Analyzer_trunk (AnalyzeKv) pass")
    ap.add_argument("--topk", type=int, default=12)
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    if a.status:
        status()            # prints running/DONE/STALE in the text; always exit 0 (no scary error banner)
        return 0
    if a.fresh and os.path.exists(RESULTS):
        os.remove(RESULTS)

    boot = M.bootstrap(threads=4, compile_kernel=True)
    print("FW_RunMeFirstOnce[BOOTSTRAP] kernel=%s smoke=%d" % (boot["kernel_backend"], boot["smoke_code"]), flush=True)
    d = dataset()
    print("DATA mode-mixture: modes=%d content=%d train=%d heldout=%d long_S=%d | chance=%.3f oracle=%.3f"
          % (NMODES, CONT_C, d["x"].size(0), d["hx"].size(0), S_LONG, 1.0 / CONT_C, d["oracle"]), flush=True)
    cands = subset(a.all)
    if a.limit:
        cands = cands[:a.limit]
    done = set()
    if os.path.exists(RESULTS):
        for l in open(RESULTS):
            try:
                done.add(json.loads(l)["idx"])
            except Exception:
                pass
    print("PLAN: %d candidates cap=%ds (%d done -> resume)" % (len(cands), a.cap, len(done)), flush=True)

    signal.signal(signal.SIGALRM, _alarm)
    t_start = time.time()
    rows = []
    with open(RESULTS, "a") as rf:
        for i, c in enumerate(cands):
            if i in done:
                continue
            json.dump({"ts": time.time(), "done": len(done), "total": len(cands), "elapsed": round(time.time() - t_start, 1)}, open(HEART, "w"))
            ts = time.time()
            signal.alarm(a.cap)
            try:
                met = evaluate_final(make_geno(*c), d)
            except SweepTimeout:
                met = {"code": 10, "err": "TIMEOUT_%ds" % a.cap, "train_s": round(time.time() - ts, 2)}
            except BaseException as e:  # noqa: BLE001
                met = {"code": 9, "err": (type(e).__name__ + ":" + str(e)[:40]).replace(" ", "_"), "train_s": round(time.time() - ts, 2)}
            finally:
                signal.alarm(0)
            n, t, ch, p, me, o = c
            rec = {"idx": i, "norm": n, "tok": t, "chan": ch, "pos": p, "med": me, "opt": ("+".join(o) if o else "none"), **met}
            rf.write(json.dumps(rec) + "\n"); rf.flush()
            rows.append(rec); done.add(i)
            print("[%2d/%2d] tok=%-14s chan=%-15s pos=%-4s | mode=%.3f(min %.3f spr %.3f) long=%.3f(ret %.2f) med_t2=%.3f int8=%.3f qgap=%.3f CAP=%.3f code=%d %s t=%.1fs"
                  % (len(done), len(cands), t, ch, p, met.get("mode_acc", 0), met.get("mode_min", 0),
                     met.get("mode_spread", 0), met.get("mode_acc_long", 0), met.get("len_ret", 0),
                     met.get("medusa_t2", 0), met.get("int8_mode_acc", 0), met.get("quant_gap", 0),
                     met.get("capability", 0), met.get("code", -1), met.get("err", "?"), met.get("train_s", 0)), flush=True)

    json.dump({"ts": time.time(), "done": len(done), "total": len(cands), "elapsed": round(time.time() - t_start, 1)}, open(HEART, "w"))
    allrows = [json.loads(l) for l in open(RESULTS)]
    summarize(allrows, d.get("oracle", 0))
    run_id, nvalid = write_corpus(allrows)
    print("Wrote %d valid candidate K=V line(s) -> %s (run_id=%s)" % (nvalid, CORPUS, run_id))
    if nvalid and not a.no_analyze:
        run_analyzer(nvalid, a.topk)


def summarize(rows, oracle):
    ok = [r for r in rows if r.get("code") == 0]
    print("=" * 112)
    print("FINAL-END CAPABILITY SUMMARY — %d candidates, %d valid | content chance=%.3f oracle-ceiling=%.3f"
          % (len(rows), len(ok), 1.0 / CONT_C, oracle))
    if not ok:
        print("no valid rows"); return

    def axis(key, vals, fields):
        for v in vals:
            sub = [r for r in ok if r.get(key) == v]
            if sub:
                print("    %-15s %s (n=%d)" % (v, " ".join("%s=%.3f" % (f, sum(r[f] for r in sub) / len(sub)) for f in fields), len(sub)))

    print("  CHANMIX (per-mode breadth — does routing beat a dense FFN at fitting K conflicting rules?):")
    axis("chan", CHANMIX, ["mode_acc", "mode_min", "mode_spread", "int8_mode_acc"])
    print("  TOKENMIX (length-generalization — does the mixer carry the mode token far?):")
    axis("tok", TOKENMIX, ["mode_acc", "mode_acc_long", "len_ret"])
    print("  NORMPOS:")
    axis("pos", NORMPOS, ["mode_acc", "capability"])
    print("  quantization: mean quant_gap=%.4f (int8 vs fp) ; medusa T+2 mean=%.3f"
          % (sum(r["quant_gap"] for r in ok) / len(ok), sum(r["medusa_t2"] for r in ok) / len(ok)))
    top = sorted(ok, key=lambda r: -r["capability"])[:8]
    print("  TOP by deployed CAPABILITY (0.55 int8_mode + 0.25 long + 0.20 mode_min):")
    for r in top:
        print("    CAP=%.3f mode=%.3f min=%.3f long=%.3f med_t2=%.3f | tok=%s chan=%s pos=%s"
              % (r["capability"], r["int8_mode_acc"], r["mode_min"], r["mode_acc_long"], r["medusa_t2"], r["tok"], r["chan"], r["pos"]))
    best = max(ok, key=lambda r: r["capability"])
    print("  BEST: tok=%s chan=%s pos=%s -> CAP=%.3f" % (best["tok"], best["chan"], best["pos"], best["capability"]))
    print("=" * 112)


if __name__ == "__main__":
    raise SystemExit(main())
