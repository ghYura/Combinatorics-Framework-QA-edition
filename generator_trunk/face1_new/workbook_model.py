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

"""Read a legacy Core workbook into a UI-friendly, plain-language model.

The legacy workbook is a program expressed through sheets:

* ``FW_Seq`` is the ordered instruction stream;
* ``FW_SheetNames`` supplies per-step framing text;
* ordinary sheets hold the source values (the first value is the baseline);
* the remaining ``FW_*`` sheets describe runtime arguments and verdicts.

This module intentionally has no NiceGUI dependency.  It is the tested seam which
future intake, linting, editing, and spec conversion work can build upon.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
from typing import Any, Iterable
from zipfile import BadZipFile, ZipFile

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter


CONTROL_SHEETS = (
    "FW_Seq",
    "FW_SheetNames",
    "FW_RunMeFirstOnce",
    "FW_Arguments",
    "FW_CUSTOM_VAR",
    "FW_Info",
)

ROLE_LABELS = {
    "control": "Control contract",
    "composed": "Composed result",
    "optional": "Optional axis",
    "intermediate": "Intermediate input",
    "sequence": "Sequence input",
    "helper": "Assembly helper",
    "reference": "Reference example",
    "dormant": "Unsequenced sheet",
    "empty": "Empty sheet",
}

OPERATION_LABELS = {
    "FW_Brace": "join earlier results",
    "FW_Combi": "choose values",
    "FW_CombiR": "choose with repetition",
    "FW_Permut": "order values",
    "FW_PermutR": "ordered sequence with repetition",
    "FW_Subsets": "build subsets",
    "FW_Subsets_after": "build bounded subsets",
    "FW_Cartes": "cross with another sheet",
    "FW_Cartes_first": "cross from a baseline",
    "FW_Group": "re-combine produced rows",
    "FW_Separator": "insert a separator",
    "FW_ReplaceRE": "rewrite the coded structure",
}

MAX_XLSX_BYTES = 12 * 1024 * 1024
MAX_EXPANDED_BYTES = 96 * 1024 * 1024
MAX_CELL_PREVIEW = 8_000


@dataclass(frozen=True)
class CellDatum:
    coordinate: str
    value: str


@dataclass(frozen=True)
class SheetProfile:
    index: int
    name: str
    role: str
    role_label: str
    used_range: str
    row_span: int
    column_span: int
    cell_count: int
    formula_count: int
    merged_count: int
    baseline: str
    values: tuple[CellDatum, ...]
    sequence_position: int | None = None
    prefix: str = ""
    suffix: str = ""

    @property
    def value_preview(self) -> str:
        values = [item.value for item in self.values[:3]]
        return " · ".join(values) if values else "No populated cells"


@dataclass(frozen=True)
class SequenceStep:
    position: int
    sheet_name: str
    role: str
    role_label: str
    source_value_count: int
    flags: tuple[str, ...]
    operations: tuple[str, ...]
    directives: tuple[str, ...]
    prefix: str
    suffix: str
    summary: str

    @property
    def operation_text(self) -> str:
        labels = [OPERATION_LABELS.get(op, op.removeprefix("FW_")) for op in self.operations]
        return ", ".join(dict.fromkeys(labels)) or "baseline value"


@dataclass(frozen=True)
class RuntimeContract:
    arguments: tuple[str, ...]
    custom_verdicts: tuple[tuple[str, str], ...]
    run_once_source: str
    info_row_count: int


@dataclass
class WorkbookAnalysis:
    source_name: str
    source_bytes: int
    fingerprint: str
    active_sheet: str
    sheet_count: int
    data_sheet_count: int
    sequence_steps: tuple[SequenceStep, ...]
    sheets: tuple[SheetProfile, ...]
    runtime: RuntimeContract
    role_counts: dict[str, int]
    operation_counts: dict[str, int]
    traits: tuple[str, ...]
    insights: tuple[str, ...]
    warnings: tuple[str, ...]
    detected_pattern: str
    _sheet_map: dict[str, SheetProfile] = field(default_factory=dict, repr=False)

    @property
    def sheet_by_name(self) -> dict[str, SheetProfile]:
        return self._sheet_map

    @property
    def metrics(self) -> dict[str, int]:
        return {
            "sequence_rows": len(self.sequence_steps),
            "source_cells": sum(s.cell_count for s in self.sheets if s.role != "control"),
            "optional_steps": sum("FW_Optional" in s.flags for s in self.sequence_steps),
            "intermediate_steps": sum("FW_Exclude" in s.flags for s in self.sequence_steps),
            "composed_steps": sum(s.role == "composed" for s in self.sequence_steps),
            "grouped_steps": sum("FW_Group" in s.operations for s in self.sequence_steps),
        }

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe analysis artifact (without the private lookup map)."""
        result = asdict(self)
        result.pop("_sheet_map", None)
        result["metrics"] = self.metrics
        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


class WorkbookInputError(ValueError):
    """Raised when an upload is not a safe, readable XLSX workbook."""


def _read_source(source: str | Path | bytes | bytearray, source_name: str | None) -> tuple[bytes, str]:
    if isinstance(source, (str, Path)):
        path = Path(source)
        data = path.read_bytes()
        name = source_name or path.name
    else:
        data = bytes(source)
        name = source_name or "uploaded-workbook.xlsx"
    if not data:
        raise WorkbookInputError("The workbook is empty.")
    if len(data) > MAX_XLSX_BYTES:
        raise WorkbookInputError(f"Workbook exceeds the {MAX_XLSX_BYTES // 1024 // 1024} MB mockup limit.")
    try:
        with ZipFile(BytesIO(data)) as archive:
            if sum(item.file_size for item in archive.infolist()) > MAX_EXPANDED_BYTES:
                raise WorkbookInputError("Expanded workbook is too large for local inspection.")
            if "xl/workbook.xml" not in archive.namelist():
                raise WorkbookInputError("The file is not an XLSX workbook.")
    except BadZipFile as exc:
        raise WorkbookInputError("The file is not a valid XLSX archive.") from exc
    return data, name


def _text(value: Any) -> str:
    if value is None:
        return ""
    rendered = str(value)
    return rendered if len(rendered) <= MAX_CELL_PREVIEW else rendered[:MAX_CELL_PREVIEW] + "…"


def _populated_cells(ws: Any) -> tuple[tuple[CellDatum, ...], str, int, int, int, int, int]:
    cells: list[CellDatum] = []
    min_row: int | None = None
    min_col: int | None = None
    max_row = 0
    max_col = 0
    formulas = 0
    for row in ws.iter_rows():
        for cell in row:
            if cell.value is None:
                continue
            cells.append(CellDatum(cell.coordinate, _text(cell.value)))
            min_row = cell.row if min_row is None else min(min_row, cell.row)
            min_col = cell.column if min_col is None else min(min_col, cell.column)
            max_row = max(max_row, cell.row)
            max_col = max(max_col, cell.column)
            formulas += int(cell.data_type == "f")
    if not cells:
        return (), "Empty", 0, 0, 0, 0, 0
    used_range = f"{get_column_letter(min_col)}{min_row}:{get_column_letter(max_col)}{max_row}"
    merged_count = len(getattr(ws, "merged_cells", ()).ranges) if hasattr(ws, "merged_cells") else 0
    return (
        tuple(cells),
        used_range,
        max_row - min_row + 1,
        max_col - min_col + 1,
        formulas,
        merged_count,
        len(cells),
    )


def _operation_names(cells: Iterable[str]) -> tuple[str, ...]:
    operations: list[str] = []
    for value in cells:
        for line in value.splitlines():
            stripped = line.strip()
            if stripped.startswith("FW_("):
                operations.append("FW_Brace")
                continue
            match = re.match(r"(FW_[A-Za-z_]+)", stripped)
            if match and match.group(1) not in {"FW_Optional", "FW_Exclude", "FW_Reuse", "FW_ReuseTableOnly"}:
                operations.append(match.group(1))
    return tuple(operations)


def _helper_references(cells: Iterable[str], available: set[str]) -> set[str]:
    references: set[str] = set()
    for value in cells:
        for name in re.findall(r"\+\s*([A-Za-z0-9_]+)\s*\+", value):
            if name in available:
                references.add(name)
        for pattern in (
            r"FW_Separator\(([^)]+)\)",
            r"FW_Cartes(?:_first)?\(([^)]+)\)",
        ):
            for name in re.findall(pattern, value):
                if name.strip() in available:
                    references.add(name.strip())
        if value.strip().startswith("FW_("):
            for name in (part.strip() for part in value.strip()[4:-1].split(",")):
                if name in available:
                    references.add(name)
    return references


def _step_role(flags: tuple[str, ...], operations: tuple[str, ...]) -> str:
    if "FW_Brace" in operations:
        return "composed"
    if "FW_Optional" in flags:
        return "optional"
    if "FW_Exclude" in flags:
        return "intermediate"
    return "sequence"


def _step_summary(role: str, operations: tuple[str, ...], value_count: int) -> str:
    if role == "composed":
        return "Joins result rows produced by earlier steps"
    if role == "optional":
        return f"May be absent or use one of {value_count} source value(s)"
    if role == "intermediate":
        return f"Produces an intermediate table from {value_count} value(s)"
    if "FW_Group" in operations:
        return f"Re-combines generated rows from {value_count} source value(s)"
    return f"Contributes {value_count} source value(s) to the ordered sequence"


def _runtime_contract(wb: Any) -> RuntimeContract:
    arguments: list[str] = []
    if "FW_Arguments" in wb.sheetnames:
        for row in wb["FW_Arguments"].iter_rows():
            for cell in row:
                if cell.value is None:
                    continue
                value = _text(cell.value)
                arguments.append("" if value.upper() == "FW_EMPTY_STRING" else value)

    verdicts: list[tuple[str, str]] = []
    if "FW_CUSTOM_VAR" in wb.sheetnames:
        for row in wb["FW_CUSTOM_VAR"].iter_rows(values_only=True):
            if row and row[0] is not None:
                code = _text(row[0])
                message = _text(row[1] if len(row) > 1 else "")
                verdicts.append((code, "" if message.upper() == "FW_EMPTY_STRING" else message))

    run_once = ""
    if "FW_RunMeFirstOnce" in wb.sheetnames:
        values = [cell.value for row in wb["FW_RunMeFirstOnce"].iter_rows() for cell in row if cell.value is not None]
        run_once = _text(values[0]) if values else ""

    info_rows = 0
    if "FW_Info" in wb.sheetnames:
        info_rows = sum(any(cell.value is not None for cell in row) for row in wb["FW_Info"].iter_rows())
    return RuntimeContract(tuple(arguments), tuple(verdicts), run_once, info_rows)


def _pattern_insights(steps: tuple[SequenceStep, ...]) -> tuple[str, tuple[str, ...]]:
    first = steps[:33]
    tail = steps[33:]
    brace_prelude = len(first) == 33 and sum(step.role == "composed" for step in first) == 11
    numeric_matrix = len(tail) == 144 and all(step.sheet_name == str(i) for i, step in enumerate(tail, 1))
    insights: list[str] = []
    if brace_prelude:
        insights.append("Steps 1–33 form eleven three-step join scenarios: two intermediate operands followed by one composed result.")
    if numeric_matrix:
        insights.append("Steps 34–177 are a 12 × 12 interaction corpus: 144 uniquely configured operator-composition cases.")
    if brace_prelude and numeric_matrix:
        return "Legacy Core compatibility / operator-composition corpus", tuple(insights)
    if steps:
        return "Legacy Core sequence workbook", tuple(insights)
    return "Generic workbook (no FW_Seq contract detected)", tuple(insights)


def analyze_workbook(
    source: str | Path | bytes | bytearray,
    *,
    source_name: str | None = None,
) -> WorkbookAnalysis:
    """Parse an XLSX file or byte string without changing it."""
    data, name = _read_source(source, source_name)
    try:
        wb = load_workbook(BytesIO(data), read_only=False, data_only=False, keep_links=False)
    except Exception as exc:  # openpyxl has several format-specific exception types
        raise WorkbookInputError(f"Could not read workbook: {exc}") from exc

    control_names = set(CONTROL_SHEETS) & set(wb.sheetnames)
    data_names = set(wb.sheetnames) - control_names

    sheet_names_rows: list[tuple[str, str, str]] = []
    if "FW_SheetNames" in wb.sheetnames:
        for row in wb["FW_SheetNames"].iter_rows(values_only=True):
            if row and row[0] is not None:
                sheet_names_rows.append((_text(row[0]), _text(row[1] if len(row) > 1 else ""), _text(row[2] if len(row) > 2 else "")))

    raw_steps: list[tuple[int, str, tuple[str, ...], tuple[str, ...], tuple[str, ...], str, str]] = []
    all_directive_cells: list[str] = []
    sequence_targets: set[str] = set()
    if "FW_Seq" in wb.sheetnames:
        for position, row in enumerate(wb["FW_Seq"].iter_rows(values_only=True), 1):
            values = tuple(_text(value) for value in row if value is not None)
            if not values:
                continue
            sheet_name = values[0]
            directives = values[1:]
            flags = tuple(value for value in directives if value in {"FW_Optional", "FW_Exclude", "FW_Reuse", "FW_ReuseTableOnly"})
            operations = _operation_names(directives)
            prefix = sheet_names_rows[position - 1][1] if position <= len(sheet_names_rows) else ""
            suffix = sheet_names_rows[position - 1][2] if position <= len(sheet_names_rows) else ""
            raw_steps.append((position, sheet_name, directives, flags, operations, prefix, suffix))
            all_directive_cells.extend(directives)
            sequence_targets.add(sheet_name)

    helper_refs = _helper_references(all_directive_cells, data_names - sequence_targets)
    info_targets: set[str] = set()
    info_cells: list[str] = []
    if "FW_Info" in wb.sheetnames:
        for row in wb["FW_Info"].iter_rows(values_only=True):
            values = [_text(value) for value in row if value is not None]
            if values:
                info_targets.add(values[0])
                info_cells.extend(values[1:])
    info_refs = _helper_references(info_cells, data_names - sequence_targets)

    position_by_sheet = {sheet_name: position for position, sheet_name, *_ in raw_steps}
    role_by_sheet: dict[str, str] = {name: "control" for name in control_names}
    raw_by_sheet = {sheet_name: (flags, operations) for _, sheet_name, _, flags, operations, _, _ in raw_steps}
    for sheet_name in sequence_targets:
        flags, operations = raw_by_sheet[sheet_name]
        role_by_sheet[sheet_name] = _step_role(flags, operations)
    for sheet_name in data_names - sequence_targets:
        if sheet_name in helper_refs:
            role_by_sheet[sheet_name] = "helper"
        elif sheet_name in info_targets or sheet_name in info_refs:
            role_by_sheet[sheet_name] = "reference"
        else:
            role_by_sheet[sheet_name] = "dormant"

    profiles: list[SheetProfile] = []
    for index, ws in enumerate(wb.worksheets):
        cells, used_range, row_span, column_span, formulas, merged, count = _populated_cells(ws)
        role = role_by_sheet.get(ws.title, "dormant")
        if role == "dormant" and not cells:
            role = "empty"
            role_by_sheet[ws.title] = role
        prefix = suffix = ""
        position = position_by_sheet.get(ws.title)
        if position and position <= len(sheet_names_rows):
            prefix, suffix = sheet_names_rows[position - 1][1:]
        profiles.append(SheetProfile(
            index=index,
            name=ws.title,
            role=role,
            role_label=ROLE_LABELS[role],
            used_range=used_range,
            row_span=row_span,
            column_span=column_span,
            cell_count=count,
            formula_count=formulas,
            merged_count=merged,
            baseline=cells[0].value if cells else "",
            values=cells,
            sequence_position=position,
            prefix=prefix,
            suffix=suffix,
        ))

    profile_map = {sheet.name: sheet for sheet in profiles}
    steps: list[SequenceStep] = []
    operation_counts: Counter[str] = Counter()
    for position, sheet_name, directives, flags, operations, prefix, suffix in raw_steps:
        role = role_by_sheet[sheet_name]
        source_value_count = profile_map[sheet_name].cell_count if sheet_name in profile_map else 0
        operation_counts.update(operations)
        steps.append(SequenceStep(
            position=position,
            sheet_name=sheet_name,
            role=role,
            role_label=ROLE_LABELS[role],
            source_value_count=source_value_count,
            flags=flags,
            operations=operations,
            directives=directives,
            prefix=prefix,
            suffix=suffix,
            summary=_step_summary(role, operations, source_value_count),
        ))

    runtime = _runtime_contract(wb)
    role_counts = dict(Counter(profile.role for profile in profiles))
    formula_total = sum(profile.formula_count for profile in profiles)
    merged_total = sum(profile.merged_count for profile in profiles)
    traits = (
        f"{len(steps)} ordered FW_Seq rows map one-to-one to {len(sequence_targets)} target sheets.",
        f"Every populated cell is literal data: {formula_total} formulas and {merged_total} merged regions.",
        "The first populated value of each source sheet is the baseline inherited by compact Core rows.",
        f"Runtime contract: {len(runtime.arguments)} arguments, {len(runtime.custom_verdicts)} custom verdict codes, and one run-once source block.",
    )
    pattern, pattern_notes = _pattern_insights(tuple(steps))
    insights = list(pattern_notes)
    if operation_counts["FW_Group"]:
        insights.append(f"{sum('FW_Group' in step.operations for step in steps)} steps re-combine prior rows; their cardinality is not safely inferred from raw value counts.")
    optional_count = sum("FW_Optional" in step.flags for step in steps)
    if optional_count:
        insights.append(f"{optional_count} sequence steps are optional and are assembled later by the Reader.")

    warnings: list[str] = []
    empty_sheets = [sheet.name for sheet in profiles if sheet.role == "empty"]
    if empty_sheets:
        warnings.append(f"{len(empty_sheets)} sheet(s) are empty: {', '.join(empty_sheets[:3])}.")
    dormant = [sheet.name for sheet in profiles if sheet.role == "dormant"]
    if dormant:
        warnings.append(f"{len(dormant)} populated sheet(s) are neither sequenced nor referenced by detected helper syntax.")
    if sheet_names_rows and all(prefix in {"", "FW_EMPTY_STRING"} and suffix in {"", "FW_EMPTY_STRING"} for _, prefix, suffix in sheet_names_rows):
        warnings.append("FW_SheetNames defines no visible prefix/suffix framing in this example; every row uses the empty-string sentinel.")

    active_sheet = wb.active.title if wb.active else wb.sheetnames[0]
    analysis = WorkbookAnalysis(
        source_name=name,
        source_bytes=len(data),
        fingerprint=sha256(data).hexdigest()[:12],
        active_sheet=active_sheet,
        sheet_count=len(wb.sheetnames),
        data_sheet_count=len(data_names),
        sequence_steps=tuple(steps),
        sheets=tuple(profiles),
        runtime=runtime,
        role_counts=role_counts,
        operation_counts=dict(operation_counts),
        traits=traits,
        insights=tuple(insights),
        warnings=tuple(warnings),
        detected_pattern=pattern,
    )
    analysis._sheet_map = profile_map
    wb.close()
    return analysis
