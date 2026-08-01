"""Execution-safety gates (docs/32_EXECUTION_SAFETY_AUDIT.md findings F1-F3, F6).

The property under test throughout: **nothing executes candidate code without an
explicit, recorded, re-verifiable trust decision.** Each test names the audit
finding it pins so a future change that reopens one is obvious in the failure.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from bundle import architecture as arch
from bundle.cli import _require_executor_summary, _resolve_execution_policy
from bundle.config import BundleConfig, ConfigError
from bundle.errors import StageError
from bundle.policy import (
    ExecutionAuthorization, ORIGIN_UNSPECIFIED, ORIGINS, PROFILES, PolicyError,
    PolicyIdentityError, TRUSTED_LOCAL_ELIGIBLE_ORIGINS, authorization_from_dict,
    authorize_execution, is_trusted_profile, policy_hash, policy_id, profile_choices,
    required_backend, resolve_policy, verify_same_policy,
)

REPO_ROOT = arch.REPO_ROOT


# ------------------------------------------------ F1: no implicit trust -------
def test_no_execution_policy_is_configured_by_default() -> None:
    """The audit's central finding: an operator who says nothing used to get
    unsandboxed host execution."""
    assert BundleConfig().execution_policy_profile == ""


def test_an_unset_profile_refuses_to_run_and_explains_the_choice() -> None:
    with pytest.raises(PolicyError) as excinfo:
        authorize_execution("")
    message = str(excinfo.value)
    assert "no execution policy selected" in message
    # The refusal must be actionable, naming both the secure and the reviewed path.
    assert "generated-default" in message
    assert "--acknowledge-trusted-local" in message
    assert "plan" in message                       # planning stays available


def test_unknown_profile_fails_closed() -> None:
    with pytest.raises(PolicyError):
        authorize_execution("balanced")            # see F2


def test_secure_profiles_need_no_acknowledgement() -> None:
    for name in ("generated-default", "networked-api-probe"):
        policy, auth = authorize_execution(name)
        assert auth.sandboxed is True
        assert auth.origin == ORIGIN_UNSPECIFIED
        assert auth.policy_hash == policy_hash(policy)


def test_trusted_local_requires_a_non_empty_reason() -> None:
    for reason in ("", "   "):
        with pytest.raises(PolicyError, match="explicit, recorded reason"):
            authorize_execution("trusted-local", origin="reviewed-checked-in",
                                acknowledgement=reason)


def test_trusted_local_requires_an_origin_classification() -> None:
    with pytest.raises(PolicyError, match="candidate origin"):
        authorize_execution("trusted-local", acknowledgement="reviewed in this checkout")


@pytest.mark.parametrize("origin", ["generated", "imported-untrusted", "network-facing"])
def test_an_acknowledgement_cannot_authorize_untrusted_code_on_the_host(origin: str) -> None:
    """The acknowledgement records a decision; it does not grant a permission.
    Without this, the gate would be pure friction: anyone blocked by it would
    type a reason and run generated code unsandboxed anyway."""
    with pytest.raises(PolicyError) as excinfo:
        authorize_execution("trusted-local", origin=origin,
                            acknowledgement="I accept the risk")
    assert "cannot authorize" in str(excinfo.value)
    assert "generated-default" in str(excinfo.value)


@pytest.mark.parametrize("origin", TRUSTED_LOCAL_ELIGIBLE_ORIGINS)
def test_reviewed_origins_may_use_trusted_local_with_a_reason(origin: str) -> None:
    policy, auth = authorize_execution("trusted-local", origin=origin,
                                       acknowledgement="checked-in reviewed candidate fragments")
    assert auth.sandboxed is False
    assert auth.origin == origin
    assert auth.acknowledgement
    assert auth.policy_id == policy_id(policy)


def test_unknown_origin_is_rejected() -> None:
    with pytest.raises(PolicyError, match="unknown candidate origin"):
        authorize_execution("generated-default", origin="probably-fine")


def test_origin_is_never_taken_from_the_specification() -> None:
    """A scenario that could declare itself trusted would defeat the gate, so the
    origin must not be a spec-level key."""
    import fwgen as fg
    for key in ("candidate_origin", "execution_policy_profile", "trusted_local_acknowledgement"):
        assert key not in fg.SPEC_V1_KNOWN_KEYS
        assert key not in fg.SPEC_V1_SLOT_KNOWN_KEYS


def test_config_layer_refuses_an_unset_profile_with_a_bundle_error() -> None:
    """The CLI surface must render this as a concise BundleError, not a traceback."""
    with pytest.raises(ConfigError):
        _resolve_execution_policy(BundleConfig())


def test_config_layer_records_the_final_policy_identity() -> None:
    """Folding a network allowlist changes the policy document; the recorded
    identity must be the one actually executed under, or resume would compare
    against a hash no run ever used."""
    cfg = dataclasses.replace(
        BundleConfig(),
        execution_policy_profile="networked-api-probe",
        sandbox_network_allowlist="api-server")
    policy, view, auth = _resolve_execution_policy(cfg)
    assert auth.policy_hash == policy_hash(policy) == view["sha256"]
    assert "api-server" in policy.network_allowlist


# ------------------------------------- F2: one profile registry, no phantoms --
def test_profile_choices_offer_exactly_the_profiles_that_exist() -> None:
    assert {c["profile"] for c in profile_choices()} == set(PROFILES)


def test_profile_choices_include_the_secure_profile_and_flag_the_unsandboxed_one() -> None:
    """Face 1 New offered 'balanced'/'strict' (which do not exist) and omitted
    'generated-default' (the only secure profile that does)."""
    choices = {c["profile"]: c for c in profile_choices()}
    assert choices["generated-default"]["sandboxed"] is True
    assert choices["trusted-local"]["sandboxed"] is False
    assert choices["trusted-local"]["requires_acknowledgement"] is True
    assert "NO SANDBOX" in choices["trusted-local"]["label"]
    assert choices["trusted-local"]["warning"]
    # The secure profile is offered before the unsandboxed one.
    order = [c["profile"] for c in profile_choices()]
    assert order.index("generated-default") < order.index("trusted-local")


#: Surfaces an operator uses to choose an execution policy.
_OPERATOR_SURFACES = (
    "generator_trunk/face1_new/run_ui.py",
    "generator_trunk/intake/face1.html",
    "generator_trunk/intake/serve_face1.py",
)


@pytest.mark.parametrize("phantom", ["balanced", "strict"])
def test_no_operator_surface_offers_a_nonexistent_profile(phantom: str) -> None:
    """Every surface must render the canonical registry. A surface that builds
    its own list can reintroduce a profile the engine cannot resolve.

    Matched as a profile-map entry (``"balanced": "…"``) rather than as a bare
    word, so JavaScript's ``"use strict"`` is not a false positive.
    """
    import re
    entry = re.compile(rf'["\']{phantom}["\']\s*:\s*["\']')
    for name in _OPERATOR_SURFACES:
        path = REPO_ROOT / name
        if not path.is_file():
            continue
        assert not entry.search(path.read_text(encoding="utf-8")), \
            f"{name} offers a profile {phantom!r} that policy.PROFILES cannot resolve"


def test_the_python_surfaces_render_the_canonical_registry() -> None:
    """Stronger than absence-of-phantoms: the list must come FROM the registry,
    so it cannot drift again."""
    text = (REPO_ROOT / "generator_trunk/face1_new/run_ui.py").read_text(encoding="utf-8")
    assert "profile_choices" in text


def test_every_operator_surface_offers_the_secure_profile() -> None:
    from intake.serve_face1 import _ping_payload
    advertised = {item["profile"] for item in _ping_payload()["execution_policy_profiles"]}
    assert advertised == set(PROFILES)
    text = (REPO_ROOT / "generator_trunk/face1_new/run_ui.py").read_text(encoding="utf-8")
    assert "profile_choices" in text


def test_face1_old_does_not_maintain_a_second_profile_list() -> None:
    text = (REPO_ROOT / "generator_trunk/intake/face1.html").read_text(encoding="utf-8")
    assert 'CH_PROFILE=[""]' in text
    assert "execution_policy_profiles" in text
    assert 'CH_PROFILE=["","generated-default"' not in text


# ---------------------------------------- F3: resume cannot add or lose trust --
def _auth(profile: str, **overrides) -> ExecutionAuthorization:
    policy = resolve_policy(profile)
    base = dict(profile=profile, origin="reviewed-checked-in", acknowledgement="reviewed",
                sandboxed=not is_trusted_profile(policy),
                policy_id=policy_id(policy), policy_hash=policy_hash(policy))
    base.update(overrides)
    return ExecutionAuthorization(**base)


def test_resume_accepts_the_identical_policy() -> None:
    verify_same_policy(_auth("generated-default"), _auth("generated-default"))


@pytest.mark.parametrize("field,value", [
    ("origin", "locally-authored"),
    ("acknowledgement", "a different decision"),
    ("sandboxed", False),
    ("policy_id", "ep-tampered0000"),
])
def test_resume_refuses_any_authorization_identity_change(field: str, value) -> None:
    recorded = _auth("generated-default")
    verify = dataclasses.replace(recorded, **{field: value})
    with pytest.raises(PolicyIdentityError, match="authorization decision|execution policy"):
        verify_same_policy(recorded, verify)


def test_resume_refuses_a_sandboxed_to_unsandboxed_downgrade() -> None:
    """The concrete mechanism the audit found: a secure run resuming into the
    legacy unsandboxed Python path."""
    with pytest.raises(PolicyIdentityError) as excinfo:
        verify_same_policy(_auth("generated-default"), _auth("trusted-local"))
    assert "downgrade" in str(excinfo.value)
    assert "refused" in str(excinfo.value)


def test_resume_refuses_any_policy_change_not_only_downgrades() -> None:
    with pytest.raises(PolicyIdentityError):
        verify_same_policy(_auth("trusted-local"), _auth("generated-default"))


def test_resume_refuses_a_run_with_no_recorded_authorization() -> None:
    """An unauthorized older run must be re-run, not retro-authorized by a
    resume that assumes whatever policy is convenient now."""
    with pytest.raises(PolicyIdentityError, match="records no execution authorization"):
        verify_same_policy(None, _auth("generated-default"))


def test_authorization_round_trips_through_the_manifest() -> None:
    original = _auth("generated-default")
    restored = authorization_from_dict(json.loads(json.dumps(original.to_dict())))
    assert restored == original


@pytest.mark.parametrize("bad", [
    None, {}, {"profile": "trusted-local"}, "trusted-local",
    {**_auth("trusted-local").to_dict(), "sandboxed": "false"},
    {**_auth("trusted-local").to_dict(), "profile": None},
])
def test_a_malformed_authorization_record_is_not_accepted(bad) -> None:
    assert authorization_from_dict(bad) is None


# -------------------------- F3: the sandbox check cannot be omitted by a caller --
def test_required_backend_is_derived_from_the_policy_not_the_call_site() -> None:
    assert required_backend(resolve_policy("generated-default")) == "container"
    assert required_backend(resolve_policy("networked-api-probe")) == "container"
    assert required_backend(resolve_policy("trusted-local")) is None
    with pytest.raises(PolicyError, match="resolved execution policy is required"):
        required_backend(None)


def test_executor_summary_checker_cannot_be_called_without_a_policy(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        _require_executor_summary(tmp_path / "executor-summary.json")


def test_a_secure_run_whose_executor_recorded_no_sandbox_fails(tmp_path: Path) -> None:
    summary = tmp_path / "executor-summary.json"
    summary.write_text(json.dumps({"processed": 4, "sandbox_backend": "local"}), encoding="utf-8")
    with pytest.raises(StageError, match="refusing a secure run"):
        _require_executor_summary(summary, resolve_policy("generated-default"))


def test_a_secure_run_with_the_container_backend_passes(tmp_path: Path) -> None:
    summary = tmp_path / "executor-summary.json"
    summary.write_text(json.dumps({"processed": 4, "sandbox_backend": "container"}),
                       encoding="utf-8")
    assert _require_executor_summary(summary, resolve_policy("generated-default"))["processed"] == 4


def test_every_executor_summary_check_passes_the_resolved_policy() -> None:
    """Regression guard for the exact defect: `_run` passed the requirement and
    both resume sites silently omitted it. The signature now takes the policy, so
    a bare call is the bug this test catches."""
    import ast
    source = (REPO_ROOT / "generator_trunk/bundle/cli.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
             and n.func.id == "_require_executor_summary"]
    assert calls, "expected the launcher to verify the executor summary"
    for call in calls:
        assert len(call.args) >= 2 or call.keywords, (
            f"_require_executor_summary at line {call.lineno} does not pass the resolved policy, "
            f"so a secure run there would never be verified against its sandbox backend")


# ------------------------------------------- F6: documentation self-consistency --
def test_documentation_does_not_call_trusted_local_the_default() -> None:
    """The overview claimed fail-closed security while naming the unsandboxed
    profile as the default; that contradiction is why F1 survived so long."""
    for name in ("README.md", "docs/01_EXECUTIVE_OVERVIEW.md", "docs/10_SECURITY_AND_SANDBOXING.md",
                 "docs/README.md"):
        text = (REPO_ROOT / name).read_text(encoding="utf-8").lower()
        for claim in ("default `trusted-local`", "`trusted-local` is the current cli/config default",
                      "default is `trusted-local`", "trusted-local is the default"):
            assert claim not in text, f"{name} still calls trusted-local the default"


def test_documented_trusted_local_commands_include_the_required_evidence() -> None:
    """A command that names trusted-local but omits either new flag is now a
    copy-paste failure and trains users to work around the gate."""
    docs = [REPO_ROOT / "README.md", REPO_ROOT / "QUICKSTART.md"]
    docs += list((REPO_ROOT / "docs").glob("*.md"))
    docs += list((REPO_ROOT / "generator_trunk").rglob("*.md"))
    docs += [REPO_ROOT / "generator_trunk/usecases/ml_eval_surrogate/ml_eval_surrogate.toml"]
    marker = "--execution-policy-profile trusted-local"
    for path in docs:
        if path.name == "32_EXECUTION_SAFETY_AUDIT.md" or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        start = 0
        while (index := text.find(marker, start)) >= 0:
            window = text[index:index + 500]
            assert "--candidate-origin" in window, path
            assert "--acknowledge-trusted-local" in window, path
            start = index + len(marker)


def test_current_docs_do_not_describe_the_retired_port_only_grpc_bind() -> None:
    for path in (REPO_ROOT / "docs").glob("*.md"):
        if path.name == "32_EXECUTION_SAFETY_AUDIT.md":  # historical finding, preserved verbatim
            continue
        text = path.read_text(encoding="utf-8").lower()
        assert "receiver binds by port" not in text, path
        assert "receiver currently binds by port" not in text, path
