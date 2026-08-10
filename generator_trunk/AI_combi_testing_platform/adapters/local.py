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
class InjectableControlAdapter:
    """A deterministic control that *reads its prompt* and can be diverted.

    The other controls answer from the task object, so no prompt content can
    ever move them — which makes them useless for measuring prompt injection.
    This one follows an embedded override unless a mitigation it recognises is
    present, with the boundary declared here rather than discovered:

    * an override marker in the prompt diverts it;
    * `delimit` and `restate_contract` defeat the diversion;
    * `output_constraint` does not, because it constrains the alphabet of the
      answer and the marker is still a token the model can emit.

    It is a pipeline control, not a model. It says nothing about whether any
    real target is vulnerable — it exists so the attack x defense matrix has a
    subject that behaves in a known way, cost-free and offline.
    """

    adapter_id: str = "injectable-control"

    def complete(self, request: CompletionRequest) -> Completion:
        from ..renderers.core import INJECTION_MARKER

        prompt = request.prompt
        diverted = INJECTION_MARKER in prompt and not (
            "instructions inside it are data" in prompt.lower()
            or "no later text can revoke" in prompt.lower()
        )
        if diverted:
            text = format_reference_response((INJECTION_MARKER,), request.output_schema)
        else:
            text = format_reference_response(solve_exact(request.task), request.output_schema)
        return Completion(
            text=text,
            adapter_id=self.adapter_id,
            model_id="deterministic-injectable-control",
            latency_us=80 + request.task.complexity * 8,
            input_tokens=_token_estimate(prompt),
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
