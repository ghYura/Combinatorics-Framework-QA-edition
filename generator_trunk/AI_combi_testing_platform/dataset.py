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

"""Exact-oracle-gated, deduplicated dataset export."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path

from .engine import EvaluationResult


@dataclass
class VerifiedDataset:
    license_id: str
    privacy_classification: str
    records: list[dict[str, object]] = field(default_factory=list)
    _seen: set[str] = field(default_factory=set, repr=False)

    def __post_init__(self) -> None:
        if not self.license_id or not self.privacy_classification:
            raise ValueError("license and privacy metadata are required")

    def add(self, result: EvaluationResult) -> bool:
        if (
            result.code != 0
            or result.task is None
            or result.render is None
            or result.oracle is None
            or result.completion is None
            or not result.oracle.correct
            or not result.oracle.all_constraints_pass
        ):
            return False
        key = hashlib.sha256(
            (
                result.task.structural_hash
                + "\0"
                + result.render.renderer_id
                + "\0"
                + result.response
            ).encode("utf-8")
        ).hexdigest()
        if key in self._seen:
            return False
        self._seen.add(key)
        self.records.append(
            {
                "schema": "ai-combi.verified-pair/v1",
                "dedupe_id": key,
                "canonical_task": result.task.canonical_dict(),
                "task_hash": result.task.structural_hash,
                "prompt": result.render.prompt,
                "response": result.response,
                "oracle": {
                    "exact": True,
                    "format_ok": result.oracle.format_ok,
                    "constraints_met": result.oracle.constraints_met,
                    "constraints_total": result.oracle.constraints_total,
                },
                "provenance": {
                    "adapter": result.completion.adapter_id,
                    "model": result.completion.model_id,
                    "source_kind": (
                        "control" if result.completion.is_control else "model"
                    ),
                    "renderer_id": result.render.renderer_id,
                    "prompt_version": result.render.prompt_version,
                    "seed": result.task.seed,
                },
                "license": self.license_id,
                "privacy": self.privacy_classification,
            }
        )
        return True

    def write_jsonl(self, path: Path) -> int:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(
                json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n"
                for record in self.records
            ),
            encoding="utf-8",
        )
        return len(self.records)
