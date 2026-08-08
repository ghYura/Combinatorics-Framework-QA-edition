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

r"""surrogate_runner — plug the user's LEARNED surrogate (app.py: RandomForest +
confidence-gated oracle delegation + online learning) into the attack x guard matrix.

This swaps the deterministic mock surrogate for the REAL classifier from
$BUNDLE_SUT_ROOT/legacy_surrogate_apps/app.py, closing the two gaps that file has for this
domain: a featurization (attack,guard)->vector, and its oracle = our breach oracle
(severity with order effects). It demonstrates the genuine surrogate-assisted loop:

  • bootstrap the RF on a small labelled sample (the "expensive oracle" = our full
    breach function);
  • triage ALL 10,368 pairs cheaply; confidence < threshold => DELEGATE to the oracle
    (the real, uncertainty-driven frontier — the only expensive calls);
  • ONLINE LEARNING: retrain on bootstrap + the delegated hard cases => the surrogate
    learns the boundary and the frontier shrinks (self-improvement).

Reuses app.SurrogateModel untouched. No model/network; sklearn etc. already installed.
  python3 surrogate_runner.py
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

GENERATOR_ROOT = Path(__file__).resolve().parents[2]
if str(GENERATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(GENERATOR_ROOT))

from sut_paths import project_path  # noqa: E402

import matrix_spec as M
from surrogate_executor import OUT, features as feat_dict, severity

sys.path.insert(0, str(project_path("legacy_surrogate_apps")))          # where app.py lives
import app                                                    # noqa: E402
app.MODEL_PATH = str(OUT / "surrogate_model.pkl")             # keep the .pkl under scratch
from app import SurrogateModel, CONFIDENCE_THRESHOLD          # noqa: E402

TECH = {"direct": 0, "leak": 1, "delimiter": 2, "roleplay": 3}
GUARD = {g: i for i, g in enumerate(M.GUARDS)}
LANG = {"en": 0, "de": 1, "ru": 2}


def featurize(lab: dict) -> list:
    obf = set() if lab["obfuscation"] == "none" else set(lab["obfuscation"].split("+"))
    order = lab["order"].split(">")
    ramp = order.index("persuade") < order.index("escalate")
    return [float(TECH[lab["technique"]]), float(len(obf)),
            float("unicode" in obf), float("homoglyph" in obf), float("leet" in obf),
            float(lab["role"] == "dev"), float(lab["role"] == "grandma"),
            float(LANG[lab["lang"]]), float(lab["lang"] != "en"), float(ramp),
            float(GUARD[lab["guard"]])]


def oracle(lab: dict) -> int:                                 # the EXPENSIVE function the surrogate approximates
    return 1 if severity(feat_dict(lab), use_order=True) > 0 else 0


def triage(model, pairs):
    """Return (confident_correct, confident_total, delegations, used_labels)."""
    cc = ct = deleg = 0
    used = []
    for _idx, lab, _t in pairs:
        out = model.predict_proba(featurize(lab))
        pred, conf = out["prediction"], out["confidence"]
        truth = oracle(lab)
        if conf >= CONFIDENCE_THRESHOLD:                      # cheap surrogate path
            ct += 1; cc += (pred == truth)
            used.append((lab["guard"], pred))
        else:                                                 # uncertainty frontier -> expensive oracle
            deleg += 1
            used.append((lab["guard"], truth))
    return cc, ct, deleg, used


def matrix_breach(used):
    agg = {g: [0, 0] for g in M.GUARDS}
    for g, lab in used:
        agg[g][0] += lab; agg[g][1] += 1
    return {g: (100.0 * a[0] / a[1] if a[1] else 0.0) for g, (a) in
            ((g, agg[g]) for g in M.GUARDS)}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pairs = list(M.reassemble())
    random.seed(42)
    print(f"=== LEARNED surrogate (app.py RandomForest) on the {len(pairs):,}-pair matrix ===")
    print(f"  confidence threshold = {CONFIDENCE_THRESHOLD}  (below => delegate to the oracle)")

    # ground truth (the full oracle on everything — for fidelity scoring only)
    truth_rate = matrix_breach([(lab["guard"], oracle(lab)) for _i, lab, _t in pairs])

    # --- bootstrap the surrogate on a small labelled sample ---
    boot = random.sample(pairs, 400)
    Xb = [featurize(l) for _i, l, _t in boot]
    yb = [oracle(l) for _i, l, _t in boot]
    model = SurrogateModel()
    model.train(Xb, yb)
    print(f"\n  [v1] bootstrapped on {len(boot)} oracle-labelled pairs")

    # --- triage ALL pairs with v1 ---
    cc, ct, deleg, used = triage(model, pairs)
    acc = 100.0 * cc / max(1, ct)
    print(f"  [v1] surrogate handled {ct:,} confidently (acc {acc:.1f}% vs oracle); "
          f"DELEGATED {deleg:,} uncertain to the oracle")
    print(f"       expensive oracle calls = {deleg:,} of {len(pairs):,}  "
          f"=>  {len(pairs)//max(1,deleg)}x fewer than scoring all with the oracle")

    # --- ONLINE LEARNING: retrain on bootstrap + delegated hard cases, re-triage ---
    hard = [(lab) for (_i, lab, _t) in pairs
            if model.predict_proba(featurize(lab))["confidence"] < CONFIDENCE_THRESHOLD]
    Xc = Xb + [featurize(l) for l in hard]
    yc = yb + [oracle(l) for l in hard]
    model.train(Xc, yc)
    cc2, ct2, deleg2, used2 = triage(model, pairs)
    acc2 = 100.0 * cc2 / max(1, ct2)
    print(f"\n  [v2] retrained on bootstrap + {len(hard):,} delegated hard cases (online/self-focus)")
    print(f"  [v2] confident {ct2:,} (acc {acc2:.1f}%); DELEGATED {deleg2:,}  "
          f"(frontier {('shrank' if deleg2 < deleg else 'changed')} {deleg:,} -> {deleg2:,})")

    # --- fidelity: does the learned surrogate reproduce the vulnerability matrix? ---
    pred_rate = matrix_breach(used2)
    print(f"\n=== vulnerability matrix: LEARNED surrogate vs ground-truth oracle ===")
    print(f"  {'guard':<24}{'surrogate%':>11}{'oracle%':>9}{'Δ':>7}")
    for g in M.GUARDS:
        print(f"  {g:<24}{pred_rate[g]:>10.1f}%{truth_rate[g]:>8.1f}%{pred_rate[g]-truth_rate[g]:>+7.1f}")

    print(f"\nsurrogate model → {app.MODEL_PATH}")
    print("(production path: run app.py via uvicorn and POST /predict per pair — same model, "
          "with background oracle delegation + buffer retrain, per the manual.)")


if __name__ == "__main__":
    main()
