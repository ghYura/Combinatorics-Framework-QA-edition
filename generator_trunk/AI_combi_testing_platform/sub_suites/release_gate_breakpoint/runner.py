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

"""Safe local Bundle planning, execution, and ephemeral-database cleanup."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys


HERE = Path(__file__).resolve().parent
FRAMEWORK_ROOT = HERE.parents[3]
BUNDLE = FRAMEWORK_ROOT / "generator_trunk" / "bundle_run.py"
RELEASE_GOALS = (
    "correct:max,format_ok:max,semantic_correct:max,difficulty_units:max,"
    "construction_states:max,input_tokens:min,cost_microusd:min"
)
_EPHEMERAL_DB_RE = re.compile(r"ai_combi_release_gate_[a-f0-9]{12}")


class ReleaseGateRunError(RuntimeError):
    """A local Bundle command or mandatory cleanup did not succeed."""


#: Provider credentials are stripped BY PATTERN, not by a fixed list of vendor
#: variable names. A named list leaks silently the moment a new provider appears
#: and nobody remembers to extend it; a pattern fails closed instead.
_CREDENTIAL_NAME = re.compile(
    r"(API_KEY|ACCESS_TOKEN|AUTH_TOKEN|SESSION_TOKEN|BEARER|SECRET|CREDENTIALS?|PASSWORD)$"
)


def without_provider_credentials(env: dict[str, str]) -> dict[str, str]:
    """Drop every variable whose name marks it as a credential."""
    return {k: v for k, v in env.items() if not _CREDENTIAL_NAME.search(k.upper())}


def run_checked(command: list[str], *, env: dict[str, str]) -> None:
    completed = subprocess.run(
        command,
        cwd=FRAMEWORK_ROOT,
        env=env,
        check=False,
    )
    if completed.returncode:
        raise ReleaseGateRunError(
            f"Bundle command failed with exit code {completed.returncode}"
        )


def bundle_plan_command(
    spec: Path,
    destination: Path,
    candidate_count: int,
) -> list[str]:
    return [
        sys.executable,
        str(BUNDLE),
        "plan",
        str(spec),
        "--out",
        str(destination),
        "--repeat",
        "1",
        "--repeat-policy",
        "local",
        "--repeat-scope",
        "all",
        "--budget-requests",
        str(candidate_count),
        "--cost-per-candidate",
        "0",
    ]


def bundle_run_command(
    spec: Path,
    *,
    db_name: str,
    run_id: str,
    runs_root: Path,
    scratch_root: Path,
    main_port: int,
    results_port: int,
    candidate_count: int,
) -> list[str]:
    return [
        sys.executable,
        str(BUNDLE),
        str(spec),
        "--db",
        db_name,
        "--run-id",
        run_id,
        "--runs-root",
        str(runs_root),
        "--scratch-root",
        str(scratch_root),
        "--main-port",
        str(main_port),
        "--results-port",
        str(results_port),
        "--lang",
        "py",
        "--candidate-sink",
        "loose-files",
        "--execution-policy-profile",
        "generated-default",
        "--analyzer",
        RELEASE_GOALS,
        "--analysis-mode",
        "formal",
        "--repeat",
        "1",
        "--repeat-policy",
        "local",
        "--repeat-scope",
        "all",
        "--budget-requests",
        str(candidate_count),
        "--cost-per-candidate",
        "0",
        "--allow-extreme",
        "--override-budget",
        "reviewed bounded fourth-order release-gate prompt construction",
    ]


def drop_ephemeral_databases(
    db_name: str,
    *,
    main_host: str,
    main_port: int,
    main_user: str,
    results_host: str,
    results_port: int,
    results_user: str,
    env: dict[str, str],
) -> None:
    if not _EPHEMERAL_DB_RE.fullmatch(db_name):
        raise ReleaseGateRunError("refusing cleanup of a non-ephemeral database name")
    targets = (
        (main_host, main_port, main_user, env["BUNDLE_MAIN_DB_PASSWORD"]),
        (
            results_host,
            results_port,
            results_user,
            env["BUNDLE_RESULTS_DB_PASSWORD"],
        ),
    )
    failures: list[str] = []
    for host, port, user, password in dict.fromkeys(targets):
        drop_env = env.copy()
        drop_env["PGPASSWORD"] = password
        try:
            completed = subprocess.run(
                [
                    "psql",
                    "-X",
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-h",
                    host,
                    "-p",
                    str(port),
                    "-U",
                    user,
                    "-d",
                    "postgres",
                    "-c",
                    f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE);',
                ],
                cwd=FRAMEWORK_ROOT,
                env=drop_env,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            failures.append(f"{host}:{port}")
            continue
        if completed.returncode:
            failures.append(f"{host}:{port}")
    if failures:
        raise ReleaseGateRunError(
            "ephemeral replay database cleanup failed at " + ",".join(failures)
        )


def runtime_environment(
    source: dict[str, str],
    *,
    main_host: str,
    main_user: str,
    results_host: str,
    results_user: str,
) -> dict[str, str]:
    env = without_provider_credentials(source)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.update(
        {
            "BUNDLE_MAIN_DB_HOST": main_host,
            "BUNDLE_MAIN_DB_USER": main_user,
            "BUNDLE_RESULTS_DB_HOST": results_host,
            "BUNDLE_RESULTS_DB_USER": results_user,
        }
    )
    framework = str(FRAMEWORK_ROOT)
    python_path = [
        item for item in env.get("PYTHONPATH", "").split(os.pathsep) if item
    ]
    if framework not in python_path:
        env["PYTHONPATH"] = os.pathsep.join((framework, *python_path))
    return env
