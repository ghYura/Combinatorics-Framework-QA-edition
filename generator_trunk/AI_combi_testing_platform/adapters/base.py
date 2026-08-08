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
