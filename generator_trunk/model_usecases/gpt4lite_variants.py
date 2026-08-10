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

r"""gpt4lite_variants — the GPT-4-Lite sandbox turned into a Combinatorics-Framework use-case.

Source lineage: $BUNDLE_SUT_ROOT/GPT-4-Lite_sandbox/ — a from-scratch
CPU-targeted GPT (RoPE + Grouped-Query-Attention + Mixture-of-Experts + SwiGLU). Its README makes
FOUR explicit performance claims for this hardware (FX-8320, no AVX2, DDR3). This module breeds many
FUNCTIONALLY-EQUIVALENT implementations of each hot kernel and lets the Bundle's verdict MEASURE
whether each claim actually pays off on THIS CPU — exactly the spirit of model_usecases #2/#6.

THE COMBINATORIAL OBJECT — what is synthesized / composed — is ONLY the four middle slots, the
interchangeable kernels (every variant a drop-in with an identical contract, so ALL combos are valid):

  | slot  | variants                                   | README claim it tests           | rule
  | ROPE  | cat_neg / narrow / split                   | "RoPE без комплексных чисел"     | FW_Combi(1)
  | KV    | expand_reshape / repeat_interleave /       | "избегает .repeat(); expand без  | FW_Combi(1)
  |       | index_select                               |  копий в DDR3"                  |
  | ATTN  | sdpa / manual / einsum                     | "SDPA → C++ ядра даже на CPU"    | FW_Combi(1)
  | MOE   | mask_loop / dense_all / sort_batched       | "маскирование вместо плотных     | FW_Combi(1)
  |       |                                            |  умножений матриц"              |
  -> 3 x 3 x 3 x 3 = 81 equivalent models.

HEAD and TAIL are the INVARIANT MEASUREMENT RIG (they do NOT vary): HEAD builds ONE tiny model with
fixed weights and computes the REFERENCE logits with the canonical kernels; the four slots OVERRIDE
the four global kernel functions; TAIL re-runs the SAME model with the selected kernels, checks
numerical equivalence vs the reference (FW_VAR=0 iff equivalent & finite), times forward and
forward+backward on this host, and prints the K=V line the Analyzer ranks.

Combinatorics rules used here:  orthogonal knobs -> FW_Combi(1) (cartesian product).  All 81 combos
are valid by construction (identical kernel contract); NO sieve needed.  (A 5th variant — SDPA's
native enable_gqa, skipping the KV broadcast entirely — would be valid ONLY with ATTN=sdpa; that is
the textbook case for the constraint sidecar/sieve, deliberately left out of this orthogonal V1.)

RunMeFirstOnce is the OBSERVER/ANALYZER: it profiles the CPU + cores + thread env + toolchain (so the
optimum is annotated with the machine it is FOR), stdlib-only and fast (it does NOT import torch).

  python3 gpt4lite_variants.py          # observe host -> breed & run all 81 here -> emit run spec
  python3 gpt4lite_variants.py --run    # just (re)emit the bundle_run spec + RunMeFirstOnce observer
"""
from __future__ import annotations

import importlib.util
import io
import os
import platform
import sys
from contextlib import redirect_stdout
from pathlib import Path

# ============================== HEAD — the invariant rig ============================== #
# Builds ONE model with fixed weights, sets the canonical kernels, computes REFERENCE logits.
HEAD = r'''
import math, time, os, platform
import torch
import torch.nn as nn
from torch.nn import functional as F

torch.manual_seed(1234)
_THREADS = torch.get_num_threads()

# tiny CPU config — mirrors the sandbox's "сверхлёгкая конфигурация" test philosophy
VOCAB, BLOCK = 256, 64
N_LAYER, NHQ, NHKV, NEMB = 2, 4, 2, 64
NEXP, TOPK = 4, 2
HEAD_DIM = NEMB // NHQ            # 16 (even -> RoPE ok)
N_GROUPS = NHQ // NHKV            # 2
B, T = 2, 16
TOL = 2e-3                        # equivalence tolerance vs the reference kernels

# ===== the four INTERCHANGEABLE kernels — canonical here, OVERRIDDEN per candidate below ===== #
def apply_rope(x, cos, sin):
    x1, x2 = x.chunk(2, dim=-1)
    x_rot = torch.cat((-x2, x1), dim=-1)
    return x * cos.unsqueeze(0).unsqueeze(2) + x_rot * sin.unsqueeze(0).unsqueeze(2)

def kv_broadcast(t, n_groups):
    Bb, Tt, nkv, hd = t.shape
    return t.unsqueeze(3).expand(-1, -1, -1, n_groups, -1).reshape(Bb, Tt, nkv * n_groups, hd)

def attn_kernel(q, k, v):
    return F.scaled_dot_product_attention(q, k, v, is_causal=True)

def moe_dispatch(x_flat, routing_weights, selected_experts, experts, n_experts):
    out = torch.zeros_like(x_flat)
    tk = selected_experts.shape[1]
    for i, expert in enumerate(experts):
        for kk in range(tk):
            m = (selected_experts[:, kk] == i)
            if m.any():
                out[m] += expert(x_flat[m]) * routing_weights[m, kk].unsqueeze(-1)
    return out

# ===== invariant model skeleton (calls the four kernels by GLOBAL name) ===== #
def _rope_cache(dim, seq, base=10000):
    inv = 1.0 / (base ** (torch.arange(0, dim, 2).float() / dim))
    pos = torch.arange(seq, dtype=torch.float32)
    fr = torch.einsum("i,j->ij", pos, inv)
    emb = torch.cat((fr, fr), dim=-1)
    return emb.cos(), emb.sin()

_COS, _SIN = _rope_cache(HEAD_DIM, BLOCK)

class Attn(nn.Module):
    def __init__(self):
        super().__init__()
        self.wq = nn.Linear(NEMB, NHQ * HEAD_DIM, bias=False)
        self.wk = nn.Linear(NEMB, NHKV * HEAD_DIM, bias=False)
        self.wv = nn.Linear(NEMB, NHKV * HEAD_DIM, bias=False)
        self.wo = nn.Linear(NEMB, NEMB, bias=False)
    def forward(self, x):
        Bb, Tt, C = x.shape
        q = self.wq(x).view(Bb, Tt, NHQ, HEAD_DIM)
        k = self.wk(x).view(Bb, Tt, NHKV, HEAD_DIM)
        v = self.wv(x).view(Bb, Tt, NHKV, HEAD_DIM)
        cos, sin = _COS[:Tt], _SIN[:Tt]
        q = apply_rope(q, cos, sin)
        k = apply_rope(k, cos, sin)
        k = kv_broadcast(k, N_GROUPS)
        v = kv_broadcast(v, N_GROUPS)
        q = q.transpose(1, 2); k = k.transpose(1, 2); v = v.transpose(1, 2)
        y = attn_kernel(q, k, v)
        y = y.transpose(1, 2).contiguous().view(Bb, Tt, C)
        return self.wo(y)

class Expert(nn.Module):
    def __init__(self):
        super().__init__()
        hid = int(8 * NEMB / 3)
        self.w1 = nn.Linear(NEMB, hid, bias=False)
        self.w2 = nn.Linear(NEMB, hid, bias=False)
        self.w3 = nn.Linear(hid, NEMB, bias=False)
    def forward(self, x):
        return self.w3(F.silu(self.w1(x)) * self.w2(x))

class MoE(nn.Module):
    def __init__(self):
        super().__init__()
        self.router = nn.Linear(NEMB, NEXP, bias=False)
        self.experts = nn.ModuleList([Expert() for _ in range(NEXP)])
    def forward(self, x):
        Bb, Tt, C = x.shape
        xf = x.view(-1, C)
        logits = self.router(xf)
        rw, sel = torch.topk(logits, TOPK, dim=-1)
        rw = F.softmax(rw, dim=-1)
        out = moe_dispatch(xf, rw, sel, self.experts, NEXP)
        return out.view(Bb, Tt, C)

class Block(nn.Module):
    def __init__(self):
        super().__init__()
        self.ln1 = nn.LayerNorm(NEMB, bias=False)
        self.attn = Attn()
        self.ln2 = nn.LayerNorm(NEMB, bias=False)
        self.moe = MoE()
    def forward(self, x):
        x = x + self.attn(self.ln1(x))
        x = x + self.moe(self.ln2(x))
        return x

class GPT(nn.Module):
    def __init__(self):
        super().__init__()
        self.wte = nn.Embedding(VOCAB, NEMB)
        self.h = nn.ModuleList([Block() for _ in range(N_LAYER)])
        self.lnf = nn.LayerNorm(NEMB, bias=False)
        self.head = nn.Linear(NEMB, VOCAB, bias=False)
        self.wte.weight = self.head.weight
    def forward(self, idx, targets=None):
        x = self.wte(idx)
        for blk in self.h:
            x = blk(x)
        x = self.lnf(x)
        if targets is None:
            return self.head(x[:, -1, :]), None
        logits = self.head(x)
        loss = F.cross_entropy(logits.view(-1, logits.size(-1)), targets.view(-1))
        return logits, loss

# ===== build ONE model (fixed weights); REFERENCE logits via the CANONICAL kernels ===== #
torch.manual_seed(1234)
_MODEL = GPT().eval()
_X = torch.randint(0, VOCAB, (B, T))
_Y = torch.randint(0, VOCAB, (B, T))
with torch.inference_mode():
    _ref, _ = _MODEL(_X)
_REF = _ref.clone()
_PARAMS = sum(p.numel() for p in _MODEL.parameters())
'''

# ============================ the four combinatorial axes ============================ #
# Each fragment REASSIGNS one global kernel; the chosen value per axis shadows the canonical one.
ROPE = {
    "cat_neg": r'''
def apply_rope(x, cos, sin):
    x1, x2 = x.chunk(2, dim=-1)
    x_rot = torch.cat((-x2, x1), dim=-1)
    return x * cos.unsqueeze(0).unsqueeze(2) + x_rot * sin.unsqueeze(0).unsqueeze(2)
''',
    "narrow": r'''
def apply_rope(x, cos, sin):
    half = x.shape[-1] // 2
    x1 = x.narrow(-1, 0, half); x2 = x.narrow(-1, half, half)
    x_rot = torch.cat((-x2, x1), dim=-1)
    return x * cos.unsqueeze(0).unsqueeze(2) + x_rot * sin.unsqueeze(0).unsqueeze(2)
''',
    "split": r'''
def apply_rope(x, cos, sin):
    x1, x2 = torch.split(x, x.shape[-1] // 2, dim=-1)
    x_rot = torch.cat((-x2, x1), dim=-1)
    return x * cos.unsqueeze(0).unsqueeze(2) + x_rot * sin.unsqueeze(0).unsqueeze(2)
''',
}
KV = {
    "expand_reshape": r'''
def kv_broadcast(t, n_groups):
    Bb, Tt, nkv, hd = t.shape
    return t.unsqueeze(3).expand(-1, -1, -1, n_groups, -1).reshape(Bb, Tt, nkv * n_groups, hd)
''',
    "repeat_interleave": r'''
def kv_broadcast(t, n_groups):
    return torch.repeat_interleave(t, n_groups, dim=2)
''',
    "index_select": r'''
def kv_broadcast(t, n_groups):
    nkv = t.shape[2]
    idx = torch.arange(nkv).repeat_interleave(n_groups)
    return t.index_select(2, idx)
''',
}
ATTN = {
    "sdpa": r'''
def attn_kernel(q, k, v):
    return F.scaled_dot_product_attention(q, k, v, is_causal=True)
''',
    "manual": r'''
def attn_kernel(q, k, v):
    Tt = q.shape[-2]; D = q.shape[-1]
    scores = (q @ k.transpose(-2, -1)) / (D ** 0.5)
    cmask = torch.tril(torch.ones(Tt, Tt, dtype=torch.bool, device=q.device))
    scores = scores.masked_fill(~cmask, float("-inf"))
    return torch.softmax(scores, dim=-1) @ v
''',
    "einsum": r'''
def attn_kernel(q, k, v):
    Tt = q.shape[-2]; D = q.shape[-1]
    scores = torch.einsum("bhid,bhjd->bhij", q, k) / (D ** 0.5)
    cmask = torch.tril(torch.ones(Tt, Tt, dtype=torch.bool, device=q.device))
    scores = scores.masked_fill(~cmask, float("-inf"))
    return torch.einsum("bhij,bhjd->bhid", torch.softmax(scores, dim=-1), v)
''',
}
MOE = {
    "mask_loop": r'''
def moe_dispatch(x_flat, routing_weights, selected_experts, experts, n_experts):
    out = torch.zeros_like(x_flat)
    tk = selected_experts.shape[1]
    for i, expert in enumerate(experts):
        for kk in range(tk):
            m = (selected_experts[:, kk] == i)
            if m.any():
                out[m] += expert(x_flat[m]) * routing_weights[m, kk].unsqueeze(-1)
    return out
''',
    "dense_all": r'''
def moe_dispatch(x_flat, routing_weights, selected_experts, experts, n_experts):
    N = x_flat.shape[0]
    W = torch.zeros(N, n_experts, dtype=routing_weights.dtype)
    W.scatter_(1, selected_experts, routing_weights)
    out = torch.zeros_like(x_flat)
    for i, expert in enumerate(experts):
        out = out + expert(x_flat) * W[:, i].unsqueeze(-1)
    return out
''',
    "sort_batched": r'''
def moe_dispatch(x_flat, routing_weights, selected_experts, experts, n_experts):
    out = torch.zeros_like(x_flat)
    tk = selected_experts.shape[1]
    tok = torch.arange(x_flat.shape[0]).repeat_interleave(tk)
    exp = selected_experts.reshape(-1)
    wgt = routing_weights.reshape(-1)
    order = torch.argsort(exp)
    exp, tok, wgt = exp[order], tok[order], wgt[order]
    counts = torch.bincount(exp, minlength=n_experts)
    start = 0
    for i, expert in enumerate(experts):
        c = int(counts[i])
        if c > 0:
            toks = tok[start:start + c]
            out.index_add_(0, toks, expert(x_flat[toks]) * wgt[start:start + c].unsqueeze(-1))
        start += c
    return out
''',
}

# ============================== TAIL — oracle + K=V emit ============================== #
TAIL = r'''
try:
    REPS = 12
    with torch.inference_mode():
        _var, _ = _MODEL(_X)
        ok_shape = (_var.shape == _REF.shape)
        finite = bool(torch.isfinite(_var).all())
        err = float((_var - _REF).abs().max()) if ok_shape else float("inf")
        best = None
        for _ in range(REPS):
            _t = time.perf_counter(); _MODEL(_X); _e = time.perf_counter() - _t
            best = _e if best is None or _e < best else best
    fwd_ms = best * 1000.0
    bb = None
    for _ in range(3):
        _MODEL.zero_grad(set_to_none=True)
        _t = time.perf_counter(); _, _loss = _MODEL(_X, _Y); _loss.backward()
        _e = time.perf_counter() - _t
        bb = _e if bb is None or _e < bb else bb
    fwd_bwd_ms = bb * 1000.0
    correct = 1 if (ok_shape and finite and err < TOL) else 0
    tok_per_s = (B * T) / best if best and best > 0 else 0.0
    FW_VAR = 0 if correct else 2
    print("app=gpt4lite correct=%d max_abs_err=%.3e fwd_ms=%.3f fwd_bwd_ms=%.3f tok_per_s=%.1f "
          "params=%d torch_threads=%d FW_VAR=%d"
          % (correct, err, fwd_ms, fwd_bwd_ms, tok_per_s, _PARAMS, _THREADS, FW_VAR))
except Exception as _ex:
    FW_VAR = 3
    print("app=gpt4lite correct=0 max_abs_err=inf fwd_ms=0.0 fwd_bwd_ms=0.0 tok_per_s=0.0 "
          "params=0 torch_threads=%d FW_VAR=3" % (torch.get_num_threads() if "torch" in dir() else 0))
'''

# ===================== RunMeFirstOnce — the hardware/thread observer ===================== #
# stdlib-only, fast (does NOT import torch); annotates which CPU the optimum is FOR.
RUNME = r'''
import os, platform, subprocess, sys, importlib.util
def _v(c):
    try: return subprocess.run(c, capture_output=True, text=True).stdout.splitlines()[0]
    except Exception: return "n/a"
cpu = "unknown"; flags = ""
try:
    for ln in open("/proc/cpuinfo"):
        if ln.startswith("model name"): cpu = ln.split(":", 1)[1].strip()
        if ln.startswith("flags"):
            fl = ln.lower(); flags = "avx2" if "avx2" in fl else ("avx" if " avx " in fl else "no-avx")
            break
except Exception: pass
thr = os.environ.get("OMP_NUM_THREADS") or os.environ.get("MKL_NUM_THREADS") or "default"
has_torch = "yes" if importlib.util.find_spec("torch") else "NO"
cand = os.path.basename(sys.argv[1]) if len(sys.argv) > 1 else "-"
print("[RunMeFirstOnce] optimizing FOR: %s | %s | cores %s | %s | omp_threads %s | torch %s | %s | observing %s"
      % (cpu, platform.machine(), os.cpu_count(), flags, thr, has_torch, _v(["gcc", "--version"]), cand))
'''


# --------------------------------- render + offline run --------------------------------- #
def render(rope: str, kv: str, attn: str, moe: str) -> str:
    """One candidate = HEAD + the four selected kernel overrides + TAIL (slot order = toml order)."""
    return HEAD + ROPE[rope] + KV[kv] + ATTN[attn] + MOE[moe] + TAIL


def _torch_available() -> bool:
    return importlib.util.find_spec("torch") is not None


def _exec_capture(src: str):
    buf, ns = io.StringIO(), {}
    try:
        with redirect_stdout(buf):
            exec(compile(src, "<candidate>", "exec"), ns)
    except Exception as e:  # noqa: BLE001
        return None, f"EXC {type(e).__name__}: {e}"
    for ln in buf.getvalue().splitlines():
        if ln.startswith("app=") and "FW_VAR=" in ln:
            return ln.strip(), buf.getvalue()
    return None, buf.getvalue()


def _kv(line: str) -> dict:
    d = {}
    for tok in line.split():
        if "=" in tok:
            k, v = tok.split("=", 1)
            d[k] = v
    return d


def _observe_print():
    out, _ = _exec_capture("__import__('runpy')")  # noop to keep imports warm
    try:
        ns = {}
        exec(compile(RUNME.replace('sys.argv[1]', '"offline"').replace('len(sys.argv) > 1', 'True'),
                     "<runme>", "exec"), ns)
    except Exception as e:  # noqa: BLE001
        print(f"[RunMeFirstOnce] (observer error: {e})")


def main():
    if "--run" in sys.argv[1:]:
        a = [x for x in sys.argv[1:] if not x.startswith("--")]
        emit_run_toml(Path(a[0]) if a else
                      Path(__file__).resolve().parent / "run" / "gpt4lite_variants" / "gpt4lite_variants.toml")
        return

    print("=== GPT-4-Lite variants — equivalent kernels bred & measured on THIS CPU ===\n")
    _observe_print()
    n = len(ROPE) * len(KV) * len(ATTN) * len(MOE)
    print(f"\n  combinatorial object = ROPE({len(ROPE)}) x KV({len(KV)}) x ATTN({len(ATTN)}) "
          f"x MOE({len(MOE)}) = {n} equivalent models")
    print("  HEAD/TAIL = invariant rig (build once, reference logits, time + equivalence-check); "
          "only the 4 kernels vary.\n")
    if not _torch_available():
        print("  torch not importable here — emitting the run spec only (the Bundle will run it).")
        emit_run_toml(Path(__file__).resolve().parent / "run" / "gpt4lite_variants" / "gpt4lite_variants.toml")
        return

    rows, n_ok = [], 0
    for r in ROPE:
        for k in KV:
            for at in ATTN:
                for mo in MOE:
                    line, _full = _exec_capture(render(r, k, at, mo))
                    if line is None:
                        rows.append((r, k, at, mo, None)); continue
                    d = _kv(line)
                    n_ok += int(d.get("correct", "0") == "1")
                    rows.append((r, k, at, mo, d))

    good = [row for row in rows if row[4] and row[4].get("correct") == "1"]
    print(f"  variants bred: {n}   |   passed the equivalence oracle (FW_VAR=0): {n_ok}\n")
    print(f"    {'ROPE':<8}{'KV':<18}{'ATTN':<8}{'MOE':<14}{'fwd_ms':>9}{'fwd_bwd':>9}{'tok/s':>10}{'max_err':>11}")
    for r, k, at, mo, d in sorted(good, key=lambda x: float(x[4]["fwd_ms"]))[:12]:
        print(f"    {r:<8}{k:<18}{at:<8}{mo:<14}{float(d['fwd_ms']):>9.3f}{float(d['fwd_bwd_ms']):>9.3f}"
              f"{float(d['tok_per_s']):>10.1f}{float(d['max_abs_err']):>11.1e}")

    if good:
        fastest = min(good, key=lambda x: float(x[4]["fwd_ms"]))
        slowest = max(good, key=lambda x: float(x[4]["fwd_ms"]))
        fr, fk, fa, fm, fd = fastest
        sr, sk, sa, sm, sd = slowest
        print(f"\n  *** FASTEST correct on this CPU: ROPE={fr} KV={fk} ATTN={fa} MOE={fm}  "
              f"({float(fd['fwd_ms']):.3f} ms/fwd) ***")
        print(f"      slowest correct: ROPE={sr} KV={sk} ATTN={sa} MOE={sm}  ({float(sd['fwd_ms']):.3f} ms) "
              f"-> {float(sd['fwd_ms']) / float(fd['fwd_ms']):.2f}x slower")
        # marginal effect of each axis (median fwd_ms per variant) — which README claim actually matters
        import statistics as st
        print("\n  per-axis impact (median fwd_ms; bigger spread = the optimization that matters here):")
        for name, idx, table in (("ROPE", 0, ROPE), ("KV", 1, KV), ("ATTN", 2, ATTN), ("MOE", 3, MOE)):
            meds = {v: st.median([float(x[4]["fwd_ms"]) for x in good if x[idx] == v]) for v in table}
            lo, hi = min(meds.values()), max(meds.values())
            order = " ".join(f"{v}={meds[v]:.2f}" for v in sorted(meds, key=meds.get))
            print(f"    {name:<6} spread {hi - lo:5.2f} ms  ({order})")

    emit_run_toml(Path(__file__).resolve().parent / "run" / "gpt4lite_variants" / "gpt4lite_variants.toml")
    print(f"\n  -> the engine breeds {n} equivalent GPT-4-Lite models; the Bundle runs each in isolation "
          f"and the verdict picks the fastest CORRECT kernel-set FOR THIS CPU (measured, not guessed).")


# ----------------------------------- emit bundle_run spec ----------------------------------- #
def emit_run_toml(path: Path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    def raw_slot(sheet, frags):
        L = ['[[slots]]', f'sheet = "{sheet}"', f'key   = "{sheet.lower()}"',
             'verb  = "FW_Combi(1)"', 'raw   = true', 'values = [']
        for f in frags:
            body = f if f.startswith("\n") else "\n" + f
            L.append("'''" + (body if body.endswith("\n") else body + "\n") + "''',")
        return L + [']', '']

    L = ['title = "GPT-4-Lite variants (RUN) — fastest correct kernel-set for THIS CPU, full Bundle"',
         'note  = "Middle slots ROPE x KV x ATTN x MOE = the combinatorial kernel object (81 equivalent '
         'models); HEAD builds one model + reference logits, TAIL re-runs the selected kernels, checks '
         'equivalence (FW_VAR=0 iff within tol) and times fwd/fwd+bwd on the host. RunMeFirstOnce observes '
         'the CPU/threads. Analyzer fwd_ms:min picks the hardware-optimal kernel-set."',
         'args = ["model=gpt4lite", "metric=fwd_ms_min", "target=this_host"]',
         "runme = '''\n" + RUNME.lstrip("\n") + "'''", '',
         '[[goals]]', 'key = "fwd_ms"', 'dir = "min"',
         '[[goals]]', 'key = "correct"', 'dir = "max"',
         '[[goals]]', 'key = "fwd_bwd_ms"', 'dir = "min"',
         '[[goals]]', 'key = "max_abs_err"', 'dir = "min"',
         '[[goals]]', 'key = "tok_per_s"', 'dir = "max"', '']
    L += raw_slot("HEAD", [HEAD])
    L += raw_slot("ROPE", [ROPE[k] for k in ROPE])
    L += raw_slot("KV", [KV[k] for k in KV])
    L += raw_slot("ATTN", [ATTN[k] for k in ATTN])
    L += raw_slot("MOE", [MOE[k] for k in MOE])
    L += raw_slot("TAIL", [TAIL])
    L += ['[[custom_vars]]', 'code = 2', 'msg  = "variant not numerically equivalent to reference"',
          '[[custom_vars]]', 'code = 3', 'msg  = "variant raised an exception / did not run"', '']
    path.write_text("\n".join(L) + "\n", encoding="utf-8")
    (path.parent / "runmefirstonce.first").write_text(RUNME.lstrip("\n"), encoding="utf-8")
    n = len(ROPE) * len(KV) * len(ATTN) * len(MOE)
    print(f"  RUN spec -> {path}  ({n} kernel-set candidates; runme = hardware observer)")


if __name__ == "__main__":
    main()
