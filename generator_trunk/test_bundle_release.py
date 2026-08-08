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

"""Release manifest, SBOM, skip classification and dependency pins (Prompt 03 B–D).

The governing property: **the release machinery may not assert anything it did
not observe.** An unclassified skip is blocking, an unpinned dependency is
reported as unpinned rather than assumed fine, and the reproducibility claim
carries its own limits.
"""
from __future__ import annotations

import json
import re
import sys

import pytest

from bundle import architecture as arch
from bundle import release as rel

REPO_ROOT = arch.REPO_ROOT


# ------------------------------------------------------ skip classification --
@pytest.mark.parametrize("reason,expected", [
    ("EXPECTED_OPTIONAL: browser E2E needs the test-full extra", rel.EXPECTED_OPTIONAL),
    ("could not import 'grpc': No module named 'grpc'", rel.EXPECTED_OPTIONAL),
    ("Analyzer build not present", rel.EXPECTED_OPTIONAL),
    ("live E2E is opt-in; set FACE1_E2E=1", rel.EXPECTED_OPTIONAL),
    ("refusing to delete a real deploy/.env", rel.EXPECTED_OPTIONAL),
    ("requires Linux user namespaces", rel.UNSUPPORTED_PLATFORM),
    ("not supported on macOS", rel.UNSUPPORTED_PLATFORM),
    ("rootless Docker container backend not reachable", rel.MISSING_AUTHORIZED_BACKEND),
    ("main PostgreSQL :5433 not reachable", rel.MISSING_AUTHORIZED_BACKEND),
    ("Core jar missing", rel.MISSING_AUTHORIZED_BACKEND),
    ("MISSING_AUTHORIZED_BACKEND: needs the sibling SUT checkout on PYTHONPATH",
     rel.MISSING_AUTHORIZED_BACKEND),
])
def test_known_skip_reasons_are_classified(reason, expected) -> None:
    assert rel.classify_skip(reason) == expected


@pytest.mark.parametrize("reason", [
    "", "   ", "flaky, will look at it later", "temporarily disabled", "TODO",
])
def test_an_unrecognized_skip_is_blocking(reason) -> None:
    """Fail-closed: a skip nobody has classified must stop a release gate, not be
    quietly tolerated. This is the whole point of the taxonomy."""
    assert rel.classify_skip(reason) == rel.BLOCKING_UNEXPECTED


def test_skip_report_separates_blocking_from_accounted_for() -> None:
    report = rel.classify_skips([
        "could not import 'grpc'",
        "rootless Docker not reachable",
        "we'll fix it next sprint",
    ])
    assert report.total == 3
    assert report.by_class[rel.EXPECTED_OPTIONAL] == 1
    assert report.by_class[rel.MISSING_AUTHORIZED_BACKEND] == 1
    assert [e["reason"] for e in report.blocking] == ["we'll fix it next sprint"]
    assert [e["class"] for e in report.release_blocking] == [
        rel.MISSING_AUTHORIZED_BACKEND, rel.BLOCKING_UNEXPECTED]


def test_missing_backend_is_classified_but_still_release_blocking() -> None:
    report = rel.classify_skips(["main PostgreSQL :5433 not reachable"])
    assert report.entries[0]["class"] == rel.MISSING_AUTHORIZED_BACKEND
    assert report.blocking == []
    assert len(report.release_blocking) == 1


def test_pytest_skip_lines_are_parsed() -> None:
    output = (
        "==== short test summary info ====\n"
        "SKIPPED [1] generator_trunk/test_bundle_gateway.py:270: could not import 'grpc'\n"
        "SKIPPED [3] generator_trunk/test_bundle_benchmark.py:201: Analyzer build not present\n"
        "1019 passed, 13 skipped in 854.07s\n"
    )
    parsed = rel.parse_pytest_skips(output)
    assert [p["count"] for p in parsed] == [1, 3]
    assert [p["where"] for p in parsed] == [
        "generator_trunk/test_bundle_gateway.py:270",
        "generator_trunk/test_bundle_benchmark.py:201"]
    assert all(rel.classify_skip(p["reason"]) != rel.BLOCKING_UNEXPECTED for p in parsed)


def test_pytest_summary_records_failures_and_refuses_truncated_logs() -> None:
    summary = rel.parse_pytest_summary("2 failed, 10 passed, 3 skipped in 4.20s\n")
    assert summary["complete"] is True
    assert (summary["failed"], summary["passed"], summary["skipped"]) == (2, 10, 3)
    assert rel.parse_pytest_summary("test output stopped mid-run")["complete"] is False


def test_release_cli_refuses_a_failed_pytest_log_after_emitting_evidence(tmp_path) -> None:
    from bundle import cli
    pytest_log = tmp_path / "pytest.txt"
    pytest_log.write_text(
        "FAILED test_demo.py::test_broken - AssertionError\n"
        "1 failed, 1 passed in 0.10s\n",
        encoding="utf-8",
    )
    output = tmp_path / "release.json"
    args = type("Args", (), {
        "pytest_output": str(pytest_log), "sbom": "", "out": str(output),
        "allow_blocking_skips": False,
    })()
    with pytest.raises(Exception, match="not release-green"):
        cli.cmd_release(args)
    assert output.is_file(), "failed evidence should still be inspectable/uploadable"


def test_release_cli_counts_grouped_skips_not_summary_lines(tmp_path) -> None:
    from bundle import cli
    pytest_log = tmp_path / "pytest.txt"
    pytest_log.write_text(
        "SKIPPED [3] test_demo.py:10: EXPECTED_OPTIONAL: optional fixture\n"
        "4 passed, 3 skipped in 0.10s\n",
        encoding="utf-8",
    )
    output = tmp_path / "release.json"
    args = type("Args", (), {
        "pytest_output": str(pytest_log), "sbom": "", "out": str(output),
        "allow_blocking_skips": False,
    })()
    cli.cmd_release(args)
    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert manifest["tests"]["skipped"] == 3
    assert manifest["tests"]["classified_skip_count"] == 3
    assert manifest["skips"]["total"] == 3


def test_every_skip_in_this_repository_is_classifiable() -> None:
    """The repository's own skip reasons must all be classifiable, or the gate it
    is meant to protect cannot be switched on."""
    unclassified = []
    pattern = re.compile(r"""(?:reason|skip)\s*=\s*["'](?P<reason>[^"']{4,})["']""")
    for path in REPO_ROOT.glob("generator_trunk/**/test_*.py"):
        if "__pycache__" in str(path):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "importorskip" not in text and "pytest.skip" not in text and "skipif" not in text:
            continue
        for match in pattern.finditer(text):
            reason = match.group("reason")
            if rel.classify_skip(reason) == rel.BLOCKING_UNEXPECTED:
                unclassified.append(f"{arch.repo_relative(path)}: {reason}")
    assert not unclassified, (
        "these skip reasons are not classifiable; prefix them with a class "
        f"(EXPECTED_OPTIONAL / UNSUPPORTED_PLATFORM / MISSING_AUTHORIZED_BACKEND): {unclassified}")


# ---------------------------------------------------------- release manifest --
def test_release_manifest_validates_and_records_provenance() -> None:
    manifest = rel.release_manifest()
    rel.validate_release_manifest(manifest)
    json.dumps(manifest)
    assert manifest["source"]["engine_revision"].startswith("sha256:")
    assert manifest["release_inputs"], "a release with no hashed inputs describes nothing"
    assert manifest["capability_matrix"]["counts"]["SUPPORTED"] > 0


def test_the_manifest_records_dirty_state_rather_than_hiding_it() -> None:
    source = rel.release_manifest()["source"]
    if source["available"]:
        assert "dirty" in source
        # This working tree is intentionally modified, so the manifest must say so.
        assert isinstance(source["dirty"], bool)


def test_reproducibility_states_what_is_not_claimed() -> None:
    """Overclaiming reproducibility is worse than not claiming it: a consumer
    would trust a byte-equality property that does not hold."""
    block = rel.release_manifest()["reproducibility"]
    assert block["claim"]
    joined = " ".join(block["not_claimed"]).lower()
    assert "byte" in joined, "Maven jars are not byte-reproducible; say so"
    assert "timestamp_note" in block


def test_a_manifest_without_the_not_claimed_block_is_invalid() -> None:
    bad = rel.release_manifest()
    bad["reproducibility"] = {"claim": "perfectly reproducible"}
    with pytest.raises(ValueError, match="NOT claimed"):
        rel.validate_release_manifest(bad)


def test_a_manifest_with_a_bad_input_hash_is_invalid() -> None:
    bad = rel.release_manifest()
    bad["release_inputs"][0]["sha256"] = "not-a-hash"
    with pytest.raises(ValueError, match="sha256"):
        rel.validate_release_manifest(bad)


# ------------------------------------------------------------------- SBOM ----
def test_sbom_is_cyclonedx_and_covers_each_ecosystem() -> None:
    sbom = rel.generate_sbom()
    assert sbom["bomFormat"] == "CycloneDX" and sbom["specVersion"] == "1.5"
    kinds = {c["type"] for c in sbom["components"]}
    assert "library" in kinds
    names = {c["name"] for c in sbom["components"]}
    assert "postgres" in names, "the deploy stack's images belong in the SBOM"
    assert any(c.get("group", "").startswith("com.") for c in sbom["components"]), \
        "the Maven reactor modules belong in the SBOM"


def test_sbom_states_its_own_scope() -> None:
    """A reader must not mistake a declared-component SBOM for a transitive one."""
    properties = {p["name"]: p["value"] for p in rel.generate_sbom()["metadata"]["properties"]}
    assert "not a transitive" in properties["bundle:scope"]


def test_every_sbom_component_has_a_purl() -> None:
    for component in rel.generate_sbom()["components"]:
        assert component.get("purl"), component["name"]


# -------------------------------------------------------- dependency pins ----
def test_pin_audit_reports_state_rather_than_assuming_it() -> None:
    pins = rel.dependency_pins()
    assert pins["counts"]["total"] > 0
    kinds = {e["kind"] for e in pins["entries"]}
    assert {"github-action", "container-image", "python"} <= kinds
    for entry in pins["unpinned"]:
        # An unpinned entry is only useful if it says how to fix it.
        assert entry["remediation"].strip(), entry["name"]


def test_github_actions_pin_state_is_detected_correctly() -> None:
    actions = [e for e in rel.dependency_pins()["entries"] if e["kind"] == "github-action"]
    assert actions, "the workflow declares no actions?"
    for entry in actions:
        expected = bool(re.fullmatch(r"[0-9a-f]{40}", entry["pin"]))
        assert entry["pinned"] is expected, entry


def test_container_images_are_detected_as_digest_pinned_only_with_a_digest() -> None:
    images = [e for e in rel.dependency_pins()["entries"] if e["kind"] == "container-image"]
    assert images
    for entry in images:
        assert entry["pinned"] is ("@sha256:" in entry["pin"]), entry


def test_the_python_release_lock_exists_and_declares_its_limits() -> None:
    lock = REPO_ROOT / "requirements-release.lock"
    assert lock.is_file(), "generate it with pip freeze in a clean release venv"
    text = lock.read_text(encoding="utf-8")
    assert "SCOPE AND LIMITS" in text
    assert "not a universal lock" in text or "universal lock" in text
    assert "pyproject.toml remains the human-maintained" in text
    pinned = [line for line in text.splitlines()
              if line.strip() and not line.startswith("#")]
    assert pinned, "the lock records no resolved distributions"
    for line in pinned:
        assert "==" in line, f"a release lock must pin exactly, got {line!r}"


# ---------------------------------------------------------------- workflow ---
def test_the_workflow_declares_three_tiers() -> None:
    text = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    for job in ("tier1-hygiene:", "tier1-contracts:", "tier1-java:",
                "tier2-integration:", "tier3-release-evidence:"):
        assert job in text, job


def test_tier3_is_not_run_on_every_push() -> None:
    """Release evidence on every push would make it meaningless and slow."""
    text = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    tier3 = text.split("tier3-release-evidence:", 1)[1]
    assert "github.event_name == 'schedule'" in tier3
    assert "github.event_name == 'workflow_dispatch'" in tier3


def test_the_workflow_documents_immutable_action_pins() -> None:
    """The comment and every observed action ref must agree: full SHA pins."""
    text = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "ACTION PINNING" in text
    assert "immutable full commit SHA" in text
    actions = [entry for entry in rel.dependency_pins()["entries"]
               if entry["kind"] == "github-action"]
    assert actions and all(entry["pinned"] for entry in actions), actions


def test_the_workflow_asserts_the_fail_closed_security_properties() -> None:
    text = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "no execution policy selected" in text, "CI must prove a run without a policy is refused"
    assert "a secure profile completed without a sandbox" in text, \
        "CI must prove generated-default fails closed"


# ============================================================================
# Review item A.1 — SBOM/pin-audit correctness regressions.
#
# Each of these encodes a defect found in review: an SBOM that inventoried the
# reviewer's host, licence metadata borrowed across versions, the private SUT
# checkout leaking into the Framework inventory, and an aggregate Python surface
# described as locked when it is not.
# ============================================================================
def _sbom():
    return rel.generate_sbom()


def test_python_sbom_names_equal_the_lock_exactly() -> None:
    """The SBOM describes what this repository declares, not what happens to be
    installed on the machine that generated it."""
    locked = {name.lower() for name, _ in rel.locked_python_requirements()}
    reported = {c["name"].lower() for c in _sbom()["components"]
                if c["purl"].startswith("pkg:pypi/")}
    assert reported == locked, reported.symmetric_difference(locked)


def test_all_sbom_purls_are_unique() -> None:
    components = _sbom()["components"]
    purls = [c["purl"] for c in components]
    duplicates = {p for p in purls if purls.count(p) > 1}
    assert not duplicates, duplicates


def test_unresolved_maven_versions_are_encoded_in_purls() -> None:
    """An unresolved version such as `(managed)` must not produce a purl with raw
    parentheses; a consumer parsing it would silently mis-read the coordinate."""
    for component in _sbom()["components"]:
        purl = component["purl"]
        if purl.startswith("pkg:maven/"):
            assert " " not in purl, purl
            assert "(" not in purl and ")" not in purl, purl


def test_no_inventory_source_comes_from_the_sibling_sut_checkout() -> None:
    """CI checks the private SUT out INSIDE the Framework tree. Discovery must be
    limited to Git-tracked Framework files, or the SUT leaks into the SBOM."""
    offenders = []
    for component in _sbom()["components"]:
        for prop in component.get("properties", []):
            value = str(prop.get("value", ""))
            if value.startswith("SUT/") or "/SUT/" in value:
                offenders.append(f"{component['name']}: {value}")
    for entry in rel.dependency_pins()["entries"]:
        for source in entry.get("sources", [entry.get("source", "")]):
            if str(source).startswith("SUT/") or "/SUT/" in str(source):
                offenders.append(f"{entry['name']}: {source}")
    assert not offenders, offenders


def test_the_upstream_fork_is_inventoried_and_not_first_party() -> None:
    """`com.github.ghYura` is the owner's namespace, but the fork's CODE is
    upstream's. Marking it first-party would hide the provenance question."""
    forks = [c for c in _sbom()["components"]
             if "combinatoricslib3parallel" in c["purl"].lower()]
    assert forks, "the fork must appear in the SBOM"
    for component in forks:
        props = {p["name"]: str(p["value"]).lower() for p in component.get("properties", [])}
        assert props.get("bundle:first_party") == "false", props


def test_same_reactor_snapshots_are_treated_as_source_pinned() -> None:
    """A SNAPSHOT built from this reactor is pinned by the source revision; only
    a SNAPSHOT resolved from outside is mutable."""
    snapshots = [e for e in rel.dependency_pins()["entries"]
                 if e["kind"] == "maven" and "SNAPSHOT" in str(e.get("pin", ""))]
    for entry in snapshots:
        if "combinatoricslib3parallel" in entry["name"] or "com.yurii" in entry["name"]:
            assert entry["pinned"] is True, entry


def test_python_extras_outside_the_lock_are_reported_as_uncovered() -> None:
    """The lock covers Tier-3 test,science,deploy only. Reporting the aggregate
    Python surface as locked would be the overclaim."""
    uncovered = {e["name"].lower() for e in rel.dependency_pins()["entries"]
                 if e["kind"] == "python" and not e["pinned"]}
    for expected in ("nicegui", "grpcio", "fastapi"):
        assert expected in uncovered, f"{expected} is outside the lock and must be reported"


def test_the_lock_header_states_its_profile_scope() -> None:
    text = (REPO_ROOT / "requirements-release.lock").read_text(encoding="utf-8")
    assert "PROFILE SCOPE" in text
    assert "test,science,deploy" in text
    assert "does NOT cover every published feature surface" in text


# --- A.2 validation ----------------------------------------------------------
def test_dirty_source_is_not_release_evidence() -> None:
    manifest = rel.release_manifest()
    source = manifest["source"]
    eligible = manifest["reproducibility"]["release_evidence_eligible"]
    assert eligible == bool(source.get("available") and not source.get("dirty"))


def test_contradictory_eligibility_is_rejected() -> None:
    manifest = rel.release_manifest()
    manifest["reproducibility"]["release_evidence_eligible"] = True
    manifest["source"]["dirty"] = True
    manifest["source"]["available"] = True
    with pytest.raises(ValueError, match="contradicts the recorded source state"):
        rel.validate_release_manifest(manifest)


def test_a_failed_canonical_sut_inventory_is_rejected() -> None:
    manifest = rel.release_manifest()
    manifest["canonical_suts"] = {"error": "SutManifestError: boom"}
    with pytest.raises(ValueError, match="canonical SUT inventory failed"):
        rel.validate_release_manifest(manifest)


@pytest.mark.parametrize("drift_key", ["missing_ci_paths", "missing_ci_wiring"])
def test_any_canonical_sut_drift_is_rejected(drift_key: str) -> None:
    manifest = rel.release_manifest()
    manifest["canonical_suts"].setdefault("drift", {})[drift_key] = ["engine-demo: nope"]
    with pytest.raises(ValueError, match="canonical SUT drift"):
        rel.validate_release_manifest(manifest)


@pytest.mark.parametrize("section", [
    "dependency_pins", "third_party_licenses", "tests", "canonical_suts", "release_inputs",
])
def test_a_missing_evidence_section_invalidates_a_manifest(section: str) -> None:
    manifest = rel.release_manifest()
    manifest.pop(section)
    with pytest.raises(ValueError):
        rel.validate_release_manifest(manifest)


# --- A.3 exit code -----------------------------------------------------------
def test_a_recorded_non_zero_exit_code_is_parsed() -> None:
    parsed = rel.parse_pytest_summary("10 passed in 2.0s\nBUNDLE_PYTEST_EXIT_CODE=3\n")
    assert parsed["exit_code"] == 3
    assert parsed["passed"] == 10          # the summary still reads green...


def test_the_release_gate_refuses_a_green_summary_with_a_non_zero_exit(tmp_path) -> None:
    """...and the gate must still refuse it. An internal error after the summary
    line is exactly this shape."""
    import subprocess
    log = tmp_path / "pytest.txt"
    log.write_text("10 passed in 2.0s\nBUNDLE_PYTEST_EXIT_CODE=3\n", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "generator_trunk/bundle_run.py", "release",
         "--pytest-output", str(log)],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=600)
    assert proc.returncode != 0
    assert "BUNDLE_PYTEST_EXIT_CODE=3" in (proc.stdout + proc.stderr)


def test_a_zero_exit_marker_does_not_block(tmp_path) -> None:
    parsed = rel.parse_pytest_summary("10 passed in 2.0s\nBUNDLE_PYTEST_EXIT_CODE=0\n")
    assert parsed["exit_code"] == 0


# --- A.4 CI capture ----------------------------------------------------------
def test_tier3_preserves_the_real_pytest_exit_code() -> None:
    """`| tee` makes $? the exit code of tee. Without PIPESTATUS a crashed run
    looks green to anything reading only the log."""
    text = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    tier3 = text.split("tier3-release-evidence:", 1)[1]
    assert "PIPESTATUS[0]" in tier3
    assert "BUNDLE_PYTEST_EXIT_CODE=" in tier3
    assert "|| true" not in tier3.split("BUNDLE_PYTEST_EXIT_CODE=", 1)[0].rsplit("pytest", 1)[-1]
