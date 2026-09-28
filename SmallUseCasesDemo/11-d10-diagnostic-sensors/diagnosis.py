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

"""D10 offline diagnosis analysis from the OBSERVED subset x fault matrix (not Framework-native diagnosis).

    python diagnosis.py --run evidence/<run-id>     # write evidence/<run-id>/diagnosis.json

Input guard: exactly one PASS observation for each of 256 masks x 12 fault labels, known identities
only, and every subset's readings equal to the projection of that label's observed full-mask
signature. Equivalence classes are inferred from observed full signatures; the declared healthy
reference H0 (all-zero signature, a DB-free control, not a Framework observation) makes seven
diagnosis classes. For each of 256 masks: seven projected class words, 21 pairwise Hamming
distances, and detection / separation / one-erasure / one-error obligations; minimum-cost suites with
all ties; the noiseless adaptive program over all 127 beliefs (ties -> smallest sensor); the
erasure (49) and error (56) decoding controls for the chosen suites.
"""
import argparse
import itertools
import json
import re
from pathlib import Path

LABELS = [f"F{i:02}" for i in range(1, 13)]
ID_RE = re.compile(r"S=([01]{8})\|H=(F0[1-9]|F1[0-2])")
H0 = {"class": 0, "members": ["H0"], "source": "declared healthy reference (DB-free control), not a Framework observation"}


class DiagnosisInputError(ValueError):
    pass


def observed_matrix(records):
    seen = {}
    for r in records:
        m = ID_RE.fullmatch(r.get("case_id", ""))
        if not m or (r.get("mask"), r.get("fault")) != (m.group(1), m.group(2)):
            raise DiagnosisInputError(f"unknown identity {r.get('case_id')!r}")
        if r.get("verdict") != "PASS":
            raise DiagnosisInputError(f"non-PASS observation {r['case_id']}")
        if (m.group(1), m.group(2)) in seen:
            raise DiagnosisInputError(f"duplicate observation {r['case_id']}")
        seen[(m.group(1), m.group(2))] = r["readings"]
    missing = [(f"{i:08b}", f) for i in range(256) for f in LABELS if (f"{i:08b}", f) not in seen]
    if missing:
        raise DiagnosisInputError(f"{len(missing)} missing observations, e.g. {missing[:2]}")
    full = {f: seen[("11111111", f)] for f in LABELS}
    for (mask, f), readings in seen.items():
        if readings != [full[f][i] for i in range(8) if mask[i] == "1"]:
            raise DiagnosisInputError(f"S={mask}|H={f}: readings differ from the projection of its full signature")
    return seen, full


def classes_from(full):
    groups = {}
    for f in LABELS:
        groups.setdefault(tuple(full[f]), []).append(f)
    measured = sorted(groups.items(), key=lambda kv: LABELS.index(kv[1][0]))
    out = [dict(H0, code=0, signature=[0] * 8)]
    for k, (sig, members) in enumerate(measured, start=1):
        a, b, c, d = sig[:4]
        out.append({"class": k, "members": members, "code": a | b << 1 | c << 2 | d << 3, "signature": list(sig),
                    "source": "inferred from observed full-mask signatures"})
    return out


def suite(mask, sigs):
    sel = [i for i in range(8) if mask[i] == "1"]
    words = ["".join(str(s[i]) for i in sel) for s in sigs]
    dist = [{"classes": [i, j], "distance": sum(x != y for x, y in zip(words[i], words[j]))} for i, j in itertools.combinations(range(7), 2)]
    md = min(x["distance"] for x in dist)
    return {"mask": mask, "cost": len(sel), "signatures": words, "distances": dist, "min_distance": md,
            "detect": all(w != words[0] for w in words[1:]), "separate": md >= 1, "erasure": md >= 2, "error": md >= 3}


def adaptive(sigs):
    memo = {}

    def best(belief):
        if belief not in memo:
            if len(belief) == 1:
                memo[belief] = (0, None)
            else:
                options = []
                for s in range(8):
                    parts = [tuple(c for c in belief if sigs[c][s] == v) for v in (0, 1)]
                    if parts[0] and parts[1]:
                        options.append((1 + max(best(parts[0])[0], best(parts[1])[0]), s))
                memo[belief] = min(options)
        return memo[belief]

    def tree(belief):
        cost, s = best(belief)
        if s is None:
            return {"class": belief[0], "cost": 0}
        return {"sensor": s, "cost": cost, "branches": {str(v): tree(tuple(c for c in belief if sigs[c][s] == v)) for v in (0, 1)}}
    dp = []
    for flags in itertools.product((0, 1), repeat=7):
        belief = tuple(i for i in range(7) if flags[i])
        if belief:
            cost, s = best(belief)
            dp.append({"belief": list(belief), "cost": cost, "sensor": s})
    root = tree(tuple(range(7)))
    paths = []
    for cl in range(7):
        node, steps = root, []
        while "sensor" in node:
            steps.append({"sensor": node["sensor"], "reading": sigs[cl][node["sensor"]]})
            node = node["branches"][str(sigs[cl][node["sensor"]])]
        paths.append({"class": cl, "steps": steps, "cost": len(steps)})
    return {"tree": root, "dp": dp, "paths": paths}


def noise_controls(words, kind):
    rows = []
    for cl, word in enumerate(words):
        for pos in [-1, *range(len(word))]:
            obs = list(word)
            if pos >= 0:
                obs[pos] = "?" if kind == "erasure" else str(1 - int(obs[pos]))
            if kind == "erasure":
                keep = [c for c, w in enumerate(words) if all(o == "?" or o == x for o, x in zip(obs, w))]
            else:
                keep = [c for c, w in enumerate(words) if sum(o != x for o, x in zip(obs, w)) <= 1]
            rows.append({"class": cl, "position": pos, "observed": "".join(obs), "decoded": keep})
    return rows


def identify(signature, classes):
    """The diagnosis for a full observed signature: the whole class and BOTH alias labels, never one cause."""
    hit = [c for c in classes if c["signature"] == list(signature)]
    return {"class": hit[0]["class"], "members": hit[0]["members"]} if hit else None


def analyse(records):
    seen, full = observed_matrix(records)
    classes = classes_from(full)
    sigs = [c["signature"] for c in classes]
    suites = [suite(f"{i:08b}"[::1], sigs) for i in range(256)]
    suites = sorted(suites, key=lambda s: s["mask"])
    winners = {}
    for goal in ("detect", "separate", "erasure", "error"):
        feas = sorted((s for s in suites if s[goal]), key=lambda s: (s["cost"], s["mask"]))
        winners[goal] = {"mask": feas[0]["mask"], "cost": feas[0]["cost"], "feasible_count": len(feas),
                         "minimum_cost_masks": [s["mask"] for s in feas if s["cost"] == feas[0]["cost"]]}
    noise = {g: noise_controls(next(s for s in suites if s["mask"] == winners[g]["mask"])["signatures"], g) for g in ("erasure", "error")}
    alias_full_distance = min(sum(x != y for x, y in zip(full[a], full[b])) for a, b in itertools.combinations(LABELS, 2))
    return {"schema": "d10.diagnosis/v1", "source": "observed readings of all 256 x 12 evaluations; H0 declared",
            "classes": classes, "healthy_reference": H0, "suites": suites, "winners": winners, "adaptive": adaptive(sigs),
            "noise": noise, "unquotiented_label_min_distance": alias_full_distance,
            "identify_examples": {f: identify(full[f], classes) for f in LABELS}}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", required=True, type=Path)
    a = ap.parse_args()
    records = [json.loads(l) for l in (a.run / "observations.jsonl").read_text().splitlines() if l.strip()]
    doc = analyse(records)
    (a.run / "diagnosis.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({g: {k: v for k, v in w.items() if k != "minimum_cost_masks"} for g, w in doc["winners"].items()}
                     | {"adaptive_cost": doc["adaptive"]["tree"]["cost"], "noise": {g: len(r) for g, r in doc["noise"].items()}}))


if __name__ == "__main__":
    main()
