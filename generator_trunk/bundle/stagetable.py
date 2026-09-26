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

"""The orchestrator's explicit dependency seam.

Historically the run orchestrator called its stages as module-level globals in
``bundle.cli``, and anything that needed to substitute one rebound the name on
that module -- ``bundle_cli.stage_gen = my_stage``. That worked, but it made the
module namespace a load-bearing public interface: a function moved to another
module resolves globals in its *own* module, so relocating the orchestrator
silently disabled every override. It also meant the substitution points were
invisible in the signature -- you had to read the body to learn they existed.

`StageTable` makes them explicit and injectable. The orchestrator takes one and
calls through it; a caller that wants a different Generator passes a table with
``gen=`` replaced instead of mutating a module.

The table also carries three non-stage collaborators (``component_artifacts``,
``optional_tables``, ``record_handoff_manifest``) because the orchestrator is
their only caller and they are substituted for the same reason the stages are.

Deliberately *not* included: ``psql``. It is a shared low-level accessor that
four sibling helpers call directly, so injecting it here would cover the
orchestrator body and silently miss those -- a seam that looks complete and is
not is worse than no seam at all. Substituting the database still means patching
``psql`` in the module that defines the caller.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable


@dataclass(frozen=True)
class StageTable:
    """Every collaborator the run/resume orchestrator invokes indirectly.

    Frozen so a table cannot be mutated in place after a run has started --
    swapping a stage mid-run is exactly the class of surprise this type exists
    to remove. Use :meth:`with_` to derive a variant.
    """

    # pipeline stages, in execution order
    gen: Callable[..., Any]
    core: Callable[..., Any]
    sieve: Callable[..., Any]
    draw: Callable[..., Any]
    seed_bias: Callable[..., Any]
    reader: Callable[..., Any]
    executor: Callable[..., Any]
    analyzer: Callable[..., Any]
    stress: Callable[..., Any]

    # orchestrator-only collaborators: helpers no other code path calls, which
    # is what makes them safe to substitute without surprising a third party
    component_artifacts: Callable[..., Any]
    optional_tables: Callable[..., Any]
    record_handoff_manifest: Callable[..., Any]
    # rows Core wrote into fw_opt<size>, summed over the consumed sizes — how a run
    # measures the optional multiplier when the spec can only bound it (verb chains,
    # FW_Group, braces in optional sheets: legacy XLSX input, re-declared TOML slots)
    optional_table_rows: "Callable[..., Any] | None" = None

    def with_(self, **overrides: Callable[..., Any]) -> "StageTable":
        """Return a copy with the named collaborators replaced.

        >>> table.with_(gen=my_exact_workbook_stage)   # doctest: +SKIP
        """
        unknown = set(overrides) - {f for f in self.__dataclass_fields__}
        if unknown:
            raise TypeError(f"unknown stage(s): {', '.join(sorted(unknown))}")
        return replace(self, **overrides)
