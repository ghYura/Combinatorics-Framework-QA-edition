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

"""Execution policy (STEP 27): the versioned, hashable description of WHAT a
generated candidate is allowed to do at execution time -- separated from the
Executor code that will (STEP 28+) actually enforce it.

STEP 27 introduced the *model*, three named *profiles*, parse/validate, and a
stable id/hash. STEP 28 wired the enforcement: the secure profiles now name
backend ``"container"`` and the Python Executor's ``sandbox`` module turns these
limits into a real rootless-Docker sandbox (read-only root, tmpfs scratch,
pids/mem/cpu/timeout, env allowlist, network none/internal). Because every
executor run resolves and records an explicit, validated policy (its id/hash
goes into the handoff and the run manifest), policy violations are *detectable*
and the effective policy is inspectable without secrets (the model carries
env-var *names*, never their values).

Acceptance (STEP 27):
  * Every executor run has a policy   -> `_run` resolves one via `resolve_policy`
                                          and records `effective_policy_view` in
                                          the run manifest + handoff ref.
  * Unknown policy field/version rejected -> `policy_from_dict` (unknown key ->
                                          PolicyError; bad version -> SchemaError).
  * Effective policy visible w/o secrets  -> `effective_policy_view` (no secret
                                          values exist in the model to leak).
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Mapping, Sequence

from .models import require_schema, to_dict

POLICY_SCHEMA = "bundle.execution-policy/v1"

# Backends the model knows about. STEP 28 wired up real enforcement: the secure
# profiles now name "container" (rootless Docker, the Python Executor's
# sandbox.ContainerBackend); "bubblewrap" is the daemonless alternative; only
# "trusted-local" stays "local" (explicit unsandboxed opt-in).
KNOWN_BACKENDS = ("local", "bubblewrap", "systemd-run", "container")


class PolicyError(ValueError):
    """An execution policy failed validation: unknown field, out-of-range value,
    unknown profile, or a secure profile asking for something it must not get
    (a credential-shaped env var, or arbitrary network)."""


class NetworkMode(str, Enum):
    DISABLED = "disabled"          # no network at all
    ALLOWLIST = "allowlist"        # only the hosts named in network_allowlist
    UNRESTRICTED = "unrestricted"  # any network -- trusted profiles only


# Env-var NAMES that look credential-bearing. A profile that does not explicitly
# allow secrets (`trusted=False`) must not name any of these in its env
# allowlist -- that is how "generated-default не получает secrets" (action 4)
# becomes a *validated*, detectable property rather than a convention.
_SECRET_ENV_RE = re.compile(r"(PASSWORD|PASSWD|SECRET|TOKEN|CREDENTIAL|API_?KEY|KEY)", re.IGNORECASE)


@dataclass(frozen=True)
class ExecutionPolicy:
    """Versioned, hashable execution policy (STEP 27 action 1)."""

    schema: str
    profile: str
    backend: str
    timeout_seconds: float
    cpu_seconds: "float | None"
    memory_bytes: "int | None"
    max_processes: "int | None"
    fs_read: Sequence[str]            # allowed read roots ('/' = unrestricted; '{scratch}' = the run tree)
    fs_write: Sequence[str]           # allowed write roots
    network: NetworkMode
    network_allowlist: Sequence[str]  # host[:port] entries, only when network == ALLOWLIST
    env_allowlist: Sequence[str]      # env var NAMES the candidate may inherit ('*' = all; trusted only)
    stdout_max_bytes: int
    stderr_max_bytes: int
    allowed_interpreters: Sequence[str]
    # Trusted profile: may inherit the full environment (secrets included) and use
    # unrestricted network. False = a secure profile, where `validate_policy`
    # forbids credential-shaped env names, the '*' env wildcard, and unrestricted
    # network. (Named `trusted`, not `*secret*`, so the redactor -- which nukes any
    # key containing 'secret'/'token'/... -- never clobbers this flag in run.json.)
    trusted: bool = False


_ALLOWED_KEYS = frozenset(f.name for f in dataclasses.fields(ExecutionPolicy))


# ----------------------------------- validation ------------------------------ #
def validate_policy(p: ExecutionPolicy) -> None:
    """Reject a structurally- or semantically-invalid policy (action 5).

    Raises :class:`PolicyError` (or :class:`~bundle.models.SchemaError` on a bad
    version); never mutates *p*. Both hand-built profiles and externally-parsed
    documents go through here, so there is no path to an unvalidated policy.
    """
    require_schema(p.schema, POLICY_SCHEMA)  # SchemaError on unknown/incompatible version
    if not p.profile or not p.profile.strip():
        raise PolicyError("profile must not be empty")
    if p.backend not in KNOWN_BACKENDS:
        raise PolicyError(f"unknown backend {p.backend!r}; known: {KNOWN_BACKENDS}")
    if not (isinstance(p.timeout_seconds, (int, float)) and p.timeout_seconds > 0):
        raise PolicyError(f"timeout_seconds must be a positive number, got {p.timeout_seconds!r}")
    for name, val in (("cpu_seconds", p.cpu_seconds), ("memory_bytes", p.memory_bytes),
                      ("max_processes", p.max_processes)):
        if val is not None and not (isinstance(val, (int, float)) and val > 0):
            raise PolicyError(f"{name} must be a positive number when set, got {val!r}")
    if p.stdout_max_bytes <= 0 or p.stderr_max_bytes <= 0:
        raise PolicyError("stdout_max_bytes/stderr_max_bytes must be > 0")
    if not p.allowed_interpreters:
        raise PolicyError("allowed_interpreters must not be empty")
    if not isinstance(p.network, NetworkMode):
        raise PolicyError(f"network must be a NetworkMode, got {p.network!r}")
    if p.network is NetworkMode.ALLOWLIST and not p.network_allowlist:
        raise PolicyError("network=allowlist requires a non-empty network_allowlist")
    if p.network is not NetworkMode.ALLOWLIST and p.network_allowlist:
        raise PolicyError("network_allowlist is only meaningful when network=allowlist")
    # --- secure-profile guarantees (action 4): no secrets, no arbitrary network ---
    if not p.trusted:
        leaked = [n for n in p.env_allowlist if _SECRET_ENV_RE.search(n)]
        if leaked:
            raise PolicyError(
                f"profile {p.profile!r} does not allow secrets but its env_allowlist names "
                f"credential-shaped var(s): {leaked}")
        if "*" in p.env_allowlist:
            raise PolicyError(
                f"profile {p.profile!r} does not allow secrets but its env_allowlist is the "
                f"'*' wildcard (would inherit the full environment, secrets included)")
        if p.network is NetworkMode.UNRESTRICTED:
            raise PolicyError(
                f"profile {p.profile!r} does not allow secrets but requests unrestricted network "
                f"(arbitrary egress); use network=allowlist or disabled")


# ------------------------------- JSON (de)serialization ---------------------- #
def policy_from_dict(data: Mapping[str, Any]) -> ExecutionPolicy:
    """Parse + validate. Fail closed: an unknown field raises :class:`PolicyError`
    and an unknown/incompatible ``schema`` raises :class:`~bundle.models.SchemaError`
    -- there is no path that returns a policy :func:`validate_policy` would reject."""
    unknown = set(data) - _ALLOWED_KEYS
    if unknown:
        raise PolicyError(f"unknown execution-policy field(s): {sorted(unknown)}")
    schema = require_schema(data.get("schema", ""), POLICY_SCHEMA)
    p = ExecutionPolicy(
        schema=schema,
        profile=data["profile"],
        backend=data["backend"],
        timeout_seconds=float(data["timeout_seconds"]),
        cpu_seconds=data.get("cpu_seconds"),
        memory_bytes=data.get("memory_bytes"),
        max_processes=data.get("max_processes"),
        fs_read=tuple(data.get("fs_read", ())),
        fs_write=tuple(data.get("fs_write", ())),
        network=NetworkMode(data["network"]),
        network_allowlist=tuple(data.get("network_allowlist", ())),
        env_allowlist=tuple(data.get("env_allowlist", ())),
        stdout_max_bytes=int(data["stdout_max_bytes"]),
        stderr_max_bytes=int(data["stderr_max_bytes"]),
        allowed_interpreters=tuple(data.get("allowed_interpreters", ())),
        trusted=bool(data.get("trusted", False)),
    )
    validate_policy(p)
    return p


def policy_to_dict(p: ExecutionPolicy) -> Mapping[str, Any]:
    """Plain JSON-able dict (enums -> values, tuples -> lists)."""
    return to_dict(p)


def _canonical_json(p: ExecutionPolicy) -> str:
    # Deterministic: sorted keys so the hash is stable regardless of field order.
    return json.dumps(to_dict(p), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def policy_hash(p: ExecutionPolicy) -> str:
    """Stable SHA-256 over the canonical (sorted-key) policy JSON."""
    return hashlib.sha256(_canonical_json(p).encode("utf-8")).hexdigest()


def policy_id(p: ExecutionPolicy) -> str:
    """Short, stable id derived from the hash -- the value carried in the handoff
    (`execution_policy_ref`) and the run manifest."""
    return "ep-" + policy_hash(p)[:12]


def effective_policy_view(p: ExecutionPolicy) -> Mapping[str, Any]:
    """The resolved policy as recorded in run.json / execution_policy.json.

    Secret-free by construction: the model holds env-var *names*, never values,
    and never a password/token -- so there is nothing to redact here (acceptance:
    "Effective policy visible without secrets")."""
    return {"id": policy_id(p), "sha256": policy_hash(p), "policy": to_dict(p)}


# ----------------------------------- profiles -------------------------------- #
# action 3: three named profiles. The secure two (generated-default, networked-
# api-probe) name backend="container" -- STEP 28's sandbox.ContainerBackend
# enforces these limits (read-only root, tmpfs scratch, pids/mem/cpu/timeout,
# env allowlist, network none/internal). trusted-local stays backend="local":
# an explicit, unsandboxed opt-in (sandbox.build_sandbox returns no backend).
_TRUSTED_LOCAL = ExecutionPolicy(
    schema=POLICY_SCHEMA, profile="trusted-local", backend="local",
    timeout_seconds=600.0, cpu_seconds=None, memory_bytes=None, max_processes=None,
    fs_read=("/",), fs_write=("/",),
    network=NetworkMode.UNRESTRICTED, network_allowlist=(),
    env_allowlist=("*",),
    stdout_max_bytes=16 * 1024 * 1024, stderr_max_bytes=16 * 1024 * 1024,
    allowed_interpreters=("python", "java", "javac"),
    trusted=True,
)

_GENERATED_DEFAULT = ExecutionPolicy(
    schema=POLICY_SCHEMA, profile="generated-default", backend="container",
    timeout_seconds=30.0, cpu_seconds=15.0, memory_bytes=512 * 1024 * 1024, max_processes=64,
    fs_read=("{scratch}",), fs_write=("{scratch}",),
    network=NetworkMode.DISABLED, network_allowlist=(),
    env_allowlist=("PATH", "LANG", "LC_ALL", "TZ", "HOME", "TMPDIR"),
    stdout_max_bytes=1024 * 1024, stderr_max_bytes=1024 * 1024,
    # STEP 29: the secure backend runs BOTH Python and Java candidates, so the
    # shared secure profile must explicitly permit java/javac -- the Java Executor
    # (SandboxedJavaRunner.decideExecMode) refuses to run a Java candidate under a
    # policy whose allowed_interpreters does not name "java"+"javac" (fail-closed).
    allowed_interpreters=("python", "java", "javac"),
    trusted=False,
)

# Like generated-default but permitted narrow, allowlisted egress to a probe
# target (still no secrets, still no arbitrary network). On the container backend
# (STEP 28) each NON-loopback network_allowlist entry names the *target container*
# the candidate may reach: the Executor attaches exactly those to the candidate's
# dedicated --internal network (sandbox.ContainerBackend.provision/attach_target),
# and nothing else is reachable. The default below is the loopback placeholder
# (no external egress, no target attached); operators set network_allowlist to
# their local target container name(s) -- the local-only, inter-container model.
_NETWORKED_API_PROBE = replace(
    _GENERATED_DEFAULT,
    profile="networked-api-probe",
    network=NetworkMode.ALLOWLIST,
    network_allowlist=("127.0.0.1",),
)

PROFILES: "Mapping[str, ExecutionPolicy]" = {
    p.profile: p for p in (_TRUSTED_LOCAL, _GENERATED_DEFAULT, _NETWORKED_API_PROBE)
}

# Catch a malformed built-in profile at import time rather than mid-run.
for _p in PROFILES.values():
    validate_policy(_p)


def with_network_allowlist(policy: ExecutionPolicy, targets: Sequence[str]) -> ExecutionPolicy:
    """Return a validated copy of *policy* whose ``network_allowlist`` is replaced
    by *targets* (STEP 28).

    This is how an operator's configured target containers (Bundle config/CLI
    ``sandbox_network_allowlist`` -> ``cli._resolve_execution_policy``) reach the
    *persisted* policy: a networked-api-probe run names the concrete container(s)
    its candidates may connect to, the Executor's sandbox attaches exactly those
    to the candidate's dedicated ``--internal`` network, and nothing else is
    reachable. Fails closed (:class:`PolicyError`) when *policy* is not in
    ALLOWLIST mode (targets are meaningless for a disabled/unrestricted network),
    when *targets* is empty, or when the resulting policy is otherwise invalid."""
    if policy.network is not NetworkMode.ALLOWLIST:
        raise PolicyError(
            f"network allowlist targets {list(targets)} given, but profile "
            f"{policy.profile!r} is network={policy.network.value}, not 'allowlist' "
            f"(use the networked-api-probe profile)")
    if not targets:
        raise PolicyError("network allowlist targets must be non-empty")
    p = replace(policy, network_allowlist=tuple(targets))
    validate_policy(p)
    return p


def with_env_allowlist(policy: ExecutionPolicy, extra_names: Sequence[str]) -> ExecutionPolicy:
    """Return a validated copy of *policy* with *extra_names* added to
    ``env_allowlist`` (STEP 30: operator-passed candidate env such as
    ``TRYOUT_URL``).

    Order-preserving and de-duplicated. :func:`validate_policy` runs on the
    result, so for a non-trusted (secure) profile a credential-shaped name fails
    closed -- secrets can never be folded into a sandboxed candidate's
    environment this way."""
    if not extra_names:
        return policy
    merged = tuple(dict.fromkeys(tuple(policy.env_allowlist) + tuple(extra_names)))
    p = replace(policy, env_allowlist=merged)
    validate_policy(p)
    return p


def resolve_policy(profile_name: str) -> ExecutionPolicy:
    """Resolve a named profile to its (validated) :class:`ExecutionPolicy`.

    Fails closed on an unknown profile name -- this is the "policy validation
    before execution" entry point the launcher calls before any stage runs."""
    try:
        p = PROFILES[profile_name]
    except KeyError:
        raise PolicyError(
            f"unknown execution-policy profile {profile_name!r}; known profiles: {sorted(PROFILES)}")
    validate_policy(p)
    return p


# ------------------------------- execution authorization --------------------- #
# Phase 02 / audit finding F1. Before this, `execution_policy_profile` defaulted
# to "trusted-local", so an operator who said nothing got unsandboxed host
# execution and no record of why that was acceptable. The model below makes the
# trust decision explicit, classified, and auditable:
#
#   * there is NO default profile -- `authorize_execution` refuses an unset one,
#     so there is nothing to silently fall back to;
#   * `trusted-local` additionally requires the operator's own origin
#     classification and a non-empty reason;
#   * an origin the threat model forbids cannot be waved through by supplying a
#     reason -- the acknowledgement authorizes a decision, it does not authorize
#     running generated code on the host.

#: Where candidate source came from. The OPERATOR declares this. It is never read
#: from the specification: a scenario that could declare itself trusted would
#: defeat the gate entirely (audit F1, "must not be accepted solely because an
#: untrusted scenario self-declares itself trusted").
ORIGINS: "tuple[str, ...]" = (
    "reviewed-checked-in",     # committed in this repository and reviewed
    "locally-authored",        # written by the operator in this checkout
    "generated",               # produced by a generator, model, or transformation
    "imported-untrusted",      # obtained from outside this checkout
    "network-facing",          # reaches a network target during execution
)

#: Origins for which unsandboxed host execution is a defensible operator choice.
#: Everything else must use a secure profile -- no acknowledgement can override
#: this, because the acknowledgement records a decision rather than granting a
#: permission.
TRUSTED_LOCAL_ELIGIBLE_ORIGINS: "tuple[str, ...]" = (
    "reviewed-checked-in", "locally-authored",
)

ORIGIN_UNSPECIFIED = "unspecified"


@dataclass(frozen=True)
class ExecutionAuthorization:
    """The recorded justification for one run's execution policy.

    Persisted in the run manifest so a reviewer can answer "why was this allowed
    to run this way?" from the artifact alone, and so `resume` can prove it is
    continuing the same decision rather than a new, weaker one.
    """

    profile: str
    origin: str
    acknowledgement: str          # operator's reason; required for trusted-local
    sandboxed: bool
    policy_id: str
    policy_hash: str

    def to_dict(self) -> Mapping[str, Any]:
        return {"profile": self.profile, "origin": self.origin,
                "acknowledgement": self.acknowledgement, "sandboxed": self.sandboxed,
                "policy_id": self.policy_id, "policy_hash": self.policy_hash}


def is_trusted_profile(policy: ExecutionPolicy) -> bool:
    """True when this profile executes candidates without an isolation boundary."""
    return policy.backend == "local"


def required_backend(policy: ExecutionPolicy) -> "str | None":
    """The sandbox backend a run under *policy* MUST demonstrably have used, or
    None when the profile is the explicit unsandboxed opt-in.

    Centralized so every verification site derives it the same way. The audit
    (F3) found the resume path silently omitting this check because each call
    site computed it independently.
    """
    if policy is None:
        raise PolicyError(
            "a resolved execution policy is required before an Executor summary can be "
            "verified; omitting it would silently disable the sandbox-backend check")
    if is_trusted_profile(policy):
        return None
    return policy.backend


def profile_choices() -> "tuple[Mapping[str, Any], ...]":
    """The canonical, ordered profile list every operator surface must render.

    One registry for the CLI and both UIs (audit F2): Face 1 New offered
    ``balanced``/``strict``, which do not exist, while omitting
    ``generated-default``, the only secure profile that does. A surface that
    builds its own list can make that mistake again; one that renders this
    cannot.
    """
    order = ("generated-default", "networked-api-probe", "trusted-local")
    out = []
    for name in order:
        policy = PROFILES[name]
        out.append({
            "profile": name,
            "label": {
                "generated-default": "Generated / untrusted — sandboxed (recommended)",
                "networked-api-probe": "Networked API probe — sandboxed, allowlisted egress",
                "trusted-local": "Trusted local — NO SANDBOX, host access",
            }[name],
            "sandboxed": not is_trusted_profile(policy),
            "backend": policy.backend,
            "requires_acknowledgement": is_trusted_profile(policy),
            "warning": (
                "Runs candidate code on this host with your full environment, filesystem and "
                "network. Only for reviewed code you control. Requires an explicit reason and "
                "an origin classification."
                if is_trusted_profile(policy) else ""),
        })
    return tuple(out)


def authorize_execution(profile_name: str, *, origin: str = "",
                        acknowledgement: str = "") -> "tuple[ExecutionPolicy, ExecutionAuthorization]":
    """Resolve a profile *and* the justification for using it. Fails closed.

    Raises :class:`PolicyError` when no profile was chosen, when the profile is
    unknown, or when ``trusted-local`` was requested without an eligible origin
    and a non-empty reason.
    """
    # =========================================================================
    # !!! BREAKING CHANGE vs. 158ab91 -- THE ONLY ONE IN PHASES 01-05 !!!
    # =========================================================================
    # Before this line existed, `--execution-policy-profile` DEFAULTED to
    # `trusted-local`, i.e. every run that omitted the flag executed candidate
    # code on the host with no sandbox, no recorded origin and no stated reason.
    # Omitting the flag now FAILS instead. That is the entire point.
    #
    # If you are reading this while an old command or CI job has stopped working:
    # it is not a bug. See docs/38_MIGRATION_PHASE_01_05.md for the one-line fix
    # and for the exact revert if you decide you want the old behaviour back.
    #
    # TO REVERT (understand what you are buying first):
    #   1. Delete this `if not (profile_name or "").strip():` block, and
    #   2. in `cli.py::_resolve_execution_policy`, pass "trusted-local" when the
    #      profile is unset instead of the empty string.
    #   Effect: unsandboxed host execution becomes reachable again by DEFAULT --
    #   silently, on every run that forgets the flag. That is precisely the
    #   condition Phase 02 audit item F1 was raised to remove, and the reason the
    #   engine now refuses rather than assumes. Reverting is a security decision,
    #   not a convenience one; make it deliberately and record why.
    # =========================================================================
    if not (profile_name or "").strip():
        raise PolicyError(
            "no execution policy selected. This run would execute candidate code, so the "
            "policy must be an explicit decision -- there is deliberately no default.\n"
            "  Generated, imported or untrusted candidates:\n"
            "      --execution-policy-profile generated-default\n"
            "  Reviewed code you control, executed on this host WITHOUT a sandbox:\n"
            "      --execution-policy-profile trusted-local \\\n"
            "        --candidate-origin reviewed-checked-in \\\n"
            "        --acknowledge-trusted-local 'why this is reviewed code'\n"
            "  (`bundle_run.py plan` needs no policy and remains available.)")
    policy = resolve_policy(profile_name.strip())
    origin = (origin or "").strip()
    acknowledgement = (acknowledgement or "").strip()
    if origin and origin not in ORIGINS:
        raise PolicyError(
            f"unknown candidate origin {origin!r}; known origins: {list(ORIGINS)}")

    if is_trusted_profile(policy):
        if not acknowledgement:
            raise PolicyError(
                f"profile {policy.profile!r} executes candidate code on this host with no "
                f"sandbox, no filesystem restriction and your full environment. It requires an "
                f"explicit, recorded reason: --acknowledge-trusted-local '<why this code is "
                f"reviewed and trusted>'")
        if not origin:
            raise PolicyError(
                f"profile {policy.profile!r} requires an explicit candidate origin so the "
                f"decision is auditable: --candidate-origin "
                f"{{{','.join(TRUSTED_LOCAL_ELIGIBLE_ORIGINS)}}}")
        if origin not in TRUSTED_LOCAL_ELIGIBLE_ORIGINS:
            raise PolicyError(
                f"candidate origin {origin!r} must not execute under {policy.profile!r}: that "
                f"profile has no isolation boundary. An acknowledgement records a decision; it "
                f"cannot authorize running {origin} code on the host. Use "
                f"--execution-policy-profile generated-default (or networked-api-probe for a "
                f"declared network target).")
    elif not origin:
        origin = ORIGIN_UNSPECIFIED

    authorization = ExecutionAuthorization(
        profile=policy.profile, origin=origin, acknowledgement=acknowledgement,
        sandboxed=not is_trusted_profile(policy),
        policy_id=policy_id(policy), policy_hash=policy_hash(policy))
    return policy, authorization


def authorization_from_dict(data: "Mapping[str, Any] | None") -> "ExecutionAuthorization | None":
    """Rebuild a recorded authorization from a run manifest, or None when the run
    predates the record (an older manifest is not retro-authorized: the caller
    decides what to do about a missing record)."""
    if not isinstance(data, Mapping):
        return None
    required = ("profile", "origin", "acknowledgement", "sandboxed", "policy_id", "policy_hash")
    if not all(k in data for k in required):
        return None
    # Do not coerce evidence. In particular bool("false") is True in Python;
    # accepting that representation would let a malformed manifest silently
    # change the recorded trust decision during resume.
    if not all(isinstance(data[k], str) for k in required if k != "sandboxed"):
        return None
    if not isinstance(data["sandboxed"], bool):
        return None
    return ExecutionAuthorization(
        profile=data["profile"], origin=data["origin"],
        acknowledgement=data["acknowledgement"], sandboxed=data["sandboxed"],
        policy_id=data["policy_id"], policy_hash=data["policy_hash"])


class PolicyIdentityError(PolicyError):
    """A resume tried to continue a run under a different execution policy."""


def verify_same_policy(recorded: "ExecutionAuthorization | None",
                       resolved: ExecutionAuthorization) -> None:
    """Fail closed when a resume would change this run's execution policy.

    Audit F3: `resume` never re-resolved or compared the policy, and its executor
    verification omitted the required-backend check, so a secure run could resume
    into the legacy unsandboxed path. Resume must continue the SAME decision --
    it is not an opportunity to add trust.
    """
    if recorded is None:
        raise PolicyIdentityError(
            "this run's manifest records no execution authorization, so a resume cannot prove "
            "it is continuing the same policy. Re-run it rather than resuming: a resume must "
            "never be the step that grants trust the original run did not have.")
    # The hash identifies the resolved policy document, but the authorization is
    # a larger decision: who classified the source, which profile was named, and
    # the exact acknowledgement for unsandboxed host execution. Hash-only
    # equality allowed a resume to change origin/reason while claiming it was the
    # same decision. Dataclass equality deliberately covers every recorded field.
    if recorded == resolved:
        return
    downgrade = recorded.sandboxed and not resolved.sandboxed
    same_policy = (recorded.policy_id == resolved.policy_id
                   and recorded.policy_hash == resolved.policy_hash)
    raise PolicyIdentityError(
        f"resume would change the {'authorization decision' if same_policy else 'execution policy'}: "
        f"the run was authorized as "
        f"{recorded.profile!r} (policy {recorded.policy_id}) and this invocation resolves to "
        f"{resolved.profile!r} (policy {resolved.policy_id}); recorded origin/reason/sandboxed="
        f"{recorded.origin!r}/{recorded.acknowledgement!r}/{recorded.sandboxed}, resolved="
        f"{resolved.origin!r}/{resolved.acknowledgement!r}/{resolved.sandboxed}."
        + (" That is a downgrade from a sandboxed profile to unsandboxed host execution and is "
           "refused outright." if downgrade else
           " Resume continues an existing decision; start a new run to change it."))
