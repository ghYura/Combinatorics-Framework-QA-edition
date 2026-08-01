"""Direct candidate gRPC boundary (docs/32 finding F5).

The Reader targets `127.0.0.1`, but the Java receiver was constructed with
`NettyServerBuilder.forPort(port)` — which binds every interface. A loopback
*target* never constrained what the receiver *listened on*, so a plaintext,
unauthenticated code-ingestion socket could be reachable from the network while
the documentation described the channel as local.

These tests check the configuration gate and, where a JVM and the built Executor
classes are available, the **actual listening socket** — because the interesting
failure is a bind that succeeds on the wrong interface, which no amount of
config validation would reveal.
"""
from __future__ import annotations

import shutil
import socket
import subprocess
import textwrap
from pathlib import Path

import pytest

from bundle import architecture as arch
from bundle.config import BundleConfig, ConfigError

REPO_ROOT = arch.REPO_ROOT
_EXECUTOR_CLASSES = REPO_ROOT / "Executor_trunk" / "target" / "classes"
_RECEIVER_CLASS = _EXECUTOR_CLASSES / "com/company/GrpcCandidateReceiver.class"


def _cfg(**kw) -> BundleConfig:
    import dataclasses
    return dataclasses.replace(BundleConfig(), **kw)


# ------------------------------------------------------ configuration gate ---
def test_the_default_bind_host_is_loopback() -> None:
    assert BundleConfig().grpc_bind_host == "127.0.0.1"
    assert _cfg().validate_grpc_bind_host() == "127.0.0.1"


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", "127.0.0.53"])
def test_loopback_addresses_are_accepted(host: str) -> None:
    assert _cfg(grpc_bind_host=host).validate_grpc_bind_host() == host


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "*"])
def test_wildcard_binds_are_refused(host: str) -> None:
    with pytest.raises(ConfigError, match="wildcard"):
        _cfg(grpc_bind_host=host).validate_grpc_bind_host()


@pytest.mark.parametrize("host", ["10.0.0.5", "192.168.1.10", "8.8.8.8", "172.16.0.1"])
def test_routable_addresses_are_refused(host: str) -> None:
    with pytest.raises(ConfigError, match="not a loopback address"):
        _cfg(grpc_bind_host=host).validate_grpc_bind_host()


def test_an_empty_bind_host_is_refused_because_it_means_the_wildcard() -> None:
    with pytest.raises(ConfigError, match="empty"):
        _cfg(grpc_bind_host="").validate_grpc_bind_host()


def test_preflight_validates_the_bind_host_before_any_stage_runs() -> None:
    from types import SimpleNamespace
    from bundle.errors import PreflightError
    from bundle.stages import preflight
    args = SimpleNamespace(lang="java", mode="verdict", legacy_handoff=False,
                           spec_dir=str(REPO_ROOT), main_port=5433, results_port=5432)
    with pytest.raises((ConfigError, PreflightError)):
        preflight(args, _cfg(candidate_sink="grpc", grpc_bind_host="0.0.0.0"))


def test_the_launcher_passes_an_explicit_bind_host_to_the_receiver() -> None:
    """A validated config that never reaches the JVM would be decoration."""
    source = (REPO_ROOT / "generator_trunk/bundle/stages.py").read_text(encoding="utf-8")
    assert '"-grpcBindHost", str(cfg.grpc_bind_host),' in source


# ------------------------------------------------- the real listening socket --
_JAVA_PROBE = textwrap.dedent('''
    import com.company.GrpcCandidateReceiver;
    import java.io.IOException;

    public class BindProbe {
        public static void main(String[] args) throws Exception {
            String host = args[0];
            int port = Integer.parseInt(args[1]);
            try {
                GrpcCandidateReceiver r = GrpcCandidateReceiver.start(host, port);
                System.out.println("BOUND");
                System.out.flush();
                Thread.sleep(Long.parseLong(args[2]));
                r.shutdown();
            } catch (IOException e) {
                System.out.println("REFUSED: " + e.getMessage());
            }
        }
    }
''').strip()

_JAVA_AVAILABLE = shutil.which("java") is not None and _RECEIVER_CLASS.is_file()
_needs_java = pytest.mark.skipif(
    not _JAVA_AVAILABLE,
    reason="EXPECTED_OPTIONAL: JDK and Executor_trunk/target/classes needed for a real bind probe")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _classpath() -> str:
    cp = [str(_EXECUTOR_CLASSES)]
    lib = REPO_ROOT / "Executor_trunk" / "target"
    jars = sorted(lib.glob("*-jar-with-dependencies.jar")) or sorted(lib.glob("*.jar"))
    cp.extend(str(j) for j in jars)
    return ":".join(cp)


def _compile_probe(tmp_path: Path) -> "str | None":
    src = tmp_path / "BindProbe.java"
    src.write_text(_JAVA_PROBE, encoding="utf-8")
    javac = shutil.which("javac")
    if javac is None:
        return None
    proc = subprocess.run([javac, "-cp", _classpath(), "-d", str(tmp_path), str(src)],
                          capture_output=True, text=True, timeout=180)
    if proc.returncode != 0:
        return None
    return f"{tmp_path}:{_classpath()}"


@_needs_java
def test_the_receiver_refuses_a_wildcard_bind_in_the_jvm(tmp_path: Path) -> None:
    """The Java side must fail closed on its own, not only because Python
    validated first — a standalone MainWatch invocation bypasses the launcher."""
    cp = _compile_probe(tmp_path)
    if cp is None:
        pytest.skip("EXPECTED_OPTIONAL: javac unavailable or probe did not compile")
    proc = subprocess.run(["java", "-cp", cp, "BindProbe", "0.0.0.0", str(_free_port()), "50"],
                          capture_output=True, text=True, timeout=180)
    assert "REFUSED" in proc.stdout, proc.stdout + proc.stderr
    assert "loopback" in proc.stdout


@_needs_java
def test_the_listening_socket_is_not_reachable_off_loopback(tmp_path: Path) -> None:
    """The check that actually matters: with the receiver up on 127.0.0.1, a
    connection to this host's routable address must NOT succeed."""
    cp = _compile_probe(tmp_path)
    if cp is None:
        pytest.skip("EXPECTED_OPTIONAL: javac unavailable or probe did not compile")
    port = _free_port()
    proc = subprocess.Popen(["java", "-cp", cp, "BindProbe", "127.0.0.1", str(port), "8000"],
                            stdout=subprocess.PIPE, text=True)
    try:
        assert (proc.stdout.readline() or "").strip() == "BOUND"

        with socket.socket() as s:                       # loopback: reachable
            s.settimeout(5)
            assert s.connect_ex(("127.0.0.1", port)) == 0

        routable = _routable_address()
        if routable is None:
            pytest.skip("EXPECTED_OPTIONAL: host has no non-loopback address to probe")
        with socket.socket() as s:                       # off-loopback: must NOT be
            s.settimeout(5)
            assert s.connect_ex((routable, port)) != 0, (
                f"the unauthenticated candidate receiver accepted a connection on {routable}:{port}")
    finally:
        proc.kill()
        proc.wait(timeout=30)


def _routable_address() -> "str | None":
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))                   # no packet is sent
            address = s.getsockname()[0]
        return None if address.startswith("127.") else address
    except OSError:
        return None


# ----------------------------------------------------------- documentation ---
def test_documentation_does_not_promise_a_secure_remote_channel() -> None:
    for name in ("docs/10_SECURITY_AND_SANDBOXING.md", "docs/09_READER_EXECUTOR_AND_RESULTS.md"):
        text = (REPO_ROOT / name).read_text(encoding="utf-8").lower()
        assert "plaintext" in text and "unauthenticated" in text, name
