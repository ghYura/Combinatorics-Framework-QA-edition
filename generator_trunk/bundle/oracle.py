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

"""Reusable FW_VAR correctness oracle — one canonical, correct set of verdict checks for synthesized
candidates, so every campaign uses the SAME (and correctly-calibrated) checks instead of re-deriving
them ad hoc (BUNDLE_TODO #3; the recurrence threshold was gotten wrong precisely because it was
re-implemented per spec).

Framework-agnostic: the caller passes already-computed outputs (shapes as tuples, logits/probabilities
as nested sequences) — no torch here. Each `*_code` returns the canonical FW_VAR code (0 == ok), and
`first_failure(...)` reduces a list of codes to the verdict (first non-zero, else 0).

Canonical codes (keep stable across campaigns):
  0 valid · 1 wrong shape · 2 non-finite · 3 untrainable · 4 causal leak · 5 non-deterministic ·
  6 no loss reduction · 7 recurrence/cache inexact · 8 incompatible genotype · 9 crash · 10 timeout
"""
from __future__ import annotations

from typing import Any

from . import verify

CODES = {
    0: "valid", 1: "wrong_shape", 2: "non_finite", 3: "untrainable", 4: "causal_leak",
    5: "non_deterministic", 6: "no_loss_reduction", 7: "recurrence_inexact",
    8: "incompatible_genotype", 9: "crash", 10: "timeout",
}


def shape_code(actual_shape: Any, expected_shape: Any) -> int:
    return 0 if tuple(actual_shape) == tuple(expected_shape) else 1


def finite_code(values: Any) -> int:
    return 0 if verify.all_finite(values) else 2


def trainable_code(grad_norm: float, *, finite: bool = True) -> int:
    return 0 if (finite and grad_norm == grad_norm and grad_norm > 0.0) else 3  # grad_norm==grad_norm: not NaN


def determinism_code(out_a: Any, out_b: Any) -> int:
    return 0 if list(verify._flatten(out_a)) == list(verify._flatten(out_b)) else 5


def loss_reduction_code(loss_before: float, loss_after: float) -> int:
    return 0 if (loss_after < loss_before) else 6


def recurrence_code(full_suffix: Any, cached_suffix: Any, *, rtol: float = 2e-2) -> int:
    """O(1)-cache exactness via RELATIVE tolerance (default 2% — generous "exact", per BUNDLE_TODO #1).
    A logically-exact recurrence is ~1e-7..1e-3 relative even on deep/high-magnitude models; a broken
    one is O(0.1-1). 2% passes the former, catches the latter."""
    return 0 if verify.is_close(full_suffix, cached_suffix, rtol=rtol) else 7


def quant_fidelity(fp_probs_rows: Any, int8_probs_rows: Any) -> float:
    """KL(fp || int8) over heldout rows — distributional deploy fidelity (report, or gate with a max)."""
    return verify.kl_divergence(fp_probs_rows, int8_probs_rows)


def first_failure(*codes: int) -> int:
    """Verdict = first non-zero code in declared order (shape→finite→determinism→causal→recurrence→…)."""
    return next((c for c in codes if c != 0), 0)


def label(code: int) -> str:
    return CODES.get(code, "unknown_%s" % code)
