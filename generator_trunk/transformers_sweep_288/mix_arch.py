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

"""mix_arch — a parametric ternary Medusa transformer assembled from interchangeable UNITS.

The transformer in ../  was decomposed (across considerme_as_upgrade1..4) into independent logical
units, each with several verified variants. This module makes every unit a SWAPPABLE axis so the
Combinatorics framework (the Bundle) can synthesize architectures by taking the Cartesian product of
unit-variants and judging each one. Units / axes (the "freedom: exactly one of a set" -> FW_Combi(1)):

  NORM     residual-stream norm   : rmsnorm | layernorm                 (upgrade2 vs baseline; FPU cost)
  TOKENMIX token mixer (attention): lin_cumsum | lin_fused_qkvg | lin_decay
                                    (upgrade1/2 cumsum ; upgrade4 fused QKVG ; upgrade3 decay scan)
  CHANMIX  channel mixer (FFN/MoE): dense | moe_top2 | moe_shared_top1  (baseline / +routing / upgrade2-4)
  NORMPOS  norm placement         : pre | post                          (upgrade2-4 vs upgrade1)
  MEDUSA   speculative heads      : separate | vectorized               (baseline vs all upgrades)

Sudden actions (the "may or may not fire, any combination" freedom -> FW_Optional, present (+) absent):
  OPT_JITTER  router jitter noise (training stabiliser, upgrade3)
  OPT_CONVQ   causal depthwise Conv1D on Q too (extra positional mixing, upgrade3)

Everything is kept deliberately TINY (weak FX-8320 PC): the per-candidate oracle builds a small model
and runs forward+backward+one SGD step + cheap proxies, never compiling the C++ kernel (that happens
once, in the bootstrap). The kernel/int8 path is exercised with the PyTorch int32 fallback here.
"""
from __future__ import annotations

import math
import statistics
import sys
import time
from pathlib import Path

GENERATOR_ROOT = Path(__file__).resolve().parent.parent
if str(GENERATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(GENERATOR_ROOT))

from sut_paths import project_path  # noqa: E402

import torch
import torch.nn as nn
import torch.nn.functional as F


class GenotypeError(ValueError):
    """Raised for an incompatible architecture config (fail-loud -> sieve/PRUNE code 8)."""


# --------------------------------------------------------------------------------------------------
# Norms
# --------------------------------------------------------------------------------------------------
class RMSNorm(nn.Module):
    def __init__(self, dim: int, eps: float = 1e-6, affine: bool = True):
        super().__init__()
        self.eps = eps
        self.weight = nn.Parameter(torch.ones(dim)) if affine else None

    def forward(self, x):
        out = x * torch.rsqrt(x.pow(2).mean(-1, keepdim=True) + self.eps)
        return out * self.weight if self.weight is not None else out


def build_norm(kind: str, dim: int) -> nn.Module:
    if kind == "rmsnorm":
        return RMSNorm(dim, affine=True)
    if kind == "layernorm":
        return nn.LayerNorm(dim)
    raise GenotypeError("unknown norm %r" % kind)


# --------------------------------------------------------------------------------------------------
# Ternary BitLinear (per-channel fake-quant training + int8 fallback inference)
# --------------------------------------------------------------------------------------------------
class BitLinear(nn.Linear):
    def __init__(self, in_features: int, out_features: int, bias: bool = False):
        super().__init__(in_features, out_features, bias)
        self.inner_norm = RMSNorm(in_features, affine=False)  # pre-quant norm (non-affine, verified)
        self.is_infer = False

    def _wscale(self):
        return 1.0 / self.weight.abs().mean(dim=1, keepdim=True).clamp(min=1e-5)

    def export_for_inference(self):
        if self.is_infer:
            return
        with torch.no_grad():
            ws = self._wscale()
            q = (self.weight * ws).round().clamp(-1, 1).to(torch.int8).contiguous()
        self.register_buffer("qw", q)
        self.register_buffer("ws", ws.detach().float().squeeze(-1).contiguous())
        del self.weight
        self.is_infer = True

    def forward(self, x):
        xn = self.inner_norm(x)
        xs = 127.0 / xn.abs().amax(dim=-1, keepdim=True).clamp(min=1e-5)
        xq = (xn * xs).round().clamp(-128, 127)
        if not self.is_infer:
            ws = self._wscale()
            wq = (self.weight * ws).round().clamp(-1, 1)
            wt = (wq - self.weight).detach() + self.weight                 # weight STE
            xste = (xq - xn * xs).detach() + xn * xs                       # activation STE
            out = F.linear(xste, wt, self.bias)
            return out / (ws.view(-1) * xs)                               # rank-safe per-channel dequant
        oi = torch.matmul(xq.to(torch.int8).to(torch.int32), self.qw.t().to(torch.int32))
        out = oi.to(x.dtype) / (self.ws.to(x.device, x.dtype) * xs)
        if self.bias is not None:
            out = out + self.bias
        return out


def _ffn(d_model: int, d_ffn: int) -> nn.Sequential:
    return nn.Sequential(BitLinear(d_model, d_ffn), nn.GELU(), BitLinear(d_ffn, d_model))


# --------------------------------------------------------------------------------------------------
# Token mixer: gated linear attention (fused/separate proj, conv K/V[/Q], cumsum or decay scan, cache)
# --------------------------------------------------------------------------------------------------
class LinAttn(nn.Module):
    def __init__(self, d_model, n_heads, *, fused, use_decay, conv_q, norm_kind):
        super().__init__()
        if d_model % n_heads != 0:
            raise GenotypeError("d_model %d not divisible by n_heads %d" % (d_model, n_heads))
        self.n_heads, self.head_dim, self.d_model = n_heads, d_model // n_heads, d_model
        self.fused, self.use_decay, self.conv_q = fused, use_decay, conv_q
        if fused:
            self.qkvg = BitLinear(d_model, 4 * d_model)
        else:
            self.q_proj = BitLinear(d_model, d_model)
            self.k_proj = BitLinear(d_model, d_model)
            self.v_proj = BitLinear(d_model, d_model)
            self.gate = BitLinear(d_model, d_model)
        self.out_proj = BitLinear(d_model, d_model)
        self.norm = build_norm(norm_kind, d_model)
        self.conv_k = nn.Conv1d(d_model, d_model, 3, groups=d_model, bias=False)
        self.conv_v = nn.Conv1d(d_model, d_model, 3, groups=d_model, bias=False)
        if conv_q:
            self.convq = nn.Conv1d(d_model, d_model, 3, groups=d_model, bias=False)
        if use_decay:
            self.decay_proj = nn.Linear(d_model, n_heads, bias=True)
            nn.init.zeros_(self.decay_proj.weight)
            nn.init.constant_(self.decay_proj.bias, 4.0)  # sigmoid(4)~0.982: near no-forgetting at init

    @staticmethod
    def _causal_conv(conv, feats, state):
        ci = feats.transpose(1, 2).contiguous()                          # [B,D,S]
        if state is None:
            state = ci.new_zeros(ci.size(0), ci.size(1), 2)
        if ci.size(-1) >= 2:
            nxt = ci[:, :, -2:].contiguous()
        else:
            nxt = torch.cat([state[:, :, ci.size(-1):], ci], dim=-1).contiguous()
        out = conv(torch.cat([state, ci], dim=-1)).transpose(1, 2)       # [B,S,D]
        return out, nxt

    def _scan(self, k, v, decay, past_kv, past_k):
        if decay is None:                                                # fast vectorized cumsum path
            kv = (k.unsqueeze(-1) * v.unsqueeze(-2)).cumsum(2) + past_kv.unsqueeze(2)
            ks = k.cumsum(2) + past_k.unsqueeze(2)
            return kv, ks
        upd = k.unsqueeze(-1) * v.unsqueeze(-2)                          # data-dependent decay scan
        kv_s, k_s, KV, K = past_kv, past_k, [], []
        for t in range(k.size(2)):
            f = decay[:, :, t, :]
            kv_s = kv_s * f.unsqueeze(-1) + upd[:, :, t]
            k_s = k_s * f + k[:, :, t]
            KV.append(kv_s); K.append(k_s)
        return torch.stack(KV, 2), torch.stack(K, 2)

    def forward(self, x, past=None):
        B, S, D = x.shape
        H, hd = self.n_heads, self.head_dim
        if self.fused:
            q_f, k_f, v_f, g_f = self.qkvg(x).split(D, dim=-1)
        else:
            q_f, k_f, v_f, g_f = self.q_proj(x), self.k_proj(x), self.v_proj(x), self.gate(x)
        st = past or {}
        k_f, nck = self._causal_conv(self.conv_k, k_f, st.get("ck"))
        v_f, ncv = self._causal_conv(self.conv_v, v_f, st.get("cv"))
        ncq = None
        if self.conv_q:
            q_f, ncq = self._causal_conv(self.convq, q_f, st.get("cq"))
        q = F.elu(q_f.reshape(B, S, H, hd).transpose(1, 2)) + 1.0
        k = F.elu(k_f.reshape(B, S, H, hd).transpose(1, 2)) + 1.0
        v = v_f.reshape(B, S, H, hd).transpose(1, 2)
        pkv, pk = st.get("kv"), st.get("k")
        if pkv is None:
            pkv = k.new_zeros(B, H, hd, hd); pk = k.new_zeros(B, H, hd)
        decay = None
        if self.use_decay:
            decay = torch.sigmoid(self.decay_proj(x).to(q.dtype)).transpose(1, 2).unsqueeze(-1)
        kv, ks = self._scan(k, v, decay, pkv, pk)
        num = torch.matmul(q.unsqueeze(-2), kv).squeeze(-2)
        den = (q * ks).sum(-1, keepdim=True).clamp_min(1e-6)
        o = (num / den).transpose(1, 2).contiguous().view(B, S, D)
        o = self.out_proj(self.norm(F.silu(g_f) * o))
        nstate = {"ck": nck, "cv": ncv, "cq": ncq,
                  "kv": kv[:, :, -1].contiguous(), "k": ks[:, :, -1].contiguous()}
        return o, nstate


# --------------------------------------------------------------------------------------------------
# Channel mixer: dense FFN, or MoE (top-2, or shared-expert + top-1)
# --------------------------------------------------------------------------------------------------
class DenseFFN(nn.Module):
    def __init__(self, d_model, d_ffn):
        super().__init__()
        self.net = _ffn(d_model, d_ffn)
        self.last_aux = None

    def forward(self, x):
        self.last_aux = None
        return self.net(x)


class BitMoE(nn.Module):
    def __init__(self, d_model, d_ffn, num_experts, *, mode, jitter, load_balance):
        super().__init__()
        if num_experts < 2:
            raise GenotypeError("num_experts must be >= 2")
        self.mode, self.num_experts = mode, num_experts
        self.jitter = jitter
        self.load_balance = load_balance
        self.top_k = 1 if mode == "moe_shared_top1" else 2
        self.router = nn.Linear(d_model, num_experts, bias=False)
        self.shared = _ffn(d_model, d_ffn) if mode == "moe_shared_top1" else None
        self.experts = nn.ModuleList([_ffn(d_model, d_ffn) for _ in range(num_experts)])
        self.last_aux = None

    def forward(self, x):
        B, S, D = x.shape
        xf = x.reshape(-1, D)
        ri = xf
        if self.training and self.jitter > 0:
            ri = xf * torch.empty_like(xf).uniform_(1.0 - self.jitter, 1.0 + self.jitter)
        probs = F.softmax(self.router(ri), dim=-1)
        w, sel = torch.topk(probs, self.top_k, dim=-1)
        w = w / w.sum(-1, keepdim=True).clamp_min(1e-9)
        self.last_aux = None
        if self.training and self.load_balance:
            imp = probs.mean(0)
            load = F.one_hot(sel[:, 0], self.num_experts).to(probs.dtype).mean(0)
            self.last_aux = self.num_experts * torch.sum(imp * load)
        out = self.shared(xf) if self.shared is not None else torch.zeros_like(xf)
        for i, expert in enumerate(self.experts):
            mask = (sel == i).any(dim=-1)
            if mask.any():
                idx = (sel[mask] == i).nonzero(as_tuple=True)[1]
                out[mask] = out[mask] + expert(xf[mask]) * w[mask, idx].unsqueeze(-1)
        return out.reshape(B, S, D)


# --------------------------------------------------------------------------------------------------
# Block (pre / post norm) and Medusa heads
# --------------------------------------------------------------------------------------------------
class Block(nn.Module):
    def __init__(self, geno, norm_kind):
        super().__init__()
        d, h = geno["d_model"], geno["n_heads"]
        self.normpos = geno["normpos"]
        self.attn = LinAttn(d, h, fused=(geno["token_mixer"] == "lin_fused_qkvg"),
                            use_decay=(geno["token_mixer"] == "lin_decay"),
                            conv_q=geno["conv_q"], norm_kind=norm_kind)
        if geno["channel_mixer"] == "dense":
            self.mix = DenseFFN(d, geno["d_ffn"])
        else:
            self.mix = BitMoE(d, geno["d_ffn"], geno["num_experts"], mode=geno["channel_mixer"],
                             jitter=(geno["router_jitter"] if geno["channel_mixer"] != "dense" else 0.0),
                             load_balance=geno["load_balance"])
        if self.normpos == "pre":
            self.attn_norm = build_norm(norm_kind, d)
            self.moe_norm = build_norm(norm_kind, d)

    def forward(self, x, past=None):
        if self.normpos == "pre":
            a, st = self.attn(self.attn_norm(x), past)
            x = x + a
            x = x + self.mix(self.moe_norm(x))
        else:
            a, st = self.attn(x, past)
            x = x + a
            x = x + self.mix(x)
        return x, st


class MedusaHeads(nn.Module):
    def __init__(self, d_model, vocab, num_heads, mode):
        super().__init__()
        self.mode, self.num_heads = mode, num_heads
        if mode == "separate":
            self.heads = nn.ModuleList(
                [nn.Sequential(BitLinear(d_model, d_model), nn.SiLU(), BitLinear(d_model, vocab))
                 for _ in range(num_heads)])
        else:
            self.shared_hidden = BitLinear(d_model, d_model)
            self.batched_out = BitLinear(d_model, vocab * num_heads)

    def forward(self, x):
        if self.mode == "separate":
            return [head(x) for head in self.heads]
        h = F.silu(self.shared_hidden(x))
        return list(self.batched_out(h).chunk(self.num_heads, dim=-1))


# --------------------------------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------------------------------
class MixTransformer(nn.Module):
    def __init__(self, geno):
        super().__init__()
        self.g = geno
        nk = geno["norm"]
        self.token_emb = nn.Embedding(geno["vocab"], geno["d_model"])
        self.layers = nn.ModuleList([Block(geno, nk) for _ in range(geno["n_layers"])])
        self.final_norm = build_norm(nk, geno["d_model"])
        self.primary_head = BitLinear(geno["d_model"], geno["vocab"])
        self.medusa_heads = MedusaHeads(geno["d_model"], geno["vocab"], 3, geno["medusa"])

    def forward(self, x, past_key_values=None, use_cache=False):
        if x.ndim != 2 or x.shape[1] == 0:
            raise GenotypeError("tokens must be [batch, sequence] non-empty")
        hidden = self.token_emb(x)
        new_past = [] if use_cache else None
        for i, layer in enumerate(self.layers):
            lp = None if past_key_values is None else past_key_values[i]
            hidden, st = layer(hidden, lp)
            if use_cache:
                new_past.append(st)
        final = self.final_norm(hidden)
        primary = self.primary_head(final)
        medusa = self.medusa_heads(final)
        if use_cache:
            return primary, medusa, new_past
        return primary, medusa

    def export_for_inference(self):
        for m in self.modules():
            if isinstance(m, BitLinear):
                m.export_for_inference()

    def router_aux_loss(self):
        auxes = [m.last_aux for m in self.modules() if isinstance(m, BitMoE) and m.last_aux is not None]
        return torch.stack(auxes).mean() if auxes else None


# --------------------------------------------------------------------------------------------------
# Genotype defaults + build
# --------------------------------------------------------------------------------------------------
def default_geno(**over):
    g = dict(vocab=48, d_model=24, n_heads=3, d_ffn=48, num_experts=3, n_layers=2, max_seq_len=64,
             norm="rmsnorm", token_mixer="lin_cumsum", channel_mixer="moe_shared_top1",
             normpos="pre", medusa="vectorized", conv_q=False, router_jitter=0.0, load_balance=False)
    g.update(over)
    return g


def build_model(geno):
    for key in ("vocab", "d_model", "n_heads", "d_ffn", "num_experts", "n_layers"):
        if not isinstance(geno.get(key), int) or geno[key] <= 0:
            raise GenotypeError("%s must be a positive int" % key)
    return MixTransformer(geno)


# --------------------------------------------------------------------------------------------------
# FW_VAR oracle  (the "meaning" layer)
# --------------------------------------------------------------------------------------------------
def _objective(model, tokens, targets, vocab):
    primary, medusa = model(tokens)
    seq = tokens.shape[1]
    loss = F.cross_entropy(primary.reshape(-1, vocab), targets[:, :seq].reshape(-1))
    for hi, hl in enumerate(medusa):
        tgt = targets[:, hi + 1: hi + 1 + seq]
        if tgt.shape[1] == seq:
            loss = loss + 0.25 * F.cross_entropy(hl.reshape(-1, vocab), tgt.reshape(-1))
    aux = model.router_aux_loss()
    if aux is not None:
        loss = loss + 0.01 * aux
    return loss, aux


def _causal_audit(model, tokens, reference, vocab, max_checks=4):
    """Perturb a future token; positions strictly before the cut must not change. Returns (ok, checks)."""
    B, S = tokens.shape
    cuts = list(range(1, S))
    if len(cuts) > max_checks:
        step = len(cuts) / max_checks
        cuts = [cuts[int(i * step)] for i in range(max_checks)]
    checks = 0
    for cut in cuts:
        perturbed = tokens.clone()
        perturbed[:, cut] = (perturbed[:, cut] + 1) % vocab
        out = model(perturbed)[0]
        checks += 1
        if not torch.allclose(out[:, :cut], reference[:, :cut], atol=1e-5, rtol=1e-4):
            return False, checks
    return True, checks


def _recurrence_delta(model, tokens):
    """Full pass vs prefix+suffix cached pass: max |Δ| on the suffix logits (should be ~0)."""
    S = tokens.shape[1]
    cut = max(1, S // 2)
    full = model(tokens, use_cache=True)[0]
    _, _, past = model(tokens[:, :cut], use_cache=True)
    suf = model(tokens[:, cut:], past_key_values=past, use_cache=True)[0]
    ref = full[:, cut:]
    # RELATIVE delta: a magnitude-blind absolute threshold falsely rejects deep / high-activation
    # configs (e.g. conv_q on Q multiplies the large kv state, so its length-dependent conv1d fp
    # rounding gets amplified — logically exact, ~8e-4 relative). Normalise by the logit scale.
    return float((ref - suf).abs().max() / (ref.abs().max() + 1e-6))


def evaluate(geno, batch=2, seq=12, seed=0, lr=1e-2, repeats=1):
    """Build one architecture and return cheap, deterministic proxy metrics + a verdict code.

    code: 0 valid; 1 wrong shape; 2 non-finite; 3 untrainable grad; 4 causal leak; 5 non-deterministic;
          6 optimizer didn't reduce same-batch loss; 7 recurrence cache inexact; 8 incompatible
          genotype (fail-loud); 9 unexpected crash.
    """
    m = dict(params=0, model_bytes=0, build_ms=0.0, latency_ms=0.0, tokens_per_s=0.0,
             out_std=0.0, loss=0.0, proxy_gradnorm=0.0, grad_coverage=0.0, step_delta=0.0,
             loss_after_step=0.0, loss_improvement=0.0, aux=0.0, causal_ok=-1, causal_checks=0,
             deterministic_ok=-1, recur_delta=-1.0, recur_ok=-1, int8_ok=-1, code=0, err="none")
    t0 = time.perf_counter()
    try:
        torch.manual_seed(seed)
        tb = time.perf_counter()
        model = build_model(geno)
        m["build_ms"] = round((time.perf_counter() - tb) * 1000.0, 3)
        m["params"] = sum(p.numel() for p in model.parameters())
        m["model_bytes"] = sum(p.numel() * p.element_size() for p in model.parameters())
        vocab = geno["vocab"]
        tokens = torch.randint(0, vocab, (batch, seq))

        model.eval()
        with torch.no_grad():
            ref = model(tokens)[0]
        if tuple(ref.shape) != (batch, seq, vocab):
            m["code"], m["err"] = 1, "wrong_shape"
        elif not bool(torch.isfinite(ref).all()):
            m["code"], m["err"] = 2, "nonfinite_output"
        else:
            with torch.no_grad():
                m["deterministic_ok"] = int(torch.equal(ref, model(tokens)[0]))
            if not m["deterministic_ok"]:
                m["code"], m["err"] = 5, "nondeterministic"
            else:
                with torch.no_grad():
                    ok, checks = _causal_audit(model, tokens, ref, vocab)
                m["causal_ok"], m["causal_checks"] = int(ok), checks
                if not ok:
                    m["code"], m["err"] = 4, "causal_leak"
                else:
                    with torch.no_grad():
                        m["recur_delta"] = round(_recurrence_delta(model, tokens), 9)
                    m["recur_ok"] = int(m["recur_delta"] <= 1e-3)
                    if not m["recur_ok"]:
                        m["code"], m["err"] = 7, "recurrence_inexact"

        if m["code"] == 0:
            m["out_std"] = round(float(ref.std()), 4)
            with torch.no_grad():
                model(tokens)
                timings = []
                for _ in range(repeats):
                    ts = time.perf_counter(); model(tokens)
                    timings.append((time.perf_counter() - ts) * 1000.0)
            m["latency_ms"] = round(statistics.median(timings), 3)
            if m["latency_ms"] > 0:
                m["tokens_per_s"] = round(batch * seq * 1000.0 / m["latency_ms"], 1)

            model.train()
            targets = torch.randint(0, vocab, (batch, seq))
            loss, aux = _objective(model, tokens, targets, vocab)
            m["loss"] = round(float(loss.detach()), 4)
            if aux is not None:
                m["aux"] = round(float(aux.detach()), 4)
            if not bool(torch.isfinite(loss)):
                m["code"], m["err"] = 2, "nonfinite_loss"
            else:
                loss.backward()
                gsq, gnum, tnum, finite = 0.0, 0, 0, True
                for p in model.parameters():
                    if not p.requires_grad:
                        continue
                    tnum += p.numel()
                    if p.grad is None:
                        continue
                    gnum += p.numel()
                    if not bool(torch.isfinite(p.grad).all()):
                        finite = False; continue
                    gsq += float(p.grad.pow(2).sum())
                m["grad_coverage"] = round(gnum / max(1, tnum), 4)
                m["proxy_gradnorm"] = round(gsq ** 0.5, 4)
                if not finite or not math.isfinite(gsq) or gsq <= 0.0:
                    m["code"], m["err"] = 3, "absent_or_nonfinite_grad"
                else:
                    with torch.no_grad():
                        for p in model.parameters():
                            if p.requires_grad and p.grad is not None:
                                p.add_(p.grad, alpha=-lr)
                    before = float(loss.detach())
                    model.train()
                    with torch.no_grad():
                        after, _ = _objective(model, tokens, targets, vocab)
                    m["loss_after_step"] = round(float(after), 6)
                    m["loss_improvement"] = round(before - float(after), 8)
                    m["step_delta"] = m["loss_improvement"]
                    if not bool(torch.isfinite(after)):
                        m["code"], m["err"] = 2, "nonfinite_post_step"
                    elif m["loss_improvement"] <= 0.0:
                        m["code"], m["err"] = 6, "no_loss_reduction"

        if m["code"] == 0:                                                # cheap int8 export shape check
            try:
                model.eval(); model.export_for_inference()
                io = model(tokens)[0]
                m["int8_ok"] = int(tuple(io.shape) == (batch, seq, vocab) and bool(torch.isfinite(io).all()))
                if not m["int8_ok"]:
                    m["code"], m["err"] = 1, "int8_shape"
            except Exception as exc:  # noqa: BLE001
                m["int8_ok"], m["code"], m["err"] = 0, 9, "int8_export:" + type(exc).__name__
    except GenotypeError as exc:
        m["code"], m["err"] = 8, ("Geno:" + str(exc)[:64]).replace(" ", "_")
    except Exception as exc:  # noqa: BLE001
        m["code"], m["err"] = 9, (type(exc).__name__ + ":" + str(exc)[:64]).replace(" ", "_")
    m["eval_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)
    return m


# --------------------------------------------------------------------------------------------------
# Fixed synthetic pre-training data (SAME corpus + schedule for every candidate) + full quality oracle
# --------------------------------------------------------------------------------------------------
_DATA_CACHE = {}


class _Done(Exception):
    """Internal early-exit once a verdict is set."""


def synthetic_corpus(vocab=48, n_tokens=3072, seed=1234, temp=0.5):
    """Deterministic order-2 Markov corpus with peaked transitions: learnable local+medium structure
    with a real entropy floor, so trained models actually separate by quality. Generated once and
    cached (shared across every candidate in a sweep process)."""
    key = (vocab, n_tokens, seed, round(temp, 4))
    if key in _DATA_CACHE:
        return _DATA_CACHE[key]
    g = torch.Generator().manual_seed(seed)
    mat = torch.randn(vocab, vocab, generator=g)
    seq = torch.zeros(n_tokens, dtype=torch.long)
    seq[0] = torch.randint(0, vocab, (1,), generator=g)
    seq[1] = torch.randint(0, vocab, (1,), generator=g)
    for t in range(2, n_tokens):
        logits = (mat[seq[t - 1]] + 0.5 * torch.roll(mat[seq[t - 2]], 1)) / temp
        seq[t] = torch.multinomial(torch.softmax(logits, -1), 1, generator=g)
    _DATA_CACHE[key] = seq
    return seq


def make_dataset(vocab=48, seq=16, batch=8, steps=120, n_tokens=3072, seed=1234):
    """Fixed train/held-out windows + a fixed batch schedule — byte-identical for every candidate."""
    corpus = synthetic_corpus(vocab=vocab, n_tokens=n_tokens, seed=seed)
    n = corpus.numel()
    split = int(n * 0.8)

    def windows(lo, hi):
        xs, ys = [], []
        t = lo
        while t + seq + 3 < hi:
            xs.append(corpus[t:t + seq])
            ys.append(corpus[t + 1:t + seq + 4])         # wide targets: primary (+1) + 3 medusa offsets
            t += seq
        return torch.stack(xs), torch.stack(ys)

    xtr, ytr = windows(0, split)
    xho, yho = windows(split, n)
    g = torch.Generator().manual_seed(777)
    perm = torch.randperm(xtr.size(0), generator=g)
    nt = xtr.size(0)
    sched = [perm[[(s * batch + j) % nt for j in range(batch)]] for s in range(steps)]
    return dict(vocab=vocab, seq=seq, batch=batch, steps=steps, xtr=xtr, ytr=ytr,
                xho=xho, yho=yho, sched=sched, uniform_ce=round(math.log(vocab), 4))


@torch.no_grad()
def _heldout(model, xho, yho, vocab, batch=32):
    model.eval()
    tot_ce, tot_ok, tot = 0.0, 0, 0
    for i in range(0, xho.size(0), batch):
        xb = xho[i:i + batch]
        yb = yho[i:i + batch, :xb.size(1)]               # primary next-token targets
        logits = model(xb)[0]
        tot_ce += float(F.cross_entropy(logits.reshape(-1, vocab), yb.reshape(-1), reduction="sum"))
        tot_ok += int((logits.argmax(-1) == yb).sum())
        tot += yb.numel()
    return tot_ce / max(1, tot), tot_ok / max(1, tot)


def evaluate_full(geno, data, *, lr=3e-3, seed=0):
    """End-to-last-end candidate test: structural oracle + cheap NAS proxy + PRE-TRAINING on the fixed
    shared corpus + final fp and int8-deployed held-out quality. Returns extended metrics + verdict."""
    vocab, seq, batch = data["vocab"], data["seq"], data["batch"]
    m = dict(code=0, err="none", params=0, model_bytes=0, latency_ms=0.0,
             proxy_gradnorm=0.0, recur_delta=-1.0, recur_ok=-1, causal_ok=-1, deterministic_ok=-1,
             init_ce=0.0, final_ce=0.0, quality_gain=0.0, heldout_acc=0.0, ppl=0.0,
             int8_ce=0.0, int8_acc=0.0, int8_ppl=0.0, quant_gap=0.0, uniform_ce=data["uniform_ce"],
             train_s=0.0, train_steps=data["steps"])
    t0 = time.perf_counter()
    try:
        torch.manual_seed(seed)
        model = build_model(geno)
        m["params"] = sum(p.numel() for p in model.parameters())
        m["model_bytes"] = sum(p.numel() * p.element_size() for p in model.parameters())
        xho, yho = data["xho"], data["yho"]
        xb0 = xho[:batch]

        model.eval()
        with torch.no_grad():
            ref = model(xb0)[0]
        if tuple(ref.shape) != (xb0.size(0), seq, vocab):
            m["code"], m["err"] = 1, "shape"; raise _Done
        if not bool(torch.isfinite(ref).all()):
            m["code"], m["err"] = 2, "nonfinite_init"; raise _Done
        with torch.no_grad():
            m["deterministic_ok"] = int(torch.equal(ref, model(xb0)[0]))
        if not m["deterministic_ok"]:
            m["code"], m["err"] = 5, "nondet"; raise _Done
        with torch.no_grad():
            ok, _ = _causal_audit(model, xb0, ref, vocab, max_checks=3)
        m["causal_ok"] = int(ok)
        if not ok:
            m["code"], m["err"] = 4, "causal"; raise _Done
        with torch.no_grad():
            m["recur_delta"] = round(_recurrence_delta(model, xb0), 9)
        m["recur_ok"] = int(m["recur_delta"] <= 1e-3)
        if not m["recur_ok"]:
            m["code"], m["err"] = 7, "recur"; raise _Done

        with torch.no_grad():
            model(xb0)
            timings = []
            for _ in range(3):
                ts = time.perf_counter(); model(xb0); timings.append((time.perf_counter() - ts) * 1000.0)
        m["latency_ms"] = round(statistics.median(timings), 3)
        m["init_ce"] = round(_heldout(model, xho, yho, vocab)[0], 5)

        # cheap NAS proxy: gradient norm on the first training batch (init model)
        model.train()
        sel = data["sched"][0]
        loss0, _ = _objective(model, data["xtr"][sel], data["ytr"][sel], vocab)
        loss0.backward()
        gsq, finite = 0.0, True
        for p in model.parameters():
            if p.grad is not None:
                if not bool(torch.isfinite(p.grad).all()):
                    finite = False
                else:
                    gsq += float(p.grad.pow(2).sum())
        m["proxy_gradnorm"] = round(gsq ** 0.5, 4)
        if not finite or gsq <= 0.0:
            m["code"], m["err"] = 3, "grad"; raise _Done
        model.zero_grad(set_to_none=True)

        # PRE-TRAINING (fixed schedule, Adam)
        opt = torch.optim.Adam(model.parameters(), lr=lr)
        model.train()
        for s in range(data["steps"]):
            sel = data["sched"][s]
            loss, _ = _objective(model, data["xtr"][sel], data["ytr"][sel], vocab)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()

        fce, facc = _heldout(model, xho, yho, vocab)
        if not math.isfinite(fce):
            m["code"], m["err"] = 2, "nonfinite_final"; raise _Done
        m["final_ce"], m["heldout_acc"] = round(fce, 5), round(facc, 4)
        m["ppl"] = round(math.exp(min(fce, 20)), 3)
        m["quality_gain"] = round(m["init_ce"] - fce, 5)

        # the very last end: quality of the int8-DEPLOYED model
        model.eval(); model.export_for_inference()
        ice, iacc = _heldout(model, xho, yho, vocab)
        m["int8_ce"], m["int8_acc"] = round(ice, 5), round(iacc, 4)
        m["int8_ppl"] = round(math.exp(min(ice, 20)), 3)
        m["quant_gap"] = round(ice - fce, 5)
    except _Done:
        pass
    except GenotypeError as exc:
        m["code"], m["err"] = 8, ("Geno:" + str(exc)[:60]).replace(" ", "_")
    except Exception as exc:  # noqa: BLE001
        m["code"], m["err"] = 9, (type(exc).__name__ + ":" + str(exc)[:60]).replace(" ", "_")
    m["train_s"] = round(time.perf_counter() - t0, 2)
    return m


# --------------------------------------------------------------------------------------------------
# FW_RunMeFirstOnce bootstrap  (one-time, run-level; NOT an axis)
# --------------------------------------------------------------------------------------------------
def bootstrap(threads: int = 4, compile_kernel: bool = True) -> dict:
    """One-time run-level setup: pin threads, seed, optionally compile the FX-8320 C++ kernel once
    (so the per-candidate sweep never pays for it), and run a single tiny end-to-end smoke."""
    torch.manual_seed(0)
    torch.set_num_threads(threads)
    info = {"threads": threads, "torch": torch.__version__, "kernel_backend": "fallback-int32"}
    if compile_kernel:
        import os, sys
        # The source chunks (considerme_as_upgrade4) live in the testme5upgraded tree; search a few
        # candidate locations so this campaign stays runnable wherever it is copied. Falls back to the
        # built-in int32 path if the chunk / compiler is unavailable (mix_arch is self-contained).
        candidates = [
            str(project_path("llm_transformer", "testme5upgraded", "considerme_as_upgrade4")),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "considerme_as_upgrade4"),
        ]
        up4 = next((p for p in candidates if os.path.isdir(p)), None)
        try:
            if up4 is None:
                raise FileNotFoundError("considerme_as_upgrade4 not found")
            if up4 not in sys.path:
                sys.path.insert(0, up4)
            import llm_transformer_testme5_fx8320_synth as synth
            ops = synth._load_ternary_ops()
            if ops is not None:
                info["kernel_backend"] = str(ops.ternary_kernel_backend())
        except Exception as exc:  # noqa: BLE001
            info["kernel_backend"] = "fallback-int32 (compile skipped: %s)" % type(exc).__name__
    smoke = evaluate(default_geno(), batch=2, seq=8)
    info["smoke_code"] = smoke["code"]
    info["smoke_loss_improvement"] = smoke["loss_improvement"]
    return info


if __name__ == "__main__":
    print("bootstrap:", bootstrap(compile_kernel=False))
    print("sample evaluate:", {k: evaluate(default_geno())[k] for k in
          ("code", "params", "latency_ms", "loss_improvement", "recur_delta", "int8_ok")})
