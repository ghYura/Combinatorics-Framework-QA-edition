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

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from AI_combi_testing_platform.sub_suites.release_gate_breakpoint.config import (
    TargetCell,
    suite_config,
)
from AI_combi_testing_platform.sub_suites.release_gate_breakpoint.exchange import (
    RELEASE_CANDIDATES_PER_TASK,
    build_release_gate_spec_text,
    write_release_exchange_package,
)
from AI_combi_testing_platform.sub_suites.release_gate_breakpoint.runtime import (
    rg_candidate_id,
    rg_render,
    rg_task_id,
)
from AI_combi_testing_platform.sub_suites.release_gate_breakpoint.task_factory import (
    generate_release_gate_ladder,
)


SEED = b"public-release-gate-package-test-seed-v2"


def _plan_from_signature(signature: str) -> dict:
    options = [
        option
        for bit, option in zip(
            signature[5:],
            (
                "alt_rule_labels",
                "alt_decision_words",
                "dist_archive",
                "dist_override",
            ),
        )
        if bit == "1"
    ]
    return {
        "section_order": (
            ["evidence", "policy"]
            if signature[0] == "1"
            else ["policy", "evidence"]
        ),
        "numeric_surface": "converted" if signature[1] == "1" else "native",
        "context_depth": "long" if signature[2] == "1" else "clean",
        "schema": "plain" if signature[3] == "1" else "json",
        "trust_wording": "nested" if signature[4] == "1" else "direct",
        "options": options,
    }


def _fake_reader_source(task: dict, signature: str) -> str:
    plan = _plan_from_signature(signature)
    lines = [
        "import json",
        'RG_PLAN = {"section_order": [], "options": []}',
        "RG_LEVEL = 0",
    ]
    for section in plan["section_order"]:
        lines.append(f'RG_PLAN["section_order"].append("{section}")')
    for key in ("numeric_surface", "context_depth", "schema", "trust_wording"):
        lines.append(f'RG_PLAN["{key}"] = "{plan[key]}"')
    for option in plan["options"]:
        lines.append(f'RG_PLAN["options"].append("{option}")')
    document = {
        "candidate_id": rg_candidate_id(task, plan),
        "task_id": rg_task_id(task),
        "level": 0,
        "difficulty_units": task["difficulty_units"],
        "factor_signature": signature,
        "plan": plan,
        "prompt": rg_render(task, plan),
    }
    lines.append(f"print({json.dumps(json.dumps(document, sort_keys=True))})")
    return "\n".join(lines) + "\n"


def test_package_writer_and_bootstrap_reconcile_dynamic_design(
    tmp_path: Path,
) -> None:
    config = suite_config(
        (TargetCell("provider", "model label", "middle"),),
        difficulty_units=(2,),
    )
    task = generate_release_gate_ladder(SEED, (2,))[0].task
    candidates = tmp_path / "reader"
    candidates.mkdir()
    for bits in range(RELEASE_CANDIDATES_PER_TASK):
        signature = f"{bits:09b}"
        (candidates / f"candidate_{signature}.py").write_text(
            _fake_reader_source(task, signature),
            encoding="utf-8",
        )
    spec = tmp_path / "spec"
    spec.mkdir()
    (spec / "scenario.toml").write_text(
        build_release_gate_spec_text([task]),
        encoding="utf-8",
    )
    output = tmp_path / "exchange"
    write_release_exchange_package(
        output,
        tasks=[task],
        config=config,
        seed_commitment="rgh-test-commitment",
        spec=spec,
        reader_candidates=sorted(candidates.glob("*.py")),
        bundle_evidence={"all_reconciliation_checks": True},
    )
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["request_count"] == 2
    assert manifest["cell_count"] == 1
    assert manifest["full_constructor_candidate_count"] == 512
    assert (output / "bodies" / "HEAD.py").is_file()
    assert (output / "bodies" / "HEAD_RUNTIME.py").is_file()
    assert (output / "bodies" / "TASK_DATA.py").is_file()
    completed = subprocess.run(
        [sys.executable, str(output / "RunMeFirstOnce.py")],
        env={"PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    assert "2 of 2 slots remain empty" in completed.stdout
    assert not (output / "scored_results.json").exists()

    response_file = next((output / "responses").glob("*.txt"))
    response_file.write_text(
        response_file.read_text(encoding="utf-8").replace(
            "TARGET_MODEL_LABEL=model label",
            "TARGET_MODEL_LABEL=different model",
        ),
        encoding="utf-8",
    )
    rejected = subprocess.run(
        [sys.executable, str(output / "RunMeFirstOnce.py")],
        env={"PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert rejected.returncode != 0
