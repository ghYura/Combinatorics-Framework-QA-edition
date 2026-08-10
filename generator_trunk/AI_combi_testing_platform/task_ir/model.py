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

"""Canonical problems generated before any model-facing language exists.

The task objects are frozen and serialize canonically.  Renderers receive one
of these objects, never an oracle answer or certificate.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Literal, TypeAlias


SCHEMA_VERSION = "ai-combi.task/v1"
NEUTRAL_NAMES = (
    "Aster",
    "Beryl",
    "Cedar",
    "Delta",
    "Ember",
    "Flint",
    "Grove",
    "Harbor",
)
LOADED_NAMES = (
    "Zero",
    "False",
    "Infinity",
    "One",
    "Null",
    "Prime",
    "Negative",
    "Undefined",
)


def _stable_order(values: tuple[str, ...], seed: int, namespace: str) -> tuple[str, ...]:
    return tuple(
        sorted(
            values,
            key=lambda value: hashlib.sha256(
                f"{namespace}:{seed}:{value}".encode("utf-8")
            ).digest(),
        )
    )


def _stable_int(seed: int, namespace: str, low: int, high: int) -> int:
    if low > high:
        raise ValueError("low must not exceed high")
    digest = hashlib.sha256(f"{namespace}:{seed}".encode("utf-8")).digest()
    return low + int.from_bytes(digest[:8], "big") % (high - low + 1)


def _canonical_hash(document: dict[str, Any]) -> str:
    encoded = json.dumps(
        document,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, order=True)
class OrderingConstraint:
    before: str
    after: str

    def __post_init__(self) -> None:
        if not self.before or not self.after or self.before == self.after:
            raise ValueError("an ordering constraint needs two distinct identifiers")

    def canonical_dict(self) -> dict[str, str]:
        return {"before": self.before, "after": self.after}


@dataclass(frozen=True)
class OrderingTask:
    seed: int
    entities: tuple[str, ...]
    constraints: tuple[OrderingConstraint, ...]
    complexity: int
    semantic_mode: Literal["neutral", "loaded"] = "neutral"
    schema_version: str = SCHEMA_VERSION
    family: Literal["ordering"] = "ordering"

    def __post_init__(self) -> None:
        if not 3 <= len(self.entities) <= 8:
            raise ValueError("ordering tasks require 3..8 unique entities")
        if len(set(self.entities)) != len(self.entities):
            raise ValueError("ordering task entities must be unique")
        entity_set = set(self.entities)
        if not self.constraints:
            raise ValueError("ordering tasks require at least one constraint")
        if any(
            constraint.before not in entity_set or constraint.after not in entity_set
            for constraint in self.constraints
        ):
            raise ValueError("ordering constraints must reference declared entities")
        if self.complexity < 1:
            raise ValueError("complexity must be positive")

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema_version,
            "family": self.family,
            "seed": self.seed,
            "entities": list(self.entities),
            "constraints": [
                constraint.canonical_dict() for constraint in self.constraints
            ],
            "complexity": self.complexity,
            "semantic_mode": self.semantic_mode,
        }

    @property
    def structural_hash(self) -> str:
        return _canonical_hash(self.canonical_dict())

    @property
    def task_id(self) -> str:
        return f"ord-{self.structural_hash[:16]}"


@dataclass(frozen=True)
class CancellationTask:
    seed: int
    symbol: str
    symbol_value: int
    numerator: int
    denominator: int
    inverse_depth: int
    complexity: int
    semantic_mode: Literal["neutral", "loaded"] = "neutral"
    schema_version: str = SCHEMA_VERSION
    family: Literal["cancellation"] = "cancellation"

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("the cancellation symbol must be non-empty")
        if self.symbol_value == 0:
            raise ValueError("the assigned symbol value must be nonzero")
        if self.denominator == 0:
            raise ValueError("the denominator must be nonzero")
        if not 1 <= self.inverse_depth <= 8:
            raise ValueError("inverse_depth must be in 1..8")
        if self.complexity < 1:
            raise ValueError("complexity must be positive")

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema_version,
            "family": self.family,
            "seed": self.seed,
            "symbol": self.symbol,
            "symbol_value": self.symbol_value,
            "numerator": self.numerator,
            "denominator": self.denominator,
            "inverse_depth": self.inverse_depth,
            "complexity": self.complexity,
            "semantic_mode": self.semantic_mode,
        }

    @property
    def structural_hash(self) -> str:
        return _canonical_hash(self.canonical_dict())

    @property
    def task_id(self) -> str:
        return f"cancel-{self.structural_hash[:16]}"


#: The actions a dispatch run may contain, in the order they must legally occur.
DISPATCH_ACTIONS: tuple[str, ...] = ("reserve", "charge", "ship", "notify", "settle")


@dataclass(frozen=True)
class DispatchTask:
    """An agentic order-sensitivity task: which steps actually took effect?

    The target is handed a sequence of instructions *as delivered* — which is
    not necessarily a legal order — plus zero or more injected step failures,
    and must report the actions that really took effect. This is state tracking
    over time rather than a static puzzle, and it is exactly solvable by
    simulation, so the oracle stays exact.

    The design is lifted from the companion `combination_thinking_tutor` SUT,
    where an exhaustive sweep found that **120 of 144 legal orderings violate**
    the dispatch rules. Order is where the failures live, and permuting delivery
    order is the one axis a single-turn prompt suite cannot reach.
    """

    seed: int
    delivered: tuple[str, ...]
    failed_steps: tuple[int, ...]
    complexity: int
    semantic_mode: Literal["neutral", "loaded"] = "neutral"
    schema_version: str = SCHEMA_VERSION
    family: Literal["dispatch"] = "dispatch"

    def __post_init__(self) -> None:
        if not self.delivered:
            raise ValueError("a dispatch task needs at least one delivered step")
        unknown = set(self.delivered) - set(DISPATCH_ACTIONS)
        if unknown:
            raise ValueError(f"unknown dispatch actions: {sorted(unknown)}")
        for index in self.failed_steps:
            if not 0 <= index < len(self.delivered):
                raise ValueError("failed step index outside the delivered sequence")
        if len(set(self.failed_steps)) != len(self.failed_steps):
            raise ValueError("failed step indices must be unique")
        if self.complexity < 1:
            raise ValueError("complexity must be positive")

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema_version,
            "family": self.family,
            "seed": self.seed,
            "delivered": list(self.delivered),
            "failed_steps": list(self.failed_steps),
            "complexity": self.complexity,
            "semantic_mode": self.semantic_mode,
        }

    @property
    def structural_hash(self) -> str:
        return _canonical_hash(self.canonical_dict())

    @property
    def task_id(self) -> str:
        return f"dispatch-{self.structural_hash[:16]}"


Task: TypeAlias = OrderingTask | CancellationTask | DispatchTask


def _ordering_task(seed: int, complexity: int, semantic_mode: str) -> OrderingTask:
    names = LOADED_NAMES if semantic_mode == "loaded" else NEUTRAL_NAMES
    count = min(6, 3 + (complexity - 1) // 2)
    entities = _stable_order(names, seed, "entities")[:count]
    hidden_order = _stable_order(entities, seed, "hidden-order")
    possible = tuple(
        OrderingConstraint(hidden_order[left], hidden_order[right])
        for left in range(len(hidden_order))
        for right in range(left + 1, len(hidden_order))
    )
    shuffled = tuple(
        sorted(
            possible,
            key=lambda item: hashlib.sha256(
                f"edge:{seed}:{item.before}:{item.after}".encode("utf-8")
            ).digest(),
        )
    )
    constraint_count = min(max(1, complexity), len(shuffled))
    return OrderingTask(
        seed=seed,
        entities=entities,
        constraints=shuffled[:constraint_count],
        complexity=complexity,
        semantic_mode=semantic_mode,  # type: ignore[arg-type]
    )


def _cancellation_task(
    seed: int,
    complexity: int,
    semantic_mode: str,
) -> CancellationTask:
    names = LOADED_NAMES if semantic_mode == "loaded" else NEUTRAL_NAMES
    symbol = _stable_order(names, seed, "symbol")[0]
    symbol_value = _stable_int(seed, "symbol-value", 2, 19)
    numerator = _stable_int(seed, "numerator", 7, 47)
    denominator = _stable_int(seed, "denominator", 2, 13)
    return CancellationTask(
        seed=seed,
        symbol=symbol,
        symbol_value=symbol_value,
        numerator=numerator,
        denominator=denominator,
        inverse_depth=min(8, max(1, complexity)),
        complexity=complexity,
        semantic_mode=semantic_mode,  # type: ignore[arg-type]
    )


def generate_task(
    family: str,
    *,
    seed: int,
    complexity: int,
    semantic_mode: str = "neutral",
) -> Task:
    """Generate a deterministic immutable task without rendering or solving it."""
    if complexity < 1 or complexity > 8:
        raise ValueError("complexity must be in 1..8")
    if semantic_mode not in {"neutral", "loaded"}:
        raise ValueError("semantic_mode must be neutral or loaded")
    if family == "ordering":
        return _ordering_task(seed, complexity, semantic_mode)
    if family == "cancellation":
        return _cancellation_task(seed, complexity, semantic_mode)
    if family == "dispatch":
        return _dispatch_task(seed, complexity, semantic_mode)
    raise ValueError(f"unsupported task family: {family!r}")


def _dispatch_task(seed: int, complexity: int, semantic_mode: str) -> DispatchTask:
    """Deterministically deal a delivery order and a set of step failures.

    Complexity controls how many actions are in play; the delivered order is a
    stable shuffle rather than the legal order, because a sequence that is
    already legal exercises none of the state tracking this family exists for.
    """
    action_count = min(len(DISPATCH_ACTIONS), max(2, complexity))
    actions = DISPATCH_ACTIONS[:action_count]
    delivered = _stable_order(actions, seed, "dispatch-delivery")
    # A failure is the optional "sudden action": the step is delivered and does
    # not take effect. At most one per two actions keeps the task solvable by
    # reasoning rather than by exhaustive guessing.
    failure_budget = max(0, (action_count - 1) // 2)
    failed: list[int] = []
    for slot in range(failure_budget):
        index = _stable_int(seed, f"dispatch-failure-{slot}", 0, action_count - 1)
        if index not in failed:
            failed.append(index)
    return DispatchTask(
        seed=seed,
        delivered=tuple(delivered),
        failed_steps=tuple(sorted(failed)),
        complexity=complexity,
        semantic_mode=semantic_mode,       # type: ignore[arg-type]
    )
