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

# --- re-exports -------------------------------------------------------------
# The implementations moved to `cliutil`/`cliargs`/`commands/` (2026-08-05). They
# stay importable and patchable as `bundle.cli.<name>` so existing callers and
# tests keep working unchanged.
from .cliutil import (  # noqa: E402
    _UNSET,
    _CLI_ARG_TO_CONFIG_KEY,
    _resolve_execution_policy,
    _resolve_bundle_config,
    _with_db,
    _load_one_spec,
    _budget_limits_from_config,
)
from .cliargs import (  # noqa: E402
    _optional_number,
    _add_budget_ceiling_args,
    _add_repeat_args,
    _add_bundle_config_args,
)
from .commands.cleanup import (  # noqa: E402
    cmd_cleanup,
    _main_cleanup,
)
from .commands.plan import (  # noqa: E402
    PLAN_SCHEMA,
    _slot_summary,
    _plan_warnings,
    cmd_plan,
    _main_plan,
)
from .commands.constraints import (  # noqa: E402
    _table_count,
    cmd_constraints,
    _main_constraints,
)
from .commands.doctor import (  # noqa: E402
    cmd_doctor,
    _main_doctor,
)
from .commands.bench import (  # noqa: E402
    cmd_bench,
    _main_bench,
)
from .commands.hygiene import (  # noqa: E402
    cmd_hygiene,
    _main_hygiene,
)
from .commands.inventory import (  # noqa: E402
    cmd_inventory,
    _main_inventory,
)
from .commands.architecture import (  # noqa: E402
    cmd_architecture,
    _main_architecture,
)
from .commands.coverage import (  # noqa: E402
    cmd_coverage,
    _main_coverage,
)
from .commands.capabilities import (  # noqa: E402
    cmd_capabilities,
    _main_capabilities,
)
from .commands.sut_manifests import (  # noqa: E402
    cmd_sut_manifests,
    _main_sut_manifests,
)
from .commands.release import (  # noqa: E402
    cmd_release,
    _main_release,
)
from .commands.provenance import (  # noqa: E402
    cmd_provenance,
    _main_provenance,
)
from .commands.deploy import (  # noqa: E402
    cmd_deploy,
    _main_deploy,
)
from .commands.iterate import (  # noqa: E402
    ITERATE_SCHEMA,
    _stage_count_value,
    _winner_candidate_id,
    _seed_front_ids,
    _cmd_iterate,
    _main_iterate,
)
