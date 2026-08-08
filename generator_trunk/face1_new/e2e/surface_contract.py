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

"""Static coverage gate between NiceGUI source and ``selectors.toml``."""

from __future__ import annotations

import ast
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from face1_new.run_ui import GROUP_KEYS

from .selectors import DEFAULT_SELECTORS, SelectorRegistry


ROOT = Path(__file__).resolve().parents[2]
UI_SOURCES = (ROOT / "face1_new" / "app.py", ROOT / "face1_new" / "run_ui.py", ROOT / "face1_new" / "invitation_ui.py")
INTERACTIVE_KINDS = (
    "button", "input", "number", "select", "checkbox", "textarea",
    "upload", "expansion", "tab", "dialog", "table",
)


@dataclass(frozen=True)
class SurfaceInventory:
    calls: Counter[str]
    static_labels: dict[str, frozenset[str]]
    icon_only: frozenset[str]


def scan_surface(paths: Iterable[Path] = UI_SOURCES) -> SurfaceInventory:
    calls: Counter[str] = Counter()
    labels: dict[str, set[str]] = {kind: set() for kind in INTERACTIVE_KINDS}
    icon_only: set[str] = set()
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "ui"
                and node.func.attr in INTERACTIVE_KINDS
            ):
                continue
            kind = node.func.attr
            calls[kind] += 1
            found_label = False
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                labels[kind].add(node.args[0].value)
                found_label = True
            for keyword in node.keywords:
                if keyword.arg == "label" and isinstance(keyword.value, ast.Constant) \
                        and isinstance(keyword.value.value, str):
                    labels[kind].add(keyword.value.value)
                    found_label = True
                if not found_label and keyword.arg == "icon" and isinstance(keyword.value, ast.Constant) \
                        and isinstance(keyword.value.value, str):
                    icon_only.add(keyword.value.value)
    return SurfaceInventory(calls, {key: frozenset(value) for key, value in labels.items()}, frozenset(icon_only))


def selector_contract_problems(
    registry: SelectorRegistry = DEFAULT_SELECTORS,
    inventory: SurfaceInventory | None = None,
) -> list[str]:
    inventory = inventory or scan_surface()
    problems: list[str] = []
    expected_counts = {key: int(value) for key, value in registry.section("inventory").items()}
    for kind in INTERACTIVE_KINDS:
        if inventory.calls[kind] != expected_counts.get(kind):
            problems.append(
                f"ui.{kind} call count changed: source={inventory.calls[kind]} "
                f"registry={expected_counts.get(kind)}"
            )
    registered_labels = set()
    for section in ("buttons", "fields", "checkboxes", "expansions", "tabs"):
        registered_labels.update(str(value) for value in registry.section(section).values())
    for kind, values in inventory.static_labels.items():
        for value in sorted(values - registered_labels):
            problems.append(f"static ui.{kind} label is unregistered: {value!r}")
    registered_icons = set(str(value) for value in registry.section("icons").values())
    for icon in sorted(inventory.icon_only - registered_icons):
        problems.append(f"icon-only button is unregistered: {icon!r}")
    registered_groups = set(str(value) for value in registry.section("expansions").values())
    for group in GROUP_KEYS:
        if group not in registered_groups:
            problems.append(f"dynamic advanced expansion is unregistered: {group!r}")
    return problems
