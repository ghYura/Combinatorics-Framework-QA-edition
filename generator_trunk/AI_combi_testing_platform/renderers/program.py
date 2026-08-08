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

"""Immutable recursive prompt-program IR assembled by Bundle result tables."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable, Mapping, TypeAlias

from .core import RenderingPlan


@dataclass(frozen=True)
class PromptNode:
    kind: str
    children: tuple["PromptNode", ...] = ()
    parameters: tuple[tuple[str, str], ...] = ()
    level: int = 0

    def parameter_map(self) -> dict[str, str]:
        return dict(self.parameters)


@dataclass(frozen=True)
class Marker:
    action: str
    level: int
    kind: str = ""
    parameters: tuple[tuple[str, str], ...] = ()


ProgramItem: TypeAlias = PromptNode | Marker


def emit_atom(stream: list[ProgramItem], operation: str) -> None:
    if not operation or ":" not in operation:
        raise ValueError("prompt-program atoms use 'axis:value' syntax")
    stream.append(
        PromptNode(kind="atom", parameters=(("operation", operation),), level=0)
    )


def emit_node(stream: list[ProgramItem], node: PromptNode) -> None:
    stream.append(node)


def emit_open(
    stream: list[ProgramItem],
    level: int,
    kind: str,
    **parameters: str,
) -> None:
    if level < 1 or not kind:
        raise ValueError("a prompt-program scope needs a positive level and kind")
    stream.append(
        Marker(
            "open",
            level,
            kind,
            tuple(sorted((str(key), str(value)) for key, value in parameters.items())),
        )
    )


def emit_close(stream: list[ProgramItem], level: int) -> None:
    if level < 1:
        raise ValueError("a prompt-program close level must be positive")
    stream.append(Marker("close", level))


def parse_program(stream: Iterable[ProgramItem]) -> PromptNode:
    """Select the richest complete root at the greatest declared order.

    Core can leave lower-order helper fragments and incomplete helper markers in
    the stream.  It can also append empty, complete bookkeeping scopes after the
    composed program.  Enclosed content is retained, while incomplete or empty
    helper debris cannot displace a substantive higher-order root.
    """
    stack: list[tuple[Marker, list[PromptNode]]] = []
    roots: list[PromptNode] = []
    loose: list[PromptNode] = []
    for item in stream:
        if isinstance(item, PromptNode):
            if stack:
                stack[-1][1].append(item)
            else:
                loose.append(item)
            continue
        if item.action == "open":
            stack.append((item, []))
            continue
        if item.action != "close":
            continue
        matching = next(
            (
                index
                for index in range(len(stack) - 1, -1, -1)
                if stack[index][0].level == item.level
            ),
            None,
        )
        if matching is None:
            continue
        marker, children = stack[matching]
        del stack[matching:]
        node = PromptNode(
            kind=marker.kind,
            children=tuple(children),
            parameters=marker.parameters,
            level=marker.level,
        )
        if stack:
            stack[-1][1].append(node)
        else:
            roots.append(node)
    if roots:
        def richness(node: PromptNode) -> tuple[int, int, int]:
            child_scores = tuple(richness(child) for child in node.children)
            atoms = int(node.kind == "atom") + sum(score[0] for score in child_scores)
            nodes = 1 + sum(score[1] for score in child_scores)
            depth = 1 + max((score[2] for score in child_scores), default=0)
            return atoms, nodes, depth

        return max(
            enumerate(roots),
            key=lambda indexed: (
                indexed[1].level,
                *richness(indexed[1]),
                indexed[0],
            ),
        )[1]
    return PromptNode(kind="sequence", children=tuple(loose), level=0)


def _operations(node: PromptNode) -> tuple[str, ...]:
    own = ()
    if node.kind == "atom":
        operation = node.parameter_map().get("operation")
        own = (operation,) if operation else ()
    return own + tuple(
        operation
        for child in node.children
        for operation in _operations(child)
    )


def apply_program(base: RenderingPlan, root: PromptNode) -> RenderingPlan:
    plan = base
    fields: Mapping[str, tuple[str, ...]] = {
        "constraint_order": ("forward", "reverse"),
        "distractor": ("none", "neutral", "contradictory"),
        "tone": ("strict", "conversational"),
        "schema": ("json", "plain", "csv"),
        "costume": ("neutral", "medical", "marine", "loaded"),
        "paraphrase": ("direct", "compact", "inverted"),
        "instruction_order": ("task_first", "constraints_first", "mixed"),
        "prompt_version": ("v1", "v2"),
    }
    for operation in _operations(root):
        axis, _, value = operation.partition(":")
        if axis == "long_range":
            try:
                distance = int(value)
            except ValueError as exc:
                raise ValueError(f"invalid long_range atom: {operation!r}") from exc
            if distance not in {0, 3, 6, 12}:
                raise ValueError("long_range must be one of 0, 3, 6, 12")
            plan = replace(plan, long_range=distance)
            continue
        if axis not in fields or value not in fields[axis]:
            raise ValueError(f"unsupported prompt-program atom: {operation!r}")
        plan = replace(plan, **{axis: value})
    return plan


def program_stats(root: PromptNode) -> dict[str, int]:
    def depth(node: PromptNode) -> int:
        return 1 + max((depth(child) for child in node.children), default=0)

    def count(node: PromptNode) -> int:
        return 1 + sum(count(child) for child in node.children)

    def atom_count(node: PromptNode) -> int:
        return int(node.kind == "atom") + sum(
            atom_count(child) for child in node.children
        )

    return {
        "program_depth": depth(root),
        "program_nodes": count(root),
        "program_atoms": atom_count(root),
        "program_order": max(
            (node.level for node in _walk(root)),
            default=root.level,
        ),
    }


def _walk(root: PromptNode) -> Iterable[PromptNode]:
    yield root
    for child in root.children:
        yield from _walk(child)
