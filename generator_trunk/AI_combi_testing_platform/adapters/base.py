"""Adapter boundary shared by local controls and external providers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..task_ir import Task


class AdapterInfrastructureError(RuntimeError):
    """Provider/network/configuration failure, not a wrong domain answer."""


@dataclass(frozen=True)
class CompletionRequest:
    prompt: str
    task: Task
    output_schema: str
    prompt_version: str
    request_id: str


@dataclass(frozen=True)
class Completion:
    text: str
    adapter_id: str
    model_id: str
    latency_us: int
    input_tokens: int
    output_tokens: int
    cost_microusd: int
    is_control: bool

    def __post_init__(self) -> None:
        numeric = (
            self.latency_us,
            self.input_tokens,
            self.output_tokens,
            self.cost_microusd,
        )
        if any(value < 0 for value in numeric):
            raise ValueError("completion measurements must be nonnegative")


class Adapter(Protocol):
    adapter_id: str

    def complete(self, request: CompletionRequest) -> Completion:
        ...
