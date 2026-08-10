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

"""
arch_zoo — a small, FAIL-LOUD library of interchangeable Transformer components,
plus a genotype -> model factory, for COMBINATORIAL ARCHITECTURE SEARCH driven by
the Bundle (Combinatorics Framework).

This is the deliberate counter-design to the "universal polymorphic Transformer
constructor" reviewed in CombinatoricsInDesignOfLLMtransformers_Conversation2.txt.
That design tried to make *any* block fit *any* slot by silently synthesising
missing state, auto-projecting mismatched dims, and inferring residual-vs-replace
from tensor shape — turning incompatibilities into silently-wrong models.

Here the stance is inverted, matching the Bundle's "verbs x bonds x meaning":
  * Components are a TYPED CATALOG (role, causal, residual policy) -> see COMPONENTS.
  * build_model() VALIDATES and FAILS LOUD (raises ValueError) on an incompatible
    genotype. It never auto-projects, never synthesises, never guesses.
  * Residual-add vs state-replace is EXPLICIT in Block.forward, never inferred.
The combinatorics (which components, in which order, with which optional plugins)
lives in the Bundle spec (mechanics); compatibility pruning lives in the sieve
(bonds); this module only supplies correct, swappable parts + an honest evaluator.

CPU/tiny by design (an FX-8320-class box): every model here builds + does a
forward+backward in milliseconds, so the *outer* combinatorial search is the cost,
not any single candidate.
"""
import math
import statistics
import time
import torch
import torch.nn as nn
import torch.nn.functional as F


class GenotypeError(ValueError):
    """Invalid architecture or evaluator configuration supplied by the caller."""


# ===========================================================================
# 1. NORMALIZATION slots  (role="norm"; semantics: REPLACE the activation)
# ===========================================================================
class RMSNorm(nn.Module):
    def __init__(self, d_model, eps=1e-6):
        super().__init__()
        self.scale = nn.Parameter(torch.ones(d_model))
        self.eps = eps

    def forward(self, x):
        var = x.pow(2).mean(-1, keepdim=True)
        return x * torch.rsqrt(var + self.eps) * self.scale


class LayerNormSlot(nn.Module):
    def __init__(self, d_model, eps=1e-6):
        super().__init__()
        self.ln = nn.LayerNorm(d_model, eps=eps)

    def forward(self, x):
        return self.ln(x)


NORMS = {"rmsnorm": RMSNorm, "layernorm": LayerNormSlot}


# ===========================================================================
# 2. TOKEN MIXERS  (role="token_mixer"; causal; semantics: RESIDUAL delta)
#    All take and return [B, S, D].
# ===========================================================================
class MultiHeadSelfAttention(nn.Module):
    """Standard causal MHSA — real Q/K/V, scaled, causal-masked. O(S^2)."""

    def __init__(self, d_model, n_heads, **_):
        super().__init__()
        if d_model % n_heads != 0:
            raise ValueError("MHSA: d_model %d not divisible by n_heads %d" % (d_model, n_heads))
        self.h, self.dh = n_heads, d_model // n_heads
        self.qkv = nn.Linear(d_model, 3 * d_model, bias=False)
        self.out = nn.Linear(d_model, d_model, bias=False)

    def forward(self, x):
        B, S, D = x.shape
        q, k, v = self.qkv(x).chunk(3, dim=-1)
        q = q.view(B, S, self.h, self.dh).transpose(1, 2)
        k = k.view(B, S, self.h, self.dh).transpose(1, 2)
        v = v.view(B, S, self.h, self.dh).transpose(1, 2)
        att = (q @ k.transpose(-2, -1)) / math.sqrt(self.dh)
        causal = torch.triu(torch.ones(S, S, dtype=torch.bool, device=x.device), diagonal=1)
        att = att.masked_fill(causal, float("-inf")).softmax(dim=-1)
        y = (att @ v).transpose(1, 2).reshape(B, S, D)
        return self.out(y)


class SlidingWindowAttention(nn.Module):
    """Causal sliding-window attention — each token attends to <= `window` past tokens."""

    def __init__(self, d_model, n_heads, window=4, **_):
        super().__init__()
        if d_model % n_heads != 0:
            raise ValueError("SWA: d_model %d not divisible by n_heads %d" % (d_model, n_heads))
        if window < 1:
            raise ValueError("SWA: window must be >= 1, got %d" % window)
        self.h, self.dh, self.w = n_heads, d_model // n_heads, window
        self.qkv = nn.Linear(d_model, 3 * d_model, bias=False)
        self.out = nn.Linear(d_model, d_model, bias=False)

    def forward(self, x):
        B, S, D = x.shape
        q, k, v = self.qkv(x).chunk(3, dim=-1)
        q = q.view(B, S, self.h, self.dh).transpose(1, 2)
        k = k.view(B, S, self.h, self.dh).transpose(1, 2)
        v = v.view(B, S, self.h, self.dh).transpose(1, 2)
        att = (q @ k.transpose(-2, -1)) / math.sqrt(self.dh)
        i = torch.arange(S, device=x.device)
        future = i[None, :] > i[:, None]               # j > i  (no peeking ahead)
        too_old = (i[:, None] - i[None, :]) >= self.w   # i - j >= window
        att = att.masked_fill(future | too_old, float("-inf")).softmax(dim=-1)
        y = (att @ v).transpose(1, 2).reshape(B, S, D)
        return self.out(y)


class LinearAttention(nn.Module):
    """Causal linear attention via an (elu+1) feature map + prefix sums.

    NO S x S score matrix is ever materialised — contrast the 'falsely quadratic'
    linear attention in the reviewed Conversation2 design (Automation found the same in
    the testme variants). Memory is O(S * h * dh^2), no O(S^2) term.
    """

    def __init__(self, d_model, n_heads, **_):
        super().__init__()
        if d_model % n_heads != 0:
            raise ValueError("LinAttn: d_model %d not divisible by n_heads %d" % (d_model, n_heads))
        self.h, self.dh = n_heads, d_model // n_heads
        self.qkv = nn.Linear(d_model, 3 * d_model, bias=False)
        self.out = nn.Linear(d_model, d_model, bias=False)

    @staticmethod
    def _phi(t):
        return F.elu(t) + 1.0

    def forward(self, x):
        B, S, D = x.shape
        q, k, v = self.qkv(x).chunk(3, dim=-1)
        q = self._phi(q.view(B, S, self.h, self.dh))
        k = self._phi(k.view(B, S, self.h, self.dh))
        v = v.view(B, S, self.h, self.dh)
        kv = torch.einsum("bshd,bshe->bshde", k, v).cumsum(dim=1)   # causal prefix of k⊗v
        z = k.cumsum(dim=1)                                          # causal prefix of k
        num = torch.einsum("bshd,bshde->bshe", q, kv)
        den = torch.einsum("bshd,bshd->bsh", q, z).clamp_min(1e-6).unsqueeze(-1)
        y = (num / den).reshape(B, S, D)
        return self.out(y)


TOKEN_MIXERS = {
    "mhsa": MultiHeadSelfAttention,
    "swa": SlidingWindowAttention,
    "linattn": LinearAttention,
}


# ===========================================================================
# 3. CHANNEL MIXERS  (role="channel_mixer"; semantics: RESIDUAL delta)
#    MoE stashes its load-balance aux loss on `.last_aux` (read by TinyLM).
# ===========================================================================
class SwiGLUFFN(nn.Module):
    def __init__(self, d_model, d_ffn, **_):
        super().__init__()
        self.w_gate = nn.Linear(d_model, d_ffn, bias=False)
        self.w_up = nn.Linear(d_model, d_ffn, bias=False)
        self.w_down = nn.Linear(d_ffn, d_model, bias=False)
        self.last_aux = None

    def forward(self, x):
        return self.w_down(F.silu(self.w_gate(x)) * self.w_up(x))


class MoEFFN(nn.Module):
    """Top-k token-choice MoE with a Switch-style load-balancing aux loss."""

    def __init__(self, d_model, d_ffn, num_experts=4, top_k=2, **_):
        super().__init__()
        if num_experts < 1:
            raise ValueError("MoE: num_experts must be >= 1, got %d" % num_experts)
        if not (1 <= top_k <= num_experts):
            raise ValueError("MoE: need 1 <= top_k <= num_experts (top_k=%d, experts=%d)"
                             % (top_k, num_experts))
        self.ne, self.k = num_experts, top_k
        self.router = nn.Linear(d_model, num_experts, bias=False)
        self.experts = nn.ModuleList([
            nn.Sequential(nn.Linear(d_model, d_ffn, bias=False), nn.SiLU(),
                          nn.Linear(d_ffn, d_model, bias=False))
            for _ in range(num_experts)])
        self.last_aux = None

    def forward(self, x):
        B, S, D = x.shape
        xf = x.reshape(B * S, D)
        probs = self.router(xf).softmax(dim=-1)            # N, ne
        topv, topi = probs.topk(self.k, dim=-1)            # N, k
        topv = topv / topv.sum(dim=-1, keepdim=True).clamp_min(1e-9)
        # Evaluate each expert over the same token matrix, then gather only the
        # selected outputs. Besides removing Python routing loops, this keeps a
        # prefix token's GEMM shape independent of suffix routing, so a causal
        # model is bit-identical under suffix perturbations.
        all_outputs = torch.stack([expert(xf) for expert in self.experts], dim=1)
        selected = all_outputs.gather(
            1, topi.unsqueeze(-1).expand(-1, -1, D)
        )
        out = (selected * topv.unsqueeze(-1)).sum(dim=1)
        importance = probs.mean(dim=0)                     # ne
        load = torch.stack([(topi == e).float().mean() for e in range(self.ne)])
        self.last_aux = self.ne * (importance * load).sum()
        return out.reshape(B, S, D)


CHANNEL_MIXERS = {"swiglu": SwiGLUFFN, "moe": MoEFFN}


# ===========================================================================
# 4. BLOCK + MODEL  (residual policy EXPLICIT: pre-norm or post-norm)
# ===========================================================================
class Block(nn.Module):
    def __init__(self, token_mixer, channel_mixer, norm_cls, d_model, prenorm=True):
        super().__init__()
        self.tm, self.cm = token_mixer, channel_mixer
        self.n1, self.n2 = norm_cls(d_model), norm_cls(d_model)
        self.prenorm = prenorm

    def forward(self, x):
        if self.prenorm:
            x = x + self.tm(self.n1(x))
            x = x + self.cm(self.n2(x))
        else:
            x = self.n1(x + self.tm(x))
            x = self.n2(x + self.cm(x))
        return x


DEFAULTS = dict(
    vocab=64, d_model=64, n_heads=4, d_ffn=128, num_experts=4, top_k=2,
    window=4, max_seq_len=64, n_layers=2, prenorm=True, norm="rmsnorm",
    token_mixer="mhsa", channel_mixer="swiglu",
    tie_head=False, extra_final_norm=False, layers=None,
)


def _require_int(g, name, minimum):
    value = g[name]
    if isinstance(value, bool) or not isinstance(value, int):
        raise GenotypeError("%s must be an integer, got %r" % (name, value))
    if value < minimum:
        raise GenotypeError("%s must be >= %d, got %d" % (name, minimum, value))


def _validate(geno):
    """Return a fully-resolved, valid genotype or fail loudly."""
    if not isinstance(geno, dict):
        raise GenotypeError("genotype must be a dict, got %s" % type(geno).__name__)
    unknown = sorted(set(geno) - set(DEFAULTS))
    if unknown:
        raise GenotypeError("unknown genotype key(s): %s" % ",".join(unknown))

    g = dict(DEFAULTS)
    g.update(geno)
    for name, minimum in (
        ("vocab", 2),
        ("d_model", 1),
        ("n_heads", 1),
        ("d_ffn", 1),
        ("num_experts", 1),
        ("top_k", 1),
        ("window", 1),
        ("max_seq_len", 2),
        ("n_layers", 1),
    ):
        _require_int(g, name, minimum)
    for name in ("prenorm", "tie_head", "extra_final_norm"):
        if not isinstance(g[name], bool):
            raise GenotypeError("%s must be bool, got %r" % (name, g[name]))

    if g["norm"] not in NORMS:
        raise GenotypeError("unknown norm %r (have %s)" % (g["norm"], list(NORMS)))
    if g["token_mixer"] not in TOKEN_MIXERS:
        raise GenotypeError(
            "unknown token_mixer %r (have %s)"
            % (g["token_mixer"], list(TOKEN_MIXERS))
        )
    if g["channel_mixer"] not in CHANNEL_MIXERS:
        raise GenotypeError(
            "unknown channel_mixer %r (have %s)"
            % (g["channel_mixer"], list(CHANNEL_MIXERS))
        )
    if g["d_model"] % g["n_heads"] != 0:
        raise GenotypeError(
            "d_model %d not divisible by n_heads %d"
            % (g["d_model"], g["n_heads"])
        )
    if g["top_k"] > g["num_experts"]:
        raise GenotypeError(
            "top_k %d exceeds num_experts %d"
            % (g["top_k"], g["num_experts"])
        )

    explicit_layers = g["layers"] is not None
    if explicit_layers:
        if not isinstance(g["layers"], (list, tuple)) or not g["layers"]:
            raise GenotypeError("layers must be a non-empty list/tuple")
        layers = []
        expected_keys = {"token_mixer", "channel_mixer"}
        for index, spec in enumerate(g["layers"]):
            if not isinstance(spec, dict):
                raise GenotypeError("layers[%d] must be a dict" % index)
            unknown_layer = sorted(set(spec) - expected_keys)
            missing_layer = sorted(expected_keys - set(spec))
            if unknown_layer or missing_layer:
                raise GenotypeError(
                    "layers[%d] keys invalid (missing=%s unknown=%s)"
                    % (index, missing_layer, unknown_layer)
                )
            layers.append(dict(spec))
    else:
        layers = [
            {
                "token_mixer": g["token_mixer"],
                "channel_mixer": g["channel_mixer"],
            }
            for _ in range(g["n_layers"])
        ]

    if explicit_layers and "n_layers" in geno and g["n_layers"] != len(layers):
        raise GenotypeError(
            "n_layers %d disagrees with explicit layers length %d"
            % (g["n_layers"], len(layers))
        )

    for spec in layers:
        if spec["token_mixer"] not in TOKEN_MIXERS:
            raise GenotypeError(
                "unknown token_mixer %r (have %s)"
                % (spec["token_mixer"], list(TOKEN_MIXERS))
            )
        if spec["channel_mixer"] not in CHANNEL_MIXERS:
            raise GenotypeError(
                "unknown channel_mixer %r (have %s)"
                % (spec["channel_mixer"], list(CHANNEL_MIXERS))
            )
    g["layers"] = layers
    g["n_layers"] = len(layers)
    return g


class TinyLM(nn.Module):
    def __init__(self, geno):
        super().__init__()
        g = _validate(geno)
        self.g = g
        V, D, Smax = g["vocab"], g["d_model"], g["max_seq_len"]
        norm_cls = NORMS[g["norm"]]
        self.tok = nn.Embedding(V, D)
        self.pos = nn.Embedding(Smax, D)
        self.blocks = nn.ModuleList([
            Block(TOKEN_MIXERS[s["token_mixer"]](D, g["n_heads"], window=g["window"]),
                  CHANNEL_MIXERS[s["channel_mixer"]](D, g["d_ffn"],
                                                     num_experts=g["num_experts"], top_k=g["top_k"]),
                  norm_cls, D, prenorm=g["prenorm"])
            for s in g["layers"]])
        self.norm_f = norm_cls(D)
        self.extra_norm = norm_cls(D) if g["extra_final_norm"] else None
        self.head = nn.Linear(D, V, bias=False)
        if g["tie_head"]:
            self.head.weight = self.tok.weight   # weight tying (both [V, D])
        self.max_seq_len = Smax

    def forward(self, idx):
        B, S = idx.shape
        if S > self.max_seq_len:
            raise GenotypeError("seq_len %d exceeds max_seq_len %d" % (S, self.max_seq_len))
        pos = torch.arange(S, device=idx.device)
        x = self.tok(idx) + self.pos(pos)[None, :, :]
        for blk in self.blocks:
            x = blk(x)
        x = self.norm_f(x)
        if self.extra_norm is not None:
            x = self.extra_norm(x)
        return self.head(x)

    def aux_loss(self):
        tot = None
        for m in self.modules():
            a = getattr(m, "last_aux", None)
            if a is not None:
                tot = a if tot is None else tot + a
        return tot


def build_model(geno):
    """The genotype -> model factory. Fail-loud on any incompatible genotype."""
    return TinyLM(geno)


# A small TYPED CATALOG — the "component contract" the Conversation2 design lacked.
COMPONENTS = {
    "norm":          {k: {"role": "norm", "semantics": "replace"} for k in NORMS},
    "token_mixer":   {"mhsa":    {"role": "token_mixer", "causal": True, "cost": "O(S^2)"},
                      "swa":     {"role": "token_mixer", "causal": True, "cost": "O(S*w)"},
                      "linattn": {"role": "token_mixer", "causal": True, "cost": "O(S)"}},
    "channel_mixer": {"swiglu":  {"role": "channel_mixer", "stateful": False},
                      "moe":     {"role": "channel_mixer", "stateful": False, "aux_loss": True}},
}


# ===========================================================================
# 5. EVALUATOR  (the "meaning" layer's oracle — used by every Bundle candidate)
# ===========================================================================
def _causal_audit(model, tokens, reference, vocab):
    """Exhaustively test every prefix/suffix boundary, preserving batch shape."""
    sequence = tokens.shape[1]
    for cutoff in range(1, sequence):
        perturbed = tokens.clone()
        perturbed[:, cutoff:] = (perturbed[:, cutoff:] + 1) % vocab
        candidate = model(perturbed)
        if not torch.equal(reference[:, :cutoff], candidate[:, :cutoff]):
            return False, cutoff
    return True, sequence - 1


def _objective(model, tokens, targets, vocab):
    logits = model(tokens)
    if tuple(logits.shape) != (*tokens.shape, vocab):
        raise RuntimeError(
            "training forward returned shape %r" % (tuple(logits.shape),)
        )
    loss = F.cross_entropy(logits.reshape(-1, vocab), targets.reshape(-1))
    auxiliary = model.aux_loss()
    if auxiliary is not None:
        loss = loss + 0.01 * auxiliary
    return loss, auxiliary


def _sgd_step(model, learning_rate):
    """Apply one explicit SGD step and return the actual global update norm."""
    snapshots = []
    with torch.no_grad():
        for parameter in model.parameters():
            if parameter.requires_grad and parameter.grad is not None:
                snapshots.append((parameter, parameter.detach().clone()))
                parameter.add_(parameter.grad, alpha=-learning_rate)
        delta_square = sum(
            float((parameter.detach() - before).pow(2).sum())
            for parameter, before in snapshots
        )
    return delta_square ** 0.5


def evaluate(
    geno,
    batch=2,
    seq=16,
    seed=0,
    repeats=1,
    learning_rate=1e-3,
    benchmark_threads=None,
):
    """Build and audit one architecture with cheap, deterministic proxies.

    Verdict ``code``:
      0 valid; 1 wrong shape; 2 non-finite output/loss; 3 absent/non-finite
      gradients; 4 causal leak; 5 non-deterministic output; 6 optimizer failed
      to reduce the same-batch objective; 8 incompatible genotype/config caught
      fail-loud; 9 unexpected implementation/runtime crash.

    ``causal_ok`` and ``deterministic_ok`` use -1 when a preceding shape/finite
    failure made that check unavailable. ``latency_ms`` is median inference
    latency after one warm-up; ``eval_ms`` is the complete audit wall time.
    """
    metrics = dict(
        app="arch", params=0, model_bytes=0, build_ms=0.0, latency_ms=0.0,
        eval_ms=0.0, fwd_ms=0.0, tokens_per_s=0.0, out_std=0.0, loss=0.0,
        proxy_gradnorm=0.0, grad_coverage=0.0, nonzero_grad_coverage=0.0,
        step_delta=0.0, loss_after_step=0.0, loss_improvement=0.0, aux=0.0,
        causal_ok=-1, causal_checks=0, deterministic_ok=-1,
        benchmark_threads=torch.get_num_threads(), code=0, err="none",
    )
    started = time.perf_counter()
    previous_threads = None
    try:
        for name, value, minimum in (
            ("batch", batch, 1),
            ("seq", seq, 2),
            ("repeats", repeats, 1),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise GenotypeError("%s must be an integer" % name)
            if value < minimum:
                raise GenotypeError("%s must be >= %d" % (name, minimum))
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise GenotypeError("seed must be an integer")
        if (
            isinstance(learning_rate, bool)
            or not isinstance(learning_rate, (int, float))
            or not math.isfinite(float(learning_rate))
            or learning_rate <= 0
        ):
            raise GenotypeError("learning_rate must be finite and > 0")
        if benchmark_threads is not None:
            if (
                isinstance(benchmark_threads, bool)
                or not isinstance(benchmark_threads, int)
                or benchmark_threads < 1
            ):
                raise GenotypeError("benchmark_threads must be an integer >= 1")
            previous_threads = torch.get_num_threads()
            if previous_threads != benchmark_threads:
                torch.set_num_threads(benchmark_threads)
            metrics["benchmark_threads"] = benchmark_threads

        torch.manual_seed(seed)
        build_started = time.perf_counter()
        model = build_model(geno)
        metrics["build_ms"] = round(
            (time.perf_counter() - build_started) * 1000.0, 3
        )
        metrics["params"] = sum(
            parameter.numel() for parameter in model.parameters()
        )
        metrics["model_bytes"] = sum(
            parameter.numel() * parameter.element_size()
            for parameter in model.parameters()
        )
        vocab, max_sequence = model.g["vocab"], model.g["max_seq_len"]
        if seq > max_sequence:
            raise GenotypeError(
                "seq %d exceeds model max_seq_len %d" % (seq, max_sequence)
            )
        tokens = torch.randint(0, vocab, (batch, seq))

        model.eval()
        with torch.no_grad():
            reference = model(tokens)
        if tuple(reference.shape) != (batch, seq, vocab):
            metrics["code"] = 1
            metrics["err"] = "wrong_eval_shape"
        elif not bool(torch.isfinite(reference).all()):
            metrics["code"] = 2
            metrics["err"] = "nonfinite_eval_output"
        else:
            with torch.no_grad():
                repeated = model(tokens)
            metrics["deterministic_ok"] = int(
                torch.equal(reference, repeated)
            )
            if not metrics["deterministic_ok"]:
                metrics["code"] = 5
                metrics["err"] = "nondeterministic_eval"
            else:
                with torch.no_grad():
                    causal_ok, failed_cutoff = _causal_audit(
                        model, tokens, reference, vocab
                    )
                metrics["causal_checks"] = seq - 1
                metrics["causal_ok"] = int(causal_ok)
                if not causal_ok:
                    metrics["code"] = 4
                    metrics["err"] = "causal_leak_at_cutoff_%d" % failed_cutoff

        if metrics["code"] == 0:
            with torch.no_grad():
                model(tokens)
                timings = []
                for _ in range(repeats):
                    forward_started = time.perf_counter()
                    model(tokens)
                    timings.append(
                        (time.perf_counter() - forward_started) * 1000.0
                    )
            metrics["latency_ms"] = round(statistics.median(timings), 3)
            metrics["fwd_ms"] = metrics["latency_ms"]
            if metrics["latency_ms"] > 0:
                metrics["tokens_per_s"] = round(
                    batch * seq * 1000.0 / metrics["latency_ms"], 1
                )

            metrics["out_std"] = round(float(reference.std()), 4)
            model.train()
            targets = torch.randint(0, vocab, (batch, seq))
            loss, auxiliary = _objective(model, tokens, targets, vocab)
            if auxiliary is not None:
                metrics["aux"] = round(float(auxiliary.detach()), 4)
            metrics["loss"] = round(float(loss.detach()), 4)
            if not bool(torch.isfinite(loss)):
                metrics["code"] = 2
                metrics["err"] = "nonfinite_training_loss"
            else:
                loss.backward()
                grad_square = 0.0
                grad_numel = 0
                nonzero_grad_numel = 0
                trainable_numel = 0
                gradients_finite = True
                for parameter in model.parameters():
                    if not parameter.requires_grad:
                        continue
                    trainable_numel += parameter.numel()
                    if parameter.grad is None:
                        continue
                    grad_numel += parameter.numel()
                    if not bool(torch.isfinite(parameter.grad).all()):
                        gradients_finite = False
                        continue
                    nonzero_grad_numel += int(torch.count_nonzero(parameter.grad))
                    grad_square += float(parameter.grad.pow(2).sum())
                metrics["grad_coverage"] = round(
                    grad_numel / max(1, trainable_numel), 4
                )
                metrics["nonzero_grad_coverage"] = round(
                    nonzero_grad_numel / max(1, trainable_numel), 4
                )
                metrics["proxy_gradnorm"] = round(grad_square ** 0.5, 4)
                if (
                    not gradients_finite
                    or not math.isfinite(grad_square)
                    or grad_square <= 0.0
                ):
                    metrics["code"] = 3
                    metrics["err"] = "absent_or_nonfinite_gradients"
                else:
                    step_delta = _sgd_step(model, float(learning_rate))
                    metrics["step_delta"] = round(step_delta, 10)
                    model.train()
                    with torch.no_grad():
                        after_loss, _ = _objective(
                            model, tokens, targets, vocab
                        )
                    metrics["loss_after_step"] = round(float(after_loss), 6)
                    improvement = float(loss.detach() - after_loss)
                    metrics["loss_improvement"] = round(improvement, 8)
                    if not bool(torch.isfinite(after_loss)):
                        metrics["code"] = 2
                        metrics["err"] = "nonfinite_post_step_loss"
                    elif (
                        not math.isfinite(step_delta)
                        or step_delta <= 0.0
                        or improvement <= 0.0
                    ):
                        metrics["code"] = 6
                        metrics["err"] = "optimizer_did_not_reduce_loss"
    except GenotypeError as error:
        metrics["code"] = 8
        metrics["err"] = (
            type(error).__name__ + ":" + str(error)[:96]
        ).replace(" ", "_")
    except Exception as error:
        metrics["code"] = 9
        metrics["err"] = (
            type(error).__name__ + ":" + str(error)[:96]
        ).replace(" ", "_")
    finally:
        if (
            previous_threads is not None
            and torch.get_num_threads() != previous_threads
        ):
            torch.set_num_threads(previous_threads)
    metrics["eval_ms"] = round(
        (time.perf_counter() - started) * 1000.0, 1
    )
    return metrics
