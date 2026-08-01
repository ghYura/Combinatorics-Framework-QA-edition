#!/usr/bin/env python3
"""Plan, test, and optionally execute the complete LLM architecture suite."""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
GENERATOR = HERE.parent
sys.path.insert(0, str(GENERATOR))

from bundle.database import psql, sql_identifier, sql_literal  # noqa: E402

BUNDLE = GENERATOR / "bundle_run.py"
SPECS = {
    "arch_grid": {
        "goals": "params:min,latency_ms:min,proxy_gradnorm:max",
        "sieve": False,
        "expected": 48,
    },
    "arch_order": {
        "goals": "params:min,latency_ms:min,proxy_gradnorm:max",
        "sieve": False,
        "expected": 6,
    },
    "arch_optional": {
        "goals": "params:min,proxy_gradnorm:max",
        "sieve": False,
        "expected": 24,
    },
    "arch_compat": {
        "goals": "params:min,latency_ms:min,proxy_gradnorm:max",
        "sieve": True,
        "expected": 8,
    },
}
DEFENSE_NAME = "arch_compat_no_sieve"
_PREFIX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,41}$")


def run(command, env=None):
    print("+", " ".join(map(str, command)), flush=True)
    subprocess.run(
        [str(part) for part in command],
        cwd=GENERATOR,
        env=env,
        check=True,
    )


def validate_prefix(prefix):
    if not _PREFIX.fullmatch(prefix):
        raise ValueError(
            "prefix must be 1-42 characters matching "
            "[A-Za-z0-9][A-Za-z0-9._-]*"
        )
    return prefix


def database_name(prefix, scenario):
    name = f"{prefix}_{scenario}".replace("-", "_").replace(".", "_").lower()
    if len(name) > 63:
        raise ValueError("generated PostgreSQL database name exceeds 63 characters")
    return name


def run_directory(scratch_root, db_name, run_id):
    return Path(scratch_root) / db_name / "runs" / run_id


def _cardinality_summary(cardinality):
    return {
        key: {
            field: cardinality[key].get(field)
            for field in ("mode", "value", "lower", "upper", "formula")
        }
        for key in ("mandatory", "post_sieve", "optional_multiplier", "final")
    }


def plan_summary(plan):
    return {
        "schema": plan["schema"],
        "spec_name": plan["spec_name"],
        "spec_version": plan["spec_version"],
        "spec_sha256": plan["spec_sha256"],
        "constraints_present": plan["constraints_present"],
        "cardinality": _cardinality_summary(plan["cardinality"]),
        "graph_hash": plan["dependency_graph"]["graph_hash"],
        "warnings": plan["warnings"],
    }


def parse_run(run_dir):
    state = json.loads((run_dir / "state.json").read_text())
    summary = json.loads((run_dir / "executor-summary.json").read_text())
    provenance = json.loads((run_dir / "provenance.json").read_text())
    return {
        "run_dir": str(run_dir),
        "status": state["status"],
        "processed": summary["processed"],
        "outcomes": summary["outcomes"],
        "analyzer_seen": provenance["candidates_seen"],
        "pareto_count": len(provenance["candidates"]),
        "provenance_ok": provenance["provenance_ok"],
    }


def _has_expected_code_8(metrics):
    required = {
        "app=arch_compat",
        "d_model=64",
        "n_heads=6",
        "divisible=0",
        "code=8",
        "FW_VAR=1",
        "FW_CUSTOM_VAR=8",
    }
    return any(required.issubset(set(line.split())) for line in metrics.splitlines())


def parse_executor_run(run_dir):
    state = json.loads((run_dir / "state.json").read_text())
    summary = json.loads((run_dir / "executor-summary.json").read_text())
    metrics_path = run_dir / "metrics.kv"
    metrics = metrics_path.read_text() if metrics_path.exists() else ""
    return {
        "run_dir": str(run_dir),
        "status": state["status"],
        "processed": summary["processed"],
        "outcomes": summary["outcomes"],
        "expected_code_8_seen": _has_expected_code_8(metrics),
    }


def require_counts(label, result, expected_pass, expected_domain_fail=0, analyzer=False):
    expected_total = expected_pass + expected_domain_fail
    failures = []
    if result["status"] != "SUCCEEDED":
        failures.append(f"status={result['status']}")
    if result["processed"] != expected_total:
        failures.append(f"processed={result['processed']} expected={expected_total}")
    outcomes = result["outcomes"]
    if outcomes.get("PASS") != expected_pass:
        failures.append(f"PASS={outcomes.get('PASS')} expected={expected_pass}")
    if outcomes.get("DOMAIN_FAIL") != expected_domain_fail:
        failures.append(
            f"DOMAIN_FAIL={outcomes.get('DOMAIN_FAIL')} expected={expected_domain_fail}"
        )
    for outcome in ("BROKEN", "TIMEOUT", "INFRA_FAIL", "SKIPPED", "CANCELLED"):
        if outcomes.get(outcome, 0) != 0:
            failures.append(f"{outcome}={outcomes[outcome]}")
    if analyzer:
        if result["analyzer_seen"] != expected_total:
            failures.append(
                f"analyzer_seen={result['analyzer_seen']} expected={expected_total}"
            )
        if not result["provenance_ok"]:
            failures.append("provenance_ok=false")
    if failures:
        raise AssertionError(f"{label}: " + "; ".join(failures))


def require_defense(result):
    require_counts(DEFENSE_NAME, result, 8, expected_domain_fail=1)
    if not result["expected_code_8_seen"]:
        raise AssertionError(
            "no-sieve defense did not record the exact 64/6 fail-loud verdict"
        )


def _database_settings(args, env, results=False):
    prefix = "RESULTS" if results else "MAIN"
    default_port = args.results_port if results else args.main_port
    return {
        "host": env.get(f"BUNDLE_{prefix}_DB_HOST", "127.0.0.1"),
        "user": env.get(f"BUNDLE_{prefix}_DB_USER", "postgres"),
        "password": env[f"BUNDLE_{prefix}_DB_PASSWORD"],
        "port": default_port,
    }


def _database_exists(name, settings):
    out, return_code = psql(
        settings["port"],
        "postgres",
        "select 1 from pg_database where datname=" + sql_literal(name) + ";",
        host=settings["host"],
        user=settings["user"],
        password=settings["password"],
    )
    if return_code != 0:
        raise RuntimeError("failed to inspect PostgreSQL database %r" % name)
    return out == "1"


def _drop_database(name, settings):
    _out, return_code = psql(
        settings["port"],
        "postgres",
        "drop database if exists %s with (force);" % sql_identifier(name),
        host=settings["host"],
        user=settings["user"],
        password=settings["password"],
    )
    if return_code != 0:
        raise RuntimeError("failed to drop PostgreSQL database %r" % name)


def _write_report(path, report):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(f"verification report: {path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--full",
        action="store_true",
        help="run all specs through PostgreSQL, Executor, and Analyzer",
    )
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--main-port", type=int, default=5433)
    parser.add_argument("--results-port", type=int, default=5432)
    parser.add_argument(
        "--scratch-root",
        type=Path,
        default=Path(os.environ.get("BUNDLE_SCRATCH_ROOT", "/tmp/fw_work")),
    )
    parser.add_argument(
        "--prefix",
        default=datetime.now(timezone.utc).strftime("archsuite-%Y%m%dT%H%M%SZ"),
        help="unique DB/run prefix",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="report path (defaults to a full or plan-only filename)",
    )
    parser.add_argument(
        "--keep-dbs",
        action="store_true",
        help="retain the five temporary PostgreSQL databases for inspection",
    )
    args = parser.parse_args()
    try:
        validate_prefix(args.prefix)
    except ValueError as error:
        parser.error(str(error))
    if args.workers < 1:
        parser.error("--workers must be >= 1")
    if not (1 <= args.main_port <= 65535 and 1 <= args.results_port <= 65535):
        parser.error("database ports must be in 1..65535")
    report_path = args.report or HERE / (
        "verification_report.json" if args.full else "verification_plan_report.json"
    )

    report = {
        "schema": "llm-arch-search.verification/v2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "prefix": args.prefix,
        "full": args.full,
        "status": "RUNNING",
        "plans": {},
        "runs": {},
        "defense_in_depth": {},
        "database_cleanup": {
            "retained": bool(args.keep_dbs),
            "targets": [],
            "databases": [],
            "errors": [],
        },
    }
    failure = None
    cleanup_failure = None
    owned_database_names = []
    database_settings = []
    try:
        run([sys.executable, HERE / "_selfcheck.py"])
        run([sys.executable, "-m", "pytest", HERE / "test_arch_search.py", "-q"])

        with tempfile.TemporaryDirectory(prefix="llm-arch-plan-") as temp_dir:
            for name in SPECS:
                plan_dir = Path(temp_dir) / name
                run([
                    sys.executable,
                    BUNDLE,
                    "plan",
                    HERE / name,
                    "--out",
                    plan_dir,
                ])
                plan = json.loads((plan_dir / "plan.json").read_text())
                report["plans"][name] = plan_summary(plan)

        if args.full:
            env = dict(os.environ)
            for variable in (
                "BUNDLE_MAIN_DB_PASSWORD",
                "BUNDLE_RESULTS_DB_PASSWORD",
            ):
                if not env.get(variable):
                    raise RuntimeError(f"{variable} must be set for --full")

            planned_database_names = [
                database_name(args.prefix, name)
                for name in (*SPECS, DEFENSE_NAME)
            ]
            database_settings = [
                _database_settings(args, env, results=False),
                _database_settings(args, env, results=True),
            ]
            collisions = [
                f"{settings['host']}:{settings['port']}/{name}"
                for name in planned_database_names
                for settings in database_settings
                if _database_exists(name, settings)
            ]
            if collisions:
                raise RuntimeError(
                    "refusing to reuse pre-existing verification DB(s): "
                    + ", ".join(collisions)
                )
            owned_database_names = planned_database_names
            report["database_cleanup"]["targets"] = [
                f"{settings['host']}:{settings['port']}/{name}"
                for name in owned_database_names
                for settings in database_settings
            ]

            for name, config in SPECS.items():
                db_name = database_name(args.prefix, name)
                run_id = f"{args.prefix}-{name}"
                command = [
                    sys.executable,
                    BUNDLE,
                    HERE / name,
                    "--db",
                    db_name,
                    "--main-port",
                    args.main_port,
                    "--results-port",
                    args.results_port,
                    "--scratch-root",
                    args.scratch_root,
                    "--execution-policy-profile",
                    "trusted-local",
                    "--candidate-origin",
                    "reviewed-checked-in",
                    "--acknowledge-trusted-local",
                    "reviewed checked-in llm_arch_search scenario fragments in this repository",
                    "--analyzer",
                    config["goals"],
                    "--analysis-mode",
                    "formal",
                    "--workers",
                    args.workers,
                    "--run-id",
                    run_id,
                ]
                if config["sieve"]:
                    command.append("--sieve")
                run(command, env=env)
                run_dir = run_directory(args.scratch_root, db_name, run_id)
                result = parse_run(run_dir)
                report["runs"][name] = result
                require_counts(name, result, config["expected"], analyzer=True)

            db_name = database_name(args.prefix, DEFENSE_NAME)
            run_id = f"{args.prefix}-{DEFENSE_NAME}"
            run([
                sys.executable,
                BUNDLE,
                HERE / "arch_compat",
                "--db",
                db_name,
                "--main-port",
                args.main_port,
                "--results-port",
                args.results_port,
                "--scratch-root",
                args.scratch_root,
                "--execution-policy-profile",
                "trusted-local",
                "--candidate-origin",
                "reviewed-checked-in",
                "--acknowledge-trusted-local",
                "reviewed checked-in llm_arch_search scenario fragments in this repository",
                "--workers",
                args.workers,
                "--run-id",
                run_id,
            ], env=env)
            run_dir = run_directory(args.scratch_root, db_name, run_id)
            defense = parse_executor_run(run_dir)
            report["defense_in_depth"][DEFENSE_NAME] = defense
            require_defense(defense)

        report["status"] = "SUCCEEDED"
    except BaseException as error:
        failure = error
        report["status"] = "FAILED"
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        if args.full and owned_database_names and not args.keep_dbs:
            for name in owned_database_names:
                for settings in database_settings:
                    target = f"{settings['host']}:{settings['port']}/{name}"
                    try:
                        _drop_database(name, settings)
                        report["database_cleanup"]["databases"].append(target)
                    except Exception as error:
                        report["database_cleanup"]["errors"].append(
                            f"{target}: {type(error).__name__}: {error}"
                        )
            if report["database_cleanup"]["errors"]:
                cleanup_failure = RuntimeError(
                    "temporary database cleanup failed: "
                    + "; ".join(report["database_cleanup"]["errors"])
                )
                if failure is None:
                    report["status"] = "FAILED"
                    report["error"] = str(cleanup_failure)
        _write_report(report_path, report)

    if failure is not None:
        raise failure.with_traceback(failure.__traceback__)
    if cleanup_failure is not None:
        raise cleanup_failure


if __name__ == "__main__":
    main()
