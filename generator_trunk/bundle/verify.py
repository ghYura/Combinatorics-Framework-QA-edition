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

"""Numeric-equivalence helpers for FW_VAR oracles — relative-tolerance, magnitude-blind safe.

Why this exists (transformers_sweep_288 / BUNDLE_TODO #1): an *absolute* `1e-3` logit-delta gate
falsely rejected ~144 architecture candidates whose recurrence was actually exact to <0.1% — the
absolute threshold does not scale with output magnitude or model depth. Every equivalence check here
defaults to a **relative** tolerance normalised by the reference scale, so "exact to X%" is the bar.

Framework-agnostic on purpose: operates on plain floats or arbitrarily-nested sequences (lists/tuples),
no numpy/torch dependency, so any executor or oracle (Python, or a subprocess emitting numbers) can use
it without pulling a tensor library into the orchestration layer.
"""
from __future__ import annotations

import math
from typing import Any

_EPS = 1e-12


def _flatten(x: Any):
    if isinstance(x, bool):
        yield float(x); return
    if isinstance(x, (int, float)):
        yield float(x); return
    try:
        for e in x:
            yield from _flatten(e)
    except TypeError:
        raise TypeError(f"cannot flatten value of type {type(x).__name__}")


def max_abs(x: Any) -> float:
    """max|value| over a scalar or nested sequence (0.0 if empty)."""
    return max((abs(v) for v in _flatten(x)), default=0.0)


def abs_delta(a: Any, b: Any) -> float:
    fa, fb = list(_flatten(a)), list(_flatten(b))
    if len(fa) != len(fb):
        raise ValueError(f"length mismatch: {len(fa)} vs {len(fb)}")
    return max((abs(x - y) for x, y in zip(fa, fb)), default=0.0)


def relative_delta(a: Any, b: Any) -> float:
    """max|a-b| / (max|a| + eps): scale-invariant. 0 == identical; ~O(1) == unrelated.

    This is THE number an exactness oracle should threshold (e.g. a recurrence/cache check), not the
    raw absolute delta — it stays meaningful as activations grow with width/depth.
    """
    return abs_delta(a, b) / (max_abs(a) + _EPS)


def is_close(a: Any, b: Any, *, rtol: float = 1e-2, atol: float = 0.0) -> bool:
    """True if a≈b within a RELATIVE tolerance (default 1%), OR an absolute atol if given.

    Default rtol=1e-2 is a deliberately generous "numerically exact" bar: deterministic fp rounding
    from length-dependent kernels (e.g. conv1d) amplified through a matmul can reach ~1e-3 relative on
    a deep model while being logically exact; a genuinely broken cache/quant path is O(0.1-1) relative,
    so 1% cleanly separates "exact" from "broken". Tighten for unit tests, loosen for deep models.
    """
    if not math.isfinite(rtol) or rtol < 0 or atol < 0:
        raise ValueError("rtol/atol must be non-negative and finite")
    d = abs_delta(a, b)
    return (atol > 0 and d <= atol) or relative_delta(a, b) <= rtol


def assert_close(a: Any, b: Any, *, rtol: float = 1e-2, atol: float = 0.0, what: str = "values") -> None:
    if not is_close(a, b, rtol=rtol, atol=atol):
        raise AssertionError(
            f"{what} not close: rel={relative_delta(a, b):.2e} abs={abs_delta(a, b):.2e} "
            f"(rtol={rtol:.1e}, atol={atol:.1e})")


def all_finite(x: Any) -> bool:
    return all(math.isfinite(v) for v in _flatten(x))


def kl_divergence(p_rows: Any, q_rows: Any, *, eps: float = 1e-9) -> float:
    """Mean KL(p || q) over rows of probability distributions — fp-vs-int8 distributional fidelity.

    p_rows / q_rows: sequence of equal-length probability vectors. Returns mean per-row KL (nats).
    A near-0 value means the quantized/deployed model is distributionally faithful, not just
    argmax-equal (catches drift that accuracy-only checks miss).
    """
    p_rows, q_rows = list(p_rows), list(q_rows)
    if len(p_rows) != len(q_rows):
        raise ValueError(f"row count mismatch: {len(p_rows)} vs {len(q_rows)}")
    total = 0.0
    for p, q in zip(p_rows, q_rows):
        p, q = list(p), list(q)
        if len(p) != len(q):
            raise ValueError("distribution length mismatch")
        total += sum(pi * (math.log(pi + eps) - math.log(qi + eps)) for pi, qi in zip(p, q))
    return total / max(1, len(p_rows))
