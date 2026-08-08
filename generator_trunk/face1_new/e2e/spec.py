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

"""Build inspectable HEAD/variation/TAIL specs and collision-free partitions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Sequence

from .actions import ALL_FLOW_NAMES, FLOW_NAMES


HEAD = '''import os
import sys

_FACE1_ROOT = os.environ.get("FACE1_E2E_ROOT", "")
if _FACE1_ROOT and _FACE1_ROOT not in sys.path:
    sys.path.insert(0, _FACE1_ROOT)

from face1_new.e2e.candidate import execute_candidate, metric_line

BROWSER = VIEWPORT = FLOW = DATA_PROFILE = None'''

TAIL = '''_FACE1_RESULT = execute_candidate(BROWSER, VIEWPORT, FLOW, DATA_PROFILE)
if not _FACE1_RESULT.ok:
    print("face1_e2e_failure:", _FACE1_RESULT.error, file=sys.stderr)
_FACE1_VERDICT_PREFIX = "F" + "W" + "_"
globals()[_FACE1_VERDICT_PREFIX + "VAR"] = 0 if _FACE1_RESULT.ok else 2
globals()[_FACE1_VERDICT_PREFIX + "CUSTOM_VAR"] = globals()[_FACE1_VERDICT_PREFIX + "VAR"]
print(metric_line(_FACE1_RESULT, BROWSER, VIEWPORT, DATA_PROFILE))'''


def _slot(sheet: str, values: Iterable[str]) -> str:
    encoded = ",\n".join(f"  {json.dumps(value)}" for value in values)
    return f'''[[slots]]
sheet = {json.dumps(sheet)}
raw = true
values = [
{encoded},
]
'''


def build_spec_text(
    *,
    flows: Sequence[str] = FLOW_NAMES,
    browsers: Sequence[str] = ("chromium",),
    viewports: Sequence[str] = ("desktop", "compact"),
    data_profiles: Sequence[str] = ("compact", "expanded"),
    title: str = "Face 1 new PageObject dogfooding",
) -> str:
    unknown = sorted(set(flows) - set(ALL_FLOW_NAMES))
    if unknown:
        raise ValueError(f"unknown Face 1 flow(s): {unknown}")
    dimensions = {
        "flows": flows,
        "browsers": browsers,
        "viewports": viewports,
        "data_profiles": data_profiles,
    }
    if any(not values for values in dimensions.values()):
        empty = [name for name, values in dimensions.items() if not values]
        raise ValueError(f"empty dogfood dimension(s): {empty}")
    parts = [
        f"title = {json.dumps(title)}",
        'note = "Generated PageObject action-flow candidates: HEAD + browser/viewport/flow/data + TAIL."',
        "",
        "[[goals]]\nkey = \"correct\"\ndir = \"max\"",
        "",
        "[[goals]]\nkey = \"checks\"\ndir = \"max\"",
        "",
        "[[goals]]\nkey = \"latency_ms\"\ndir = \"min\"",
        "",
        _slot("HEAD", (HEAD,)),
        _slot("BROWSER", (f'BROWSER = {browser!r}' for browser in browsers)),
        _slot("VIEWPORT", (f'VIEWPORT = {viewport!r}' for viewport in viewports)),
        _slot("FLOW", (f'FLOW = {flow!r}' for flow in flows)),
        _slot("DATA_PROFILE", (f'DATA_PROFILE = {profile!r}' for profile in data_profiles)),
        _slot("TAIL", (TAIL,)),
    ]
    return "\n".join(parts).rstrip() + "\n"


def write_spec(directory: Path, **dimensions: object) -> Path:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / "face1_dogfood.toml"
    destination.write_text(build_spec_text(**dimensions), encoding="utf-8")
    return destination


def cardinality(
    flows: Sequence[str], browsers: Sequence[str], viewports: Sequence[str], data_profiles: Sequence[str]
) -> int:
    return len(flows) * len(browsers) * len(viewports) * len(data_profiles)


def partition_flows(flows: Sequence[str], instances: int) -> tuple[tuple[str, ...], ...]:
    if instances < 1:
        raise ValueError("instances must be >= 1")
    if not flows:
        raise ValueError("cannot partition an empty flow list")
    count = min(instances, len(flows))
    buckets: list[list[str]] = [[] for _ in range(count)]
    for index, flow in enumerate(flows):
        buckets[index % count].append(flow)
    return tuple(tuple(bucket) for bucket in buckets)
