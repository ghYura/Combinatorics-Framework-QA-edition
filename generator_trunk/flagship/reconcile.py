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

"""Full-chain reconciliation for a Bundle-native flagship level.

The claim this file exists to check is narrow and falsifiable: **the engine chain
and the in-process study ran the same experiment.** Not "roughly the same size" —
the same candidates, producing the same measurements, judged the same way.

Five counts must agree, and each is read from a different stage's own artifact so
that an error in one stage cannot hide itself:

1. **Core** — ``fw_final`` rows in the main database (the mandatory product).
2. **Optional contract** — ``fw_final × optional multiplier`` from the spec.
3. **Reader** — candidate ``.py`` files actually emitted.
4. **Executor** — terminal verdict rows in the Results database.
5. **Analyzer** — ``K=V`` lines in the harvested corpus.

Then the strong check: the **multiset of metric tuples** the engine chain measured
must equal the one the in-process study computes from the same factor space. Two
chains agreeing on 256 five-tuples of independently produced integers is not a
coincidence that survives a wrong tree.

Read-only. It opens the databases with the run's own credentials and issues
``SELECT`` only; it never drops, creates or modifies anything.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter
from pathlib import Path

from generator_trunk.engine_demo import record_pipeline as rp
from generator_trunk.flagship import levels as L
from generator_trunk.flagship import pipeline_flagship as F

#: The metric keys that make a candidate's measurement, in a stable order. These
#: are produced by `record_pipeline.Result.metrics_line` inside the candidate, so
#: the engine side of the comparison is genuinely the executed value.
METRIC_KEYS = ("stages", "depth", "branches", "ops", "retained", "reason", "FW_VAR")

_KV = re.compile(r"(\w+)=(\S*)")


def parse_corpus(path: Path) -> "list[dict]":
    """Parse an Analyzer corpus file into one dict per candidate."""
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(dict(_KV.findall(line)))
    return rows


def metric_multiset(rows: "list[dict]") -> Counter:
    return Counter(tuple(row.get(k, "") for k in METRIC_KEYS) for row in rows)


def _store_twin():
    """The transactional-store twin, imported on demand.

    Importing every SUT at module scope would make this reconciler depend on all
    of them: reconciling the record pipeline would drag in the store, and a third
    SUT would drag in both. The registry is a lookup, not a reason to couple.
    """
    from generator_trunk.flagship import store_flagship as S
    return (lambda: F.cartesian_suite(S.FACTORS), S.build)


#: Each level's in-process twin: the factor space and the builder that turns one
#: assignment into a tree. Values are thunks so a level's SUT module is imported
#: only when that level is actually reconciled.
TWINS = {
    "l2": lambda: (F.cartesian_suite, F.build),
    "s2": _store_twin,
    "l3": lambda: (lambda: L.l3_suite("l3"), L.build_l3),
    "l4": lambda: (lambda: L.l3_suite("l4"), L.build_l3),
}


def expected_multiset(version: str, suite=None, build=None) -> Counter:
    """The same multiset, computed in-process from the factor space.

    Uses `record_pipeline.evaluate` under the selected SUT version — the identical
    parser, executor and oracle the candidates use — so any difference is a
    difference in *which trees were built*, which is exactly the question.
    """
    build = build or F.build
    # The twin must run under the SAME mutant the engine run used. Which module
    # installs it depends on the SUT, so it is selected from the builder rather
    # than hardwired — a twin that always patched the pipeline would silently
    # compare the store's mutant run against the store's correct one.
    counter: Counter = Counter()
    for assignment in (suite if suite is not None else F.cartesian_suite()):
        node = build(assignment)
        if getattr(build, "__module__", "").endswith("store_flagship"):
            from generator_trunk.flagship import store_flagship as S
            result = S.evaluate_stream_under([node], version)
        else:
            saved = rp._compile_atom
            rp._compile_atom = F.compiled_evaluator(version)
            try:
                result = rp.evaluate([node])
            finally:
                rp._compile_atom = saved
        counter[(str(result.stages), str(result.depth), str(result.branches),
                 str(result.ops), str(result.retained), result.reason or "ok",
                 str(result.code))] += 1
    return counter


def _query(host: str, port: int, database: str, sql: str, password: str):
    import pg8000.dbapi
    connection = pg8000.dbapi.connect(user="postgres", password=password,
                                      host=host, port=port, database=database)
    try:
        cursor = connection.cursor()
        cursor.execute(sql)
        return cursor.fetchall()
    finally:
        connection.close()


def _stage_count(run_dir: Path, stage: str, name: str):
    """One stage's own declared count, from its `bundle.stage-result/v1` artifact.

    Reading each stage's own record rather than re-deriving the number here is the
    point: a stage that miscounts is then caught by the *next* stage disagreeing,
    instead of by this file quietly recomputing what it wishes were true.
    """
    data = json.loads((run_dir / "stages" / f"{stage}.json").read_text(encoding="utf-8"))
    for entry in data.get("counts", []):
        if entry.get("name") == name:
            return entry.get("actual")
    return None


def reconcile(run_dir: Path, version: str, *, database: str, host: str = "127.0.0.1",
              main_port: int = 5433, results_port: int = 5432,
              optional_multiplier: int = 2, suite=None, build=None) -> dict:
    """Reconcile one run. Returns a report; `ok` is true only if every check passed."""
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    corpus = parse_corpus(run_dir / "metrics.kv")

    main_password = os.environ["BUNDLE_MAIN_DB_PASSWORD"]
    results_password = os.environ["BUNDLE_RESULTS_DB_PASSWORD"]
    # fw_final is the POST-sieve table: the sieve deletes violating rows in place.
    core_db_rows = _query(host, main_port, database,
                          'SELECT count(*) FROM public.fw_final', main_password)[0][0]
    results_db_rows = _query(host, results_port, database,
                             'SELECT count(*) FROM public.results_v2', results_password)[0][0]

    core_rows = _stage_count(run_dir, "core", "fw_final")
    post_sieve = _stage_count(run_dir, "sieve", "post_sieve") \
        if (run_dir / "stages" / "sieve.json").exists() else None
    effective_rows = post_sieve if post_sieve is not None else core_rows
    multiplier = _stage_count(run_dir, "core", "optional_multiplier") or optional_multiplier
    expected_candidates = effective_rows * multiplier
    checks = {
        "core_fw_final": core_rows,
        "sieve_post_sieve": post_sieve,
        "sieve_removed": None if post_sieve is None else core_rows - post_sieve,
        "core_fw_final_in_db": core_db_rows,
        "optional_multiplier": multiplier,
        "contract_expected_candidates": expected_candidates,
        "reader_emitted": _stage_count(run_dir, "reader", "candidates"),
        "reader_source_files": len(list((run_dir / "src").glob("*.py"))),
        "executor_processed": _stage_count(run_dir, "executor", "processed"),
        "executor_terminal_sum": sum(_stage_count(run_dir, "executor", k) or 0
                                     for k in ("pass", "fail", "broken", "timeout", "infra_fail")),
        "executor_persisted": _stage_count(run_dir, "executor", "results_v2_inserted"),
        "results_db_rows": results_db_rows,
        "analyzer_corpus_lines": _stage_count(run_dir, "analyzer", "metrics_lines"),
        "analyzer_corpus_file_lines": len(corpus),
    }
    # Every count in the chain must equal the one the optional-table contract
    # predicts from Core's own product. Any single stage dropping or duplicating a
    # candidate breaks this, which is the whole reason to check it end to end.
    agree = {key: value == expected_candidates
             for key, value in checks.items()
             if key not in ("core_fw_final", "sieve_post_sieve", "sieve_removed",
                            "core_fw_final_in_db", "optional_multiplier",
                            "contract_expected_candidates")}
    # fw_final is edited in place by the sieve, so the live table must match the
    # post-sieve count, not Core's original product.
    agree["core_db_matches_stage"] = core_db_rows == effective_rows

    measured = metric_multiset(corpus)
    expected = expected_multiset(version, suite=suite, build=build)
    report = {
        "run_id": run.get("run_id"),
        "version": version,
        "counts": checks,
        "counts_agree": all(agree.values()),
        "disagreeing": sorted(k for k, v in agree.items() if not v),
        "metric_multiset_equal": measured == expected,
        "measured_distinct_tuples": len(measured),
        "expected_distinct_tuples": len(expected),
        "verdict_codes": dict(Counter(row.get("FW_VAR") for row in corpus)),
        "reasons": dict(Counter(row.get("reason") for row in corpus)),
    }
    if measured != expected:
        # Report the difference, not just the failure: a silent "not equal" is
        # unusable evidence either way.
        report["only_measured"] = sorted((measured - expected).items())[:10]
        report["only_expected"] = sorted((expected - measured).items())[:10]
    report["ok"] = report["counts_agree"] and report["metric_multiset_equal"]
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs-root", type=Path, default=Path("/tmp/fw_work"))
    parser.add_argument("--level", default="l2", choices=sorted(TWINS))
    parser.add_argument("--versions", default="", help="comma-separated; default all three")
    parser.add_argument("--main-port", type=int, default=5433)
    parser.add_argument("--results-port", type=int, default=5432)
    args = parser.parse_args(argv)

    make_suite, build = TWINS[args.level]()
    suite = make_suite()
    versions = tuple(v.strip() for v in args.versions.split(",") if v.strip()) or F.VERSIONS

    overall = True
    for version in versions:
        run_dir = args.runs_root / f"flagship-{args.level}-{version}"
        if not run_dir.is_dir():
            print(f"(no run at {run_dir} — skipping)")
            continue
        report = reconcile(run_dir, version, database=f"flagship_{args.level}",
                           main_port=args.main_port, results_port=args.results_port,
                           suite=suite, build=build)
        overall &= report["ok"]
        print(json.dumps(report, indent=2, sort_keys=True))
    print("\nRECONCILED" if overall else "\nMISMATCH")
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
