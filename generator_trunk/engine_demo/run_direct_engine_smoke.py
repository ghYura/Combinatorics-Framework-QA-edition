#!/usr/bin/env python3
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

"""Launcher for the direct engine demonstration.

`list` / `plan` are side-effect-free and need no database. `run` executes the
bounded full chain: Generator -> Core -> Reader -> Executor -> persistence ->
formal Analyzer.

This launcher is deliberately thin. It does not re-implement lifecycle, budget,
policy or evidence logic — it invokes the canonical `bundle_run.py` entry point
as a subprocess, which is the documented boundary a reference application (or a
demonstration) is supposed to use. A second orchestrator would be a second
source of truth.

Planning always precedes execution: the brace chain's cardinality is genuinely
runtime-known, so the plan reports UNKNOWN and the run carries an explicit,
recorded bounded materialization gate instead of pretending to a count nobody
can compute in advance.

Database endpoint selection (`run` only) is explicit and coherent. There is no
implicit host-PostgreSQL default: `run` refuses to start until `--db-endpoint`
names *one* source for the ports **and** the credentials, so the demonstration
can never appear to exercise the deployed stack while actually writing into an
unrelated host cluster. Endpoint resolution reuses `bundle.deploy`'s existing
`.env` parsing — this module introduces no second secret loader.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
GENERATOR_TRUNK = HERE.parent
FRAMEWORK_ROOT = GENERATOR_TRUNK.parent
BUNDLE = GENERATOR_TRUNK / "bundle_run.py"

# Run as a script, `sys.path[0]` is this directory, so the sibling `bundle`
# package is not importable. Endpoint resolution reuses `bundle.deploy` rather
# than re-parsing deploy/.env here, so make that import work the same way
# `bundle_run.py` gets it.
if str(GENERATOR_TRUNK) not in sys.path:
    sys.path.insert(0, str(GENERATOR_TRUNK))

SCENARIO = "direct_engine_smoke"
SPEC_DIR = HERE / SCENARIO
GOALS = "stages:max,retained:max,ops:min"

# The brace chain materializes 8 roots. The gate is set just above that so a
# structural regression that multiplies the space (typically a missing
# FW_Exclude on an intermediate brace target) fails the run instead of quietly
# executing hundreds of redundant candidates.
BUDGET_FINAL_CANDIDATES = 64
BUDGET_MANDATORY_ROWS = 64
OVERRIDE_REASON = ("bounded direct engine smoke: higher-order brace cardinality is "
                   "runtime-known and capped by explicit budgets")

DEFAULT_DB_HOST = "127.0.0.1"

# Every ambient `BUNDLE_*` database variable. Once an endpoint is selected these
# are stripped from the child environment and re-set from that one source, so a
# process environment left over from another cluster can neither redirect the
# run nor supply half of its connection settings.
_AMBIENT_DB_ENV_KEYS = (
    "BUNDLE_MAIN_DB_HOST", "BUNDLE_MAIN_DB_PORT",
    "BUNDLE_MAIN_DB_USER", "BUNDLE_MAIN_DB_PASSWORD",
    "BUNDLE_RESULTS_DB_HOST", "BUNDLE_RESULTS_DB_PORT",
    "BUNDLE_RESULTS_DB_USER", "BUNDLE_RESULTS_DB_PASSWORD",
)

_PASSWORD_ENV_KEYS = ("BUNDLE_MAIN_DB_PASSWORD", "BUNDLE_RESULTS_DB_PASSWORD")


class EndpointError(SystemExit):
    """An ambiguous, incomplete or inconsistent database-endpoint selection.

    Raised as a `SystemExit` so the launcher keeps its single "print the reason,
    exit non-zero" failure mode; the message never carries a credential value.
    """


@dataclass(frozen=True)
class Endpoint:
    """One coherent database selection: ports and credentials from a single
    source. The password fields are `repr=False` so an accidental `print(ep)`,
    traceback or log line cannot leak them — only `credential_source` (a
    provenance label) is ever displayed."""
    main_host: str
    main_port: int
    results_host: str
    results_port: int
    user: str
    endpoint_source: str
    credential_source: str
    main_password: str = field(repr=False, default="")
    results_password: str = field(repr=False, default="")

    def banner(self, db_name: str) -> str:
        """Preflight banner: what was resolved and where it came from. Prints the
        credential *source* only — never a credential value."""
        return "\n".join((
            "direct engine smoke — resolved database endpoint",
            f"  endpoint source   : {self.endpoint_source}",
            f"  credential source : {self.credential_source} (value not shown)",
            f"  main DB           : {self.main_host}:{self.main_port}/{db_name}",
            f"  results DB        : {self.results_host}:{self.results_port}/{db_name}",
            f"  database user     : {self.user}",
        ))

    def child_env(self, base_env) -> "dict[str, str]":
        """The child `bundle_run.py` environment: ambient `BUNDLE_*` database
        variables removed, then re-set from this endpoint alone."""
        env = {k: v for k, v in base_env.items() if k not in _AMBIENT_DB_ENV_KEYS}
        env.update({
            "BUNDLE_MAIN_DB_HOST": self.main_host,
            "BUNDLE_MAIN_DB_PORT": str(self.main_port),
            "BUNDLE_MAIN_DB_USER": self.user,
            "BUNDLE_MAIN_DB_PASSWORD": self.main_password,
            "BUNDLE_RESULTS_DB_HOST": self.results_host,
            "BUNDLE_RESULTS_DB_PORT": str(self.results_port),
            "BUNDLE_RESULTS_DB_USER": self.user,
            "BUNDLE_RESULTS_DB_PASSWORD": self.results_password,
        })
        return env


def _deploy_overlay():
    """The deploy stack's `config_overlay()` (host/ports/user/password from
    `generator_trunk/deploy/.env`), or `None` when the deploy extra is not
    installed. Import is local so `list`/`plan` never require PyYAML."""
    try:
        from bundle import deploy  # noqa: PLC0415 - keep `plan` dependency-free
    except ImportError:
        return None
    try:
        return deploy.config_overlay()
    except Exception as exc:                       # DeployError: no .env yet
        raise EndpointError(
            f"--db-endpoint deploy: {exc}\n"
            f"Start the local stack first: "
            f"python generator_trunk/bundle_run.py deploy up") from exc


def _deploy_overlay_if_available():
    """Best-effort deploy overlay used only for the consistency guard below.
    Any failure (extra not installed, no `.env`, unreadable) means "nothing to
    compare against" and must never block an otherwise valid manual selection."""
    try:
        from bundle import deploy  # noqa: PLC0415
        return deploy.config_overlay()
    except Exception:
        return None


def resolve_endpoint(args, env=None, *, overlay=None, probe_overlay=None) -> Endpoint:
    """Resolve the `run` stage's database endpoint from exactly one source.

    `overlay`/`probe_overlay` are injection points for the tests; production
    calls leave them `None` and go through `bundle.deploy`.
    """
    env = os.environ if env is None else env
    choice = getattr(args, "db_endpoint", None)

    if choice is None:
        raise EndpointError(
            "the run stage needs an explicit database endpoint: pass "
            "--db-endpoint deploy (the local `bundle deploy up` stack) or "
            "--db-endpoint manual together with --main-port/--results-port.\n"
            "There is deliberately no implicit host-PostgreSQL default — an "
            "implicit 5433/5432 made the demonstration look like it exercised "
            "the deployed stack while writing into an unrelated host cluster.")

    if choice == "deploy":
        # Ports and credentials must arrive together. Accepting an explicit port
        # here would mean "deploy credentials, operator ports" — precisely the
        # mixed selection this function exists to prevent.
        conflicting = [flag for flag, value in (("--main-port", args.main_port),
                                                ("--results-port", args.results_port),
                                                ("--main-host", args.main_host),
                                                ("--results-host", args.results_host))
                       if value is not None]
        if conflicting:
            raise EndpointError(
                f"--db-endpoint deploy already supplies the connection settings from "
                f"deploy/.env; refusing to also apply {', '.join(conflicting)}. "
                f"Drop the flag(s), or use --db-endpoint manual to specify every "
                f"setting yourself.")
        data = overlay if overlay is not None else _deploy_overlay()
        if data is None:
            raise EndpointError(
                "--db-endpoint deploy requires the deployment extra: "
                "python -m pip install -e '.[deploy]'")
        return Endpoint(
            main_host=data["main_db_host"], main_port=int(data["main_db_port"]),
            results_host=data["results_db_host"], results_port=int(data["results_db_port"]),
            user=data["main_db_user"],
            main_password=data["main_db_password"],
            results_password=data["results_db_password"],
            endpoint_source="deploy/.env (local deploy stack)",
            credential_source="deploy/.env",
        )

    # --- manual -------------------------------------------------------------
    missing_ports = [flag for flag, value in (("--main-port", args.main_port),
                                              ("--results-port", args.results_port))
                     if value is None]
    if missing_ports:
        raise EndpointError(
            f"--db-endpoint manual requires {' and '.join(missing_ports)}. "
            f"Ports are never defaulted: the demonstration must not pick a "
            f"PostgreSQL endpoint on the operator's behalf.")

    missing_creds = [key for key in _PASSWORD_ENV_KEYS if not env.get(key)]
    if missing_creds:
        raise EndpointError(
            f"--db-endpoint manual reads credentials from the environment, but "
            f"{' and '.join(missing_creds)} {'is' if len(missing_creds) == 1 else 'are'} "
            f"not set; the run stage needs both database passwords.")

    endpoint = Endpoint(
        main_host=args.main_host or DEFAULT_DB_HOST,
        main_port=int(args.main_port),
        results_host=args.results_host or DEFAULT_DB_HOST,
        results_port=int(args.results_port),
        user=env.get("BUNDLE_MAIN_DB_USER", "postgres"),
        main_password=env["BUNDLE_MAIN_DB_PASSWORD"],
        results_password=env["BUNDLE_RESULTS_DB_PASSWORD"],
        endpoint_source="--main-port/--results-port (manual)",
        credential_source="environment (BUNDLE_MAIN_DB_PASSWORD/BUNDLE_RESULTS_DB_PASSWORD)",
    )

    # Consistency guard: manual ports that address the deploy stack, with
    # ambient credentials that are not the deploy stack's, would authenticate the
    # deployed containers with a foreign secret. Fail rather than let the
    # operator discover it as an auth error halfway through a chain.
    probe = probe_overlay if probe_overlay is not None else _deploy_overlay_if_available()
    if probe:
        addresses_deploy = (
            endpoint.main_host == probe["main_db_host"]
            and endpoint.main_port == int(probe["main_db_port"])
        ) or (
            endpoint.results_host == probe["results_db_host"]
            and endpoint.results_port == int(probe["results_db_port"])
        )
        mismatched = (endpoint.main_password != probe["main_db_password"]
                      or endpoint.results_password != probe["results_db_password"])
        if addresses_deploy and mismatched:
            raise EndpointError(
                "inconsistent selection: the manual ports address the local deploy "
                "stack, but the environment's credentials are not the ones in "
                "deploy/.env. Use --db-endpoint deploy to take ports and "
                "credentials from that file as one coherent source, or point the "
                "manual ports at the cluster those credentials belong to.")
    return endpoint


def _plan_command(out_dir: Path) -> "list[str]":
    return [sys.executable, str(BUNDLE), "plan", str(SPEC_DIR), "--out", str(out_dir)]


def _run_command(args: argparse.Namespace, endpoint: Endpoint) -> "list[str]":
    return [
        sys.executable, str(BUNDLE), str(SPEC_DIR),
        "--db", args.db,
        "--run-id", args.run_id,
        "--runs-root", str(args.runs_root.resolve()),
        "--main-port", str(endpoint.main_port),
        "--results-port", str(endpoint.results_port),
        "--lang", "py",
        # Checked-in, reviewed candidate source in this repository: the reviewed
        # trusted-local origin class. Generated or imported candidates must not
        # reuse this profile.
        "--execution-policy-profile", "trusted-local",
        "--candidate-origin", "reviewed-checked-in",
        "--acknowledge-trusted-local", "reviewed checked-in scenario fragments in this repository",
        "--analyzer", GOALS,
        "--analysis-mode", "formal",
        "--allow-extreme",
        "--override-budget", OVERRIDE_REASON,
        "--budget-final-candidates", str(BUDGET_FINAL_CANDIDATES),
        "--budget-mandatory-rows", str(BUDGET_MANDATORY_ROWS),
    ]


def _checked(command: "list[str]", env=None) -> None:
    completed = subprocess.run(command, cwd=FRAMEWORK_ROOT, check=False, env=env)
    if completed.returncode:
        raise SystemExit(completed.returncode)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("list", "plan", "run"))
    parser.add_argument("--db", default="engine_demo_smoke")
    parser.add_argument("--run-id", default="direct-engine-smoke")
    parser.add_argument("--runs-root", type=Path, default=Path("/tmp/fw_work"))
    parser.add_argument("--plan-out", type=Path, default=Path("/tmp/engine-demo-plan"))
    parser.add_argument("--db-endpoint", choices=("deploy", "manual"), default=None,
                        help="run only: where the database ports AND credentials come from. "
                             "'deploy' reads generator_trunk/deploy/.env (the local `bundle "
                             "deploy up` stack); 'manual' requires --main-port/--results-port "
                             "and reads BUNDLE_MAIN_DB_PASSWORD/BUNDLE_RESULTS_DB_PASSWORD "
                             "from the environment. There is no default.")
    # No port defaults, by design: an implicit 5433/5432 silently targeted the
    # host PostgreSQL while the output looked like a deploy-stack run.
    parser.add_argument("--main-port", type=int, default=None,
                        help="main DB port; required with --db-endpoint manual")
    parser.add_argument("--results-port", type=int, default=None,
                        help="results DB port; required with --db-endpoint manual")
    parser.add_argument("--main-host", default=None,
                        help=f"main DB host with --db-endpoint manual (default: {DEFAULT_DB_HOST})")
    parser.add_argument("--results-host", default=None,
                        help=f"results DB host with --db-endpoint manual (default: {DEFAULT_DB_HOST})")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "list":
        print(f"{SCENARIO}\t{SPEC_DIR}")
        print(f"  goals: {GOALS} (formal)")
        print(f"  bounded gate: final<={BUDGET_FINAL_CANDIDATES}, mandatory<={BUDGET_MANDATORY_ROWS}")
        return 0

    # Resolve (and print) the endpoint BEFORE planning: an incomplete or
    # inconsistent selection is an operator error that should surface
    # immediately, not after a full plan has been computed. `plan` itself never
    # reaches this and stays a no-database operation.
    endpoint = None
    if args.command == "run":
        endpoint = resolve_endpoint(args)
        # Flush before any subprocess writes: the children inherit this stdout
        # fd and would otherwise print ahead of our buffered banner.
        print(endpoint.banner(args.db), end="\n\n", flush=True)

    _checked(_plan_command(args.plan_out))
    if args.command == "plan":
        return 0

    _checked(_run_command(args, endpoint), env=endpoint.child_env(os.environ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
