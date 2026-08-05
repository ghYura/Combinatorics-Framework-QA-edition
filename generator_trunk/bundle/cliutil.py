"""Shared CLI helpers: layered-config resolution and spec loading.
"""
from __future__ import annotations
import dataclasses
from pathlib import Path
from .budgets import BudgetLimits
from .config import BundleConfig, ConfigError, resolve_config
from .errors import PreflightError
from .policy import (
    PolicyError,
    authorize_execution,
    effective_policy_view,
    policy_hash,
    policy_id,
    validate_policy,
    with_env_allowlist,
    with_network_allowlist,
)
from .stages import fg


# Sentinel meaning "this argparse flag was not given on the command line" —
# deliberately distinct from a resolved value of `None` (e.g.
# `--budget-monetary-cost none` legitimately resolves to `None`, "no limit").
# Every flag that feeds `BundleConfig`'s CLI layer below defaults to `_UNSET`:
# an *unspecified* flag must fall through to the environment/config-file/
# default layers in `resolve_config`, not silently shadow them with whatever
# argparse's own "convenience" default happened to be. (That silent shadowing
# — e.g. `--main-port` always carrying `5433` into the CLI layer regardless of
# whether the operator typed it — was exactly the bug: BUNDLE_MAIN_DB_PORT/
# --config-file could never actually take effect.)
_UNSET = object()

# Every argparse destination whose *explicitly-given* value becomes part of
# `BundleConfig`'s CLI layer (highest precedence), and the field it sets.
# Combines the brand-new `--<bundleconfig-key>` flags with the pre-existing
# flags that already represented the same setting under a different name
# (--main-port/--results-port/--analyzer/--mode/--budget-*/...) — unifying
# *all* of them behind one typed, layered resolution is the actual point of
# STEP 13 ("Убрать конфигурационную логику из случайных мест").
_CLI_ARG_TO_CONFIG_KEY = {
    "main_db_host": "main_db_host", "main_db_user": "main_db_user", "main_db_password": "main_db_password",
    "results_db_host": "results_db_host", "results_db_user": "results_db_user",
    "results_db_password": "results_db_password",
    "scratch_root": "scratch_root", "core_jar": "core_jar", "reader_jar": "reader_jar",
    "core_props": "core_props", "reader_props": "reader_props", "py_executor": "py_executor",
    "java_executor_jar": "java_executor_jar", "java_jars_dir": "java_jars_dir",
    "java_cmd": "java_cmd", "javac_cmd": "javac_cmd", "python_cmd": "python_cmd",
    "executor_compiler": "executor_compiler",
    "unleash_initial_productivity_power": "unleash_initial_productivity_power",
    "core_timeout": "core_timeout_seconds", "reader_timeout": "reader_timeout_seconds",
    "executor_timeout": "executor_timeout_seconds",
    "sandbox_policy": "sandbox_policy",
    "execution_policy_profile": "execution_policy_profile",
    "candidate_origin": "candidate_origin",
    "trusted_local_acknowledgement": "trusted_local_acknowledgement",
    "sandbox_network_allowlist": "sandbox_network_allowlist",
    "sandbox_candidate_env": "sandbox_candidate_env",
    "executor_tolerate_outcomes": "executor_tolerate_outcomes",
    "candidate_sink": "candidate_sink", "grpc_host": "grpc_host", "grpc_port": "grpc_port",
    "executor_pool_size": "executor_pool_size",
    "seed_output": "seed_output", "exploration_floor": "exploration_floor",
    "min_winner_support": "min_winner_support",
    "main_port": "main_db_port", "results_port": "results_db_port",
    "analyzer": "analyzer_goals", "mode": "run_mode",
    "budget_mandatory_rows": "budget_mandatory_rows", "budget_final_candidates": "budget_final_candidates",
    "budget_disk_bytes": "budget_disk_bytes", "budget_inodes": "budget_inodes",
    "budget_wall_time_seconds": "budget_wall_time_seconds", "budget_requests": "budget_external_requests",
    "budget_monetary_cost": "budget_monetary_cost", "budget_warn_fraction": "budget_warn_fraction",
    "repeat": "repeat_each_candidate", "repeat_policy": "repeat_policy",
    "repeat_scope": "repeat_scope", "repeat_environments": "repeat_environments",
}


def _resolve_execution_policy(cfg: BundleConfig):
    """Resolve + validate this run's execution policy from the typed config
    (STEP 27/28). Starts from the named profile, then folds in the operator's
    configured network-allowlist *targets* (``sandbox_network_allowlist``, layered
    CLI > env > config file) so a networked-api-probe run's target container
    reaches the *persisted* policy (run.json + execution_policy.json) the Executor
    enforces -- closing the gap where only a hand-built sidecar could carry it.

    Phase 02 / audit F1: the profile is no longer defaulted. `authorize_execution`
    refuses an unset profile, and refuses ``trusted-local`` without an eligible
    origin classification and a non-empty operator reason. The returned
    authorization is persisted in the run manifest and re-checked by `resume`.

    Returns ``(policy, effective_policy_view, authorization)``. Fails closed with a
    `ConfigError` (a `BundleError`, so `report_and_exit` renders it concisely) when
    targets are set on a non-allowlist profile or any entry is invalid."""
    try:
        policy, authorization = authorize_execution(
            cfg.execution_policy_profile,
            origin=cfg.candidate_origin,
            acknowledgement=cfg.trusted_local_acknowledgement)
    except PolicyError as exc:
        raise ConfigError(str(exc))
    targets = cfg.network_allowlist_targets()          # validated; ConfigError on a bad entry
    if targets:
        try:
            policy = with_network_allowlist(policy, targets)
        except PolicyError as exc:
            raise ConfigError(f"sandbox_network_allowlist: {exc}")
    # STEP 30: fold operator-passed candidate env NAMEs (e.g. TRYOUT_URL) into the
    # persisted policy's env_allowlist so the sandbox forwards exactly these; the
    # values are exported to the Executor in `_run`. A credential-shaped name
    # fails closed here (with_env_allowlist -> validate_policy).
    env_names = list(cfg.candidate_env_passthrough())  # validated; ConfigError on a bad/secret name
    if env_names:
        try:
            policy = with_env_allowlist(policy, env_names)
        except PolicyError as exc:
            raise ConfigError(f"sandbox_candidate_env: {exc}")
    validate_policy(policy)
    # The allowlist/env folds above change the policy document, so the recorded
    # identity must be the FINAL one -- otherwise resume would compare against a
    # hash no run ever executed under.
    authorization = dataclasses.replace(
        authorization, policy_id=policy_id(policy), policy_hash=policy_hash(policy))
    return policy, effective_policy_view(policy), authorization


def _resolve_bundle_config(a):
    """Build the typed `BundleConfig` (STEP 13) — precedence CLI > environment
    (`BUNDLE_<KEY>`) > config file (`--config-file`) > defaults
    (`config.resolve_config`). The CLI layer is exactly the flags in
    `_CLI_ARG_TO_CONFIG_KEY` that were *explicitly given* (i.e. whose argparse
    value is not the `_UNSET` sentinel) — an unspecified flag falls through to
    the layers beneath it instead of shadowing them with a baked-in default.
    Returns ``(config, sources)``; raises `ConfigError` (a `BundleError`) on
    an invalid type or an unknown key, naming both the key and its source
    layer (action 7)."""
    cli = {}
    for arg_name, key in _CLI_ARG_TO_CONFIG_KEY.items():
        val = getattr(a, arg_name, _UNSET)
        if val is not _UNSET:
            cli[key] = val
    return resolve_config(cli=cli, config_file=(getattr(a, "config_file", "") or None))


def _with_db(a):
    if not a.db:
        tomls = sorted(Path(a.spec_dir).glob("*.toml"))
        a.db = tomls[0].stem if tomls else "bundle_run"
    return a


def _load_one_spec(spec_dir):
    tomls = sorted(Path(spec_dir).glob("*.toml"))
    if len(tomls) != 1:
        raise PreflightError(f"expected exactly one .toml in {spec_dir}, found {len(tomls)}")
    try:
        return fg.load_spec(tomls[0]), tomls[0]
    except ValueError as exc:
        # invalid spec (e.g. a missing operand / undeclared sheet caught by parse_spec)
        # rejects gracefully — never let it crash mid-command or write a partial artifact.
        raise PreflightError(f"spec {tomls[0].name} is invalid: {exc}") from exc


def _budget_limits_from_config(cfg: BundleConfig) -> BudgetLimits:
    """STEP 13 action 3 folds the STEP-12 budget ceilings into `BundleConfig`
    (layered CLI > environment > config file > defaults, like everything else)
    — this is the single place that turns the typed config's flat
    `budget_*` fields back into the `BudgetLimits` shape `evaluate_budgets`
    expects. Replaces the old `_budget_limits_from_args`, which read
    `a.budget_*` directly off argparse and so never saw `BUNDLE_BUDGET_*`/
    `--config-file` overrides."""
    return BudgetLimits(
        mandatory_rows=cfg.budget_mandatory_rows,
        final_candidates=cfg.budget_final_candidates,
        disk_bytes=cfg.budget_disk_bytes,
        inodes=cfg.budget_inodes,
        wall_time_seconds=cfg.budget_wall_time_seconds,
        external_requests=cfg.budget_external_requests,
        monetary_cost=cfg.budget_monetary_cost,
        warn_fraction=cfg.budget_warn_fraction,
    )
