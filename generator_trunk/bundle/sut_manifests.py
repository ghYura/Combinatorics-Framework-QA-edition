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

Which systems the Bundle is actually verified against — and on what terms — was
previously implicit in whichever scenario happened to reference a sibling
checkout. A manifest makes each one answerable without reading the scenario:
how it is resolved, started, reset and stopped; what its oracle is and **how
independent** that oracle is; which known-pass and known-fail controls exist;
what it may read, write and reach; the capability-matrix row it is gated at; and
the CI test that proves it.

Two properties are enforced rather than described:

* a manifest cannot claim a capability row the registry refuses
  (:func:`validate_manifest` classifies it through `bundle.capabilities`);
* a canonical manifest must carry at least one known-fail control — a SUT that
  has never been shown to fail cannot demonstrate that its oracle detects
  anything.

The canonical set is deliberately small. Promoting every historical experiment
would make "canonical" mean nothing; the excluded ones are recorded in
:data:`EXCLUDED` with the reason, so exclusion is a decision rather than an
oversight.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Mapping, Sequence

from . import architecture as arch
from . import capabilities as caps
from .handoff import validate_against_json_schema, HandoffError

SCHEMA = "bundle.sut-manifest/v1"

MANIFEST_DIR = arch.REPO_ROOT / "generator_trunk" / "sut_manifests"
SCHEMA_PATH = arch.REPO_ROOT / "generator_trunk" / "bundle-sut-manifest-v1.schema.json"

CANONICAL = "canonical"
REFERENCE = "reference"
EXPERIMENTAL = "experimental"


class SutManifestError(ValueError):
    """A SUT manifest is malformed, internally inconsistent, or claims a
    capability row the engine does not support."""


#: SUTs deliberately kept OUT of the canonical release set, with the reason.
#: Recorded here so a reader can see that each was considered — an undocumented
#: absence is indistinguishable from an oversight.
EXCLUDED: "Mapping[str, str]" = {
    "GPT-2_sandbox": "mutable ML weights; outputs are not reproducible across environments",
    "GPT-4-Lite_sandbox": "mutable ML weights; same reason",
    "llm_transformer_testme": "ML inference; no exact oracle and no deterministic reset",
    "3Dprofile-VS-2Dsieve": "approximate geometry; verdicts depend on floating-point tolerances",
    "shape_vs_sieve": "approximate geometry; same reason",
    "legacy_surrogate_apps": "historical surrogates retained for comparison, not maintained as gates",
    "advanced_surrogate": "tryout fixture; no versioned oracle contract",
    "advanced_surrogate2": "tryout fixture; no versioned oracle contract",
    "bundle_pricing_tryout": "tryout fixture; superseded by the fintech stack",
    "bundle_secure_pipeline_tryout": "tryout fixture used for dated 2026-06-11 sandbox evidence; "
                                     "kept as historical evidence rather than a current gate",
    "combination_thinking_tutor": "intentionally simple teaching fixture; not a defect-detection SUT",
    "tester_vs_pub": "illustrative fixture, not a defect-detection SUT",
}


def manifest_paths() -> "list[Path]":
    if not MANIFEST_DIR.is_dir():
        return []
    return sorted(MANIFEST_DIR.glob("*.json"))


def load_manifest(path: Path) -> dict:
    """Read one manifest, validate it, and return it."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SutManifestError(f"{path}: not readable JSON: {exc}")
    validate_manifest(data, source=arch.repo_relative(path))
    if data["id"] != Path(path).stem:
        raise SutManifestError(
            f"{path}: id {data['id']!r} must match the filename stem {Path(path).stem!r}")
    return data


def validate_manifest(data: Mapping, *, source: str = "<manifest>") -> None:
    """Structural + semantic validation. Raises :class:`SutManifestError`."""
    if data.get("schema") != SCHEMA:
        raise SutManifestError(f"{source}: schema must be {SCHEMA!r}, got {data.get('schema')!r}")
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SutManifestError(f"SUT manifest schema unreadable: {exc}")
    try:
        validate_against_json_schema(data, schema)
    except HandoffError as exc:
        raise SutManifestError(f"{source}: {exc}")

    # --- semantic checks the JSON Schema cannot express ---------------------
    row = dict(data["capability_row"])
    try:
        verdict = caps.classify(row)
    except caps.UnknownDimensionValue as exc:
        raise SutManifestError(f"{source}: capability_row names an unknown value: {exc}")
    if verdict.blocking_code:
        raise SutManifestError(
            f"{source}: capability_row is {caps.UNSUPPORTED} ({verdict.blocking_code}): "
            f"{caps.RULES_BY_CODE[verdict.blocking_code].reason}")

    if data["maturity"] == CANONICAL:
        # A canonical SUT must be able to demonstrate detection, not just success.
        if not data["controls"]["known_fail"]:
            raise SutManifestError(
                f"{source}: a canonical SUT must declare at least one known-fail control, or its "
                f"oracle has never been shown to detect anything")
        if not data["ci"]["tests"]:
            raise SutManifestError(f"{source}: a canonical SUT must name its CI tests")
        if not data["ci"].get("workflow_gate"):
            raise SutManifestError(
                f"{source}: a canonical SUT must name a stable ci.workflow_gate marker")

        # --- review item B.3 ------------------------------------------------
        # A canonical SUT is a release gate. A gate whose result can vary run to
        # run, or whose source revision can move under it, is not a gate.
        if not data["determinism"].get("deterministic"):
            raise SutManifestError(
                f"{source}: a canonical SUT must be deterministic; a gate whose result varies "
                f"between runs cannot fail closed")
        if not data.get("candidate_origin"):
            raise SutManifestError(
                f"{source}: a canonical SUT must declare its candidate_origin so the execution "
                f"policy it is gated at is justified")
        src = data["source"]
        kind = src.get("kind")
        if kind == "sibling-checkout":
            if not src.get("sut_paths_key"):
                raise SutManifestError(
                    f"{source}: a sibling-checkout SUT must resolve through a sut_paths key, "
                    f"never a hardcoded path")
            revision = str(src.get("revision", ""))
            if not re.fullmatch(r"[0-9a-f]{40}", revision):
                raise SutManifestError(
                    f"{source}: a canonical sibling checkout must pin a full 40-hex revision, got "
                    f"{revision!r}; a floating checkout means the gate tests an unknown SUT")
        elif kind == "in-repository":
            if not src.get("path"):
                raise SutManifestError(f"{source}: an in-repository SUT must declare its path")
        else:
            raise SutManifestError(f"{source}: unknown source kind {kind!r}")

        # Network access and the gated policy must agree in both directions: a
        # sandboxed profile with no allowlist cannot reach a target, and a SUT
        # that declares no network has no business requesting egress.
        policy = data["capability_row"].get("execution_policy")
        network = data["access"]["network"]
        if network and policy != "networked-api-probe":
            raise SutManifestError(
                f"{source}: declares network access {network} but is gated at {policy!r}; "
                f"reaching a network target requires networked-api-probe with an allowlist")
        if policy == "networked-api-probe" and not network:
            raise SutManifestError(
                f"{source}: is gated at networked-api-probe but declares no network access; "
                f"either declare the targets or use a profile without egress")

    # A weak oracle must say so. 'threshold' is the only kind allowed to be
    # non-independent, and only when it admits that in writing.
    if data["oracle"]["kind"] == "threshold" and not data.get("caveats"):
        raise SutManifestError(
            f"{source}: a threshold oracle must record its limitations in `caveats`")

    # A network-facing SUT must not be gated at the unsandboxed profile.
    if data.get("candidate_origin") == "network-facing" and \
            row.get("execution_policy") == "trusted-local":
        raise SutManifestError(
            f"{source}: a network-facing SUT must not be gated at trusted-local; use "
            f"networked-api-probe with a declared allowlist")


def load_all() -> "list[dict]":
    """Every manifest, validated, sorted by id."""
    return sorted((load_manifest(p) for p in manifest_paths()), key=lambda d: d["id"])


def missing_ci_tests(manifests: "Sequence[Mapping] | None" = None) -> "list[str]":
    """CI test paths a manifest names that do not exist. Non-empty is drift."""
    manifests = manifests if manifests is not None else load_all()
    missing = []
    for manifest in manifests:
        for test in manifest["ci"]["tests"]:
            if not (arch.REPO_ROOT / test).exists():
                missing.append(f"{manifest['id']}: {test}")
        for scenario in manifest["ci"].get("scenarios", ()):
            if not (arch.REPO_ROOT / scenario).exists():
                missing.append(f"{manifest['id']}: {scenario}")
    return missing


def missing_ci_wiring(manifests: "Sequence[Mapping] | None" = None) -> "list[str]":
    """Canonical gates absent from the actual workflow.

    Existing-path checks alone accepted ``harness.py`` as a CI test even though
    no workflow invoked it.  A canonical status is now coupled to a stable marker
    in the workflow that is reviewable beside the command it labels.
    """
    manifests = manifests if manifests is not None else load_all()
    workflow = arch.REPO_ROOT / ".github" / "workflows" / "ci.yml"
    text = workflow.read_text(encoding="utf-8") if workflow.is_file() else ""
    # Review item B.2: the marker must label an actual workflow STEP. Accepting
    # it anywhere in the file meant a comment mentioning the gate satisfied the
    # check — a gate that is discussed but never runs.
    step_names = set(re.findall(r"^\s*-?\s*name:\s*(.+?)\s*$", text, re.MULTILINE))
    missing = []
    for manifest in manifests:
        if manifest["maturity"] != CANONICAL:
            continue
        marker = manifest["ci"].get("workflow_gate", "")
        if not marker:
            missing.append(f"{manifest['id']}: (no workflow_gate declared)")
        elif not any(marker in name for name in step_names):
            missing.append(f"{manifest['id']}: {marker} is not in any workflow step name")
    return missing


def report() -> dict:
    """The versioned inventory of canonical SUTs."""
    manifests = load_all()
    return {
        "schema": SCHEMA,
        "engine_revision": arch.engine_revision(),
        "counts": {level: sum(1 for m in manifests if m["maturity"] == level)
                   for level in (CANONICAL, REFERENCE, EXPERIMENTAL)},
        "manifests": manifests,
        "excluded": dict(EXCLUDED),
        "drift": {"missing_ci_paths": missing_ci_tests(manifests),
                  "missing_ci_wiring": missing_ci_wiring(manifests)},
        "notes": [
            "The canonical set is intentionally small: promoting every historical experiment "
            "would make 'canonical' meaningless. Exclusions are recorded with their reason.",
            "Oracle independence is stated per SUT and is not uniform. `threshold` is the weakest "
            "kind and must record its limitations.",
            "A capability_row is validated against the capability registry, so a manifest cannot "
            "claim a combination the engine refuses.",
        ],
    }


def format_report(data: "dict | None" = None) -> str:
    data = data or report()
    lines = [f"canonical SUT manifests {data['schema']}  "
             f"engine_revision={data['engine_revision']}"]
    for manifest in data["manifests"]:
        defects = manifest["controls"].get("intentional_defects", [])
        interaction = sum(1 for d in defects if d.get("interaction_only"))
        lines.append(
            f"  {manifest['id']:<32} [{manifest['maturity']}] tier={manifest['ci']['tier']} "
            f"oracle={manifest['oracle']['kind']} "
            f"controls={len(manifest['controls']['known_pass'])}P/"
            f"{len(manifest['controls']['known_fail'])}F "
            f"defects={len(defects)}({interaction} interaction-only)")
        lines.append(f"      policy={manifest['capability_row']['execution_policy']} "
                     f"origin={manifest.get('candidate_origin', '-')} "
                     f"network={manifest['access']['network'] or 'none'}")
    lines.append(f"  excluded from the canonical set: {len(data['excluded'])} "
                 f"({', '.join(sorted(data['excluded'])[:4])}, ...)")
    if data["drift"]["missing_ci_paths"]:
        lines.append(f"  ⛔ drift: {len(data['drift']['missing_ci_paths'])} referenced path(s) "
                     f"do not exist")
        for entry in data["drift"]["missing_ci_paths"]:
            lines.append(f"      {entry}")
    else:
        lines.append("  ✓ every referenced test/scenario path exists")
    if data["drift"].get("missing_ci_wiring"):
        lines.append(f"  ⛔ drift: {len(data['drift']['missing_ci_wiring'])} canonical SUT gate(s) "
                     "are not wired into CI")
        for entry in data["drift"]["missing_ci_wiring"]:
            lines.append(f"      {entry}")
    else:
        lines.append("  ✓ every canonical SUT names an actual workflow gate")
    return "\n".join(lines)
