"""Deterministic local controls.

These adapters validate the pipeline and oracle.  They are deliberately marked
as controls and must never be advertised as measured AI models.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from .base import Completion, CompletionRequest
from ..oracles import format_reference_response, solve_exact


def _token_estimate(text: str) -> int:
    return max(1, (len(text.encode("utf-8")) + 3) // 4)


@dataclass(frozen=True)
class OracleControlAdapter:
    adapter_id: str = "oracle-control"

    def complete(self, request: CompletionRequest) -> Completion:
        answer = solve_exact(request.task)
        text = format_reference_response(answer, request.output_schema)
        return Completion(
            text=text,
            adapter_id=self.adapter_id,
            model_id="not-a-model",
            latency_us=100 + request.task.complexity * 10,
            input_tokens=_token_estimate(request.prompt),
            output_tokens=_token_estimate(text),
            cost_microusd=0,
            is_control=True,
        )


@dataclass(frozen=True)
class FragileControlAdapter:
    """A deterministic negative control with declared failure boundaries."""

    threshold: int = 4
    adapter_id: str = "fragile-control"

    def complete(self, request: CompletionRequest) -> Completion:
        answer = solve_exact(request.task)
        should_fail = (
            request.task.complexity >= self.threshold
            and (
                request.task.semantic_mode == "loaded"
                or request.prompt.count("Context note") >= 3
            )
        )
        if should_fail:
            if isinstance(answer, Fraction):
                answer = answer + 1
            elif len(answer) >= 2:
                answer = (answer[1], answer[0], *answer[2:])
        text = format_reference_response(answer, request.output_schema)
        return Completion(
            text=text,
            adapter_id=self.adapter_id,
            model_id="deterministic-negative-control",
            latency_us=70 + request.task.complexity * 7,
            input_tokens=_token_estimate(request.prompt),
            output_tokens=_token_estimate(text),
            cost_microusd=0,
            is_control=True,
        )
