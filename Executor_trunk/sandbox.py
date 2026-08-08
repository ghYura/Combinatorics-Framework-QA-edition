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

r"""sandbox — the Linux sandbox backend layer for the Python Executor (STEP 28).

Generated Python candidates must NOT execute with unrestricted host access.
This module is the *backend interface*, kept deliberately separate from
py_executor's candidate loop (STEP 28 action 2): the loop asks a backend to run
one candidate and gets back a plain :class:`SandboxResult`; it never learns how
the isolation is achieved. py_executor.run_candidate maps that result onto the
canonical outcome model (STEP 21) exactly as it does for an unsandboxed run, so
TIMEOUT / BROKEN / INFRA_FAIL classification stays in one place.

Backends (selected by the execution policy's ``backend`` field, STEP 27):

  * ``container``  -- rootless Docker. The secure default for the
                      ``generated-default`` / ``networked-api-probe`` profiles.
                      Enforces (action 3): ``--read-only`` root, an isolated
                      writable ``--tmpfs`` scratch, ``--pids-limit`` /
                      ``--memory`` / CPU-time ``--ulimit cpu`` (the policy's
                      cpu_seconds) / wall-clock timeout, a from-empty env with
                      only allowlisted names, an output cap, and ``--network
                      none`` (disabled) or a DEDICATED, per-sandbox local-only
                      ``--internal`` Docker network (allowlist) whose only
                      members are the candidate and the targets the operator
                      attaches via :meth:`ContainerBackend.attach_target`. It
                      NEVER publishes a port (no ``-p``), so a sandboxed candidate
                      is never reachable from the LAN/Internet -- only local,
                      inter-container traffic to an explicitly-allowlisted target
                      is possible (the operator's explicit constraint).
  * ``bubblewrap`` -- daemonless user-namespace sandbox for hosts that permit
                      unprivileged userns. Argv is built + unit-tested here; its
                      availability is probed with a real `/bin/true` self-test,
                      so a host that cannot create the namespaces fails closed
                      rather than silently running unconfined.
  * ``local``      -- the ``trusted-local`` profile's explicit opt-in. A trusted
                      policy returns *no* backend (None) and py_executor runs the
                      candidate exactly as the legacy path did. A *non*-trusted
                      ``local`` policy still gets best-effort rlimit / env /
                      output / timeout confinement (no fs or network namespace
                      isolation -- that is what ``container``/``bubblewrap`` are
                      for) so the knobs are testable without a container runtime.

Fail-closed (action 5): :func:`build_sandbox` raises :class:`SandboxUnavailable`
when a *secure* policy names a backend whose :meth:`SandboxBackend.is_available`
self-test does not pass. py_executor turns that into a fatal, non-fallback exit
-- a secure run never degrades to unsandboxed local execution.

Cleanup (action 7): every backend guarantees teardown of what it created -- the
container backend force-removes its (uniquely named) container even on timeout,
and :meth:`ContainerBackend.close` removes the dedicated per-sandbox internal
network (disconnecting any attached targets first); the local backend deletes
its scratch tempdir. :meth:`SandboxBackend.close` is idempotent and best-effort;
:func:`cleanup_sandbox_networks` is a defensive sweep for any network a crash
left behind.

Standalone by design (no generator_trunk import, like py_executor itself) so the
Executor stays independently runnable; the policy it consumes is the plain dict
the launcher writes to ``execution_policy.json`` (bundle.policy.effective_policy
_view -> ``["policy"]``).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence

try:                       # POSIX-only; absent on non-Unix, where rlimits are skipped.
    import resource
except ImportError:        # pragma: no cover - this Executor only ever runs on Linux
    resource = None


# The default container image for the Python sandbox. Overridable via the
# BUNDLE_SANDBOX_IMAGE env var (and, later, bundle config). Must contain a
# `python` interpreter; the candidate runs as `python -c <runner> /candidate.py`.
DEFAULT_SANDBOX_IMAGE = os.environ.get("BUNDLE_SANDBOX_IMAGE", "python:3-slim")

# Each ContainerBackend in `allowlist` mode creates its OWN dedicated
# `<prefix><uuid>` network with `--internal` (containers on it talk to each other
# but have NO route to the host loopback or the Internet -- the operator's
# local-only requirement) and removes it on close(). A dedicated-per-sandbox
# network -- not a shared one -- is what makes the allowlist real: the only
# things on a candidate's network are the candidate and the targets the operator
# explicitly attaches (attach_target), nothing else, and it does not persist.
SANDBOX_NETWORK_PREFIX = os.environ.get("BUNDLE_SANDBOX_NETWORK_PREFIX", "bundle-sbx-net-")

_CANDIDATE_IN_SANDBOX = "/candidate.py"   # read-only mount point inside the sandbox
_SCRATCH_IN_SANDBOX = "/sandbox"          # writable tmpfs / scratch inside the sandbox


class SandboxError(RuntimeError):
    """A sandbox could not be built or run for a reason that is the sandbox's
    own fault (misconfiguration, runtime failure), not the candidate's."""


class SandboxUnavailable(SandboxError):
    """The backend a *secure* policy requires is not usable on this host. The
    launcher MUST fail closed on this -- never silently run the candidate
    unsandboxed (STEP 28 action 5 / STEP 30 "Secure mode не использует local
    fallback")."""


@dataclass(frozen=True)
class SandboxResult:
    """What a backend hands back for one candidate run -- deliberately the same
    shape an unsandboxed ``subprocess.run`` would yield, so py_executor.run_
    candidate classifies it identically. ``spawn_error`` is set when the sandbox
    itself could not start the process (-> INFRA_FAIL, the candidate is
    blameless); ``timed_out`` when the wall-clock/CPU limit fired (-> TIMEOUT).
    ``truncated`` flags that output hit the policy's byte cap."""

    returncode: Optional[int]
    stdout: str
    stderr: str
    timed_out: bool = False
    spawn_error: Optional[str] = None
    truncated: bool = False


# --------------------------- normalized policy view -------------------------- #
@dataclass(frozen=True)
class SandboxSpec:
    """The execution-policy knobs a backend needs, parsed from the plain policy
    dict (bundle.policy.ExecutionPolicy serialized). Tolerant of missing keys so
    a partial/legacy sidecar still yields a usable (conservative) spec."""

    backend: str = "local"
    profile: str = "unknown"
    trusted: bool = False
    timeout_seconds: float = 30.0
    cpu_seconds: Optional[float] = None
    memory_bytes: Optional[int] = None
    max_processes: Optional[int] = 64
    network: str = "disabled"             # disabled | allowlist | unrestricted
    network_allowlist: Sequence[str] = ()
    env_allowlist: Sequence[str] = ()
    stdout_max_bytes: int = 1024 * 1024
    stderr_max_bytes: int = 1024 * 1024
    interpreter: str = "python"

    @classmethod
    def from_policy(cls, policy: Mapping) -> "SandboxSpec":
        interps = tuple(policy.get("allowed_interpreters") or ("python",))
        return cls(
            backend=policy.get("backend", "local"),
            profile=policy.get("profile", "unknown"),
            trusted=bool(policy.get("trusted", False)),
            timeout_seconds=float(policy.get("timeout_seconds", 30.0)),
            cpu_seconds=policy.get("cpu_seconds"),
            memory_bytes=policy.get("memory_bytes"),
            max_processes=policy.get("max_processes", 64),
            network=policy.get("network", "disabled"),
            network_allowlist=tuple(policy.get("network_allowlist") or ()),
            env_allowlist=tuple(policy.get("env_allowlist") or ()),
            stdout_max_bytes=int(policy.get("stdout_max_bytes", 1024 * 1024)),
            stderr_max_bytes=int(policy.get("stderr_max_bytes", 1024 * 1024)),
            interpreter=interps[0],
        )


# ------------------------------- bounded capture ----------------------------- #
def _run_capped(argv, *, env, timeout, out_cap, err_cap,
                preexec_fn=None, start_new_session=False,
                on_timeout: Optional[Callable[[subprocess.Popen], None]] = None):
    """Run *argv*, capturing at most ``out_cap``/``err_cap`` bytes of each stream
    (output cap, action 3) and enforcing a wall-clock ``timeout``.

    Excess output is drained-and-discarded by the reader threads rather than
    left to fill the pipe, so a candidate that floods stdout cannot deadlock the
    Executor *or* balloon its memory -- it simply runs on until the timeout/CPU
    limit stops it. On timeout the process is killed (``on_timeout`` first, for
    backends -- e.g. Docker -- that must tear down out-of-process state, then
    SIGKILL to the process/group). Returns
    ``(returncode, stdout, stderr, timed_out, truncated, spawn_error)``."""
    try:
        proc = subprocess.Popen(
            argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, preexec_fn=preexec_fn, start_new_session=start_new_session)
    except OSError as exc:
        return None, "", "", False, False, f"{type(exc).__name__}: {exc}"

    bufs = {"out": bytearray(), "err": bytearray()}
    truncated = {"out": False, "err": False}
    caps = {"out": out_cap, "err": err_cap}

    def drain(stream, key):
        cap = caps[key]
        buf = bufs[key]
        try:
            while True:
                chunk = stream.read(65536)
                if not chunk:
                    break
                if len(buf) < cap:
                    buf.extend(chunk[: cap - len(buf)])
                if len(buf) >= cap:
                    truncated[key] = True   # keep looping to drain (don't block the child)
        except (OSError, ValueError):
            pass

    threads = [threading.Thread(target=drain, args=(proc.stdout, "out"), daemon=True),
               threading.Thread(target=drain, args=(proc.stderr, "err"), daemon=True)]
    for t in threads:
        t.start()

    timed_out = False
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        if on_timeout is not None:
            try:
                on_timeout(proc)
            except Exception:
                pass
        _kill(proc, start_new_session)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
    for t in threads:
        t.join(timeout=5)
    for s in (proc.stdout, proc.stderr):
        try:
            s.close()
        except Exception:
            pass

    out = bufs["out"].decode("utf-8", "replace")
    err = bufs["err"].decode("utf-8", "replace")
    return proc.returncode, out, err, timed_out, (truncated["out"] or truncated["err"]), None


def _kill(proc: subprocess.Popen, killpg: bool) -> None:
    try:
        if killpg:
            os.killpg(os.getpgid(proc.pid), 9)
        else:
            proc.kill()
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except Exception:
            pass


# ------------------------------- backend base -------------------------------- #
class SandboxBackend:
    """Run one candidate under isolation. Subclasses implement :meth:`run`;
    :meth:`is_available` is a real functional self-test, not a version check."""

    name = "base"

    def __init__(self, spec: SandboxSpec, runner: str):
        self.spec = spec
        self.runner = runner

    def is_available(self) -> bool:          # pragma: no cover - overridden
        return False

    def run(self, candidate: Path, argv: Sequence[str]) -> SandboxResult:  # pragma: no cover
        raise NotImplementedError

    def provision(self) -> int:
        """Production hook the launcher/Executor calls once, before any candidate
        runs, to wire up policy-mandated resources (the container backend attaches
        the allowlisted network targets here). Base: nothing. Returns the number
        provisioned."""
        return 0

    def describe(self) -> str:               # pragma: no cover - trivial
        return self.name

    def close(self) -> None:                 # idempotent, best-effort
        pass


# ------------------------------- local backend ------------------------------- #
def _rlimit_preexec(spec: SandboxSpec) -> Optional[Callable[[], None]]:
    """Build a ``preexec_fn`` applying the policy's CPU/memory/file-size rlimits
    to the child (defense-in-depth; also the only enforcement the no-namespace
    ``local`` backend has). Returns None when ``resource`` is unavailable. rlimits
    are inherited across exec and into a namespace, so the same function hardens
    the bubblewrap child too.

    Note: RLIMIT_NPROC is intentionally NOT set -- it is per-real-uid (counting
    every process the user already runs, not just the candidate's), so on a busy
    host it would block the candidate's forks wholesale or even mis-account. The
    correct process-count control is the container backend's per-cgroup
    ``--pids-limit`` (and, for bubblewrap, the PID namespace bounded by the
    memory limit); the local backend leaves process count to the OS."""
    if resource is None:
        return None

    def apply() -> None:
        def _set(which, soft):
            try:
                inf = resource.RLIM_INFINITY
                _, cur_hard = resource.getrlimit(which)
                if cur_hard != inf and soft > cur_hard:
                    soft = cur_hard
                resource.setrlimit(which, (soft, soft if cur_hard == inf else cur_hard))
            except (ValueError, OSError):
                pass
        if spec.cpu_seconds:
            _set(resource.RLIMIT_CPU, int(spec.cpu_seconds) + 1)
        if spec.memory_bytes:
            _set(resource.RLIMIT_AS, int(spec.memory_bytes))
        # cap any single file the candidate writes to its scratch (no fs namespace here)
        _set(resource.RLIMIT_FSIZE, 64 * 1024 * 1024)
        # NB: the child's own session/process-group (so a timeout can killpg the
        # whole tree) comes from Popen(start_new_session=True); we must NOT call
        # os.setsid() here too -- the second call would EPERM (already a session
        # leader) and abort the spawn.

    return apply


def _filtered_env(spec: SandboxSpec, scratch: str) -> dict:
    """A minimal environment: only the policy's allowlisted names (never the
    '*' wildcard for a secure profile -- the policy validator already forbids
    that), with HOME/TMPDIR redirected into the scratch dir."""
    env = {}
    src = dict(os.environ)
    if "*" in spec.env_allowlist:
        env.update(src)                       # trusted profiles only
    else:
        for name in spec.env_allowlist:
            if name in src:
                env[name] = src[name]
    env.setdefault("PATH", src.get("PATH", "/usr/bin:/bin"))
    env["HOME"] = scratch
    env["TMPDIR"] = scratch
    return env


class LocalBackend(SandboxBackend):
    """No namespace isolation -- best-effort rlimit/env/output/timeout
    confinement only. Used for a *non*-trusted ``local`` policy (so the resource
    knobs are exercisable without a container runtime); a *trusted* ``local``
    policy bypasses the sandbox entirely (build_sandbox returns None)."""

    name = "local"

    def __init__(self, spec: SandboxSpec, runner: str, host_python: str):
        super().__init__(spec, runner)
        self.host_python = host_python
        self._scratch = tempfile.mkdtemp(prefix="bundle-sbx-local-")

    def is_available(self) -> bool:
        return True

    def describe(self) -> str:
        return (f"local (no namespace isolation; rlimits cpu={self.spec.cpu_seconds} "
                f"nproc={self.spec.max_processes} as={self.spec.memory_bytes})")

    def run(self, candidate: Path, argv: Sequence[str]) -> SandboxResult:
        cmd = [self.host_python, "-c", self.runner, str(candidate), *map(str, argv)]
        env = _filtered_env(self.spec, self._scratch)
        rc, out, err, timed_out, trunc, spawn = _run_capped(
            cmd, env=env, timeout=self.spec.timeout_seconds,
            out_cap=self.spec.stdout_max_bytes, err_cap=self.spec.stderr_max_bytes,
            preexec_fn=_rlimit_preexec(self.spec), start_new_session=True)
        return SandboxResult(rc, out, err, timed_out=timed_out, spawn_error=spawn, truncated=trunc)

    def close(self) -> None:
        shutil.rmtree(self._scratch, ignore_errors=True)


# ----------------------------- bubblewrap backend ---------------------------- #
class BubblewrapBackend(SandboxBackend):
    """Daemonless userns sandbox. Builds a ``bwrap`` command that ro-binds only
    the system runtime (NOT /home, /root, /etc/shadow, ...), gives a writable
    tmpfs scratch, drops the candidate in read-only, and unshares the network
    when the policy disables it. rlimits ride along via the same preexec_fn."""

    name = "bubblewrap"
    BWRAP = shutil.which("bwrap") or "/usr/bin/bwrap"
    # ro-bound only if present -- the candidate gets the interpreter + libs and
    # nothing user-private. `--ro-bind-try` no-ops a missing path.
    _RUNTIME_ROOTS = ("/usr", "/bin", "/sbin", "/lib", "/lib32", "/lib64",
                      "/etc/alternatives", "/etc/ssl", "/etc/ld.so.cache")

    def __init__(self, spec: SandboxSpec, runner: str, host_python: str):
        super().__init__(spec, runner)
        self.host_python = host_python

    def build_argv(self, candidate: Path, argv: Sequence[str]) -> list:
        """The full ``bwrap ... python -c <runner> /candidate.py`` argv. Pure /
        side-effect-free so it is unit-testable without creating namespaces."""
        cmd = [self.BWRAP,
               "--unshare-user", "--unshare-pid", "--unshare-ipc",
               "--unshare-uts", "--unshare-cgroup",
               "--die-with-parent", "--new-session",
               "--clearenv",
               "--proc", "/proc", "--dev", "/dev",
               "--tmpfs", "/tmp", "--tmpfs", _SCRATCH_IN_SANDBOX,
               "--chdir", _SCRATCH_IN_SANDBOX,
               "--ro-bind", str(candidate), _CANDIDATE_IN_SANDBOX]
        for root in self._RUNTIME_ROOTS:
            cmd += ["--ro-bind-try", root, root]
        if self.spec.network == "disabled":
            cmd += ["--unshare-net"]          # isolated netns (loopback only) -> no egress
        elif self.spec.network == "allowlist":
            # bwrap enforces network at namespace granularity only; a loopback-
            # only allowlist maps cleanly to an isolated netns, anything wider
            # cannot be narrowed by bwrap alone -> caller should use `container`.
            if all(_is_loopback(h) for h in self.spec.network_allowlist):
                cmd += ["--unshare-net"]
            # else: leave host net shared (documented limitation; see describe()).
        for name in self.spec.env_allowlist:
            if name == "*":
                continue
            val = os.environ.get(name)
            if val is not None:
                cmd += ["--setenv", name, val]
        cmd += ["--setenv", "HOME", _SCRATCH_IN_SANDBOX,
                "--setenv", "TMPDIR", _SCRATCH_IN_SANDBOX]
        cmd += [self.host_python, "-c", self.runner, _CANDIDATE_IN_SANDBOX, *map(str, argv)]
        return cmd

    def is_available(self) -> bool:
        """Functional self-test: actually create the namespaces and run
        ``/bin/true``. Returns False on a host that forbids unprivileged userns
        (the harness CI sandbox, locked-down kernels) so build_sandbox fails
        closed instead of running unconfined."""
        if not (self.BWRAP and Path(self.BWRAP).exists()):
            return False
        probe = [self.BWRAP, "--unshare-user", "--unshare-net",
                 "--ro-bind", "/usr", "/usr", "--ro-bind-try", "/lib", "/lib",
                 "--ro-bind-try", "/lib64", "/lib64", "--ro-bind-try", "/bin", "/bin",
                 "--proc", "/proc", "--dev", "/dev", "--die-with-parent", "/bin/true"]
        try:
            return subprocess.run(probe, capture_output=True, timeout=20).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def describe(self) -> str:
        net = {"disabled": "unshare-net", "allowlist": "loopback-only" if all(
            _is_loopback(h) for h in self.spec.network_allowlist) else "host-shared(!)",
            "unrestricted": "host-shared"}.get(self.spec.network, self.spec.network)
        return f"bubblewrap (ro-runtime, tmpfs scratch, net={net})"

    def run(self, candidate: Path, argv: Sequence[str]) -> SandboxResult:
        rc, out, err, timed_out, trunc, spawn = _run_capped(
            self.build_argv(candidate, argv), env=dict(os.environ),
            timeout=self.spec.timeout_seconds,
            out_cap=self.spec.stdout_max_bytes, err_cap=self.spec.stderr_max_bytes,
            preexec_fn=_rlimit_preexec(self.spec), start_new_session=True)
        return SandboxResult(rc, out, err, timed_out=timed_out, spawn_error=spawn, truncated=trunc)


# ------------------------------ container backend ---------------------------- #
def _discover_docker():
    """Locate the docker CLI + rootless socket without assuming the launcher's
    env was set up. Honors DOCKER_HOST/PATH if present, else falls back to the
    rootless defaults (~/bin/docker, $XDG_RUNTIME_DIR/docker.sock)."""
    cmd = shutil.which("docker")
    if not cmd:
        for cand in (Path.home() / "bin" / "docker", Path("/usr/bin/docker"),
                     Path("/usr/local/bin/docker")):
            if cand.exists():
                cmd = str(cand)
                break
    host = os.environ.get("DOCKER_HOST")
    if not host:
        runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
        sock = Path(runtime) / "docker.sock"
        if sock.exists():
            host = f"unix://{sock}"
    return cmd, host


def _docker_env(host: Optional[str]) -> dict:
    env = dict(os.environ)
    if host:
        env["DOCKER_HOST"] = host
    env["PATH"] = f"{Path.home() / 'bin'}{os.pathsep}{env.get('PATH', '')}"
    return env


def _is_loopback(host: str) -> bool:
    h = (host or "").split(":")[0].strip().lower()
    return h in ("127.0.0.1", "localhost", "::1", "0.0.0.0")


class ContainerBackend(SandboxBackend):
    """Rootless-Docker sandbox -- the secure default for generated candidates.

    Each candidate runs in a throwaway ``docker run`` container with a read-only
    root, a writable tmpfs scratch, dropped capabilities, no new privileges,
    pids/memory limits, a CPU-time ``--ulimit cpu`` (the policy's cpu_seconds), a
    wall-clock timeout, only allowlisted env (Docker starts from the image's env,
    never the host's -- so host secrets cannot leak), the candidate bind-mounted
    read-only, and NO published ports. Network is ``--network none`` (disabled)
    or a DEDICATED, per-sandbox ``--internal`` network (allowlist) whose only
    members are the candidate and the targets the operator attaches via
    :meth:`attach_target`; it has no route off the host and is removed on
    :meth:`close`."""

    name = "container"
    _SIGKILL_RC, _SIGXCPU_RC = 137, 152      # docker exit = 128 + signal number

    def __init__(self, spec: SandboxSpec, runner: str, image: str,
                 docker_cmd: Optional[str], docker_host: Optional[str]):
        super().__init__(spec, runner)
        self.image = image
        self.docker_cmd = docker_cmd
        self.docker_host = docker_host
        self._env = _docker_env(docker_host)
        self._net_name: Optional[str] = None     # this sandbox's dedicated --internal network

    # -- availability: image present (which also proves the daemon is reachable) --
    def is_available(self) -> bool:
        if not self.docker_cmd:
            return False
        try:
            r = subprocess.run([self.docker_cmd, "image", "inspect", self.image],
                               env=self._env, capture_output=True, timeout=30)
            return r.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    # ------------------------------- network ------------------------------- #
    def _resolve_network(self) -> str:
        if self.spec.network == "disabled":
            return "none"
        if self.spec.network == "allowlist":
            return self._ensure_dedicated_network()
        # unrestricted is trusted-only and would expose external egress; the
        # secure container backend refuses it rather than open the network.
        raise SandboxError(
            f"container backend refuses network mode {self.spec.network!r} "
            f"(would allow non-local egress); use the bubblewrap/local trusted path")

    def _ensure_dedicated_network(self) -> str:
        """Create (once) this sandbox's own ``--internal`` network. Dedicated --
        not shared -- so the only reachable hosts are the candidate and whatever
        :meth:`attach_target` adds; nothing else, no external route."""
        if self._net_name:
            return self._net_name
        net = f"{SANDBOX_NETWORK_PREFIX}{uuid.uuid4().hex[:12]}"
        r = subprocess.run([self.docker_cmd, "network", "create", "--internal", net],
                           env=self._env, capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            raise SandboxError(f"could not create dedicated internal sandbox network "
                               f"{net!r}: {r.stderr.strip()}")
        self._net_name = net
        return net

    def _allowlist_hosts(self) -> set:
        """The non-loopback host parts of ``network_allowlist`` -- the container
        names/aliases a candidate is permitted to reach. Loopback entries
        (127.0.0.1/localhost/::1) are no-ops: a candidate's own loopback needs no
        bridging, and the rootless daemon disables host-loopback egress anyway."""
        hosts = set()
        for entry in self.spec.network_allowlist:
            h = (entry or "").split(":")[0].strip()      # host[:port] -> host
            if h and not _is_loopback(h):
                hosts.add(h)
        return hosts

    def attach_target(self, container: str, alias: Optional[str] = None) -> None:
        """Place an allowlisted target onto THIS sandbox's dedicated internal
        network so candidates can reach it -- and only it.

        ENFORCES the policy: the target's reachable name (``alias`` if given, else
        the container name) MUST appear in ``network_allowlist``, otherwise it is
        rejected -- ``attach_target`` can never widen the allowlist. The candidate
        has no route anywhere else (the network is ``--internal`` and nothing else
        is attached). This is what makes ``network_allowlist`` enforced, not
        advisory."""
        reachable = alias or container
        allowed = self._allowlist_hosts()
        if reachable not in allowed:
            raise SandboxError(
                f"refusing to attach {reachable!r}: not in network_allowlist {sorted(allowed)} "
                f"-- attach_target cannot widen the policy")
        net = self._ensure_dedicated_network()
        cmd = [self.docker_cmd, "network", "connect"]
        if alias and alias != container:
            cmd += ["--alias", alias]
        cmd += [net, container]
        r = subprocess.run(cmd, env=self._env, capture_output=True, text=True, timeout=30)
        stderr = r.stderr or ""
        if r.returncode != 0 and "already exists" not in stderr and "already attached" not in stderr:
            raise SandboxError(f"could not attach target {container!r} to {net}: {stderr.strip()}")

    def provision(self) -> int:
        """Production wiring (called by py_executor.main / the launcher, NOT just
        tests): for an ``allowlist`` policy, attach each allowlisted *container
        target* to this sandbox's dedicated internal network so api-probe
        candidates can actually reach it -- and only it. Non-loopback
        ``network_allowlist`` entries name the target container/alias (the
        operator's local-only, inter-container model). A named target that is not
        a running container is warned-and-skipped: the candidate's probe simply
        fails to connect (a domain outcome), it is not a sandbox failure. Returns
        the number of targets attached."""
        if self.spec.network != "allowlist":
            return 0
        self._ensure_dedicated_network()
        attached = 0
        for host in sorted(self._allowlist_hosts()):
            if not self._container_exists(host):
                print(f"sandbox: allowlist target {host!r} is not a running container -- "
                      f"candidates probing it will fail to connect (nothing attached)")
                continue
            self.attach_target(host)          # validated against the allowlist
            attached += 1
        return attached

    def _container_exists(self, name: str) -> bool:
        try:
            r = subprocess.run([self.docker_cmd, "container", "inspect", name],
                               env=self._env, capture_output=True, timeout=15)
            return r.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    # ------------------------------- run ----------------------------------- #
    def build_argv(self, candidate: Path, argv: Sequence[str], *, name: str, network: str) -> list:
        spec = self.spec
        scratch_bytes = max(spec.memory_bytes or 0, 64 * 1024 * 1024)
        # NB: no `--rm` -- the container must survive its own exit just long
        # enough for run() to `docker inspect` .State.OOMKilled (the only way to
        # tell a CPU-time kill from a memory kill; both surface as exit 137).
        # run()'s finally always removes it.
        cmd = [self.docker_cmd, "run", "--name", name,
               "--network", network,
               "--read-only",
               "--cap-drop", "ALL",
               "--security-opt", "no-new-privileges",
               "--pids-limit", str(int(spec.max_processes or 64)),
               "--tmpfs", f"{_SCRATCH_IN_SANDBOX}:rw,size={scratch_bytes},mode=1777",
               "--tmpfs", f"/tmp:rw,size={scratch_bytes},mode=1777",
               "--workdir", _SCRATCH_IN_SANDBOX,
               "--env", f"HOME={_SCRATCH_IN_SANDBOX}",
               "--env", f"TMPDIR={_SCRATCH_IN_SANDBOX}"]
        if spec.memory_bytes:
            cmd += ["--memory", str(int(spec.memory_bytes)),
                    "--memory-swap", str(int(spec.memory_bytes))]   # ==memory -> no swap headroom
        if spec.cpu_seconds:
            # Enforce the policy's CPU-time budget. The runtime escalates the
            # ulimit kill to SIGKILL (exit 137), so run() distinguishes it from a
            # memory OOM (also 137) via `.State.OOMKilled` and maps it to TIMEOUT.
            cmd += ["--ulimit", f"cpu={int(spec.cpu_seconds)}:{int(spec.cpu_seconds)}"]
        # Docker does NOT inherit the host env; pass only allowlisted names that
        # exist (never '*': a secure profile's validator forbids it, and we will
        # not expand it here even for a trusted one running on this backend).
        for n in spec.env_allowlist:
            if n in ("*", "HOME", "TMPDIR", "PATH"):
                continue
            val = os.environ.get(n)
            if val is not None:
                cmd += ["--env", f"{n}={val}"]
        cmd += ["--volume", f"{candidate.resolve()}:{_CANDIDATE_IN_SANDBOX}:ro",
                self.image,
                spec.interpreter, "-c", self.runner, _CANDIDATE_IN_SANDBOX, *map(str, argv)]
        return cmd

    def run(self, candidate: Path, argv: Sequence[str]) -> SandboxResult:
        name = f"bundle-sbx-{uuid.uuid4().hex[:12]}"
        try:
            network = self._resolve_network()
        except SandboxError as exc:
            return SandboxResult(None, "", "", spawn_error=str(exc))
        cmd = self.build_argv(candidate, argv, name=name, network=network)

        def kill_container(_proc):
            # the wall timeout kills the docker CLIENT; the container keeps
            # running in the daemon -> force-remove it so nothing is left behind.
            self._rm(name)

        started = time.monotonic()
        try:
            rc, out, err, timed_out, trunc, spawn = _run_capped(
                cmd, env=self._env, timeout=self.spec.timeout_seconds,
                out_cap=self.spec.stdout_max_bytes, err_cap=self.spec.stderr_max_bytes,
                on_timeout=kill_container)
            elapsed = time.monotonic() - started
            # A non-wall signal-kill (137/152): tell a CPU-time exhaustion (the
            # cpu_seconds ulimit -> TIMEOUT, a *time* limit like the wall clock)
            # apart from a memory OOM kill or a crash, which leave a no-verdict
            # BROKEN. `.State.OOMKilled` is the discriminator.
            if not timed_out and spawn is None and rc in (self._SIGKILL_RC, self._SIGXCPU_RC):
                if self._is_cpu_time_kill(name, elapsed):
                    timed_out = True
            return SandboxResult(rc, out, err, timed_out=timed_out, spawn_error=spawn, truncated=trunc)
        finally:
            self._rm(name)     # guaranteed teardown (action 7)

    def _rm(self, name: str) -> None:
        subprocess.run([self.docker_cmd, "rm", "-f", name],
                       env=self._env, capture_output=True, timeout=30)

    def _is_cpu_time_kill(self, name: str, elapsed: float) -> bool:
        if not self.spec.cpu_seconds:
            return False
        if self._oom_killed(name):                      # memory kill -> BROKEN, not TIMEOUT
            return False
        return elapsed >= self.spec.cpu_seconds * 0.5   # reached ~the CPU budget -> a time limit

    def _oom_killed(self, name: str) -> bool:
        try:
            r = subprocess.run([self.docker_cmd, "inspect", "-f", "{{.State.OOMKilled}}", name],
                               env=self._env, capture_output=True, text=True, timeout=15)
            return r.returncode == 0 and r.stdout.strip() == "true"
        except (OSError, subprocess.SubprocessError):
            return False

    def describe(self) -> str:
        net = {"disabled": "none",
               "allowlist": f"internal:{self._net_name or '(dedicated, on first use)'}"}.get(
                   self.spec.network, self.spec.network)
        return (f"container (rootless docker, image={self.image}, read-only root, "
                f"tmpfs scratch, pids<={self.spec.max_processes}, mem={self.spec.memory_bytes}, "
                f"cpu_s={self.spec.cpu_seconds}, net={net}, no published ports)")

    def close(self) -> None:
        """Remove this sandbox's dedicated internal network (action 7) --
        disconnecting any still-attached operator targets first so the removal
        cannot be blocked by active endpoints. Idempotent / best-effort."""
        if not self._net_name or not self.docker_cmd:
            return
        net, self._net_name = self._net_name, None
        insp = subprocess.run(
            [self.docker_cmd, "network", "inspect", "-f",
             "{{range .Containers}}{{.Name}} {{end}}", net],
            env=self._env, capture_output=True, text=True)
        if insp.returncode == 0:
            for cont in insp.stdout.split():
                subprocess.run([self.docker_cmd, "network", "disconnect", "-f", net, cont],
                               env=self._env, capture_output=True, timeout=30)
        subprocess.run([self.docker_cmd, "network", "rm", net],
                       env=self._env, capture_output=True, timeout=30)


def cleanup_sandbox_networks(docker_cmd: Optional[str] = None,
                             docker_host: Optional[str] = None) -> int:
    """Defensive sweep: remove any leftover dedicated sandbox networks
    (``bundle-sbx-net-*``). Each :meth:`ContainerBackend.close` already removes
    its own; this catches anything a crash left behind. Returns the count
    removed."""
    cmd, host = _discover_docker()
    cmd = docker_cmd or cmd
    if not cmd:
        return 0
    env = _docker_env(docker_host or host)
    ls = subprocess.run([cmd, "network", "ls", "--filter", f"name={SANDBOX_NETWORK_PREFIX}",
                         "--format", "{{.Name}}"], env=env, capture_output=True, text=True)
    removed = 0
    for net in ls.stdout.split():
        insp = subprocess.run([cmd, "network", "inspect", "-f",
                               "{{range .Containers}}{{.Name}} {{end}}", net],
                              env=env, capture_output=True, text=True)
        for cont in (insp.stdout.split() if insp.returncode == 0 else []):
            subprocess.run([cmd, "network", "disconnect", "-f", net, cont],
                           env=env, capture_output=True)
        if subprocess.run([cmd, "network", "rm", net],
                          env=env, capture_output=True).returncode == 0:
            removed += 1
    return removed


# --------------------------------- factory ----------------------------------- #
def build_sandbox(policy: Optional[Mapping], *, runner: str, host_python: str,
                  image: Optional[str] = None) -> Optional[SandboxBackend]:
    """Select + construct the sandbox backend a policy demands.

    Returns:
      * ``None``  -- run the candidate UNSANDBOXED. Only for a *trusted* ``local``
                     policy (the ``trusted-local`` explicit opt-in) or no policy
                     at all (legacy handshake / pre-STEP-27 runs).
      * a backend -- otherwise.

    Raises :class:`SandboxUnavailable` when a secure policy names a backend whose
    self-test fails -- the launcher must NOT fall back to unsandboxed execution
    (fail closed, action 5)."""
    if not policy:
        return None
    spec = SandboxSpec.from_policy(policy)

    if spec.backend == "local":
        if spec.trusted:
            return None                       # trusted-local: explicit unsandboxed opt-in
        return LocalBackend(spec, runner, host_python)

    if spec.backend == "container":
        cmd, host = _discover_docker()
        backend = ContainerBackend(spec, runner, image or DEFAULT_SANDBOX_IMAGE, cmd, host)
    elif spec.backend == "bubblewrap":
        backend = BubblewrapBackend(spec, runner, host_python)
    else:
        raise SandboxUnavailable(
            f"execution policy '{spec.profile}' names backend {spec.backend!r}, "
            f"which the Python Executor does not implement")

    if not backend.is_available():
        raise SandboxUnavailable(
            f"execution policy '{spec.profile}' requires the {spec.backend!r} sandbox backend, "
            f"but it is not usable on this host (functional self-test failed) -- refusing to run "
            f"generated candidates unsandboxed")
    return backend
