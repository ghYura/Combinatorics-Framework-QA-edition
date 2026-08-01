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
