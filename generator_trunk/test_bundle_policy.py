"""STEP 27 targeted tests: execution policy parse/validation, profiles, id/hash,
secret-free effective view, and the Handoff v2 integration check.

No DB / no full run (per STEP 27 minimal checks).
"""
import dataclasses
import json
from pathlib import Path

import pytest

from bundle.handoff import (handoff_from_dict, handoff_to_dict, validate_against_json_schema)
from bundle.models import SchemaError
from bundle.policy import (
    ExecutionPolicy, KNOWN_BACKENDS, NetworkMode, POLICY_SCHEMA, PROFILES, PolicyError,
    effective_policy_view, policy_from_dict, policy_hash, policy_id, policy_to_dict,
    resolve_policy, validate_policy, with_env_allowlist, with_network_allowlist,
)

HERE = Path(__file__).resolve().parent
_SECRET_RE_FIELDS = ("PASSWORD", "TOKEN", "SECRET", "CREDENTIAL", "API_KEY")


# ------------------------------------ profiles ------------------------------- #
def test_three_named_profiles_present_and_valid():
    assert set(PROFILES) == {"trusted-local", "generated-default", "networked-api-probe"}
    # STEP 28 wired enforcement: the secure profiles name the "container" backend
    # (rootless Docker), only trusted-local stays "local" (explicit opt-in).
    expected_backend = {"trusted-local": "local",
                        "generated-default": "container",
                        "networked-api-probe": "container"}
    for name in PROFILES:
        p = resolve_policy(name)            # resolves + validates
        assert p.profile == name
        assert p.schema == POLICY_SCHEMA
        assert p.backend == expected_backend[name]
        assert p.backend in KNOWN_BACKENDS
        assert p.allowed_interpreters       # non-empty
        validate_policy(p)


def test_generated_default_has_no_secrets_and_no_arbitrary_network():
    p = resolve_policy("generated-default")
    assert p.trusted is False
    assert p.network is NetworkMode.DISABLED          # no arbitrary network
    assert "*" not in p.env_allowlist                  # not the inherit-all wildcard
    for name in p.env_allowlist:                       # no credential-shaped env names
        up = name.upper()
        assert not any(s in up for s in _SECRET_RE_FIELDS), name


def test_secure_profiles_allow_java_and_javac_interpreters():
    # STEP 29: the shared secure backend runs Python AND Java candidates, so the
    # secure profiles must explicitly permit java/javac -- the Java Executor
    # fails closed on a policy that does not (SandboxedJavaRunner.decideExecMode).
    for name in ("generated-default", "networked-api-probe", "trusted-local"):
        interps = set(resolve_policy(name).allowed_interpreters)
        assert {"python", "java", "javac"} <= interps, (name, interps)


def test_networked_api_probe_is_narrow_allowlist_no_secrets():
    p = resolve_policy("networked-api-probe")
    assert p.trusted is False
    assert p.network is NetworkMode.ALLOWLIST
    assert p.network_allowlist and "*" not in p.network_allowlist


def test_trusted_local_is_the_only_permissive_profile():
    t = resolve_policy("trusted-local")
    assert t.trusted is True
    assert t.network is NetworkMode.UNRESTRICTED


# --------------------------------- id / hash --------------------------------- #
def test_policy_id_and_hash_are_stable_and_roundtrip():
    p = resolve_policy("generated-default")
    pid, ph = policy_id(p), policy_hash(p)
    assert pid.startswith("ep-") and len(ph) == 64
    # round-trip through dict must preserve identity
    p2 = policy_from_dict(policy_to_dict(p))
    assert policy_id(p2) == pid and policy_hash(p2) == ph


def test_distinct_policies_have_distinct_ids():
    a = resolve_policy("trusted-local")
    b = resolve_policy("generated-default")
    assert policy_id(a) != policy_id(b)
    # a one-field change changes the id
    c = dataclasses.replace(b, timeout_seconds=b.timeout_seconds + 1)
    assert policy_id(c) != policy_id(b)


# ------------------------------ parse / validation --------------------------- #
def test_unknown_field_rejected():
    d = dict(policy_to_dict(resolve_policy("generated-default")))
    d["totally_unknown"] = 1
    with pytest.raises(PolicyError):
        policy_from_dict(d)


def test_unknown_or_incompatible_version_rejected():
    d = dict(policy_to_dict(resolve_policy("generated-default")))
    d["schema"] = "bundle.execution-policy/v2"
    with pytest.raises(SchemaError):
        policy_from_dict(d)
    d["schema"] = "not-a-schema"
    with pytest.raises(SchemaError):
        policy_from_dict(d)


def test_secure_profile_rejects_credential_env_name():
    base = resolve_policy("generated-default")
    bad = dataclasses.replace(base, env_allowlist=tuple(base.env_allowlist) + ("DB_PASSWORD",))
    with pytest.raises(PolicyError):
        validate_policy(bad)


def test_secure_profile_rejects_env_wildcard():
    base = resolve_policy("generated-default")
    with pytest.raises(PolicyError):
        validate_policy(dataclasses.replace(base, env_allowlist=("*",)))


def test_secure_profile_rejects_unrestricted_network():
    base = resolve_policy("generated-default")
    with pytest.raises(PolicyError):
        validate_policy(dataclasses.replace(base, network=NetworkMode.UNRESTRICTED))


def test_allowlist_network_requires_nonempty_allowlist():
    base = resolve_policy("networked-api-probe")
    with pytest.raises(PolicyError):
        validate_policy(dataclasses.replace(base, network_allowlist=()))


def test_bad_scalar_values_rejected():
    base = resolve_policy("trusted-local")
    with pytest.raises(PolicyError):
        validate_policy(dataclasses.replace(base, timeout_seconds=0))
    with pytest.raises(PolicyError):
        validate_policy(dataclasses.replace(base, backend="wormhole"))
    with pytest.raises(PolicyError):
        validate_policy(dataclasses.replace(base, allowed_interpreters=()))
    with pytest.raises(PolicyError):
        validate_policy(dataclasses.replace(base, stdout_max_bytes=0))


def test_unknown_profile_fails_closed():
    with pytest.raises(PolicyError):
        resolve_policy("does-not-exist")


# --------- STEP 28: operator-configured network allowlist override ----------- #
def test_with_network_allowlist_overrides_and_revalidates():
    base = resolve_policy("networked-api-probe")
    p = with_network_allowlist(base, ["api-server", "api-server:8000"])
    assert p.network is NetworkMode.ALLOWLIST
    assert p.network_allowlist == ("api-server", "api-server:8000")
    validate_policy(p)                                  # still a valid policy
    assert policy_id(p) != policy_id(base)              # the override changes identity
    # and it round-trips through the persisted dict unchanged
    assert effective_policy_view(p)["policy"]["network_allowlist"] == ["api-server", "api-server:8000"]


def test_with_network_allowlist_rejects_non_allowlist_profiles():
    for name in ("trusted-local", "generated-default"):
        with pytest.raises(PolicyError):
            with_network_allowlist(resolve_policy(name), ["api-server"])


def test_with_network_allowlist_rejects_empty_targets():
    with pytest.raises(PolicyError):
        with_network_allowlist(resolve_policy("networked-api-probe"), [])


# ----- STEP 30: candidate-env passthrough folded into env_allowlist ----------- #
def test_with_env_allowlist_adds_names_and_rejects_secrets():
    base = resolve_policy("generated-default")
    p = with_env_allowlist(base, ["TRYOUT_URL"])
    assert "TRYOUT_URL" in p.env_allowlist
    validate_policy(p)
    assert policy_id(p) != policy_id(base)                 # the addition changes identity
    # a credential-shaped name fails closed (validate_policy forbids it on a secure profile)
    for secret in ("DB_TOKEN", "API_KEY", "X_SECRET"):
        with pytest.raises(PolicyError):
            with_env_allowlist(base, [secret])


# --------------------------- effective view (no secrets) --------------------- #
def test_effective_view_is_secret_free_and_json_serializable():
    for name in PROFILES:
        v = effective_policy_view(resolve_policy(name))
        assert set(v) == {"id", "sha256", "policy"}
        blob = json.dumps(v)                       # must serialize
        low = blob.lower()
        # no secret VALUE could ever be here -- the model holds env var NAMES only;
        # assert no obvious credential token leaked into the rendered view.
        assert "password=" not in low and '"password"' not in low
        assert "secret-" not in low


# ------------------------- Handoff v2 integration check ---------------------- #
def _minimal_handoff_dict(policy_ref):
    return {
        "protocol": "bundle.handoff/v2",
        "run_id": "step27-itest",
        "language": "python",
        "candidate_transport": "loose-files",
        "candidate_count": 1,
        "id_format": "<combi>_<opt>_<j>",
        "sources": [{"kind": "dir", "path": "/tmp/src"}],
        "result_target": {"host": "127.0.0.1", "port": 5432, "database": "db", "user": "postgres"},
        "result_schema_mode": "placeholders=14",
        "verdict_mode": "FW_VAR",
        "shift": 1,
        "execution_policy_ref": policy_ref,
    }


def test_handoff_carries_policy_ref_and_roundtrips():
    pid = policy_id(resolve_policy("generated-default"))
    h = handoff_from_dict(_minimal_handoff_dict(pid))     # parses + validates
    assert h.execution_policy_ref == pid
    # round-trip through the wire dict keeps the ref
    again = handoff_from_dict(handoff_to_dict(h))
    assert again.execution_policy_ref == pid


def test_persist_handoff_policy_stamps_manifest_file_and_writes_sidecar(tmp_path):
    """STEP 27 Fix 1: the launcher must write execution_policy_ref into the
    PERSISTED manifest the (separate-process) Executor reads -- not just an
    in-memory object -- and drop execution_policy.json next to it (the Executor's
    sha256 source). Validates the real `_persist_handoff_policy`."""
    from bundle.cli import _persist_handoff_policy
    hoff = tmp_path / "handoff"; hoff.mkdir()
    manifest = hoff / "manifest.json"
    # a manifest as the Reader leaves it today: execution_policy_ref unset/null
    manifest.write_text(json.dumps({"protocol": "bundle.handoff/v2", "run_id": "r",
                                    "execution_policy_ref": None}), encoding="utf-8")
    pol = resolve_policy("generated-default")
    _persist_handoff_policy(manifest, policy_id(pol), effective_policy_view(pol))
    on_disk = json.loads(manifest.read_text(encoding="utf-8"))
    assert on_disk["execution_policy_ref"] == policy_id(pol)        # no longer null on disk
    sidecar = json.loads((hoff / "execution_policy.json").read_text(encoding="utf-8"))
    assert sidecar["id"] == policy_id(pol) and len(sidecar["sha256"]) == 64


def test_handoff_with_policy_ref_validates_against_schema_doc():
    pid = policy_id(resolve_policy("networked-api-probe"))
    schema = json.loads((HERE / "bundle-handoff-v2.schema.json").read_text(encoding="utf-8"))
    wire = handoff_to_dict(handoff_from_dict(_minimal_handoff_dict(pid)))
    validate_against_json_schema(wire, schema)            # raises on any violation
    assert wire["execution_policy_ref"] == pid
