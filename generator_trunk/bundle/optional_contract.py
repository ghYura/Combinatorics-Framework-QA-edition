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

"""The canonical optional-table contract (docs/32 finding F4).

`FW_Optional` makes *presence* a degree of freedom. Core materializes optional
combinations of each requested size into `fw_opt<size>` tables; the Reader joins
them onto each `fw_final` row at assembly time. Two similarly-named properties
own the two halves:

```text
core.optional.includeOptionalCombiPairsToDBCSVList   -> P, the sizes Core PRODUCES
reader.core.isOptCSVList                             -> R, the sizes Reader CONSUMES
```

The required invariant is ``R ⊆ P``: the Reader may not consume a table Core
never built. For a normal complete Bundle run, ``R = P = 1..N``.

Before this module the two properties were rendered independently from the same
`n_opt` integer — correct in the launcher, but nothing *stated* the relationship
or checked it, and all four standalone property templates violated it (the audit
records the exact values). Deriving both from one recorded contract, validating
it during side-effect-free planning, and re-checking materialization after Core
is what turns a convention into an enforced invariant.

The contract also predicts the Reader's expansion exactly, including for a
deliberate subset, via elementary symmetric polynomials over the optional slot
sizes — so `fw_final × multiplier` is a real expectation the reader stage can be
reconciled against rather than a guess.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

SCHEMA = "bundle.optional-table-contract/v1"

#: Core's producer property and the Reader's consumer property.
CORE_PROPERTY = "core.optional.includeOptionalCombiPairsToDBCSVList"
READER_PROPERTY = "reader.core.isOptCSVList"
READER_ENABLE_PROPERTY = "reader.core.processIsOpt"
READER_BOTH_PROPERTY = "reader.core.processBothFinalAndOpt"

#: The only supported consumption modes. A Reader subset is legitimate, but only
#: as an explicitly named mode with documented count semantics -- never as the
#: emergent result of two property files drifting apart.
MODE_COMPLETE = "complete"
MODE_EXPLICIT_SUBSET = "explicit-subset"
MODES = (MODE_COMPLETE, MODE_EXPLICIT_SUBSET)


class OptionalContractError(ValueError):
    """The optional-table contract is unsatisfiable or internally inconsistent."""


def _elementary_symmetric(sizes: "Sequence[int]") -> "list[int]":
    """``e[k]`` = number of optional combinations of exactly size *k*.

    ``e[k]`` is the elementary symmetric polynomial over the per-slot value
    counts: choosing k distinct optional slots and one value from each. With N
    one-valued slots this reduces to C(N,k), matching the worked example in
    docs/27 (four slots -> 4, 6, 4, 1).
    """
    e = [1] + [0] * len(sizes)
    for n in sizes:
        for k in range(len(sizes), 0, -1):
            e[k] += e[k - 1] * n
    return e


@dataclass(frozen=True)
class OptionalTableContract:
    """One run's optional-table agreement between Core and Reader."""

    optional_sheet_count: int
    slot_value_counts: "tuple[int, ...]"
    produced_sizes: "tuple[int, ...]"        # P
    consumed_sizes: "tuple[int, ...]"        # R
    mode: str
    sources: "Mapping[str, str]"             # value -> the layer that decided it

    # ---------------------------------------------------------------- counts --
    @property
    def active(self) -> bool:
        return self.optional_sheet_count > 0

    @property
    def complete(self) -> bool:
        return self.mode == MODE_COMPLETE

    def combinations_of_size(self, size: int) -> int:
        e = _elementary_symmetric(self.slot_value_counts)
        return e[size] if 0 <= size < len(e) else 0

    def expected_multiplier(self) -> int:
        """Reader candidates per `fw_final` row: 1 (the absent branch) plus one
        per consumed optional combination. Exact -- there is no UNKNOWN here,
        because every factor is declared in the specification."""
        if not self.active:
            return 1
        return 1 + sum(self.combinations_of_size(size) for size in self.consumed_sizes)

    def required_tables(self) -> "tuple[str, ...]":
        """The `fw_opt<size>` tables that must exist before the Reader starts."""
        return tuple(f"fw_opt{size}" for size in self.consumed_sizes)

    # ------------------------------------------------------------ properties --
    def core_property_value(self) -> str:
        return ",".join(str(s) for s in self.produced_sizes)

    def reader_property_value(self) -> str:
        return ",".join(str(s) for s in self.consumed_sizes)

    def core_edits(self) -> "dict[str, str]":
        """Property edits for Core, rendered FROM the contract."""
        if not self.active:
            return {}
        return {CORE_PROPERTY: self.core_property_value()}

    def reader_edits(self) -> "dict[str, str]":
        """Property edits for the Reader, rendered FROM the same contract."""
        if not self.active:
            return {READER_ENABLE_PROPERTY: "false"}
        return {
            READER_ENABLE_PROPERTY: "true",
            READER_BOTH_PROPERTY: "true",
            READER_PROPERTY: self.reader_property_value(),
        }

    def to_dict(self) -> dict:
        return {
            "schema": SCHEMA,
            "optional_sheet_count": self.optional_sheet_count,
            "slot_value_counts": list(self.slot_value_counts),
            "produced_sizes": list(self.produced_sizes),
            "consumed_sizes": list(self.consumed_sizes),
            "mode": self.mode,
            "complete": self.complete,
            "expected_multiplier": self.expected_multiplier(),
            "combinations_by_size": {
                str(size): self.combinations_of_size(size) for size in self.produced_sizes},
            "required_tables": list(self.required_tables()),
            "core_property": {CORE_PROPERTY: self.core_property_value()},
            "reader_property": {READER_PROPERTY: self.reader_property_value()},
            "sources": dict(self.sources),
        }


# ------------------------------------------------------------- construction --
def _parse_sizes(raw, *, label: str) -> "tuple[int, ...]":
    """Parse a `1,2,3` size list with stable diagnostics for every malformation
    the audit calls out: duplicate, malformed, zero, negative."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return ()
    items = [p.strip() for p in str(raw).split(",")] if isinstance(raw, str) else list(raw)
    sizes: "list[int]" = []
    for item in items:
        if item == "" or item is None:
            raise OptionalContractError(f"{label}: empty entry in {raw!r}")
        try:
            value = int(item)
        except (TypeError, ValueError):
            raise OptionalContractError(f"{label}: {item!r} is not an integer (in {raw!r})")
        if value <= 0:
            raise OptionalContractError(
                f"{label}: optional combination size must be >= 1, got {value}")
        if value in sizes:
            raise OptionalContractError(f"{label}: duplicate size {value} in {raw!r}")
        sizes.append(value)
    return tuple(sorted(sizes))


def contract_from_spec(spec, *, consumed_override=None,
                       source: str = "run contract") -> OptionalTableContract:
    """Build the contract from the specification's `FW_Optional` slots.

    The complete run -- the normal case -- produces and consumes ``1..N``. An
    intentional Reader subset is available only by passing *consumed_override*,
    which records itself as an explicitly named mode. It can never arise from
    drifting property templates, because neither property is written by hand.
    """
    slots = [s for s in spec.slots if "FW_Optional" in (getattr(s, "flags", ()) or ())]
    counts = tuple(len(s.values) for s in slots)
    n = len(slots)
    produced = tuple(range(1, n + 1))
    sources = {"optional_sheet_count": f"{source}: FW_Optional slots in the specification",
               "produced_sizes": f"{source}: complete 1..{n}" if n else f"{source}: none"}

    if consumed_override is None:
        consumed, mode = produced, MODE_COMPLETE
        sources["consumed_sizes"] = f"{source}: complete 1..{n}" if n else f"{source}: none"
    else:
        consumed = _parse_sizes(consumed_override, label="consumed optional sizes")
        mode = MODE_COMPLETE if consumed == produced else MODE_EXPLICIT_SUBSET
        sources["consumed_sizes"] = "operator: explicit --optional-consumed-sizes"

    contract = OptionalTableContract(
        optional_sheet_count=n, slot_value_counts=counts, produced_sizes=produced,
        consumed_sizes=consumed, mode=mode, sources=sources)
    validate_contract(contract)
    return contract


def contract_for_sheet_count(n_opt: int, *, slot_value_counts: "Sequence[int]" = (),
                             source: str = "legacy n_opt") -> OptionalTableContract:
    """The complete contract for *n_opt* optional sheets: produce and consume
    ``1..n_opt``.

    Exists so the legacy `stage_core`/`stage_reader` call paths (benchmarks,
    direct callers) render the two properties from a contract object too, rather
    than re-deriving the CSV list independently — which is the drift the audit
    found in every standalone property template.
    """
    counts = tuple(slot_value_counts) or tuple([1] * max(0, n_opt))
    sizes = tuple(range(1, max(0, n_opt) + 1))
    contract = OptionalTableContract(
        optional_sheet_count=max(0, n_opt), slot_value_counts=counts,
        produced_sizes=sizes, consumed_sizes=sizes, mode=MODE_COMPLETE,
        sources={"produced_sizes": source, "consumed_sizes": source})
    validate_contract(contract)
    return contract


def validate_contract(contract: OptionalTableContract) -> None:
    """Enforce ``R ⊆ P`` and structural sanity. Raises `OptionalContractError`.

    Called during side-effect-free planning, so an unsatisfiable contract is
    rejected before Core and Reader do expensive work rather than after.
    """
    if contract.mode not in MODES:
        raise OptionalContractError(
            f"unknown optional consumption mode {contract.mode!r}; known: {list(MODES)}")
    n = contract.optional_sheet_count
    if n < 0:
        raise OptionalContractError(f"optional sheet count must be >= 0, got {n}")
    if len(contract.slot_value_counts) != n:
        raise OptionalContractError(
            f"optional slot value counts {list(contract.slot_value_counts)} do not match the "
            f"declared optional sheet count {n}")
    for size in contract.produced_sizes + contract.consumed_sizes:
        if size <= 0:
            raise OptionalContractError(f"optional combination size must be >= 1, got {size}")
        if size > n:
            raise OptionalContractError(
                f"optional combination size {size} exceeds the {n} declared FW_Optional sheet(s): "
                f"there is no such combination to build")
    if len(set(contract.produced_sizes)) != len(contract.produced_sizes):
        raise OptionalContractError(
            f"duplicate produced size in {list(contract.produced_sizes)}")
    if len(set(contract.consumed_sizes)) != len(contract.consumed_sizes):
        raise OptionalContractError(
            f"duplicate consumed size in {list(contract.consumed_sizes)}")
    missing = sorted(set(contract.consumed_sizes) - set(contract.produced_sizes))
    if missing:
        raise OptionalContractError(
            f"optional-table contract violated: the Reader would consume size(s) {missing} that "
            f"Core does not produce (produced={list(contract.produced_sizes)}, "
            f"consumed={list(contract.consumed_sizes)}). The consumed set must be a subset of the "
            f"produced set -- {READER_PROPERTY} ⊆ {CORE_PROPERTY}.")
    if contract.mode == MODE_COMPLETE and contract.consumed_sizes != contract.produced_sizes:
        raise OptionalContractError(
            f"contract claims mode {MODE_COMPLETE!r} but consumes "
            f"{list(contract.consumed_sizes)} of {list(contract.produced_sizes)}; an intentional "
            f"subset must declare mode {MODE_EXPLICIT_SUBSET!r}")
    if n == 0 and (contract.produced_sizes or contract.consumed_sizes):
        raise OptionalContractError(
            "no FW_Optional sheets are declared, so no optional table may be produced or consumed")


def verify_materialized(contract: OptionalTableContract,
                        existing_tables: "Sequence[str]") -> None:
    """After Core, before the Reader: every consumed `fw_opt<size>` must exist.

    A missing table would otherwise surface as an opaque Reader failure or, worse,
    a silently short candidate corpus.
    """
    if not contract.active:
        return
    present = {t.lower() for t in existing_tables}
    missing = [t for t in contract.required_tables() if t.lower() not in present]
    if missing:
        raise OptionalContractError(
            f"Core did not materialize {missing} required by the optional-table contract "
            f"(consumed sizes {list(contract.consumed_sizes)}). Refusing to start the Reader: it "
            f"would assemble an incomplete candidate corpus. Present optional tables: "
            f"{sorted(t for t in present if t.startswith('fw_opt'))}")


def contract_from_properties(core_value, reader_value, *,
                             optional_sheet_count: int,
                             slot_value_counts: "Sequence[int]" = (),
                             source: str = "property file") -> OptionalTableContract:
    """Build (and validate) a contract from two raw property values.

    Used to audit standalone/template property files against the same invariant
    the launcher enforces -- the check the templates never had.
    """
    produced = _parse_sizes(core_value, label=f"{source} {CORE_PROPERTY}")
    consumed = _parse_sizes(reader_value, label=f"{source} {READER_PROPERTY}")
    counts = tuple(slot_value_counts) or tuple([1] * optional_sheet_count)
    contract = OptionalTableContract(
        optional_sheet_count=optional_sheet_count, slot_value_counts=counts,
        produced_sizes=produced, consumed_sizes=consumed,
        mode=(MODE_COMPLETE if produced == consumed else MODE_EXPLICIT_SUBSET),
        sources={"produced_sizes": f"{source}: {CORE_PROPERTY}",
                 "consumed_sizes": f"{source}: {READER_PROPERTY}"})
    validate_contract(contract)
    return contract
