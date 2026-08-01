#!/usr/bin/env python3
"""STEP 33 — tests for deterministic sharding + the local worker pool.

Covers the step's minimal validation on a medium synthetic corpus (400 cheap
"candidates"): deterministic id-hash assignment, 1-vs-N workers producing the same
outcome set with no duplicate/lost candidate, structured-summary aggregation across
real local worker subprocesses, and a killed-worker recovery (the survivors' results
are preserved and the crashed partition is resumable with no duplicates).

Test functions use `assert` (return None) so they are clean under pytest AND under the
plain `python3 test_worker_pool.py` runner below.
"""
import importlib.util
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("worker_pool", HERE / "worker_pool.py")
worker_pool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(worker_pool)

CORPUS = [f"{i}_0_0" for i in range(400)]            # 400 cheap synthetic candidates


# A synthetic worker: recompute MY partition from the full id list (exactly like py_executor
# filters with worker_pool.assign), classify each id (PASS if even, else DOMAIN_FAIL), and
# write a structured result JSON. Mirrors py_executor's result shape.
_WORKER_SRC = f"""
import sys, json
sys.path.insert(0, {str(HERE)!r})
import worker_pool
ids = open(sys.argv[1]).read().split()
wi, wc = int(sys.argv[2]), int(sys.argv[3])
mine = [x for x in ids if worker_pool.assign(x, wc) == wi]
npass = sum(1 for x in mine if int(x.split('_')[0]) % 2 == 0)
nfail = len(mine) - npass
json.dump({{"processed": len(mine), "pass": npass, "fail": nfail, "broken": 0,
           "inserted": len(mine), "timeout": 0, "infra_fail": 0,
           "outcomes": {{"PASS": npass, "DOMAIN_FAIL": nfail}},
           "results_v2_write_counts": {{"attempted": len(mine), "inserted": len(mine),
                                        "already_present": 0, "updated_selected": 0}},
           "ids": mine}}, open(sys.argv[4], "w"))
"""

_CRASH_SRC = "import sys; sys.exit(1)"   # a worker that dies without writing a result


def _check(label, cond):
    print(("  ✓ " if cond else "  ✗ ") + label)
    assert cond, label


def _expected_1worker():
    npass = sum(1 for x in CORPUS if int(x.split("_")[0]) % 2 == 0)
    return {"processed": len(CORPUS), "pass": npass, "fail": len(CORPUS) - npass}


def _specs(ids_file, n, tmp, *, crash_index=None):
    specs = []
    for w in range(n):
        rp = tmp / f"w-{w}.json"
        src = _CRASH_SRC if w == crash_index else _WORKER_SRC
        cmd = [sys.executable, "-c", src, str(ids_file), str(w), str(n), str(rp)]
        specs.append({"index": w, "cmd": cmd, "result_path": str(rp)})
    return specs


def test_assign_is_stable_and_deterministic():
    print("\n── assign(): stable, deterministic, balanced ──")
    _check("same id → same index on repeated calls",
           all(worker_pool.assign("123_0_0", 4) == worker_pool.assign("123_0_0", 4) for _ in range(5)))
    _check("num_workers<=1 → always worker 0", all(worker_pool.assign(c, 1) == 0 for c in CORPUS))
    counts = [0] * 4
    for c in CORPUS:
        counts[worker_pool.assign(c, 4)] += 1
    _check(f"roughly balanced across 4 workers ({counts})", all(c > 0 for c in counts))


def test_partition_is_disjoint_and_complete():
    print("\n── partition(): disjoint, complete, deterministic ──")
    for n in (1, 2, 3, 5):
        parts = worker_pool.partition(CORPUS, n)
        union = [cid for p in parts for cid in p]
        _check(f"N={n}: union == corpus (no loss/dup)",
               sorted(union) == sorted(CORPUS) and len(union) == len(CORPUS))
        _check(f"N={n}: partitions are disjoint", len(set(union)) == len(union))
    _check("partition deterministic across calls",
           worker_pool.partition(CORPUS, 3) == worker_pool.partition(CORPUS, 3))


def test_one_vs_n_workers_same_outcome_set():
    print("\n── 1 vs N workers: identical outcome set, no duplicates ──")
    def classify(ids):
        npass = sum(1 for x in ids if int(x.split("_")[0]) % 2 == 0)
        return {"PASS": npass, "DOMAIN_FAIL": len(ids) - npass}
    one = classify(CORPUS)
    for n in (2, 3, 4):
        parts = worker_pool.partition(CORPUS, n)
        per = [{"processed": len(p), "pass": classify(p)["PASS"], "fail": classify(p)["DOMAIN_FAIL"],
                "outcomes": classify(p)} for p in parts]
        agg = worker_pool.aggregate_summaries(per)
        every_id = [cid for p in parts for cid in p]
        _check(f"N={n}: aggregated outcomes == 1-worker", agg["outcomes"] == one)
        _check(f"N={n}: every candidate processed exactly once",
               sorted(every_id) == sorted(CORPUS) and len(every_id) == len(set(every_id)))


def test_run_workers_aggregates_real_subprocesses():
    print("\n── run_workers(): spawn real workers + aggregate ──")
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        ids_file = d / "ids.txt"; ids_file.write_text("\n".join(CORPUS), encoding="utf-8")
        results, crashed = worker_pool.run_workers(_specs(ids_file, 3, d), heartbeat_interval=10.0)
        agg = worker_pool.aggregate_summaries([results[i] for i in sorted(results)])
        exp = _expected_1worker()
        all_ids = [x for i in sorted(results) for x in results[i]["ids"]]
        _check("no worker crashed", crashed == [])
        _check(f"processed == {exp['processed']}", agg["processed"] == exp["processed"])
        _check(f"pass/fail aggregate matches 1-worker ({exp['pass']}/{exp['fail']})",
               agg["pass"] == exp["pass"] and agg["fail"] == exp["fail"])
        _check("every candidate covered exactly once across workers",
               sorted(all_ids) == sorted(CORPUS) and len(all_ids) == len(set(all_ids)))
        _check("v2 write counts aggregate (attempted == corpus)",
               agg["results_v2_write_counts"]["attempted"] == len(CORPUS))


def test_killed_worker_recovery():
    print("\n── killed worker: survivors preserved + crashed range resumable ──")
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        ids_file = d / "ids.txt"; ids_file.write_text("\n".join(CORPUS), encoding="utf-8")
        n = 3
        results, crashed = worker_pool.run_workers(_specs(ids_file, n, d, crash_index=1), heartbeat_interval=10.0)
        _check("the killed worker is reported crashed", crashed == [1])
        _check("the OTHER workers' results are preserved (not lost)",
               set(results) == {0, 2} and all("ids" in results[i] for i in (0, 2)))
        done_ids = [x for i in (0, 2) for x in results[i]["ids"]]
        expected_done = [c for c in CORPUS if worker_pool.assign(c, n) != 1]
        _check("survivors cover exactly the non-crashed partitions", sorted(done_ids) == sorted(expected_done))

        # Resume: re-run ONLY the crashed worker's partition (now healthy). Deterministic
        # assignment means it picks up exactly the missing candidates -- no duplicates.
        rec_results, rec_crashed = worker_pool.run_workers(
            [{"index": 1, "cmd": [sys.executable, "-c", _WORKER_SRC, str(ids_file), "1", str(n), str(d / "w-1.json")],
              "result_path": str(d / "w-1.json")}], heartbeat_interval=10.0)
        _check("recovery run completes cleanly", rec_crashed == [])
        recovered_ids = rec_results[1]["ids"]
        missing = [c for c in CORPUS if worker_pool.assign(c, n) == 1]
        _check("recovered partition == exactly the previously-missing candidates",
               sorted(recovered_ids) == sorted(missing))
        full = done_ids + recovered_ids
        _check("full corpus recovered with NO duplicates after resume",
               sorted(full) == sorted(CORPUS) and len(full) == len(set(full)))


def test_heartbeat_progress_is_reported():
    print("\n── heartbeat/progress callback ──")
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        ids_file = d / "ids.txt"; ids_file.write_text("\n".join(CORPUS), encoding="utf-8")
        slow = "import time,sys; time.sleep(0.3); open(sys.argv[4],'w').write('{\"processed\":0}')"
        specs = [{"index": 0, "cmd": [sys.executable, "-c", slow, str(ids_file), "0", "1", str(d / "w-0.json")],
                  "result_path": str(d / "w-0.json")}]
        beats = []
        worker_pool.run_workers(specs, heartbeat_interval=0.0, on_progress=lambda alive: beats.append(list(alive)))
        _check("on_progress fired while a worker was alive", len(beats) >= 1 and beats[0] == [0])


def main():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failures = 0
    for fn in fns:
        try:
            fn()
        except AssertionError as exc:
            failures += 1
            print(f"  ✗ FAILED {fn.__name__}: {exc}")
    print()
    if failures == 0:
        print("✅ ALL WORKER-POOL CHECKS PASSED")
    else:
        print(f"❌ {failures} WORKER-POOL CHECK(S) FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
