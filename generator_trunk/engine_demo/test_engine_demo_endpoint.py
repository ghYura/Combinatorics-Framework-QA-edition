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

"""Regression tests for the direct engine demonstration's database-endpoint
selection.

Self-contained: no database, no network, no container runtime. Every test
injects its own overlay, so a machine that happens to have a real
`generator_trunk/deploy/.env` cannot change an outcome here.

What these pin down — the demonstration used to default to `--main-port 5433
--results-port 5432` and pick up whatever `BUNDLE_*_DB_PASSWORD` the shell
happened to export. On a host with its own PostgreSQL that silently ran the
whole chain against the host cluster while the output read like a deploy-stack
run. The rules below are what replaced it:

* no implicit port defaults, ever;
* ports and credentials always come from ONE selected source;
* a mixed or inconsistent selection fails loudly instead of connecting;
* credential *values* never reach stdout, a repr, or a traceback.
"""
from __future__ import annotations

import argparse

import pytest

from generator_trunk.engine_demo import run_direct_engine_smoke as demo

#: Stand-in for `bundle.deploy.config_overlay()` — the deploy stack's ports,
#: user and password as one coherent mapping.
DEPLOY_OVERLAY = {
    "main_db_host": "127.0.0.1", "results_db_host": "127.0.0.1",
    "main_db_port": 15433, "results_db_port": 15432,
    "main_db_user": "postgres", "results_db_user": "postgres",
    "main_db_password": "deploy-secret", "results_db_password": "deploy-secret",
}

#: A shell that exports credentials for an unrelated cluster — the exact
#: condition that made the original defect invisible.
AMBIENT_ENV = {
    "BUNDLE_MAIN_DB_PASSWORD": "host-cluster-secret",
    "BUNDLE_RESULTS_DB_PASSWORD": "host-cluster-secret",
    "PATH": "/usr/bin",
}


def _args(**overrides) -> argparse.Namespace:
    """A parsed-args namespace with the launcher's real defaults."""
    base = dict(db_endpoint=None, main_port=None, results_port=None,
                main_host=None, results_host=None, db="engine_demo_smoke")
    base.update(overrides)
    return argparse.Namespace(**base)


# --------------------------------------------------- no implicit defaults ----
def test_port_flags_have_no_default_at_the_parser_level() -> None:
    """The regression itself: argparse must not carry 5433/5432 any more."""
    parsed = demo.build_parser().parse_args(["run"])
    assert parsed.main_port is None
    assert parsed.results_port is None
    assert parsed.db_endpoint is None


def test_plan_and_list_need_no_endpoint_selection() -> None:
    """`plan`/`list` stay database-free: parsing must succeed with nothing set."""
    for command in ("list", "plan"):
        parsed = demo.build_parser().parse_args([command])
        assert parsed.command == command
        assert parsed.db_endpoint is None


def test_run_without_an_endpoint_selection_is_refused() -> None:
    with pytest.raises(SystemExit) as excinfo:
        demo.resolve_endpoint(_args(), env={}, probe_overlay={})
    message = str(excinfo.value)
    assert "--db-endpoint" in message
    # The error must teach the safe choices, not merely complain.
    assert "deploy" in message and "manual" in message


def test_refusal_never_silently_falls_back_to_host_ports() -> None:
    """No path through resolution may yield 5433/5432 unless asked for them."""
    with pytest.raises(SystemExit):
        demo.resolve_endpoint(_args(), env=AMBIENT_ENV, probe_overlay={})
    # …and a manual selection missing its ports is refused rather than defaulted.
    with pytest.raises(SystemExit) as excinfo:
        demo.resolve_endpoint(_args(db_endpoint="manual"),
                              env=AMBIENT_ENV, probe_overlay={})
    assert "--main-port" in str(excinfo.value)


# ------------------------------------------------------ explicit selection ---
def test_manual_selection_uses_cli_ports_and_environment_credentials() -> None:
    endpoint = demo.resolve_endpoint(
        _args(db_endpoint="manual", main_port=5433, results_port=5432),
        env=AMBIENT_ENV, probe_overlay={})
    assert (endpoint.main_host, endpoint.main_port) == ("127.0.0.1", 5433)
    assert (endpoint.results_host, endpoint.results_port) == ("127.0.0.1", 5432)
    assert endpoint.main_password == "host-cluster-secret"
    assert "manual" in endpoint.endpoint_source
    assert "environment" in endpoint.credential_source


def test_manual_selection_honours_explicit_hosts() -> None:
    endpoint = demo.resolve_endpoint(
        _args(db_endpoint="manual", main_port=6000, results_port=6001,
              main_host="::1", results_host="::1"),
        env=AMBIENT_ENV, probe_overlay={})
    assert endpoint.main_host == "::1" and endpoint.results_host == "::1"


@pytest.mark.parametrize("missing", ["BUNDLE_MAIN_DB_PASSWORD",
                                     "BUNDLE_RESULTS_DB_PASSWORD"])
def test_manual_selection_requires_both_passwords(missing: str) -> None:
    env = {k: v for k, v in AMBIENT_ENV.items() if k != missing}
    with pytest.raises(SystemExit) as excinfo:
        demo.resolve_endpoint(
            _args(db_endpoint="manual", main_port=5433, results_port=5432),
            env=env, probe_overlay={})
    assert missing in str(excinfo.value)


def test_stripped_environment_is_refused_for_manual() -> None:
    """A clean shell must fail closed, naming both missing variables."""
    with pytest.raises(SystemExit) as excinfo:
        demo.resolve_endpoint(
            _args(db_endpoint="manual", main_port=5433, results_port=5432),
            env={}, probe_overlay={})
    message = str(excinfo.value)
    assert "BUNDLE_MAIN_DB_PASSWORD" in message
    assert "BUNDLE_RESULTS_DB_PASSWORD" in message


# -------------------------------------------------------- deploy selection ---
def test_deploy_selection_takes_ports_and_credentials_from_the_env_file() -> None:
    endpoint = demo.resolve_endpoint(_args(db_endpoint="deploy"),
                                     env={}, overlay=DEPLOY_OVERLAY)
    assert (endpoint.main_port, endpoint.results_port) == (15433, 15432)
    assert endpoint.main_password == "deploy-secret"
    assert endpoint.credential_source == "deploy/.env"


def test_deploy_selection_ignores_hostile_ambient_credentials() -> None:
    """Ambient credentials for another cluster must not reach the child."""
    endpoint = demo.resolve_endpoint(_args(db_endpoint="deploy"),
                                     env=AMBIENT_ENV, overlay=DEPLOY_OVERLAY)
    assert endpoint.main_password == "deploy-secret"
    child = endpoint.child_env(AMBIENT_ENV)
    assert child["BUNDLE_MAIN_DB_PASSWORD"] == "deploy-secret"
    assert child["BUNDLE_RESULTS_DB_PASSWORD"] == "deploy-secret"
    assert "host-cluster-secret" not in child.values()


@pytest.mark.parametrize("flag,value", [("main_port", 5433), ("results_port", 5432),
                                        ("main_host", "10.0.0.1"), ("results_host", "10.0.0.1")])
def test_deploy_selection_refuses_mixed_connection_flags(flag: str, value) -> None:
    """Deploy credentials with operator-chosen ports is exactly the mixture the
    endpoint contract forbids."""
    with pytest.raises(SystemExit) as excinfo:
        demo.resolve_endpoint(_args(db_endpoint="deploy", **{flag: value}),
                              env={}, overlay=DEPLOY_OVERLAY)
    assert flag.replace("_", "-") in str(excinfo.value)


# ------------------------------------------------ inconsistency is refused ---
def test_manual_ports_addressing_the_deploy_stack_with_foreign_credentials() -> None:
    """The subtle case: right ports, wrong secret. Refuse before connecting."""
    with pytest.raises(SystemExit) as excinfo:
        demo.resolve_endpoint(
            _args(db_endpoint="manual", main_port=15433, results_port=15432),
            env=AMBIENT_ENV, probe_overlay=DEPLOY_OVERLAY)
    message = str(excinfo.value)
    assert "inconsistent selection" in message
    assert "--db-endpoint deploy" in message


def test_manual_ports_matching_deploy_credentials_are_allowed() -> None:
    """Same ports, and the credentials really are the deploy stack's — coherent."""
    env = {"BUNDLE_MAIN_DB_PASSWORD": "deploy-secret",
           "BUNDLE_RESULTS_DB_PASSWORD": "deploy-secret"}
    endpoint = demo.resolve_endpoint(
        _args(db_endpoint="manual", main_port=15433, results_port=15432),
        env=env, probe_overlay=DEPLOY_OVERLAY)
    assert endpoint.main_port == 15433


def test_manual_selection_of_an_unrelated_cluster_is_unaffected() -> None:
    """A genuine host cluster stays usable — the guard is about the deploy ports."""
    endpoint = demo.resolve_endpoint(
        _args(db_endpoint="manual", main_port=5433, results_port=5432),
        env=AMBIENT_ENV, probe_overlay=DEPLOY_OVERLAY)
    assert endpoint.main_port == 5433


# ------------------------------------------------------------- redaction -----
def test_banner_reports_sources_and_never_credential_values() -> None:
    endpoint = demo.resolve_endpoint(_args(db_endpoint="deploy"),
                                     env=AMBIENT_ENV, overlay=DEPLOY_OVERLAY)
    banner = endpoint.banner("engine_demo_smoke")
    assert "deploy-secret" not in banner
    assert "host-cluster-secret" not in banner
    # …while still stating everything an operator needs to identify the target.
    for expected in ("127.0.0.1:15433", "127.0.0.1:15432", "engine_demo_smoke",
                     "deploy/.env", "postgres"):
        assert expected in banner


def test_repr_does_not_leak_credentials() -> None:
    """`repr` reaches tracebacks and logs, so the password fields are repr=False."""
    endpoint = demo.resolve_endpoint(_args(db_endpoint="deploy"),
                                     env={}, overlay=DEPLOY_OVERLAY)
    assert "deploy-secret" not in repr(endpoint)


def test_child_env_strips_every_ambient_database_variable() -> None:
    """Whatever the parent shell exported, the child sees exactly one source."""
    hostile = {**AMBIENT_ENV,
               "BUNDLE_MAIN_DB_HOST": "10.9.9.9", "BUNDLE_MAIN_DB_PORT": "5433",
               "BUNDLE_RESULTS_DB_HOST": "10.9.9.9", "BUNDLE_RESULTS_DB_PORT": "5432",
               "BUNDLE_MAIN_DB_USER": "someone-else",
               "BUNDLE_RESULTS_DB_USER": "someone-else"}
    endpoint = demo.resolve_endpoint(_args(db_endpoint="deploy"),
                                     env=hostile, overlay=DEPLOY_OVERLAY)
    child = endpoint.child_env(hostile)
    assert child["BUNDLE_MAIN_DB_HOST"] == "127.0.0.1"
    assert child["BUNDLE_MAIN_DB_PORT"] == "15433"
    assert child["BUNDLE_RESULTS_DB_PORT"] == "15432"
    assert child["BUNDLE_MAIN_DB_USER"] == "postgres"
    assert "10.9.9.9" not in child.values()
    assert "someone-else" not in child.values()
    # Unrelated variables are passed through untouched.
    assert child["PATH"] == "/usr/bin"
