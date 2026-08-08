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

"""Canonical SUT adapter manifests (Prompt 03 Part E).

A manifest is a claim about a System Under Test. These tests make the claims
checkable: the schema is enforced, the declared capability row must be one the
engine actually supports, every referenced test and scenario path must exist,
and a canonical SUT must be able to demonstrate that its oracle detects
something.
"""
from __future__ import annotations

import copy
import json

import pytest

from bundle import architecture as arch
from bundle import capabilities as caps
from bundle import sut_manifests as sm

REPO_ROOT = arch.REPO_ROOT
MANIFESTS = sm.load_all()
IDS = [m["id"] for m in MANIFESTS]


# ------------------------------------------------------------- the set -------
def test_the_canonical_set_is_three_to_five_suts() -> None:
    """Prompt 03 asks for three to five. Fewer is not a release gate; more means
    'canonical' has stopped meaning anything."""
    canonical = [m for m in MANIFESTS if m["maturity"] == sm.CANONICAL]
    assert 3 <= len(canonical) <= 5, IDS


def test_every_manifest_validates() -> None:
    for path in sm.manifest_paths():
        sm.load_manifest(path)                    # raises on any violation


def test_ids_are_unique_and_match_their_filename() -> None:
    assert len(IDS) == len(set(IDS))
    for path in sm.manifest_paths():
        assert json.loads(path.read_text(encoding="utf-8"))["id"] == path.stem


def test_exclusions_are_recorded_with_a_reason() -> None:
    """An undocumented absence is indistinguishable from an oversight."""
    assert sm.EXCLUDED
    for name, reason in sm.EXCLUDED.items():
        assert reason.strip(), name
    assert set(sm.EXCLUDED) & {"GPT-2_sandbox", "3Dprofile-VS-2Dsieve"}, (
        "mutable ML and approximate geometry must be explicitly excluded")
    assert not set(sm.EXCLUDED) & set(IDS), "a SUT cannot be both canonical and excluded"


# ------------------------------------------------------------- contents ------
@pytest.mark.parametrize("manifest", MANIFESTS, ids=IDS)
def test_capability_row_is_supported_by_the_engine(manifest) -> None:
    """A manifest cannot claim a combination the registry refuses."""
    verdict = caps.classify(manifest["capability_row"])
    assert verdict.blocking_code == "", (manifest["id"], verdict.codes)


@pytest.mark.parametrize("manifest", MANIFESTS, ids=IDS)
def test_every_referenced_path_exists(manifest) -> None:
    for path in list(manifest["ci"]["tests"]) + list(manifest["ci"].get("scenarios", [])):
        assert (REPO_ROOT / path).exists(), f"{manifest['id']} references missing {path}"


@pytest.mark.parametrize("manifest", MANIFESTS, ids=IDS)
def test_controls_can_demonstrate_detection(manifest) -> None:
    """Known-pass alone proves nothing about an oracle: a check that never fails
    and a check that never runs look identical."""
    assert manifest["controls"]["known_pass"]
    assert manifest["controls"]["known_fail"]


@pytest.mark.parametrize("manifest", MANIFESTS, ids=IDS)
def test_oracle_independence_is_stated_plainly(manifest) -> None:
    oracle = manifest["oracle"]
    assert oracle["independence"].strip()
    if oracle["kind"] == "threshold":
        # The weakest kind must admit its limits rather than imply independence.
        assert manifest.get("caveats"), manifest["id"]
        assert "PARTIAL" in oracle["independence"] or "not independent" in oracle["independence"]


@pytest.mark.parametrize("manifest", MANIFESTS, ids=IDS)
def test_no_machine_specific_path_or_credential(manifest) -> None:
    blob = json.dumps(manifest)
    assert "/home/" not in blob, manifest["id"]
    for shape in ("password=", "api_key=", "token="):
        assert shape not in blob.lower(), manifest["id"]


@pytest.mark.parametrize("manifest", MANIFESTS, ids=IDS)
def test_a_sibling_checkout_resolves_through_bundle_sut_root(manifest) -> None:
    """Never a hardcoded sibling path: the workspace layout is the operator's."""
    source = manifest["source"]
    if source["kind"] == "sibling-checkout":
        assert source.get("sut_paths_key"), manifest["id"]
        import sut_paths
        assert source["sut_paths_key"] in sut_paths.PROJECT_DIRS, (
            f"{manifest['id']} names an unknown sut_paths key")


def test_network_facing_suts_are_not_gated_unsandboxed() -> None:
    for manifest in MANIFESTS:
        if manifest.get("candidate_origin") == "network-facing":
            assert manifest["capability_row"]["execution_policy"] != "trusted-local", manifest["id"]
            assert manifest["access"]["network"], manifest["id"]


def test_a_sut_with_no_network_declares_an_empty_network_set() -> None:
    """An empty list is a statement; a missing key would be an assumption."""
    for manifest in MANIFESTS:
        assert isinstance(manifest["access"]["network"], list), manifest["id"]


def test_the_set_covers_more_than_one_oracle_kind() -> None:
    """A canonical set that shares one oracle style would share its blind spot."""
    kinds = {m["oracle"]["kind"] for m in MANIFESTS}
    assert len(kinds) >= 3, kinds
    assert "exact-differential" in kinds, "at least one SUT must have an exact oracle"


def test_at_least_one_interaction_only_defect_is_declared() -> None:
    """The fault class flat construction misses is the one the Bundle exists to
    find; the canonical set must contain at least one."""
    interaction = [d for m in MANIFESTS for d in m["controls"].get("intentional_defects", [])
                   if d.get("interaction_only")]
    assert interaction, "no canonical SUT declares an interaction-only defect"


# ---------------------------------------------------------- fail-closed ------
def _mutated(index: int = 0, **changes) -> dict:
    data = copy.deepcopy(MANIFESTS[index])
    data.update(changes)
    return data


def test_an_unsupported_capability_row_is_refused() -> None:
    bad = _mutated()
    bad["capability_row"] = dict(bad["capability_row"], language="python", candidate_sink="grpc")
    with pytest.raises(sm.SutManifestError, match="UNSUPPORTED"):
        sm.validate_manifest(bad)


def test_an_unknown_capability_value_is_refused() -> None:
    bad = _mutated()
    bad["capability_row"] = dict(bad["capability_row"], candidate_sink="carrier-pigeon")
    with pytest.raises(sm.SutManifestError, match="unknown value"):
        sm.validate_manifest(bad)


def test_a_canonical_sut_without_a_known_fail_control_is_refused() -> None:
    bad = _mutated()
    bad["maturity"] = sm.CANONICAL
    bad["controls"] = dict(bad["controls"], known_fail=[])
    with pytest.raises(sm.SutManifestError):
        sm.validate_manifest(bad)


def test_a_wrong_schema_id_is_refused() -> None:
    with pytest.raises(sm.SutManifestError, match="schema must be"):
        sm.validate_manifest(_mutated(schema="bundle.sut-manifest/v99"))


def test_an_unknown_field_is_refused() -> None:
    with pytest.raises(sm.SutManifestError):
        sm.validate_manifest(_mutated(surprise="hello"))


def test_report_is_serializable_and_drift_free() -> None:
    data = sm.report()
    json.dumps(data)
    assert data["schema"] == sm.SCHEMA
    assert data["drift"]["missing_ci_paths"] == []
    assert data["drift"]["missing_ci_wiring"] == []


def test_canonical_means_invoked_by_the_workflow_not_merely_a_path_that_exists() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    for manifest in MANIFESTS:
        if manifest["maturity"] != sm.CANONICAL:
            continue
        marker = manifest["ci"]["workflow_gate"]
        assert marker in workflow, (manifest["id"], marker)


def test_ungated_candidate_harness_is_not_called_canonical() -> None:
    fintech = next(m for m in MANIFESTS if m["id"] == "fin-tech-to-test")
    assert fintech["maturity"] == sm.EXPERIMENTAL


# ============================================================================
# Review item B — canonical fail-closed wiring.
#
# A canonical SUT is a release gate. These pin the properties that make it one:
# it must actually run in CI, be deterministic, pin its source, and be gated at
# a policy consistent with the access it declares.
# ============================================================================
def _canonical() -> dict:
    return next(m for m in MANIFESTS if m["maturity"] == sm.CANONICAL)


# --- B.2 the marker must label a real step ----------------------------------
def test_every_canonical_gate_names_an_actual_workflow_step() -> None:
    assert sm.missing_ci_wiring() == []


def test_a_marker_only_in_a_comment_does_not_satisfy_the_gate(monkeypatch, tmp_path) -> None:
    """The defect this replaces: a comment mentioning the gate counted as
    coverage, so a gate that is discussed but never runs looked wired."""
    workflow = tmp_path / ".github" / "workflows"
    workflow.mkdir(parents=True)
    (workflow / "ci.yml").write_text(
        "jobs:\n  x:\n    steps:\n"
        "      # [canonical-sut-engine-demo] we should add this one day\n"
        "      - name: something else\n        run: true\n", encoding="utf-8")
    monkeypatch.setattr(sm.arch, "REPO_ROOT", tmp_path)
    manifest = dict(_canonical())
    manifest["ci"] = dict(manifest["ci"], workflow_gate="[canonical-sut-engine-demo]")
    assert sm.missing_ci_wiring([manifest]), "a comment must not satisfy the wiring check"


def test_a_marker_in_a_step_name_does_satisfy_the_gate(monkeypatch, tmp_path) -> None:
    workflow = tmp_path / ".github" / "workflows"
    workflow.mkdir(parents=True)
    (workflow / "ci.yml").write_text(
        "jobs:\n  x:\n    steps:\n"
        "      - name: \"[canonical-sut-engine-demo] direct engine smoke\"\n        run: true\n",
        encoding="utf-8")
    monkeypatch.setattr(sm.arch, "REPO_ROOT", tmp_path)
    manifest = dict(_canonical())
    manifest["ci"] = dict(manifest["ci"], workflow_gate="[canonical-sut-engine-demo]")
    assert sm.missing_ci_wiring([manifest]) == []


# --- B.3 canonical constraints -----------------------------------------------
def test_a_nondeterministic_canonical_sut_is_refused() -> None:
    bad = copy.deepcopy(_canonical())
    bad["determinism"] = dict(bad["determinism"], deterministic=False)
    with pytest.raises(sm.SutManifestError, match="must be deterministic"):
        sm.validate_manifest(bad)


def test_a_canonical_sut_without_a_candidate_origin_is_refused() -> None:
    bad = copy.deepcopy(_canonical())
    bad.pop("candidate_origin", None)
    with pytest.raises(sm.SutManifestError, match="candidate_origin"):
        sm.validate_manifest(bad)


@pytest.mark.parametrize("revision", ["main", "", "db1ac78", "z" * 40])
def test_a_canonical_sibling_checkout_must_pin_a_full_revision(revision: str) -> None:
    """A floating checkout means the gate tests an unknown SUT."""
    sibling = next((m for m in MANIFESTS
                    if m["maturity"] == sm.CANONICAL
                    and m["source"]["kind"] == "sibling-checkout"), None)
    if sibling is None:
        pytest.skip("EXPECTED_OPTIONAL: no canonical sibling-checkout SUT in this set")
    bad = copy.deepcopy(sibling)
    bad["source"] = dict(bad["source"], revision=revision)
    with pytest.raises(sm.SutManifestError, match="40-hex revision"):
        sm.validate_manifest(bad)


def test_a_canonical_sibling_checkout_must_use_a_sut_paths_key() -> None:
    sibling = next((m for m in MANIFESTS
                    if m["maturity"] == sm.CANONICAL
                    and m["source"]["kind"] == "sibling-checkout"), None)
    if sibling is None:
        pytest.skip("EXPECTED_OPTIONAL: no canonical sibling-checkout SUT in this set")
    bad = copy.deepcopy(sibling)
    bad["source"] = {k: v for k, v in bad["source"].items() if k != "sut_paths_key"}
    with pytest.raises(sm.SutManifestError, match="sut_paths key"):
        sm.validate_manifest(bad)


def test_network_access_and_gated_policy_must_agree() -> None:
    bad = copy.deepcopy(_canonical())
    bad["access"] = dict(bad["access"], network=["10.0.0.5"])
    with pytest.raises(sm.SutManifestError, match="networked-api-probe"):
        sm.validate_manifest(bad)


def test_a_probe_profile_without_declared_targets_is_refused() -> None:
    bad = copy.deepcopy(_canonical())
    bad["capability_row"] = dict(bad["capability_row"], execution_policy="networked-api-probe")
    bad["access"] = dict(bad["access"], network=[])
    with pytest.raises(sm.SutManifestError, match="declares no network access"):
        sm.validate_manifest(bad)


# --- B.4 the CLI fails closed ------------------------------------------------
@pytest.mark.parametrize("drift_key", ["missing_ci_paths", "missing_ci_wiring"])
def test_the_cli_fails_on_every_drift_list(monkeypatch, drift_key: str, capsys) -> None:
    """It previously failed only on missing paths, so an unwired gate — which
    looks like coverage — passed."""
    from bundle import cli
    from bundle.errors import PreflightError
    from types import SimpleNamespace

    data = sm.report()
    data["drift"] = {"missing_ci_paths": [], "missing_ci_wiring": []}
    data["drift"][drift_key] = ["engine-demo: fabricated drift"]
    monkeypatch.setattr(sm, "report", lambda: data)
    with pytest.raises(PreflightError, match="canonical SUT drift"):
        cli.cmd_sut_manifests(SimpleNamespace(json="", debug=False))


# --- B.5 status honesty -------------------------------------------------------
def test_telemetry_and_fintech_are_not_canonical_until_their_rows_run() -> None:
    """Absence of a bounded runtime row in CI is not evidence; they stay
    reference/experimental until it genuinely executes."""
    by_id = {m["id"]: m for m in MANIFESTS}
    for name in ("telemetry-catalog-service", "fin-tech-to-test"):
        manifest = by_id.get(name)
        if manifest:
            assert manifest["maturity"] != sm.CANONICAL, name
