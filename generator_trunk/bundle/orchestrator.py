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

"""The run orchestrator: the five-stage pipeline and its resume cascade.

Extracted from `cli.py` (2026-08-05). It reaches its stages through an injected
`StageTable` rather than module-global rebinding, which is what makes living
here rather than in `cli` a detail instead of a breaking change.
"""
from __future__ import annotations

import dataclasses
import json
import os
from . import invariants, shards
from .budgets import blocking_checks, evaluate_budgets, warning_checks
from .cliutil import (
    _budget_limits_from_config,
    _resolve_bundle_config,
    _resolve_execution_policy,
    _with_db,
)
from .config import BundleConfig, config_to_dict
from .controlplane import write_plan_json
from .counts import count_plan
from .database import psql, sql_identifier, sql_literal
from .errors import BudgetError, PreflightError, StageError, ok
from .handoff import HandoffError, handoff_from_dict
from .journal import NullJournal, RunJournal
from .jsonio import write_json_atomic
from .models import RunStatus, SchemaError, analysis_block
from .optional_contract import OptionalContractError, contract_from_spec, verify_materialized
from .policy import (
    PolicyIdentityError,
    authorization_from_dict,
    policy_id,
    required_backend,
    verify_same_policy,
)
from .resources import RunClass, estimate_resources
from .resume import (
    ResumeError,
    artifacts_match,
    count_actual,
    dir_artifact,
    file_artifact,
    read_stage,
    succeeded_with_invariants,
)
from .runs import create_run, file_sha256
from .stages import (
    CORE_JAR,
    CORE_PROPS,
    JAVA_EXECUTOR_JAR,
    JAVA_JARS_DIR,
    PY_EXECUTOR,
    READER_JAR,
    READER_PROPS,
    SRC,
    capability_gate,
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
from .stagetable import StageTable
from pathlib import Path


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


def default_stage_table() -> StageTable:
    """The production seam: every collaborator bound to its real implementation.

    Resolved from this module's globals at call time, so the historical
    ``bundle.cli.stage_gen = ...`` override still works for any caller that has
    not migrated to passing a `StageTable`. New callers should inject instead --
    that is what lets the orchestrator live anywhere.
    """
    return StageTable(
        gen=stage_gen, core=stage_core, sieve=stage_sieve, draw=stage_draw,
        seed_bias=stage_seed_bias, reader=stage_reader, executor=stage_executor,
        analyzer=stage_analyzer, stress=stage_stress,
        component_artifacts=_stage_component_artifacts,
        optional_tables=_optional_tables,
        record_handoff_manifest=_record_handoff_manifest,
    )


def _run(a, *, stages: 'StageTable | None' = None) -> None:
    st = stages if stages is not None else default_stage_table()
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
    # A t-wise request is applied by the sieve stage; enabling it here, before the run
    # directory records its settings, also makes resume re-apply or reuse it.
    if fg.coverage_requested(spec):
        a.sieve = True
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
        spec.constraints, spec.params = st.draw(spec, work, cfg)
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
        xlsx = st.gen(a.spec_dir, work)
        _record_artifacts(rec, file_artifact("input.spec", toml_path),
                          file_artifact("output.workbook", xlsx),
                          *st.component_artifacts("gen", cfg))
    with journal.stage("core", log_path=work / "core.log") as rec:
        fw_final = st.core(spec, xlsx, work, a.db, a.main_port, n_opt, cfg,
                              optional_contract=optional_contract)
        rec.count("fw_final", actual=fw_final, expected=core_est)
        # Audit F4: prove Core actually built every fw_opt<size> the Reader is
        # about to consume. A missing table would otherwise surface as an opaque
        # Reader failure or, worse, a silently short candidate corpus.
        if optional_contract.active:
            try:
                verify_materialized(optional_contract, st.optional_tables(cfg, a.main_port, a.db))
            except OptionalContractError as exc:
                raise StageError(str(exc))
            rec.count("optional_multiplier", actual=optional_contract.expected_multiplier())
        _record_artifacts(rec, file_artifact("input.workbook", xlsx),
                          *st.component_artifacts("core", cfg))
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
        spec.constraints, spec.params = st.draw(spec, work, cfg, exact=True,
                                                   db=a.db, main_port=a.main_port)
    if getattr(a, "seed_from", ""):
        with journal.stage("seed_bias") as rec:
            bias = st.seed_bias(spec, work, a.db, a.main_port, a.seed_from, cfg)
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
            fw_final = st.sieve(spec, work, a.db, a.main_port, fw_final, cfg)
            rec.count("post_sieve", actual=fw_final)
            _record_artifacts(rec, *st.component_artifacts("sieve", cfg))
            rec.invariant(invariants.post_sieve_le_core(fw_final, pre_sieve))
            invariants.enforce(rec.invariants)
        full = fw_final * optional_factor
    run_id = run_layout.run_id if run_layout else None
    manifest = None
    manifest_path = None
    with journal.stage("reader", log_path=work / "reader.log") as rec:
        src, hs, n_cands, n_empty, manifest_path = st.reader(
            work, a.db, a.lang, a.main_port, a.results_port, fw_final, n_opt, full, a.mode == "stress",
            cfg, run_id=run_id, legacy_handoff=a.legacy_handoff, policy_ref=policy_id(policy),
            optional_contract=optional_contract)
        rec.count("candidates", actual=n_cands, expected=full)
        # Record the manifest only after _persist_handoff_policy stamps its
        # execution_policy_ref; resume must hash the finalized on-disk document.
        _record_artifacts(rec, _candidate_artifact("output.candidates", src, ext),
                          *st.component_artifacts("reader", cfg))
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
        manifest = st.record_handoff_manifest(rec, manifest_path, run_id, n_cands, a.legacy_handoff)
        invariants.enforce(rec.invariants)
    if a.mode == "stress":
        with journal.stage("stress"):
            st.stress(src, hs, a.db, a.results_port, a)
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
            processed, passed, failed, broken, inserted, db_total, timeout, infra_fail, v2_counts = st.executor(
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
                              *st.component_artifacts("executor", cfg, a.lang))
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
            st.analyzer(src, work, a.analyzer, cfg=cfg,
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
            _record_artifacts(rec, *artifacts, *st.component_artifacts("analyzer", cfg))
            expected_metrics = repeat_metric_rows if repeat_metric_rows is not None else n_cands
            rec.count("metrics_lines", actual=metrics_lines, expected=expected_metrics)
            rec.invariant(invariants.analyzer_input_matches_metrics(expected_metrics, metrics_lines))
            invariants.enforce(rec.invariants)
    journal.mark_run(RunStatus.SUCCEEDED)
    where = f"run '{run_layout.run_id}' ({run_layout.root})" if run_layout else f"scratch {scratch}"
    print(f"\n✓ DONE — {a.db}: full Bundle chain green. {where}")
    return run_layout


# --------------------------------- resume (STEP 24) -------------------------- #
def _resume_run(layout, manifest, spec, toml_path, cfg, *, spec_changed: bool = False,
                stages: 'StageTable | None' = None) -> None:
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
    st = stages if stages is not None else default_stage_table()
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
                     *st.component_artifacts("gen", cfg))
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
            xlsx = st.gen(str(Path(toml_path).parent), work)
            _record_artifacts(rec, file_artifact("input.spec", toml_path),
                              file_artifact("output.workbook", xlsx),
                              *st.component_artifacts("gen", cfg))
    trusted = reuse_gen

    # ---- core: reusable iff upstream trusted, prior SUCCEEDED, and fw_final's
    # live row count still matches what that run recorded (the closest
    # observable proxy for "input hash unchanged" Bundle has without re-running
    # Core itself: same spec + same workbook + same n_opt -> same row count) --
    core_prior = read_stage(layout, "core")
    recorded_fw_final = count_actual(core_prior, "fw_final")
    reuse_core = False
    core_artifacts = (file_artifact("input.workbook", xlsx), *st.component_artifacts("core", cfg))
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
            verify_materialized(optional_contract, st.optional_tables(cfg, main_port, db))
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
            fw_final = st.core(spec, xlsx, work, db, main_port, n_opt, cfg,
                                  optional_contract=optional_contract)
            rec.count("fw_final", actual=fw_final, expected=core_est)
            if optional_contract.active:
                try:
                    verify_materialized(optional_contract, st.optional_tables(cfg, main_port, db))
                except OptionalContractError as exc:
                    raise StageError(str(exc))
                rec.count("optional_multiplier", actual=optional_factor)
            _record_artifacts(rec, file_artifact("input.workbook", xlsx),
                              *st.component_artifacts("core", cfg))
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
        sieve_artifacts = st.component_artifacts("sieve", cfg)
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
                fw_final = st.sieve(spec, work, db, main_port, fw_final, cfg)
                rec.count("post_sieve", actual=fw_final)
                _record_artifacts(rec, *st.component_artifacts("sieve", cfg))
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
                        *st.component_artifacts("reader", cfg)]
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
            src, hs, n_cands, n_empty, manifest_path = st.reader(
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
                              *st.component_artifacts("reader", cfg))
            rec.invariant(invariants.reader_emitted_eq_expected(n_cands, full))
            rec.invariant(invariants.reader_empty_zero(n_empty))
            handoff_manifest = st.record_handoff_manifest(rec, manifest_path, run_id, n_cands, legacy_handoff)
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
                          *st.component_artifacts("executor", cfg, lang))
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
            processed, passed, failed, broken, inserted, db_total, timeout, infra_fail, v2_counts = st.executor(
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
                              *st.component_artifacts("executor", cfg, lang))
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
                              *st.component_artifacts("analyzer", cfg))
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
                st.analyzer(src, work, analyzer_goals, cfg=cfg,
                               mode=settings.get("analysis_mode", "exploratory"), corpus_count=n_cands,
                               run_id=run_id or "", harvested_metrics=work / "metrics.kv")
                metrics_lines = sum(1 for _ in kv.open(encoding="utf-8")) if kv.exists() else 0
                prov_artifacts = ((file_artifact("output.provenance", work / "provenance.json"),)
                                  if (work / "provenance.json").exists() else ())
                _record_artifacts(rec, _candidate_artifact("input.candidates", src, ext),
                                  file_artifact("output.metrics", kv),
                                  *prov_artifacts,
                                  *st.component_artifacts("analyzer", cfg))
                expected_metrics = repeat_metric_rows if repeat_metric_rows is not None else n_cands
                rec.count("metrics_lines", actual=metrics_lines, expected=expected_metrics)
                rec.invariant(invariants.analyzer_input_matches_metrics(expected_metrics, metrics_lines))
                invariants.enforce(rec.invariants)

    journal.mark_run(RunStatus.SUCCEEDED)
    print(f"\n✓ DONE — {db}: resumed run '{layout.run_id}' ({layout.root}) green.")
