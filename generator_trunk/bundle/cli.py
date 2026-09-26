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
from .stagetable import StageTable
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


def cmd_resume(a, *, stages: 'StageTable | None' = None) -> None:
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
    spec, toml_path = _load_one_spec(Path(manifest.spec_path))
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
    _resume_run(layout, manifest, spec, toml_path, cfg, spec_changed=spec_changed,
                stages=stages)


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
    ("triage", "group a finished run's failures into findings + minimal witnesses"),
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
    ("report", "render a finished run as a readable HTML page (Face 3)"),
)

_VERB_HELP = "subcommands (run `bundle_run <verb> --help` for each):\n" + "\n".join(
    f"  {name:<15} {blurb}" for name, blurb in _VERBS)


def main(*, stages: 'StageTable | None' = None):
    # `bundle plan <spec-dir>` (STEP 10) is a side-effect-free subcommand — kept
    # as a thin argv dispatch ahead of the legacy single-purpose parser so the
    # existing `bundle_run.py <spec-dir> [options]` invocation stays untouched.
    if len(sys.argv) > 1 and sys.argv[1] == "plan":
        return _main_plan(sys.argv[2:])
    # `bundle doctor` (STEP 15) is likewise side-effect-free w.r.t. any run/DB
    # state — diagnostics live entirely outside the legacy single-run parser.
    if len(sys.argv) > 1 and sys.argv[1] == "doctor":
        return _main_doctor(sys.argv[2:])
    # `bundle triage <run>` (post-run): group a finished run's failures into
    # distinct findings with a minimal witness each. Like plan/doctor it is
    # side-effect-free -- it reads what the run persisted and never re-executes
    # a candidate.
    if len(sys.argv) > 1 and sys.argv[1] == "triage":
        from .commands.triage import _main_triage
        return _main_triage(sys.argv[2:])
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
    # `bundle report <run>` (Face 3): render a finished run as readable HTML.
    # Reads only what the run already recorded — no DB, no stage, no re-execution.
    if len(sys.argv) > 1 and sys.argv[1] == "report":
        return _main_report(sys.argv[2:])
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
        _run(a, stages=stages)
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
from .commands.report import (  # noqa: E402
    cmd_report,
    _main_report,
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

# --- orchestrator ------------------------------------------------------------
# `_run`/`_resume_run` and their helpers moved to `orchestrator` (2026-08-05).
# Re-exported so `bundle.cli.<name>` keeps resolving for existing callers; note
# that PATCHING them now belongs on `bundle.orchestrator`, where they are defined.
from .orchestrator import (  # noqa: E402
    _stage_component_artifacts,
    _candidate_pattern,
    _candidate_artifact,
    _record_artifacts,
    _require_executor_summary,
    _results_v2_latest_attempt_candidates,
    _results_v2_next_attempt,
    _reset_owned_legacy_results,
    _expected_verdicts,
    _check_budgets,
    _build_component_inventory,
    _optional_tables,
    _create_run_directory,
    _persist_handoff_policy,
    _record_handoff_manifest,
    default_stage_table,
    _run,
    _resume_run,
)
