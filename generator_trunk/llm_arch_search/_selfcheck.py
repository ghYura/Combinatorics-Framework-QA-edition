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
Standalone verification of arch_zoo: enumerate the SAME combinatorial space the
Bundle `arch_grid` spec generates, build + forward + backward + proxy every variant,
and assert correctness. Also confirm the fail-loud contract on an incompatible
genotype. This proves the candidate logic independently of the DB pipeline.

Run:  python3 _selfcheck.py
"""
import itertools

import torch

import arch_zoo

torch.set_num_threads(1)

NORMS = ["rmsnorm", "layernorm"]
TOKMIX = ["mhsa", "swa", "linattn"]
CHANMIX = ["swiglu", "moe"]
PRENORM = [True, False]
DEPTH = [2, 3]

rows, bad = [], 0
for norm, tm, cm, pre, nl in itertools.product(NORMS, TOKMIX, CHANMIX, PRENORM, DEPTH):
    geno = dict(norm=norm, token_mixer=tm, channel_mixer=cm, prenorm=pre, n_layers=nl)
    m = arch_zoo.evaluate(geno, batch=2, seq=16, repeats=1)
    rows.append((norm, tm, cm, pre, nl, m))
    if (
        m["code"] != 0
        or m["causal_ok"] != 1
        or m["deterministic_ok"] != 1
        or m["grad_coverage"] <= 0.0
        or m["step_delta"] <= 0.0
        or m["loss_improvement"] <= 0.0
        or m["causal_checks"] != 15
    ):
        bad += 1
        print(
            "FAIL code=%d %s %s %s pre=%s L=%d causal=%d deterministic=%d "
            "coverage=%.3f step_delta=%.3g improvement=%.3g err=%s"
            % (
                m["code"], norm, tm, cm, pre, nl, m["causal_ok"],
                m["deterministic_ok"], m["grad_coverage"], m["step_delta"],
                m["loss_improvement"], m["err"],
            )
        )

n = len(rows)
params = [m["params"] for *_, m in rows]
lat = [m["latency_ms"] for *_, m in rows]
gn = [m["proxy_gradnorm"] for *_, m in rows]
print("arch_grid space: %d variants, %d PASS, %d defect" % (n, n - bad, bad))
print("params  : min %d  max %d" % (min(params), max(params)))
print("latency : min %.1f ms  max %.1f ms" % (min(lat), max(lat)))
print("gradnorm: min %.3f  max %.3f" % (min(gn), max(gn)))

# show the two extremes (smallest and a MoE one) as a sanity spot-check
sm = min(rows, key=lambda r: r[5]["params"])
print("smallest:", sm[:5], "params=%d gradnorm=%.3f" % (sm[5]["params"], sm[5]["proxy_gradnorm"]))
moe = next(r for r in rows if r[2] == "moe")
print("a MoE   :", moe[:5], "params=%d aux=%.3f gradnorm=%.3f"
      % (moe[5]["params"], moe[5]["aux"], moe[5]["proxy_gradnorm"]))

# fail-loud contract: an indivisible (d_model, n_heads) must be caught, NOT silently run
inv = arch_zoo.evaluate(dict(d_model=64, n_heads=6, token_mixer="mhsa"))
assert inv["code"] == 8, "expected fail-loud code 8 on incompatible genotype, got %d" % inv["code"]
print("fail-loud OK: incompatible (d_model=64,n_heads=6) -> code 8 (%s)" % inv["err"])

assert bad == 0, "%d valid variants failed — zoo is not correct" % bad
print(
    "OK: all %d valid variants build, preserve causality, reproduce outputs, "
    "backpropagate finite gradients, and reduce the same-batch objective." % n
)
