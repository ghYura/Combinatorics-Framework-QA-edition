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

"""Validated, provider-neutral configuration for the breakpoint sub-suite."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .runtime import RG_FACTOR_NAMES


CONFIG_SCHEMA = "ai-combi-release-gate-config/v1"
DEFAULT_DIFFICULTY_UNITS = (2, 4, 8, 16, 32)
DEFAULT_SESSION_INSTRUCTION = (
    "Run each block in a fresh conversation with no prior task context. "
    "Paste only the text between its BEGIN and END markers."
)


def _bounded_text(value: Any, field: str, *, maximum: int = 128) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    text = value.strip()
    if (
        not text
        or len(text.encode("utf-8")) > maximum
        or any(ord(character) < 32 for character in text)
    ):
        raise ValueError(f"{field} must be nonempty, printable, and at most {maximum} bytes")
    return text


@dataclass(frozen=True)
class TargetCell:
    """One provider/model/effort cell in the bounded manual experiment."""

    provider: str
    model: str
    effort: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider", _bounded_text(self.provider, "provider"))
        object.__setattr__(self, "model", _bounded_text(self.model, "model"))
        object.__setattr__(self, "effort", _bounded_text(self.effort, "effort"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "TargetCell":
        if not isinstance(value, Mapping) or set(value) != {
            "provider",
            "model",
            "effort",
        }:
            raise ValueError("each target cell requires exactly provider, model, and effort")
        return cls(
            provider=value["provider"],
            model=value["model"],
            effort=value["effort"],
        )

    def as_dict(self) -> dict[str, str]:
        return {
            "provider": self.provider,
            "model": self.model,
            "effort": self.effort,
        }


@dataclass(frozen=True)
class BreakpointVariant:
    """A named prompt-construction coordinate used in the first phase."""

    name: str
    factor_signature: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _bounded_text(self.name, "variant name", maximum=64))
        signature = _bounded_text(
            self.factor_signature,
            "factor signature",
            maximum=len(RG_FACTOR_NAMES),
        )
        if len(signature) != len(RG_FACTOR_NAMES) or set(signature) - {"0", "1"}:
            raise ValueError(
                f"factor signature must contain exactly {len(RG_FACTOR_NAMES)} binary digits"
            )
        object.__setattr__(self, "factor_signature", signature)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "BreakpointVariant":
        if not isinstance(value, Mapping) or set(value) != {
            "name",
            "factor_signature",
        }:
            raise ValueError("each breakpoint variant requires name and factor_signature")
        return cls(name=value["name"], factor_signature=value["factor_signature"])

    def as_dict(self) -> dict[str, str]:
        return {"name": self.name, "factor_signature": self.factor_signature}


def default_breakpoint_variants() -> tuple[BreakpointVariant, ...]:
    width = len(RG_FACTOR_NAMES)
    return (
        BreakpointVariant("baseline", "0" * width),
        BreakpointVariant("max-stress", "1" * width),
    )


@dataclass(frozen=True)
class ReleaseGateSuiteConfig:
    """All choices that may legitimately vary between uses of the sub-suite."""

    target_cells: tuple[TargetCell, ...]
    difficulty_units: tuple[int, ...] = DEFAULT_DIFFICULTY_UNITS
    breakpoint_variants: tuple[BreakpointVariant, ...] = ()
    session_instruction: str = DEFAULT_SESSION_INSTRUCTION

    def __post_init__(self) -> None:
        cells = tuple(self.target_cells)
        if not cells:
            raise ValueError("at least one target cell is required")
        if not all(isinstance(cell, TargetCell) for cell in cells):
            raise ValueError("target_cells must contain TargetCell values")
        if len(set(cells)) != len(cells):
            raise ValueError("target cells must be unique")

        units = tuple(self.difficulty_units)
        if not units or len(units) > 6:
            raise ValueError("difficulty_units must contain one through six levels")
        if any(
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < 2
            or value > 64
            or value & (value - 1)
            for value in units
        ):
            raise ValueError("difficulty units must be powers of two from 2 through 64")
        if any(right != left * 2 for left, right in zip(units, units[1:])):
            raise ValueError("difficulty units must form a strictly doubling ladder")

        variants = tuple(self.breakpoint_variants) or default_breakpoint_variants()
        if not all(isinstance(item, BreakpointVariant) for item in variants):
            raise ValueError("breakpoint_variants must contain BreakpointVariant values")
        if len({item.name for item in variants}) != len(variants):
            raise ValueError("breakpoint variant names must be unique")
        if len({item.factor_signature for item in variants}) != len(variants):
            raise ValueError("breakpoint factor signatures must be unique")

        instruction = _bounded_text(
            self.session_instruction,
            "session_instruction",
            maximum=512,
        )
        object.__setattr__(self, "target_cells", cells)
        object.__setattr__(self, "difficulty_units", units)
        object.__setattr__(self, "breakpoint_variants", variants)
        object.__setattr__(self, "session_instruction", instruction)

    @property
    def task_count(self) -> int:
        return len(self.difficulty_units)

    @property
    def prompts_per_cell(self) -> int:
        return self.task_count * len(self.breakpoint_variants)

    @property
    def request_count(self) -> int:
        return len(self.target_cells) * self.prompts_per_cell

    @property
    def constructor_candidate_count(self) -> int:
        return self.task_count * (2 ** len(RG_FACTOR_NAMES))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": CONFIG_SCHEMA,
            "target_cells": [cell.as_dict() for cell in self.target_cells],
            "difficulty_units": list(self.difficulty_units),
            "breakpoint_variants": [
                variant.as_dict() for variant in self.breakpoint_variants
            ],
            "session_instruction": self.session_instruction,
        }


def suite_config(
    target_cells: Iterable[TargetCell],
    *,
    difficulty_units: Iterable[int] = DEFAULT_DIFFICULTY_UNITS,
    breakpoint_variants: Iterable[BreakpointVariant] = (),
    session_instruction: str = DEFAULT_SESSION_INSTRUCTION,
) -> ReleaseGateSuiteConfig:
    return ReleaseGateSuiteConfig(
        target_cells=tuple(target_cells),
        difficulty_units=tuple(difficulty_units),
        breakpoint_variants=tuple(breakpoint_variants),
        session_instruction=session_instruction,
    )


def load_suite_config(path: Path) -> ReleaseGateSuiteConfig:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read release-gate configuration: {path}") from exc
    if not isinstance(document, dict):
        raise ValueError("release-gate configuration must be a JSON object")
    expected = {
        "schema",
        "target_cells",
        "difficulty_units",
        "breakpoint_variants",
        "session_instruction",
    }
    if set(document) != expected or document.get("schema") != CONFIG_SCHEMA:
        raise ValueError(f"configuration fields/schema must match {CONFIG_SCHEMA}")
    cells = document["target_cells"]
    units = document["difficulty_units"]
    variants = document["breakpoint_variants"]
    if not isinstance(cells, list) or not isinstance(units, list) or not isinstance(
        variants, list
    ):
        raise ValueError("target_cells, difficulty_units, and breakpoint_variants must be arrays")
    return suite_config(
        (TargetCell.from_mapping(value) for value in cells),
        difficulty_units=units,
        breakpoint_variants=(
            BreakpointVariant.from_mapping(value) for value in variants
        ),
        session_instruction=document["session_instruction"],
    )
