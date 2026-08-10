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

"""Finite K=V records harvested by the Python Executor and Analyzer."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Mapping


_TOKEN_RE = re.compile(r"[^A-Za-z0-9_.:@+-]+")


def sanitize_token(value: object, default: str = "none") -> str:
    token = _TOKEN_RE.sub("_", str(value).strip()).strip("_")
    return token or default


@dataclass(frozen=True)
class MetricRecord:
    dimensions: Mapping[str, str]
    measurements: Mapping[str, int | float]
    verdict_code: int

    def __post_init__(self) -> None:
        if self.verdict_code < 0:
            raise ValueError("verdict_code must be nonnegative")
        for key, value in self.measurements.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"measurement {key!r} is not numeric")
            if not math.isfinite(float(value)):
                raise ValueError(f"measurement {key!r} is not finite")

    def metrics_line(self) -> str:
        """Return exactly one whitespace-separated line beginning with ``app=``."""
        dimensions = {"app": "ai_combi_testing", **dict(self.dimensions)}
        parts: list[str] = []
        for key, value in dimensions.items():
            parts.append(f"{sanitize_token(key)}={sanitize_token(value)}")
        for key, value in self.measurements.items():
            rendered = str(int(value)) if isinstance(value, int) else f"{value:.9g}"
            parts.append(f"{sanitize_token(key)}={rendered}")
        parts.append(f"FW_VAR={self.verdict_code}")
        return " ".join(parts)
