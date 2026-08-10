#!/usr/bin/env python3
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
# Some names in this file are name-holders: neutral stand-ins where a
# vendor's product name would otherwise appear. Deliberate, not an
# oversight -- see 'Name-holders' in NOTICE.md.

"""Validate and score the offline exponential release-gate exchange."""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import importlib.util
import json
from pathlib import Path
import re
from types import ModuleType


HERE = Path(__file__).resolve().parent
PLACEHOLDER = "[[PASTE EXACT AI RESPONSE HERE]]"
BEGIN = re.compile(
    r"^----- BEGIN RELEASE_GATE_RESPONSE cell_sequence=(\d+) "
    r"global_sequence=(\d+) request_id=(rgx-[a-f0-9]{20}) -----$"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_oracle() -> ModuleType:
    path = HERE / "oracle_runtime.py"
    spec = importlib.util.spec_from_file_location("release_gate_exchange_oracle", path)
    if spec is None or spec.loader is None:
        raise SystemExit("could not load packaged exact oracle")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_response_file(path: Path) -> tuple[str, dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    model_line = next((line for line in lines if line.startswith("TARGET_MODEL_LABEL=")), "")
    model = model_line.partition("=")[2].strip()
    responses: dict[str, str] = {}
    index = 0
    while index < len(lines):
        match = BEGIN.fullmatch(lines[index])
        if not match:
            index += 1
            continue
        cell_sequence, global_sequence, request_id = match.groups()
        end = (
            "----- END RELEASE_GATE_RESPONSE "
            f"cell_sequence={cell_sequence} global_sequence={global_sequence} "
            f"request_id={request_id} -----"
        )
        try:
            end_index = lines.index(end, index + 1)
        except ValueError as exc:
            raise SystemExit(f"missing END marker in {path.name}: {request_id}") from exc
        response = "\n".join(lines[index + 1 : end_index]).strip()
        if request_id in responses:
            raise SystemExit(f"duplicate response marker in {path.name}: {request_id}")
        if len(response.encode("utf-8")) > 16384:
            raise SystemExit(f"response exceeds 16384 bytes: {request_id}")
        responses[request_id] = response
        index = end_index + 1
    return model, responses


def _safe_diagnostic(value: dict[str, object]) -> dict[str, object]:
    result = dict(value)
    strict = dict(result.pop("strict"))
    return {"strict": strict, **result}


def _cell_summaries(
    scored: list[dict[str, object]],
    variant_names: list[str],
) -> dict[str, dict[str, object]]:
    summaries: dict[str, dict[str, object]] = {}
    cells = sorted(
        {
            (
                str(row["provider"]),
                str(row["model_label"]),
                str(row["effort"]),
            )
            for row in scored
        }
    )
    for provider, model, effort in cells:
        rows = [
            row
            for row in scored
            if (
                str(row["provider"]) == provider
                and str(row["model_label"]) == model
                and str(row["effort"]) == effort
            )
        ]
        first_failure: dict[str, dict[str, int] | None] = {}
        for variant in variant_names:
            failures = sorted(
                (
                    int(row["level"]),
                    int(row["difficulty_units"]),
                )
                for row in rows
                if row["variant"] == variant
                and not int(row["diagnostic"]["semantic_correct"])
            )
            first_failure[variant] = (
                None
                if not failures
                else {
                    "level": failures[0][0],
                    "difficulty_units": failures[0][1],
                }
            )
        key = json.dumps([provider, model, effort], ensure_ascii=False)
        summaries[key] = {
            "provider": provider,
            "model_label": model,
            "effort": effort,
            "requests": len(rows),
            "strict_pass": sum(
                int(row["diagnostic"]["strict"]["code"] == 0) for row in rows
            ),
            "semantic_extracted_pass": sum(
                int(row["diagnostic"]["semantic_correct"]) for row in rows
            ),
            "first_semantic_failure": first_failure,
            "claim_scope": (
                "single-run breakpoint discovery; repeat evidence still required"
            ),
        }
    return summaries


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    manifest = json.loads((HERE / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != "ai-combi-release-gate-exchange/v2":
        raise SystemExit("unsupported release-gate exchange manifest")
    for relative, expected in manifest.get("immutable_sha256", {}).items():
        path = HERE / relative
        if not path.is_file() or sha256(path) != expected:
            raise SystemExit(f"immutable exchange file changed or missing: {relative}")

    records = manifest.get("records", [])
    by_file: dict[str, list[dict[str, object]]] = defaultdict(list)
    for record in records:
        by_file[str(record["response_file"])].append(record)
    completed: list[dict[str, object]] = []
    empty: list[str] = []
    for relative, file_records in sorted(by_file.items()):
        model_label, responses = parse_response_file(HERE / relative)
        expected_models = {str(record["target_model"]) for record in file_records}
        if len(expected_models) != 1 or model_label not in expected_models:
            raise SystemExit(f"response model label does not match manifest: {relative}")
        expected_ids = [str(record["request_id"]) for record in file_records]
        if set(responses) != set(expected_ids):
            raise SystemExit(f"response markers do not match manifest: {relative}")
        for record in file_records:
            request_id = str(record["request_id"])
            response = responses[request_id]
            if not response or response == PLACEHOLDER:
                empty.append(request_id)
                continue
            completed.append({**record, "model_label": model_label, "response": response})
    if empty:
        print(f"READY FOR RESPONSES: {len(empty)} of {len(records)} slots remain empty")
        return 2 if args.require_complete else 0
    if len(completed) != len(records):
        raise SystemExit("response count did not reconcile")

    oracle = load_oracle()
    scored: list[dict[str, object]] = []
    for row in sorted(completed, key=lambda item: int(item["global_sequence"])):
        task = json.loads((HERE / str(row["task_file"])).read_text(encoding="utf-8"))
        plan = json.loads((HERE / str(row["plan_file"])).read_text(encoding="utf-8"))
        if oracle.rg_task_id(task) != row["task_id"]:
            raise SystemExit(f"task identity mismatch: {row['request_id']}")
        if oracle.rg_candidate_id(task, plan) != row["candidate_id"]:
            raise SystemExit(f"candidate identity mismatch: {row['request_id']}")
        diagnostic = oracle.rg_diagnose_response(task, plan, str(row["response"]))
        scored.append(
            {
                key: value
                for key, value in row.items()
                if key != "response"
            }
            | {"diagnostic": _safe_diagnostic(diagnostic)}
        )

    variant_docs = manifest.get("breakpoint_variants")
    if (
        not isinstance(variant_docs, list)
        or not variant_docs
        or any(not isinstance(item, dict) or "name" not in item for item in variant_docs)
    ):
        raise SystemExit("manifest has no valid breakpoint variants")
    variant_names = [str(item["name"]) for item in variant_docs]
    observed_variants = {str(row["variant"]) for row in scored}
    if observed_variants != set(variant_names):
        raise SystemExit("scored response variants do not match the manifest")
    summaries = _cell_summaries(scored, variant_names)

    (HERE / "responses_for_import.json").write_text(
        json.dumps(
            {
                "schema": "ai-combi-release-gate-response-import/v2",
                "responses": sorted(completed, key=lambda row: int(row["global_sequence"])),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    output = HERE / "scored_results.json"
    output.write_text(
        json.dumps(
            {
                "schema": "ai-combi-release-gate-scores/v2",
                "strict_gate_upgraded_by_extraction": False,
                "oracle": "deterministic packaged policy-tree evaluator",
                "summaries": summaries,
                "results": scored,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"COMPLETE: {len(scored)} responses scored -> {output}")
    for summary in summaries.values():
        label = "/".join(
            str(summary[key]) for key in ("provider", "model_label", "effort")
        )
        print(
            f"{label}: strict={summary['strict_pass']}/{summary['requests']} "
            f"semantic={summary['semantic_extracted_pass']}/{summary['requests']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
