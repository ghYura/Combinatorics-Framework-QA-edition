#!/usr/bin/env python3
"""Generate a fresh, provider-neutral release-gate breakpoint exchange."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import secrets
import shutil
import sys
import tempfile
from typing import Iterable

if __package__:
    from ...reporting import reconcile_run
    from .config import (
        DEFAULT_DIFFICULTY_UNITS,
        ReleaseGateSuiteConfig,
        TargetCell,
        load_suite_config,
        suite_config,
    )
    from .exchange import materialize_release_gate_spec, write_release_exchange_package
    from .runner import (
        bundle_plan_command,
        bundle_run_command,
        drop_ephemeral_databases,
        run_checked,
        runtime_environment,
    )
    from .runtime import rg_solve
    from .task_factory import (
        generate_release_gate_ladder,
        new_release_holdout_seed,
        release_seed_commitment,
    )
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from AI_combi_testing_platform.reporting import reconcile_run
    from AI_combi_testing_platform.sub_suites.release_gate_breakpoint.config import (
        DEFAULT_DIFFICULTY_UNITS,
        ReleaseGateSuiteConfig,
        TargetCell,
        load_suite_config,
        suite_config,
    )
    from AI_combi_testing_platform.sub_suites.release_gate_breakpoint.exchange import (
        materialize_release_gate_spec,
        write_release_exchange_package,
    )
    from AI_combi_testing_platform.sub_suites.release_gate_breakpoint.runner import (
        bundle_plan_command,
        bundle_run_command,
        drop_ephemeral_databases,
        run_checked,
        runtime_environment,
    )
    from AI_combi_testing_platform.sub_suites.release_gate_breakpoint.runtime import (
        rg_solve,
    )
    from AI_combi_testing_platform.sub_suites.release_gate_breakpoint.task_factory import (
        generate_release_gate_ladder,
        new_release_holdout_seed,
        release_seed_commitment,
    )


HERE = Path(__file__).resolve().parent
FRAMEWORK_SOURCE = HERE.parents[3]


def _target(value: str) -> TargetCell:
    fields = value.split("::")
    if len(fields) != 3:
        raise argparse.ArgumentTypeError(
            "target must be PROVIDER::EXACT_MODEL_LABEL::EFFORT_LABEL"
        )
    try:
        return TargetCell(*fields)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _difficulty_units(value: str) -> tuple[int, ...]:
    try:
        units = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "difficulty units must be comma-separated integers"
        ) from exc
    if not units:
        raise argparse.ArgumentTypeError("at least one difficulty size is required")
    return units


def _configuration(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
) -> ReleaseGateSuiteConfig:
    if args.config is not None:
        if args.target or args.difficulty_units is not None:
            parser.error("--config cannot be combined with --target or --difficulty-units")
        try:
            return load_suite_config(args.config)
        except ValueError as exc:
            parser.error(str(exc))
    if not args.target:
        parser.error("provide --config or at least one --target")
    try:
        return suite_config(
            args.target,
            difficulty_units=args.difficulty_units or DEFAULT_DIFFICULTY_UNITS,
        )
    except ValueError as exc:
        parser.error(str(exc))


def _safe_evidence(run_dir: Path) -> dict[str, object]:
    evidence = reconcile_run(run_dir)
    return {
        "core": evidence["core"],
        "reader": evidence["reader"],
        "reader_expected": evidence["reader_expected"],
        "processed": evidence["processed"],
        "pass": evidence["pass"],
        "domain_fail": evidence["domain_fail"],
        "metrics_lines": evidence["metrics_lines"],
        "formal_candidates_seen": evidence["formal_candidates_seen"],
        "unexpected_outcomes": sum(
            int(evidence["outcomes"].get(name, 0) or 0)
            for name in (
                "BROKEN",
                "TIMEOUT",
                "INFRA_FAIL",
                "CANCELLED",
                "SKIPPED",
            )
        ),
        "all_reconciliation_checks": all(evidence["checks"].values()),
    }


def _inside_framework_source(path: Path) -> bool:
    try:
        path.relative_to(FRAMEWORK_SOURCE)
    except ValueError:
        return False
    return True


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument(
        "--target",
        action="append",
        type=_target,
        help="repeatable PROVIDER::EXACT_MODEL_LABEL::EFFORT_LABEL target cell",
    )
    parser.add_argument("--difficulty-units", type=_difficulty_units)
    parser.add_argument("--main-host", default="127.0.0.1")
    parser.add_argument("--main-port", type=int, default=5433)
    parser.add_argument("--main-user", default="postgres")
    parser.add_argument("--results-host", default="127.0.0.1")
    parser.add_argument("--results-port", type=int, default=5432)
    parser.add_argument("--results-user", default="postgres")
    args = parser.parse_args(list(argv) if argv is not None else None)
    config = _configuration(parser, args)

    destination = args.out.resolve()
    if destination.exists():
        parser.error("--out must not already exist")
    if _inside_framework_source(destination):
        parser.error("--out must be outside the Framework source checkout")
    destination.parent.mkdir(parents=True, exist_ok=True)

    env = runtime_environment(
        os.environ.copy(),
        main_host=args.main_host,
        main_user=args.main_user,
        results_host=args.results_host,
        results_user=args.results_user,
    )
    missing = [
        key
        for key in ("BUNDLE_MAIN_DB_PASSWORD", "BUNDLE_RESULTS_DB_PASSWORD")
        if not env.get(key)
    ]
    if missing:
        parser.error("set " + " and ".join(missing))

    seed = new_release_holdout_seed()
    generated = generate_release_gate_ladder(seed, config.difficulty_units)
    for row in generated:
        if rg_solve(row.task) != row.planted_answer:
            raise RuntimeError("independent runtime oracle disagrees with planted answer")
    tasks = [row.task for row in generated]
    db_name = "ai_combi_release_gate_" + secrets.token_hex(6)
    run_id = "ai-combi-release-gate-" + secrets.token_hex(6)
    staging_root = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.staging-",
            dir=destination.parent,
        )
    )
    staging = staging_root / "exchange"
    run_error: Exception | None = None
    cleanup_error: Exception | None = None
    safe_evidence: dict[str, object] = {}
    try:
        with tempfile.TemporaryDirectory(
            prefix="ai-combi-release-gate-run-"
        ) as temporary:
            root = Path(temporary)
            spec = materialize_release_gate_spec(root / "spec", tasks)
            try:
                run_checked(
                    bundle_plan_command(
                        spec,
                        root / "plan",
                        config.constructor_candidate_count,
                    ),
                    env=env,
                )
                run_checked(
                    bundle_run_command(
                        spec,
                        db_name=db_name,
                        run_id=run_id,
                        runs_root=root / "runs",
                        scratch_root=root / "scratch",
                        main_port=args.main_port,
                        results_port=args.results_port,
                        candidate_count=config.constructor_candidate_count,
                    ),
                    env=env,
                )
                run_dir = root / "runs" / run_id
                safe_evidence = _safe_evidence(run_dir)
                candidates = sorted((run_dir / "src").rglob("*.py"))
                write_release_exchange_package(
                    staging,
                    tasks=tasks,
                    config=config,
                    seed_commitment=release_seed_commitment(seed),
                    spec=spec,
                    reader_candidates=candidates,
                    bundle_evidence=safe_evidence,
                )
            except Exception as exc:
                run_error = exc
            finally:
                try:
                    drop_ephemeral_databases(
                        db_name,
                        main_host=args.main_host,
                        main_port=args.main_port,
                        main_user=args.main_user,
                        results_host=args.results_host,
                        results_port=args.results_port,
                        results_user=args.results_user,
                        env=env,
                    )
                except Exception as exc:
                    cleanup_error = exc
        if cleanup_error is not None:
            raise cleanup_error
        if run_error is not None:
            raise run_error
        staging.rename(destination)
        staging_root.rmdir()
        print(f"CREATED: {destination}")
        print(
            f"CORE_ROWS={safe_evidence['core']} "
            f"READER_CANDIDATES={safe_evidence['reader']} "
            f"EXECUTOR_PROCESSED={safe_evidence['processed']} "
            f"BREAKPOINT_PROMPTS={config.request_count} "
            f"FOLLOWUP_DESIGN_ROWS=10"
        )
        print("TEMP_SPEC_PLAN_RUN_SCRATCH_AND_DATABASES_REMOVED=true")
        return 0
    except Exception:
        shutil.rmtree(staging_root, ignore_errors=True)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
