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

"""The one capability registry (Prompt 03 Part A).

Two obligations, and the second is the one that makes consolidation safe:

1. the registry must not claim more than the engine does — unknown values fail
   closed, every `SUPPORTED` row names real evidence, every rule's message is
   the one preflight actually raises;
2. routing preflight through the registry must not have **changed** which
   combinations are refused. `test_preflight_matches_the_registry_for_every_
   combination` is that characterization: it drives the real `preflight` over
   the enumerated matrix and asserts the accept/refuse decision agrees.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from bundle import architecture as arch
from bundle import capabilities as caps
from bundle.config import BundleConfig
from bundle.errors import PreflightError
from bundle.stages import capability_gate, capability_selection

REPO_ROOT = arch.REPO_ROOT
MATRIX_DOC = REPO_ROOT / "docs" / "33_CAPABILITY_MATRIX.md"


# --------------------------------------------------------------- registry ----
def test_levels_and_rule_codes_are_well_formed() -> None:
    codes = [r.code for r in caps.RULES]
    assert len(codes) == len(set(codes)), "reason codes must be unique and stable"
    for rule in caps.RULES:
        assert rule.level in (caps.UNSUPPORTED, caps.EXPERIMENTAL), rule.code
        assert rule.code.isupper() and " " not in rule.code
        assert rule.reason.strip() and rule.title.strip()
        assert rule.evidence, f"{rule.code} cites no evidence"


def test_unknown_dimension_values_fail_closed() -> None:
    """A value the registry has never heard of must not be waved through."""
    for bad in ({"language": "rust"}, {"candidate_sink": "carrier-pigeon"},
                {"run_mode": "yolo"}, {"execution_policy": "balanced"},
                {"network_mode": "sometimes"}, {"repeat_policy": "remote"},
                {"repeat_scope": "half"}, {"repeat_environments": "many"},
                {"lifecycle": "rewind"}, {"entrypoint": "telepathy"},
                {"repeat_polciy": "local"}):
        with pytest.raises(caps.UnknownDimensionValue):
            caps.classify(bad)


def test_defaults_produce_a_supported_combination() -> None:
    verdict = caps.classify({"execution_policy": "generated-default"})
    assert verdict.level == caps.SUPPORTED
    assert verdict.codes == ()
    assert verdict.evidence == caps.BASELINE_EVIDENCE


def test_every_runnable_row_cites_evidence_that_exists() -> None:
    """A SUPPORTED row whose evidence does not exist is a claim with no proof."""
    for case in caps.ci_cases():
        assert case["evidence"], case["id"]
        for evidence in case["evidence"]:
            path = REPO_ROOT / "generator_trunk" / evidence
            assert path.is_file(), f"{case['id']} cites missing evidence {evidence}"


def test_unsupported_rows_all_carry_a_blocking_code() -> None:
    for row in caps.capability_matrix()["combinations"]:
        if row["level"] != caps.UNSUPPORTED:
            continue
        blocking = [c for c in row["codes"] if caps.RULES_BY_CODE[c].level == caps.UNSUPPORTED]
        assert blocking, row["selection"]


def test_experimental_is_not_a_weaker_unsupported() -> None:
    """EXPERIMENTAL rows must be runnable: no blocking code, real evidence."""
    for row in caps.capability_matrix()["combinations"]:
        if row["level"] != caps.EXPERIMENTAL:
            continue
        assert not any(caps.RULES_BY_CODE[c].level == caps.UNSUPPORTED for c in row["codes"])
        assert row["evidence"]


def test_matrix_is_deterministic_and_serializable() -> None:
    first = json.dumps(caps.capability_matrix(), sort_keys=True)
    assert first == json.dumps(caps.capability_matrix(), sort_keys=True)


def test_counts_add_up() -> None:
    matrix = caps.capability_matrix()
    assert sum(matrix["counts"].values()) == len(matrix["combinations"])
    expected = 1
    for dimension in caps.ENUMERATED:
        expected *= len(dimension.values)
    assert len(matrix["combinations"]) == expected


# ------------------------------------- characterization: preflight parity ----
def _args(selection) -> SimpleNamespace:
    return SimpleNamespace(
        lang={"python": "py", "java": "java"}[selection["language"]],
        mode=selection["run_mode"],
        legacy_handoff=(selection["handoff"] == "legacy"),
        analyzer=("m:min" if selection["analyzer"] != "none" else ""),
        analysis_mode=(selection["analyzer"] if selection["analyzer"] != "none"
                       else "exploratory"),
        lifecycle=selection.get("lifecycle", "run"),
        entrypoint=selection.get("entrypoint", "direct"),
    )


def _cfg(selection) -> BundleConfig:
    import dataclasses
    return dataclasses.replace(
        BundleConfig(),
        candidate_sink=selection["candidate_sink"],
        execution_policy_profile=selection["execution_policy"],
        executor_pool_size=(4 if selection["executor_pool"] == "multi" else 1),
        repeat_each_candidate=(3 if selection["repeat"] == "k_gt_1" else 1),
        repeat_policy=selection.get("repeat_policy", "local"),
        repeat_scope=selection.get("repeat_scope", "metrics"),
        repeat_environments=(2 if selection.get("repeat_environments") == "configured" else 0),
        analyzer_goals=("m:min" if selection["analyzer"] != "none" else ""),
    )


def test_selection_projection_round_trips() -> None:
    """The launcher's arguments must land on the matrix coordinates they mean."""
    for selection in caps.iter_selections():
        assert capability_selection(_args(selection), _cfg(selection)) == selection


def _pre_registry_guards_would_refuse(s) -> bool:
    """Independent transcription of the guards removed from stages.preflight.

    This deliberately does not call the registry.  Comparing capability_gate()
    with classify() is tautological because the former delegates to the latter.
    """
    pool = s["executor_pool"] == "multi"
    grpc = s["candidate_sink"] == "grpc"
    return any((
        pool and s["language"] != "java",
        pool and s["candidate_sink"] != "loose-files",
        pool and s["run_mode"] == "stress",
        pool and s["handoff"] != "v2",
        pool and s["repeat"] != "k1",
        grpc and s["language"] != "java",
        grpc and s["run_mode"] == "stress",
        grpc and s["handoff"] != "v2",
        grpc and s["execution_policy"] != "trusted-local",
        s["language"] == "java" and s["run_mode"] == "stress",
        s["language"] == "java" and s["handoff"] != "v2",
        s["run_mode"] == "stress" and s["analyzer"] != "none",
        s["repeat"] == "k_gt_1" and s["handoff"] != "v2",
        s["repeat"] == "k_gt_1" and s["repeat_policy"] != "local",
    ))


def test_preflight_matches_the_independent_pre_registry_guards() -> None:
    """The compact matrix preserves the old engine accept/refuse boundary."""
    mismatches = []
    for selection in caps.iter_selections():
        expected_blocked = _pre_registry_guards_would_refuse(selection)
        try:
            capability_gate(_args(selection), _cfg(selection))
            actual_blocked = False
        except PreflightError:
            actual_blocked = True
        if actual_blocked != expected_blocked:
            mismatches.append((selection, expected_blocked, actual_blocked))
    assert not mismatches, mismatches[:5]


@pytest.mark.parametrize("selection,code", [
    ({"language": "python", "executor_pool": "multi"}, "POOL_REQUIRES_JAVA"),
    ({"language": "java", "executor_pool": "multi", "candidate_sink": "sharded"},
     "POOL_REQUIRES_LOOSE_FILES"),
    ({"language": "java", "executor_pool": "multi", "run_mode": "stress"},
     "POOL_REQUIRES_VERDICT"),
    ({"language": "java", "executor_pool": "multi", "handoff": "legacy"},
     "POOL_REQUIRES_HANDOFF_V2"),
    ({"language": "java", "executor_pool": "multi", "repeat": "k_gt_1"},
     "POOL_INCOMPATIBLE_WITH_REPEAT"),
    ({"language": "python", "candidate_sink": "grpc"}, "GRPC_REQUIRES_JAVA"),
    ({"language": "java", "candidate_sink": "grpc", "run_mode": "stress"},
     "GRPC_REQUIRES_VERDICT"),
    ({"language": "java", "candidate_sink": "grpc", "handoff": "legacy"},
     "GRPC_REQUIRES_HANDOFF_V2"),
    ({"language": "java", "candidate_sink": "grpc", "execution_policy": "generated-default"},
     "GRPC_REQUIRES_TRUSTED_LOCAL"),
    ({"language": "java", "run_mode": "stress"}, "JAVA_REQUIRES_VERDICT"),
    ({"language": "java", "handoff": "legacy"}, "JAVA_REQUIRES_HANDOFF_V2"),
    ({"run_mode": "stress", "analyzer": "formal"}, "STRESS_HAS_NO_ANALYZER"),
    ({"repeat": "k_gt_1", "handoff": "legacy"}, "REPEAT_REQUIRES_HANDOFF_V2"),
    ({"repeat": "k_gt_1", "repeat_policy": "disperse"},
     "REPEAT_POLICY_NOT_LAUNCHER_EXECUTABLE"),
    ({"repeat": "k_gt_1", "repeat_policy": "nested",
      "repeat_environments": "inactive"}, "REPEAT_POLICY_NOT_LAUNCHER_EXECUTABLE"),
])
def test_each_refusal_names_its_stable_code(selection, code) -> None:
    """Every refusal an operator can hit is identified by a code they can search
    for — the point of a stable reason code."""
    verdict = caps.classify(selection)
    assert verdict.level == caps.UNSUPPORTED
    assert code in verdict.codes
    with pytest.raises(PreflightError) as excinfo:
        capability_gate(_args(caps.normalize(selection)), _cfg(caps.normalize(selection)))
    assert str(excinfo.value).startswith(code)


def test_the_policy_rule_does_not_fire_before_the_policy_is_resolved() -> None:
    """Preflight runs before `authorize_execution`. A policy-dependent rule must
    stay quiet rather than guess, so the operator gets the policy error — which
    is more actionable — instead of a capability error."""
    undecided = caps.classify({"language": "java", "candidate_sink": "grpc",
                               "execution_policy": caps.UNDECIDED})
    assert undecided.blocking_code == ""
    decided = caps.classify({"language": "java", "candidate_sink": "grpc",
                             "execution_policy": "networked-api-probe"})
    assert decided.blocking_code == "GRPC_REQUIRES_TRUSTED_LOCAL"


# ------------------------------------------------------- generated outputs ---
def test_the_documentation_table_is_generated_and_current() -> None:
    assert MATRIX_DOC.is_file(), "run `bundle_run.py capabilities --markdown docs/33_CAPABILITY_MATRIX.md`"
    text = MATRIX_DOC.read_text(encoding="utf-8")
    assert text.startswith("<!-- GENERATED"), "the table must declare that it is generated"
    assert text == caps.format_matrix_markdown(), (
        "docs/33_CAPABILITY_MATRIX.md is stale; regenerate it from the registry")


def test_the_markdown_lists_every_rule_and_no_unsupported_row() -> None:
    text = caps.format_matrix_markdown()
    for rule in caps.RULES:
        assert f"`{rule.code}`" in text
    # Unsupported combinations are represented by their rules, not enumerated one
    # by one: 717 rows whose information content is entirely in 12 rules would be
    # noise. (The rules table legitimately shows UNSUPPORTED in its level column,
    # so this checks the combinations section specifically.)
    combinations = text.split("## Runnable combinations", 1)[1]
    assert " | UNSUPPORTED | " not in combinations


def test_ci_cases_cover_exactly_the_runnable_combinations() -> None:
    matrix = caps.capability_matrix()
    runnable = [r for r in matrix["combinations"] if r["level"] != caps.UNSUPPORTED]
    cases = caps.ci_cases()
    assert len(cases) == len(runnable)
    assert len({c["id"] for c in cases}) == len(cases)


# ------------------------------------------------------ GUI option surface ---
def test_a_gui_is_told_which_values_are_selectable_and_why() -> None:
    """The failure the audit found: a UI offering something the engine refuses.
    A surface that renders this cannot do that."""
    options = {e["value"]: e for e in caps.available_values(
        "candidate_sink", {"language": "python", "execution_policy": "generated-default"})}
    assert options["loose-files"]["enabled"] is True
    assert options["grpc"]["enabled"] is False
    assert options["grpc"]["code"] == "GRPC_REQUIRES_JAVA"
    assert options["grpc"]["reason"] == caps.RULES_BY_CODE["GRPC_REQUIRES_JAVA"].reason


def test_available_values_reflects_the_rest_of_the_selection() -> None:
    java = {e["value"]: e for e in caps.available_values(
        "candidate_sink", {"language": "java", "execution_policy": "trusted-local"})}
    assert java["grpc"]["enabled"] is True
    assert java["grpc"]["level"] == caps.EXPERIMENTAL


def test_contextual_dimensions_are_preserved_and_policy_network_is_derived() -> None:
    resolved = caps.normalize({"execution_policy": "networked-api-probe",
                               "repeat_scope": "all", "lifecycle": "resume",
                               "entrypoint": "gateway"})
    assert resolved["network_mode"] == "allowlist"
    assert resolved["repeat_scope"] == "all"
    assert resolved["lifecycle"] == "resume"
    assert resolved["entrypoint"] == "gateway"


def test_nested_environment_and_policy_network_rules_are_independently_visible() -> None:
    nested = caps.classify({"repeat": "k_gt_1", "repeat_policy": "nested",
                            "repeat_environments": "inactive"})
    assert "NESTED_REPEAT_REQUIRES_ENVIRONMENTS" in nested.codes
    mismatch = caps.classify({"execution_policy": "generated-default",
                              "network_mode": "unrestricted"})
    assert mismatch.blocking_code == "POLICY_NETWORK_MODE_MISMATCH"
