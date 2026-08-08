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

"""STEP 34 — backpressure + bounded queue between producer (Reader) and consumer (Executor).

The Reader and the Executor are separate processes whose "queue" is the on-disk candidate
set: the Reader PRODUCES candidates, the Executor CONSUMES them. The legacy Reader already
paces emission with an OPEN-LOOP time ramp (``FILE_GENERATION_DELAY`` / rampUp* in
ComboGenerationPipeline — it just sleeps a shrinking delay between candidates). That is a
gentle-start guess, not a bound: a slow Executor still lets the (eventually fast) Reader run
ahead without limit, so candidate artifacts pile up on disk.

This adds the CLOSED-LOOP bound the ramp lacks: a cross-process bounded-queue coordinator
backed by a small shared state directory — no distributed broker (action 6). It is lock-free
by construction: every writer owns its own counter files (the single producer writes
``produced``; each consumer/worker writes its own ``consumed-<id>``), so there is no
read-modify-write race across processes. The in-flight DEPTH is ``produced - sum(consumed)``;
the producer PAUSES (recording its wait) while the depth is at/above the high watermark and
resumes once it drains to the low watermark — so the queue is genuinely bounded by ``high``
regardless of consumer speed. Cancellation is a shared flag both sides poll.

State files are plain text (one number per file) so the Java Reader can read the same depth
(``produced`` minus the sum of ``consumed-*``) to gate its emission loop; the Python Executor
uses this module directly to publish consumer progress. Metrics: queue depth, peak depth,
producer wait, consumer utilization, throughput.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path


class Backpressure:
    """Bounded-queue coordinator. One instance per writer (the producer, or one per consumer
    worker). High/low watermarks give hysteresis so the producer does not thrash."""

    def __init__(self, state_dir, *, high=256, low=None, writer_id="0"):
        if int(high) <= 0:
            raise ValueError("high watermark must be > 0")
        self.dir = Path(state_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.high = int(high)
        self.low = int(low if low is not None else max(1, self.high // 2))
        if self.low >= self.high:
            self.low = self.high - 1
        self.writer_id = str(writer_id)
        self._lock = threading.Lock()
        self._paused = False               # hysteresis state (guarded by _lock)
        self._produced = self.dir / "produced"
        self._wait = self.dir / "producer_wait"
        self._consumed = self.dir / f"consumed-{self.writer_id}"
        self._busy = self.dir / f"consumer_busy-{self.writer_id}"
        self._maxdepth = self.dir / "max_depth"
        self._cancel = self.dir / "cancel"
        self._started = self.dir / "started"
        if not self._started.exists():
            self._write(self._started, repr(time.time()))

    # ── producer side ────────────────────────────────────────────────────────────────
    def admit(self, *, poll=0.05):
        """Atomically admit ONE candidate into the bounded queue. The depth check and the
        ``produced`` reservation happen under one lock, so CONCURRENT producer threads cannot all
        observe "depth < high" and then all emit — overshooting the watermark. Blocks while the
        in-flight depth ≥ high (recording the wait); returns ``False`` if cancelled (the caller
        must NOT emit the candidate), else reserves one produced slot and returns ``True``.
        Replaces the earlier non-atomic ``await_capacity``/``note_produced`` pair."""
        while not self.is_cancelled():
            with self._lock:
                if self.is_cancelled():
                    return False
                d = self.depth()
                self._bump_max_depth(d)                                   # publish peak even while blocked
                if self._paused:
                    if d <= self.low:
                        self._paused = False                             # hysteresis: drained to LOW → resume
                elif d >= self.high:
                    self._paused = True                                  # hit HIGH → pause until it drains to low
                else:
                    prod = self._read_int(self._produced)
                    self._write(self._produced, str(prod + 1))           # reserve, atomic with the check
                    self._bump_max_depth(max(0, (prod + 1) - self.consumed()))
                    return True
            t0 = time.monotonic()
            time.sleep(poll)                                             # at/over high → wait, then re-check
            with self._lock:
                self._write(self._wait, repr(self._read_float(self._wait) + (time.monotonic() - t0)))
        return False

    # ── consumer side ────────────────────────────────────────────────────────────────
    def note_consumed(self, n=1, busy_seconds=0.0):
        """Record that this consumer/worker processed ``n`` candidates (consumer progress —
        action 3), optionally crediting ``busy_seconds`` of processing time (utilization)."""
        with self._lock:
            self._write(self._consumed, str(self._read_int(self._consumed) + n))
            if busy_seconds:
                self._write(self._busy, repr(self._read_float(self._busy) + busy_seconds))

    # ── shared state / queries ───────────────────────────────────────────────────────
    def produced(self):
        return self._read_int(self._produced)

    def consumed(self):
        return sum(self._read_int(f) for f in self.dir.glob("consumed-*"))

    def consumed_busy(self):
        return sum(self._read_float(f) for f in self.dir.glob("consumer_busy-*"))

    def depth(self):
        """In-flight candidates: produced minus consumed (never negative)."""
        return max(0, self.produced() - self.consumed())

    def cancel(self):
        self._write(self._cancel, "1")

    def is_cancelled(self):
        return self._cancel.exists()

    def metrics(self):
        produced, consumed = self.produced(), self.consumed()
        started = self._read_float(self._started) or time.time()
        elapsed = max(1e-9, time.time() - started)
        busy = self.consumed_busy()
        return {
            "produced": produced,
            "consumed": consumed,
            "depth": max(0, produced - consumed),
            "max_depth": self._read_int(self._maxdepth),
            "high_watermark": self.high,
            "low_watermark": self.low,
            "producer_wait_seconds": round(self._read_float(self._wait), 3),
            "consumer_busy_seconds": round(busy, 3),
            "throughput_per_sec": round(consumed / elapsed, 3),
            "utilization": round(min(1.0, busy / elapsed), 3),
            "cancelled": self.is_cancelled(),
        }

    # ── internals ────────────────────────────────────────────────────────────────────
    def _bump_max_depth(self, depth):
        if depth > self._read_int(self._maxdepth):
            self._write(self._maxdepth, str(depth))

    def _read_int(self, path):
        try:
            return int(path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return 0

    def _read_float(self, path):
        try:
            return float(path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return 0.0

    def _write(self, path, text):
        tmp = path.with_name(path.name + f".tmp.{os.getpid()}.{threading.get_ident()}")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
