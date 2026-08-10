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

"""STEP 34 — tests for backpressure + the bounded producer/consumer queue.

Covers the step's minimal validation: a fast producer against a SYNTHETIC SLOW consumer must
stay bounded by the high watermark (the producer pauses and waits), and a cancel must terminate
both sides coherently (no deadlock). Producer and consumer use SEPARATE Backpressure instances
over one shared state dir — faithful to the real cross-process Reader↔Executor split.

Test functions assert (return None) so they are clean under pytest and the plain runner below.
"""
import collections
import importlib.util
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("backpressure", HERE / "backpressure.py")
backpressure = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(backpressure)
Backpressure = backpressure.Backpressure


def _check(label, cond):
    print(("  ✓ " if cond else "  ✗ ") + label)
    assert cond, label


def _run_pipeline(state_dir, *, n, high, low, consume_delay, cancel_after=None):
    """A fast producer feeding a slow consumer through a shared bounded queue. Returns
    (producer_bp, max_pending_observed)."""
    prod = Backpressure(state_dir, high=high, low=low, writer_id="prod")
    cons = Backpressure(state_dir, high=high, low=low, writer_id="c0")
    q = collections.deque()
    qlock = threading.Lock()
    max_pending = [0]

    def producer():
        for i in range(n):
            if not prod.admit():                   # atomic admit; blocks at high, False if cancelled
                return
            with qlock:
                q.append(i)
                max_pending[0] = max(max_pending[0], len(q))

    def consumer():
        done = 0
        while done < n and not cons.is_cancelled():
            with qlock:
                item = q.popleft() if q else None
            if item is None:
                time.sleep(0.001)
                continue
            time.sleep(consume_delay)              # the SLOW worker
            cons.note_consumed(1, busy_seconds=consume_delay)
            done += 1

    tp = threading.Thread(target=producer, name="producer")
    tc = threading.Thread(target=consumer, name="consumer")
    tp.start(); tc.start()
    if cancel_after is not None:
        time.sleep(cancel_after)
        prod.cancel()
    tp.join(timeout=20); tc.join(timeout=20)
    assert not tp.is_alive() and not tc.is_alive(), "threads did not terminate (deadlock?)"
    return prod, max_pending[0]


def test_slow_consumer_keeps_the_queue_bounded():
    print("\n── slow consumer: queue stays bounded by the high watermark ──")
    with tempfile.TemporaryDirectory() as d:
        high, low, n = 10, 5, 200
        prod, max_pending = _run_pipeline(d, n=n, high=high, low=low, consume_delay=0.003)
        m = prod.metrics()
        _check(f"all {n} candidates produced", m["produced"] == n)
        _check(f"all {n} candidates consumed", m["consumed"] == n)
        _check("final depth drained to 0", m["depth"] == 0)
        _check(f"observed queue never exceeded high watermark ({max_pending} ≤ {high})", max_pending <= high)
        _check(f"recorded peak depth ≤ high ({m['max_depth']} ≤ {high})", m["max_depth"] <= high)
        _check("backpressure engaged: producer actually waited", m["producer_wait_seconds"] > 0)


def test_faster_consumer_needs_little_backpressure():
    print("\n── fast consumer: little/no waiting, still correct ──")
    with tempfile.TemporaryDirectory() as d:
        prod, max_pending = _run_pipeline(d, n=120, high=50, low=25, consume_delay=0.0)
        m = prod.metrics()
        _check("all produced+consumed", m["produced"] == 120 and m["consumed"] == 120)
        _check("queue stayed within the (generous) bound", max_pending <= 50)


def test_cancel_terminates_both_sides_coherently():
    print("\n── cancel terminates producer + consumer (no deadlock) ──")
    with tempfile.TemporaryDirectory() as d:
        high, low = 8, 4
        # A very slow consumer + a large N: without cancel this would run for a long time;
        # cancel must stop both threads promptly and coherently.
        prod, _ = _run_pipeline(d, n=100000, high=high, low=low, consume_delay=0.01, cancel_after=0.1)
        m = prod.metrics()
        _check("run was cancelled", m["cancelled"] is True)
        _check("producer stopped early (did not emit the whole corpus)", m["produced"] < 100000)
        _check("queue stayed bounded even under cancel", m["max_depth"] <= high)
        # depth may be > 0 at cancel (un-consumed in-flight items) -- that's fine; the point is
        # both sides STOPPED. The join in _run_pipeline already asserted no deadlock.


def test_concurrent_producers_stay_bounded():
    print("\n── concurrent producers stay bounded by high (the race a sequential test misses) ──")
    with tempfile.TemporaryDirectory() as d:
        high, producers, per = 20, 6, 80
        total = producers * per
        prod = Backpressure(d, high=high, low=high // 2, writer_id="prod")
        cons = Backpressure(d, high=high, writer_id="c0")
        consumed = [0]
        max_depth = [0]
        stop = [False]
        clock = threading.Lock()

        def consumer():
            while not stop[0]:
                time.sleep(0.002)
                with clock:
                    if consumed[0] < prod.produced():        # drain only real in-flight items
                        consumed[0] += 1
                        cons.note_consumed(1, busy_seconds=0.002)

        def producer():
            for _ in range(per):
                if not prod.admit():
                    return
                d2 = prod.depth()
                with clock:
                    if d2 > max_depth[0]:
                        max_depth[0] = d2

        tc = threading.Thread(target=consumer); tc.start()
        ths = [threading.Thread(target=producer) for _ in range(producers)]
        for t in ths: t.start()
        for t in ths: t.join(30)
        for _ in range(5000):
            if consumed[0] >= total:
                break
            time.sleep(0.002)
        stop[0] = True; tc.join(5)

        m = prod.metrics()
        _check(f"all {total} candidates admitted", m["produced"] == total)
        _check(f"queue NEVER exceeded high under {producers} concurrent producers "
               f"({max_depth[0]} ≤ {high})", max_depth[0] <= high)
        _check("consumer drained the whole queue", consumed[0] >= total)
        # STEP 34 metrics must be REAL (not 0) when backpressure actually engaged:
        _check(f"metrics.producer_wait_seconds > 0 ({m['producer_wait_seconds']})",
               m["producer_wait_seconds"] > 0.0)
        _check(f"metrics.max_depth in (0, high] ({m['max_depth']})",
               0 < m["max_depth"] <= high)


def test_concurrent_cancel_stops_all_producers():
    print("\n── cancel stops all concurrent producers (no overshoot) ──")
    with tempfile.TemporaryDirectory() as d:
        high, producers = 10, 6
        prod = Backpressure(d, high=high, low=5, writer_id="prod")
        admits = [0]
        clock = threading.Lock()

        def producer():
            while prod.admit():                              # no consumer → fill to high then block
                with clock:
                    admits[0] += 1

        ths = [threading.Thread(target=producer) for _ in range(producers)]
        for t in ths: t.start()
        time.sleep(0.4)                                      # let them fill to high and block
        filled = admits[0]
        prod.cancel()
        for t in ths: t.join(5)

        _check("all producers terminated after cancel", not any(t.is_alive() for t in ths))
        _check(f"exactly high ({high}) admitted — no overshoot (got {admits[0]})", admits[0] == high)
        _check("queue was filled to high before cancel", filled == high)
        _check("admit() returns False after cancel", prod.admit() is False)


def test_metrics_read_java_published_files():
    print("\n── metrics read the Java-gate-published producer_wait + max_depth ──")
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        # mimic exactly what BackpressureGate.java writes (plain text, Double/Long.toString style)
        (d / "produced").write_text("100", encoding="utf-8")
        (d / "consumed-0").write_text("60", encoding="utf-8")
        (d / "producer_wait").write_text("1.234", encoding="utf-8")
        (d / "max_depth").write_text("20", encoding="utf-8")
        (d / "started").write_text(repr(time.time() - 5), encoding="utf-8")
        m = Backpressure(d, high=20).metrics()
        _check(f"reads Java-written producer_wait ({m['producer_wait_seconds']})",
               abs(m["producer_wait_seconds"] - 1.234) < 1e-6)
        _check(f"reads Java-written max_depth ({m['max_depth']})", m["max_depth"] == 20)
        _check(f"computes depth = produced − consumed ({m['depth']})", m["depth"] == 40)


def test_metrics_are_sane():
    print("\n── metrics shape/values ──")
    with tempfile.TemporaryDirectory() as d:
        prod, _ = _run_pipeline(d, n=60, high=12, low=6, consume_delay=0.002)
        m = prod.metrics()
        for key in ("produced", "consumed", "depth", "max_depth", "high_watermark",
                    "low_watermark", "producer_wait_seconds", "consumer_busy_seconds",
                    "throughput_per_sec", "utilization", "cancelled"):
            _check(f"metric present: {key}", key in m)
        _check("throughput > 0", m["throughput_per_sec"] > 0)
        _check("utilization in [0,1]", 0.0 <= m["utilization"] <= 1.0)
        _check("consumer recorded busy time", m["consumer_busy_seconds"] > 0)


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
        print("✅ ALL BACKPRESSURE CHECKS PASSED")
    else:
        print(f"❌ {failures} BACKPRESSURE CHECK(S) FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
