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

"""Shared candidate engine for router, prompt-CI, and dataset modes."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import os
from pathlib import Path
from typing import Any

from .adapters import Completion, CompletionRequest, load_adapter
from .invariance import answer_digest, applicable_relations, orbit_key
from .metrics import MetricRecord, sanitize_token
from .oracles import OracleResult, solve_exact, verify_response
from .oracles.exact import ExactAnswer
from .renderers import (
    Marker,
    PromptNode,
    RenderArtifact,
    RenderingPlan,
    apply_program,
    parse_program,
    program_stats,
    render_task,
)
from .task_ir import Task, generate_task


@dataclass
class CandidatePlan:
    """Mutable HEAD/BODY construction state, frozen into immutable IR at TAIL."""

    task_family: str
    seed: int
    complexity: int
    semantic_mode: str = "neutral"
    adapter_id: str = "oracle-control"
    schema: str = "json"
    costume: str = "neutral"
    tone: str = "strict"
    constraint_order: str = "forward"
    distractor: str = "none"
    paraphrase: str = "direct"
    instruction_order: str = "task_first"
    long_range: int = 0
    prompt_version: str = "v1"
    injection: str = "none"
    defense: str = "none"
    environment_id: str = "local"
    generation_revision: str = "v1"
    product_mode: str = "router"
    program_stream: list[PromptNode | Marker] = field(default_factory=list)

    def rendering_plan(self) -> RenderingPlan:
        plan = RenderingPlan(
            schema=self.schema,
            costume=self.costume,
            tone=self.tone,
            constraint_order=self.constraint_order,
            distractor=self.distractor,
            paraphrase=self.paraphrase,
            instruction_order=self.instruction_order,
            long_range=self.long_range,
            prompt_version=self.prompt_version,
            injection=self.injection,
            defense=self.defense,
        )
        plan.validate()
        return plan

    def validate(self) -> None:
        if self.task_family not in {"ordering", "cancellation", "dispatch"}:
            raise ValueError("task_family must be ordering, cancellation, or dispatch")
        if not 1 <= int(self.complexity) <= 8:
            raise ValueError("complexity must be in 1..8")
        if self.semantic_mode not in {"neutral", "loaded"}:
            raise ValueError("semantic_mode must be neutral or loaded")
        if not self.adapter_id:
            raise ValueError("adapter_id must be non-empty")
        if not self.generation_revision:
            raise ValueError("generation_revision must be non-empty")
        if self.product_mode not in {"router", "prompt-ci", "dataset"}:
            raise ValueError("product_mode must be router, prompt-ci, or dataset")
        self.rendering_plan().validate()


@dataclass(frozen=True)
class EvaluationResult:
    code: int
    metrics: MetricRecord
    task: Task | None
    expected: ExactAnswer | None
    render: RenderArtifact | None
    response: str
    oracle: OracleResult | None
    program: PromptNode | None
    completion: Completion | None
    reason: str

    def metrics_line(self) -> str:
        return self.metrics.metrics_line()


def initialize_candidate(
    *,
    family: str = "ordering",
    seed: int = 1729,
    complexity: int = 2,
) -> CandidatePlan:
    return CandidatePlan(task_family=family, seed=seed, complexity=complexity)


def _record(
    *,
    plan: CandidatePlan,
    code: int,
    task: Task | None,
    render: RenderArtifact | None,
    oracle: OracleResult | None,
    completion: Completion | None,
    stats: dict[str, int],
    reason: str,
) -> MetricRecord:
    constraints_met = oracle.constraints_met if oracle else 0
    constraints_total = oracle.constraints_total if oracle else 0
    correct = int(bool(oracle and oracle.correct))
    format_ok = int(bool(oracle and oracle.format_ok))
    all_constraints = int(bool(oracle and oracle.all_constraints_pass))
    # Metamorphic bookkeeping: the digest is the canonical parsed answer, and
    # each orbit_* dimension names an equivalence class this candidate belongs
    # to. The verdict for those classes is a group property, so it is decided in
    # reporting once every member has run -- exactly how repeat_consistency
    # already works. See invariance.py.
    task_hash = task.structural_hash if task else "none"
    digest = answer_digest(oracle.parsed if oracle else None)
    orbit_dimensions = {
        f"orbit_{relation}": orbit_key(plan, task_hash, relation)
        for relation in applicable_relations(plan)
    }
    # The individual presentation axes, not only the composite renderer_id.
    # renderer_id is a hash, so without these a report can tell that two
    # candidates were rendered differently but never which axis differed --
    # which makes per-axis fragility and any interaction map impossible to
    # compute from the results DB.
    presentation_dimensions = {
        "px_schema": plan.schema,
        "px_costume": plan.costume,
        "px_tone": plan.tone,
        "px_constraint_order": plan.constraint_order,
        "px_distractor": plan.distractor,
        "px_paraphrase": plan.paraphrase,
        "px_instruction_order": plan.instruction_order,
        "px_long_range": str(plan.long_range),
        "px_injection": plan.injection,
        "px_defense": plan.defense,
    }
    return MetricRecord(
        dimensions={
            **orbit_dimensions,
            **presentation_dimensions,
            "answer_digest": digest,
            "family": task.family if task else plan.task_family,
            "task_id": task.task_id if task else "construction-failure",
            "task_hash": task.structural_hash if task else "none",
            "renderer_id": render.renderer_id if render else "none",
            "adapter": completion.adapter_id if completion else plan.adapter_id,
            "model": completion.model_id if completion else "none",
            "prompt_version": (
                render.prompt_version if render else plan.prompt_version
            ),
            "environment": sanitize_token(
                os.environ.get("AI_COMBI_ENVIRONMENT_ID")
                or plan.environment_id
            ),
            "generation_revision": plan.generation_revision,
            "product_mode": plan.product_mode,
            "semantic_mode": plan.semantic_mode,
            "reason": reason,
        },
        measurements={
            "correct": correct,
            "format_ok": format_ok,
            "all_constraints_pass": all_constraints,
            "constraints_met": constraints_met,
            "constraints_total": constraints_total,
            "semantic_invariance_ok": correct,
            "complexity": int(plan.complexity),
            "failure_complexity": int(plan.complexity if code else 0),
            "program_depth": int(stats.get("program_depth", 0)),
            "program_nodes": int(stats.get("program_nodes", 0)),
            "program_atoms": int(stats.get("program_atoms", 0)),
            "program_order": int(stats.get("program_order", 0)),
            "latency_us": int(completion.latency_us if completion else 0),
            "input_tokens": int(completion.input_tokens if completion else 0),
            "output_tokens": int(completion.output_tokens if completion else 0),
            "cost_microusd": int(completion.cost_microusd if completion else 0),
            "is_control": int(completion.is_control if completion else 0),
            "provider_error": 0,
            "seed": int(plan.seed),
        },
        verdict_code=code,
    )


def _construction_failure(plan: CandidatePlan, reason: str) -> EvaluationResult:
    record = _record(
        plan=plan,
        code=2,
        task=None,
        render=None,
        oracle=None,
        completion=None,
        stats={},
        reason=reason,
    )
    return EvaluationResult(
        code=2,
        metrics=record,
        task=None,
        expected=None,
        render=None,
        response="",
        oracle=None,
        program=None,
        completion=None,
        reason=reason,
    )


def run_candidate(
    plan: CandidatePlan,
    *,
    adapter: Any | None = None,
    config_path: str | Path | None = None,
) -> EvaluationResult:
    """Run one independent candidate and return its single metrics record.

    Adapter/provider exceptions intentionally propagate.  The Bundle Executor
    must classify infrastructure failures separately from a domain wrong answer.
    """
    try:
        plan.validate()
        task = generate_task(
            plan.task_family,
            seed=int(plan.seed),
            complexity=int(plan.complexity),
            semantic_mode=plan.semantic_mode,
        )
        expected = solve_exact(task)
        program = parse_program(plan.program_stream)
        rendering_plan = apply_program(plan.rendering_plan(), program)
        render = render_task(task, rendering_plan)
        stats = program_stats(program)
    except (TypeError, ValueError) as exc:
        return _construction_failure(
            plan,
            sanitize_token(type(exc).__name__ + "_" + str(exc), "construction"),
        )

    selected = adapter or load_adapter(plan.adapter_id, config_path=config_path)
    completion = selected.complete(
        CompletionRequest(
            prompt=render.prompt,
            task=task,
            output_schema=render.schema,
            prompt_version=render.prompt_version,
            request_id=f"{task.task_id}-{render.renderer_id}",
        )
    )
    oracle = verify_response(
        task,
        completion.text,
        render.schema,
        expected=expected,
    )
    code = oracle.code
    record = _record(
        plan=plan,
        code=code,
        task=task,
        render=render,
        oracle=oracle,
        completion=completion,
        stats=stats,
        reason=oracle.reason,
    )
    return EvaluationResult(
        code=code,
        metrics=record,
        task=task,
        expected=expected,
        render=render,
        response=completion.text,
        oracle=oracle,
        program=program,
        completion=completion,
        reason=oracle.reason,
    )
