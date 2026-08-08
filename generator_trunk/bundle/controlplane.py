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

"""Plan-2 control-plane plan emitter — the Python → Java seam (REPEAT_POLICY_REFACTOR_PLAN.md §P2.3 #1).

Emits the JSON run-plan consumed by the Java ``BundleControlPlane.Plan.fromJson``
(``Analyzer_trunk/.../optimization/BundleControlPlane.java``). The Python planner
keeps owning experiment design (ADR-8); it hands the Java control plane a plan to
dispatch. This is the mirror of the Java ingest.

Field provenance:
  * **Plan-1** fields come from ``BundleConfig.validate_repeat()`` —
    ``policy`` / ``repeatK`` (= ``repeat_each_candidate``) / ``repeatScope`` and
    the env list (``nested`` → one named env per ``repeat_environments``).
  * **Plan-2 control-plane** fields — ``maxInFlight``, ``serializePerHost`` /
    ``metricSensitivity``, ``budgetMillis``, and a named env pool — are
    deployment-level. They are included only when explicitly supplied, so the
    Java side falls back to its own defaults otherwise.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Mapping, Optional, Sequence

if TYPE_CHECKING:  # avoid import cost / cycles; we only duck-type cfg
    from .config import BundleConfig


def controlplane_plan(
    cfg: "BundleConfig",
    *,
    candidates: "Optional[Sequence[Any]]" = None,
    env_names: "Optional[Sequence[str]]" = None,
    max_in_flight: "Optional[int]" = None,
    serialize_per_host: "Optional[bool]" = None,
    metric_sensitivity: "Optional[str]" = None,
    budget_millis: "Optional[int]" = None,
    run_id: "Optional[str]" = None,
) -> dict:
    """Build the control-plane plan dict the Java side consumes.

    Mirrors ``BundleControlPlane.Plan.fromJson``. ``repeatScope`` is carried for
    fidelity (the Java control plane ignores fields it does not consume). Invalid
    repeat parameters fail closed via :meth:`BundleConfig.validate_repeat`.

    Env identity (2026-07-03 reconciliation): the default single-host env id is
    ``local:<run_id or 'default'>`` — byte-identical to the ``--envId`` /
    ``-envId`` value ``bundle.stages._repeat_executor_flags`` /
    ``_java_repeat_executor_flags`` hand the live executors, which is what they
    stamp into every ``results_v2`` row's ``env_id``. Before this, the plan
    defaulted to ``""`` while the live rows said ``local:<run>`` — the same
    sample carried two different identities depending on which control-plane
    layer described it. A plan and the rows it dispatches must join on equal
    keys, so the emitter now mirrors the live convention exactly (including the
    ``'default'`` fallback).

    ``budget_millis`` left unset falls back to the layered config's
    ``budget_wall_time_seconds`` ceiling (converted to ms) — the Python budget
    gate and the Java dispatch deadline then enforce the SAME wall-clock number
    instead of two independently-configured ones.
    """
    policy, scope, k, _e_eff = cfg.validate_repeat()
    envs = list(env_names) if env_names else _default_envs(policy, cfg.repeat_environments, run_id)
    plan: "dict[str, Any]" = {
        "policy": policy,
        "repeatK": k,
        "repeatScope": scope,
        "envs": envs,
    }
    if max_in_flight is not None:
        plan["maxInFlight"] = int(max_in_flight)
    if serialize_per_host is not None:
        plan["serializePerHost"] = bool(serialize_per_host)
    if metric_sensitivity is not None:
        plan["metricSensitivity"] = str(metric_sensitivity)
    if budget_millis is None and cfg.budget_wall_time_seconds is not None:
        budget_millis = int(float(cfg.budget_wall_time_seconds) * 1000)
    if budget_millis is not None:
        plan["budgetMillis"] = int(budget_millis)
    if candidates is not None:
        plan["candidates"] = [_candidate_obj(c) for c in candidates]
    return plan


def _default_envs(policy: str, repeat_environments: int, run_id: "Optional[str]" = None) -> "list[str]":
    """``nested`` → one named env per ``repeat_environments``; ``local`` /
    ``disperse`` → the single-host env id ``local:<run_id or 'default'>``
    (the exact identity the live executors stamp into results_v2 — see
    ``bundle.stages._repeat_executor_flags``). For a real multi-instance
    ``disperse`` run the deployment supplies the executor pool via
    ``env_names``; on one host ``disperse`` degenerates to ``local``
    (no between-env signal)."""
    if policy == "nested":
        e = max(1, int(repeat_environments or 0))
        return [f"env-{i}" for i in range(e)]
    return [f"local:{run_id or 'default'}"]


def _candidate_obj(c: Any) -> dict:
    """Normalize a candidate (``Mapping`` or ``(lineNo, candidateId, raw)``) to
    the Java plan's candidate shape."""
    if isinstance(c, Mapping):
        cid = c.get("candidateId", c.get("candidate_id", ""))
        return {
            "lineNo": int(c.get("lineNo", c.get("line_no", 0))),
            "candidateId": str(cid),
            "raw": str(c.get("raw", "")),
        }
    line_no, candidate_id, raw = c
    return {"lineNo": int(line_no), "candidateId": str(candidate_id), "raw": str(raw)}


def plan_json(cfg: "BundleConfig", *, indent: "Optional[int]" = 2, **kwargs) -> str:
    """Serialize :func:`controlplane_plan` to a JSON string."""
    return json.dumps(controlplane_plan(cfg, **kwargs), indent=indent)


def write_plan_json(path, cfg: "BundleConfig", **kwargs) -> None:
    """Write the plan JSON to ``path`` (what a launcher would feed to
    ``java … BundleControlPlane <plan.json>``)."""
    from pathlib import Path

    Path(path).write_text(plan_json(cfg, **kwargs), encoding="utf-8")
