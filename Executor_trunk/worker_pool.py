"""STEP 33 — deterministic sharding + local worker pool.

Parallelises candidate execution WITHOUT changing identity/result semantics. Each
candidate is assigned to exactly ONE worker by a stable hash of its candidate id
({@link assign}), so a candidate always runs in the same worker regardless of the
worker count. Consequences:

* 1-worker and N-worker runs process the same candidate set and produce the same
  outcome set (the partitions are disjoint and their union is the whole corpus);
* no duplicate final results (each candidate runs once; downstream results_v2
  writes are additionally idempotent — STEP 23);
* a worker that crashes does not lose the other workers' completed results, and its
  range is resumable: a re-run assigns the same candidates to the same worker, and
  the idempotent result writes make reprocessing a no-op.

Workers are LOCAL OS processes (subprocesses) — no remote orchestration (action 6).
This module is transport-agnostic: callers build one worker command per partition
(e.g. a `py_executor … --workerIndex w --workerCount N` invocation that filters its
candidates with {@link assign}); the pool runs them, reports heartbeat/progress,
collects each worker's structured result JSON, and aggregates them.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

_FNV64_OFFSET = 0xcbf29ce484222325
_FNV64_PRIME = 0x100000001b3
_MASK64 = 0xFFFFFFFFFFFFFFFF

# Numeric summary fields summed across workers; matches py_executor's result JSON.
_NUMERIC_FIELDS = ("processed", "pass", "fail", "broken", "inserted", "timeout", "infra_fail")


def assign(candidate_id: str, num_workers: int) -> int:
    """Stable worker index for a candidate id: ``fnv1a64(id) % num_workers``.

    Deterministic across runs AND independent of how the work is scheduled, so the
    SAME id always maps to the same worker for a given ``num_workers`` (the property
    that makes 1-vs-N equivalence and crash-resumability hold). ``num_workers <= 1``
    is the degenerate single-worker case (everything in worker 0)."""
    if num_workers <= 1:
        return 0
    h = _FNV64_OFFSET
    for b in candidate_id.encode("utf-8"):
        h ^= b
        h = (h * _FNV64_PRIME) & _MASK64
    return h % num_workers


def partition(candidate_ids, num_workers):
    """Split ``candidate_ids`` into ``num_workers`` disjoint, order-preserving ranges
    by {@link assign}. The union of the ranges is exactly the input (no loss, no dup)."""
    n = max(1, num_workers)
    buckets = [[] for _ in range(n)]
    for cid in candidate_ids:
        buckets[assign(cid, n)].append(cid)
    return buckets


def aggregate_summaries(summaries):
    """Merge per-worker structured summaries, including optional repeat tallies."""
    total = {k: 0 for k in _NUMERIC_FIELDS}
    outcomes, v2, repeats = {}, {}, {}
    saw_repeats = False
    for summary in summaries:
        for key in _NUMERIC_FIELDS:
            total[key] += int(summary.get(key, 0) or 0)
        for key, value in (summary.get("outcomes") or {}).items():
            outcomes[key] = outcomes.get(key, 0) + int(value or 0)
        for key, value in (summary.get("results_v2_write_counts") or {}).items():
            v2[key] = v2.get(key, 0) + int(value or 0)
        if summary.get("repeat_measurements") is not None:
            saw_repeats = True
            for key, value in summary["repeat_measurements"].items():
                repeats[key] = repeats.get(key, 0) + int(value or 0)
    total["outcomes"] = outcomes
    total["results_v2_write_counts"] = v2
    if saw_repeats:
        total["repeat_measurements"] = repeats
    return total


def run_workers(worker_specs, *, heartbeat_interval=5.0, on_progress=None, env=None):
    """Run one local subprocess per worker spec and collect their result JSONs.

    Each spec is a dict ``{"index": int, "cmd": [argv...], "result_path": str|Path}``.
    Returns ``(results, crashed)`` where ``results`` maps a worker index to its parsed
    result-JSON summary, and ``crashed`` is the sorted list of worker indices that
    exited non-zero or left no valid result JSON. A crash of one worker never discards
    another's collected result — completed work survives (action 5).

    ``on_progress(alive_indices)`` is called about every ``heartbeat_interval`` seconds
    with the indices of workers still running (heartbeat/progress — action 3)."""
    procs = {}
    for spec in worker_specs:
        idx = spec["index"]
        procs[idx] = (subprocess.Popen(spec["cmd"], env=env), spec)
    results, crashed = {}, []
    pending = set(procs)
    last_hb = time.time()
    while pending:
        for idx in list(pending):
            proc, spec = procs[idx]
            rc = proc.poll()
            if rc is None:
                continue
            pending.discard(idx)
            rp = Path(spec["result_path"])
            if rc == 0 and rp.is_file():
                try:
                    results[idx] = json.loads(rp.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    crashed.append(idx)        # exited cleanly but produced no usable summary
            else:
                crashed.append(idx)            # non-zero exit / killed / missing result
        if pending and (time.time() - last_hb) >= heartbeat_interval:
            last_hb = time.time()
            if on_progress:
                on_progress(sorted(pending))
        if pending:
            time.sleep(0.05)
    return results, sorted(crashed)
