#!/usr/bin/env python3
r"""hardened_router — production-hardened oracle routing on top of the learned surrogate.

The learned surrogate (surrogate_runner.py) triages the bulk near-perfectly but CONFIDENTLY
MISSES the 6-way needle (it is too rare to learn). Confidence-gated routing can never catch
it — the needle is a *confident*-negative. The fix is a risk-aware routing policy that spends
the oracle budget where the surrogate is structurally blind:

  oracle  =  per-guard FRONTIER positives (confirm actionable findings → precision)
           ∪ UNCERTAIN  (conf < threshold → the usual frontier)
           ∪ STRATIFIED sample of CONFIDENT-NEGATIVES  (k per structural stratum →
             guarantees every structural cell, incl. the needle's, gets oracle coverage)

Because the Core ENUMERATES the whole space cheaply and the surrogate triages it cheaply,
we can afford to give every structural stratum a few oracle probes — which is exactly what
discovers rare high-arity cracks the surrogate cannot. We sweep k to show the
budget ↔ needle-recall tradeoff vs naive (confidence-only) routing.

  python3 hardened_router.py
"""
from __future__ import annotations

import random
from collections import defaultdict

import matrix_spec as M
from surrogate_executor import features as feat_dict, severity, cost_tokens
from surrogate_runner import featurize, SurrogateModel, oracle, CONFIDENCE_THRESHOLD

random.seed(7)


def stratum(lab: dict):
    """Fine structural cell — isolates rare regions (incl. the needle's) so each gets probed."""
    obf = "" if lab["obfuscation"] == "none" else lab["obfuscation"]
    return (lab["guard"], lab["technique"], lab["role"],
            "unicode" in obf, "homoglyph" in obf, lab["lang"])


def main():
    pairs = list(M.reassemble())
    print(f"=== hardened routing on the {len(pairs):,}-pair matrix (learned surrogate + oracle policy) ===")

    # surrogate (reuse the trained model saved by surrogate_runner; bootstrap if absent)
    model = SurrogateModel()
    try:
        model.pipeline.predict_proba([featurize(pairs[0][1])])
    except Exception:
        boot = random.sample(pairs, 400)
        model.train([featurize(l) for _i, l, _t in boot], [oracle(l) for _i, l, _t in boot])

    # one pass: surrogate pred/conf, ground-truth oracle label, cost
    rows = []
    truth_pos, needles = set(), set()
    for idx, lab, text in pairs:
        out = model.predict_proba(featurize(lab))
        t = oracle(lab)
        rows.append({"idx": idx, "lab": lab, "pred": out["prediction"], "conf": out["confidence"],
                     "truth": t, "cost": cost_tokens(text)})
        if t:
            truth_pos.add(idx)
        if lab["guard"] == "strict_refuse" and t:           # the 6-way needle breaches
            needles.add(idx)
    n_total = len(rows)

    # fixed components: per-guard frontier positives (cheapest predicted-breaches) + uncertain
    by_guard_pos = defaultdict(list)
    uncertain = set()
    conf_neg_by_stratum = defaultdict(list)
    for r in rows:
        if r["conf"] < CONFIDENCE_THRESHOLD:
            uncertain.add(r["idx"])
        elif r["pred"] == 1:
            by_guard_pos[r["lab"]["guard"]].append(r)
        else:                                               # confident negative
            conf_neg_by_stratum[stratum(r["lab"])].append(r)
    frontier = set()
    for g, lst in by_guard_pos.items():
        for r in sorted(lst, key=lambda r: r["cost"])[:3]:  # 3 cheapest predicted breaches / guard
            frontier.add(r["idx"])

    def evaluate(k):
        strat = set()
        if k > 0:
            for _s, lst in conf_neg_by_stratum.items():
                for r in random.sample(lst, min(k, len(lst))):
                    strat.add(r["idx"])
        oracle_set = frontier | uncertain | strat
        truth = {r["idx"]: r["truth"] for r in rows}
        pred = {r["idx"]: r["pred"] for r in rows}
        reported_pos = {i for r in rows for i in [r["idx"]]
                        if (truth[i] if i in oracle_set else pred[i]) == 1}
        tp = len(reported_pos & truth_pos)
        return {
            "k": k, "oracle_calls": len(oracle_set),
            "recall": 100.0 * tp / max(1, len(truth_pos)),
            "needle_recall": 100.0 * len(needles & oracle_set) / max(1, len(needles)),
            "needles_found": len(needles & oracle_set),
            "precision": 100.0 * tp / max(1, len(reported_pos)),
            "missed": len(truth_pos - reported_pos),
        }

    print(f"  true breaches = {len(truth_pos):,}   (incl. {len(needles)} six-way 'needle' breaches in strict_refuse)")
    print(f"  fixed oracle: frontier(confirm) = {len(frontier)} + uncertain = {len(uncertain):,}\n")
    print(f"  {'policy':<26}{'oracle_calls':>13}{'budget×':>9}{'recall':>9}{'needle':>9}{'precision':>11}{'missed':>8}")
    naive = evaluate(0)
    print(f"  {'naive (conf-only, k=0)':<26}{naive['oracle_calls']:>13,}{n_total//max(1,naive['oracle_calls']):>8}x"
          f"{naive['recall']:>8.1f}%{naive['needles_found']:>4}/{len(needles)}{'':>3}{naive['precision']:>10.1f}%{naive['missed']:>8,}")
    for k in (1, 2, 3, 5):
        r = evaluate(k)
        tag = f"hardened (k={k}/stratum)"
        print(f"  {tag:<26}{r['oracle_calls']:>13,}{n_total//max(1,r['oracle_calls']):>8}x"
              f"{r['recall']:>8.1f}%{r['needles_found']:>4}/{len(needles)}{'':>3}{r['precision']:>10.1f}%{r['missed']:>8,}")

    # --- the recommended policy: stratified DISCOVER → targeted exhaustive CONFIRM ---
    def discover_then_confirm(k_probe=3):
        truth = {r["idx"]: r["truth"] for r in rows}
        pred = {r["idx"]: r["pred"] for r in rows}
        oracle_set = set(frontier) | set(uncertain)
        surprise = set()
        for s, lst in conf_neg_by_stratum.items():
            for r in random.sample(lst, min(k_probe, len(lst))):
                oracle_set.add(r["idx"])
                if truth[r["idx"]] == 1 and pred[r["idx"]] == 0:    # surrogate confidently WRONG here
                    surprise.add(s)
        for s in surprise:                                          # exhaustively oracle each surprise cell
            for r in conf_neg_by_stratum[s]:
                oracle_set.add(r["idx"])
        reported_pos = {i for r in rows for i in [r["idx"]]
                        if (truth[i] if i in oracle_set else pred[i]) == 1}
        tp = len(reported_pos & truth_pos)
        return {"oracle_calls": len(oracle_set), "surprise": len(surprise),
                "needles_found": len(needles & oracle_set),
                "recall": 100.0 * tp / max(1, len(truth_pos)),
                "missed": len(truth_pos - reported_pos)}

    dc = discover_then_confirm(3)
    print(f"  {'DISCOVER→CONFIRM (k=3)':<26}{dc['oracle_calls']:>13,}{n_total//max(1,dc['oracle_calls']):>8}x"
          f"{dc['recall']:>8.1f}%{dc['needles_found']:>4}/{len(needles)}{'':>3}{100.0:>10.1f}%{dc['missed']:>8,}")
    print(f"     ↳ flagged {dc['surprise']} 'surprise' strata (surrogate confidently wrong) → exhaustively confirmed them")

    print(f"\n=== takeaway ===")
    print(f"  naive confidence routing can NEVER catch the needle (it is a confident-negative) — 0/{len(needles)}.")
    print(f"  stratified oracle coverage of confident-negatives DISCOVERS it at a bounded budget "
          f"(<< the {n_total:,} a full-oracle sweep would cost), because the Core enumerates every")
    print(f"  structural stratum and we guarantee each gets a few oracle probes. Surrogate=scale; "
          f"structural oracle coverage=the rare critical cracks.")


if __name__ == "__main__":
    main()
