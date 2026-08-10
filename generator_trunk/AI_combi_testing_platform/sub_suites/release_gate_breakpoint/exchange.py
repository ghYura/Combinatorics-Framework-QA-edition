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

"""Fourth-order Bundle prompt construction and bounded offline exchange design."""

from __future__ import annotations

import base64
from collections import defaultdict
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any, Iterable, Mapping
import zlib

from . import runtime
from .config import ReleaseGateSuiteConfig, TargetCell
from .runtime import (
    RG_FACTOR_NAMES,
    RG_OPTIONS,
    rg_candidate_id,
    rg_factor_signature,
    rg_validate_task,
)


RELEASE_EXCHANGE_SCHEMA = "ai-combi-release-gate-exchange/v2"
RELEASE_PLACEHOLDER = "[[PASTE EXACT AI RESPONSE HERE]]"
RELEASE_CANDIDATES_PER_TASK = 2 ** len(RG_FACTOR_NAMES)
ZERO_SIGNATURE = "0" * len(RG_FACTOR_NAMES)
FULL_SIGNATURE = "1" * len(RG_FACTOR_NAMES)

# Ten rows, nine binary prompt-construction factors.  Row weights are exactly
# 0..9, every column is balanced 5/5, and every factor pair realizes 00, 01,
# 10, and 11.  Thus contrast states rise exactly as 2**weight while a bounded
# follow-up still has strength-two interaction coverage.
PAIRWISE_COVERING_SIGNATURES = (
    "000000000",
    "000100000",
    "000010001",
    "100001010",
    "011000101",
    "001011110",
    "110111100",
    "111110011",
    "111101111",
    "111111111",
)



@dataclass(frozen=True)
class ReleaseExchangeRequest:
    global_sequence: int
    cell_sequence: int
    request_id: str
    provider: str
    target_model: str
    effort: str
    level: int
    difficulty_units: int
    variant: str
    factor_signature: str
    candidate_id: str
    task_id: str
    prompt: str


def standalone_release_runtime_source() -> str:
    source = Path(runtime.__file__).read_text(encoding="utf-8")
    if "from ." in source or "import generator_trunk" in source:
        raise RuntimeError("standalone release runtime acquired a repository import")
    if "'''" in source:
        raise RuntimeError("standalone release runtime cannot enter TOML raw strings")
    return source.rstrip() + "\n"


def _raw_toml(source: str) -> str:
    if "'''" in source:
        raise ValueError("generated release source contains a raw-string terminator")
    return "'''\n" + source.rstrip() + "\n'''"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _validated_task_rows(tasks: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = list(tasks)
    if not rows:
        raise ValueError("the breakpoint ladder requires at least one task")
    if len(rows) > 6:
        raise ValueError("the breakpoint ladder supports at most six tasks")
    for level, task in enumerate(rows):
        rg_validate_task(task)
        if task["level"] != level:
            raise ValueError("task levels must be zero-based, contiguous, and ordered")
    return rows


def build_release_head_cells(
    tasks: Iterable[dict[str, Any]],
) -> tuple[str, str]:
    rows = _validated_task_rows(tasks)
    compressed = zlib.compress(_canonical_json(rows).encode("utf-8"), level=9)
    encoded = base64.b85encode(compressed).decode("ascii")
    # Keep the standalone oracle and compressed held-out data in separate cells;
    # every workbook cell stays below Excel's 32,767-character hard limit.
    chunks = (
        "\n".join(
            f"    {encoded[index:index + 512]!r},"
            for index in range(0, len(encoded), 512)
        )
    )
    runtime_head = (
        standalone_release_runtime_source()
        + "\nimport base64\n"
        + "import os\n"
        + "import zlib\n"
        + "RG_LEVEL = -1\n"
        + "RG_PLAN = {\n"
        + '    "section_order": [], "numeric_surface": "",\n'
        + '    "context_depth": "", "schema": "", "trust_wording": "",\n'
        + '    "options": [],\n'
        + "}\n"
        + "RG_CONSTRUCTION_TRACE = []\n"
    )
    task_data = (
        "RG_TASK_B64_PARTS = (\n"
        + chunks
        + "\n)\n"
        + 'RG_TASKS = json.loads(zlib.decompress(base64.b85decode("".join(RG_TASK_B64_PARTS))).decode("utf-8"))\n'
        + "del RG_TASK_B64_PARTS\n"
    )
    for name, source in (("HEAD", runtime_head), ("TASK_DATA", task_data)):
        if len(source) > 32_000 or max(map(len, source.splitlines())) > 1024:
            raise ValueError(f"release {name} exceeds its safe spreadsheet-cell budget")
    return runtime_head, task_data


def build_release_head_source(tasks: Iterable[dict[str, Any]]) -> str:
    runtime_head, task_data = build_release_head_cells(tasks)
    return runtime_head + task_data


def build_release_tail_source() -> str:
    return """\
RG_TASK = RG_TASKS[RG_LEVEL]
rg_validate_construction_trace(RG_CONSTRUCTION_TRACE)
RG_PROMPT = rg_render(RG_TASK, RG_PLAN)
RG_CANDIDATE_ID = rg_candidate_id(RG_TASK, RG_PLAN)
if os.environ.get("AI_COMBI_EXPORT_PROMPT") == "1":
    print(json.dumps(
        {
            "candidate_id": RG_CANDIDATE_ID,
            "task_id": rg_task_id(RG_TASK),
            "level": RG_LEVEL,
            "difficulty_units": RG_TASK["difficulty_units"],
            "factor_signature": rg_factor_signature(RG_PLAN),
            "plan": RG_PLAN,
            "prompt": RG_PROMPT,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ))
else:
    RG_RESPONSE = rg_format_reference(RG_TASK, RG_PLAN)
    RG_IDENTITY = {
        "provider": "oracle-control",
        "model": "not-a-model",
        "environment": "generated-default",
    }
    RG_VERDICT = rg_verify(RG_TASK, RG_PLAN, RG_RESPONSE)
    FW_VAR = int(RG_VERDICT["code"])
    FW_CUSTOM_VAR = FW_VAR
    print(rg_metrics_line(
        RG_TASK,
        RG_PLAN,
        RG_RESPONSE,
        RG_IDENTITY,
        is_control=True,
    ))
"""


def _goals() -> str:
    return """\
[[goals]]
key = "correct"
dir = "max"
[[goals]]
key = "format_ok"
dir = "max"
[[goals]]
key = "semantic_correct"
dir = "max"
[[goals]]
key = "difficulty_units"
dir = "max"
[[goals]]
key = "construction_states"
dir = "max"
[[goals]]
key = "input_tokens"
dir = "min"
[[goals]]
key = "cost_microusd"
dir = "min"
"""


def build_release_gate_spec_text(tasks: Iterable[dict[str, Any]]) -> str:
    """Build N x 2^9 candidates through four real result-table brace levels."""
    rows = _validated_task_rows(tasks)
    head, task_data = build_release_head_cells(rows)
    tail = build_release_tail_source()
    difficulty_text = "/".join(str(task["difficulty_units"]) for task in rows)
    candidate_count = len(rows) * RELEASE_CANDIDATES_PER_TASK
    levels = ",\n".join(
        _raw_toml(f"RG_LEVEL = {level}\n") for level in range(len(rows))
    )
    return f"""\
spec_version = "1"
title = "Exponential ordinary-task breakpoint via fourth-order prompt construction"
note = "Target AIs audit ordinary release policies with {difficulty_text} leaves. Bundle uses FW_Permut, FW_Group, four nested result-table braces, and four independent FW_Optional atoms to construct {candidate_count:,} exact apparatus candidates; no target prompt asks a combinatorics question."
args = ["suite=ai_combi_testing", "study=release-gate-breakpoint", "evidence=apparatus-only", "prompt-order=4"]

seq_extra = [
  ["L1_RESULT", "FW_Reuse", "FW_(L1_OPEN,,SECTION_ORDER,,NUMERIC_SURFACE,,L1_CLOSE,,M:N)"],
  ["L2_RESULT", "FW_Reuse", "FW_(L2_OPEN,,FW_(),,CONTEXT_DEPTH,,L2_CLOSE,,M:N)"],
  ["L3_RESULT", "FW_Reuse", "FW_(L3_OPEN,,FW_(),,OUTPUT_SCHEMA,,L3_CLOSE,,M:N)"],
  ["ROOT_RESULT", "FW_Reuse", "FW_(L4_OPEN,,FW_(),,TRUST_WORDING,,L4_CLOSE,,M:N)"],
]

{_goals()}
[[slots]]
sheet = "HEAD"
key = "head"
verb = "FW_Combi(1)"
raw = true
values = [{_raw_toml(head)}]

[[slots]]
sheet = "TASK_DATA"
key = "task_data"
verb = "FW_Combi(1)"
raw = true
values = [{_raw_toml(task_data)}]

[[slots]]
sheet = "TASK_LEVEL"
key = "task_level"
verb = "FW_Combi(1)"
raw = true
values = [
{levels}
]

[[slots]]
sheet = "SECTION_ORDER"
key = "section_order"
verb = "FW_Permut(2)"
flags = ["FW_Exclude"]
raw = true
values = [
'''RG_PLAN["section_order"].append("policy")
''',
'''RG_PLAN["section_order"].append("evidence")
'''
]

[[slots]]
sheet = "NUMERIC_SURFACE"
key = "numeric_surface"
verb = "FW_Combi(1)"
flags = ["FW_Exclude"]
group_replace = [["47", "47"]]
raw = true
values = [
'''RG_PLAN["numeric_surface"] = "native"
''',
'''RG_PLAN["numeric_surface"] = "converted"
'''
]

[[slots]]
sheet = "CONTEXT_DEPTH"
key = "context_depth"
verb = "FW_Combi(1)"
flags = ["FW_Exclude"]
raw = true
values = [
'''RG_PLAN["context_depth"] = "clean"
''',
'''RG_PLAN["context_depth"] = "long"
'''
]

[[slots]]
sheet = "OUTPUT_SCHEMA"
key = "output_schema"
verb = "FW_Combi(1)"
flags = ["FW_Exclude"]
raw = true
values = [
'''RG_PLAN["schema"] = "json"
''',
'''RG_PLAN["schema"] = "plain"
'''
]

[[slots]]
sheet = "TRUST_WORDING"
key = "trust_wording"
verb = "FW_Combi(1)"
flags = ["FW_Exclude"]
raw = true
values = [
'''RG_PLAN["trust_wording"] = "direct"
''',
'''RG_PLAN["trust_wording"] = "nested"
'''
]

[[slots]]
sheet = "L1_RESULT"
key = "l1_result"
verb = "FW_Combi(1)"
flags = ["FW_Exclude"]
raw = true
values = ["pass\\n"]

[[slots]]
sheet = "L2_RESULT"
key = "l2_result"
verb = "FW_Combi(1)"
flags = ["FW_Exclude"]
raw = true
values = ["pass\\n"]

[[slots]]
sheet = "L3_RESULT"
key = "l3_result"
verb = "FW_Combi(1)"
flags = ["FW_Exclude"]
raw = true
values = ["pass\\n"]

[[slots]]
sheet = "ROOT_RESULT"
key = "root_result"
verb = "FW_Combi(1)"
raw = true
values = ["pass\\n"]

[[slots]]
sheet = "L1_OPEN"
key = "l1_open"
verb = "FW_Combi(1)"
raw = true
values = ['''rg_emit_open(RG_CONSTRUCTION_TRACE, 1, "section_numeric")
''']
[[slots]]
sheet = "L1_CLOSE"
key = "l1_close"
verb = "FW_Combi(1)"
raw = true
values = ['''rg_emit_close(RG_CONSTRUCTION_TRACE, 1, "section_numeric")
''']

[[slots]]
sheet = "L2_OPEN"
key = "l2_open"
verb = "FW_Combi(1)"
raw = true
values = ['''rg_emit_open(RG_CONSTRUCTION_TRACE, 2, "context")
''']
[[slots]]
sheet = "L2_CLOSE"
key = "l2_close"
verb = "FW_Combi(1)"
raw = true
values = ['''rg_emit_close(RG_CONSTRUCTION_TRACE, 2, "context")
''']

[[slots]]
sheet = "L3_OPEN"
key = "l3_open"
verb = "FW_Combi(1)"
raw = true
values = ['''rg_emit_open(RG_CONSTRUCTION_TRACE, 3, "schema")
''']
[[slots]]
sheet = "L3_CLOSE"
key = "l3_close"
verb = "FW_Combi(1)"
raw = true
values = ['''rg_emit_close(RG_CONSTRUCTION_TRACE, 3, "schema")
''']

[[slots]]
sheet = "L4_OPEN"
key = "l4_open"
verb = "FW_Combi(1)"
raw = true
values = ['''rg_emit_open(RG_CONSTRUCTION_TRACE, 4, "trust")
''']
[[slots]]
sheet = "L4_CLOSE"
key = "l4_close"
verb = "FW_Combi(1)"
raw = true
values = ['''rg_emit_close(RG_CONSTRUCTION_TRACE, 4, "trust")
''']

[[slots]]
sheet = "OPT_ALT_RULE_LABELS"
key = "fw_opt_alt_rule_labels"
verb = "FW_Combi(1)"
flags = ["FW_Optional"]
raw = true
values = ['''RG_PLAN["options"].append("alt_rule_labels")
''']

[[slots]]
sheet = "OPT_ALT_DECISION_WORDS"
key = "fw_opt_alt_decision_words"
verb = "FW_Combi(1)"
flags = ["FW_Optional"]
raw = true
values = ['''RG_PLAN["options"].append("alt_decision_words")
''']

[[slots]]
sheet = "OPT_DIST_ARCHIVE"
key = "fw_opt_dist_archive"
verb = "FW_Combi(1)"
flags = ["FW_Optional"]
raw = true
values = ['''RG_PLAN["options"].append("dist_archive")
''']

[[slots]]
sheet = "OPT_DIST_OVERRIDE"
key = "fw_opt_dist_override"
verb = "FW_Combi(1)"
flags = ["FW_Optional"]
raw = true
values = ['''RG_PLAN["options"].append("dist_override")
''']

[[slots]]
sheet = "TAIL"
key = "tail"
verb = "FW_Combi(1)"
raw = true
values = [{_raw_toml(tail)}]

[[custom_vars]]
code = 4
msg = "strict response-format or declared ordering failure"
[[custom_vars]]
code = 5
msg = "semantic release-audit failure"
[[custom_vars]]
code = 6
msg = "explicit model refusal"
"""


def materialize_release_gate_spec(
    destination: Path, tasks: Iterable[dict[str, Any]]
) -> Path:
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "scenario.toml").write_text(
        build_release_gate_spec_text(tasks), encoding="utf-8"
    )
    return destination


_LEVEL_ASSIGNMENT = re.compile(r"^RG_LEVEL = ([0-9]+)$", re.MULTILINE)
_ORDER_APPEND = re.compile(
    r'^RG_PLAN\["section_order"\]\.append\("(policy|evidence)"\)$', re.MULTILINE
)
_AXIS_ASSIGNMENTS = {
    "numeric_surface": re.compile(
        r'^RG_PLAN\["numeric_surface"\] = "(native|converted)"$', re.MULTILINE
    ),
    "context_depth": re.compile(
        r'^RG_PLAN\["context_depth"\] = "(clean|long)"$', re.MULTILINE
    ),
    "schema": re.compile(r'^RG_PLAN\["schema"\] = "(json|plain)"$', re.MULTILINE),
    "trust_wording": re.compile(
        r'^RG_PLAN\["trust_wording"\] = "(direct|nested)"$', re.MULTILINE
    ),
}
_OPTION_APPEND = re.compile(
    r'^RG_PLAN\["options"\]\.append\("([a-z_]+)"\)$', re.MULTILINE
)


def candidate_coordinates(source: str) -> tuple[int, dict[str, Any], str]:
    levels = _LEVEL_ASSIGNMENT.findall(source)
    order = _ORDER_APPEND.findall(source)
    if len(levels) != 1 or len(order) != 2 or set(order) != {"policy", "evidence"}:
        raise RuntimeError("Reader candidate lost its task level or section permutation")
    plan: dict[str, Any] = {"section_order": order, "options": []}
    for key, pattern in _AXIS_ASSIGNMENTS.items():
        values = pattern.findall(source)
        if len(values) != 1:
            raise RuntimeError(f"Reader candidate lost one {key} assignment")
        plan[key] = values[0]
    options = _OPTION_APPEND.findall(source)
    if len(options) != len(set(options)) or any(option not in RG_OPTIONS for option in options):
        raise RuntimeError("Reader candidate optional atom set is invalid")
    plan["options"] = options
    return int(levels[0]), plan, rg_factor_signature(plan)


def index_reader_candidates(
    candidates: Iterable[Path], tasks: Iterable[dict[str, Any]]
) -> dict[tuple[int, str], Path]:
    task_rows = _validated_task_rows(tasks)
    indexed: dict[tuple[int, str], Path] = {}
    for candidate in candidates:
        source = candidate.read_text(encoding="utf-8")
        level, plan, signature = candidate_coordinates(source)
        key = level, signature
        if key in indexed:
            raise RuntimeError("Reader produced a duplicate release-gate coordinate")
        if level >= len(task_rows):
            raise RuntimeError("Reader candidate references an unknown task level")
        rg_candidate_id(task_rows[level], plan)
        indexed[key] = candidate
    expected = {
        (level, f"{bits:0{len(RG_FACTOR_NAMES)}b}")
        for level in range(len(task_rows))
        for bits in range(RELEASE_CANDIDATES_PER_TASK)
    }
    if set(indexed) != expected:
        raise RuntimeError(
            f"Reader coordinate matrix is incomplete: {len(indexed)} of {len(expected)}"
        )
    return indexed


def extract_release_prompt(candidate: Path) -> dict[str, Any]:
    env = os.environ.copy()
    env["AI_COMBI_EXPORT_PROMPT"] = "1"
    completed = subprocess.run(
        [sys.executable, str(candidate)],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if completed.returncode or completed.stderr.strip():
        raise RuntimeError(f"assembled candidate prompt export failed: {candidate.name}")
    try:
        document = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("assembled candidate did not emit one prompt document") from exc
    if (
        not isinstance(document, dict)
        or not isinstance(document.get("prompt"), str)
        or len(document["prompt"].encode("utf-8")) > 32768
    ):
        raise RuntimeError("assembled candidate emitted an invalid prompt document")
    return document


def _request_id(candidate_id: str, cell: TargetCell) -> str:
    payload = _canonical_json(
        {"candidate_id": candidate_id, **cell.as_dict()}
    ).encode("utf-8")
    return "rgx-" + hashlib.sha256(payload).hexdigest()[:20]


def build_breakpoint_requests(
    selected_documents: Mapping[tuple[int, str], Mapping[str, Any]],
    config: ReleaseGateSuiteConfig,
) -> tuple[ReleaseExchangeRequest, ...]:
    candidates = [
        (level, variant.name, variant.factor_signature)
        for level in range(config.task_count)
        for variant in config.breakpoint_variants
    ]
    requests: list[ReleaseExchangeRequest] = []
    global_sequence = 0
    for cell in config.target_cells:
        for cell_sequence, (level, variant, signature) in enumerate(candidates, start=1):
            global_sequence += 1
            document = selected_documents[level, signature]
            difficulty_units = int(document["difficulty_units"])
            if difficulty_units != config.difficulty_units[level]:
                raise RuntimeError("executed prompt has the wrong difficulty size")
            candidate_id = str(document["candidate_id"])
            requests.append(
                ReleaseExchangeRequest(
                    global_sequence=global_sequence,
                    cell_sequence=cell_sequence,
                    request_id=_request_id(candidate_id, cell),
                    provider=cell.provider,
                    target_model=cell.model,
                    effort=cell.effort,
                    level=level,
                    difficulty_units=difficulty_units,
                    variant=variant,
                    factor_signature=signature,
                    candidate_id=candidate_id,
                    task_id=str(document["task_id"]),
                    prompt=str(document["prompt"]),
                )
            )
    return tuple(requests)


def _file_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.+-]+", "-", value).strip("-.")
    return slug[:48] or "unnamed"


def release_cell_filename(cell: TargetCell, count: int, kind: str) -> str:
    stem = "__".join(_file_slug(value) for value in (cell.provider, cell.model, cell.effort))
    digest = hashlib.sha256(
        _canonical_json(cell.as_dict()).encode("utf-8")
    ).hexdigest()[:12]
    return f"{stem}__{digest}__{count}-{kind}.txt"


def _input_list(
    rows: Iterable[ReleaseExchangeRequest], session_instruction: str
) -> str:
    requests = list(rows)
    header = (
        f"TARGET_PROVIDER={requests[0].provider}\n"
        f"TARGET_MODEL={requests[0].target_model}\n"
        f"EFFORT_LEVEL={requests[0].effort}\n"
        f"PROMPT_COUNT={len(requests)}\n"
        f"{session_instruction}\n\n"
    )
    blocks = []
    for row in requests:
        begin = (
            "----- BEGIN RELEASE_GATE_INPUT "
            f"cell_sequence={row.cell_sequence} global_sequence={row.global_sequence} "
            f"request_id={row.request_id} level={row.level} variant={row.variant} -----"
        )
        end = (
            "----- END RELEASE_GATE_INPUT "
            f"cell_sequence={row.cell_sequence} global_sequence={row.global_sequence} "
            f"request_id={row.request_id} -----"
        )
        blocks.append(begin + "\n" + row.prompt + "\n" + end)
    return header + "\n\n".join(blocks) + "\n"


def _response_list(rows: Iterable[ReleaseExchangeRequest]) -> str:
    requests = list(rows)
    header = (
        f"TARGET_PROVIDER={requests[0].provider}\n"
        f"TARGET_MODEL_LABEL={requests[0].target_model}\n"
        f"EFFORT_LEVEL={requests[0].effort}\n"
        f"RESPONSE_COUNT={len(requests)}\n"
        "Replace each placeholder only; preserve every marker line.\n\n"
    )
    blocks = []
    for row in requests:
        begin = (
            "----- BEGIN RELEASE_GATE_RESPONSE "
            f"cell_sequence={row.cell_sequence} global_sequence={row.global_sequence} "
            f"request_id={row.request_id} -----"
        )
        end = (
            "----- END RELEASE_GATE_RESPONSE "
            f"cell_sequence={row.cell_sequence} global_sequence={row.global_sequence} "
            f"request_id={row.request_id} -----"
        )
        blocks.append(begin + "\n" + RELEASE_PLACEHOLDER + "\n" + end)
    return header + "\n\n".join(blocks) + "\n"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_release_exchange_package(
    destination: Path,
    *,
    tasks: Iterable[dict[str, Any]],
    config: ReleaseGateSuiteConfig,
    seed_commitment: str,
    spec: Path,
    reader_candidates: Iterable[Path],
    bundle_evidence: Mapping[str, Any],
) -> Path:
    destination.mkdir(parents=True, exist_ok=False)
    task_rows = _validated_task_rows(tasks)
    actual_units = tuple(int(task["difficulty_units"]) for task in task_rows)
    if actual_units != config.difficulty_units:
        raise ValueError("generated task ladder does not match suite configuration")
    indexed = index_reader_candidates(reader_candidates, task_rows)
    breakpoint_signatures = tuple(
        variant.factor_signature for variant in config.breakpoint_variants
    )
    selected_keys = {
        (level, signature)
        for level in range(config.task_count)
        for signature in (*breakpoint_signatures, *PAIRWISE_COVERING_SIGNATURES)
    }
    documents: dict[tuple[int, str], dict[str, Any]] = {}
    selected_sources: dict[tuple[int, str], Path] = {}
    for key in sorted(selected_keys):
        document = extract_release_prompt(indexed[key])
        if (int(document["level"]), str(document["factor_signature"])) != key:
            raise RuntimeError("executed prompt coordinate differs from Reader source")
        documents[key] = document
        selected_sources[key] = indexed[key]

    requests = build_breakpoint_requests(documents, config)
    inputs = destination / "inputs"
    responses = destination / "responses"
    bodies = destination / "bodies"
    assembled = bodies / "selected_assembled"
    plans = destination / "plans"
    tasks_dir = destination / "tasks"
    bundle_spec = destination / "bundle_spec"
    for directory in (inputs, responses, assembled, plans, tasks_dir, bundle_spec):
        directory.mkdir(parents=True)

    head_runtime, task_data = build_release_head_cells(task_rows)
    (bodies / "HEAD.py").write_text(
        head_runtime + task_data, encoding="utf-8"
    )
    (bodies / "HEAD_RUNTIME.py").write_text(head_runtime, encoding="utf-8")
    (bodies / "TASK_DATA.py").write_text(task_data, encoding="utf-8")
    (bodies / "TAIL.py").write_text(build_release_tail_source(), encoding="utf-8")
    shutil.copy2(spec / "scenario.toml", bundle_spec / "scenario.toml")
    shutil.copy2(
        Path(runtime.__file__),
        destination / "oracle_runtime.py",
    )
    for level, task in enumerate(task_rows):
        (tasks_dir / f"level_{level}.json").write_text(
            json.dumps(task, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    candidate_paths: dict[tuple[int, str], str] = {}
    plan_paths: dict[tuple[int, str], str] = {}
    for key, source in selected_sources.items():
        level, signature = key
        stem = f"level_{level}__factors_{signature}"
        output = assembled / f"{stem}.py"
        shutil.copy2(source, output)
        plan_path = plans / f"{stem}.json"
        plan_path.write_text(
            json.dumps(documents[key]["plan"], indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        candidate_paths[key] = output.relative_to(destination).as_posix()
        plan_paths[key] = plan_path.relative_to(destination).as_posix()

    grouped: dict[tuple[str, str, str], list[ReleaseExchangeRequest]] = defaultdict(list)
    for request in requests:
        grouped[request.provider, request.target_model, request.effort].append(request)
    input_paths: dict[tuple[str, str, str], str] = {}
    response_paths: dict[tuple[str, str, str], str] = {}
    for key, rows in grouped.items():
        cell = TargetCell(*key)
        input_path = inputs / release_cell_filename(cell, len(rows), "prompts")
        response_path = responses / release_cell_filename(cell, len(rows), "responses")
        input_path.write_text(_input_list(rows, config.session_instruction), encoding="utf-8")
        response_path.write_text(_response_list(rows), encoding="utf-8")
        input_paths[key] = input_path.relative_to(destination).as_posix()
        response_paths[key] = response_path.relative_to(destination).as_posix()

    bootstrap = Path(__file__).with_name("bootstrap.py")
    shutil.copy2(bootstrap, destination / "RunMeFirstOnce.py")
    design = {
        "factor_names": list(RG_FACTOR_NAMES),
        "full_constructor_candidates_per_level": RELEASE_CANDIDATES_PER_TASK,
        "task_difficulty_units": list(config.difficulty_units),
        "breakpoint_variants": [
            variant.as_dict() for variant in config.breakpoint_variants
        ],
        "breakpoint_signatures": list(breakpoint_signatures),
        "followup_pairwise_signatures": list(PAIRWISE_COVERING_SIGNATURES),
        "followup_row_weights": [row.count("1") for row in PAIRWISE_COVERING_SIGNATURES],
        "followup_construction_states": [2 ** row.count("1") for row in PAIRWISE_COVERING_SIGNATURES],
        "suite_config": config.as_dict(),
    }
    (destination / "DESIGN.json").write_text(
        json.dumps(design, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (destination / "README.txt").write_text(
        f"""\
EXPONENTIAL RELEASE-GATE AI ROBUSTNESS EXCHANGE

The target AI performs an ordinary software release audit, not a combinatorics task.
Bundle used fourth-order result-table composition to construct the prompts.

Phase 1 uses {config.prompts_per_cell} prompts per target cell across task sizes
{", ".join(str(value) for value in config.difficulty_units)} and the configured
breakpoint variants. Follow the session instruction in each input file, paste exact
responses into the matching response file, and run:

    python3 RunMeFirstOnce.py --require-complete

The bootstrap validates immutable files and produces strict plus extracted-semantic
scores. Strict failure is never upgraded by extraction. The 10-row strength-two
covering design in DESIGN.json is reserved for a focused follow-up at the observed
breakpoint; it spans contrast weights 0..9 without spending those calls up front.

No API key, cookie, browser profile, raw holdout seed, database, reference-answer
file, or Bundle runtime directory is included.
""",
        encoding="utf-8",
    )

    records: list[dict[str, Any]] = []
    for request in requests:
        key = request.level, request.factor_signature
        records.append(
            {
                "global_sequence": request.global_sequence,
                "cell_sequence": request.cell_sequence,
                "request_id": request.request_id,
                "provider": request.provider,
                "target_model": request.target_model,
                "effort": request.effort,
                "level": request.level,
                "difficulty_units": request.difficulty_units,
                "variant": request.variant,
                "factor_signature": request.factor_signature,
                "candidate_id": request.candidate_id,
                "task_id": request.task_id,
                "prompt_sha256": hashlib.sha256(request.prompt.encode("utf-8")).hexdigest(),
                "input_file": input_paths[request.provider, request.target_model, request.effort],
                "response_file": response_paths[request.provider, request.target_model, request.effort],
                "task_file": f"tasks/level_{request.level}.json",
                "plan_file": plan_paths[key],
                "assembled_candidate": candidate_paths[key],
            }
        )
    immutable_files = [
        path
        for path in destination.rglob("*")
        if path.is_file()
        and path.name != "manifest.json"
        and "responses" not in path.relative_to(destination).parts
    ]
    manifest = {
        "schema": RELEASE_EXCHANGE_SCHEMA,
        "seed_commitment": seed_commitment,
        "request_count": len(records),
        "cell_count": len(grouped),
        "full_constructor_candidate_count": config.constructor_candidate_count,
        "suite_config": config.as_dict(),
        "breakpoint_variants": [variant.as_dict() for variant in config.breakpoint_variants],
        "bundle_evidence": dict(bundle_evidence),
        "raw_seed_retained": False,
        "reference_answers_included": False,
        "records": records,
        "immutable_sha256": {
            path.relative_to(destination).as_posix(): _sha256(path)
            for path in sorted(immutable_files)
        },
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return destination
