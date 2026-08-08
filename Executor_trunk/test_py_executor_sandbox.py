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
# (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
# Ukraine
#
# See LICENSE and NOTICE.md for the binding terms.

"""STEP 28 targeted tests: the Linux sandbox backend for the Python Executor.

Covers the acceptance criteria with the four adversarial candidates + one normal
API candidate run under the secure rootless-Docker ``container`` backend, the
fail-closed selection when a secure backend is unavailable, the always-on
``local`` backend's rlimit/env/output controls, and deterministic argv
construction for the ``container``/``bubblewrap`` backends (no namespace or
daemon required).

The container/network tests skip cleanly when rootless Docker (or the sandbox
image) is unavailable -- e.g. inside a CI sandbox that forbids it -- so the suite
runs everywhere; the namespace-free local/argv/fail-closed tests always run.

    python3 -m pytest test_py_executor_sandbox.py        # from Executor_trunk
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import sandbox  # noqa: E402

_spec = importlib.util.spec_from_file_location("py_executor_sbx", HERE / "py_executor.py")
py_executor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(py_executor)
RUNNER = py_executor._RUNNER
Outcome = py_executor.Outcome


# ----------------------------- docker availability --------------------------- #
def _docker_available() -> bool:
    cmd, host = sandbox._discover_docker()
    if not cmd:
        return False
    try:
        r = subprocess.run([cmd, "image", "inspect", sandbox.DEFAULT_SANDBOX_IMAGE],
                           env=sandbox._docker_env(host), capture_output=True, timeout=30)
        return r.returncode == 0
    except Exception:
        return False


DOCKER_OK = _docker_available()
requires_docker = pytest.mark.skipif(
    not DOCKER_OK,
    reason=f"rootless docker + image {sandbox.DEFAULT_SANDBOX_IMAGE!r} not available")


def _policy(backend="container", network="disabled", timeout=8, **over):
    p = dict(backend=backend, profile="step28-test", trusted=False,
             timeout_seconds=timeout, cpu_seconds=None,
             memory_bytes=256 * 1024 * 1024, max_processes=16,
             network=network,
             network_allowlist=["127.0.0.1"] if network == "allowlist" else [],
             env_allowlist=["PATH", "HOME", "TMPDIR"],
             stdout_max_bytes=65536, stderr_max_bytes=65536,
             allowed_interpreters=["python"])
    p.update(over)
    return p


def _container_sandbox(**over):
    return sandbox.build_sandbox(_policy(**over), runner=RUNNER, host_python=sys.executable)


def _candidate(td, name, body):
    p = Path(td) / name
    p.write_text(body, encoding="utf-8")
    return p


def _run(sb, candidate):
    return py_executor.run_candidate(sys.executable, candidate, [], None, sb)


@pytest.fixture(scope="module", autouse=True)
def _sweep_sandbox_networks():
    yield
    sandbox.cleanup_sandbox_networks()      # defensive: remove any leftover dedicated networks


# a real tiny HTTP API the allowlist test's candidate actually contacts
_API_SERVER_SRC = (
    "from http.server import HTTPServer, BaseHTTPRequestHandler\n"
    "class H(BaseHTTPRequestHandler):\n"
    "    def do_GET(self):\n"
    "        self.send_response(200); self.end_headers(); self.wfile.write(b'API-OK')\n"
    "    def log_message(self, *a):\n"
    "        pass\n"
    "HTTPServer(('0.0.0.0', 8000), H).serve_forever()\n")


# =========================== container backend (secure) ====================== #
@requires_docker
def test_container_cannot_read_protected_host_file():
    """Acceptance: a candidate cannot read an arbitrary protected host file. The
    host's directories are simply not mounted into the read-only container, so
    open() raises and the candidate dies before printing a verdict -> BROKEN. The
    A/B control (same candidate, no sandbox) reads it fine, proving the sandbox
    is what blocks it."""
    sb = _container_sandbox()
    try:
        with tempfile.TemporaryDirectory() as td:
            secret = Path(td) / "host_secret.txt"
            secret.write_text("TOP SECRET\n", encoding="utf-8")
            c = _candidate(td, "1_0_0.py", f"open({str(secret)!r}).read()\nFW_VAR = 0\n")

            assert _run(sb, c) == (Outcome.BROKEN, None, None)      # sandboxed: blocked
            assert _run(None, c) == (None, 0, -999)                 # control: reads fine
    finally:
        sb.close()


@requires_docker
def test_container_cannot_write_outside_scratch():
    """Acceptance: a candidate cannot write outside its scratch. The root fs is
    --read-only; only the /sandbox tmpfs is writable."""
    sb = _container_sandbox()
    try:
        with tempfile.TemporaryDirectory() as td:
            outside = _candidate(td, "2_0_0.py", "open('/etc/bundle_evil','w').write('x')\nFW_VAR = 0\n")
            assert _run(sb, outside) == (Outcome.BROKEN, None, None)
            # writing INTO the scratch works -> the candidate reaches a verdict
            inside = _candidate(td, "3_0_0.py", "open('/sandbox/ok','w').write('x')\nFW_VAR = 0\n")
            assert _run(sb, inside) == (None, 0, -999)
    finally:
        sb.close()


@requires_docker
def test_container_infinite_loop_is_timeout():
    """Acceptance: an infinite loop -> TIMEOUT (wall-clock bound, killed near the
    timeout, not hung)."""
    sb = _container_sandbox(timeout=4)
    try:
        with tempfile.TemporaryDirectory() as td:
            c = _candidate(td, "4_0_0.py", "while True:\n    pass\n")
            t0 = time.time()
            assert _run(sb, c) == (Outcome.TIMEOUT, None, None)
            assert time.time() - t0 < 25
    finally:
        sb.close()


@requires_docker
def test_container_cpu_seconds_is_enforced():
    """Acceptance / gap-3: the policy's cpu_seconds is enforced (--ulimit cpu).
    A CPU burn is stopped by the CPU-time budget WELL before the (much larger)
    wall-clock timeout, and is classified TIMEOUT -- not left to run to the wall
    bound, and not mis-read as a memory kill."""
    sb = _container_sandbox(timeout=30, cpu_seconds=2)
    try:
        with tempfile.TemporaryDirectory() as td:
            c = _candidate(td, "8_0_0.py", "x = 0\nwhile True:\n    x += 1\n")
            t0 = time.time()
            assert _run(sb, c) == (Outcome.TIMEOUT, None, None)
            assert time.time() - t0 < 15      # stopped near cpu=2s, NOT the 30s wall timeout
    finally:
        sb.close()


@requires_docker
def test_container_fork_abuse_is_limited():
    """Acceptance: fork/process abuse limited. --pids-limit caps the live process
    count; the candidate's forks start failing with OSError well before its 500
    target, it handles them and still produces a verdict -- demonstrating the cap
    without the container melting down."""
    sb = _container_sandbox(max_processes=8, timeout=12)
    try:
        with tempfile.TemporaryDirectory() as td:
            body = (
                "import os, time\n"
                "forked = 0\n"
                "for _ in range(500):\n"
                "    try:\n"
                "        pid = os.fork()\n"
                "    except OSError:\n"
                "        break\n"
                "    if pid == 0:\n"
                "        time.sleep(30)\n"       # children stay alive -> occupy the pids budget
                "        os._exit(0)\n"
                "    forked += 1\n"
                "FW_VAR = 0 if forked < 500 else 1\n")
            c = _candidate(td, "6_0_0.py", body)
            outcome, fw, _ = _run(sb, c)
            assert outcome is None and fw == 0, (outcome, fw)
    finally:
        sb.close()


@requires_docker
def test_container_network_disabled_blocks_internet():
    """Acceptance: network policy demonstrable. network=disabled (--network none)
    -> the candidate cannot reach the Internet."""
    sb = _container_sandbox(network="disabled", timeout=8)
    try:
        with tempfile.TemporaryDirectory() as td:
            body = ("import socket\n"
                    "try:\n"
                    "    socket.create_connection(('1.1.1.1', 53), 3)\n"
                    "    FW_VAR = 1\n"            # reached the Internet -- must NOT happen
                    "except OSError:\n"
                    "    FW_VAR = 0\n")           # blocked, as required
            c = _candidate(td, "5_0_0.py", body)
            assert _run(sb, c) == (None, 0, -999)
    finally:
        sb.close()


@requires_docker
def test_container_allowlist_is_policy_driven_and_enforced():
    """The allowlist is real AND policy-driven, not a test-only attach.

    `network_allowlist` names the target container. `provision()` -- the SAME
    method py_executor.main() calls in production -- attaches only that target to
    the sandbox's DEDICATED ``--internal`` network. The candidate actually GETs it
    (b'API-OK'), yet cannot reach the Internet NOR a non-allowlisted server. And
    `attach_target` itself refuses anything outside `network_allowlist` (it cannot
    widen the policy). Finally close() removes the dedicated network (gap-4)."""
    cmd, host = sandbox._discover_docker()
    env = sandbox._docker_env(host)
    allowed = f"bundle-sbx-api-{uuid.uuid4().hex[:8]}"
    denied = f"bundle-sbx-other-{uuid.uuid4().hex[:8]}"
    # the policy's allowlist NAMES the permitted target container
    sb = _container_sandbox(network="allowlist", timeout=15, network_allowlist=[allowed])
    net = None
    try:
        # two real servers, NEITHER pre-attached to the candidate's network
        for nm in (allowed, denied):
            subprocess.run([cmd, "run", "-d", "--name", nm, sandbox.DEFAULT_SANDBOX_IMAGE,
                            "python", "-c", _API_SERVER_SRC], env=env, check=True,
                           capture_output=True, timeout=60)
        time.sleep(2)        # let the servers bind

        # PRODUCTION wiring: provision() attaches allowlisted targets, driven by
        # the policy -- exactly what py_executor.main() invokes. Only `allowed`.
        assert sb.provision() == 1
        net = sb._net_name
        assert subprocess.run([cmd, "network", "inspect", "-f", "{{.Internal}}", net],
                              env=env, capture_output=True, text=True).stdout.strip() == "true"

        with tempfile.TemporaryDirectory() as td:
            body = ("import urllib.request, socket\n"
                    "def get(u):\n"
                    "    try:\n"
                    "        return urllib.request.urlopen(u, timeout=5).read()\n"
                    "    except Exception:\n"
                    "        return b''\n"
                    f"reached_allowed = get('http://{allowed}:8000/') == b'API-OK'\n"
                    "try:\n"
                    "    socket.create_connection(('1.1.1.1', 53), 3); internet = True\n"
                    "except OSError:\n"
                    "    internet = False\n"
                    "try:\n"
                    f"    socket.create_connection(('{denied}', 8000), 3); reached_denied = True\n"
                    "except OSError:\n"
                    "    reached_denied = False\n"
                    "FW_VAR = 0 if (reached_allowed and not internet and not reached_denied) else 1\n")
            c = _candidate(td, "7_0_0.py", body)
            assert _run(sb, c) == (None, 0, -999)      # reached only the allowlisted target

        # the primitive itself enforces the policy: a non-allowlisted target is refused
        with pytest.raises(sandbox.SandboxError):
            sb.attach_target(denied)
    finally:
        subprocess.run([cmd, "rm", "-f", allowed, denied], env=env, capture_output=True)
        sb.close()
        if net:                                        # gap-4: close() removed the dedicated net
            left = subprocess.run([cmd, "network", "ls", "--filter", f"name={net}", "--format",
                                   "{{.Name}}"], env=env, capture_output=True, text=True).stdout.strip()
            assert left == "", f"close() must remove the dedicated network, found {left!r}"


@requires_docker
def test_main_provisions_allowlist_target_in_production(tmp_path):
    """End-to-end PRODUCTION proof: a real py_executor process, given an
    `allowlist` execution policy whose network_allowlist names a running target
    container, attaches it (logs "attached 1 target") and the candidate reaches
    it -- i.e. provision() is wired into main(), not only the tests."""
    cmd, host = sandbox._discover_docker()
    env = sandbox._docker_env(host)
    target = f"bundle-sbx-api-{uuid.uuid4().hex[:8]}"
    candidate_body = (
        "import urllib.request, time\n"
        "ok = False\n"
        "for _ in range(12):\n"
        "    try:\n"
        f"        ok = urllib.request.urlopen('http://{target}:8000/', timeout=3).read() == b'API-OK'\n"
        "        if ok:\n"
        "            break\n"
        "    except Exception:\n"
        "        time.sleep(0.5)\n"
        "FW_VAR = 0 if ok else 1\n")
    manifest, sqldir = _write_manifest_and_policy(
        tmp_path, "container", network="allowlist", network_allowlist=[target],
        candidate_body=candidate_body)
    try:
        subprocess.run([cmd, "run", "-d", "--name", target, sandbox.DEFAULT_SANDBOX_IMAGE,
                        "python", "-c", _API_SERVER_SRC], env=env, check=True, capture_output=True, timeout=60)
        time.sleep(2)
        out, rc = _run_py_executor(manifest, sqldir)
        assert "attached 1 target" in out, out          # main() provisioned it (production wiring)
        assert "processed=1 pass=1" in out, out          # the candidate reached the allowlisted API
        assert rc == 0, out
    finally:
        subprocess.run([cmd, "rm", "-f", target], env=env, capture_output=True)
        sandbox.cleanup_sandbox_networks()


@requires_docker
def test_container_leaves_nothing_behind():
    """Acceptance / action 7: sandbox cleanup guaranteed -- including the harder
    timeout case where the wall-clock kill leaves the container running in the
    daemon until force-removed."""
    sb = _container_sandbox(timeout=4)
    cmd, host = sandbox._discover_docker()
    env = sandbox._docker_env(host)

    def leftover():
        r = subprocess.run([cmd, "ps", "-a", "--filter", "name=bundle-sbx-",
                            "--format", "{{.Names}}"], env=env, capture_output=True, text=True)
        return [n for n in r.stdout.split() if n]

    try:
        with tempfile.TemporaryDirectory() as td:
            _run(sb, _candidate(td, "1_0_0.py", "FW_VAR = 0\n"))          # clean exit
            _run(sb, _candidate(td, "4_0_0.py", "while True:\n    pass\n"))  # timeout kill
            assert leftover() == []
    finally:
        sb.close()


@requires_docker
def test_main_runs_candidate_under_container_sandbox(tmp_path):
    """End-to-end: py_executor, given a manifest + a container execution policy,
    runs the candidate inside the sandbox (no DB needed: --writeToDB false)."""
    manifest, sqldir = _write_manifest_and_policy(tmp_path, "container")
    out, rc = _run_py_executor(manifest, sqldir)
    assert "sandbox → container" in out, out
    assert "processed=1" in out, out
    assert rc == 0, out


# ============================== fail-closed (action 5) ======================= #
def test_build_sandbox_fails_closed_on_missing_container_image():
    """A secure container policy whose image/daemon is unavailable must raise --
    never silently return an unsandboxed run. Works with or without Docker
    present (no daemon -> unavailable; daemon -> bogus image inspect fails)."""
    with pytest.raises(sandbox.SandboxUnavailable):
        sandbox.build_sandbox(_policy(backend="container"), runner=RUNNER,
                              host_python=sys.executable,
                              image="bundle/definitely-not-real:nope")


def test_build_sandbox_fails_closed_when_bubblewrap_unavailable():
    spec = sandbox.SandboxSpec.from_policy(_policy(backend="bubblewrap"))
    if sandbox.BubblewrapBackend(spec, RUNNER, sys.executable).is_available():
        pytest.skip("bubblewrap IS usable here; the unavailable path isn't exercisable")
    with pytest.raises(sandbox.SandboxUnavailable):
        sandbox.build_sandbox(_policy(backend="bubblewrap"), runner=RUNNER, host_python=sys.executable)


def test_main_fails_closed_when_secure_backend_unavailable(tmp_path):
    """py_executor must refuse to run candidates when a secure policy's backend
    is unavailable: FATAL, non-zero exit, processed=0 (no candidate ran)."""
    spec = sandbox.SandboxSpec.from_policy(_policy(backend="bubblewrap"))
    if sandbox.BubblewrapBackend(spec, RUNNER, sys.executable).is_available():
        pytest.skip("bubblewrap usable here; cannot exercise the unavailable path")
    manifest, sqldir = _write_manifest_and_policy(tmp_path, "bubblewrap")
    out, rc = _run_py_executor(manifest, sqldir)
    assert rc != 0, out
    assert "FATAL" in out and "bubblewrap" in out, out
    assert "processed=0" in out, out


def test_unknown_backend_is_rejected():
    with pytest.raises(sandbox.SandboxUnavailable):
        sandbox.build_sandbox(_policy(backend="wormhole"), runner=RUNNER, host_python=sys.executable)


def test_attach_target_enforces_allowlist_without_docker():
    """attach_target validates against network_allowlist BEFORE touching Docker,
    so the policy check is exercisable here: a non-allowlisted target is rejected
    (it cannot widen the policy), and _allowlist_hosts strips ports and drops
    loopback placeholders. provision() is a no-op (0) for a non-allowlist policy."""
    spec = sandbox.SandboxSpec.from_policy(
        _policy(backend="container", network="allowlist", network_allowlist=["api-target:8000", "127.0.0.1"]))
    be = sandbox.ContainerBackend(spec, RUNNER, "python:3-slim", "docker", None)
    assert be._allowlist_hosts() == {"api-target"}                 # port stripped, loopback dropped
    with pytest.raises(sandbox.SandboxError):
        be.attach_target("evil-host")                              # not allowlisted -> rejected (no docker call)
    with pytest.raises(sandbox.SandboxError):
        be.attach_target("api-target", alias="evil-alias")         # alias must be allowlisted too


def test_provision_is_noop_for_non_allowlist_policy():
    spec = sandbox.SandboxSpec.from_policy(_policy(backend="container", network="disabled"))
    be = sandbox.ContainerBackend(spec, RUNNER, "python:3-slim", "docker", None)
    assert be.provision() == 0          # nothing to attach; no Docker calls made


# ====================== backend selection (local / trusted) ================== #
def test_trusted_local_returns_no_backend():
    pol = _policy(backend="local", trusted=True, env_allowlist=["*"], network="unrestricted")
    assert sandbox.build_sandbox(pol, runner=RUNNER, host_python=sys.executable) is None


def test_no_policy_returns_no_backend():
    assert sandbox.build_sandbox(None, runner=RUNNER, host_python=sys.executable) is None
    assert sandbox.build_sandbox({}, runner=RUNNER, host_python=sys.executable) is None


def test_nontrusted_local_returns_local_backend():
    sb = sandbox.build_sandbox(_policy(backend="local"), runner=RUNNER, host_python=sys.executable)
    try:
        assert isinstance(sb, sandbox.LocalBackend)
    finally:
        sb.close()


# ============================ local backend (no docker) ====================== #
def test_local_backend_filters_secret_env():
    """The candidate sees only allowlisted env names -- a host secret-shaped var
    never reaches it."""
    os.environ["BUNDLE_SBX_FAKE_SECRET"] = "leak-me"
    os.environ["BUNDLE_SBX_OK"] = "visible"
    try:
        pol = _policy(backend="local", timeout=10,
                      env_allowlist=["PATH", "HOME", "TMPDIR", "BUNDLE_SBX_OK"])
        sb = sandbox.build_sandbox(pol, runner=RUNNER, host_python=sys.executable)
        try:
            with tempfile.TemporaryDirectory() as td:
                body = ("import os\n"
                        "leaked = 'BUNDLE_SBX_FAKE_SECRET' in os.environ\n"
                        "ok = os.environ.get('BUNDLE_SBX_OK') == 'visible'\n"
                        "FW_VAR = 0 if (ok and not leaked) else 1\n")
                assert _run(sb, _candidate(td, "1_0_0.py", body)) == (None, 0, -999)
        finally:
            sb.close()
    finally:
        os.environ.pop("BUNDLE_SBX_FAKE_SECRET", None)
        os.environ.pop("BUNDLE_SBX_OK", None)


def test_local_backend_timeout_via_wall_clock():
    sb = sandbox.build_sandbox(_policy(backend="local", timeout=2),
                               runner=RUNNER, host_python=sys.executable)
    try:
        with tempfile.TemporaryDirectory() as td:
            c = _candidate(td, "1_0_0.py", "import time\ntime.sleep(30)\nFW_VAR = 0\n")
            t0 = time.time()
            assert _run(sb, c) == (Outcome.TIMEOUT, None, None)
            assert time.time() - t0 < 15
    finally:
        sb.close()


def test_local_backend_caps_stdout():
    """Output cap: a candidate that floods stdout is truncated to the policy cap
    (and the flood does not deadlock or balloon the Executor)."""
    sb = sandbox.build_sandbox(_policy(backend="local", timeout=10, stdout_max_bytes=4096),
                               runner=RUNNER, host_python=sys.executable)
    try:
        with tempfile.TemporaryDirectory() as td:
            c = _candidate(td, "1_0_0.py", "import sys\nsys.stdout.write('A'*1000000)\nFW_VAR=0\n")
            res = sb.run(c, [])
            assert len(res.stdout.encode("utf-8", "replace")) <= 4096
            assert res.truncated
    finally:
        sb.close()


# ======================= argv construction (deterministic) =================== #
def test_container_argv_enforces_isolation_and_never_publishes_ports():
    cmd, host = sandbox._discover_docker()
    spec = sandbox.SandboxSpec.from_policy(_policy(backend="container"))
    be = sandbox.ContainerBackend(spec, RUNNER, "python:3-slim", cmd or "docker", host)
    argv = be.build_argv(Path("/tmp/cand.py"), ["ARG1"], name="bundle-sbx-x", network="none")

    assert "--read-only" in argv
    assert "--network" in argv and "none" in argv
    assert "--pids-limit" in argv
    assert "--cap-drop" in argv and "ALL" in argv
    assert "--security-opt" in argv and "no-new-privileges" in argv
    assert any(":/candidate.py:ro" in tok for tok in argv)        # candidate mounted read-only
    assert "-p" not in argv and "--publish" not in argv           # NEVER exposes a port
    for tok in argv:                                              # no host secret env leaked
        assert "PASSWORD" not in tok.upper() and "SECRET" not in tok.upper()
    # the candidate runs as: <interpreter> -c <runner> /candidate.py ARG1
    assert argv[-4:] == ["-c", RUNNER, "/candidate.py", "ARG1"]


def test_container_memory_limit_present_when_set():
    spec = sandbox.SandboxSpec.from_policy(_policy(backend="container", memory_bytes=128 * 1024 * 1024))
    be = sandbox.ContainerBackend(spec, RUNNER, "python:3-slim", "docker", None)
    argv = be.build_argv(Path("/tmp/c.py"), [], name="n", network="none")
    assert "--memory" in argv and str(128 * 1024 * 1024) in argv


def test_bubblewrap_argv_isolates_fs_and_network():
    spec = sandbox.SandboxSpec.from_policy(_policy(backend="bubblewrap", network="disabled"))
    argv = sandbox.BubblewrapBackend(spec, RUNNER, sys.executable).build_argv(Path("/tmp/cand.py"), [])
    assert "--unshare-net" in argv          # network disabled -> isolated netns
    assert "--clearenv" in argv             # host env dropped
    assert "--ro-bind" in argv              # candidate bound read-only
    assert "/candidate.py" in argv
    assert "/usr" in argv                   # runtime is bound...
    assert "/home" not in argv and "/root" not in argv   # ...user-private dirs are NOT


def test_bubblewrap_loopback_allowlist_isolates_net():
    spec = sandbox.SandboxSpec.from_policy(_policy(backend="bubblewrap", network="allowlist"))
    argv = sandbox.BubblewrapBackend(spec, RUNNER, sys.executable).build_argv(Path("/tmp/c.py"), [])
    assert "--unshare-net" in argv          # loopback-only allowlist -> isolated netns


# --------------------------------- helpers ----------------------------------- #
def _write_manifest_and_policy(td, backend, run_id="step28-run", network="disabled",
                               network_allowlist=None, candidate_body="FW_VAR = 0\n"):
    td = Path(td)
    srcdir = td / "candidates"; srcdir.mkdir(parents=True, exist_ok=True)
    (srcdir / "1_0_0.py").write_text(candidate_body, encoding="utf-8")
    sqldir = td / "sql"; sqldir.mkdir(exist_ok=True)
    (sqldir / "insert.sql").write_text("INSERT INTO results VALUES (?,?,?,?,?,?,?,?,?);", encoding="utf-8")
    manifest = td / "manifest.json"
    manifest.write_text(json.dumps({
        "protocol": "bundle.handoff/v2", "run_id": run_id, "language": "python",
        "candidate_transport": "loose-files", "candidate_count": 1, "id_format": "<c>_0_0",
        "sources": [{"kind": "dir", "path": str(srcdir)}],
        "result_target": {"host": "127.0.0.1", "port": 5432, "database": "d", "user": "postgres"},
        "result_schema_mode": "placeholders=9", "verdict_mode": "FW_VAR",
        "arguments": [], "shift": 1, "execution_policy_ref": "ep-step28",
    }), encoding="utf-8")
    # the sidecar the launcher writes next to the manifest (effective_policy_view
    # shape: id + sha256 + the full policy dict the sandbox backend consumes).
    policy = _policy(backend=backend, network=network)
    if network_allowlist is not None:
        policy["network_allowlist"] = network_allowlist
    (td / "execution_policy.json").write_text(json.dumps({
        "id": "ep-step28", "sha256": "0" * 64, "policy": policy,
    }), encoding="utf-8")
    return manifest, sqldir


def _run_py_executor(manifest, sqldir):
    env = dict(os.environ)
    env["BUNDLE_RESULTS_DB_PASSWORD"] = "x"
    r = subprocess.run([sys.executable, str(HERE / "py_executor.py"),
                        "--manifest", str(manifest), "-dirSqlTemplate", str(sqldir),
                        "--writeToDB", "false", "--failOnly", "false"],
                       capture_output=True, text=True, env=env, timeout=120)
    return r.stdout + r.stderr, r.returncode


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
