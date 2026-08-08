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

"""Reference-coverage audit tests.

Two properties matter most and both are enforced here:

* the capability registry cannot drift from the engine — every capability must
  be parseable by the real `fwgen` grammar, and every ``FW_`` name that grammar
  recognizes must be owned by exactly one capability;
* the audit must not editorialize — no aggregate "power" score, no invented
  measurement, no silently dropped spec.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import fwgen as fg
from bundle import architecture as arch
from bundle import coverage as cov
from bundle.handoff import validate_against_json_schema

SCHEMA_PATH = arch.REPO_ROOT / "generator_trunk" / "bundle-reference-coverage-v1.schema.json"


# ------------------------------------------- registry <-> engine agreement ----
@pytest.mark.parametrize("capability", cov.CAPABILITIES, ids=lambda c: c.id)
def test_every_capability_probe_is_accepted_by_the_real_parser(capability) -> None:
    """The registry may not claim a capability the engine cannot parse."""
    accepted = fg.is_core_verb(capability.probe) or fg.is_core_flag(capability.probe)
    assert accepted, f"{capability.id}: fwgen rejects probe {capability.probe!r}"


def test_every_grammar_token_is_owned_by_exactly_one_capability() -> None:
    """The inverse guard: a verb added to the engine must be added to the audit,
    or the audit would silently under-report the engine's vocabulary."""
    owners: "dict[str, list[str]]" = {}
    for capability in cov.CAPABILITIES:
        for token in capability.tokens:
            owners.setdefault(token, []).append(capability.id)
    tokens = cov.grammar_tokens()
    assert set(owners) == tokens, (
        f"unowned engine tokens: {sorted(tokens - set(owners))}; "
        f"registry tokens the grammar does not know: {sorted(set(owners) - tokens)}")
    duplicated = {token: ids for token, ids in owners.items() if len(ids) > 1}
    assert duplicated == {}


def test_capability_ids_are_unique_and_orders_are_sane() -> None:
    ids = [c.id for c in cov.CAPABILITIES]
    assert len(ids) == len(set(ids))
    assert {c.order for c in cov.CAPABILITIES} <= {1, 2, 3}
    # Second/third-order composition must be present: it is the engine's
    # distinguishing property, not an optional extra.
    assert {"composition.brace", "composition.brace_nested",
            "composition.brace_nested_grouped", "operator.group"} <= set(ids)


# ------------------------------------------------------- report properties ----
def test_report_validates_against_its_published_schema() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validate_against_json_schema(cov.reference_coverage_report(), schema)


def test_report_is_deterministic_for_one_source_revision() -> None:
    first = json.dumps(cov.reference_coverage_report(), sort_keys=True)
    second = json.dumps(cov.reference_coverage_report(), sort_keys=True)
    assert first == second


def test_report_contains_no_aggregate_power_score() -> None:
    """`Do not invent a single "power percentage"` — made enforceable, because a
    later contributor's convenience summary is exactly how such a number
    appears."""
    blob = json.dumps(cov.reference_coverage_report()).lower()
    for forbidden in ("power_percent", "coverage_percent", "coverage_score",
                      "power_score", "overall_score", "capability_percent"):
        assert forbidden not in blob


def test_every_registered_specification_parses() -> None:
    for app in cov.reference_coverage_report()["coverage_targets"]:
        assert app["specs_unreadable"] == [], (app["id"], app["specs_unreadable"])
        assert app["specs_scanned"] > 0, app["id"]


def test_capability_state_rejects_an_unknown_capability() -> None:
    entry = cov.reference_coverage_report()["coverage_targets"][0]
    with pytest.raises(KeyError):
        cov.capability_state(entry, "operator.does_not_exist")


# --------------------------------------------------- per-application facts ----
def _app(report: dict, app_id: str) -> dict:
    return next(a for a in report["coverage_targets"] if a["id"] == app_id)


def test_the_direct_engine_demonstration_reaches_fourth_order_composition() -> None:
    entry = _app(cov.reference_coverage_report(), "engine-demo")
    assert entry["max_composition_order"] >= 4
    for capability in ("composition.brace", "composition.brace_nested",
                       "operator.group", "operator.permut_repetition", "flag.exclude"):
        assert cov.capability_state(entry, capability) == cov.EXERCISED, capability


def test_the_ai_platform_is_registered_as_a_reference_application() -> None:
    entry = _app(cov.reference_coverage_report(), "ai-combi")
    assert entry["status"] == "experimental"
    assert entry["role"] == arch.REFERENCE_APPLICATION
    assert entry["unexercised_capabilities"], (
        "an application that exercised the engine's whole vocabulary would make the "
        "engine/application distinction unobservable; this assertion documents that it does not")


def test_launcher_restrictions_are_evidence_bearing() -> None:
    report = cov.reference_coverage_report()
    for app in report["coverage_targets"]:
        for restriction in app["policy_restrictions"]:
            assert restriction["value_kind"] in ("literal", "dynamic", "switch")
            assert restriction["presence_kind"] in ("always", "conditional")
            assert bool(restriction["condition"]) == (
                restriction["presence_kind"] == "conditional")
            assert restriction["line"] >= 1
            # A dynamic value must not be reported as if it were pinned text.
            if restriction["value_kind"] != "literal":
                assert restriction["value"] == ""
    ai = _app(report, "ai-combi")
    pinned = {r["flag"]: r["value"] for r in ai["policy_restrictions"]
              if r["value_kind"] == "literal"}
    assert pinned.get("--execution-policy-profile") == "trusted-local"
    assert pinned.get("--analysis-mode") == "formal"


def test_argparse_options_and_optional_dynamic_budgets_are_not_pinned_policy() -> None:
    """Declaring ``parser.add_argument('--budget-requests')`` or conditionally
    forwarding a user value is not the same as imposing a budget ceiling."""
    ai = _app(cov.reference_coverage_report(), "ai-combi")
    flags = {restriction["flag"] for restriction in ai["policy_restrictions"]}
    assert "--budget-requests" not in flags
    assert "--budget-monetary-cost" not in flags
    conditional = {restriction["flag"] for restriction in ai["policy_restrictions"]
                   if restriction["presence_kind"] == "conditional"}
    assert {"--allow-extreme", "--override-budget"} <= conditional


def test_declared_direct_benchmark_args_match_the_launcher_policy() -> None:
    """The overhead comparison is only fair if the direct leg reproduces the
    application's own pinned policy. This checks the declaration against the
    launcher source rather than trusting it."""
    report = cov.reference_coverage_report()
    for app in arch.COVERAGE_TARGETS:
        if not app.benchmark_direct_args:
            continue
        declared = dict(zip(app.benchmark_direct_args, app.benchmark_direct_args[1:]))
        pinned = {r["flag"]: r["value"] for r in _app(report, app.id)["policy_restrictions"]
                  if r["value_kind"] == "literal"}
        for flag in ("--execution-policy-profile", "--analysis-mode", "--lang", "--candidate-sink"):
            if flag in pinned and flag in declared:
                assert declared[flag] == pinned[flag], (app.id, flag)
        if declared.get("--execution-policy-profile") == "trusted-local":
            assert declared.get("--candidate-origin") in {
                "reviewed-checked-in", "locally-authored"}, app.id
            assert declared.get("--acknowledge-trusted-local"), app.id


# -------------------------------------------------------- measurement flow ----
def test_measurements_are_only_carried_when_actually_measured() -> None:
    bench = {
        "schema": "bundle.benchmark/v1",
        "environment": {"hardware": {"cpu_count": 8}},
        "stages": [
            {"stage": "reference_overhead[engine-demo]", "application": "engine-demo",
             "skipped": False, "candidates": 8, "scenario": "spec",
             "phases": {"engine.core": 1.5, "application_overhead": 0.25}},
            {"stage": "reference_overhead[ai-combi]", "application": "ai-combi",
             "skipped": True, "skip_reason": "no database", "candidates": 0},
        ],
    }
    measurements = cov.measurements_from_benchmark(bench)
    assert set(measurements) == {"engine-demo"}
    assert measurements["engine-demo"]["phases"]["engine.core"] == 1.5

    report = cov.reference_coverage_report(bench)
    assert "measurement" in _app(report, "engine-demo")
    # A skipped stage must leave no measurement block at all — not a zero.
    assert "measurement" not in _app(report, "ai-combi")


def test_report_survives_schema_validation_with_measurements_attached() -> None:
    bench = {
        "schema": "bundle.benchmark/v1",
        "environment": {"hardware": {"cpu_count": 8}, "os_kernel": {}, "toolchain": {}},
        "stages": [
            {"stage": "reference_overhead[engine-demo]", "application": "engine-demo",
             "skipped": False, "candidates": 8, "scenario": "spec",
             "notes": "aggregate wrapper cost", "phases": {"engine.core": 1.5}},
        ],
    }
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validate_against_json_schema(cov.reference_coverage_report(bench), schema)
