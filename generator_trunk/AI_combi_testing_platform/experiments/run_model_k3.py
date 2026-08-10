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
# Some names in this file are name-holders: neutral stand-ins where a
# vendor's product name would otherwise appear. Deliberate, not an
# oversight -- see 'Name-holders' in NOTICE.md.

"""the target model at K=3 over three tasks: the full decomposition on a live model.

108 requests = 3 tasks x 12 presentations x 3 repeats. K>1 is what makes
stability measurable at all -- with K=1 a disagreement between two cells is
indistinguishable from the model simply being non-deterministic, so every
fragility number from a K=1 run really means "fragility *or* noise".

Three complexities rather than three seeds at one size, so the same run also
yields a capability ladder. Failures are recorded and the run continues: a
partial result reported honestly beats a clean result that required pretending
nothing broke.

Run:
    export AI_COMBI_ALLOW_BROWSER=1
    python3 experiments/run_model_k3.py          # ~30 min, 108 requests

Results from the 2026-08-06 execution are in ../FINDINGS_TARGET_MODEL_2026-08-06.md.
"""
from __future__ import annotations

import itertools
import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from generator_trunk.AI_combi_testing_platform import engine as eng
from generator_trunk.AI_combi_testing_platform.adapters.browser import BrowserChatAdapter
from generator_trunk.AI_combi_testing_platform.decomposition import (
    capability_profile,
    fragility_profile,
)
from generator_trunk.AI_combi_testing_platform.invariance import (
    answer_digest,
    evaluate_orbits,
    lenient_answer,
    summarize,
)

#: (seed, complexity). Distinct tasks *and* a size ladder from one run.
TASKS = [(20260806, 3), (777001, 4), (424242, 5)]
SCHEMAS = ("json", "plain", "csv")
FILLERS = (0, 3)
ORDERS = ("forward", "reverse")
K = 3

OUT = Path(os.environ.get("AI_COMBI_RUN_OUT") or (Path(__file__).parent / "model_k3.json"))


def main() -> int:
    adapter = BrowserChatAdapter()
    original = eng.load_adapter
    eng.load_adapter = lambda aid, **kw: adapter if aid == "browser-chat" else original(aid, **kw)

    rows, records = [], []
    grid = list(itertools.product(TASKS, SCHEMAS, FILLERS, ORDERS, range(K)))
    started_all = time.time()
    try:
        adapter.start()
        print(f"model pinned  : {adapter._model_label!r}")
        print(f"history before: {adapter.history_count()}")
        print(f"planned       : {len(grid)} requests "
              f"({len(TASKS)} tasks x {len(SCHEMAS)*len(FILLERS)*len(ORDERS)} presentations x K={K})\n",
              flush=True)

        for index, ((seed, complexity), schema, filler, order, rep) in enumerate(grid, 1):
            plan = eng.initialize_candidate(family="ordering", seed=seed, complexity=complexity)
            plan.adapter_id = "browser-chat"
            plan.schema, plan.long_range, plan.constraint_order = schema, filler, order
            t0 = time.time()
            try:
                result = eng.run_candidate(plan)
                rows.append({
                    "seed": seed, "complexity": complexity, "schema": schema,
                    "filler": filler, "order": order, "rep": rep,
                    "code": result.code, "response": result.response[:160],
                    "lenient_digest": answer_digest(lenient_answer(result.response, schema)),
                    "task_hash": result.metrics.dimensions.get("task_hash", ""),
                })
                records.append(result.metrics)
                mark = "PASS" if result.code == 0 else f"c{result.code}"
                print(f"  [{index:3}/{len(grid)}] cx{complexity} {schema:5} f{filler} {order:7} "
                      f"r{rep} -> {mark:5} {time.time()-t0:4.0f}s", flush=True)
            except Exception as exc:
                rows.append({
                    "seed": seed, "complexity": complexity, "schema": schema,
                    "filler": filler, "order": order, "rep": rep,
                    "code": None, "error": f"{type(exc).__name__}: {exc}"[:120],
                })
                print(f"  [{index:3}/{len(grid)}] cx{complexity} {schema:5} f{filler} {order:7} "
                      f"r{rep} -> ERROR {type(exc).__name__}", flush=True)
        print(f"\nhistory after : {adapter.history_count()}")
    finally:
        adapter.close()
        eng.load_adapter = original

    ok_rows = [r for r in rows if r.get("code") is not None]
    print(f"\ncompleted {len(ok_rows)}/{len(grid)} in {(time.time()-started_all)/60:.1f} min")
    if not ok_rows:
        return 1

    passed = sum(1 for r in ok_rows if r["code"] == 0)
    print(f"\n=== ACCURACY ===  {passed}/{len(ok_rows)} = {100*passed/len(ok_rows):.1f}%")
    print(f"  verdicts: {dict(Counter(r['code'] for r in ok_rows))}  (0=pass, 4=format, 5=wrong)")

    print("\n=== CAPABILITY (pass rate by task size) ===")
    cap = capability_profile(records)
    for level, bucket in sorted(cap.by_complexity.items()):
        print(f"  complexity {level}: {bucket['pass_rate']}  "
              f"({bucket['passed']}/{bucket['candidates']})")
    print(f"  ceiling = {cap.ceiling}")

    # --- stability: the marginal that bounds the other two ----------------
    cells: dict[tuple, list[str]] = defaultdict(list)
    for row in ok_rows:
        cells[(row["seed"], row["schema"], row["filler"], row["order"])].append(row["lenient_digest"])
    comparable = {k: v for k, v in cells.items() if len(v) > 1}
    flaky = {k: v for k, v in comparable.items() if len(set(v)) > 1}
    instability = round(len(flaky) / len(comparable), 4) if comparable else None
    print(f"\n=== STABILITY (K={K}; identical input repeated) ===")
    print(f"  comparable cells: {len(comparable)}   flaky: {len(flaky)}")
    print(f"  instability_rate = {instability}")
    print(f"  distinct answers per cell: "
          f"{dict(sorted(Counter(len(set(v)) for v in cells.values()).items()))}")

    print(f"\n=== INVARIANCE (lenient digests, no ground truth) ===")
    inv_records = []
    for row in ok_rows:
        base = f"{row['seed']}|{row['complexity']}"
        inv_records.append({
            "answer_digest": row["lenient_digest"],
            "orbit_joint": f"{base}|joint",
            "orbit_output_schema": f"{base}|f{row['filler']}|{row['order']}",
            "orbit_neutral_context": f"{base}|{row['schema']}|{row['order']}",
            "orbit_constraint_order": f"{base}|{row['schema']}|f{row['filler']}",
        })
    inv = summarize(evaluate_orbits(inv_records))
    for name, bucket in inv["relations"].items():
        if bucket["comparable"]:
            print(f"  {name:20} comparable={bucket['comparable']:3} "
                  f"violated={bucket['violated']:3} rate={bucket['violation_rate']}")
    print(f"  OVERALL = {inv['invariance_violation_rate']}")

    # Between-presentation disagreement measured on per-cell MAJORITIES. This is
    # the number to read when instability is high: the raw invariance rate above
    # is then largely re-measuring non-determinism, not sensitivity to phrasing.
    majority = {k: Counter(v).most_common(1)[0][0] for k, v in cells.items()}
    per_task: dict[int, set[str]] = defaultdict(set)
    for (seed, _schema, _filler, _order), digest in majority.items():
        per_task[seed].add(digest)
    print("\n=== BETWEEN-PRESENTATION (per-cell majorities) ===")
    for seed, answers in sorted(per_task.items()):
        print(f"  seed={seed}: {len(answers)} distinct majority answers "
              f"across {len(SCHEMAS)*len(FILLERS)*len(ORDERS)} presentations")

    print("\n=== FRAGILITY (by task) ===")
    frag = fragility_profile(records, presentation_keys=("renderer_id",))
    for task, bucket in frag["tasks"].items():
        print(f"  {task[:12]}: {bucket['failing_presentations']}/{bucket['presentation_space']} "
              f"-> {bucket['fragility_coefficient']}")
    print(f"  overall = {frag['fragility_coefficient']}")
    if instability and instability > 0.3:
        print(f"\n  !! instability is {instability}: fragility and invariance above are")
        print(f"     CONFOUNDED by non-determinism and must not be read as")
        print(f"     presentation sensitivity. Use the majority figures instead.")

    OUT.write_text(json.dumps({
        "config": {"tasks": TASKS, "schemas": SCHEMAS, "fillers": FILLERS,
                   "orders": ORDERS, "K": K},
        "model": adapter._model_label,
        "rows": rows,
        "accuracy": {"passed": passed, "total": len(ok_rows)},
        "capability": cap.as_dict(),
        "stability": {"comparable": len(comparable), "flaky": len(flaky),
                      "instability_rate": instability},
        "invariance": inv,
        "fragility": frag,
    }, indent=1), encoding="utf-8")
    print(f"\nraw -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
