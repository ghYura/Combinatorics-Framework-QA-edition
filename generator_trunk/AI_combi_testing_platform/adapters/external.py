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

"""Opt-in OpenAI-compatible HTTPS adapter with fail-closed budget guards."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import socket
import time
from urllib import error, parse, request

from .base import AdapterInfrastructureError, Completion, CompletionRequest


@dataclass(frozen=True)
class ExternalHTTPConfig:
    adapter_id: str
    endpoint: str
    model: str
    api_key_env: str
    enabled: bool = False
    timeout_seconds: float = 30.0
    max_output_tokens: int = 256
    cost_per_request_microusd: int = 0
    request_budget: int = 0
    monetary_budget_microusd: int = 0

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "ExternalHTTPConfig":
        return cls(
            adapter_id=str(value.get("id") or ""),
            endpoint=str(value.get("endpoint") or ""),
            model=str(value.get("model") or ""),
            api_key_env=str(value.get("api_key_env") or ""),
            enabled=value.get("enabled") is True,
            timeout_seconds=float(value.get("timeout_seconds") or 30.0),
            max_output_tokens=int(value.get("max_output_tokens") or 256),
            cost_per_request_microusd=int(
                value.get("cost_per_request_microusd") or 0
            ),
            request_budget=int(value.get("request_budget") or 0),
            monetary_budget_microusd=int(
                value.get("monetary_budget_microusd") or 0
            ),
        )

    def validate(self) -> None:
        if not self.adapter_id or not self.model or not self.api_key_env:
            raise AdapterInfrastructureError(
                "external adapter id, model, and api_key_env are required"
            )
        url = parse.urlparse(self.endpoint)
        insecure_allowed = os.environ.get("AI_COMBI_ALLOW_INSECURE_HTTP") == "1"
        if url.scheme != "https" and not insecure_allowed:
            raise AdapterInfrastructureError(
                "external endpoint must use HTTPS; insecure HTTP needs an explicit "
                "AI_COMBI_ALLOW_INSECURE_HTTP=1 test-only override"
            )
        if not url.netloc:
            raise AdapterInfrastructureError("external endpoint is invalid")
        if self.timeout_seconds <= 0 or self.max_output_tokens < 1:
            raise AdapterInfrastructureError("external timeout/token limits are invalid")
        if self.request_budget < 1:
            raise AdapterInfrastructureError(
                "external adapter needs a positive request_budget"
            )
        if self.cost_per_request_microusd < 0:
            raise AdapterInfrastructureError("cost cannot be negative")
        if (
            self.cost_per_request_microusd > 0
            and self.monetary_budget_microusd < self.cost_per_request_microusd
        ):
            raise AdapterInfrastructureError(
                "per-request estimate exceeds the configured monetary budget"
            )


@dataclass
class ExternalHTTPAdapter:
    config: ExternalHTTPConfig

    @property
    def adapter_id(self) -> str:
        return self.config.adapter_id

    def complete(self, completion_request: CompletionRequest) -> Completion:
        if os.environ.get("AI_COMBI_ALLOW_EXTERNAL") != "1":
            raise AdapterInfrastructureError(
                "external execution is disabled; set AI_COMBI_ALLOW_EXTERNAL=1 "
                "only after reviewing request and monetary budgets"
            )
        if not self.config.enabled:
            raise AdapterInfrastructureError(
                f"external adapter {self.adapter_id!r} is disabled in configuration"
            )
        self.config.validate()
        api_key = os.environ.get(self.config.api_key_env)
        if not api_key:
            raise AdapterInfrastructureError(
                f"credential environment variable {self.config.api_key_env!r} is not set"
            )
        body = json.dumps(
            {
                "model": self.config.model,
                "messages": [{"role": "user", "content": completion_request.prompt}],
                "temperature": 0,
                "max_tokens": self.config.max_output_tokens,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        outbound = request.Request(
            self.config.endpoint,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        started = time.monotonic_ns()
        try:
            with request.urlopen(
                outbound,
                timeout=self.config.timeout_seconds,
            ) as response:
                document = json.loads(response.read().decode("utf-8"))
        except (error.URLError, socket.timeout, TimeoutError, json.JSONDecodeError) as exc:
            raise AdapterInfrastructureError(
                f"external provider request failed: {type(exc).__name__}"
            ) from exc
        latency_us = max(1, (time.monotonic_ns() - started) // 1_000)
        try:
            text = str(document["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise AdapterInfrastructureError(
                "external provider response lacks choices[0].message.content"
            ) from exc
        usage = document.get("usage") if isinstance(document, dict) else None
        usage = usage if isinstance(usage, dict) else {}
        return Completion(
            text=text,
            adapter_id=self.adapter_id,
            model_id=self.config.model,
            latency_us=int(latency_us),
            input_tokens=max(0, int(usage.get("prompt_tokens") or 0)),
            output_tokens=max(0, int(usage.get("completion_tokens") or 0)),
            cost_microusd=self.config.cost_per_request_microusd,
            is_control=False,
        )
