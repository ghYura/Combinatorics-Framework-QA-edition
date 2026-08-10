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

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, fields, MISSING
from pathlib import Path
from typing import Any, Mapping, Optional, Tuple

from .errors import BundleError

# A single sandbox network-allowlist target (STEP 28): a container name / hostname
# with an optional ``:port``. Kept strict so an operator-supplied value cannot
# smuggle anything odd into the persisted policy or a `docker network connect`.
_NETWORK_TARGET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*(:[0-9]{1,5})?$")

# STEP 30: a candidate-env passthrough NAME (e.g. TRYOUT_URL) — a plain env-var
# identifier. A credential-shaped name is refused so a sandboxed candidate can
# never be handed a secret (mirrors policy._SECRET_ENV_RE).
_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SECRET_ENV_NAME_RE = re.compile(r"(PASSWORD|PASSWD|SECRET|TOKEN|CREDENTIAL|API_?KEY|KEY)", re.IGNORECASE)

# Plan-1 Phase 2: per-candidate repeat-policy parameters (docs/24 §3). Validated by
# `BundleConfig.validate_repeat`; consumed by `bundle.counts.count_plan`.
_REPEAT_POLICIES = frozenset({"disperse", "local", "nested"})
_REPEAT_SCOPES = frozenset({"all", "metrics"})

# Every key `BundleConfig` knows about, with its scalar type — used both to
# coerce raw strings (env / config-file values arrive untyped) and to reject
# unknown keys at any layer with a message naming the key and its source
# (STEP 13 action 7: "Validation errors должны указывать key и source layer").
_FIELD_KINDS: "Mapping[str, type]" = {
    "main_db_host": str, "main_db_port": int, "main_db_user": str, "main_db_password": str,
    "results_db_host": str, "results_db_port": int, "results_db_user": str, "results_db_password": str,
    "scratch_root": str, "core_jar": str, "reader_jar": str, "core_props": str, "reader_props": str,
    "py_executor": str, "java_executor_jar": str, "java_jars_dir": str,
    "java_cmd": str, "javac_cmd": str, "python_cmd": str,
    "executor_compiler": str,
    "core_timeout_seconds": float, "reader_timeout_seconds": float, "executor_timeout_seconds": float,
    "analyzer_goals": str, "run_mode": str, "sandbox_policy": str,
    "execution_policy_profile": str, "sandbox_network_allowlist": str,
    "trusted_local_acknowledgement": str, "candidate_origin": str,
    "sandbox_candidate_env": str,
    "executor_tolerate_outcomes": str,
    "budget_warn_fraction": float,
    "candidate_sink": str, "shard_max_records": int, "shard_max_bytes": int,
    "grpc_host": str, "grpc_port": int, "grpc_bind_host": str,
    "executor_pool_size": int,
    "seed_output": bool, "exploration_floor": float, "min_winner_support": int,
    "unleash_initial_productivity_power": bool,
    "repeat_each_candidate": int, "repeat_policy": str, "repeat_scope": str,
    "repeat_environments": int,
}

# STEP 13 action 3 names "budgets" as one of the things layered config must
# cover (STEP 12's `BudgetLimits` ceilings) — these fields are `Optional`
# numbers where `None`/`"none"`/`"unlimited"` means "no limit configured for
# this dimension" (evaluated as OK, never an implicit zero ceiling; mirrors
# `cli._optional_number`). Coerced separately from `_FIELD_KINDS` because
# "valid value" includes `None` here, unlike every plain scalar field.
_OPTIONAL_NUMBER_FIELDS: "Mapping[str, type]" = {
    "budget_mandatory_rows": int, "budget_final_candidates": int,
    "budget_disk_bytes": int, "budget_inodes": int,
    "budget_wall_time_seconds": float, "budget_external_requests": int,
    "budget_monetary_cost": float,
}

_ALL_KEYS = frozenset(_FIELD_KINDS) | frozenset(_OPTIONAL_NUMBER_FIELDS)

ENV_PREFIX = "BUNDLE_"

# STEP 14 action 3: passwords must come only from environment / a protected
# config reference / interactive input — never a literal in versioned source.
# This untracked, gitignored, workspace-relative file is exactly such a
# "protected config reference": if present it fills *only* the fields whose
# in-source default is the empty "unconfigured" sentinel (today, the two
# password fields), so an existing local dev setup keeps working without the
# operator having to export env vars on every run, while a fresh checkout with
# no such file falls through to `preflight`'s fail-closed missing-credential
# error. Never created/written by Bundle itself.
DEV_DEFAULTS_PATH = Path(__file__).resolve().parent.parent / ".bundle-dev-defaults.json"


class ConfigError(BundleError):
    """A config value could not be resolved/typed — message names both the
    offending key and the layer (default/config file/environment/CLI) that
    set it, per STEP 13 action 7."""


@dataclass(frozen=True)
class BundleConfig:
    """Single typed source of Bundle runtime configuration (STEP 13).

    Before this, configuration was scattered across hardcoded module
    constants (``stages.CORE_JAR``/``READER_PROPS``/...), ad-hoc argparse
    defaults (``--main-port 5433``), and inline literals (``host="127.0.0.1"``,
    a hardcoded credential in `stage_sieve`/the old module-level `process.PGPW`). `BundleConfig`
    gathers all of it — DB host/port/user/database policy, scratch root,
    artifact/JAR paths, Java/Python commands, timeouts, Analyzer goals/run
    mode, and sandbox policy (placeholder for STEP 28's backend selection) —
    behind one typed, layered, redaction-aware surface. Resolve it with
    `resolve_config`; never construct ad-hoc dicts of these values elsewhere.

    Empty-string fields (``scratch_root``, ``*_jar``, ``*_props``,
    ``py_executor``, ``java_jars_dir``, ``python_cmd``) mean "use the existing derived/auto
    default" — see `BundleConfig.scratch_for`/`stages` — so existing
    deployments keep working unchanged (action 6: "Не менять component
    defaults без необходимости").

    STEP 14: ``main_db_password``/``results_db_password`` default to ``""``
    ("not configured") rather than carrying a literal credential in source —
    `resolve_config` may still fill them from an untracked local dev-defaults
    file (`_dev_defaults_layer`, never committed) so an existing local dev
    setup keeps working without extra steps; `preflight` fails closed with a
    named-key error if they remain empty after every layer is applied.
    """
    main_db_host: str = "127.0.0.1"
    main_db_port: int = 5433
    main_db_user: str = "postgres"
    main_db_password: str = ""
    results_db_host: str = "127.0.0.1"
    results_db_port: int = 5432
    results_db_user: str = "postgres"
    results_db_password: str = ""
    scratch_root: str = ""
    core_jar: str = ""
    reader_jar: str = ""
    core_props: str = ""
    reader_props: str = ""
    py_executor: str = ""
    java_executor_jar: str = ""
    java_jars_dir: str = ""
    java_cmd: str = "java"
    javac_cmd: str = "javac"
    python_cmd: str = ""
    # Java Executor compiler backend selector, passed to MainWatch as
    # -Dfw.exec.compiler=<value> (before -jar). "" = MainWatch's own default
    # (adaptive). Explicit values pin the backend: adaptive | janino | ecj | javac.
    executor_compiler: str = ""
    core_timeout_seconds: float = 600.0
    reader_timeout_seconds: float = 600.0
    executor_timeout_seconds: float = 3600.0
    analyzer_goals: str = ""
    run_mode: str = "verdict"
    sandbox_policy: str = "sandbox"
    # STEP 32: candidate output transport the Reader stage requests.
    #   "loose-files" (default) — one file per candidate (byte-for-byte the legacy path).
    #   "sharded"               — pack candidates into compressed *.fwshard containers
    #                             (ShardSink) to cut inode pressure for L-class runs.
    #   "grpc"    (2026-07-03) — stream candidates LIVE to the Java Executor's gRPC
    #                             ingestion server (no on-disk candidate corpus). The
    #                             launcher starts the Executor (-grpcPort) BEFORE the
    #                             Reader and adopts it in the executor stage; requires
    #                             --lang java and the trusted-local execution policy
    #                             (the manifest-less Executor runs with the explicit
    #                             -Dfw.exec.trusted=true legacy opt-in).
    # shard_max_records/shard_max_bytes are the per-shard rollover thresholds.
    candidate_sink: str = "loose-files"
    shard_max_records: int = 1000
    shard_max_bytes: int = 8 * 1024 * 1024
    # gRPC transport endpoint: the Executor binds -grpcPort <grpc_port>; the Reader
    # streams to <grpc_host>:<grpc_port> (reader.out.grpc.target).
    grpc_host: str = "127.0.0.1"
    grpc_port: int = 50061
    # Audit F5: the interface the Java Executor's candidate receiver BINDS. The
    # Reader's target (`grpc_host`) is where it connects; that never constrained
    # where the receiver listened. This channel is plaintext and unauthenticated,
    # so `validate_grpc_bind_host` refuses a wildcard or non-loopback value.
    grpc_bind_host: str = "127.0.0.1"
    # Executor pool (2026-07-04): N MainWatch processes, each owning ONE of N candidate
    # dirs the Reader round-robins into (the LEGACY reader.out.outZipDirPathList CSV +
    # LooseFileSink dir rotation — multi-dir was always in the Reader's design; this
    # finally puts an executor behind each dir). The launcher is the orchestrator:
    # it spawns, journals, cancels and reconciles the members — no external
    # orchestrator is introduced. v1 constraints (fail-closed in preflight):
    # Java candidates, loose-files transport, K=1, trusted-local flow via manifest.
    executor_pool_size: int = 1
    # BundleSeed feedback loop. seed_output is deliberately default-off so the
    # legacy single-run path stays unchanged unless the operator opts in or the
    # iterate driver forces it on.
    seed_output: bool = False
    exploration_floor: float = 0.25
    min_winner_support: int = 5
    # Do you care about exponential combinatorics explosion (guess not)?
    # When True, the budget gate stops BLOCKING (hard ceilings become advisory
    # warnings) and an X (extreme) classification no longer needs --allow-extreme:
    # Core runs at full generative power. Default False keeps the limiter on for
    # everyone else; the run manifest records that the limiter was lifted.
    unleash_initial_productivity_power: bool = False
    # STEP 27: which execution-policy profile (bundle/policy.py) every candidate
    # runs under -- "what is this candidate allowed to do", separate from the
    # `sandbox_policy` backend selector above.
    #
    # Phase 02 / audit F1: this is deliberately EMPTY. It used to default to
    # "trusted-local", so an operator who said nothing silently got unsandboxed
    # host execution. There is now no default to fall back to: `policy.
    # authorize_execution` refuses an unset profile on the run path, while
    # `bundle plan` (side-effect-free) needs no policy at all. Defaulting to
    # `generated-default` instead was considered and rejected -- it requires a
    # rootless container runtime, so the common case would fail on hosts without
    # one and train operators to reach for trusted-local to get moving.
    execution_policy_profile: str = ""
    # Required when `execution_policy_profile` is the unsandboxed trusted-local:
    # the operator's own reason, and their classification of where the candidate
    # source came from. Both are persisted in the run manifest. The origin is
    # never read from the specification -- a scenario that could declare itself
    # trusted would defeat the gate.
    trusted_local_acknowledgement: str = ""
    candidate_origin: str = ""
    # STEP 28: comma-separated target container name(s)/host(s) a networked-api-
    # probe candidate is permitted to reach. Layered like everything else (CLI >
    # env BUNDLE_SANDBOX_NETWORK_ALLOWLIST > config file > default) and resolved
    # into the *persisted* execution policy (`cli._resolve_execution_policy` ->
    # `policy.with_network_allowlist`), so the Executor's sandbox attaches exactly
    # these to the candidate's dedicated --internal network. Empty (default) =>
    # the profile's own allowlist is used unchanged. Only meaningful with the
    # networked-api-probe profile; setting it on any other profile fails closed.
    sandbox_network_allowlist: str = ""
    # STEP 30: NAME=VALUE pairs to pass into sandboxed candidates (e.g. the
    # secure-pipeline target URL TRYOUT_URL=http://secure-app:8025). Comma-
    # separated. The NAMEs are folded into the persisted execution policy's
    # env_allowlist (so the sandbox forwards exactly these and nothing else) and
    # the values are exported to the Executor. A credential-shaped NAME is refused
    # -- a secure sandbox must never receive secrets. Empty (default) => nothing
    # extra is passed.
    sandbox_candidate_env: str = ""
    # STEP 21 launcher success policy: comma-separated subset of
    # {"BROKEN", "TIMEOUT", "INFRA_FAIL"} naming infrastructure outcomes the
    # run should tolerate (downgraded from a fail-closed CRITICAL invariant to
    # a recorded WARNING). Empty (the default) means none are tolerated --
    # only DOMAIN_FAIL is an accepted outcome out of the box, matching the
    # plan's "broken/timeout/infra fail run by default". See
    # `tolerated_outcomes`/`bundle.invariants.executor_*_zero`.
    executor_tolerate_outcomes: str = ""
    # STEP-12 budget ceilings, folded into the typed/layered config (action 3).
    # `None` means "no limit configured" (see `_OPTIONAL_NUMBER_FIELDS`);
    # defaults mirror `budgets.BudgetLimits` exactly — unifying *where* these
    # values come from changes nothing about what a fresh install enforces.
    budget_mandatory_rows: "Optional[int]" = 2_000_000
    budget_final_candidates: "Optional[int]" = 2_000_000
    budget_disk_bytes: "Optional[int]" = 20 * 1024 ** 3
    budget_inodes: "Optional[int]" = 2_000_000
    budget_wall_time_seconds: "Optional[float]" = 24 * 3600
    budget_external_requests: "Optional[int]" = 2_000_000
    budget_monetary_cost: "Optional[float]" = None
    budget_warn_fraction: float = 0.5
    # Plan-1 Phase 2 (docs/24 §3): per-candidate repeat policy. K=1 (default) is the
    # legacy single-run path — zero behavioural change. `repeat_environments` defaults
    # to 0 = "unset"; it is *required* (≥1) only for `nested` with K>1, and ignored for
    # local/disperse. `--workers` (stress concurrency) is NOT a substitute for it.
    repeat_each_candidate: int = 1
    repeat_policy: str = "local"
    repeat_scope: str = "metrics"
    repeat_environments: int = 0

    def validate_repeat(self) -> "Tuple[str, str, int, int]":
        """Validate the Plan-1 repeat parameters and return the normalized
        ``(policy, scope, K, E_effective)`` (docs/24 §3.0). Raises `ConfigError`
        naming the offending key on any invalid value/combination.

        ``E_effective`` is the candidate count's environment multiplier: ``E`` for
        ``nested`` with K>1, else ``1`` (``local``/``disperse`` never multiply by ``E``,
        and K=1 normalizes the whole topology away — docs/24 §3.0)."""
        k = self.repeat_each_candidate
        if not isinstance(k, int) or isinstance(k, bool) or k < 1:
            raise ConfigError(f"config key 'repeat_each_candidate': must be an integer >= 1, got {k!r}")
        policy = self.repeat_policy
        if policy not in _REPEAT_POLICIES:
            raise ConfigError(f"config key 'repeat_policy': must be one of "
                              f"{sorted(_REPEAT_POLICIES)}, got {policy!r}")
        scope = self.repeat_scope
        if scope not in _REPEAT_SCOPES:
            raise ConfigError(f"config key 'repeat_scope': must be one of "
                              f"{sorted(_REPEAT_SCOPES)}, got {scope!r}")
        e = self.repeat_environments
        if not isinstance(e, int) or isinstance(e, bool) or e < 0:
            raise ConfigError(f"config key 'repeat_environments': must be an integer >= 0 "
                              f"(0 = unset), got {e!r}")
        if policy == "nested" and k > 1 and e < 1:
            raise ConfigError(
                "config key 'repeat_environments': repeat_policy=nested with "
                "repeat_each_candidate>1 requires repeat_environments >= 1 "
                "(set --repeat-environments N); refusing to default it, which would "
                "under-budget candidate×env×repeat work")
        e_effective = e if (policy == "nested" and k > 1) else 1
        return (policy, scope, k, e_effective)

    def validate_seed_bias(self) -> None:
        """Validate BundleSeed bias-loop controls. These are checked during
        config resolution so an invalid exploration floor or support threshold
        fails before any DB/run side effects."""
        floor = self.exploration_floor
        if not isinstance(floor, (int, float)) or isinstance(floor, bool) or not (0 < float(floor) <= 1):
            raise ConfigError(f"config key 'exploration_floor': must satisfy 0 < value <= 1, got {floor!r}")
        support = self.min_winner_support
        if not isinstance(support, int) or isinstance(support, bool) or support < 1:
            raise ConfigError(f"config key 'min_winner_support': must be an integer >= 1, got {support!r}")

    def tolerated_outcomes(self) -> frozenset:
        """Parsed `executor_tolerate_outcomes` (STEP 21 launcher success policy):
        the set of infrastructure outcome names ("BROKEN"/"TIMEOUT"/"INFRA_FAIL")
        the operator has explicitly opted to tolerate (run still succeeds, the
        corresponding invariant is recorded as WARNING rather than CRITICAL).
        DOMAIN_FAIL is always tolerated and never appears here -- it is a
        legitimate domain verdict, not an infrastructure outcome."""
        return frozenset(name.strip().upper()
                         for name in self.executor_tolerate_outcomes.split(",")
                         if name.strip())

    def validate_grpc_bind_host(self) -> str:
        """Return the receiver bind host, refusing anything not loopback.

        Audit F5: the direct Reader->Executor candidate channel is plaintext and
        unauthenticated. A wildcard bind (`0.0.0.0`, `::`, empty) or any routable
        address would put an unauthenticated code-ingestion socket on the network,
        so this fails closed rather than warning. It is deliberately the *only*
        place that decision lives, so relaxing it later requires touching one
        function with one reason.
        """
        host = (self.grpc_bind_host or "").strip()
        if not host:
            raise ConfigError(
                "grpc_bind_host is empty. The gRPC candidate receiver must bind an explicit "
                "loopback interface (127.0.0.1 or ::1); an empty value means the wildcard.")
        if host in ("localhost", "127.0.0.1", "::1", "[::1]"):
            return host
        if host in ("0.0.0.0", "::", "*"):
            raise ConfigError(
                f"grpc_bind_host={host!r} is the wildcard address. The direct candidate gRPC "
                f"channel is plaintext and unauthenticated, so it must listen on loopback only.")
        try:
            import ipaddress
            if ipaddress.ip_address(host).is_loopback:
                return host
        except ValueError:
            pass
        raise ConfigError(
            f"grpc_bind_host={host!r} is not a loopback address. The direct candidate gRPC channel "
            f"has neither TLS nor peer authentication and is not a remote transport; keep it on "
            f"127.0.0.1 (or ::1) and use host firewall/interface isolation.")

    def network_allowlist_targets(self) -> "Tuple[str, ...]":
        """Parsed + validated `sandbox_network_allowlist` (STEP 28): the target
        container names/aliases a networked-api-probe candidate may reach. Each
        comma-separated entry is a hostname/container-name with an optional
        ``:port``; an invalid entry fails closed with a `ConfigError` naming it.
        Empty list when nothing is configured (the profile's own allowlist
        stands)."""
        out = []
        for raw in self.sandbox_network_allowlist.split(","):
            entry = raw.strip()
            if not entry:
                continue
            if not _NETWORK_TARGET_RE.match(entry):
                raise ConfigError(
                    f"config key 'sandbox_network_allowlist': invalid target {entry!r} "
                    f"(expected a container name/host with an optional :port, e.g. "
                    f"'api-server' or 'api-server:8000')")
            out.append(entry)
        return tuple(out)

    def candidate_env_passthrough(self) -> "dict[str, str]":
        """Parsed + validated `sandbox_candidate_env` (STEP 30): the NAME=VALUE
        environment a sandboxed candidate should receive (e.g. its target URL).
        Comma-separated; each NAME must be a plain env identifier and must NOT be
        credential-shaped (a secure sandbox never gets secrets) -- both fail
        closed with a `ConfigError`. Empty dict when nothing is configured."""
        out: "dict[str, str]" = {}
        for raw in self.sandbox_candidate_env.split(","):
            entry = raw.strip()
            if not entry:
                continue
            if "=" not in entry:
                raise ConfigError(f"config key 'sandbox_candidate_env': entry {entry!r} "
                                  f"must be NAME=VALUE")
            name, value = entry.split("=", 1)
            name = name.strip()
            if not _ENV_NAME_RE.match(name):
                raise ConfigError(f"config key 'sandbox_candidate_env': invalid env name {name!r}")
            if _SECRET_ENV_NAME_RE.search(name):
                raise ConfigError(f"config key 'sandbox_candidate_env': refusing credential-shaped "
                                  f"env name {name!r} -- a sandboxed candidate must never receive secrets")
            out[name] = value
        return out

    def scratch_for(self, db_name: str) -> Path:
        """STEP 14 action 4: `/mnt/F` is a *configured* optional scratch
        candidate, not an implicit default — the prior `os.access("/mnt/F", ...)`
        auto-probe is gone. The default is always `/tmp/fw_work/<db>`; an
        operator who wants `/mnt/F` (or anything else) sets `scratch_root`
        explicitly (CLI `--scratch-root`, `BUNDLE_SCRATCH_ROOT`, or config
        file), e.g. `scratch_root=/mnt/F/fw_work`."""
        root = self.scratch_root or "/tmp/fw_work"
        return Path(root) / db_name

    def resolved_python_cmd(self) -> str:
        return self.python_cmd or sys.executable


def _coerce_optional_number(key: str, raw: Any, layer: str) -> "Optional[float | int]":
    kind = _OPTIONAL_NUMBER_FIELDS[key]
    if raw is None:
        return None
    if isinstance(raw, str) and raw.strip().lower() in ("", "none", "unlimited"):
        return None
    if isinstance(raw, kind) and not isinstance(raw, bool):
        return raw
    try:
        return kind(raw)
    except (TypeError, ValueError) as exc:
        raise ConfigError(
            f"config key '{key}' from {layer}: expected {kind.__name__} or "
            f"'none'/'unlimited' (no limit), got {raw!r} ({exc})") from exc


def _coerce_bool(key: str, raw: Any, layer: str) -> bool:
    """Coerce a layered boolean. Env/config-file values arrive as strings, and
    ``bool('false')`` is truthy in Python -- so parse the usual truthy/falsey
    tokens explicitly and reject anything else with a named-key error."""
    if isinstance(raw, bool):
        return raw
    s = str(raw).strip().lower()
    if s in ("1", "true", "yes", "on"):
        return True
    if s in ("0", "false", "no", "off", ""):
        return False
    raise ConfigError(
        f"config key '{key}' from {layer}: expected a boolean (true/false), got {raw!r}")


def _coerce(key: str, raw: Any, layer: str) -> Any:
    if key in _OPTIONAL_NUMBER_FIELDS:
        return _coerce_optional_number(key, raw, layer)
    kind = _FIELD_KINDS[key]
    if kind is bool:
        return _coerce_bool(key, raw, layer)
    if isinstance(raw, kind) and not isinstance(raw, bool):
        return raw
    try:
        if kind is int:
            return int(str(raw).strip())
        if kind is float:
            return float(str(raw).strip())
        return str(raw)
    except (TypeError, ValueError) as exc:
        raise ConfigError(
            f"config key '{key}' from {layer}: expected {kind.__name__}, got {raw!r} ({exc})") from exc


def _check_known(keys, layer: str) -> None:
    unknown = sorted(set(keys) - _ALL_KEYS)
    if unknown:
        raise ConfigError(f"{layer}: unknown config key(s) {unknown}")


def _defaults_layer() -> dict:
    out = {}
    for f in fields(BundleConfig):
        out[f.name] = f.default if f.default is not MISSING else f.default_factory()
    return out


def _dev_defaults_layer(defaults: "Mapping[str, Any]") -> dict:
    """STEP 14 action 3/7: an optional, untracked, gitignored, workspace-
    relative file (`DEV_DEFAULTS_PATH`) supplying fallback values *only* for
    fields whose in-source default is the empty "unconfigured" sentinel
    (currently the password fields). Absent/unreadable/malformed -> no
    fallback, and `preflight` reports the missing credential by name. Never
    promotes a value that would override an actual in-source default —
    this is strictly "fill the gap left by removing the literal", not a
    second config-file mechanism."""
    if not DEV_DEFAULTS_PATH.exists():
        return {}
    try:
        data = json.loads(DEV_DEFAULTS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, Mapping):
        return {}
    return {k: v for k, v in data.items()
            if k in _ALL_KEYS and defaults.get(k) == "" and isinstance(v, str) and v != ""}


def _config_file_layer(path: "Path | str | None") -> dict:
    if not path:
        return {}
    p = Path(path)
    layer = f"config file ({p})"
    if not p.exists():
        raise ConfigError(f"{layer}: not found")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ConfigError(f"{layer}: invalid JSON ({exc})") from exc
    if not isinstance(data, Mapping):
        raise ConfigError(f"{layer}: top-level JSON value must be an object")
    _check_known(data.keys(), layer)
    return dict(data)


def _env_layer(env: Mapping[str, str]) -> dict:
    out = {}
    for name in _ALL_KEYS:
        env_key = ENV_PREFIX + name.upper()
        if env_key in env:
            out[name] = env[env_key]
    return out


def resolve_config(*, cli: "Optional[Mapping[str, Any]]" = None,
                   env: "Optional[Mapping[str, str]]" = None,
                   config_file: "Path | str | None" = None) -> "Tuple[BundleConfig, dict]":
    """Resolve a typed `BundleConfig`, layering sources with explicit
    precedence ``CLI > environment > config file > defaults`` (STEP 13
    action 2 — later layers in the list win).

    ``cli`` carries only *explicitly given* overrides (never argparse's
    blanket defaults — those would always "win" and erase the layering).
    ``env`` defaults to ``os.environ``; keys are read as ``BUNDLE_<FIELD>``
    upper-cased. ``config_file`` is an optional JSON object of the same keys.

    Returns ``(config, sources)`` where ``sources`` maps each field name to
    the layer that ultimately set it (``"default"``, ``"dev-defaults file"``,
    ``"config file (<path>)"``, ``"environment"``, ``"CLI"``) — used to build
    the resolved-config artifact and to make precedence independently
    inspectable/testable.
    """
    env = os.environ if env is None else env
    cli = dict(cli or {})
    _check_known(cli.keys(), "CLI")

    defaults = _defaults_layer()
    layers = (
        ("default", defaults),
        ("dev-defaults file", _dev_defaults_layer(defaults)),
        (f"config file ({Path(config_file)})" if config_file else "config file", _config_file_layer(config_file)),
        ("environment", _env_layer(env)),
        ("CLI", cli),
    )
    values: dict = {}
    sources: dict = {}
    for layer_name, layer_values in layers:
        for key, raw in layer_values.items():
            values[key] = _coerce(key, raw, layer_name)
            sources[key] = layer_name
    cfg = BundleConfig(**values)
    cfg.validate_seed_bias()
    return cfg, sources


def config_to_dict(config: BundleConfig, sources: "Optional[Mapping[str, str]]" = None) -> dict:
    """Plain-dict view of a resolved config, ready for `jsonio.write_json_atomic`
    (which redacts ``*password*``-shaped keys before anything reaches disk —
    action 4: "Создать redacted resolved config artifact"). Optionally annotates
    each key with the layer that set it, for an auditable resolved-config report."""
    out = {f.name: getattr(config, f.name) for f in fields(BundleConfig)}
    if sources is not None:
        return {"values": out, "sources": dict(sources)}
    return out
