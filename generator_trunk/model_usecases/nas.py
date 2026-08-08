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

r"""nas — materialises the NEURAL-ARCHITECTURE-SEARCH half of Model proposition #3
as a Combinatorics-Framework use-case.

> "If we treat 'text chunks' as configuration files (neural network layers ...). The
>  program compiles different ML pipeline configurations, kicks off training, and
>  extracts Accuracy=0.94 and Memory_MB=450 ... multi-objective optimization to find the
>  best trade-off between accuracy and resource consumption."   — Model AI

The repo already covers the HYPERPARAMETER-tuning half (tinyml_*, k8s, postgres: scalar
knobs).  This adds the missing **architecture (topology) search**: the combinatorics breeds
the *shape* of the network — width, depth (an OPTIONAL second block), nonlinearity, and an
OPTIONAL regulariser — and every shape is REALLY TRAINED (scikit-learn MLP on a held-out
split), so the verdict is a measured accuracy, not a guess.

Decomposition -> which FW_ rule breeds what:
  | block        | variants              | rule        | what it breeds
  | WIDTH1       | {4,8,16,32}           | FW_Combi(1) | capacity axis of layer 1
  | DEEP         | second layer on/off   | FW_Subsets  | DEPTH as a topology choice
  | WIDTH2       | {4,8,16}              | FW_Combi(1) | capacity of the optional layer
  | ACT          | {relu,tanh,logistic}  | FW_Combi(1) | nonlinearity
  | L2           | regulariser on/off    | FW_Subsets  | capacity-control interaction

Multi-objective (exactly Model's "best trade-off"): accuracy MAX, params MIN, fit_ms MIN.
The Analyzer's Pareto front is the set of non-dominated architectures — the data scientist
reads the knee, not a single number.  Real training, offline, deterministic (fixed seed,
no network).  `emit_toml()` writes the equivalent fwgen spec for the real Bundle.

  python3 nas.py
"""
from __future__ import annotations

import itertools
import sys
import time
from pathlib import Path

WIDTH1 = [4, 8, 16, 32]
WIDTH2 = [4, 8, 16]
ACTS = ["relu", "tanh", "logistic"]


# ------------------------- the architecture search space ---------------------- #
def architectures():
    """Yield every distinct architecture the FW_ rules breed (DEEP/L2 are FW_Subsets;
    widths/act are FW_Combi(1)).  WIDTH2 is only meaningful when DEEP is present, so the
    conditional collapse happens here (the Core breeds the raw product; equal architectures
    score identically and the Analyzer dedups by metric)."""
    seen = set()
    for w1, act, deep, l2 in itertools.product(WIDTH1, ACTS, (False, True), (False, True)):
        w2s = WIDTH2 if deep else [None]
        for w2 in w2s:
            hidden = (w1,) if w2 is None else (w1, w2)
            key = (hidden, act, l2)
            if key in seen:
                continue
            seen.add(key)
            yield {"hidden": hidden, "act": act, "l2": l2}


# --------------------------------- the oracle --------------------------------- #
def make_data():
    from sklearn.datasets import make_moons
    from sklearn.model_selection import train_test_split
    X, y = make_moons(n_samples=400, noise=0.22, random_state=0)
    return train_test_split(X, y, test_size=0.3, random_state=0)


def train_and_score(arch, data):
    """REALLY train the architecture; return (accuracy, n_params, fit_ms, converged)."""
    from sklearn.neural_network import MLPClassifier
    Xtr, Xte, ytr, yte = data
    clf = MLPClassifier(hidden_layer_sizes=arch["hidden"], activation=arch["act"],
                        alpha=(1e-2 if arch["l2"] else 1e-5),
                        max_iter=300, random_state=0)
    import warnings
    from sklearn.exceptions import ConvergenceWarning
    t0 = time.time()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConvergenceWarning)
        clf.fit(Xtr, ytr)
    fit_ms = (time.time() - t0) * 1000.0
    acc = clf.score(Xte, yte)
    n_params = sum(c.size for c in clf.coefs_) + sum(b.size for b in clf.intercepts_)
    return acc, n_params, fit_ms, bool(clf.n_iter_ < clf.max_iter)


def pareto_front(points):
    """points: list of dicts with acc(max), params(min). Return non-dominated subset."""
    front = []
    for p in points:
        dominated = any(q is not p and q["acc"] >= p["acc"] and q["params"] <= p["params"]
                        and (q["acc"] > p["acc"] or q["params"] < p["params"]) for q in points)
        if not dominated:
            front.append(p)
    return sorted(front, key=lambda p: p["params"])


# ------------------------------- emit fwgen spec ------------------------------ #
def _to_toml() -> str:
    L = ['title = "NAS #3 — neural ARCHITECTURE search (topology), real-trained, multi-objective"',
         'note  = "FW_Combi(1) breeds width/activation; FW_Subsets toggles a second layer (DEPTH) '
         'and an L2 regulariser. Each shape is really trained (sklearn MLP on make_moons); '
         'Analyzer returns the accuracy/params Pareto front (Model\'s best trade-off)."',
         'args  = ["dataset=make_moons_400_noise0.22", "split=0.3_holdout", "seed=0"]',
         '[[goals]]', 'key = "accuracy"', 'dir = "max"',
         '[[goals]]', 'key = "params"', 'dir = "min"',
         '[[goals]]', 'key = "fit_ms"', 'dir = "min"', ""]
    L += ['[[slots]]', 'sheet = "WIDTH1"', 'key = "width1"', 'verb = "FW_Combi(1)"',
          'values = [' + ", ".join(f'"{w}"' for w in WIDTH1) + ']', ""]
    L += ['[[slots]]', 'sheet = "DEEP"', 'key = "deep"', 'verb = "FW_Subsets"',
          'values = ["second_layer"]', ""]
    L += ['[[slots]]', 'sheet = "WIDTH2"', 'key = "width2"', 'verb = "FW_Combi(1)"',
          'values = [' + ", ".join(f'"{w}"' for w in WIDTH2) + ']', ""]
    L += ['[[slots]]', 'sheet = "ACT"', 'key = "act"', 'verb = "FW_Combi(1)"',
          'values = [' + ", ".join(f'"{a}"' for a in ACTS) + ']', ""]
    L += ['[[slots]]', 'sheet = "L2"', 'key = "l2"', 'verb = "FW_Subsets"',
          'values = ["l2_reg"]', ""]
    L += ['[[custom_vars]]', 'code = 2', 'msg  = "accuracy below threshold"',
          '[[custom_vars]]', 'code = 3', 'msg  = "training did not converge in max_iter"', ""]
    return "\n".join(L) + "\n"


def emit_toml(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_to_toml(), encoding="utf-8")
    print(f"  fwgen spec -> {path}")


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else
               str(Path(__file__).resolve().parent / "specs" / "nas_micronet.toml"))
    print("=== NAS (Model #3): real-trained architecture search, accuracy/params Pareto ===\n")
    try:
        data = make_data()
    except Exception as e:                            # pragma: no cover
        print(f"  (sklearn unavailable: {e}); emitting spec only")
        emit_toml(out)
        return

    pts = []
    for arch in architectures():
        acc, params, fit_ms, conv = train_and_score(arch, data)
        pts.append({"arch": arch, "acc": acc, "params": params, "fit_ms": fit_ms, "conv": conv})
    front = pareto_front(pts)
    best_acc = max(pts, key=lambda p: (p["acc"], -p["params"]))

    def shape(a):
        d = "x".join(str(h) for h in a["hidden"])
        return f"{d}/{a['act']}" + ("/L2" if a["l2"] else "")

    print(f"  architectures really trained : {len(pts)}")
    print(f"  best accuracy overall        : {best_acc['acc']:.3f}  "
          f"[{shape(best_acc['arch'])}, params={best_acc['params']}]")
    print(f"\n  PARETO FRONT (accuracy MAX vs params MIN) — {len(front)} non-dominated architectures:")
    print(f"    {'architecture':<22}{'accuracy':>9}{'params':>8}{'fit_ms':>9}")
    for p in front:
        print(f"    {shape(p['arch']):<22}{p['acc']:>9.3f}{p['params']:>8}{p['fit_ms']:>8.1f}  "
              f"K=V -> accuracy={p['acc']:.3f} params={p['params']} fit_ms={p['fit_ms']:.1f}")
    # the trade-off headline: cheapest architecture within 1% of the best accuracy
    near = [p for p in front if p["acc"] >= best_acc["acc"] - 0.01]
    knee = min(near, key=lambda p: p["params"]) if near else front[0]
    print(f"\n  knee: {shape(knee['arch'])} is within 1% of the best accuracy "
          f"({knee['acc']:.3f} vs {best_acc['acc']:.3f}) at {knee['params']} params vs "
          f"{best_acc['params']} ({best_acc['params'] / max(1, knee['params']):.1f}x smaller) "
          f"— the trade-off the engine found.\n")
    emit_toml(out)


if __name__ == "__main__":
    main()
