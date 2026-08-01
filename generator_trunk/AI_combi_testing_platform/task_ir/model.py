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


Task: TypeAlias = OrderingTask | CancellationTask


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
    raise ValueError(f"unsupported task family: {family!r}")
