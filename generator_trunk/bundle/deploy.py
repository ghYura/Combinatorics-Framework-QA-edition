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

"""STEP 41 — reproducible local deployment profile + one-command up/down wrapper.

Provides a container/dev profile (``deploy/docker-compose.yml``) for the main +
results PostgreSQL (and optional monitoring), with PINNED image versions, health
checks, 127.0.0.1-only ports (LOCAL-ONLY — never LAN/Internet), configurable
ports/volumes, and secrets via a (never-committed) ``.env`` rendered from
``.env.template``. Freshly rendered environments also receive checkout-scoped
volume names, preventing an older checkout's PostgreSQL data from being paired
with a newly generated password.

Container names remain fixed for compatibility, so only one live stack is
supported per host. Ownership labels plus exact legacy mounts protect those
names from cross-checkout replacement. Destructive volume cleanup uses only the
selected env file, validates its scoped pair and fails closed on foreign refs.

The compose file is the canonical, validated profile; this wrapper PARSES it
(PyYAML) and drives plain ``docker run``/``docker volume`` — so it works WITHOUT
the compose plugin. ``down`` preserves data (volumes) by default; deleting data
needs an explicit ``--volumes``. If the Docker runtime is unavailable the wrapper
reports BLOCKED and does NOT auto-install anything.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

from .database import psql
from .process import run

DEPLOY_DIR = Path(__file__).resolve().parent.parent / "deploy"
COMPOSE_FILE = DEPLOY_DIR / "docker-compose.yml"
ENV_TEMPLATE = DEPLOY_DIR / ".env.template"
# The override keeps live acceptance tests and advanced multi-checkout setups
# isolated. The normal/user-facing path remains deploy/.env.
ENV_FILE = Path(os.environ.get("BUNDLE_DEPLOY_ENV_FILE", str(DEPLOY_DIR / ".env")))

# the data-bearing DB services (monitoring is opt-in and stateless)
DB_SERVICES = ("main-db", "results-db")

# Volume names are persistent resource identity, not ordinary runtime overrides.
# Once an env file exists, a sourced env from another checkout must not redirect
# this checkout's containers or destructive cleanup at somebody else's data.
_IDENTITY_KEYS = frozenset({"BUNDLE_MAIN_DB_VOLUME", "BUNDLE_RESULTS_DB_VOLUME"})
_SCOPED_VOLUME_RE = re.compile(r"^fwbundle_([0-9a-f]{16})_(main|results)_data$")
_MANAGED_LABEL = "com.ghyura.fwbundle.managed"
_SERVICE_LABEL = "com.ghyura.fwbundle.service"
_MAIN_VOLUME_LABEL = "com.ghyura.fwbundle.main-volume"
_RESULTS_VOLUME_LABEL = "com.ghyura.fwbundle.results-volume"


class DeployError(Exception):
    """A deployment-profile misconfiguration or a blocked runtime."""


@dataclass(frozen=True)
class Check:
    ok: bool
    name: str
    detail: str


# --------------------------------------------------------------------------- #
def load_compose() -> dict:
    if not COMPOSE_FILE.is_file():
        raise DeployError(f"compose profile missing: {COMPOSE_FILE}")
    return yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8")) or {}


_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def subst(value: str, env: "dict[str, str]") -> str:
    """Resolve ``${VAR}`` / ``${VAR:-default}`` against ``env`` (compose semantics)."""
    def repl(m):
        return env.get(m.group(1), m.group(2) if m.group(2) is not None else "")
    return _VAR_RE.sub(repl, str(value))


def parse_env_file(path: Path) -> "dict[str, str]":
    out: dict = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _service_env(overrides: "Optional[dict]" = None) -> "dict[str, str]":
    """Effective ordinary settings: template < file < process < overrides.
    Persistent volume identity is locked to the selected file once present."""
    env = parse_env_file(ENV_TEMPLATE)
    selected = parse_env_file(ENV_FILE)
    env.update(selected)
    for key, value in os.environ.items():
        if not (key in env or key.startswith("BUNDLE_") or key.startswith("POSTGRES_")):
            continue
        if key in _IDENTITY_KEYS and key in selected:
            continue
        env[key] = value
    if overrides:
        for key, value in overrides.items():
            value = str(value)
            if key in _IDENTITY_KEYS and key in selected and value != selected[key]:
                raise DeployError(
                    f"refusing to override persistent deploy identity {key}: selected env file "
                    f"{ENV_FILE} owns {selected[key]!r}, requested {value!r}")
            env[key] = value
    return env


def _port_parts(port_str: str):
    """Split a published-port string into (bind_ip, host_port, container_port)."""
    parts = str(port_str).strip().strip('"').split(":")
    if len(parts) == 3:
        return parts[0], parts[1], parts[2]
    if len(parts) == 2:
        return "", parts[0], parts[1]
    return "", "", parts[0]


# --------------------------------------------------------------------------- #
def validate_profile(*, overrides: "Optional[dict]" = None) -> "list[Check]":
    """Validate the deployment profile, returning checks. LOCAL-ONLY binding,
    pinned images, health checks, named volumes, env-template hygiene. Raises
    :class:`DeployError` on a hard violation (e.g. a non-127.0.0.1 port)."""
    compose = load_compose()
    env = _service_env(overrides)
    services = compose.get("services", {})
    checks: list[Check] = []
    if not services:
        raise DeployError("compose profile declares no services")

    for name in DB_SERVICES:
        if name not in services:
            raise DeployError(f"compose profile missing required service {name!r}")

    declared_volumes = set((compose.get("volumes") or {}).keys())
    for sname, svc in services.items():
        image = svc.get("image", "")
        tag = image.rsplit(":", 1)[-1] if ":" in image else ""
        pinned = bool(tag) and tag != "latest"
        checks.append(Check(pinned, f"{sname}.image_pinned", f"image={image or '(none)'}"))
        if not pinned:
            raise DeployError(f"service {sname!r} image {image!r} is not version-pinned (no :tag or :latest)")

        for port in svc.get("ports", []):
            resolved = subst(port, env)
            bind_ip, hostp, _cport = _port_parts(resolved)
            local_only = bind_ip == "127.0.0.1"
            checks.append(Check(local_only, f"{sname}.port_local_only", f"{resolved}"))
            if not local_only:
                raise DeployError(
                    f"service {sname!r} port {resolved!r} is not bound to 127.0.0.1 — "
                    f"LOCAL-ONLY rule: containers must never be reachable from the LAN/Internet")

        for vol in svc.get("volumes", []):
            vkey = subst(vol, env).split(":", 1)[0]
            named = vkey in declared_volumes
            # only DB services must use a NAMED volume (durable data); monitoring is stateless
            if sname in DB_SERVICES:
                actual = _actual_volume_name(vkey, compose, env) if named else vkey
                checks.append(Check(named, f"{sname}.named_volume", actual))
                if not named:
                    raise DeployError(f"DB service {sname!r} volume {vkey!r} is not a declared named volume "
                                      f"(data would not persist across `down`)")
                if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]+", actual):
                    raise DeployError(f"DB service {sname!r} resolved volume name {actual!r} is invalid")

        if sname in DB_SERVICES:
            has_health = bool(svc.get("healthcheck"))
            checks.append(Check(has_health, f"{sname}.healthcheck", "present" if has_health else "MISSING"))
            if not has_health:
                raise DeployError(f"DB service {sname!r} has no healthcheck")

    # env-template hygiene: it must exist and carry only a placeholder password
    tmpl = parse_env_file(ENV_TEMPLATE)
    pw = tmpl.get("POSTGRES_PASSWORD", "")
    placeholder = (not pw) or pw.upper().startswith("CHANGE_ME") or "placeholder" in pw.lower()
    checks.append(Check(placeholder, "env_template.no_real_secret", f"POSTGRES_PASSWORD={pw!r}"))
    if not placeholder:
        raise DeployError(".env.template carries a non-placeholder POSTGRES_PASSWORD — never commit a real secret")
    checks.append(Check(ENV_FILE.name in _gitignored(), "env_file.gitignored",
                        ".env is in deploy/.gitignore" if ENV_FILE.name in _gitignored() else "NOT ignored"))
    return checks


def _gitignored() -> set:
    gi = DEPLOY_DIR / ".gitignore"
    if not gi.is_file():
        return set()
    return {ln.strip() for ln in gi.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")}


# --------------------------------------------------------------------------- #
def docker_runtime_available() -> bool:
    try:
        return run(["docker", "info"]).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def render_env(*, force: bool = False, password: "Optional[str]" = None) -> Path:
    """Render ``deploy/.env`` from the template, substituting a LOCAL dev password
    (generated if not given) and unique volume names. Never overwrites an
    existing ``.env`` unless ``force``. Written 0600. The real secret never
    touches the template/VCS.

    The volume names are stored beside the password so a different checkout (or
    a re-downloaded source tree without its old ignored .env) cannot silently
    attach an older PostgreSQL cluster initialized with different credentials.
    """
    if ENV_FILE.is_file() and not force:
        return ENV_FILE
    if not ENV_TEMPLATE.is_file():
        raise DeployError(f"env template missing: {ENV_TEMPLATE}")
    pw = password or ("localdev_" + secrets.token_hex(12))
    deploy_id = secrets.token_hex(8)
    replacements = {
        "POSTGRES_PASSWORD": pw,
        "BUNDLE_MAIN_DB_VOLUME": f"fwbundle_{deploy_id}_main_data",
        "BUNDLE_RESULTS_DB_VOLUME": f"fwbundle_{deploy_id}_results_data",
    }
    lines = []
    for line in ENV_TEMPLATE.read_text(encoding="utf-8").splitlines():
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        lines.append(f"{key}={replacements[key]}" if key in replacements else line)
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        ENV_FILE.chmod(0o600)
    except OSError:
        pass
    return ENV_FILE


def _require_runtime() -> None:
    if not docker_runtime_available():
        raise DeployError("BLOCKED: Docker runtime is not available — NOT auto-installing it. "
                          "Install/start Docker (rootless, local-only) and retry, or use a host PostgreSQL.")


def _services_to_start(monitoring: bool) -> list:
    return list(DB_SERVICES) + (["monitoring"] if monitoring else [])


def _actual_volume_name(vkey: str, compose: dict, env: dict) -> str:
    """Resolve a Compose top-level volume key to its engine-level name."""
    declaration = (compose.get("volumes") or {}).get(vkey) or {}
    if isinstance(declaration, dict) and declaration.get("name"):
        return subst(str(declaration["name"]), env)
    return vkey


def _volume_mount(vol: str, compose: dict, env: dict) -> str:
    """Render a short-syntax volume mount using its resolved engine name."""
    parts = subst(vol, env).split(":")
    parts[0] = _actual_volume_name(parts[0], compose, env)
    return ":".join(parts)


def _profile_volume_names(compose: dict, env: dict) -> "dict[str, str]":
    """The exact engine-level data volume owned by each DB service."""
    result = {}
    for name in DB_SERVICES:
        mounts = (compose.get("services", {}).get(name, {}) or {}).get("volumes", [])
        if len(mounts) != 1:
            raise DeployError(f"DB service {name!r} must declare exactly one data volume")
        result[name] = _volume_mount(mounts[0], compose, env).split(":", 1)[0]
    return result


def _ownership_labels(name: str, compose: dict, env: dict) -> "dict[str, str]":
    volumes = _profile_volume_names(compose, env)
    return {
        _MANAGED_LABEL: "true",
        _SERVICE_LABEL: name,
        _MAIN_VOLUME_LABEL: volumes["main-db"],
        _RESULTS_VOLUME_LABEL: volumes["results-db"],
    }


def _run_cmd(name: str, svc: dict, env: dict, compose: dict) -> list:
    cname = svc.get("container_name", f"fwbundle-{name}")
    cmd = ["docker", "run", "-d", "--name", cname, "--restart", "unless-stopped"]
    for key, value in sorted(_ownership_labels(name, compose, env).items()):
        cmd += ["--label", f"{key}={value}"]
    if ENV_FILE.is_file():
        cmd += ["--env-file", str(ENV_FILE)]
    for port in svc.get("ports", []):
        bind_ip, hostp, cport = _port_parts(subst(port, env))
        cmd += ["-p", f"{bind_ip or '127.0.0.1'}:{hostp}:{cport}"]
    for vol in svc.get("volumes", []):
        cmd += ["-v", _volume_mount(vol, compose, env)]
    cmd += [svc["image"]]
    return cmd


def _host_port(svc: dict, env: dict) -> "Optional[str]":
    for port in svc.get("ports", []):
        _ip, hostp, _c = _port_parts(subst(port, env))
        return hostp
    return None


def up(*, monitoring: bool = False, overrides: "Optional[dict]" = None,
       health_timeout: float = 90.0) -> dict:
    """Start the DB stack (one command). Renders .env, runs each service via
    ``docker run`` (127.0.0.1-bound, named volumes), and waits for both port
    readiness and authenticated SQL access. Returns a status dict. Raises
    :class:`DeployError` (BLOCKED) with no runtime."""
    validate_profile(overrides=overrides)
    _require_runtime()
    render_env()
    compose = load_compose()
    env = _service_env(overrides)
    services = compose["services"]
    names = _services_to_start(monitoring)
    # Resolve every fixed-name collision before the first mutation. The old
    # unconditional `docker rm -f` could stop another checkout's stack.
    owned_existing = _owned_existing_containers(names, compose, env)
    started = []
    for name in names:
        svc = services[name]
        cname = _container_name(name, services)
        if name in owned_existing:
            removed = run(["docker", "rm", "-f", cname])
            if removed.returncode != 0:
                raise DeployError(f"failed to replace owned container {cname!r}: "
                                  f"{(removed.stderr or removed.stdout or '').strip()[:300]}")
        r = run(_run_cmd(name, svc, env, compose))
        if r.returncode != 0:
            for started_name in started:
                run(["docker", "rm", "-f", started_name])
            raise DeployError(f"failed to start {name!r}: {(r.stderr or r.stdout or '').strip()[:300]}")
        started.append(cname)
    health = _await_health(services, env, timeout=health_timeout)
    if all(state == "healthy" for state in health.values()):
        auth = _authenticated_health(services, env)
        failed = [name for name, ok_auth in auth.items() if not ok_auth]
        if failed:
            for cname in started:
                run(["docker", "rm", "-f", cname])
            joined = ", ".join(failed)
            raise DeployError(
                f"database authentication with {ENV_FILE} failed for: {joined}. "
                "Containers were stopped and data volumes were preserved. This usually means a legacy "
                "volume was initialized from a different deploy/.env. Restore that original .env, or, "
                "only if the local DB data is disposable, run `bundle_run.py deploy down --volumes` "
                "before retrying `deploy up`.")
    return {"started": started, "health": health, "env_file": str(ENV_FILE)}


def _await_health(services: dict, env: dict, *, timeout: float) -> dict:
    """Poll each DB service's host port with pg_isready until healthy or timeout."""
    deadline = time.time() + timeout
    health: dict = {n: "unknown" for n in DB_SERVICES}
    while time.time() < deadline:
        for name in DB_SERVICES:
            if health[name] == "healthy":
                continue
            hp = _host_port(services[name], env)
            rc = run(["pg_isready", "-h", "127.0.0.1", "-p", str(hp)]).returncode
            health[name] = "healthy" if rc == 0 else "starting"
        if all(v == "healthy" for v in health.values()):
            return health
        time.sleep(2)
    return health


def _authenticated_health(services: dict, env: dict) -> "dict[str, bool]":
    """Verify that deploy/.env credentials work, not merely that ports answer."""
    rendered = parse_env_file(ENV_FILE)
    user = rendered.get("POSTGRES_USER", "postgres")
    password = rendered.get("POSTGRES_PASSWORD", "")
    result: dict[str, bool] = {}
    for name in services:
        if name not in DB_SERVICES:
            continue
        hp = _host_port(services[name], env)
        out, rc = psql(hp, "postgres", "SELECT 1", host="127.0.0.1",
                       user=user, password=password)
        result[name] = rc == 0 and out.strip() == "1"
    return result


def down(*, volumes: bool = False, monitoring: bool = True) -> dict:
    """Stop + remove the stack's containers. DATA-PRESERVING by default — named
    volumes are kept unless ``volumes=True`` (explicit, destructive)."""
    _require_runtime()
    compose = load_compose()
    services = compose["services"]
    names = list(DB_SERVICES) + (["monitoring"] if monitoring else [])
    if not ENV_FILE.is_file() and any(
            container_exists(_container_name(name, services)) for name in names):
        raise DeployError(
            f"refusing to remove fixed-name containers without their selected env file {ENV_FILE}")
    env = _service_env()
    owned_existing = _owned_existing_containers(names, compose, env)
    volumes_by_service = _scoped_file_volumes(compose) if volumes else {}

    # Finish every destructive-scope check before the first removal. References
    # from the selected stack are expected at this point; any other container
    # proves that deleting the volume would cross an ownership boundary.
    expected_refs = set(owned_existing.values())
    existing_volumes = []
    for vname in volumes_by_service.values():
        refs = _volume_references(vname)
        foreign_refs = sorted(set(refs) - expected_refs)
        if foreign_refs:
            raise DeployError(
                f"refusing to delete selected volume {vname!r}; foreign container reference(s): "
                f"{', '.join(foreign_refs)}. No container was changed.")
        inspected = run(["docker", "volume", "inspect", vname])
        if inspected.returncode == 0:
            existing_volumes.append(vname)
            continue
        detail = (inspected.stderr or inspected.stdout or "").strip()
        if "no such volume" not in detail.lower() and "not found" not in detail.lower():
            raise DeployError(
                f"could not verify selected volume {vname!r}; refusing cleanup before any "
                f"container is changed: {detail[:300] or 'unknown Docker error'}")
    removed = []
    for name, cname in owned_existing.items():
        result = run(["docker", "rm", "-f", cname])
        if result.returncode == 0:
            removed.append(cname)
        else:
            raise DeployError(f"failed to remove owned container {cname!r}: "
                              f"{(result.stderr or result.stdout or '').strip()[:300]}")
    dropped_volumes = []
    if existing_volumes:
        # Re-check after removing our containers to catch a concurrent attach.
        for vname in existing_volumes:
            references = _volume_references(vname)
            if references:
                raise DeployError(
                    f"refusing to delete selected volume {vname!r}; it became referenced by: "
                    f"{', '.join(references)}")
        for vname in existing_volumes:
            result = run(["docker", "volume", "rm", vname])
            if result.returncode != 0:
                raise DeployError(f"failed to delete selected owned volume {vname!r}: "
                                  f"{(result.stderr or result.stdout or '').strip()[:300]}")
            dropped_volumes.append(vname)
    return {"removed": removed, "dropped_volumes": dropped_volumes, "data_preserved": not volumes}


def canonical_container_names(*, monitoring: bool = True) -> "list[str]":
    """The fixed container names this profile claims on the host.

    They are NOT scoped per checkout or per ``.env``, so a name collision is a
    collision with whoever created that container first. Resolves from the
    compose profile only — it does not contact Docker.
    """
    services = load_compose().get("services", {})
    return [(services.get(name) or {}).get("container_name", f"fwbundle-{name}")
            for name in (list(DB_SERVICES) + (["monitoring"] if monitoring else []))]


def container_exists(name: str) -> bool:
    """True if a container called ``name`` exists in ANY state.

    :func:`status` reports ``running=False`` both for a stopped container and
    for an absent one, so it cannot answer an ownership question. This can.
    READ-ONLY: it never starts, stops, removes or reads credentials from the
    container.
    """
    return run(["docker", "container", "inspect", "-f", "{{.Id}}", name]).returncode == 0


_MOUNTED_VOLUMES_FMT = '{{range .Mounts}}{{if eq .Type "volume"}}{{println .Name}}{{end}}{{end}}'


def container_volume_mounts(name: str) -> "list[str]":
    """The named volumes an existing container mounts, for proving ownership
    before a destructive cleanup. READ-ONLY; empty list if absent."""
    r = run(["docker", "container", "inspect", "-f", _MOUNTED_VOLUMES_FMT, name])
    if r.returncode != 0:
        return []
    return [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()]


def container_labels(name: str) -> "dict[str, str]":
    """Container labels used as explicit ownership evidence. READ-ONLY."""
    r = run(["docker", "container", "inspect", "-f", "{{json .Config.Labels}}", name])
    if r.returncode != 0:
        return {}
    try:
        value = json.loads((r.stdout or "{}").strip())
    except (TypeError, ValueError):
        return {}
    return {str(k): str(v) for k, v in (value or {}).items()}


def _container_name(name: str, services: dict) -> str:
    return (services.get(name) or {}).get("container_name", f"fwbundle-{name}")


def _container_is_owned(name: str, cname: str, compose: dict, env: dict) -> bool:
    """Whether the fixed-name container belongs to the selected env file.

    New containers carry the complete ownership label set. Existing deployments
    from before those labels are accepted only for a DB service whose one named
    volume exactly matches this env file. Stateless legacy monitoring cannot be
    attributed safely and is therefore refused rather than removed.
    """
    expected_labels = _ownership_labels(name, compose, env)
    actual_labels = container_labels(cname)
    # A partial or contradictory current-protocol claim is not a legacy
    # container. Never let a matching mount override explicit foreign labels.
    if set(expected_labels) & set(actual_labels):
        return all(actual_labels.get(k) == v for k, v in expected_labels.items())
    if name in DB_SERVICES:
        expected_mount = {_profile_volume_names(compose, env)[name]}
        return set(container_volume_mounts(cname)) == expected_mount
    return False


def _owned_existing_containers(names: "list[str]", compose: dict, env: dict) -> "dict[str, str]":
    """Preflight every fixed name before mutation; reject the whole operation
    if even one existing container cannot be attributed to this env file."""
    services = compose.get("services", {})
    existing, conflicts = {}, []
    for name in names:
        cname = _container_name(name, services)
        if not container_exists(cname):
            continue
        if _container_is_owned(name, cname, compose, env):
            existing[name] = cname
        else:
            conflicts.append(cname)
    if conflicts:
        raise DeployError(
            "refusing to replace/remove fixed-name container(s) not owned by the selected "
            f"deploy env {ENV_FILE}: {', '.join(conflicts)}. Stop them from their owning checkout "
            "or choose another host; no container was changed.")
    return existing


def _volume_references(name: str) -> "list[str]":
    """All containers referencing a named volume. READ-ONLY and fail-closed."""
    refs = run(["docker", "ps", "-a", "--filter", f"volume={name}",
                "--format", "{{.Names}}"])
    if refs.returncode != 0:
        detail = (refs.stderr or refs.stdout or "").strip()
        raise DeployError(
            f"could not verify references for volume {name!r}; refusing deletion: "
            f"{detail[:300] or 'unknown Docker error'}")
    return [line.strip() for line in (refs.stdout or "").splitlines() if line.strip()]


def _scoped_file_volumes(compose: dict) -> "dict[str, str]":
    """Destructive volume targets from the selected file only, never ambient env."""
    selected = parse_env_file(ENV_FILE)
    if not selected:
        raise DeployError(f"refusing destructive volume cleanup without selected env file {ENV_FILE}")
    env = parse_env_file(ENV_TEMPLATE)
    env.update(selected)
    volumes = _profile_volume_names(compose, env)
    matches = {name: _SCOPED_VOLUME_RE.fullmatch(value) for name, value in volumes.items()}
    if (not all(matches.values())
            or matches["main-db"].group(1) != matches["results-db"].group(1)
            or matches["main-db"].group(2) != "main"
            or matches["results-db"].group(2) != "results"):
        raise DeployError(
            "refusing destructive cleanup: selected env does not contain one matching pair of "
            f"checkout-scoped volumes: {volumes}")
    return volumes


def status(*, overrides: "Optional[dict]" = None) -> dict:
    """Per-service container state + DB port health (best-effort; runtime-gated)."""
    if not docker_runtime_available():
        return {"runtime": "unavailable", "services": {}}
    compose = load_compose()
    services = compose["services"]
    env = _service_env(overrides)
    out: dict = {"runtime": "available", "services": {}}
    for name in (list(DB_SERVICES) + ["monitoring"]):
        cname = services.get(name, {}).get("container_name", f"fwbundle-{name}")
        r = run(["docker", "inspect", "-f", "{{.State.Running}}", cname])
        running = r.returncode == 0 and "true" in (r.stdout or "").lower()
        info = {"container": cname, "running": running}
        if name in DB_SERVICES and running:
            hp = _host_port(services[name], env)
            port_ready = run(["pg_isready", "-h", "127.0.0.1", "-p", str(hp)]).returncode == 0
            auth_ready = port_ready and _authenticated_health({name: services[name]}, env).get(name, False)
            info["port"] = hp
            info["health"] = "healthy" if auth_ready else ("authentication-failed" if port_ready else "unhealthy")
        out["services"][name] = info
    return out


def config_overlay() -> dict:
    """The BundleConfig overlay (host=127.0.0.1, ports, user, password) for the
    LOCAL deploy stack, read from deploy/.env. Lets `bundle doctor --deploy` (and
    any other command) automatically target the deployed DBs without the operator
    re-typing ports/passwords. Raises :class:`DeployError` if the stack config is
    absent (``deploy up`` not yet run)."""
    rendered = parse_env_file(ENV_FILE)
    if not rendered or not rendered.get("POSTGRES_PASSWORD"):
        raise DeployError("deploy stack config not found — run `bundle deploy up` first (no deploy/.env)")
    env = _service_env()                                # template defaults + .env + process env
    pw = rendered["POSTGRES_PASSWORD"]
    user = rendered.get("POSTGRES_USER", "postgres")
    return {
        "main_db_host": "127.0.0.1", "results_db_host": "127.0.0.1",
        "main_db_port": int(env.get("BUNDLE_MAIN_DB_HOST_PORT", 15433)),
        "results_db_port": int(env.get("BUNDLE_RESULTS_DB_HOST_PORT", 15432)),
        "main_db_user": user, "results_db_user": user,
        "main_db_password": pw, "results_db_password": pw,
    }


def apply_to_config(cfg):
    """Return ``cfg`` with the deploy-stack ports/credentials folded in."""
    import dataclasses
    return dataclasses.replace(cfg, **config_overlay())


def format_validation(checks: "list[Check]") -> str:
    lines = ["deploy profile validation:"]
    for c in checks:
        lines.append(f"  {'✓' if c.ok else '✗'} {c.name}: {c.detail}")
    return "\n".join(lines)
