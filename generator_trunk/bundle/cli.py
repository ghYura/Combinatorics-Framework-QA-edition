from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import sys
from pathlib import Path

from . import invariants
from . import shards
from .budgets import (
    BudgetLimits,
    blocking_checks,
    budget_check_to_dict,
    evaluate_budgets,
    warning_checks,
)
from .cancel import cancel_run
from .cleanup import CleanupError, delete_run, format_cleanup_report, scan_run
from .config import BundleConfig, config_to_dict, ConfigError, resolve_config
from .controlplane import write_plan_json
from .database import psql, sql_identifier, sql_literal
from .doctor import doctor_exit_code, doctor_report_to_dict, format_doctor_report, run_doctor
from .errors import BudgetError, BundleError, ok, PreflightError, report_and_exit, StageError
from .handoff import handoff_from_dict, HandoffError
from .policy import (
    authorization_from_dict, authorize_execution, effective_policy_view, ORIGINS,
    policy_hash, policy_id, PolicyError, PolicyIdentityError, profile_choices,
    required_backend, resolve_policy, validate_policy, verify_same_policy,
    with_env_allowlist, with_network_allowlist,
)
from .journal import NullJournal, RunJournal
from .jsonio import read_json, write_json_atomic
from .models import analysis_block, RunStatus, run_manifest_from_dict, SchemaError, StageStatus
from .resume import (
    artifacts_match,
    count_actual,
    critical_invariants_ok,
    dir_artifact,
    file_artifact,
    read_stage,
    reconcile_interrupted,
    resolve_run_layout,
    ResumeError,
    succeeded_with_invariants,
)
from .counts import count_plan
from .optional_contract import (
    contract_from_spec, OptionalContractError, verify_materialized,
)
from .resources import (
    DEFAULT_PER_CANDIDATE_SECONDS,
    estimate_resources,
    format_resource_plan,
    resource_plan_to_dict,
    ResourceThresholds,
    RunClass,
)
from .runs import create_run, file_sha256, generate_run_id
from .stages import (
    capability_gate,
    CORE_JAR,
    CORE_PROPS,
    JAVA_EXECUTOR_JAR,
    JAVA_JARS_DIR,
    PY_EXECUTOR,
    READER_JAR,
    READER_PROPS,
    SRC,
    fg,
    normalize_language,
    preflight,
    probe_java_executor_repeat_capability,
    probe_python_executor_repeat_capability,
    stage_analyzer,
    stage_core,
    stage_draw,
    stage_executor,
    stage_gen,
    stage_reader,
    stage_seed_bias,
    stage_sieve,
    stage_stress,
)

import fwseq_graph as _seq_graph                            # noqa: E402  (path set by .stages above; STEP 37)


def _optional_number(kind):
    """argparse `type=` for a budget ceiling: a number, or 'none'/'unlimited'/''
    to explicitly disable that dimension's gate (-> BudgetLimits field = None,
    evaluated as OK rather than an implicit zero ceiling)."""
    def parse(s):
        if s is None or str(s).strip().lower() in ("", "none", "unlimited"):
            return None
        return kind(s)
    return parse


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


def _stage_component_artifacts(stage: str, cfg: BundleConfig, language="python"):
    """Fingerprint the executable/config inputs that define stage compatibility."""
    generator_root = Path(fg.__file__).resolve().parent
    paths = {
        "gen": (
            ("component.fwgen", Path(fg.__file__).resolve()),
            ("component.fwgen_cli", generator_root / "fwgen_cli.py"),
        ),
        "core": (
            ("component.core_jar", Path(cfg.core_jar) if cfg.core_jar else CORE_JAR),
            ("component.core_props", Path(cfg.core_props) if cfg.core_props else CORE_PROPS),
        ),
        "sieve": (("component.sieve", generator_root / "constraints" / "sieve.py"),),
        "reader": (
            ("component.reader_jar", Path(cfg.reader_jar) if cfg.reader_jar else READER_JAR),
            ("component.reader_props", Path(cfg.reader_props) if cfg.reader_props else READER_PROPS),
        ),
        "analyzer": (
            ("component.analyzer_source", SRC / "Analyzer_trunk" / "AnalyzeKv.java"),
            ("component.analyzer_jar", SRC / "Analyzer_trunk" / "target" / "heuristic-analyzer-flatlaf-1.0.0.jar"),
        ),
    }
    if stage == "executor":
        if normalize_language(language) == "java":
            java_executor = Path(cfg.java_executor_jar) if cfg.java_executor_jar else JAVA_EXECUTOR_JAR
            java_jars = Path(cfg.java_jars_dir) if cfg.java_jars_dir else JAVA_JARS_DIR
            return (
                file_artifact("component.java_executor", java_executor),
                dir_artifact("component.java_dependency_jars", java_jars, "*.jar"),
            )
        return (file_artifact(
            "component.py_executor",
            Path(cfg.py_executor) if cfg.py_executor else PY_EXECUTOR,
        ),)
    return tuple(file_artifact(kind, path) for kind, path in paths.get(stage, ()))


def _candidate_pattern(src, ext: str) -> str:
    """STEP 32: the glob describing this run's candidate output. A "sharded" Reader
    output stores candidates inside ``*.fwshard`` containers; a "loose-files" output
    stores one ``*<ext>`` file per candidate — either directly in ``src`` or, for an
    executor POOL run (2026-07-04), one level down in the per-member round-robin dirs
    (``src/e<i>/``). Detected from disk so the forward run's artifact recording and
    resume's reuse check always agree on what to hash/count."""
    if shards.has_shards(src):
        return shards.SHARD_GLOB
    src = Path(src)
    if next(src.glob(f"*{ext}"), None) is None and next(src.glob(f"*/*{ext}"), None) is not None:
        return f"*/*{ext}"
    return f"*{ext}"


def _candidate_artifact(kind: str, src, ext: str):
    """Shard-aware ``dir_artifact`` over a run's candidate output (loose files or shards)."""
    return dir_artifact(kind, src, _candidate_pattern(src, ext))


def _record_artifacts(rec, *artifacts) -> None:
    for artifact in artifacts:
        rec.artifact(artifact)


def _require_executor_summary(path, policy):
    """STEP 30 fail-closed: the launcher REQUIRES the selected Executor's structured summary
    (`executor-summary.json`).

    It must exist and be valid JSON; and when *policy* is a secure (non-``local``)
    profile the summary's ``sandbox_backend`` MUST name that backend -- so a secure
    run that did not demonstrably go through the sandbox fails the executor stage
    rather than passing silently. Returns the parsed summary (which the caller then
    registers as the ``output.executor_summary`` artifact).

    Phase 02 / audit F3: this takes the resolved POLICY, not a pre-computed
    backend string. Previously each call site derived the requirement itself and
    both resume sites simply omitted it, so a secure run could resume without the
    sandbox ever being verified. Deriving it here makes the check impossible to
    forget at a call site."""
    backend_required = required_backend(policy)
    if not path.is_file():
        raise StageError(f"executor summary missing at {path} -- the selected Executor did not write it, "
                         f"so the sandbox backend cannot be confirmed (STEP 30 fail-closed)")
    try:
        summary = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StageError(f"executor summary at {path} is not valid JSON: {exc}")
    if backend_required is not None:
        backend = summary.get("sandbox_backend")
        if not (isinstance(backend, str) and backend_required in backend):
            raise StageError(
                f"secure execution policy (backend={backend_required!r}) but the executor summary "
                f"records sandbox_backend={backend!r} -- refusing a secure run that did not go "
                f"through the {backend_required} sandbox (STEP 30 fail-closed)")
    return summary


def _results_v2_latest_attempt_candidates(cfg, results_port, db, run_id):
    # Plan-1 Phase 3b: count canonical verdicts under the 5-column SAMPLE identity. One verdict per
    # distinct (candidate_id, repeat_idx, env_id) sample, taken at its OWN latest attempt (attempt is
    # nested inside the sample). DISTINCT ON the sample key partitions correctly -- not a single
    # global max(attempt), which mis-counts once different samples reach different attempt numbers.
    # At K=1 every row is repeat_idx=0/env_id='', so this equals the prior per-candidate count and
    # the resume "live verdicts == prior processed" check is behavior-preserving.
    run = sql_literal(run_id)
    sql = ("select count(*) from (select distinct on (candidate_id, repeat_idx, env_id) 1 "
           "from public.results_v2 where run_id=" + run
           + " order by candidate_id, repeat_idx, env_id, attempt desc) s;")
    out, rc = psql(results_port, db, sql, host=cfg.results_db_host,
                   user=cfg.results_db_user, password=cfg.results_db_password)
    return int(out) if rc == 0 and out.isdigit() else None


def _results_v2_next_attempt(cfg, results_port, db, run_id) -> int:
    sql = ("select coalesce(max(attempt),0) from public.results_v2 where run_id="
           + sql_literal(run_id) + ";")
    out, rc = psql(results_port, db, sql, host=cfg.results_db_host,
                   user=cfg.results_db_user, password=cfg.results_db_password)
    return int(out) + 1 if rc == 0 and out.isdigit() else 1


def _reset_owned_legacy_results(cfg, results_port, db) -> None:
    _, rc = psql(results_port, db, f"truncate table {sql_identifier(db)};",
                 host=cfg.results_db_host, user=cfg.results_db_user,
                 password=cfg.results_db_password)
    if rc != 0:
        raise ResumeError(f"could not reset owned legacy Results table {db!r} before Executor replay")


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


def _expected_verdicts(cfg: BundleConfig, n_cands):
    """Plan-1 count-plan V (full-verdict invocations the executor must produce): local/all makes every
    sample a full verdict ⇒ V = C·K (K results_v2 rows per candidate); every other supported repeat
    mode keeps one verdict per candidate ⇒ V = C. Drives the processed-count expectation and the
    repeat verdict invariants (docs/24 §3.1: local/all has V=I=C·K, metric_only=0)."""
    k = cfg.repeat_each_candidate
    if k > 1 and cfg.repeat_policy == "local" and cfg.repeat_scope == "all":
        return n_cands * k
    return n_cands


def _check_budgets(a, spec, cfg: BundleConfig) -> dict:
    """Budget gate (STEP 12): evaluate projected resource usage against
    configured ceilings BEFORE the run directory or any stage is created — a
    hard exceed, or an X (extreme) classification, blocks the run unless
    explicitly and accountably overridden (BudgetError -> non-zero exit,
    concise reason, no Generator/Core/DB side effects). Returns the budget
    intent dict to be recorded verbatim in the run manifest (action 4:
    "запись user intent в manifest") — recorded whether or not an override
    was needed, so 'no override was required' is itself part of the record.
    """
    cardinality_plan = fg.spec_cardinality_plan(spec)
    # Plan-1 Phase 2 (docs/24 §3-§4): build the repeat count plan, then FAIL CLOSED on K>1
    # BEFORE any run directory or stage is created — per-candidate repeats are plan-only until
    # the executor/schema phases land. `validate_repeat` raises a named ConfigError on an
    # invalid combination (e.g. nested K>1 without --repeat-environments). K=1 ⇒ topology
    # inactive ⇒ the budget below is byte-identical to the legacy estimate.
    repeat_policy, repeat_scope, repeat_k, repeat_e = cfg.validate_repeat()
    repeat_plan = count_plan(repeat_policy, repeat_scope, cardinality_plan.final, repeat_k, repeat_e)
    if repeat_k > 1:
        # Capability preflight (docs/24 §4, narrowed per Automation #37): ONLY the verified Python
        # local/metrics path runs per-candidate repeats today — it keeps one canonical verdict
        # row per candidate (no 5-column sample index) and median-aggregates the metric in the
        # Analyzer. scope=all, disperse, nested, and the Java Executor stay fail-closed.
        lang = normalize_language(getattr(a, "lang", "py"))
        # Plan-1 3c/local-all: BOTH executors run the verified local repeat path -- scope=metrics
        # (verdict once, K metric samples) and scope=all (every sample a full verdict ⇒ K results_v2
        # rows, V=C·K). disperse / nested need multi-instance / multi-environment dispatch and stay
        # fail-closed. The gate PROBES the configured artifact's advertised repeat capability below
        # (incl. the local_all flag for scope=all), so an old binary that cannot report it is rejected.
        capable = (lang in ("python", "java") and repeat_policy == "local"
                   and repeat_scope in ("metrics", "all")
                   and not bool(getattr(a, "legacy_handoff", False)))
        if not capable:
            raise BudgetError(
                f"REPEAT_K_REQUIRES_EXECUTOR_CAPABILITY: repeat_each_candidate={repeat_k} is only "
                f"executable on the local/metrics or local/all path (got lang={lang}, "
                f"repeat_policy={repeat_policy}, repeat_scope={repeat_scope}). disperse / nested are "
                f"not yet repeat-capable (they need multi-instance / multi-environment dispatch), and "
                f"--legacy-handoff cannot carry the repeat manifest. Re-run with K=1, switch to "
                f"--repeat-policy local --repeat-scope metrics|all, or use `bundle plan` for the "
                f"plan-only count/budget. (docs/24 §4)")
        try:
            capability = (probe_java_executor_repeat_capability(cfg) if lang == "java"
                          else probe_python_executor_repeat_capability(cfg))
        except StageError as exc:
            raise BudgetError(
                f"REPEAT_K_REQUIRES_EXECUTOR_CAPABILITY: configured {lang} Executor failed "
                f"the pre-run capability probe: {exc}") from exc
        if repeat_scope == "all" and not capability["repeat"].get("local_all"):
            raise BudgetError(
                f"REPEAT_K_REQUIRES_EXECUTOR_CAPABILITY: configured {lang} Executor does not advertise "
                f"the local/all repeat capability (every sample a full verdict): {capability['repeat']}")
        if repeat_k > int(capability["repeat"]["max_k"]):
            raise BudgetError(
                "REPEAT_K_REQUIRES_EXECUTOR_CAPABILITY: requested repeat_each_candidate="
                f"{repeat_k} exceeds executor max_k={capability['repeat']['max_k']}")
    # `cost_per_candidate` is the only input that turns the monetary-cost
    # dimension from "no projection" (always OK, nothing to gate) into a real
    # estimate `evaluate_budgets` can compare against `--budget-monetary-cost`.
    # Without wiring it through here, a configured monetary ceiling could never
    # actually block a run — exactly the gap flagged in review.
    resource_plan = estimate_resources(cardinality_plan, cost_per_candidate=a.cost_per_candidate,
                                       count_plan=repeat_plan)
    checks = evaluate_budgets(cardinality_plan, resource_plan, _budget_limits_from_config(cfg))
    blocking = blocking_checks(checks)
    for c in warning_checks(checks):
        print(f"  ⚠ budget warning: {c.message}")

    extreme = resource_plan.run_class == RunClass.EXTREME
    # unleash_initial_productivity_power: the limiter is OFF. The budget gate becomes
    # advisory (hard exceedances are printed, not raised) and an X classification no
    # longer needs --allow-extreme -- Core runs at full generative power. Recorded in
    # the manifest so "the limiter was lifted" is part of the run's accountable record.
    unleashed = bool(getattr(cfg, "unleash_initial_productivity_power", False))
    if unleashed:
        for c in blocking:
            print(f"  ⚡ unleashed (limiter off): would have blocked — {c.message}")
        if extreme:
            print(f"  ⚡ unleashed: X (extreme — final candidates ~{resource_plan.final_count}) "
                  f"allowed without --allow-extreme")
        return {"run_class": resource_plan.run_class.value, "allow_extreme": bool(a.allow_extreme),
                "exceeded": [c.dimension for c in blocking], "override": False, "reason": None,
                "unleash_initial_productivity_power": True}

    if extreme and not a.allow_extreme:
        raise BudgetError(
            f"run classified X (extreme — final candidates ~{resource_plan.final_count}); "
            f"start blocked until --allow-extreme is given explicitly (action 5: X always "
            f"needs its own confirmation, independent of any --override-budget). "
            f"(Or set unleash_initial_productivity_power to lift the limiter entirely.)")

    intent = {"run_class": resource_plan.run_class.value, "allow_extreme": bool(a.allow_extreme),
              "exceeded": [c.dimension for c in blocking], "override": False, "reason": None,
              "unleash_initial_productivity_power": False}
    if not blocking:
        return intent
    if not (a.override_budget and a.override_budget.strip()):
        raise BudgetError(
            "hard budget threshold(s) exceeded — blocking before Generator/Core starts:\n  "
            + "\n  ".join(c.message for c in blocking)
            + "\n  override with: --override-budget '<non-empty reason>'")
    ok(f"budget override accepted ({len(blocking)} hard threshold(s) exceeded): {a.override_budget!r}")
    intent["override"] = True
    intent["reason"] = a.override_budget
    return intent


def _build_component_inventory() -> dict:
    """STEP 42: the component version/hash inventory recorded into the run manifest.
    Fail-soft — an inventory probe error must never block creating a run."""
    try:
        from . import inventory
        return inventory.build_inventory()
    except Exception as exc:  # noqa: BLE001 — recording metadata must not fail a run
        return {"schema": "bundle.inventory/v1", "error": f"inventory unavailable: {exc}"}


def _optional_tables(cfg, main_port, db) -> "list[str]":
    """The `fw_opt*` tables Core actually materialized in this run's main DB."""
    out, rc = psql(main_port, db,
                   "select table_name from information_schema.tables "
                   "where table_schema='public' and table_name like 'fw\\_opt%';",
                   host=cfg.main_db_host, user=cfg.main_db_user, password=cfg.main_db_password)
    if rc != 0:
        raise StageError(f"could not list optional tables in {db}: {out}")
    return [line.strip() for line in out.splitlines() if line.strip()]


def _create_run_directory(a, spec, toml_path, scratch, budget_intent=None, execution_policy=None,
                          authorization=None, optional_contract=None):
    """Create the run directory + run.json/state.json before stage 1 (STEP 4).

    ``runs_root`` defaults to ``scratch/runs`` but is overridable via
    ``--runs-root`` (e.g. to keep run directories off a slow/small scratch
    disk). Stage artifacts then live under ``run_layout.root`` itself — see
    ``_run`` — so distinct run IDs get distinct artifact directories instead
    of sharing (and overwriting) the same scratch files. Default run IDs are
    auto-minted (timestamp+random) so repeat invocations of the same spec/db
    never collide; an explicit ``--run-id`` is collision-checked and fails
    closed (RunCollisionError -> BundleError -> non-zero exit) rather than
    silently reusing/overwriting a prior run's manifest.
    """
    runs_root = Path(a.runs_root) if a.runs_root else scratch / "runs"
    layout = create_run(
        runs_root=runs_root,
        db_name=a.db,
        spec_path=toml_path,
        spec_sha256=file_sha256(toml_path),
        spec_version=spec.spec_version,
        mode=a.mode,
        goals=a.analyzer,
        scratch_root=scratch,
        # STEP 38: record the formal-vs-exploratory analysis contract (mode +
        # explicit goals/weights/normalization) so the run's Pareto objectives
        # are auditable and a formal study can't be silently changed.
        analysis=analysis_block(getattr(a, "analysis_mode", "exploratory"), a.analyzer),
        # STEP 42: record the component version/hash inventory (the exact build
        # artifacts this run was produced with) in the run manifest.
        component_inventory=_build_component_inventory(),
        settings={
            "lang": a.lang,
            "main_port": a.main_port,
            "results_port": a.results_port,
            "mode": a.mode,
            "sieve": a.sieve,
            "analyzer_goals": a.analyzer,
            "analysis_mode": getattr(a, "analysis_mode", "exploratory"),   # STEP 38
            "seed_output": bool(getattr(a, "seed_output", False)),
            "seed_from": getattr(a, "seed_from", "") or "",
            "exploration_floor": getattr(a, "exploration_floor", None),
            "min_winner_support": getattr(a, "min_winner_support", None),
            "budget": budget_intent,
            # STEP 27: the resolved execution policy (id + sha256 + the policy
            # itself) -- "Policy ID/hash записывать в ... result" / "Every
            # executor run имеет policy". Secret-free (effective_policy_view).
            "execution_policy": execution_policy,
            # Phase 02 / audit F1+F3: WHY this run was allowed to execute the way
            # it did -- profile, operator origin classification, reason, and the
            # resolved policy identity. `resume` re-resolves and compares this, so
            # a resume cannot silently continue under a weaker policy.
            "execution_authorization": (authorization.to_dict() if authorization else None),
            # Audit F4: the one contract both Core and the Reader rendered their
            # optional-size properties from, so a reader of the manifest can
            # reconcile mandatory x optional without re-deriving it.
            "optional_table_contract": (optional_contract.to_dict() if optional_contract else None),
        },
        run_id=a.run_id or None,
    )
    ok(f"run '{layout.run_id}' -> {layout.manifest_path}")
    return layout


def _persist_handoff_policy(manifest_path, policy_ref, policy_view) -> None:
    """STEP 27: make the resolved execution policy reach the (separate-process)
    Executor by writing it to disk -- an in-memory overlay never would.

    Stamps ``execution_policy_ref`` into the on-disk Handoff v2 manifest (the
    Java Reader does not emit it yet) and drops the secret-free
    ``execution_policy.json`` (id + sha256 + policy) next to it. Both Executors
    read these files and record ``policy_id``/``policy_hash`` into every
    ``results_v2`` row (py_executor.read_manifest/_load_execution_policy;
    MainWatch/ResultsV2Writer on the Java side). ``write_json_atomic`` redacts
    nothing here -- the manifest carries no secret-shaped key and the policy view
    holds env-var names only."""
    mp = Path(manifest_path)
    mp.parent.mkdir(parents=True, exist_ok=True)
    if mp.is_file():
        try:
            raw = json.loads(mp.read_text(encoding="utf-8"))
            raw["execution_policy_ref"] = policy_ref
            write_json_atomic(mp, raw)
        except (OSError, json.JSONDecodeError):
            pass  # a malformed/absent manifest is the reader stage's problem, not ours
    write_json_atomic(mp.parent / "execution_policy.json", policy_view)


def _record_handoff_manifest(rec, manifest_path, run_id, n_cands, legacy_handoff):
    """Wait for/parse/validate the dual-written Handoff v2 manifest and record
    its cross-stage invariants (STEP 20) -- shared by the normal `_run` reader
    stage and `_resume_run` (STEP 24), so resuming validates the manifest
    exactly the same way a fresh run does. Returns the parsed
    :class:`HandoffManifest`, or ``None`` in the explicit ``--legacy-handoff``
    compatibility mode (which skips the manifest entirely)."""
    if legacy_handoff:
        rec.warn("--legacy-handoff: Handoff v2 manifest skipped, "
                 "Executor will run against the legacy directory handshake (STEP 20 compatibility mode)")
        return None
    try:
        raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise StageError(f"Handoff v2 manifest missing at {manifest_path} "
                         f"(pass --legacy-handoff for the explicit compatibility fallback): {exc}")
    except json.JSONDecodeError as exc:
        raise StageError(f"Handoff v2 manifest at {manifest_path} is not valid JSON: {exc}")
    try:
        manifest = handoff_from_dict(raw_manifest)
    # `handoff_from_dict` is the boundary parser: a malformed/foreign document
    # can fail at any of its steps — wrong/unparseable `protocol` (SchemaError),
    # missing keys (KeyError), bad enum values or `**`-unpacking shape
    # (ValueError/TypeError), or a structurally-valid-but-invariant-violating
    # document (HandoffError from validate_handoff). All of these are the same
    # "Handoff mismatch blocks Executor" case from STEP 20's acceptance
    # criteria — none may slip past the StageError boundary.
    except (HandoffError, SchemaError, KeyError, TypeError, ValueError) as exc:
        raise StageError(f"Handoff v2 manifest at {manifest_path} failed validation: "
                         f"{type(exc).__name__}: {exc}")
    rec.invariant(invariants.handoff_run_id_matches(manifest.run_id, run_id if run_id else manifest.run_id))
    rec.invariant(invariants.handoff_candidate_count_matches(manifest.candidate_count, n_cands))
    return manifest


def _run(a) -> None:
    # STEP 13: resolve the typed config FIRST — preflight needs it for jar
    # paths and the scratch-root policy (`cfg.scratch_for`), and every later
    # stage renders its properties from it (action 5). A `ConfigError` here
    # (unknown key / wrong type, naming the offending layer) is a `BundleError`
    # and propagates to main()'s concise report_and_exit, like PreflightError.
    cfg, cfg_sources = _resolve_bundle_config(a)
    # `cfg` is now authoritative for main/results ports, run mode, and analyzer
    # goals — mirror the resolved values back onto `a` so every existing
    # `a.main_port`/`a.results_port`/`a.mode`/`a.analyzer` use site below
    # (manifest settings, stage args, the `mode == "stress"` branch, ...) sees
    # CLI > environment > config-file > defaults rather than argparse's bare
    # per-flag default (which — before this — always "won", silently shadowing
    # BUNDLE_MAIN_DB_PORT/BUNDLE_RUN_MODE/--config-file).
    a.main_port, a.results_port, a.mode, a.analyzer = (
        cfg.main_db_port, cfg.results_db_port, cfg.run_mode, cfg.analyzer_goals)
    a.seed_output, a.exploration_floor, a.min_winner_support = (
        cfg.seed_output, cfg.exploration_floor, cfg.min_winner_support)
    # STEP 38: enforce the FORMAL analysis contract BEFORE any run directory/DB/
    # stage exists. Formal mode requires explicit Analyzer goals — otherwise the
    # run would write a `formal` manifest with empty goals and silently skip the
    # Analyzer (the `if a.analyzer:` gate), which is exactly the implicit-objective
    # degradation formal mode is meant to forbid. Fail closed here.
    if getattr(a, "analysis_mode", "exploratory") == "formal" and not a.analyzer:
        raise PreflightError(
            "--analysis-mode formal requires explicit Analyzer goals (--analyzer / "
            "BUNDLE_ANALYZER_GOALS / config analyzer_goals); a formal Pareto study cannot "
            "run with no objectives. Pass goals, e.g. --analyzer \"security_failures:max\", "
            "or use --analysis-mode exploratory.")
    if getattr(a, "seed_from", ""):
        a.sieve = True
    spec, toml_path, scratch = preflight(_with_db(a), cfg)
    a.db = a.db or spec.name
    # STEP 27: resolve + validate this run's execution policy up front ("policy
    # validation before execution") -- an unknown profile / malformed policy
    # fails closed here, before any run directory, DB, or stage exists. STEP 28
    # made the backend real: the secure profiles name "container" and the Python
    # Executor's sandbox.ContainerBackend enforces the limits, and the operator's
    # configured networked-api-probe target(s) (`sandbox_network_allowlist`) are
    # folded into the policy here so they reach the persisted execution_policy.json
    # the Executor reads. id/hash are recorded in the run manifest + handoff below.
    policy, policy_view, authorization = _resolve_execution_policy(cfg)
    if not authorization.sandboxed:
        # Audit F1/F6: an unsandboxed run must be visible in the operator's own
        # terminal, not only in a manifest they may never open.
        print(f"  ⚠ EXECUTION POLICY {policy.profile!r}: candidates run on THIS HOST with no "
              f"sandbox, full filesystem and network access, and the complete environment.")
        print(f"    origin={authorization.origin}  reason={authorization.acknowledgement!r}")
    # gRPC live transport (2026-07-03) fail-closed policy gate: the ingestion Executor
    # starts BEFORE the Reader, so no manifest (and no persisted execution_policy.json)
    # exists at its launch — it runs under the explicit -Dfw.exec.trusted=true legacy
    # opt-in. That is only sound when the operator's resolved policy IS trusted-local;
    # a container-sandboxed profile combined with the live stream must refuse, not
    # silently run unsandboxed.
    # Prompt 03 Part A: the gRPC/trusted-local constraint now lives in the one
    # capability registry as GRPC_REQUIRES_TRUSTED_LOCAL. It is re-checked here
    # because preflight ran BEFORE the policy was resolved, so the rule could not
    # fire yet (capabilities.UNDECIDED) — same rule, same message, one source.
    capability_gate(a, cfg)
    # STEP 30: export the operator-passed candidate env (e.g. TRYOUT_URL) into THIS
    # process so the Executor subprocess (stage_executor) inherits it; the sandbox
    # then forwards exactly the names the policy's env_allowlist now permits.
    for _name, _val in cfg.candidate_env_passthrough().items():
        os.environ[_name] = _val
    # STEP 12: budget gate runs BEFORE the run directory (or any stage) is
    # created — "Synthetic explosion блокируется до DB writes" / "stage не
    # начинается". A BudgetError here propagates to main()'s concise
    # report_and_exit with a non-zero exit, exactly like a PreflightError.
    # Audit F4: ONE canonical optional-table contract. Core's produced-size list
    # and the Reader's consumed-size list are both rendered from it, it is
    # validated here (R ⊆ P, sizes in range, no duplicates), and after Core the
    # required fw_opt<size> tables are verified to exist before the Reader starts.
    n_opt = sum(1 for s in spec.slots if "FW_Optional" in s.flags)
    try:
        optional_contract = contract_from_spec(spec)
    except OptionalContractError as exc:
        raise PreflightError(str(exc))
    optional_factor = optional_contract.expected_multiplier()

    budget_intent = _check_budgets(a, spec, cfg)
    run_layout = None if a.legacy_scratch else _create_run_directory(
        a, spec, toml_path, scratch, budget_intent, execution_policy=policy_view,
        authorization=authorization, optional_contract=optional_contract)
    # STEP-4 fix: stages must write into the run's own directory, not the shared
    # per-db scratch root — otherwise distinct run IDs would still collide on
    # workbooks/logs/handshake/etc. Legacy mode keeps the pre-STEP-4 behaviour.
    work = run_layout.root if run_layout else scratch
    # DRAW (auto-invoke, before Core): pause and open the link editor in the browser so the user
    # draws forbidden/required value bonds by hand; whatever they Submit REPLACES the spec's
    # constraints/params before the sieve. Drawing nothing is fine (the sieve then removes nothing).
    # `--draw` implies the sieve stage so the drawn bonds actually take effect.
    if getattr(a, "draw", False):
        a.sieve = True
        spec.constraints, spec.params = stage_draw(spec, work, cfg)
    # STEP 13 action 4: write the resolved config alongside the run/scratch —
    # `write_json_atomic` redacts every `*password*`-shaped key (see
    # `jsonio.redact`) before anything reaches disk, so the artifact is safe
    # to keep, share, or attach to a bug report.
    write_json_atomic(work / "resolved_config.json", config_to_dict(cfg, cfg_sources))
    # STEP 27: the effective execution policy is recorded in run.json settings
    # (above) and -- so the separate-process Executor can read it -- persisted
    # next to the handoff manifest once the Reader has produced it (see
    # `_persist_handoff_policy` after the reader stage below).
    # STEP 5: every stage leaves a machine-readable RUNNING -> SUCCEEDED/FAILED/
    # INTERRUPTED record (run_layout.stages_dir/<name>.json + state.json).
    # Legacy mode has no run directory to journal into, hence the no-op.
    journal = RunJournal(run_layout) if run_layout else NullJournal()
    journal.mark_run(RunStatus.RUNNING)
    core_est = fg.estimate_core_combos(spec)        # mandatory Core row count (pre-optional, pre-sieve)
    full = core_est * optional_factor
    ext = {".py": ".py", "py": ".py", ".java": ".java", "java": ".java"}.get(a.lang, ".py")
    if n_opt:
        print(f"  FW_Optional: {n_opt} sudden-action slot(s) → optional Reader path enabled; "
              f"produces={optional_contract.core_property_value()} "
              f"consumes={optional_contract.reader_property_value()} "
              f"×{optional_factor}; expected total = {full}")
    with journal.stage("gen", log_path=work / "gen.log") as rec:
        xlsx = stage_gen(a.spec_dir, work)
        _record_artifacts(rec, file_artifact("input.spec", toml_path),
                          file_artifact("output.workbook", xlsx),
                          *_stage_component_artifacts("gen", cfg))
    with journal.stage("core", log_path=work / "core.log") as rec:
        fw_final = stage_core(spec, xlsx, work, a.db, a.main_port, n_opt, cfg,
                              optional_contract=optional_contract)
        rec.count("fw_final", actual=fw_final, expected=core_est)
        # Audit F4: prove Core actually built every fw_opt<size> the Reader is
        # about to consume. A missing table would otherwise surface as an opaque
        # Reader failure or, worse, a silently short candidate corpus.
        if optional_contract.active:
            try:
                verify_materialized(optional_contract, _optional_tables(cfg, a.main_port, a.db))
            except OptionalContractError as exc:
                raise StageError(str(exc))
            rec.count("optional_multiplier", actual=optional_contract.expected_multiplier())
        _record_artifacts(rec, file_artifact("input.workbook", xlsx),
                          *_stage_component_artifacts("core", cfg))
        rec.invariant(invariants.core_count_positive(fw_final))
        invariants.enforce(rec.invariants)
    # fw_final is the ACTUAL materialized Core row count. The pre-core estimate (core_est) is only
    # approximate for rich/second-order verbs (e.g. FW_Group combinations-of-combinations), so the
    # reader.emitted_eq_expected invariant must key off the real count — otherwise a legit run where
    # the Reader correctly emits fw_final×optional candidates falsely trips the invariant. (--sieve
    # recomputes this again below from the post-sieve fw_final.)
    full = fw_final * optional_factor
    # DRAW (exact, after Core): same editor, but with EXACT live impact over the assembled space
    # (fw_final × optional combos) from the live DB. Implies --sieve; the drawn constraints are then
    # applied by the sieve stage below. (`--draw` without -exact draws before Core, offline.)
    if getattr(a, "draw_exact", False):
        a.sieve = True
        spec.constraints, spec.params = stage_draw(spec, work, cfg, exact=True,
                                                   db=a.db, main_port=a.main_port)
    if getattr(a, "seed_from", ""):
        with journal.stage("seed_bias") as rec:
            bias = stage_seed_bias(spec, work, a.db, a.main_port, a.seed_from, cfg)
            spec.constraints, spec.params = bias["constraints"], bias["params"]
            rec.count("bias_excluded_values", actual=bias.get("excluded_values"))
            rec.count("pre_bias_estimate", actual=bias.get("pre_bias_estimate"))
            rec.count("post_bias_estimate", actual=bias.get("post_bias_estimate"))
            rec.count("bias_deduped_constraints", actual=bias.get("deduped_constraints"))
            artifacts = [file_artifact("input.bundle_seed", bias.get("seed_path")),
                         file_artifact("output.bias_plan", bias.get("plan_path"))]
            if bias.get("sidecar_path"):
                artifacts.append(file_artifact("output.derived_sidecar", bias.get("sidecar_path")))
            _record_artifacts(rec, *artifacts)
            rec.invariant(invariants.bias_plan_schema_valid(True))
            rec.invariant(invariants.bias_keeps_minimum_space(
                bias.get("post_bias_estimate"), bool(bias.get("degenerate"))))
            rec.invariant(invariants.seed_sha_matches_source(
                bias.get("seed_path"), bias.get("seed_sha256")))
            invariants.enforce(rec.invariants)
        # A degenerate (CONVERGED_NO_SIGNAL) plan is journaled in bias_plan.json's
        # "status" field; the iterate driver reads it from there to stop the loop —
        # no in-memory flag is needed (and none is read anywhere).
    if a.sieve:
        pre_sieve = fw_final
        with journal.stage("sieve") as rec:
            fw_final = stage_sieve(spec, work, a.db, a.main_port, fw_final, cfg)
            rec.count("post_sieve", actual=fw_final)
            _record_artifacts(rec, *_stage_component_artifacts("sieve", cfg))
            rec.invariant(invariants.post_sieve_le_core(fw_final, pre_sieve))
            invariants.enforce(rec.invariants)
        full = fw_final * optional_factor
    run_id = run_layout.run_id if run_layout else None
    manifest = None
    manifest_path = None
    with journal.stage("reader", log_path=work / "reader.log") as rec:
        src, hs, n_cands, n_empty, manifest_path = stage_reader(
            work, a.db, a.lang, a.main_port, a.results_port, fw_final, n_opt, full, a.mode == "stress",
            cfg, run_id=run_id, legacy_handoff=a.legacy_handoff, policy_ref=policy_id(policy),
            optional_contract=optional_contract)
        rec.count("candidates", actual=n_cands, expected=full)
        # Record the manifest only after _persist_handoff_policy stamps its
        # execution_policy_ref; resume must hash the finalized on-disk document.
        _record_artifacts(rec, _candidate_artifact("output.candidates", src, ext),
                          *_stage_component_artifacts("reader", cfg))
        rec.invariant(invariants.reader_emitted_eq_expected(n_cands, full))
        rec.invariant(invariants.reader_empty_zero(n_empty))
        # STEP 20: the normal Python workflow waits for, validates, and cross-
        # checks the dual-written Handoff v2 manifest right here — a mismatch
        # is a CRITICAL invariant and blocks the Executor from ever starting.
        # Legacy fallback is an explicit, visible compatibility option only.
        # STEP 27: persist the resolved policy onto the handoff BEFORE it is
        # parsed and handed to the Executor -- stamp execution_policy_ref into the
        # manifest file and drop execution_policy.json next to it, so the
        # separate-process Executor reads the policy from disk and records its
        # id/hash into every results_v2 row (an in-memory overlay never would).
        if manifest_path:
            _persist_handoff_policy(manifest_path, policy_id(policy), policy_view)
        _record_artifacts(rec, file_artifact("output.handoff_manifest", manifest_path))
        manifest = _record_handoff_manifest(rec, manifest_path, run_id, n_cands, a.legacy_handoff)
        invariants.enforce(rec.invariants)
    if a.mode == "stress":
        with journal.stage("stress"):
            stage_stress(src, hs, a.db, a.results_port, a)
    else:
        repeat_metric_rows = None
        with journal.stage("executor") as rec:
            # STEP 30: py_executor writes its structured summary (incl. the
            # sandbox_backend it ran under) here; we register it as a run artifact.
            executor_summary = work / "executor-summary.json"
            # Both executors harvest Analyzer K=V output during their actual sandboxed
            # execution into this corpus: py_executor via --metricsFile, and (Plan-1 3c)
            # the Java MainWatch via -metricsFile. The analyzer stage reads it back; no
            # host re-run of generated candidates.
            metrics_corpus = work / "metrics.kv"
            # Plan-2 seam (2026-07-03 reconciliation): a repeat campaign (K>1) journals the
            # control-plane plan the Java dispatcher (Analyzer_trunk BundleControlPlane)
            # would ingest via Plan.fromJson — the Python planner's authoritative record of
            # this run's (policy, K, env identity, budget deadline) in the exact wire shape.
            # Config-only (no candidate bodies; the corpus is already a reader artifact).
            # Today's single-host K>1 executes IN-PROCESS in the executor (the degenerate
            # local case); this artifact is where a multi-env Executor pool takes over.
            controlplane_plan_path = None
            if cfg.repeat_each_candidate > 1:
                controlplane_plan_path = work / "controlplane_plan.json"
                write_plan_json(controlplane_plan_path, cfg, run_id=run_id)
            processed, passed, failed, broken, inserted, db_total, timeout, infra_fail, v2_counts = stage_executor(
                src, hs, a.db, a.results_port, cfg,
                manifest_path=(manifest_path if manifest else None), run_id=run_id,
                summary_path=executor_summary, metrics_path=metrics_corpus,
                language=(manifest.language if manifest else a.lang))
            rec.count("processed", actual=processed, expected=_expected_verdicts(cfg, n_cands))
            rec.count("pass", actual=passed)
            rec.count("fail", actual=failed)
            rec.count("broken", actual=broken)
            rec.count("timeout", actual=timeout)
            rec.count("infra_fail", actual=infra_fail)
            rec.count("inserted", actual=inserted, expected=passed + failed)
            # STEP 30 fail-closed: the summary MUST exist + be valid JSON, and a
            # secure (non-local) policy run MUST record its sandbox backend in it;
            # then ALWAYS register it as a run artifact (never optional).
            exec_summary = _require_executor_summary(executor_summary, policy)
            _record_artifacts(rec, file_artifact("output.executor_summary", executor_summary),
                              _candidate_artifact("input.candidates", src, ext),
                              *((file_artifact("output.controlplane_plan", controlplane_plan_path),)
                                if controlplane_plan_path else ()),
                              *_stage_component_artifacts("executor", cfg, a.lang))
            for key in ("attempted", "inserted", "already_present", "updated_selected"):
                rec.count(f"results_v2_{key}", actual=v2_counts[key])
            rec.invariant(invariants.handoff_manifest_used(manifest is not None, not a.legacy_handoff))
            rec.invariant(invariants.executor_processed_positive(processed))
            rec.invariant(invariants.executor_processed_eq_sum(processed, passed, failed, broken, timeout, infra_fail))
            # STEP 21 launcher success policy: domain failures (`failed`, i.e.
            # DOMAIN_FAIL) are an accepted outcome and gate nothing here.
            # BROKEN/TIMEOUT/INFRA_FAIL fail the run by default; an operator can
            # explicitly tolerate any subset of them via --executor-tolerate-outcomes
            # / BundleConfig.executor_tolerate_outcomes (downgrades CRITICAL ->
            # WARNING so the run still succeeds but the count stays visible and
            # recorded). `tolerated` drives all three infrastructure-outcome
            # invariants identically -- BROKEN is no longer hardcoded CRITICAL.
            tolerated = cfg.tolerated_outcomes()
            def _severity(name):
                return invariants.WARNING if name in tolerated else invariants.CRITICAL
            rec.invariant(invariants.executor_broken_zero(broken, severity=_severity("BROKEN")))
            rec.invariant(invariants.executor_timeout_zero(timeout, severity=_severity("TIMEOUT")))
            rec.invariant(invariants.executor_infra_fail_zero(infra_fail, severity=_severity("INFRA_FAIL")))
            # STEP 21: persistence policy is "every candidate WITH a domain
            # verdict is inserted" (= pass + fail), not "every processed
            # candidate" -- BROKEN/TIMEOUT/INFRA_FAIL produce no verdict to
            # insert, and a tolerated-outcomes run can legitimately have
            # processed > pass + fail. Asserting inserted == processed here
            # would fail closed on exactly the runs the policy just chose to allow.
            rec.invariant(invariants.executor_inserted_matches_policy(inserted, passed, failed))
            rec.invariant(invariants.results_v2_write_counts_consistent(
                v2_counts["attempted"], v2_counts["inserted"],
                v2_counts["already_present"], v2_counts["updated_selected"]))
            if manifest is not None:
                rec.invariant(invariants.results_v2_attempted_matches_processed(
                    v2_counts["attempted"], processed))
            rec.invariant(invariants.results_db_eq_inserted(db_total, inserted))
            # Plan-1 repeat (Python local/metrics K>1, Automation #37 step 4): tie the executor's runtime
            # tallies to the count plan — one canonical verdict per candidate (V=C), and every
            # measurement opportunity (I=C·K) accounted for as a metric row or explicit missing
            # measurement. The capability gate guarantees K>1 here is exactly Python local/metrics.
            if cfg.repeat_each_candidate > 1:
                verdicts_v = _expected_verdicts(cfg, n_cands)
                opportunities_i = n_cands * cfg.repeat_each_candidate
                rm = (exec_summary or {}).get("repeat_measurements") or {}
                repeat_metric_rows = int(rm.get("metric_rows", 0))
                rec.invariant(invariants.repeat_processed_eq_verdicts(processed, verdicts_v))
                rec.invariant(invariants.repeat_results_v2_attempted_eq_verdicts(
                    v2_counts["attempted"], verdicts_v))
                rec.invariant(invariants.repeat_metric_rows_plus_missing_eq_opportunities(
                    rm.get("metric_rows", 0), rm.get("missing_measurements", 0), opportunities_i))
            invariants.enforce(rec.invariants)
    if a.analyzer:
        with journal.stage("analyzer", log_path=work / "metrics.kv") as rec:
            seed_out = (work / "bundle_seed.json") if cfg.seed_output else None
            if seed_out is not None:
                harvested = work / "metrics.kv"
                if not harvested.exists() or harvested.stat().st_size == 0:
                    raise StageError(
                        f"seed_output=true requires a harvestable metrics corpus, but {harvested} is empty; "
                        "make candidates write their Analyzer K=V line to the injected metrics sink "
                        "(Python metrics_out or Java System.getProperty(\"fw.metrics.out\")), then rerun")
            stage_analyzer(src, work, a.analyzer, cfg=cfg,
                           mode=getattr(a, "analysis_mode", "exploratory"), corpus_count=n_cands,
                           run_id=run_id or "", harvested_metrics=work / "metrics.kv",
                           seed_out=seed_out)
            kv = work / "metrics.kv"
            metrics_lines = sum(1 for _ in kv.open(encoding="utf-8")) if kv.exists() else 0
            artifacts = [_candidate_artifact("input.candidates", src, ext),
                         file_artifact("output.metrics", kv)]
            if (work / "provenance.json").exists():
                artifacts.append(file_artifact("output.provenance", work / "provenance.json"))
            if seed_out is not None and seed_out.exists():
                artifacts.append(file_artifact("output.bundle_seed", seed_out))
                try:
                    seed_doc = json.loads(seed_out.read_text(encoding="utf-8"))
                    rec.count("seed_winners", actual=len(seed_doc.get("winners") or []))
                except (OSError, json.JSONDecodeError) as exc:
                    raise StageError(f"bundle_seed.json could not be parsed after Analyzer emission: {exc}") from exc
            _record_artifacts(rec, *artifacts, *_stage_component_artifacts("analyzer", cfg))
            expected_metrics = repeat_metric_rows if repeat_metric_rows is not None else n_cands
            rec.count("metrics_lines", actual=metrics_lines, expected=expected_metrics)
            rec.invariant(invariants.analyzer_input_matches_metrics(expected_metrics, metrics_lines))
            invariants.enforce(rec.invariants)
    journal.mark_run(RunStatus.SUCCEEDED)
    where = f"run '{run_layout.run_id}' ({run_layout.root})" if run_layout else f"scratch {scratch}"
    print(f"\n✓ DONE — {a.db}: full Bundle chain green. {where}")
    return run_layout


# --------------------------------- resume (STEP 24) -------------------------- #
def _resume_run(layout, manifest, spec, toml_path, cfg, *, spec_changed: bool = False) -> None:
    """Continue run *layout* in place, reusing every stage whose recorded
    output is still trustworthy and (re)running the rest -- in pipeline order,
    so that once one stage must rerun, every later stage reruns too (a stage's
    output is only as trustworthy as the chain that produced it; STEP 24
    actions 2-3: "Stage reusable только если ... Иначе stage и downstream
    rerun"). Reuse decisions and their reasons are recorded as SKIPPED stage
    journal entries (action 6: "State transitions atomically записываются"),
    carrying the prior counts forward so the journal stays complete evidence,
    not a gap (acceptance: "inspect stage timestamps/counts").
    """
    work = layout.root
    settings = manifest.settings
    lang = settings.get("lang") or "py"
    # Phase 02 / audit F3. Before this, resume never resolved a policy at all: it
    # neither proved it was continuing the original decision nor verified that the
    # Executor honoured it, and a re-run Reader dropped the policy stamp so
    # py_executor would fall back to its "legacy unsandboxed path rather than
    # failing". Resume now re-resolves, refuses any change of policy identity, and
    # carries the policy through every downstream verification.
    #
    # The operator may omit the policy flags on resume -- continuing an authorized
    # run is not a new trust decision -- in which case the recorded authorization
    # is what we re-resolve. Supplying flags that resolve to a DIFFERENT policy is
    # refused, not silently honoured.
    recorded_auth = authorization_from_dict(settings.get("execution_authorization"))
    if (cfg.execution_policy_profile or "").strip():
        policy, policy_view, resolved_auth = _resolve_execution_policy(cfg)
    elif recorded_auth is not None:
        policy, policy_view, resolved_auth = _resolve_execution_policy(
            dataclasses.replace(
                cfg,
                execution_policy_profile=recorded_auth.profile,
                candidate_origin=recorded_auth.origin,
                trusted_local_acknowledgement=recorded_auth.acknowledgement))
    else:
        raise PreflightError(
            "this run's manifest records no execution authorization, so resume cannot prove it "
            "would continue the same execution policy. Re-run the spec instead: a resume must "
            "never be the step that grants trust the original run did not have.")
    try:
        verify_same_policy(recorded_auth, resolved_auth)
    except PolicyIdentityError as exc:
        raise PreflightError(str(exc))
    if not resolved_auth.sandboxed:
        print(f"  ⚠ resuming under {policy.profile!r}: candidates run on THIS HOST with no sandbox "
              f"(origin={resolved_auth.origin})")
    else:
        ok(f"execution policy verified: {policy.profile} ({resolved_auth.policy_id})")
    main_port = settings.get("main_port")
    results_port = settings.get("results_port")
    sieve_enabled = bool(settings.get("sieve"))
    analyzer_goals = settings.get("analyzer_goals") or ""
    run_id = manifest.run_id
    db = manifest.db_name
    ext = {".py": ".py", "py": ".py", ".java": ".java", "java": ".java"}.get(lang, ".py")

    n_opt = sum(1 for s in spec.slots if "FW_Optional" in s.flags)
    try:
        optional_contract = contract_from_spec(spec)
    except OptionalContractError as exc:
        raise PreflightError(str(exc))
    optional_factor = optional_contract.expected_multiplier()
    recorded_optional_contract = settings.get("optional_table_contract")
    expected_optional_contract = optional_contract.to_dict()
    if spec_changed:
        # cmd_resume already records the new spec hash. Keep its dependent
        # contract evidence in the same manifest transaction before any stage
        # runs; otherwise a successful changed-spec resume would permanently
        # describe the old optional topology.
        settings = dict(settings)
        settings["optional_table_contract"] = expected_optional_contract
        manifest = dataclasses.replace(manifest, settings=settings)
        write_json_atomic(layout.manifest_path, manifest)
    elif recorded_optional_contract != expected_optional_contract:
        raise ResumeError(
            "the run manifest's optional-table contract does not match the unchanged "
            "specification. Refusing to re-derive over recorded evidence; restore the original "
            "manifest/spec pair or start a fresh run.")
    # Construct the journal only after reconciling manifest evidence. RunJournal
    # loads run.json into memory; constructing it earlier made mark_run overwrite
    # the just-updated optional contract with the stale pre-resume settings.
    journal = RunJournal(layout)
    core_est = fg.estimate_core_combos(spec)
    full = core_est * optional_factor

    journal.mark_run(RunStatus.RUNNING)

    # ---- gen: reusable iff the spec is unchanged and a workbook is on disk ---
    gen_prior = read_stage(layout, "gen")
    xlsx_files = sorted((work / "wb").glob("*.xlsx"))
    xlsx = xlsx_files[0] if xlsx_files else work / "wb" / "missing.xlsx"
    gen_artifacts = (file_artifact("input.spec", toml_path),
                     file_artifact("output.workbook", xlsx),
                     *_stage_component_artifacts("gen", cfg))
    # The workbook is an *intermediate* the Core stage rewrites in place (the Core
    # JAR re-saves the .xlsx it is handed, so its bytes -- and sha256 -- change
    # after `gen` recorded them; confirmed: workbook mtime lands inside the core
    # window). Matching its hash here would therefore never hold on resume, which
    # cascaded a full pipeline rerun from the very first stage. Reuse instead on
    # the determinism of gen's *inputs* -- the spec (its sha256) and the
    # fwgen/fwgen_cli component hashes (fwgen is byte-deterministic given the same
    # spec) -- plus the workbook still being present; Core's actual output is
    # separately verified by reuse_core's live fw_final count below.
    gen_match = tuple(a for a in gen_artifacts if a.kind != "output.workbook")
    reuse_gen = (not spec_changed and succeeded_with_invariants(gen_prior)
                 and bool(xlsx_files) and artifacts_match(gen_prior, gen_match))
    if reuse_gen:
        journal.skip_stage("gen", note=f"resume: reusing workbook {xlsx.name} "
                                       f"(prior stage SUCCEEDED, spec unchanged, artifact present)")
        ok(f"resume: reusing 'gen' -> {xlsx.name}")
    else:
        with journal.stage("gen", log_path=work / "gen.log") as rec:
            xlsx = stage_gen(str(Path(toml_path).parent), work)
            _record_artifacts(rec, file_artifact("input.spec", toml_path),
                              file_artifact("output.workbook", xlsx),
                              *_stage_component_artifacts("gen", cfg))
    trusted = reuse_gen

    # ---- core: reusable iff upstream trusted, prior SUCCEEDED, and fw_final's
    # live row count still matches what that run recorded (the closest
    # observable proxy for "input hash unchanged" Bundle has without re-running
    # Core itself: same spec + same workbook + same n_opt -> same row count) --
    core_prior = read_stage(layout, "core")
    recorded_fw_final = count_actual(core_prior, "fw_final")
    reuse_core = False
    core_artifacts = (file_artifact("input.workbook", xlsx), *_stage_component_artifacts("core", cfg))
    if (trusted and succeeded_with_invariants(core_prior)
            and isinstance(recorded_fw_final, int)
            and artifacts_match(core_prior, core_artifacts)):
        cnt, rc = psql(main_port, db, "select count(*) from fw_final;",
                       host=cfg.main_db_host, user=cfg.main_db_user, password=cfg.main_db_password)
        # A completed sieve reduces fw_final *in place* (the Milestone-B reference
        # run uses --sieve: 96 -> 72), so afterwards the live table no longer holds
        # the pre-sieve core count -- it holds the post-sieve count. Accept either
        # as proof Core's output is intact: the recorded core count, or -- when this
        # run sieved -- the recorded post-sieve count. Without this, reuse_core never
        # matched on a sieve run, so core+sieve+reader+executor+analyzer all cascaded
        # into a full rerun, defeating the no-op resume the executor block below is
        # explicitly built for ("stages не должны повториться", DB counts unchanged).
        # (A genuinely tampered/short fw_final still matches neither and reruns.)
        acceptable_fw_final = {recorded_fw_final}
        if sieve_enabled:
            recorded_post_sieve = count_actual(read_stage(layout, "sieve"), "post_sieve")
            if isinstance(recorded_post_sieve, int):
                acceptable_fw_final.add(recorded_post_sieve)
        reuse_core = rc == 0 and cnt.isdigit() and int(cnt) in acceptable_fw_final
    # Optional tables are part of Core's observable output. A matching fw_final
    # count alone is insufficient if a required fw_opt<size> table disappeared.
    if reuse_core and optional_contract.active:
        try:
            verify_materialized(optional_contract, _optional_tables(cfg, main_port, db))
        except OptionalContractError:
            reuse_core = False
    if reuse_core:
        fw_final = recorded_fw_final
        journal.skip_stage("core", note=f"resume: reusing fw_final={fw_final} in DB '{db}' "
                                        f"(prior stage SUCCEEDED, live row count unchanged)",
                           carry_counts=core_prior.counts)
        ok(f"resume: reusing 'core' -> fw_final={fw_final}")
    else:
        with journal.stage("core", log_path=work / "core.log") as rec:
            fw_final = stage_core(spec, xlsx, work, db, main_port, n_opt, cfg,
                                  optional_contract=optional_contract)
            rec.count("fw_final", actual=fw_final, expected=core_est)
            if optional_contract.active:
                try:
                    verify_materialized(optional_contract, _optional_tables(cfg, main_port, db))
                except OptionalContractError as exc:
                    raise StageError(str(exc))
                rec.count("optional_multiplier", actual=optional_factor)
            _record_artifacts(rec, file_artifact("input.workbook", xlsx),
                              *_stage_component_artifacts("core", cfg))
            rec.invariant(invariants.core_count_positive(fw_final))
            invariants.enforce(rec.invariants)
    trusted = trusted and reuse_core
    # Key the reader invariant off the ACTUAL fw_final, not the approximate pre-core estimate
    # (rich second-order verbs like FW_Group make core_est diverge from the real count). Mirrors _run.
    full = fw_final * optional_factor

    # ---- sieve (only if this run had it enabled): same "live count matches
    # recorded post-sieve count" proxy. Re-running the sieve on an
    # already-sieved table is itself idempotent (its predicate matches nothing
    # the second time), but only `reuse_core` guarantees fw_final is still in
    # the *pre-sieve* state sieve expects when it does need to rerun --
    if sieve_enabled:
        sieve_prior = read_stage(layout, "sieve")
        recorded_post_sieve = count_actual(sieve_prior, "post_sieve")
        reuse_sieve = False
        sieve_artifacts = _stage_component_artifacts("sieve", cfg)
        if (trusted and succeeded_with_invariants(sieve_prior)
                and isinstance(recorded_post_sieve, int)
                and artifacts_match(sieve_prior, sieve_artifacts)):
            cnt, rc = psql(main_port, db, "select count(*) from fw_final;",
                           host=cfg.main_db_host, user=cfg.main_db_user, password=cfg.main_db_password)
            reuse_sieve = rc == 0 and cnt.isdigit() and int(cnt) == recorded_post_sieve
        if reuse_sieve:
            fw_final = recorded_post_sieve
            journal.skip_stage("sieve", note=f"resume: reusing post-sieve fw_final={fw_final} "
                                             f"(prior stage SUCCEEDED, live row count unchanged)",
                               carry_counts=sieve_prior.counts)
            ok(f"resume: reusing 'sieve' -> fw_final={fw_final}")
        else:
            pre_sieve = fw_final
            with journal.stage("sieve") as rec:
                fw_final = stage_sieve(spec, work, db, main_port, fw_final, cfg)
                rec.count("post_sieve", actual=fw_final)
                _record_artifacts(rec, *_stage_component_artifacts("sieve", cfg))
                rec.invariant(invariants.post_sieve_le_core(fw_final, pre_sieve))
                invariants.enforce(rec.invariants)
        full = fw_final * optional_factor
        trusted = trusted and reuse_sieve

    # ---- reader: reusable iff upstream trusted, prior SUCCEEDED, the same
    # number of candidate files is still on disk, and (unless legacy-handoff)
    # the Handoff v2 manifest is still present -- a missing candidate or
    # manifest invalidates Reader/Executor per the acceptance criteria --
    reader_prior = read_stage(layout, "reader")
    src = work / "src"
    recorded_n_cands = count_actual(reader_prior, "candidates")
    # STEP 32: a sharded Reader output stores candidates in *.fwshard containers, not loose
    # *<ext> files. Resume must skip VALID finalized shards: count the candidate RECORDS
    # across shards (count_candidates validates each one — a truncated/corrupt/partial shard
    # contributes 0, so the count falls short and the Reader reruns), and hash the shard files
    # for the artifact match (a byte change also invalidates reuse). Loose path is unchanged.
    sharded = src.is_dir() and shards.has_shards(src)
    if sharded:
        # STEP 32 review blocker #2: a sharded Reader output stores candidates in *.fwshard
        # containers, not loose *<ext> files. DETECT and VALIDATE the finalized shards here:
        # all_shards_valid() runs each shard's full CRC/trailer check, and count_candidates()
        # re-derives the candidate-record total. A truncated/partial/corrupt shard fails
        # validation and shorts the count, so the Reader reruns; an intact, unchanged shard set
        # is reused (skipped). The shard files are also content-hashed for the artifact match.
        shard_list = shards.list_finalized_shards(src)
        shards_valid = shards.all_shards_valid(src)
        live_cand_count = shards.count_candidates(src)
        cand_files, live_empty, cand_pattern = [], 0, shards.SHARD_GLOB
    else:
        cand_files = sorted(src.glob(f"*{ext}")) if src.is_dir() else []
        live_cand_count = len(cand_files)
        live_empty = sum(1 for c in cand_files if c.stat().st_size == 0)
        shards_valid, shard_list, cand_pattern = True, [], f"*{ext}"
    legacy_handoff = not any(inv.id == "handoff.run_id_matches"
                             for inv in (reader_prior.invariants if reader_prior else ()))
    handoff_manifest_path = work / "handshake" / "handoff" / "manifest.json"
    reader_artifacts = [dir_artifact("output.candidates", src, cand_pattern),
                        *_stage_component_artifacts("reader", cfg)]
    if not legacy_handoff:
        reader_artifacts.append(file_artifact("output.handoff_manifest", handoff_manifest_path))
    reuse_reader = (trusted and succeeded_with_invariants(reader_prior)
                    and shards_valid                       # all finalized shards pass CRC/trailer
                    and isinstance(recorded_n_cands, int) and live_cand_count == recorded_n_cands
                    and (legacy_handoff or handoff_manifest_path.is_file())
                    and artifacts_match(reader_prior, tuple(reader_artifacts)))
    if reuse_reader:
        n_cands, n_empty = recorded_n_cands, live_empty
        hs = work / "handshake"
        manifest_path = handoff_manifest_path
        _src_desc = f"{len(shard_list)} valid finalized shard(s)" if sharded else str(src)
        journal.skip_stage("reader", note=f"resume: reusing {n_cands} candidates from {_src_desc} "
                                          f"(prior stage SUCCEEDED, candidate count and "
                                          f"{'legacy handshake' if legacy_handoff else 'Handoff v2 manifest'} present)",
                           carry_counts=reader_prior.counts)
        ok(f"resume: reusing 'reader' -> {n_cands} candidates"
           + (f" ({len(shard_list)} valid finalized shards skipped)" if sharded else ""))
        if legacy_handoff:
            handoff_manifest = None
        else:
            # Re-parse (don't re-journal -- it isn't a pipeline stage) the
            # manifest the reused Reader stage already validated, purely to
            # hand the Executor the same typed object a fresh run would.
            try:
                handoff_manifest = handoff_from_dict(json.loads(manifest_path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError, HandoffError, SchemaError, KeyError, TypeError, ValueError) as exc:
                raise ResumeError(
                    f"Handoff v2 manifest at {manifest_path} could not be re-parsed while "
                    f"reusing 'reader' (it validated when the stage last ran -- has it been "
                    f"modified since?): {type(exc).__name__}: {exc}")
    else:
        with journal.stage("reader", log_path=work / "reader.log") as rec:
            # STEP 32: if the upstream is trusted (same corpus) and the prior output was sharded,
            # rerun the Reader in resume mode so the ShardSink REUSES the valid prefix shards still
            # on disk and regenerates only the missing/corrupt suffix, instead of rebuilding all.
            src, hs, n_cands, n_empty, manifest_path = stage_reader(
                work, db, lang, main_port, results_port, fw_final, n_opt, full, False,
                cfg, run_id=run_id, legacy_handoff=legacy_handoff, resume=(sharded and trusted),
                policy_ref=policy_id(policy), optional_contract=optional_contract)
            rec.count("candidates", actual=n_cands, expected=full)
            # Audit F3: a re-run Reader rewrites the manifest, so the policy stamp
            # and the secret-free execution_policy.json must be re-established here
            # too. Omitting this is how a resumed secure run reached py_executor's
            # legacy unsandboxed fallback.
            _persist_handoff_policy(manifest_path, policy_id(policy), policy_view)
            _record_artifacts(rec, _candidate_artifact("output.candidates", src, ext),
                              file_artifact("output.handoff_manifest", manifest_path),
                              *_stage_component_artifacts("reader", cfg))
            rec.invariant(invariants.reader_emitted_eq_expected(n_cands, full))
            rec.invariant(invariants.reader_empty_zero(n_empty))
            handoff_manifest = _record_handoff_manifest(rec, manifest_path, run_id, n_cands, legacy_handoff)
            invariants.enforce(rec.invariants)
    trusted = trusted and reuse_reader

    # ---- executor: idempotent (STEP 23) -- safe to either reuse or rerun, but
    # Milestone B requires "stages не должны повториться" on a no-op resume,
    # so prefer reuse whenever the candidates it ran against are unchanged --
    executor_prior = read_stage(layout, "executor")
    executor_summary = work / "executor-summary.json"
    repeat_metric_rows = None
    executor_artifacts = (_candidate_artifact("input.candidates", src, ext),
                          file_artifact("output.executor_summary", executor_summary),
                          *_stage_component_artifacts("executor", cfg, lang))
    processed_prior = count_actual(executor_prior, "processed")
    verified_executor_summary = None
    if trusted and succeeded_with_invariants(executor_prior) \
            and artifacts_match(executor_prior, executor_artifacts):
        # A reused stage needs the same evidence check as a fresh one. Including
        # the summary in artifacts also means deletion/content drift invalidates
        # reuse instead of silently accepting results with no sandbox proof.
        verified_executor_summary = _require_executor_summary(executor_summary, policy)
        if legacy_handoff:
            executor_results_ok = True
        else:
            live_v2_candidates = _results_v2_latest_attempt_candidates(cfg, results_port, db, run_id)
            executor_results_ok = isinstance(processed_prior, int) and live_v2_candidates == processed_prior
    else:
        executor_results_ok = False
    if cfg.repeat_each_candidate > 1:
        executor_results_ok = executor_results_ok and executor_summary.is_file()
    reuse_executor = trusted and succeeded_with_invariants(executor_prior) and executor_results_ok
    if reuse_executor:
        journal.skip_stage("executor", note="resume: reusing prior Executor results "
                                            "(prior stage SUCCEEDED, candidates unchanged -- "
                                            "rerunning would be idempotent per STEP 23 but pointless)",
                           carry_counts=executor_prior.counts)
        ok("resume: reusing 'executor'")
    else:
        if legacy_handoff:
            raise ResumeError("cannot safely rerun a legacy-handoff Executor stage: it has no results_v2 "
                              "attempt history/idempotency key. Start a fresh run or reconcile manually.")
        attempt = _results_v2_next_attempt(cfg, results_port, db, run_id)
        _reset_owned_legacy_results(cfg, results_port, db)
        with journal.stage("executor") as rec:
            processed, passed, failed, broken, inserted, db_total, timeout, infra_fail, v2_counts = stage_executor(
                src, hs, db, results_port, cfg,
                manifest_path=(manifest_path if handoff_manifest else None), run_id=run_id,
                attempt=attempt, summary_path=executor_summary, metrics_path=work / "metrics.kv",
                language=getattr(handoff_manifest, "language", lang))
            rec.count("processed", actual=processed, expected=_expected_verdicts(cfg, n_cands))
            rec.count("pass", actual=passed)
            rec.count("fail", actual=failed)
            rec.count("broken", actual=broken)
            rec.count("timeout", actual=timeout)
            rec.count("infra_fail", actual=infra_fail)
            rec.count("inserted", actual=inserted, expected=passed + failed)
            # Mandatory on resume too: a successful Executor stage without its
            # structured evidence is not a successful stage.
            exec_summary = _require_executor_summary(executor_summary, policy)
            _record_artifacts(rec, _candidate_artifact("input.candidates", src, ext),
                              file_artifact("output.executor_summary", executor_summary),
                              *_stage_component_artifacts("executor", cfg, lang))
            for key in ("attempted", "inserted", "already_present", "updated_selected"):
                rec.count(f"results_v2_{key}", actual=v2_counts[key])
            rec.invariant(invariants.handoff_manifest_used(handoff_manifest is not None, not legacy_handoff))
            rec.invariant(invariants.executor_processed_positive(processed))
            rec.invariant(invariants.executor_processed_eq_sum(processed, passed, failed, broken, timeout, infra_fail))
            tolerated = cfg.tolerated_outcomes()

            def _severity(name):
                return invariants.WARNING if name in tolerated else invariants.CRITICAL
            rec.invariant(invariants.executor_broken_zero(broken, severity=_severity("BROKEN")))
            rec.invariant(invariants.executor_timeout_zero(timeout, severity=_severity("TIMEOUT")))
            rec.invariant(invariants.executor_infra_fail_zero(infra_fail, severity=_severity("INFRA_FAIL")))
            rec.invariant(invariants.executor_inserted_matches_policy(inserted, passed, failed))
            rec.invariant(invariants.results_v2_write_counts_consistent(
                v2_counts["attempted"], v2_counts["inserted"],
                v2_counts["already_present"], v2_counts["updated_selected"]))
            if handoff_manifest is not None:
                rec.invariant(invariants.results_v2_attempted_matches_processed(v2_counts["attempted"], processed))
            rec.invariant(invariants.results_db_eq_inserted(db_total, inserted))
            if cfg.repeat_each_candidate > 1:
                verdicts_v = _expected_verdicts(cfg, n_cands)
                opportunities_i = n_cands * cfg.repeat_each_candidate
                rm = (exec_summary or {}).get("repeat_measurements") or {}
                repeat_metric_rows = int(rm.get("metric_rows", 0))
                rec.invariant(invariants.repeat_processed_eq_verdicts(processed, verdicts_v))
                rec.invariant(invariants.repeat_results_v2_attempted_eq_verdicts(
                    v2_counts["attempted"], verdicts_v))
                rec.invariant(invariants.repeat_metric_rows_plus_missing_eq_opportunities(
                    repeat_metric_rows, rm.get("missing_measurements", 0), opportunities_i))
            invariants.enforce(rec.invariants)
    if cfg.repeat_each_candidate > 1 and repeat_metric_rows is None:
        exec_summary = verified_executor_summary or _require_executor_summary(executor_summary, policy)
        repeat_metric_rows = int((exec_summary.get("repeat_measurements") or {}).get("metric_rows", 0))
    trusted = trusted and reuse_executor

    # ---- analyzer (only if this run requested it): metrics corpus must still
    # be on disk with the same line count Reader's candidates produced --
    if analyzer_goals:
        analyzer_prior = read_stage(layout, "analyzer")
        recorded_metrics = count_actual(analyzer_prior, "metrics_lines")
        kv = work / "metrics.kv"
        live_metrics = sum(1 for _ in kv.open(encoding="utf-8")) if kv.exists() else None
        analyzer_artifacts = (_candidate_artifact("input.candidates", src, ext),
                              file_artifact("output.metrics", kv),
                              *_stage_component_artifacts("analyzer", cfg))
        reuse_analyzer = (trusted and succeeded_with_invariants(analyzer_prior)
                          and isinstance(recorded_metrics, int) and live_metrics == recorded_metrics
                          and artifacts_match(analyzer_prior, analyzer_artifacts))
        if reuse_analyzer:
            journal.skip_stage("analyzer", note=f"resume: reusing metrics corpus at {kv} "
                                                f"({live_metrics} lines, prior stage SUCCEEDED)",
                               carry_counts=analyzer_prior.counts)
            ok(f"resume: reusing 'analyzer' -> {kv}")
        else:
            with journal.stage("analyzer", log_path=work / "metrics.kv") as rec:
                stage_analyzer(src, work, analyzer_goals, cfg=cfg,
                               mode=settings.get("analysis_mode", "exploratory"), corpus_count=n_cands,
                               run_id=run_id or "", harvested_metrics=work / "metrics.kv")
                metrics_lines = sum(1 for _ in kv.open(encoding="utf-8")) if kv.exists() else 0
                prov_artifacts = ((file_artifact("output.provenance", work / "provenance.json"),)
                                  if (work / "provenance.json").exists() else ())
                _record_artifacts(rec, _candidate_artifact("input.candidates", src, ext),
                                  file_artifact("output.metrics", kv),
                                  *prov_artifacts,
                                  *_stage_component_artifacts("analyzer", cfg))
                expected_metrics = repeat_metric_rows if repeat_metric_rows is not None else n_cands
                rec.count("metrics_lines", actual=metrics_lines, expected=expected_metrics)
                rec.invariant(invariants.analyzer_input_matches_metrics(expected_metrics, metrics_lines))
                invariants.enforce(rec.invariants)

    journal.mark_run(RunStatus.SUCCEEDED)
    print(f"\n✓ DONE — {db}: resumed run '{layout.run_id}' ({layout.root}) green.")


def cmd_resume(a) -> None:
    """`bundle resume <run-dir|run-id>` (STEP 24): continue an interrupted or
    failed run without repeating stages whose recorded output is still
    trustworthy. Refuses (fails closed) to resume a run with a stage stuck
    RUNNING after an apparent crash (action 4). A changed spec is accepted but
    invalidates Generator and every downstream stage; stress runs remain
    unsupported because a load test against a live SUT has no deterministic output
    to validate-and-reuse -- resuming it is meaningless; start a fresh one)."""
    cfg, _sources = _resolve_bundle_config(a)
    layout = resolve_run_layout(a.run, runs_root=(a.runs_root or None), scratch_root=cfg.scratch_root or None)
    manifest = run_manifest_from_dict(read_json(layout.manifest_path))
    ok(f"run '{manifest.run_id}' ({layout.root}) -- last status {manifest.status.value}")
    if manifest.mode == "stress":
        raise ResumeError(
            f"run '{manifest.run_id}' is a 'stress' run -- it floods a live SUT under timing-"
            f"sensitive load and produces no deterministic, reusable per-stage output to resume "
            f"from. Start a fresh stress run instead.")
    reconcile_interrupted(layout)
    spec, toml_path = _load_one_spec(Path(manifest.spec_path).parent)
    current_sha = file_sha256(toml_path)
    spec_changed = current_sha != manifest.spec_sha256
    if spec_changed:
        print(f"  ! spec changed ({manifest.spec_sha256} -> {current_sha}); invalidating gen and all downstream stages")
        manifest = dataclasses.replace(
            manifest, spec_path=str(toml_path), spec_sha256=current_sha,
            spec_version=spec.spec_version)
        write_json_atomic(layout.manifest_path, manifest)
    else:
        ok(f"spec '{spec.name}' unchanged (sha256 {current_sha})")
    _resume_run(layout, manifest, spec, toml_path, cfg, spec_changed=spec_changed)


def _main_resume(argv):
    ap = argparse.ArgumentParser(prog="bundle_run resume",
                                 description="Continue an interrupted/failed Bundle run in place: "
                                             "reuse every stage whose recorded output is still "
                                             "trustworthy (status SUCCEEDED, inputs/artifacts "
                                             "unchanged, critical invariants passed) and "
                                             "(re)run the rest, in pipeline order.")
    ap.add_argument("run", metavar="<run-dir|run-id>",
                    help="path to an existing run directory (containing run.json), "
                         "or a bare run ID to look up under --runs-root / the scratch root's "
                         "'<db>/runs/<run-id>' layout")
    ap.add_argument("--runs-root", default="",
                    help="directory to search for a bare run ID under (in addition to "
                         "'<scratch-root>/*/runs/<run-id>', the default layout)")
    _add_bundle_config_args(ap)
    ap.add_argument("--debug", action="store_true",
                    help="show full traceback on failure instead of a concise '✗ <message>' line")
    a = ap.parse_args(argv)
    try:
        cmd_resume(a)
    except BundleError as exc:
        report_and_exit(exc, debug=a.debug)
    except KeyboardInterrupt:
        if a.debug:
            raise
        print("\n  ✗ interrupted")
        sys.exit(130)


# --------------------------------- cancel (STEP 25) -------------------------- #
def cmd_cancel(a) -> None:
    """`bundle cancel <run-dir|run-id>` (STEP 25): stop a run in place from a
    second invocation -- mark the cancel intent durably, terminate every owned
    process whose `/proc` identity still checks out (never an unrelated
    process that happens to have recycled the same pid), then rewrite the run
    and its still-RUNNING stage to CANCELLED out of band (the original
    launcher, now dead, can never write its own terminal status)."""
    cfg, _sources = _resolve_bundle_config(a)
    layout = resolve_run_layout(a.run, runs_root=(a.runs_root or None), scratch_root=cfg.scratch_root or None)
    manifest = run_manifest_from_dict(read_json(layout.manifest_path))
    if manifest.status not in (RunStatus.PENDING, RunStatus.RUNNING):
        ok(f"run '{manifest.run_id}' is already {manifest.status.value} -- nothing to cancel")
        return
    ok(f"run '{manifest.run_id}' ({layout.root}) -- last status {manifest.status.value}; cancelling")
    report = cancel_run(layout)
    if report.outcomes:
        for o in report.outcomes:
            argv = " ".join(o.argv)
            print(f"  - pid {o.pid} ({o.stage}): {o.action}" + (f"  [{argv}]" if argv else ""))
    else:
        print("  (no owned processes were recorded as active -- only run/stage status was rewritten)")
    ok(f"run '{report.run_id}' -> {report.final_status}")


def _main_cancel(argv):
    ap = argparse.ArgumentParser(prog="bundle_run cancel",
                                 description="Stop a running/pending Bundle run in place: mark intent, "
                                             "terminate its owned (identity-verified) processes without "
                                             "touching anything unrelated, and record the run/stage as "
                                             "CANCELLED.")
    ap.add_argument("run", metavar="<run-dir|run-id>",
                    help="path to an existing run directory (containing run.json), "
                         "or a bare run ID to look up under --runs-root / the scratch root's "
                         "'<db>/runs/<run-id>' layout")
    ap.add_argument("--runs-root", default="",
                    help="directory to search for a bare run ID under (in addition to "
                         "'<scratch-root>/*/runs/<run-id>', the default layout)")
    _add_bundle_config_args(ap)
    ap.add_argument("--debug", action="store_true",
                    help="show full traceback on failure instead of a concise '✗ <message>' line")
    a = ap.parse_args(argv)
    try:
        cmd_cancel(a)
    except BundleError as exc:
        report_and_exit(exc, debug=a.debug)
    except KeyboardInterrupt:
        if a.debug:
            raise
        print("\n  ✗ interrupted")
        sys.exit(130)


# --------------------------------- cleanup (STEP 25) ------------------------- #
def cmd_cleanup(a) -> None:
    """`bundle cleanup <run-dir|run-id> [--yes]` (STEP 25): report -- and,
    only with explicit `--yes`, actually remove -- everything a finished run
    left behind (run directory, its `results_v2` rows, any temporary
    credential files). Always prints the dry-run inventory first, even when
    `--yes` is given, so the operator sees exactly what is about to disappear
    (action 2/3: dry-run shows files/bytes/DBs/credentials/age, real cleanup
    needs the explicit flag)."""
    cfg, _sources = _resolve_bundle_config(a)
    layout = resolve_run_layout(a.run, runs_root=(a.runs_root or None), scratch_root=cfg.scratch_root or None)
    manifest = run_manifest_from_dict(read_json(layout.manifest_path))
    if manifest.status in (RunStatus.PENDING, RunStatus.RUNNING):
        raise CleanupError(f"run '{manifest.run_id}' is still {manifest.status.value} -- "
                           f"cancel it first ('bundle cancel {a.run}'), then clean up")
    report = scan_run(layout, manifest, cfg, db=(a.db or None), retention_seconds=a.retention_seconds)
    print(format_cleanup_report(report))
    if not a.yes:
        ok("dry-run only -- nothing changed; pass --yes to actually delete")
        return
    if not report.db_name_matches_manifest:
        raise CleanupError(f"DB name {report.db_name!r} does not match run manifest's db_name "
                           f"{manifest.db_name!r} -- refusing to clean up (action 5)")
    print()
    log, log_path = delete_run(layout, manifest, cfg, db=(a.db or None))
    rows = log.deleted_results_v2_rows if log.deleted_results_v2_rows is not None else "?"
    ok(f"removed {log.removed_files} file(s) / {log.removed_bytes} byte(s) under {log.root}, "
       f"{rows} results_v2 row(s) for run_id={layout.run_id!r} from {log.db_name!r}")
    ok(f"cleanup action log -> {log_path}")


def _main_cleanup(argv):
    ap = argparse.ArgumentParser(prog="bundle_run cleanup",
                                 description="Inspect (dry-run, default) or remove (--yes) everything a "
                                             "finished run left behind: its directory, results_v2 rows, "
                                             "and any temporary credential files.")
    ap.add_argument("run", metavar="<run-dir|run-id>",
                    help="path to an existing run directory (containing run.json), "
                         "or a bare run ID to look up under --runs-root / the scratch root's "
                         "'<db>/runs/<run-id>' layout")
    ap.add_argument("--runs-root", default="",
                    help="directory to search for a bare run ID under (in addition to "
                         "'<scratch-root>/*/runs/<run-id>', the default layout)")
    ap.add_argument("--dry-run", action="store_true",
                    help="(default) report only -- the same as omitting --yes; kept as an "
                         "explicit, self-documenting spelling for scripts/operators")
    ap.add_argument("--yes", action="store_true",
                    help="explicit confirmation required for real deletion (action 3) -- "
                         "without it, this command always behaves as a dry-run")
    ap.add_argument("--db", default="", metavar="NAME",
                    help="DB name to validate/operate against (default: the run manifest's "
                         "own db_name -- an explicit override that disagrees with it blocks "
                         "all DB-side action, see action 5)")
    ap.add_argument("--retention-seconds", type=float, default=None, metavar="SECONDS",
                    help="report whether this run's age clears a retention threshold "
                         "(informational only -- does not gate --yes)")
    _add_bundle_config_args(ap)
    ap.add_argument("--debug", action="store_true",
                    help="show full traceback on failure instead of a concise '✗ <message>' line")
    a = ap.parse_args(argv)
    try:
        cmd_cleanup(a)
    except BundleError as exc:
        report_and_exit(exc, debug=a.debug)
    except KeyboardInterrupt:
        if a.debug:
            raise
        print("\n  ✗ interrupted")
        sys.exit(130)


PLAN_SCHEMA = "bundle.plan/v1"


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


def _slot_summary(s) -> dict:
    return {"sheet": s.sheet, "verb": str(s.verb).splitlines()[0].strip(),
            "flags": list(s.flags), "n": len(s.values)}


def _plan_warnings(spec, plan) -> list:
    """Risks the operator should see before committing to a run (STEP 10 action 2:
    plan output must include `warnings`). Each is actionable and tied to a
    concrete plan/spec fact — never a vague "be careful"."""
    M = fg.CardinalityMode
    warnings = []
    if spec.spec_version == "legacy":
        warnings.append("spec has no 'spec_version' — interpreted as legacy (bundle-spec-v1 not declared)")
    brace_rows = sum(1 for cells in spec.seq_extra for c in cells
                     if fg._BRACE_RE.fullmatch(str(c).strip().splitlines()[0].strip()))
    if brace_rows:
        warnings.append(f"{brace_rows} seq_extra brace joiner row(s): their joined-result-table row "
                        f"count is UNKNOWN until Core runs (see cardinality.mandatory.reasons)")
    if plan.mandatory.mode != M.EXACT:
        warnings.append(f"mandatory Core product is {plan.mandatory.mode.value}, not EXACT — "
                        f"{plan.mandatory.formula}")
    if spec.constraints:
        warnings.append(f"{len(spec.constraints)} constraint(s) declared — post-sieve count is only "
                        f"bounded [{plan.post_sieve.lower}, {plan.post_sieve.upper}], not predicted exactly "
                        f"(sieve selectivity is not evaluated without running it)")
    n_opt = sum(1 for s in spec.slots if "FW_Optional" in s.flags)
    if n_opt:
        warnings.append(f"{n_opt} FW_Optional slot(s) — optional multiplier ×{plan.optional_multiplier.value} "
                        f"expands the post-sieve space into the final candidate count")
    if plan.final.mode == M.UNKNOWN:
        warnings.append("final candidate count is UNKNOWN — it cannot be sized statically (no "
                        "upper bound); its true size is known only once Core runs (Automation #31 cleanup)")
    elif plan.final.mode != M.EXACT:
        warnings.append(f"final candidate count is {plan.final.mode.value} "
                        f"[{plan.final.lower}, {plan.final.upper}], not an exact prediction — "
                        f"treat {plan.final.value} as an upper-bound planning figure")
    return warnings


def cmd_plan(a) -> None:
    """`bundle plan <spec-dir>` (STEP 10): estimate a run's shape WITHOUT any
    PostgreSQL/JAR/application/candidate side effects — load the spec, build its
    STEP-9 confidence-tagged cardinality plan, print spec identity/operator
    table/counts/exactness, and write a versioned `plan.json`."""
    spec, toml_path = _load_one_spec(a.spec_dir)
    # STEP 37: the FW_Seq dependency graph is a preflight GATE — a cycle / missing
    # operand / consumed-result ambiguity must reject the spec BEFORE any plan.json
    # is written (a plan for an unbuildable graph would be misleading). Build once
    # here, gate error-level issues, then reuse the graph for the artifact block.
    graph = _seq_graph.build_graph(spec)
    graph_errors = graph.errors()
    if graph_errors:
        msg = "; ".join(f"[{e.code}] {e.message}" for e in graph_errors)
        raise PreflightError(f"FW_Seq dependency graph has {len(graph_errors)} error(s) — "
                             f"refusing to write plan.json: {msg}")
    plan = fg.spec_cardinality_plan(spec)
    try:
        plan_contract = contract_from_spec(spec)
    except OptionalContractError as exc:
        raise PreflightError(f"optional-table contract is unsatisfiable: {exc}")
    sha = file_sha256(toml_path)
    slots = [_slot_summary(s) for s in spec.slots]
    warnings = _plan_warnings(spec, plan)
    # Plan-1 Phase 2 (docs/24 §3): the repeat count plan — plan-only here (no gate; a K>1 run
    # is refused later by `_check_budgets`). `validate_repeat` raises a named ConfigError on an
    # invalid combination (e.g. nested K>1 without --repeat-environments).
    cfg, cfg_sources = _resolve_bundle_config(a)
    repeat_policy, repeat_scope, repeat_k, repeat_e = cfg.validate_repeat()
    cplan = count_plan(repeat_policy, repeat_scope, plan.final, repeat_k, repeat_e)
    res_plan = estimate_resources(
        plan,
        thresholds=ResourceThresholds(smoke_max=a.class_smoke_max, bounded_max=a.class_bounded_max,
                                       large_max=a.class_large_max),
        template_sample_bytes=a.template_sample_bytes if a.template_sample_bytes else None,
        per_candidate_seconds=(a.per_candidate_seconds_min, a.per_candidate_seconds_max),
        cost_per_candidate=a.cost_per_candidate if a.cost_per_candidate is not None else None,
        count_plan=cplan,
    )
    # Plan-1 Phase 2 (Automation #29 finding 1): evaluate the SAME budget contract against the
    # repeat-aware ResourcePlan, so `bundle plan` actually answers whether a K>1 campaign violates
    # a hard ceiling (the run path refuses K>1 *before* budget evaluation). Plan mode is
    # analysis-only: a BLOCKING projection is printed prominently and persisted in plan.json, but
    # the artifact is still written and the process exits 0 — the report is the deliverable; the
    # run path is the enforcement point.
    budget_checks = evaluate_budgets(plan, res_plan, _budget_limits_from_config(cfg))
    budget_blocking = blocking_checks(budget_checks)

    print(f"spec '{spec.name}'  ({toml_path})")
    print(f"  spec_version={spec.spec_version}  sha256={sha}")
    print(f"  slots: {len(spec.slots)}   seq_extra rows: {len(spec.seq_extra)}")
    print("operator table:")
    for s in slots:
        flags = f" flags={s['flags']}" if s["flags"] else ""
        print(f"  {s['sheet']}: {s['verb']}  n={s['n']}{flags}")
    print(f"constraints present: {len(spec.constraints)}")
    if plan_contract.active:
        print(f"optional table contract: {plan_contract.optional_sheet_count} FW_Optional sheet(s), "
              f"Core produces [{plan_contract.core_property_value()}], "
              f"Reader consumes [{plan_contract.reader_property_value()}] "
              f"({plan_contract.mode}) -> ×{plan_contract.expected_multiplier()} per fw_final row")
    print()
    print(fg.format_cardinality_plan(plan))
    print()
    # the human output must distinguish "before sieve" (mandatory) from "after
    # sieve estimate" (post_sieve) — STEP 10 action 6.
    print(f"summary: mandatory={plan.mandatory.value} ({plan.mandatory.mode.value}, before sieve)  "
          f"post-sieve={plan.post_sieve.value} ({plan.post_sieve.mode.value}, after-sieve estimate)  "
          f"optional×{plan.optional_multiplier.value} ({plan.optional_multiplier.mode.value})  "
          f"final={plan.final.value} ({plan.final.mode.value})")
    print()
    print(format_resource_plan(res_plan))
    print()
    if cplan.topology_inactive:
        print("repeat plan: K=1 — repeat topology inactive (A=V=I=C); legacy single-run path")
    else:
        def _cv(est):
            return "UNKNOWN" if est.value is None else est.value
        print(f"repeat plan: policy={cplan.policy} scope={cplan.scope} K={cplan.k} "
              f"E={cplan.e_effective} (E source: {cfg_sources.get('repeat_environments', 'default')})")
        print(f"  assignments A={_cv(cplan.A)}  verdicts V={_cv(cplan.V)}  "
              f"opportunities I={_cv(cplan.I)}  metric_only={_cv(cplan.metric_only_invocations)}")
        print("  NOTE: local/metrics K>1 is EXECUTABLE on both Executors (Python & Java); "
              "scope=all / disperse / nested remain PLAN-ONLY — refused with "
              "REPEAT_K_REQUIRES_EXECUTOR_CAPABILITY (docs/24 §4)")
    print()
    print("budget evaluation (analysis-only; the run path is the enforcement point):")
    for c in budget_checks:
        print(f"  [{c.severity.value}] {c.message}")
    if budget_blocking:
        print(f"  ⛔ BUDGET BLOCKING: {len(budget_blocking)} dimension(s) over a hard ceiling "
              f"({', '.join(c.dimension for c in budget_blocking)})")
    print()
    if warnings:
        print(f"warnings ({len(warnings)}):")
        for w in warnings:
            print(f"  ! {w}")
    else:
        print("warnings: none")

    out_dir = Path(a.out) if a.out else Path(a.spec_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    plan_path = out_dir / "plan.json"
    write_json_atomic(plan_path, {
        "schema": PLAN_SCHEMA,
        "spec_name": spec.name,
        "spec_path": str(toml_path),
        "spec_sha256": sha,
        "spec_version": spec.spec_version,
        "slots": slots,
        "seq_extra_rows": len(spec.seq_extra),
        "constraints_present": len(spec.constraints),
        "cardinality": fg.cardinality_plan_to_dict(plan),
        "resources": resource_plan_to_dict(res_plan),
        "repeat_plan": cplan.to_dict(),                            # Plan-1 Phase 2 (docs/24 §3)
        "repeat_environments_source": cfg_sources.get("repeat_environments", "default"),
        "budget_checks": [budget_check_to_dict(c) for c in budget_checks],   # Automation #29 finding 1
        "budget_blocking": [c.dimension for c in budget_blocking],
        # Audit F4: the optional-table contract is validated during side-effect-free
        # planning, so an unsatisfiable R ⊆ P is rejected before Core and Reader do
        # any expensive work rather than after.
        "optional_table_contract": plan_contract.to_dict(),
        "dependency_graph": _seq_graph.graph_plan_block(graph),    # STEP 37: graph + graph_hash (gated above)
        "warnings": warnings,
    })
    ok(f"plan -> {plan_path}  (FW_Seq graph {graph.graph_hash()})")


def _table_count(conn, table: str) -> int:
    cur = conn.cursor()
    cur.execute(f'SELECT count(*) FROM "{table}";')
    n = cur.fetchone()[0]
    cur.close()
    return int(n)


def cmd_constraints(a) -> None:
    """STEP 35: `bundle constraints explain|dry-run <spec-dir>` — the quantitative effect of every
    constraint BEFORE the destructive sieve. Both are NON-destructive: the dry-run scans a
    Core-filled fw_final and reports scanned / matched-per-rule / overlap / unique-removals /
    retained (action 1) and BOUNDED sample rejected+retained combinations, deleting NOTHING
    (action 3). The actual sieve stage records the SAME statistics (action 4)."""
    sys.path.insert(0, str(Path(fg.__file__).resolve().parent / "constraints"))
    import sieve as sv
    spec, toml_path = _load_one_spec(a.spec_dir)
    if not getattr(spec, "constraints", None):
        print(f"constraints: spec {toml_path.name} declares no constraints — nothing to explain.")
        return
    sidecar = {"version": 1, "params": spec.params, "constraints": spec.constraints}
    try:
        sv.validate_sidecar(sidecar, strict=getattr(a, "strict", False))
    except ValueError as exc:
        raise PreflightError(str(exc)) from exc

    report = None
    if getattr(a, "db", ""):
        cfg, _sources = _resolve_bundle_config(a)
        import pg8000.dbapi
        port = cfg.main_db_port if getattr(a, "main_port", _UNSET) is _UNSET else a.main_port
        conn = pg8000.dbapi.connect(host=cfg.main_db_host, port=port, user=cfg.main_db_user,
                                    password=cfg.main_db_password, database=a.db)
        try:
            before = _table_count(conn, "fw_final")
            code2val, baseline, combos_col, order = sv.build_maps_from_db(conn, "fw_final", spec.slots)
            optional_sheets = {s.sheet for s in spec.slots if "FW_Optional" in s.flags}
            report = sv.sieve_fw_final(conn, "fw_final", sidecar, code2val, order, combos_col,
                                       id_col="combi_id", baseline=baseline, dry_run=True,
                                       strict=getattr(a, "strict", False),
                                       optional_sheets=optional_sheets)   # NEVER deletes
            after = _table_count(conn, "fw_final")
        finally:
            conn.close()
        if before != after:
            raise StageError(f"[STEP 35] dry-run MUST NOT delete: fw_final {before} -> {after} rows")
        print(f"dry-run: fw_final unchanged ({before} rows on disk — deletes nothing)")
    elif a.command == "dry-run":
        raise PreflightError("`bundle constraints dry-run` needs --db <name> (a Core-filled fw_final to scan)")

    print(sv.format_explain(sidecar, report))   # report None → rules only; with --db → + stats/samples


def cmd_doctor(a) -> None:
    """`bundle doctor` (STEP 15): diagnose the environment — Python/Java/jars/
    DB connectivity+privileges/scratch/analyzer/sandbox — independent of and
    without performing an actual run. Read-only: creates nothing in any
    production DB, installs nothing (action 4/5)."""
    cfg, _sources = _resolve_bundle_config(a)
    # STEP 41: `--deploy` makes doctor automatically target the LOCAL deploy stack
    # (ports + password read from deploy/.env) instead of the host PostgreSQL, so
    # the deployment profile is validated through the REAL `bundle doctor` CLI.
    if getattr(a, "deploy", False):
        from . import deploy
        try:
            cfg = deploy.apply_to_config(cfg)
        except deploy.DeployError as exc:
            raise PreflightError(str(exc))
        print(f"(using LOCAL deploy stack: 127.0.0.1:{cfg.main_db_port}/{cfg.results_db_port} from deploy/.env)")
    checks = run_doctor(cfg)
    print("BUNDLE DOCTOR")
    print(format_doctor_report(checks))
    report = doctor_report_to_dict(checks)
    print(f"\noverall: {report['overall']}")
    if a.json:
        out_path = Path(a.json)
        write_json_atomic(out_path, report)
        ok(f"report -> {out_path}")
    code = doctor_exit_code(checks)
    if code:
        sys.exit(code)


def _add_budget_ceiling_args(ap) -> None:
    """STEP-12 budget-ceiling flags (`--budget-*`), layered into `BundleConfig` via
    `_CLI_ARG_TO_CONFIG_KEY`. Shared by the run parser and `bundle plan` (Plan-1 Phase 2,
    Automation #29 finding 1) so a repeat campaign's budget can be gated from the plan-only path —
    not only via `BUNDLE_BUDGET_*` env vars. The operational/accountability flags
    (`--override-budget`/`--allow-extreme`/`--unleash-*`) stay on the run parser only."""
    _bl = BundleConfig()
    ap.add_argument("--budget-mandatory-rows", type=_optional_number(int), default=_UNSET,
                    metavar="N|none", help=f"hard ceiling on mandatory Core rows (default: {_bl.budget_mandatory_rows})")
    ap.add_argument("--budget-final-candidates", type=_optional_number(int), default=_UNSET,
                    metavar="N|none", help=f"hard ceiling on final candidates (default: {_bl.budget_final_candidates})")
    ap.add_argument("--budget-disk-bytes", type=_optional_number(int), default=_UNSET,
                    metavar="N|none", help=f"hard ceiling on estimated disk bytes (default: {_bl.budget_disk_bytes})")
    ap.add_argument("--budget-inodes", type=_optional_number(int), default=_UNSET,
                    metavar="N|none", help=f"hard ceiling on estimated loose-file inodes (default: {_bl.budget_inodes})")
    ap.add_argument("--budget-wall-time-seconds", type=_optional_number(float), default=_UNSET,
                    metavar="N|none", help=f"hard ceiling on estimated wall time, seconds (default: {_bl.budget_wall_time_seconds:g})")
    ap.add_argument("--budget-requests", type=_optional_number(int), default=_UNSET,
                    metavar="N|none", help=f"hard ceiling on estimated external requests (default: {_bl.budget_external_requests})")
    ap.add_argument("--budget-monetary-cost", type=_optional_number(float), default=_UNSET,
                    metavar="N|none", help="hard ceiling on estimated monetary cost (default: none — not gated)")
    ap.add_argument("--budget-warn-fraction", type=float, default=_UNSET,
                    help=f"warning threshold as a fraction of each hard ceiling (default: {_bl.budget_warn_fraction:g})")


def _add_repeat_args(ap) -> None:
    """Plan-1 Phase 2 (docs/24 §3): per-candidate repeat-policy CLI flags, layered into
    `BundleConfig` like every other config flag (default `_UNSET` ⇒ falls through to
    env/config/default). K=1 (default) is the legacy single run; K>1 is plan-only until the
    executor/schema phases land — a run is refused before any run dir/stage is created with
    `REPEAT_K_REQUIRES_EXECUTOR_CAPABILITY` (docs/24 §4)."""
    rg = ap.add_argument_group("repeat policy (Plan-1 Phase 2, docs/24 §3)")
    rg.add_argument("--repeat", dest="repeat", type=int, default=_UNSET, metavar="K",
                    help="run each candidate K times (default 1 = legacy single run)")
    rg.add_argument("--repeat-policy", dest="repeat_policy", default=_UNSET,
                    choices=["disperse", "local", "nested"],
                    help="distribution of the K repeats (default: local)")
    rg.add_argument("--repeat-scope", dest="repeat_scope", default=_UNSET,
                    choices=["all", "metrics"],
                    help="repeat the whole verdict ('all') or only the metric measurement "
                         "('metrics', default — does not re-run the deterministic FW_VAR verdict)")
    rg.add_argument("--repeat-environments", dest="repeat_environments", type=int, default=_UNSET,
                    metavar="E",
                    help="planned executor-environment count; REQUIRED for --repeat-policy nested "
                         "with K>1 (this is NOT --workers stress concurrency)")


def _add_bundle_config_args(ap) -> None:
    """Register the typed-`BundleConfig` CLI layer (STEP 13) on *ap*: DB
    credentials/hosts, scratch root, jar/props/executor paths, java/python
    commands, timeouts, sandbox policy, outcome-tolerance list. Shared by the
    main run parser and `bundle resume` (STEP 24) -- resuming talks to the
    same DBs/jars/timeouts a fresh run would and must accept the same
    overrides (credentials are never persisted in run.json, see STEP 14, so
    they must be resuppliable here exactly as for a fresh run).

    Every flag defaults to `_UNSET` ("not given"): an unspecified flag must
    not shadow the environment/config-file layers beneath it -- only an
    explicit override wins at "CLI" precedence (see `_resolve_bundle_config`).
    """
    cg = ap.add_argument_group("configuration (STEP 13: typed, layered BundleConfig)")
    cg.add_argument("--config-file", default="", metavar="PATH",
                    help="JSON object of BundleConfig overrides; layered beneath "
                         "environment (BUNDLE_<KEY>) and CLI, above defaults")
    cg.add_argument("--main-db-host", default=_UNSET, metavar="HOST")
    cg.add_argument("--main-db-user", default=_UNSET, metavar="USER")
    cg.add_argument("--main-db-password", default=_UNSET, metavar="PASSWORD")
    cg.add_argument("--results-db-host", default=_UNSET, metavar="HOST")
    cg.add_argument("--results-db-user", default=_UNSET, metavar="USER")
    cg.add_argument("--results-db-password", default=_UNSET, metavar="PASSWORD")
    cg.add_argument("--scratch-root", default=_UNSET, metavar="DIR",
                    help="parent directory for per-db scratch trees "
                         "(default: '/tmp/fw_work'; set e.g. '/mnt/F/fw_work' to opt into that volume)")
    cg.add_argument("--core-jar", default=_UNSET, metavar="PATH")
    cg.add_argument("--reader-jar", default=_UNSET, metavar="PATH")
    cg.add_argument("--core-props", default=_UNSET, metavar="PATH")
    cg.add_argument("--reader-props", default=_UNSET, metavar="PATH")
    cg.add_argument("--py-executor", default=_UNSET, metavar="PATH")
    cg.add_argument("--java-executor-jar", default=_UNSET, metavar="PATH",
                    help="Java Executor fat jar (default: Executor_trunk/target/Executor-1.0-jar-with-dependencies.jar)")
    cg.add_argument("--java-jars-dir", default=_UNSET, metavar="DIR",
                    help="dependency JAR directory exposed to incoming Java candidates "
                         "(default: Executor_trunk/lib-src/target)")
    cg.add_argument("--java-cmd", default=_UNSET, metavar="CMD", help="default: 'java'")
    cg.add_argument("--javac-cmd", default=_UNSET, metavar="CMD", help="default: 'javac'")
    cg.add_argument("--executor-compiler", default=_UNSET, choices=["adaptive", "janino", "ecj", "javac"],
                    help="pin the Java Executor compiler backend (-Dfw.exec.compiler); "
                         "default: MainWatch's own 'adaptive' (Janino fast path, ECJ fallback)")
    cg.add_argument("--python-cmd", default=_UNSET, metavar="CMD", help="default: this interpreter")
    cg.add_argument("--core-timeout", type=float, default=_UNSET, metavar="SECONDS",
                    help="Core jar wall-time ceiling (default: 600)")
    cg.add_argument("--reader-timeout", type=float, default=_UNSET, metavar="SECONDS",
                    help="Reader jar wall-time ceiling (default: 600)")
    cg.add_argument("--executor-timeout", type=float, default=_UNSET, metavar="SECONDS",
                    help="candidate Executor wall-time ceiling (default: 3600)")
    cg.add_argument("--sandbox-policy", default=_UNSET, metavar="ID",
                    help="Legacy free-form sandbox policy ID (recorded only; the real STEP 28 "
                         "sandbox backend is selected by --execution-policy-profile; default: 'sandbox')")
    cg.add_argument("--execution-policy-profile", default=_UNSET, metavar="PROFILE",
                    choices=[c["profile"] for c in profile_choices()],
                    help="execution-policy profile every candidate runs under -- also selects the "
                         "sandbox backend: 'generated-default' (container; use this for generated "
                         "or untrusted candidates) | 'networked-api-probe' (container, allowlisted "
                         "local-only egress) | 'trusted-local' (NO SANDBOX, host access; requires "
                         "--candidate-origin and --acknowledge-trusted-local). There is NO default: "
                         "a run refuses until a policy is chosen. 'bundle plan' needs none.")
    cg.add_argument("--candidate-origin", dest="candidate_origin", default=_UNSET, metavar="ORIGIN",
                    choices=list(ORIGINS),
                    help="where the candidate source came from, declared by YOU (never read from "
                         "the spec): " + " | ".join(ORIGINS) + ". Required for trusted-local, which "
                         "accepts only 'reviewed-checked-in' or 'locally-authored'. Recorded in the "
                         "run manifest.")
    cg.add_argument("--acknowledge-trusted-local", dest="trusted_local_acknowledgement",
                    default=_UNSET, metavar="REASON",
                    help="explicit, recorded reason for running candidates on this host WITHOUT a "
                         "sandbox. Required by --execution-policy-profile trusted-local; must be "
                         "non-empty. Persisted in the run manifest and re-verified on resume.")
    cg.add_argument("--sandbox-network-allowlist", dest="sandbox_network_allowlist",
                    default=_UNSET, metavar="TARGETS",
                    help="STEP 28: comma-separated target container name(s)/host(s) a "
                         "networked-api-probe candidate may reach (e.g. 'api-server' or "
                         "'api-server:8000'). Folded into the persisted execution policy and "
                         "attached to the candidate's dedicated local-only internal network. "
                         "Requires --execution-policy-profile networked-api-probe.")
    cg.add_argument("--sandbox-candidate-env", dest="sandbox_candidate_env",
                    default=_UNSET, metavar="NAME=VALUE,...",
                    help="STEP 30: comma-separated NAME=VALUE env passed into sandboxed "
                         "candidates (e.g. 'TRYOUT_URL=http://secure-app:8025'). NAMEs are "
                         "folded into the policy's env_allowlist; credential-shaped names are "
                         "refused (a secure sandbox never receives secrets).")
    cg.add_argument("--executor-tolerate-outcomes", default=_UNSET, metavar="LIST",
                    help="STEP 21 success policy: comma-separated infrastructure outcomes "
                         "to tolerate (subset of BROKEN,TIMEOUT,INFRA_FAIL) -- run still "
                         "succeeds and the corresponding invariant is recorded as WARNING "
                         "rather than failing closed. DOMAIN_FAIL is always tolerated and "
                         "needs no entry here (default: '' -- none tolerated)")
    cg.add_argument("--candidate-sink", dest="candidate_sink", default=_UNSET,
                    choices=["loose-files", "sharded", "grpc"],
                    help="candidate transport Reader→Executor: 'loose-files' (default; one file "
                         "per candidate), 'sharded' (*.fwshard containers), or 'grpc' "
                         "(2026-07-03: stream candidates LIVE to the Java Executor's gRPC "
                         "ingestion server — no on-disk corpus; requires --lang java and the "
                         "trusted-local execution policy)")
    cg.add_argument("--grpc-host", dest="grpc_host", default=_UNSET, metavar="HOST",
                    help="gRPC transport: host the Reader streams to (default: 127.0.0.1)")
    cg.add_argument("--grpc-port", dest="grpc_port", type=int, default=_UNSET, metavar="PORT",
                    help="gRPC transport: port the Executor's ingestion server binds "
                         "(-grpcPort) and the Reader streams to (default: 50061)")
    cg.add_argument("--executor-pool", dest="executor_pool_size", type=int, default=_UNSET, metavar="N",
                    help="Executor pool (2026-07-04): run N Java Executors, one per Reader "
                         "round-robin candidate directory (the legacy outZipDirPathList CSV). "
                         "The launcher spawns/journals/cancels the members and merges their "
                         "summaries. Requires --lang java, loose-files transport, K=1 "
                         "(default: 1 — single executor, unchanged)")
    cg.add_argument("--seed-output", dest="seed_output", default=_UNSET, action="store_const", const=True,
                    help="emit bundle_seed.json from the Analyzer stage (default: off; iterate forces it on)")
    cg.add_argument("--exploration-floor", dest="exploration_floor", type=float, default=_UNSET, metavar="FRACTION",
                    help="minimum per-sheet value fraction retained by seed bias (default: 0.25)")
    cg.add_argument("--min-winner-support", dest="min_winner_support", type=int, default=_UNSET, metavar="N",
                    help="minimum winner observations before a sheet may be narrowed (default: 5)")
    _add_repeat_args(ap)


def _main_doctor(argv):
    ap = argparse.ArgumentParser(prog="bundle_run doctor",
                                 description="Diagnose the environment (Python/Java/jars/DB/scratch/...) "
                                             "without starting a run or touching any production DB.")
    ap.add_argument("--json", default="", metavar="PATH",
                    help="also write the report as JSON to PATH")
    ap.add_argument("--config-file", default="", metavar="PATH",
                    help="JSON file of BundleConfig overrides (lowest-precedence layer above defaults)")
    ap.add_argument("--deploy", action="store_true",
                    help="diagnose the LOCAL deploy stack instead of the host DBs — auto-reads "
                         "ports/password from deploy/.env (run `bundle deploy up` first)")
    ap.add_argument("--debug", action="store_true",
                    help="show full traceback on failure instead of a concise '✗ <message>' line")
    a = ap.parse_args(argv)
    try:
        cmd_doctor(a)
    except BundleError as exc:
        report_and_exit(exc, debug=a.debug)


def _main_plan(argv):
    ap = argparse.ArgumentParser(prog="bundle_run plan",
                                 description="Estimate a spec's run shape (cardinality/exactness) "
                                             "without creating a DB, running Core/Reader/Executor, "
                                             "or producing any candidates.")
    ap.add_argument("spec_dir")
    ap.add_argument("--out", default="", help="directory to write plan.json into (default: spec_dir)")
    _add_repeat_args(ap)
    ap.add_argument("--config-file", default="", metavar="PATH",
                    help="JSON object of BundleConfig overrides (incl. budget ceilings); lowest-"
                         "precedence layer above defaults (Automation #29 finding 1: layered budgets in plan)")
    _add_budget_ceiling_args(ap)
    # STEP 11: run-class thresholds and resource-estimate inputs are
    # configurable rather than hardcoded — defaults are conservative
    # placeholders pending real measurement (see ResourceThresholds docstring).
    ap.add_argument("--class-smoke-max", type=int, default=ResourceThresholds().smoke_max,
                    help="final-candidate-count ceiling for run class S (smoke)")
    ap.add_argument("--class-bounded-max", type=int, default=ResourceThresholds().bounded_max,
                    help="final-candidate-count ceiling for run class B (bounded)")
    ap.add_argument("--class-large-max", type=int, default=ResourceThresholds().large_max,
                    help="final-candidate-count ceiling for run class L (large); above this is X (extreme)")
    ap.add_argument("--template-sample-bytes", type=int, default=0,
                    help="size in bytes of a real candidate-source template sample, "
                         "for a sound 'candidate source bytes' estimate (default: generic placeholder range)")
    ap.add_argument("--per-candidate-seconds-min", type=float, default=DEFAULT_PER_CANDIDATE_SECONDS[0],
                    help="lower bound of the assumed per-candidate execution cost in seconds "
                         "(single worker; drives the execution-duration estimate)")
    ap.add_argument("--per-candidate-seconds-max", type=float, default=DEFAULT_PER_CANDIDATE_SECONDS[1],
                    help="upper bound of the assumed per-candidate execution cost in seconds "
                         "(single worker; drives the execution-duration estimate)")
    ap.add_argument("--cost-per-candidate", type=float, default=None,
                    help="optional flat monetary cost per candidate; enables the monetary-cost estimate")
    ap.add_argument("--debug", action="store_true",
                    help="show full traceback on failure instead of a concise '✗ <message>' line")
    a = ap.parse_args(argv)
    try:
        cmd_plan(a)
    except BundleError as exc:
        report_and_exit(exc, debug=a.debug)


def cmd_bench(a) -> None:
    """STEP 40: run the per-stage benchmark harness, validate + print the report,
    and write the versioned JSON. 100M/1B sizes are refused unless --allow-huge."""
    import tempfile
    from . import benchmark
    stages = [s.strip() for s in a.stages.split(",") if s.strip()] if a.stages \
        else list(benchmark.INFRA_FREE_STAGES)
    scratch = Path(a.scratch) if a.scratch else Path(tempfile.mkdtemp(prefix="fwbench-"))
    # Resolve the config (CLI > env > file > dev-defaults) so the harness gets the
    # real DB credentials/ports the infra-heavy stages need to connect.
    cfg, _sources = resolve_config(cli={})
    try:
        report = benchmark.run_benchmark(a.profile, stages, allow_huge=a.allow_huge,
                                         scratch=scratch, cfg=cfg,
                                         main_port=(a.main_port if a.main_port is not None else None),
                                         results_port=(a.results_port if a.results_port is not None else None))
        benchmark.validate_report(report)
    except benchmark.BenchmarkError as exc:
        raise PreflightError(str(exc))
    print(benchmark.format_table(report))
    out = Path(a.out) if a.out else (scratch / "benchmark.json")
    write_json_atomic(out, report)
    ok(f"benchmark -> {out}")


def _main_bench(argv):
    ap = argparse.ArgumentParser(prog="bundle_run bench",
                                 description="STEP 40: per-stage benchmark harness — each stage is "
                                             "measured INDEPENDENTLY at a size profile. 100M/1B are "
                                             "never run automatically (need --allow-huge).")
    ap.add_argument("--profile", default="10K", help="10K | 1M | 10M | <int>  (default: 10K)")
    from .benchmark import ALL_STAGES as _BENCH_STAGES
    ap.add_argument("--stages", default="",
                    help="comma list (default: generator,sieve). A reference_overhead[...] stage "
                         "measures what one registered target's wrapper adds around an "
                         "identical canonical Bundle run. known: " + ",".join(_BENCH_STAGES))
    ap.add_argument("--allow-huge", action="store_true",
                    help="explicitly permit profile sizes above 10M (100M/1B) — never the default")
    ap.add_argument("--main-port", type=int, default=None, help="main DB port for Core/Reader stages (optional)")
    ap.add_argument("--results-port", type=int, default=None, help="results DB port for the Executor stage (optional)")
    ap.add_argument("--scratch", default="", help="scratch dir for stage artifacts (default: a tempdir)")
    ap.add_argument("--out", default="", help="write the JSON report here (default: <scratch>/benchmark.json)")
    ap.add_argument("--debug", action="store_true",
                    help="show full traceback on failure instead of a concise '✗ <message>' line")
    a = ap.parse_args(argv)
    try:
        cmd_bench(a)
    except BundleError as exc:
        report_and_exit(exc, debug=a.debug)


def cmd_hygiene(a) -> None:
    """STEP 43: report the backup inventory + the production compile-source-set
    verification + the archival proposal. REPORT-ONLY — moves/deletes never happen
    here (apply_archival needs explicit code-level approval). Exits non-zero if the
    production compile source set captures a backup (an acceptance violation)."""
    from . import hygiene
    print(hygiene.format_report())
    if a.json:
        write_json_atomic(Path(a.json), hygiene.archival_proposal())
        ok(f"hygiene proposal -> {a.json}")
    clean, captured = hygiene.verify_clean()
    if not clean:
        raise PreflightError(f"production compile source set captures {len(captured)} backup file(s): "
                             + ", ".join(b.relpath for b in captured))


def _main_hygiene(argv):
    ap = argparse.ArgumentParser(prog="bundle_run hygiene",
                                 description="STEP 43: separate production sources from historical backups. "
                                             "Inventories backups (with checksums), verifies the compile source "
                                             "set excludes them, proposes archival. NEVER deletes/moves.")
    ap.add_argument("--json", default="", metavar="PATH", help="write the archival PROPOSAL (no execution) to PATH")
    ap.add_argument("--debug", action="store_true",
                    help="show full traceback on failure instead of a concise '✗ <message>' line")
    a = ap.parse_args(argv)
    try:
        cmd_hygiene(a)
    except BundleError as exc:
        report_and_exit(exc, debug=a.debug)


def cmd_inventory(a) -> None:
    """STEP 42: print + (optionally) write the machine-readable component version
    matrix; optionally compare to a baseline under a warn/block policy; optionally
    emit an SBOM if the toolchain is present (never blocks on a missing tool)."""
    from . import inventory
    try:
        inv = inventory.build_inventory()
        inventory.validate_inventory(inv)
        print(inventory.format_matrix(inv))
        if a.baseline:
            baseline = read_json(Path(a.baseline))
            diffs = inventory.compare(inv, baseline)
            for d in diffs:
                print(f"  {'=' if d['status'] == 'ok' else '≠'} {d['component']}: {d['status']} — {d['detail']}")
            inventory.enforce_policy(diffs, policy=a.policy)     # raises on block + mismatch
        if a.sbom:
            sb = inventory.generate_sbom()
            print(f"  SBOM: {'generated via ' + sb['tool'] if sb.get('available') and 'path' in sb else sb.get('reason') or sb.get('error') or 'unavailable'}")
        if a.out:
            write_json_atomic(Path(a.out), inv)
            ok(f"inventory -> {a.out}")
    except inventory.InventoryError as exc:
        raise PreflightError(str(exc))


def _main_inventory(argv):
    ap = argparse.ArgumentParser(prog="bundle_run inventory",
                                 description="STEP 42: machine-readable component version/hash matrix. "
                                             "Each component's canonical build + declared version + actual "
                                             "artifact sha256. Optional baseline compare (warn/block).")
    ap.add_argument("--out", default="", help="write the matrix JSON to PATH")
    ap.add_argument("--baseline", default="", help="compare artifact hashes against this saved inventory JSON")
    ap.add_argument("--policy", default="warn", choices=["warn", "block"],
                    help="version-mismatch policy when --baseline is given (default: warn)")
    ap.add_argument("--sbom", action="store_true", help="also emit an SBOM if a toolchain (syft/cyclonedx) is present")
    ap.add_argument("--debug", action="store_true",
                    help="show full traceback on failure instead of a concise '✗ <message>' line")
    a = ap.parse_args(argv)
    try:
        cmd_inventory(a)
    except BundleError as exc:
        report_and_exit(exc, debug=a.debug)


def cmd_architecture(a) -> None:
    """Engine-first architecture gate: print the declared layer model and fail
    when a module imports across a forbidden boundary. Side-effect-free."""
    from . import architecture as arch
    report = arch.architecture_report()
    print(arch.format_architecture_report(report))
    if a.json:
        write_json_atomic(Path(a.json), report)
        ok(f"architecture report -> {a.json}")
    if report["unclassified_paths"]:
        raise PreflightError(
            f"{len(report['unclassified_paths'])} repository tree(s) declare no architectural "
            f"layer: {', '.join(report['unclassified_paths'])}")
    if report["violations"]:
        raise PreflightError(
            f"{len(report['violations'])} dependency-direction violation(s) across the audited "
            f"non-test product layers; see the report above")


def _main_architecture(argv):
    ap = argparse.ArgumentParser(
        prog="bundle_run architecture",
        description="Print and enforce the engine-first architecture boundary: which layer each "
                    "tree belongs to, which imports are allowed, and which reference applications "
                    "are registered. Exits non-zero on a violation or an unclassified tree.")
    ap.add_argument("--json", default="", metavar="PATH", help="write the report JSON to PATH")
    ap.add_argument("--debug", action="store_true",
                    help="show full traceback on failure instead of a concise '✗ <message>' line")
    a = ap.parse_args(argv)
    try:
        cmd_architecture(a)
    except BundleError as exc:
        report_and_exit(exc, debug=a.debug)


def cmd_coverage(a) -> None:
    """Reference-coverage audit: which engine capabilities each registered
    target exercises, its architectural role/composition depth, and what its
    launcher pins. Side-effect-free; deterministic for a source revision."""
    from . import coverage as cov
    measurements = read_json(Path(a.measurements)) if a.measurements else None
    report = cov.reference_coverage_report(measurements)
    print(cov.format_coverage_report(report))
    if a.json:
        write_json_atomic(Path(a.json), report)
        ok(f"reference-coverage report -> {a.json}")


def _main_coverage(argv):
    ap = argparse.ArgumentParser(
        prog="bundle_run coverage",
        description="Audit engine capability exposure: engine composition vocabulary vs. the "
                    "subset each registered coverage target exercises, its role/order, "
                    "and the policy restrictions its launcher imposes. Reports individual facts "
                    "— never a single aggregate 'power' score.")
    ap.add_argument("--json", default="", metavar="PATH", help="write the report JSON to PATH")
    ap.add_argument("--measurements", default="", metavar="PATH",
                    help="merge a bundle bench --stages reference_overhead report so each "
                         "application's per-phase measurement is carried into the audit")
    ap.add_argument("--debug", action="store_true",
                    help="show full traceback on failure instead of a concise '✗ <message>' line")
    a = ap.parse_args(argv)
    try:
        cmd_coverage(a)
    except BundleError as exc:
        report_and_exit(exc, debug=a.debug)


def cmd_capabilities(a) -> None:
    """Print/emit the generated capability matrix. Side-effect-free.

    The matrix is the single source for preflight, the documentation table, the
    CI case list and the GUIs' option availability, so this command is how each
    of those is refreshed — none of them is hand-maintained."""
    from . import capabilities as caps
    matrix = caps.capability_matrix()
    if a.markdown:
        text = caps.format_matrix_markdown(matrix)
        if a.markdown == "-":
            print(text)
        else:
            Path(a.markdown).parent.mkdir(parents=True, exist_ok=True)
            Path(a.markdown).write_text(text, encoding="utf-8")
            ok(f"capability matrix (markdown) -> {a.markdown}")
    else:
        print(caps.format_matrix_text(matrix))
    if a.json:
        write_json_atomic(Path(a.json), matrix)
        ok(f"capability matrix (json) -> {a.json}")
    if a.ci_cases:
        write_json_atomic(Path(a.ci_cases), {"schema": caps.SCHEMA, "cases": caps.ci_cases()})
        ok(f"CI cases -> {a.ci_cases}")
    if a.check:
        # Freshness gate: the checked-in documentation table must match what the
        # registry generates right now, or the two have drifted.
        target = Path(a.check)
        if not target.is_file():
            raise PreflightError(f"capability matrix document missing: {target}")
        current = caps.format_matrix_markdown(matrix)
        if target.read_text(encoding="utf-8") != current:
            raise PreflightError(
                f"{target} is stale: regenerate with "
                f"`bundle_run.py capabilities --markdown {target}`")
        ok(f"{target} is up to date with the capability registry")


def _main_capabilities(argv):
    ap = argparse.ArgumentParser(
        prog="bundle_run capabilities",
        description="The one generated capability matrix: which operator-visible combinations are "
                    "SUPPORTED, EXPERIMENTAL or UNSUPPORTED, with a stable reason code, the "
                    "required backend/artifact, the security boundary and the evidence for each. "
                    "Preflight, the documentation table, the CI case list and both GUIs are all "
                    "generated from this registry.")
    ap.add_argument("--json", default="", metavar="PATH", help="write the matrix JSON to PATH")
    ap.add_argument("--markdown", default="", metavar="PATH",
                    help="write the human support table to PATH ('-' for stdout)")
    ap.add_argument("--ci-cases", default="", metavar="PATH",
                    help="write one CI case per runnable combination to PATH")
    ap.add_argument("--check", default="", metavar="PATH",
                    help="fail if the generated Markdown at PATH is stale (CI freshness gate)")
    ap.add_argument("--debug", action="store_true",
                    help="show full traceback on failure instead of a concise '✗ <message>' line")
    a = ap.parse_args(argv)
    try:
        cmd_capabilities(a)
    except BundleError as exc:
        report_and_exit(exc, debug=a.debug)


def cmd_sut_manifests(a) -> None:
    """Validate and report the canonical SUT adapter manifests. Side-effect-free."""
    from . import sut_manifests as sm
    try:
        data = sm.report()
    except sm.SutManifestError as exc:
        raise PreflightError(str(exc))
    print(sm.format_report(data))
    if a.json:
        write_json_atomic(Path(a.json), data)
        ok(f"SUT manifest inventory -> {a.json}")
    # Review item B.1: fail on EVERY drift list. Failing only on missing paths
    # let a canonical manifest claim a CI gate that no workflow step runs, which
    # is the more dangerous of the two — a missing path is visible, an unwired
    # gate looks like coverage.
    for name, entries in sorted((data.get("drift") or {}).items()):
        if entries:
            raise PreflightError(
                f"canonical SUT drift in {name!r} ({len(entries)}): {', '.join(entries)}")


def _main_sut_manifests(argv):
    ap = argparse.ArgumentParser(
        prog="bundle_run sut-manifests",
        description="Validate the canonical SUT adapter manifests: schema, capability row against "
                    "the registry, controls, oracle independence, and that every referenced test "
                    "and scenario path exists. Exits non-zero on drift.")
    ap.add_argument("--json", default="", metavar="PATH", help="write the inventory JSON to PATH")
    ap.add_argument("--debug", action="store_true",
                    help="show full traceback on failure instead of a concise '✗ <message>' line")
    a = ap.parse_args(argv)
    try:
        cmd_sut_manifests(a)
    except BundleError as exc:
        report_and_exit(exc, debug=a.debug)


def cmd_release(a) -> None:
    """Generate the release manifest and/or SBOM. Side-effect-free apart from
    the files it is asked to write.

    Instances are release ARTIFACTS, not source: write them to /tmp or a CI
    artifact store. Only the generator, its schema and its tests are committed.
    """
    from . import release as rel
    skips: "list[str]" = []
    test_summary: dict = {}
    if a.pytest_output:
        raw = Path(a.pytest_output).read_text(encoding="utf-8", errors="replace")
        parsed = rel.parse_pytest_skips(raw)
        skips = [entry["reason"] for entry in parsed for _ in range(entry["count"])]
        test_summary = {"source": a.pytest_output, **rel.parse_pytest_summary(raw)}
        # Cross-check pytest's aggregate with the grouped -ra evidence. A
        # mismatch means the log is incomplete or the parser no longer matches
        # pytest's format; either case is release-blocking.
        test_summary["classified_skip_count"] = sum(entry["count"] for entry in parsed)
    if a.sbom:
        sbom = rel.generate_sbom()
        write_json_atomic(Path(a.sbom), sbom)
        ok(f"SBOM ({len(sbom['components'])} components) -> {a.sbom}")
    manifest = rel.release_manifest(skips=skips, test_summary=test_summary)
    rel.validate_release_manifest(manifest)
    print(rel.format_release_report(manifest))
    if a.out:
        write_json_atomic(Path(a.out), manifest)
        ok(f"release manifest -> {a.out}")
    blocking = manifest["skips"]["release_blocking"]
    tests = manifest.get("tests") or {}
    # Review item A.3: the summary line can read green while the process still
    # exited non-zero (an internal error after the summary, a plugin failure, a
    # non-zero exit with no failed tests). When the runner recorded its real
    # exit code, that code is authoritative over the parsed text.
    recorded_exit = tests.get("exit_code")
    if a.pytest_output and recorded_exit is not None and int(recorded_exit) != 0:
        raise PreflightError(
            f"the supplied pytest run recorded BUNDLE_PYTEST_EXIT_CODE={recorded_exit}; a non-zero "
            f"exit is release-blocking regardless of what the summary line says. The manifest was "
            f"emitted as evidence, but the release gate is refused.")
    if a.pytest_output and (
            not tests.get("complete")
            or int(tests.get("failed") or 0) > 0
            or int(tests.get("errors") or 0) > 0):
        raise PreflightError(
            "the supplied pytest run is not release-green: "
            f"complete={tests.get('complete')}, failed={tests.get('failed')}, "
            f"errors={tests.get('errors')}. The manifest was emitted as evidence, but the "
            "release gate is refused.")
    if a.pytest_output and int(tests.get("skipped") or 0) != int(
            tests.get("classified_skip_count") or 0):
        raise PreflightError(
            "pytest skip evidence is incomplete: terminal summary reports "
            f"{tests.get('skipped')} skip(s), but classified -ra entries account for "
            f"{tests.get('classified_skip_count')}. Refusing a partially classified release.")
    if blocking and not a.allow_blocking_skips:
        raise PreflightError(
            f"{len(blocking)} release-blocking skip(s): "
            + "; ".join(f"{e['class']}: {e['reason']}" for e in blocking)
            + ". Unclassified skips must be classified; a MISSING_AUTHORIZED_BACKEND "
              "must be supplied because absence is not release evidence.")


def _main_release(argv):
    ap = argparse.ArgumentParser(
        prog="bundle_run release",
        description="Generate the release manifest (source revision + dirty state, toolchain, "
                    "hashed release inputs, capability matrix identity, canonical SUT inventory, "
                    "classified skips) and optionally a CycloneDX SBOM. Fails when a skip on the "
                    "release path is unclassified. Instances are artifacts, never source.")
    ap.add_argument("--out", default="", metavar="PATH", help="write the release manifest JSON")
    ap.add_argument("--sbom", default="", metavar="PATH", help="write the CycloneDX SBOM JSON")
    ap.add_argument("--pytest-output", default="", metavar="PATH",
                    help="a saved `pytest -ra` output to classify skips from")
    ap.add_argument("--allow-blocking-skips", action="store_true",
                    help="report unclassified skips without failing (never use on a release gate)")
    ap.add_argument("--debug", action="store_true",
                    help="show full traceback on failure instead of a concise '✗ <message>' line")
    a = ap.parse_args(argv)
    try:
        cmd_release(a)
    except BundleError as exc:
        report_and_exit(exc, debug=a.debug)


def cmd_provenance(a) -> None:
    """Provenance and third-party license inventory. NON-OPERATIVE: it gathers
    evidence for a publication decision, activates nothing, and is not legal
    advice. Side-effect-free."""
    from . import provenance as prov
    data = prov.report()
    print(prov.format_report(data))
    if a.json:
        write_json_atomic(Path(a.json), data)
        ok(f"provenance inventory -> {a.json}")
    if a.fail_on_blockers and data["blockers"]:
        raise PreflightError(
            f"{len(data['blockers'])} publication blocker(s) outstanding: "
            + ", ".join(b["id"] for b in data["blockers"]))


def _main_provenance(argv):
    ap = argparse.ArgumentParser(
        prog="bundle_run provenance",
        description="Evidence for a publication decision: what the Git history can and cannot "
                    "show, how each tracked file is classified, and what every dependency "
                    "DECLARES about its own license. Records the owner's authorship claim as an "
                    "attestation and never as a finding. Activates nothing.")
    ap.add_argument("--json", default="", metavar="PATH", help="write the inventory JSON to PATH")
    ap.add_argument("--fail-on-blockers", action="store_true",
                    help="exit non-zero while any publication blocker is outstanding")
    ap.add_argument("--debug", action="store_true",
                    help="show full traceback on failure instead of a concise '✗ <message>' line")
    a = ap.parse_args(argv)
    try:
        cmd_provenance(a)
    except BundleError as exc:
        report_and_exit(exc, debug=a.debug)


def cmd_deploy(a) -> None:
    """STEP 41: drive the local dev DB stack. validate (no runtime needed) / up /
    down (data-preserving) / status. DeployError -> PreflightError -> concise exit."""
    from . import deploy
    try:
        if a.command == "validate":
            print(deploy.format_validation(deploy.validate_profile()))
            ok("deploy profile valid (local-only, pinned, health-checked)")
        elif a.command == "up":
            rep = deploy.up(monitoring=a.monitoring)
            for svc, st in rep["health"].items():
                print(f"  {svc}: {st}")
            unhealthy = [s for s, st in rep["health"].items() if st != "healthy"]
            if unhealthy:
                raise deploy.DeployError(f"started but not healthy in time: {', '.join(unhealthy)}")
            ok(f"deploy up: {len(rep['started'])} container(s) authenticated and healthy "
               f"(env {rep['env_file']})")
        elif a.command == "down":
            rep = deploy.down(volumes=a.volumes)
            ok(f"deploy down: removed {len(rep['removed'])} container(s); "
               + ("data DELETED (--volumes)" if a.volumes else "data PRESERVED (volumes kept)"))
        elif a.command == "status":
            st = deploy.status()
            if st["runtime"] != "available":
                raise deploy.DeployError("BLOCKED: Docker runtime is not available")
            for name, info in st["services"].items():
                extra = f" health={info.get('health')}" if "health" in info else ""
                print(f"  {name}: running={info['running']}{extra}")
            ok("deploy status reported")
    except deploy.DeployError as exc:
        raise PreflightError(str(exc))


def _main_deploy(argv):
    ap = argparse.ArgumentParser(prog="bundle_run deploy",
                                 description="STEP 41: reproducible LOCAL dev DB stack (containers). "
                                             "LOCAL-ONLY (127.0.0.1); `down` preserves data by default; "
                                             "never auto-installs the runtime.")
    ap.add_argument("command", choices=["validate", "up", "down", "status"])
    ap.add_argument("--monitoring", action="store_true", help="[up] also start the optional monitoring container")
    ap.add_argument("--volumes", action="store_true",
                    help="[down] ALSO delete the data volumes (destructive; default keeps data)")
    ap.add_argument("--debug", action="store_true",
                    help="show full traceback on failure instead of a concise '✗ <message>' line")
    a = ap.parse_args(argv)
    try:
        cmd_deploy(a)
    except BundleError as exc:
        report_and_exit(exc, debug=a.debug)



ITERATE_SCHEMA = "bundle.iterate/v1"


def _stage_count_value(run_dir: Path, stage: str, name: str, field: str = "actual"):
    try:
        data = read_json(run_dir / "stages" / f"{stage}.json")
    except FileNotFoundError:
        return None
    for c in data.get("counts", []):
        if c.get("name") == name:
            return c.get(field)
    return None


def _winner_candidate_id(winner: dict) -> str | None:
    kv = winner.get("kvPairs") or {}
    if isinstance(kv, dict):
        for key in ("candidate_id", "combi_id", "id"):
            val = kv.get(key)
            if isinstance(val, str) and val:
                return val
    line = winner.get("originalLine") or ""
    if isinstance(line, str):
        for token in line.split():
            if token.startswith("candidate_id="):
                return token.split("=", 1)[1]
    return None


def _seed_front_ids(seed_doc: dict) -> list[str]:
    winners = seed_doc.get("winners") or []
    front = [_winner_candidate_id(w) for w in winners if isinstance(w, dict) and w.get("role") == "pareto"]
    front = [x for x in front if x]
    if not front:
        front = [_winner_candidate_id(w) for w in winners if isinstance(w, dict)]
        front = [x for x in front if x]
    return sorted(set(front))


def _cmd_iterate(a) -> None:
    if a.iterations < 1:
        raise PreflightError("--iterations must be >= 1")
    if not a.analyzer or a.analyzer is _UNSET:
        raise PreflightError("bundle iterate requires --analyzer goals; no goals means no winners and no feedback loop")
    if getattr(a, "legacy_scratch", False):
        raise PreflightError("bundle iterate requires journaled run directories; --legacy-scratch is not supported")
    a.seed_output = True
    cfg, _sources = _resolve_bundle_config(a)
    a.main_port, a.results_port, a.mode, a.analyzer = (
        cfg.main_db_port, cfg.results_db_port, cfg.run_mode, cfg.analyzer_goals)
    a.seed_output, a.exploration_floor, a.min_winner_support = (
        cfg.seed_output, cfg.exploration_floor, cfg.min_winner_support)
    spec, _toml_path, scratch = preflight(_with_db(a), cfg)
    runs_root = Path(a.runs_root) if a.runs_root else scratch / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    base_run_id = generate_run_id(a.run_id or None)
    lineage_path = runs_root / f"{base_run_id}-iterate.json"
    lineage = {
        "schema": ITERATE_SCHEMA,
        "status": "RUNNING",
        "base_run_id": base_run_id,
        "spec_name": spec.name,
        "db": a.db,
        "iterations_requested": a.iterations,
        "stop_when_stable": a.stop_when_stable,
        "exploration_floor": cfg.exploration_floor,
        "min_winner_support": cfg.min_winner_support,
        "iterations": [],
    }
    write_json_atomic(lineage_path, lineage)

    previous_seed = None
    previous_front: set[str] | None = None
    stable = 0
    final_status = "COMPLETED"
    for i in range(1, a.iterations + 1):
        it = argparse.Namespace(**vars(a))
        it.run_id = f"{base_run_id}-it{i}"
        it.runs_root = str(runs_root)
        it.seed_output = True
        it.seed_from = str(previous_seed) if previous_seed is not None else ""
        it.sieve = bool(getattr(a, "sieve", False) or it.seed_from)
        it.draw = False
        it.draw_exact = False
        it.legacy_scratch = False
        it.legacy_handoff = getattr(a, "legacy_handoff", False)
        print(f"\n[iterate {i}/{a.iterations}] run_id={it.run_id}" + (f" seed_from={it.seed_from}" if it.seed_from else " full-space seed run"))
        try:
            _run(it)
        except BundleError as exc:
            final_status = "FAILED"
            lineage["status"] = final_status
            lineage["error"] = str(exc)
            write_json_atomic(lineage_path, lineage)
            raise
        run_dir = runs_root / it.run_id
        seed_path = run_dir / "bundle_seed.json"
        if not seed_path.exists() or seed_path.stat().st_size == 0:
            final_status = "FAILED"
            lineage["status"] = final_status
            lineage["error"] = f"iteration {i} produced no bundle_seed.json; candidates may emit no harvestable metrics"
            write_json_atomic(lineage_path, lineage)
            raise StageError(lineage["error"])
        seed_doc = read_json(seed_path)
        front_ids = _seed_front_ids(seed_doc)
        if not front_ids:
            final_status = "FAILED"
            lineage["status"] = final_status
            lineage["error"] = f"iteration {i} seed has no joinable Pareto/front candidate ids"
            write_json_atomic(lineage_path, lineage)
            raise StageError(lineage["error"])
        front_set = set(front_ids)
        if previous_front is not None and front_set == previous_front:
            stable += 1
        else:
            stable = 0
        previous_front = front_set

        plan_path = run_dir / "bias_plan.json"
        plan_doc = read_json(plan_path) if plan_path.exists() else None
        plan_status = (plan_doc or {}).get("status") if isinstance(plan_doc, dict) else None
        entry = {
            "iteration": i,
            "run_id": it.run_id,
            "run_dir": str(run_dir),
            "input_seed": str(previous_seed) if previous_seed is not None else None,
            "input_seed_sha256": file_sha256(previous_seed) if previous_seed is not None else None,
            "seed": str(seed_path),
            "seed_sha256": file_sha256(seed_path),
            "plan": str(plan_path) if plan_path.exists() else None,
            "plan_sha256": file_sha256(plan_path) if plan_path.exists() else None,
            "candidate_count": _stage_count_value(run_dir, "reader", "candidates"),
            "core_fw_final": _stage_count_value(run_dir, "core", "fw_final"),
            "post_sieve": _stage_count_value(run_dir, "sieve", "post_sieve"),
            "pre_bias_estimate": _stage_count_value(run_dir, "seed_bias", "pre_bias_estimate"),
            "post_bias_estimate": _stage_count_value(run_dir, "seed_bias", "post_bias_estimate"),
            "winner_count": len(seed_doc.get("winners") or []),
            "front_ids": front_ids,
            "stable_transitions": stable,
            "plan_status": plan_status,
        }
        lineage["iterations"].append(entry)
        lineage["status"] = "RUNNING"
        write_json_atomic(lineage_path, lineage)
        pre = entry["pre_bias_estimate"] or entry["candidate_count"] or "?"
        post = entry["candidate_count"] or entry["post_bias_estimate"] or "?"
        keep = "?"
        if isinstance(pre, int) and isinstance(post, int) and pre:
            keep = f"{(post / pre) * 100:.1f}%"
        print(f"[iterate {i}/{a.iterations}] candidates {pre}->{post} (bias kept {keep}) · front={len(front_ids)} · stable={stable}/{a.stop_when_stable or '-'}")
        previous_seed = seed_path
        if plan_status == "CONVERGED_NO_SIGNAL":
            final_status = "CONVERGED_NO_SIGNAL"
            break
        if a.stop_when_stable and stable >= a.stop_when_stable:
            final_status = "STABLE_FRONT"
            break
    lineage["status"] = final_status
    write_json_atomic(lineage_path, lineage)
    ok(f"iterate -> {lineage_path} ({final_status})")


def _main_iterate(argv):
    ap = argparse.ArgumentParser(prog="bundle_run iterate",
                                 description="Run Bundle N times, biasing iteration i+1 from iteration i's BundleSeed")
    ap.add_argument("spec_dir")
    ap.add_argument("--db", default="")
    ap.add_argument("--lang", default="py", choices=["py", "python", "java"])
    ap.add_argument("--iterations", type=int, required=True)
    ap.add_argument("--stop-when-stable", type=int, default=0, metavar="K")
    ap.add_argument("--run-id", default="")
    ap.add_argument("--runs-root", default="")
    ap.add_argument("--main-port", type=int, default=_UNSET, metavar="PORT",
                    help=f"main DB port (default: {BundleConfig().main_db_port})")
    ap.add_argument("--results-port", type=int, default=_UNSET, metavar="PORT",
                    help=f"results DB port (default: {BundleConfig().results_db_port})")
    ap.add_argument("--analyzer", required=True,
                    help='AnalyzeKv goals, e.g. "dq_score:max,latency_ms:min"')
    ap.add_argument("--analysis-mode", default="exploratory", choices=["formal", "exploratory"])
    ap.add_argument("--mode", default=_UNSET, choices=["verdict", "stress"])
    ap.add_argument("--sieve", action="store_true")
    ap.add_argument("--seed-from", default="")
    ap.add_argument("--base-url", default="http://127.0.0.1:8121")
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--duration", type=float, default=10)
    ap.add_argument("--ramp", type=float, default=3)
    ap.add_argument("--slo-p99", type=float, default=1500)
    ap.add_argument("--err-budget", type=float, default=0.01)
    ap.add_argument("--legacy-scratch", action="store_true")
    ap.add_argument("--legacy-handoff", action="store_true")
    _add_budget_ceiling_args(ap)
    ap.add_argument("--override-budget", default=None, metavar="REASON")
    ap.add_argument("--allow-extreme", action="store_true")
    ap.add_argument("--unleash-initial-productivity-power", dest="unleash_initial_productivity_power",
                    default=_UNSET, action="store_const", const=True)
    ap.add_argument("--cost-per-candidate", type=float, default=None, metavar="PRICE")
    _add_bundle_config_args(ap)
    ap.add_argument("--debug", action="store_true")
    a = ap.parse_args(argv)
    try:
        _cmd_iterate(a)
    except BundleError as exc:
        report_and_exit(exc, debug=a.debug)


def _main_constraints(argv):
    ap = argparse.ArgumentParser(prog="bundle_run constraints",
                                 description="STEP 35: show each constraint's quantitative effect "
                                             "(non-destructive). `explain` lists the rules (+ a dry-run "
                                             "report when --db is given); `dry-run` requires --db and "
                                             "reports what the sieve WOULD remove without deleting anything.")
    ap.add_argument("command", choices=["explain", "dry-run"])
    ap.add_argument("spec_dir")
    ap.add_argument("--db", default="",
                    help="Core-filled main DB name to scan for the quantitative report "
                         "(explain works without it — rules only)")
    ap.add_argument("--main-port", type=int, default=_UNSET, metavar="PORT",
                    help=f"main DB port (default: {BundleConfig().main_db_port})")
    ap.add_argument("--strict", action="store_true",
                    help="fail if any declared constraint is unsupported by sieve v1")
    ap.add_argument("--config-file", default="")
    ap.add_argument("--debug", action="store_true",
                    help="show full traceback on failure instead of a concise '✗ <message>' line")
    a = ap.parse_args(argv)
    try:
        cmd_constraints(a)
    except BundleError as exc:
        report_and_exit(exc, debug=a.debug)


#: The verbs dispatched from ``sys.argv[1]`` below, before the legacy pipeline
#: parser ever runs. argparse therefore cannot discover them on its own, so the
#: list is restated here and shown as the pipeline parser's epilog — otherwise
#: `bundle_run.py --help` documents only the pipeline form and silently implies
#: that `doctor`, `plan`, `deploy`, ... do not exist.
_VERBS = (
    ("plan", "compile a spec to a plan + exact cardinality (no DB, no run)"),
    ("doctor", "diagnose host config; --deploy checks the deploy stack"),
    ("resume", "continue an interrupted or failed run in place"),
    ("cancel", "stop a running run"),
    ("cleanup", "remove a run's scratch state (and its credential files)"),
    ("constraints", "inspect a spec's constraint sidecar"),
    ("iterate", "closed-loop iteration over a spec"),
    ("bench", "stage benchmark harness"),
    ("deploy", "local PostgreSQL profile: validate | up | down | status"),
    ("inventory", "component/version/sha256 matrix + toolchain"),
    ("hygiene", "repository hygiene report for the production trunks"),
    ("architecture", "layer model + dependency-direction gate"),
    ("coverage", "engine capability vs. what each application exercises"),
    ("capabilities", "the capability registry and how a row is classified"),
    ("sut-manifests", "the SUT registry: canonical/reference/experimental + exclusions"),
    ("release", "release reproducibility report"),
    ("provenance", "provenance report for a run"),
)

_VERB_HELP = "subcommands (run `bundle_run <verb> --help` for each):\n" + "\n".join(
    f"  {name:<15} {blurb}" for name, blurb in _VERBS)


def main():
    # `bundle plan <spec-dir>` (STEP 10) is a side-effect-free subcommand — kept
    # as a thin argv dispatch ahead of the legacy single-purpose parser so the
    # existing `bundle_run.py <spec-dir> [options]` invocation stays untouched.
    if len(sys.argv) > 1 and sys.argv[1] == "plan":
        return _main_plan(sys.argv[2:])
    # `bundle doctor` (STEP 15) is likewise side-effect-free w.r.t. any run/DB
    # state — diagnostics live entirely outside the legacy single-run parser.
    if len(sys.argv) > 1 and sys.argv[1] == "doctor":
        return _main_doctor(sys.argv[2:])
    # `bundle resume <run-dir|run-id>` (STEP 24): continue an interrupted/failed
    # run in place -- its own parser/dispatch, like plan/doctor above, since it
    # operates on an *existing* run directory rather than starting a fresh one.
    if len(sys.argv) > 1 and sys.argv[1] == "resume":
        return _main_resume(sys.argv[2:])
    # `bundle cancel <run-dir|run-id>` / `bundle cleanup <run-dir|run-id>`
    # (STEP 25): act on an *existing* run directory from a second invocation,
    # exactly like resume above -- own parsers/dispatch ahead of the legacy
    # single-run parser.
    if len(sys.argv) > 1 and sys.argv[1] == "cancel":
        return _main_cancel(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] == "cleanup":
        return _main_cleanup(sys.argv[2:])
    # `bundle constraints explain|dry-run <spec-dir>` (STEP 35): show each constraint's
    # quantitative effect BEFORE the destructive sieve. Side-effect-free (dry-run deletes nothing).
    if len(sys.argv) > 1 and sys.argv[1] == "constraints":
        return _main_constraints(sys.argv[2:])
    # `bundle iterate <spec-dir> --iterations N --analyzer ...`: close the BundleSeed feedback loop.
    if len(sys.argv) > 1 and sys.argv[1] == "iterate":
        return _main_iterate(sys.argv[2:])
    # `bundle bench --profile 10K --stages generator,sieve` (STEP 40): per-stage
    # benchmark harness. Side-effect-free (writes only a report). 100M/1B never auto-run.
    if len(sys.argv) > 1 and sys.argv[1] == "bench":
        return _main_bench(sys.argv[2:])
    # `bundle deploy validate|up|down|status` (STEP 41): reproducible LOCAL dev DB
    # stack (containers). `down` preserves data by default; runtime-gated (reports
    # BLOCKED, never auto-installs Docker).
    if len(sys.argv) > 1 and sys.argv[1] == "deploy":
        return _main_deploy(sys.argv[2:])
    # `bundle inventory` (STEP 42): machine-readable component version/hash matrix
    # (+ optional baseline compare with a warn/block policy, + optional SBOM).
    if len(sys.argv) > 1 and sys.argv[1] == "inventory":
        return _main_inventory(sys.argv[2:])
    # `bundle hygiene` (STEP 43): inventory backups + verify the production compile
    # source set excludes them + propose archival. Report-only; never deletes/moves.
    if len(sys.argv) > 1 and sys.argv[1] == "hygiene":
        return _main_hygiene(sys.argv[2:])
    # `bundle architecture` / `bundle coverage`: the engine-first boundary gate and
    # the reference-capability audit. Both are side-effect-free source analyses —
    # no DB, no JAR, no run directory.
    if len(sys.argv) > 1 and sys.argv[1] == "architecture":
        return _main_architecture(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] == "coverage":
        return _main_coverage(sys.argv[2:])
    # `bundle capabilities`: the generated support matrix. Side-effect-free.
    if len(sys.argv) > 1 and sys.argv[1] == "capabilities":
        return _main_capabilities(sys.argv[2:])
    # `bundle sut-manifests`: validate the canonical SUT adapter manifests.
    if len(sys.argv) > 1 and sys.argv[1] == "sut-manifests":
        return _main_sut_manifests(sys.argv[2:])
    # `bundle release`: release manifest + SBOM + classified skips.
    if len(sys.argv) > 1 and sys.argv[1] == "release":
        return _main_release(sys.argv[2:])
    # `bundle provenance`: publication evidence. Non-operative.
    if len(sys.argv) > 1 and sys.argv[1] == "provenance":
        return _main_provenance(sys.argv[2:])
    ap = argparse.ArgumentParser(
        prog="bundle_run", description="One command: Core->Reader->Executor->Analyzer.",
        epilog=_VERB_HELP, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec_dir")
    ap.add_argument("--db", default="")
    ap.add_argument("--lang", default="py", choices=["py", "python", "java"],
                    help="candidate source language; java routes the validated handoff to MainWatch")
    # STEP 13: these four flags double as `BundleConfig` settings
    # (main_db_port/results_db_port/run_mode/analyzer_goals) — `_UNSET` lets an
    # *unspecified* flag fall through to BUNDLE_<KEY>/--config-file/defaults
    # instead of always shadowing them with a hardcoded "convenience" default
    # (see `_CLI_ARG_TO_CONFIG_KEY`/`_resolve_bundle_config`). The values shown
    # here are what an unconfigured install still gets — `BundleConfig`'s own
    # defaults (`main_db_port=5433`, `run_mode="verdict"`, ...).
    ap.add_argument("--main-port", type=int, default=_UNSET, metavar="PORT",
                    help=f"main DB port (default: {BundleConfig().main_db_port})")
    ap.add_argument("--results-port", type=int, default=_UNSET, metavar="PORT",
                    help=f"results DB port (default: {BundleConfig().results_db_port})")
    ap.add_argument("--analyzer", default=_UNSET,
                    help='run AnalyzeKv with these goals, e.g. "dq_score:max,latency_ms:min" (default: disabled)')
    ap.add_argument("--analysis-mode", default="exploratory", choices=["formal", "exploratory"],
                    help="formal = explicit goals only, NO auto-discovered axes, fixed directions, "
                         "corpus count required; exploratory = auto-discover + label inferred axes "
                         "(default: exploratory)")
    ap.add_argument("--mode", default=_UNSET, choices=["verdict", "stress"],
                    help="verdict = language-specific Executor; stress = py_stress "
                         f"(combinatorial storm) (default: {BundleConfig().run_mode!r})")
    ap.add_argument("--sieve", action="store_true",
                    help="apply the spec's constraint sidecar (params/constraints) to fw_final between Core and Reader")
    ap.add_argument("--draw", action="store_true",
                    help="before Core, open the browser link editor (Firefox) so the user draws "
                         "forbidden/required value bonds by hand; the submitted sidecar replaces the "
                         "spec's constraints and is applied by the sieve (implies --sieve; an empty "
                         "submission is a no-op, as if --sieve was off)")
    ap.add_argument("--draw-exact", action="store_true",
                    help="like --draw but runs AFTER Core so the editor shows EXACT live impact over "
                         "the whole assembled space (fw_final x optional combos), honest about "
                         "FW_Optional bonds; needs a live DB. Implies --sieve")
    ap.add_argument("--seed-from", default="", metavar="PATH",
                    help="consume a previous bundle_seed.json (or run dir containing it) and derive bias constraints before the sieve")
    ap.add_argument("--base-url", default="http://127.0.0.1:8121", help="[stress] live SUT to flood")
    ap.add_argument("--workers", type=int, default=24, help="[stress] concurrent worker count (the downpour)")
    ap.add_argument("--duration", type=float, default=10, help="[stress] sustain seconds")
    ap.add_argument("--ramp", type=float, default=3, help="[stress] ramp-up seconds")
    ap.add_argument("--slo-p99", type=float, default=1500, help="[stress] p99 latency budget (ms)")
    ap.add_argument("--err-budget", type=float, default=0.01, help="[stress] tolerated 5xx/conn error rate")
    ap.add_argument("--run-id", default="",
                    help="explicit run identity (default: auto-minted '<UTC timestamp>-<hex>', "
                         "collision-checked so a duplicate never overwrites a prior run.json)")
    ap.add_argument("--runs-root", default="",
                    help="directory under which run directories are created "
                         "(default: '<scratch>/runs'); each run gets its own "
                         "'<runs-root>/<run-id>/' that all stage artifacts live under")
    ap.add_argument("--legacy-scratch", action="store_true",
                    help="compatibility/rollback: skip run-directory + run.json/state.json creation, "
                         "and write stage artifacts directly into the shared pre-STEP-4 scratch layout")
    ap.add_argument("--legacy-handoff", action="store_true",
                    help="STEP 20 explicit compatibility mode: skip the Handoff v2 manifest "
                         "(wait/validate/run-ID-and-count check) between Reader and Executor, "
                         "repair the legacy fwVar.shift handshake file, and run the Executor "
                         "against the legacy directory handshake instead — visibly opt-in only")
    # STEP 12 budget gates, now folded into `BundleConfig` (STEP 13 action 3:
    # "budgets" is one of the things layered config must cover — see
    # `BundleConfig.budget_*`/`_budget_limits_from_config`). Each ceiling
    # accepts a number or 'none'/'unlimited' to disable that dimension
    # explicitly (never an implicit zero). `_UNSET` (not the `BudgetLimits`
    # default!) lets an unspecified flag fall through to BUNDLE_BUDGET_*/
    # --config-file/defaults — `None` is itself a valid *resolved* value here
    # ("no limit configured"), so it cannot double as the "not given" sentinel.
    # The defaults shown in --help are `BundleConfig`'s own — generous enough
    # that existing small/bounded runs (e.g. the 288-candidate reference) pass
    # with no override (action 6).
    _add_budget_ceiling_args(ap)
    ap.add_argument("--override-budget", default=None, metavar="REASON",
                    help="explicit non-empty reason to proceed despite a hard budget threshold "
                         "exceed; rejected if empty, recorded verbatim in the run manifest "
                         "(action 4: explicit flag + non-empty reason + manifest record)")
    ap.add_argument("--allow-extreme", action="store_true",
                    help="required (independent of --override-budget) to start a run classified "
                         "X / extreme (action 5)")
    ap.add_argument("--unleash-initial-productivity-power", dest="unleash_initial_productivity_power",
                    default=_UNSET, action="store_const", const=True,
                    help="lift the limiter: the budget gate becomes advisory (hard ceilings warn, "
                         "don't block) and X/extreme runs need no --allow-extreme -- Core at full "
                         "generative power. Layered like any config "
                         "(CLI > BUNDLE_UNLEASH_INITIAL_PRODUCTIVITY_POWER > config file > default False).")
    ap.add_argument("--cost-per-candidate", type=float, default=None, metavar="PRICE",
                    help="flat monetary cost per candidate (e.g. cloud/API price); without this, "
                         "the monetary-cost dimension has no projection and --budget-monetary-cost "
                         "can never be evaluated or block a run")
    # STEP 13: typed BundleConfig — CLI > environment (BUNDLE_<KEY>) > config
    # file (--config-file, JSON object of the same keys) > defaults. Every flag
    # here defaults to `_UNSET` ("not given"): an unspecified flag must not
    # shadow the environment/config-file layers beneath it — only an explicit
    # override wins at "CLI" precedence (see `_resolve_bundle_config`).
    _add_bundle_config_args(ap)
    ap.add_argument("--debug", action="store_true",
                    help="show full traceback on failure instead of a concise '✗ <message>' line")
    a = ap.parse_args()
    try:
        _run(a)
    except BundleError as exc:
        report_and_exit(exc, debug=a.debug)
    except KeyboardInterrupt:
        # The active stage's journal.stage() context manager has already
        # written INTERRUPTED for the stage and the run (state.json) before
        # this propagates here — this is just the concise top-level report.
        if a.debug:
            raise
        print("\n  ✗ interrupted")
        sys.exit(130)
