#!/usr/bin/env python3
"""STEP 41 — reproducible local deployment profile.

Config validation (LOCAL-ONLY ports, pinned images, health checks, env-template
hygiene) runs without Docker. The live up/health/down cycle + `bundle doctor`
green self-skip when Docker / the pinned image are unavailable. A missing runtime
is reported BLOCKED, never auto-installed. `down` preserves data by default.

Run: `python3 -m pytest test_bundle_deploy.py -q`.
"""
import os
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# `bundle.deploy` imports PyYAML at module scope to read the compose profile, and
# PyYAML ships only in the optional `deploy` extra. Without this guard the whole
# module raised ImportError during collection on an install that did not take that
# extra — which the repository's own CI gate correctly rejects, since a missing
# OPTIONAL dependency must be a classified skip rather than a collection error.
pytest.importorskip(
    "yaml",
    reason="EXPECTED_OPTIONAL: the deploy profile needs PyYAML (pip install -e '.[deploy]')")

from bundle import deploy, stages

_POSTGRES_IMAGE = deploy.load_compose()["services"]["main-db"]["image"]
_DOCKER = deploy.docker_runtime_available()
_IMAGE = _DOCKER and subprocess.run(["docker", "image", "inspect", _POSTGRES_IMAGE],
                                    capture_output=True).returncode == 0
_LIVE = _DOCKER and _IMAGE
_DOCTOR_BUILD_ARTIFACTS = (stages.CORE_JAR, stages.READER_JAR)
_MISSING_DOCTOR_BUILD_ARTIFACTS = tuple(
    artifact for artifact in _DOCTOR_BUILD_ARTIFACTS if not artifact.is_file()
)
_LIVE_SKIP_REASON = (
    "Docker runtime / pinned postgres image not available"
    if not _LIVE
    else "generated doctor prerequisite build artifact(s) absent: "
         + ", ".join(str(artifact) for artifact in _MISSING_DOCTOR_BUILD_ARTIFACTS)
    if _MISSING_DOCTOR_BUILD_ARTIFACTS
    else ""
)

# A volume minted by `render_env` — `secrets.token_hex(8)` gives 16 hex chars.
_TEST_VOLUME_RE = re.compile(r"\Afwbundle_[0-9a-f]{16}_(?:main|results)_data\Z")


def _docker(*args) -> subprocess.CompletedProcess:
    """Single funnel for this module's Docker calls, so a regression can prove
    that a given code path issues no mutating command."""
    return subprocess.run(["docker", *args], capture_output=True, text=True)


def _inventory() -> "tuple[set, set]":
    """(volumes, containers) currently on the host — the before/after witness
    that no pre-existing operator resource was touched."""
    vols = _docker("volume", "ls", "--format", "{{.Name}}")
    cons = _docker("ps", "-a", "--format", "{{.Names}}")
    return set(vols.stdout.split()), set(cons.stdout.split())


def _canonical_conflict_reason() -> str:
    """Read-only preflight: the profile's container names are fixed, so any
    existing container with one of them belongs to somebody else. Returns a
    skip reason, or "" when the live path is safe to take."""
    existing = [n for n in deploy.canonical_container_names() if deploy.container_exists(n)]
    if not existing:
        return ""
    return ("EXPECTED_OPTIONAL: fixed-name container(s) already exist and this test cannot prove "
            "ownership of them: " + ", ".join(existing) + " — the profile's container names are not "
            "checkout-scoped; run `bundle_run.py deploy down` before the live acceptance test")


def _deploy_env_variable_names() -> set:
    """Every process variable that could steer the deploy profile."""
    names = set(deploy.parse_env_file(deploy.ENV_TEMPLATE))
    names |= {k for k in os.environ if k.startswith(("POSTGRES_", "BUNDLE_"))}
    return names - {"BUNDLE_DEPLOY_ENV_FILE"}          # the child CLI still needs the pointer


def _sanitize_deploy_env(monkeypatch) -> None:
    """Ambient deploy variables must not steer a temporary test stack.

    Persistent volume identity is protected by deploy.py, but ports, credentials
    and other process overrides retain normal precedence. A live acceptance test
    must still isolate all of them from a shell that sourced an operator `.env`.
    Narrow to the test; production ownership protection is tested separately.
    """
    for name in _deploy_env_variable_names():
        monkeypatch.delenv(name, raising=False)


def _captured_test_volumes(envfile: Path) -> set:
    """The two volume names this test owns, read from the env it just rendered
    and validated for the freshly-minted shape before anything is started."""
    vals = deploy.parse_env_file(envfile)
    captured = {vals["BUNDLE_MAIN_DB_VOLUME"], vals["BUNDLE_RESULTS_DB_VOLUME"]}
    assert len(captured) == 2, f"expected two distinct test volumes, got {captured}"
    for name in captured:
        assert _TEST_VOLUME_RE.match(name), f"{name!r} is not a freshly minted test volume name"
    return captured


def _remove_captured_containers(captured: set) -> None:
    """Remove canonical containers ONLY when their mounts prove they are ours.

    Anything else is left intact and reported: a leaked disposable test resource
    is preferable to a deleted operator database.
    """
    refused = []
    for cname in deploy.canonical_container_names():
        if not deploy.container_exists(cname):
            continue
        mounts = set(deploy.container_volume_mounts(cname))
        if mounts and mounts <= captured:
            _docker("rm", "-f", cname)
        else:
            refused.append((cname, sorted(mounts)))
    assert not refused, (f"refusing to remove fixed-name container(s) whose mounts are not the "
                         f"captured test volumes {sorted(captured)}: {refused} — left intact")


def _remove_captured_volumes(captured: set) -> None:
    """Delete exactly the captured names. Never recomputed from `_service_env()`,
    which ambient operator variables can steer."""
    for vname in sorted(captured):
        assert _TEST_VOLUME_RE.match(vname), f"refusing to delete non-test volume {vname!r}"
        _docker("volume", "rm", vname)


# ---- config validation (no Docker) ---------------------------------------- #
def test_validate_profile_all_green():
    checks = deploy.validate_profile()
    assert checks and all(c.ok for c in checks)
    names = {c.name for c in checks}
    assert "main-db.port_local_only" in names and "results-db.port_local_only" in names
    assert "main-db.healthcheck" in names and "main-db.named_volume" in names


def test_validate_rejects_non_local_port(monkeypatch):
    base = deploy.load_compose()

    def bad():
        d = dict(base); d["services"] = {k: dict(v) for k, v in base["services"].items()}
        d["services"]["main-db"] = dict(d["services"]["main-db"], ports=["0.0.0.0:15433:5432"])
        return d
    monkeypatch.setattr(deploy, "load_compose", bad)
    with pytest.raises(deploy.DeployError, match="127.0.0.1|LOCAL-ONLY"):
        deploy.validate_profile()


def test_validate_rejects_unpinned_image(monkeypatch):
    base = deploy.load_compose()

    def bad():
        d = dict(base); d["services"] = {k: dict(v) for k, v in base["services"].items()}
        d["services"]["results-db"] = dict(d["services"]["results-db"], image="postgres:latest")
        return d
    monkeypatch.setattr(deploy, "load_compose", bad)
    with pytest.raises(deploy.DeployError, match="not version-pinned"):
        deploy.validate_profile()


def test_env_template_has_no_real_secret_and_is_gitignored():
    tmpl = deploy.parse_env_file(deploy.ENV_TEMPLATE)
    assert tmpl["POSTGRES_PASSWORD"].upper().startswith("CHANGE_ME")     # placeholder only
    assert ".env" in deploy._gitignored()                                # rendered secret never committed
    # the pinned images are explicit in the compose file
    compose = deploy.load_compose()
    image = compose["services"]["main-db"]["image"]
    assert image.startswith("postgres:16.9-alpine@sha256:")
    assert re.fullmatch(r"postgres:16\.9-alpine@sha256:[0-9a-f]{64}", image)


def test_render_env_substitutes_password_and_perms(tmp_path, monkeypatch):
    envfile = tmp_path / ".env"
    monkeypatch.setattr(deploy, "ENV_FILE", envfile)
    p = deploy.render_env(force=True)
    assert p == envfile and envfile.is_file()
    vals = deploy.parse_env_file(envfile)
    assert vals["POSTGRES_PASSWORD"] and not vals["POSTGRES_PASSWORD"].upper().startswith("CHANGE_ME")
    assert (envfile.stat().st_mode & 0o777) == 0o600                     # 0600 — not world-readable
    # a real secret is in .env, NOT in the committed template
    assert vals["POSTGRES_PASSWORD"] != deploy.parse_env_file(deploy.ENV_TEMPLATE)["POSTGRES_PASSWORD"]
    assert vals["BUNDLE_MAIN_DB_VOLUME"].startswith("fwbundle_")
    assert vals["BUNDLE_MAIN_DB_VOLUME"].endswith("_main_data")
    assert vals["BUNDLE_RESULTS_DB_VOLUME"].endswith("_results_data")
    assert vals["BUNDLE_MAIN_DB_VOLUME"] != "fwbundle_main_data"
    main_id = vals["BUNDLE_MAIN_DB_VOLUME"].removeprefix("fwbundle_").removesuffix("_main_data")
    results_id = vals["BUNDLE_RESULTS_DB_VOLUME"].removeprefix("fwbundle_").removesuffix("_results_data")
    assert main_id == results_id and len(main_id) == 16


def test_rendered_env_drives_checkout_scoped_engine_volume_names(tmp_path, monkeypatch):
    envfile = tmp_path / ".env"
    monkeypatch.setattr(deploy, "ENV_FILE", envfile)
    deploy.render_env(password="local-test-password")
    env = deploy.parse_env_file(envfile)
    compose = deploy.load_compose()

    main_mount = deploy._volume_mount(
        compose["services"]["main-db"]["volumes"][0], compose, env)
    results_mount = deploy._volume_mount(
        compose["services"]["results-db"]["volumes"][0], compose, env)

    assert main_mount == f'{env["BUNDLE_MAIN_DB_VOLUME"]}:/var/lib/postgresql/data'
    assert results_mount == f'{env["BUNDLE_RESULTS_DB_VOLUME"]}:/var/lib/postgresql/data'
    assert "local-test-password" not in main_mount + results_mount


def test_up_stops_containers_and_preserves_data_on_auth_mismatch(tmp_path, monkeypatch):
    envfile = tmp_path / ".env"
    monkeypatch.setattr(deploy, "ENV_FILE", envfile)
    deploy.render_env(password="new-checkout-password")
    monkeypatch.setattr(deploy, "validate_profile", lambda **_kw: [])
    monkeypatch.setattr(deploy, "docker_runtime_available", lambda: True)
    monkeypatch.setattr(
        deploy, "_await_health",
        lambda *_args, **_kw: {"main-db": "healthy", "results-db": "healthy"})
    monkeypatch.setattr(
        deploy, "_authenticated_health",
        lambda *_args, **_kw: {"main-db": False, "results-db": False})
    monkeypatch.setattr(deploy, "container_exists", lambda _name: False)

    calls = []

    def fake_run(argv, **_kw):
        calls.append(list(argv))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(deploy, "run", fake_run)
    with pytest.raises(deploy.DeployError, match="authentication.*failed.*data volumes were preserved"):
        deploy.up()

    removals = [call for call in calls if call[:3] == ["docker", "rm", "-f"]]
    assert removals.count(["docker", "rm", "-f", "fwbundle-main-db"]) == 1
    assert removals.count(["docker", "rm", "-f", "fwbundle-results-db"]) == 1
    assert not any(call[:3] == ["docker", "volume", "rm"] for call in calls)


# ---- blocked when runtime unavailable (no auto-install) ------------------- #
def test_blocked_when_runtime_unavailable(monkeypatch):
    monkeypatch.setattr(deploy, "docker_runtime_available", lambda: False)
    with pytest.raises(deploy.DeployError, match="BLOCKED.*not auto-install|BLOCKED"):
        deploy.up()
    with pytest.raises(deploy.DeployError, match="BLOCKED"):
        deploy.down()
    assert deploy.status()["runtime"] == "unavailable"


def test_cli_doctor_deploy_blocked_without_stack():
    """`bundle doctor --deploy` with no stack up reports a clear blocked message
    (deploy/.env absent) and exits non-zero — via the REAL CLI."""
    if deploy.ENV_FILE.exists():
        pytest.skip("EXPECTED_OPTIONAL: a real deploy/.env exists — refusing to delete operator data")
    r = subprocess.run([sys.executable, str(HERE / "bundle_run.py"), "doctor", "--deploy"],
                       cwd=str(HERE), capture_output=True, text=True, timeout=60)
    out = r.stdout + r.stderr
    assert r.returncode != 0
    assert "deploy stack config not found" in out or "deploy up" in out


# ---- live up + REAL CLI `bundle doctor --deploy` (Docker + pinned image) ---- #
@pytest.mark.skipif(bool(_LIVE_SKIP_REASON), reason=_LIVE_SKIP_REASON)
def test_real_cli_doctor_deploy_green_and_data_preserved(tmp_path, monkeypatch):
    # Never attach to or delete a developer's normal deploy resources. Three
    # things are required for that, and the env path alone is not enough:
    #   1. refuse the fixed-name conflict BEFORE the first mutating command,
    #   2. drop ambient deploy variables so `_service_env()` cannot re-point the
    #      stack (or the cleanup) at operator volumes,
    #   3. capture this test's own volume names up front and delete only those.
    conflict = _canonical_conflict_reason()
    if conflict:
        pytest.skip(conflict)                    # read-only: nothing was mutated

    envfile = tmp_path / ".env"
    monkeypatch.setattr(deploy, "ENV_FILE", envfile)
    _sanitize_deploy_env(monkeypatch)
    monkeypatch.setenv("BUNDLE_DEPLOY_ENV_FILE", str(envfile))

    pre_volumes, pre_containers = _inventory()
    deploy.render_env()                          # mint identity BEFORE anything starts
    captured = _captured_test_volumes(envfile)
    assert not (captured & pre_volumes), (
        f"generated test volumes collide with pre-existing ones: {sorted(captured & pre_volumes)}")
    checkout_env = deploy.parse_env_file(deploy.DEPLOY_DIR / ".env")
    operator_volumes = {checkout_env[k] for k in ("BUNDLE_MAIN_DB_VOLUME", "BUNDLE_RESULTS_DB_VOLUME")
                        if k in checkout_env}
    assert not (captured & operator_volumes), "test volumes must differ from the checkout's own"

    try:
        rep = deploy.up(health_timeout=120)
        assert rep["health"] == {"main-db": "healthy", "results-db": "healthy"}   # fresh DBs start

        # the REAL `bundle doctor --deploy` CLI auto-consumes deploy/.env (ports +
        # password) and is GREEN against the deployed stack (acceptance).
        r = subprocess.run([sys.executable, str(HERE / "bundle_run.py"), "doctor", "--deploy"],
                           cwd=str(HERE), capture_output=True, text=True, timeout=120,
                           env={**os.environ, "BUNDLE_DEPLOY_ENV_FILE": str(envfile)})
        out = r.stdout + r.stderr
        assert r.returncode == 0, out
        assert "using LOCAL deploy stack: 127.0.0.1:15433/15432" in out          # auto-consumed deploy/.env
        assert "main_db" in out and "results_db" in out and "overall: OK" in out

        st = deploy.status()
        assert st["services"]["main-db"]["running"] and st["services"]["main-db"]["health"] == "healthy"

        # down (default) removes containers but PRESERVES the data volumes
        d = deploy.down()
        assert d["data_preserved"] is True and d["dropped_volumes"] == []
        vols = _inventory()[0]
        assert captured <= vols                                                 # data survived `down`
    finally:
        # Exact captured targets only. Keep emergency cleanup independent from
        # production code so a regression there cannot widen this test's scope.
        _remove_captured_containers(captured)
        _remove_captured_volumes(captured)
        envfile.unlink(missing_ok=True)

    post_volumes, post_containers = _inventory()
    assert pre_volumes <= post_volumes, (
        f"pre-existing volume(s) disappeared: {sorted(pre_volumes - post_volumes)}")
    assert pre_containers <= post_containers, (
        f"pre-existing container(s) disappeared: {sorted(pre_containers - post_containers)}")
    assert not (captured & post_volumes), "the test's own volumes must be gone"


# ---- isolation + ownership regressions (hermetic) -------------------------- #
def _resolved_db_volumes() -> set:
    """The engine-level volumes the DB services would actually mount right now."""
    compose = deploy.load_compose()
    env = deploy._service_env()
    return {deploy._volume_mount(vol, compose, env).split(":", 1)[0]
            for name in deploy.DB_SERVICES
            for vol in compose["services"][name].get("volumes", [])}


def _recording_docker(monkeypatch) -> list:
    issued: list = []

    def fake(*args):
        issued.append(args)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(sys.modules[__name__], "_docker", fake)
    return issued


def test_container_exists_sees_a_stopped_container_that_status_calls_not_running(monkeypatch):
    """`status()` reports running=False for BOTH a stopped and an absent
    container, so it cannot establish ownership. The preflight must not rely on
    it — and must issue no mutating command."""
    issued: list = []

    def fake_run(cmd, *a, **k):
        issued.append(list(cmd))
        if cmd[:3] == ["docker", "container", "inspect"]:
            return SimpleNamespace(returncode=0, stdout="c0ffee\n", stderr="")
        if cmd[:2] == ["docker", "info"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if cmd[:2] == ["docker", "inspect"]:
            return SimpleNamespace(returncode=0, stdout="false\n", stderr="")
        return SimpleNamespace(returncode=1, stdout="", stderr="")

    monkeypatch.setattr(deploy, "run", fake_run)
    assert deploy.container_exists("fwbundle-main-db") is True
    assert deploy.status()["services"]["main-db"]["running"] is False
    assert bool(_canonical_conflict_reason())
    forbidden = {"rm", "run", "start", "stop", "kill", "prune", "create"}
    assert not [c for c in issued if forbidden & set(c)], f"mutating command issued: {issued}"


def test_selected_env_volume_identity_cannot_be_steered_by_ambient_values(tmp_path, monkeypatch):
    """Persistent volume ownership comes from the selected env file even when
    a shell still exports another checkout's identity."""
    envfile = tmp_path / ".env"
    monkeypatch.setattr(deploy, "ENV_FILE", envfile)
    monkeypatch.setenv("BUNDLE_MAIN_DB_VOLUME", "operator_main_data")
    monkeypatch.setenv("BUNDLE_RESULTS_DB_VOLUME", "operator_results_data")
    monkeypatch.setenv("POSTGRES_PASSWORD", "operator-secret")
    deploy.render_env()

    captured = _captured_test_volumes(envfile)
    assert _resolved_db_volumes() == captured
    # Non-identity runtime values retain the documented precedence.
    assert deploy._service_env()["POSTGRES_PASSWORD"] == "operator-secret"

    _sanitize_deploy_env(monkeypatch)
    rendered = deploy.parse_env_file(envfile)
    assert deploy._service_env()["POSTGRES_PASSWORD"] == rendered["POSTGRES_PASSWORD"]


def test_cleanup_refuses_a_container_that_does_not_own_the_captured_volumes(monkeypatch):
    monkeypatch.setattr(deploy, "canonical_container_names", lambda **k: ["fwbundle-main-db"])
    monkeypatch.setattr(deploy, "container_exists", lambda name: True)
    monkeypatch.setattr(deploy, "container_volume_mounts", lambda name: ["fwbundle_main_data"])
    issued = _recording_docker(monkeypatch)
    with pytest.raises(AssertionError, match="refusing to remove"):
        _remove_captured_containers({"fwbundle_0123456789abcdef_main_data"})
    assert issued == [], "an unowned container must be left intact"


def test_cleanup_deletes_only_the_captured_volume_names(monkeypatch):
    issued = _recording_docker(monkeypatch)
    _remove_captured_volumes({"fwbundle_0123456789abcdef_main_data"})
    assert issued == [("volume", "rm", "fwbundle_0123456789abcdef_main_data")]
    issued.clear()
    with pytest.raises(AssertionError, match="refusing to delete"):
        _remove_captured_volumes({"fwbundle_main_data"})       # a legacy operator volume
    assert issued == []


def test_run_command_carries_complete_volume_ownership_labels(tmp_path, monkeypatch):
    envfile = tmp_path / ".env"
    monkeypatch.setattr(deploy, "ENV_FILE", envfile)
    deploy.render_env(password="label-test-password")
    compose = deploy.load_compose()
    env = deploy._service_env()
    captured = _captured_test_volumes(envfile)

    command = deploy._run_cmd("main-db", compose["services"]["main-db"], env, compose)
    labels = {command[i + 1] for i, value in enumerate(command[:-1]) if value == "--label"}
    assert "com.ghyura.fwbundle.managed=true" in labels
    assert "com.ghyura.fwbundle.service=main-db" in labels
    assert {item.split("=", 1)[1] for item in labels if item.startswith(
        ("com.ghyura.fwbundle.main-volume=", "com.ghyura.fwbundle.results-volume="))} == captured


def test_up_refuses_a_foreign_fixed_name_before_any_mutation(tmp_path, monkeypatch):
    envfile = tmp_path / ".env"
    monkeypatch.setattr(deploy, "ENV_FILE", envfile)
    deploy.render_env(password="foreign-container-test")
    monkeypatch.setattr(deploy, "validate_profile", lambda **_kw: [])
    monkeypatch.setattr(deploy, "docker_runtime_available", lambda: True)
    monkeypatch.setattr(deploy, "container_exists", lambda _name: True)
    monkeypatch.setattr(deploy, "_container_is_owned", lambda *_args: False)
    issued = []

    def fake_run(argv, **_kw):
        issued.append(list(argv))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(deploy, "run", fake_run)
    with pytest.raises(deploy.DeployError, match="not owned.*no container was changed"):
        deploy.up()
    assert issued == [], "ownership preflight must finish before the first mutating command"


def test_legacy_db_container_is_owned_only_by_exact_selected_mount(tmp_path, monkeypatch):
    envfile = tmp_path / ".env"
    monkeypatch.setattr(deploy, "ENV_FILE", envfile)
    deploy.render_env(password="legacy-ownership-test")
    compose = deploy.load_compose()
    env = deploy._service_env()
    expected = deploy._profile_volume_names(compose, env)["main-db"]
    monkeypatch.setattr(deploy, "container_labels", lambda _name: {})

    monkeypatch.setattr(deploy, "container_volume_mounts", lambda _name: [expected])
    assert deploy._container_is_owned("main-db", "fwbundle-main-db", compose, env)

    monkeypatch.setattr(deploy, "container_volume_mounts", lambda _name: ["foreign_main_data"])
    assert not deploy._container_is_owned("main-db", "fwbundle-main-db", compose, env)


def test_explicit_foreign_labels_cannot_be_downgraded_to_legacy_mount_ownership(
        tmp_path, monkeypatch):
    envfile = tmp_path / ".env"
    monkeypatch.setattr(deploy, "ENV_FILE", envfile)
    deploy.render_env(password="contradictory-label-test")
    compose = deploy.load_compose()
    env = deploy._service_env()
    expected = deploy._profile_volume_names(compose, env)["main-db"]
    monkeypatch.setattr(deploy, "container_labels", lambda _name: {
        deploy._MANAGED_LABEL: "true",
        deploy._SERVICE_LABEL: "foreign-service",
    })
    monkeypatch.setattr(deploy, "container_volume_mounts", lambda _name: [expected])

    assert not deploy._container_is_owned(
        "main-db", "fwbundle-main-db", compose, env)


def test_destructive_down_uses_selected_file_not_ambient_volume_names(tmp_path, monkeypatch):
    envfile = tmp_path / ".env"
    monkeypatch.setattr(deploy, "ENV_FILE", envfile)
    deploy.render_env(password="destructive-target-test")
    captured = _captured_test_volumes(envfile)
    monkeypatch.setenv("BUNDLE_MAIN_DB_VOLUME", "operator_main_data")
    monkeypatch.setenv("BUNDLE_RESULTS_DB_VOLUME", "operator_results_data")
    monkeypatch.setattr(deploy, "docker_runtime_available", lambda: True)
    monkeypatch.setattr(deploy, "container_exists", lambda _name: False)
    issued = []

    def fake_run(argv, **_kw):
        issued.append(list(argv))
        if argv[:3] == ["docker", "volume", "inspect"]:
            return SimpleNamespace(returncode=1, stdout="", stderr="not found")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(deploy, "run", fake_run)
    report = deploy.down(volumes=True)
    assert report["dropped_volumes"] == []
    filters = {part.split("=", 1)[1] for call in issued for part in call if part.startswith("volume=")}
    assert filters == captured
    assert not any("operator_" in part for call in issued for part in call)


def test_destructive_down_refuses_foreign_volume_reference_before_mutation(tmp_path, monkeypatch):
    envfile = tmp_path / ".env"
    monkeypatch.setattr(deploy, "ENV_FILE", envfile)
    deploy.render_env(password="foreign-reference-test")
    monkeypatch.setattr(deploy, "docker_runtime_available", lambda: True)
    monkeypatch.setattr(deploy, "container_exists", lambda _name: False)
    issued = []

    def fake_run(argv, **_kw):
        issued.append(list(argv))
        if argv[:2] == ["docker", "ps"]:
            return SimpleNamespace(returncode=0, stdout="foreign-container\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(deploy, "run", fake_run)
    with pytest.raises(deploy.DeployError, match="foreign container reference.*No container was changed"):
        deploy.down(volumes=True)
    assert not [call for call in issued if call[:3] in (
        ["docker", "rm", "-f"], ["docker", "volume", "rm"])], issued


def test_destructive_down_fails_closed_when_volume_inspection_fails(tmp_path, monkeypatch):
    envfile = tmp_path / ".env"
    monkeypatch.setattr(deploy, "ENV_FILE", envfile)
    deploy.render_env(password="volume-inspection-test")
    monkeypatch.setattr(deploy, "docker_runtime_available", lambda: True)
    monkeypatch.setattr(deploy, "container_exists", lambda _name: False)
    issued = []

    def fake_run(argv, **_kw):
        issued.append(list(argv))
        if argv[:2] == ["docker", "ps"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if argv[:3] == ["docker", "volume", "inspect"]:
            return SimpleNamespace(returncode=1, stdout="", stderr="permission denied")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(deploy, "run", fake_run)
    with pytest.raises(deploy.DeployError, match="could not verify selected volume.*before any container"):
        deploy.down(volumes=True)
    assert not [call for call in issued if call[:3] in (
        ["docker", "rm", "-f"], ["docker", "volume", "rm"])], issued


def test_destructive_down_refuses_unscoped_legacy_volume_names(tmp_path, monkeypatch):
    envfile = tmp_path / ".env"
    envfile.write_text(
        "POSTGRES_USER=postgres\nPOSTGRES_PASSWORD=test\n"
        "BUNDLE_MAIN_DB_VOLUME=fwbundle_main_data\n"
        "BUNDLE_RESULTS_DB_VOLUME=fwbundle_results_data\n", encoding="utf-8")
    monkeypatch.setattr(deploy, "ENV_FILE", envfile)
    monkeypatch.setattr(deploy, "docker_runtime_available", lambda: True)
    monkeypatch.setattr(deploy, "container_exists", lambda _name: False)
    issued = []

    def fake_run(argv, **_kw):
        issued.append(list(argv))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(deploy, "run", fake_run)
    with pytest.raises(deploy.DeployError, match="refusing destructive cleanup"):
        deploy.down(volumes=True)


@pytest.mark.skipif(not _LIVE, reason="Docker runtime / pinned postgres image not available")
def test_live_fixed_name_conflict_is_detected_without_mutation():
    """A disposable STOPPED container holding a canonical name is detected, and
    the surrounding host inventory is provably unchanged."""
    if _canonical_conflict_reason():
        pytest.skip("EXPECTED_OPTIONAL: a canonical container already exists on this host")
    sentinel = deploy.canonical_container_names()[0]
    before = _inventory()
    created = _docker("create", "--name", sentinel, _POSTGRES_IMAGE)
    assert created.returncode == 0, created.stderr
    try:
        assert deploy.container_exists(sentinel) is True
        assert deploy.status()["services"]["main-db"]["running"] is False
        reason = _canonical_conflict_reason()
        assert reason.startswith("EXPECTED_OPTIONAL:") and sentinel in reason
    finally:
        # -v drops the anonymous volume this image declares; named volumes are
        # never removed by `docker rm`, so operator data cannot be in scope.
        _docker("rm", "-fv", sentinel)
    assert _inventory() == before


# ---- CLI ------------------------------------------------------------------- #
def test_cli_deploy_validate():
    r = subprocess.run([sys.executable, str(HERE / "bundle_run.py"), "deploy", "validate"],
                       cwd=str(HERE), capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "local-only" in (r.stdout + r.stderr).lower() and "port_local_only" in (r.stdout + r.stderr)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
