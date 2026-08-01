"""Run Face 1 new through multiple isolated Bundle and NiceGUI instances.

Isolation is explicit: every lane receives a unique app port, database name,
spec directory, scratch root, runs root, run ID and log. Browser candidates use
unique profiles and driver ports (see ``page_object.browser_session``). Sharing
the immutable source tree is therefore safer and much cheaper than copying the
whole repository to sibling directories; full clones are not required.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from typing import Callable, Iterable

from bundle.config import resolve_config

from .actions import ALL_FLOW_NAMES, FLOW_NAMES, NESTED_FLOW_NAMES
from .page_object import wait_until_reachable
from .spec import cardinality, partition_flows, write_spec


ROOT = Path(__file__).resolve().parents[2]

SMOKE_FLOWS = (
    "grid_data_sync",
    "runtime_essentials",
    "modal_guardrails",
    "download_import",
)


def server_environment() -> dict[str, str]:
    """Return an app environment independent of a parent pytest process.

    NiceGUI treats the mere presence of ``PYTEST_CURRENT_TEST`` as its own
    screen-test mode and then requires a plugin-owned port. Managed Face 1
    servers are normal subprocesses, so neither marker belongs in their
    environment.
    """
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    env.pop("PYTEST_CURRENT_TEST", None)
    env.pop("NICEGUI_SCREEN_TEST_PORT", None)
    return env


def reserve_free_port(host: str = "127.0.0.1") -> int:
    """Ask the kernel for an unused port; launch follows immediately."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


@dataclass
class ManagedServer:
    port: int
    process: subprocess.Popen[str]
    log_path: Path
    log_handle: object

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def stop(self) -> None:
        if self.process.poll() is None:
            try:
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                self.process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
                self.process.wait(timeout=5)
        try:
            self.log_handle.close()
        except Exception:
            pass


class ServerPool:
    def __init__(self, artifact_root: Path, count: int) -> None:
        if count < 1:
            raise ValueError("server count must be >= 1")
        self.artifact_root = Path(artifact_root)
        self.count = count
        self.servers: list[ManagedServer] = []

    def start(self) -> "ServerPool":
        logs = self.artifact_root / "servers"
        logs.mkdir(parents=True, exist_ok=True)
        try:
            for index in range(self.count):
                last_error: Exception | None = None
                for _attempt in range(5):
                    port = reserve_free_port()
                    log_path = logs / f"face1-{index}-{port}.log"
                    handle = log_path.open("w", encoding="utf-8")
                    process = subprocess.Popen(
                        [sys.executable, "-m", "face1_new.app", "--no-browser", "--port", str(port)],
                        cwd=ROOT,
                        env=server_environment(),
                        stdout=handle,
                        stderr=subprocess.STDOUT,
                        text=True,
                        start_new_session=True,
                    )
                    server = ManagedServer(port, process, log_path, handle)
                    try:
                        wait_until_reachable(server.url, timeout=25)
                    except Exception as exc:
                        last_error = exc
                        server.stop()
                        continue
                    self.servers.append(server)
                    break
                else:
                    raise RuntimeError(f"could not launch Face 1 lane {index}: {last_error}")
            return self
        except Exception:
            self.stop()
            raise

    def stop(self) -> None:
        for server in reversed(self.servers):
            server.stop()
        self.servers.clear()

    def __enter__(self) -> "ServerPool":
        return self.start()

    def __exit__(self, *_exc: object) -> None:
        self.stop()

    @property
    def urls(self) -> tuple[str, ...]:
        return tuple(server.url for server in self.servers)


def _connect(endpoint: tuple[str, int, str, str], database: str):
    import pg8000.dbapi

    host, port, user, password = endpoint
    return pg8000.dbapi.connect(host=host, port=port, user=user, password=password, database=database)


class DatabaseSet:
    """Unique short-lived database on every configured PostgreSQL endpoint."""

    def __init__(self, name: str) -> None:
        cfg, _ = resolve_config(cli={})
        self.name = name
        self.endpoints = tuple(dict.fromkeys((
            (str(cfg.main_db_host), int(cfg.main_db_port), str(cfg.main_db_user), str(cfg.main_db_password)),
            (str(cfg.results_db_host), int(cfg.results_db_port), str(cfg.results_db_user), str(cfg.results_db_password)),
        )))
        if any(not endpoint[3] for endpoint in self.endpoints):
            raise RuntimeError(
                "Bundle DB credentials are not configured; set BUNDLE_MAIN_DB_PASSWORD and "
                "BUNDLE_RESULTS_DB_PASSWORD in the server environment"
            )

    def create(self) -> "DatabaseSet":
        created: list[tuple[str, int, str, str]] = []
        try:
            for endpoint in self.endpoints:
                conn = _connect(endpoint, "postgres")
                conn.autocommit = True
                cursor = conn.cursor()
                cursor.execute(f'CREATE DATABASE "{self.name}";')
                cursor.close()
                conn.close()
                created.append(endpoint)
            return self
        except Exception:
            for endpoint in created:
                self._drop(endpoint)
            raise

    def _drop(self, endpoint: tuple[str, int, str, str]) -> None:
        try:
            conn = _connect(endpoint, "postgres")
            conn.autocommit = True
            cursor = conn.cursor()
            cursor.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname=%s AND pid<>pg_backend_pid();",
                (self.name,),
            )
            cursor.execute(f'DROP DATABASE IF EXISTS "{self.name}";')
            cursor.close()
            conn.close()
        except Exception:
            pass

    def drop(self) -> None:
        for endpoint in self.endpoints:
            self._drop(endpoint)

    def __enter__(self) -> "DatabaseSet":
        return self.create()

    def __exit__(self, *_exc: object) -> None:
        self.drop()


@dataclass(frozen=True)
class LaneResult:
    lane: int
    returncode: int
    state: str
    processed: int
    passed: int
    failed: int
    broken: int
    timeout: int
    infra_fail: int
    run_dir: Path
    log_path: Path

    @property
    def ok(self) -> bool:
        return (
            self.returncode == 0
            and self.state == "SUCCEEDED"
            and self.processed > 0
            and self.passed == self.processed
            and self.failed == self.broken == self.timeout == self.infra_fail == 0
        )


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _lane_command(
    lane: int,
    artifact_root: Path,
    db_name: str,
    run_id: str,
    urls: Iterable[str],
) -> tuple[list[str], Path, Path]:
    lane_root = artifact_root / f"lane-{lane}"
    spec_dir = lane_root / "spec"
    runs_root = lane_root / "runs"
    scratch_root = lane_root / "scratch"
    run_dir = runs_root / run_id
    log_path = lane_root / "bundle.log"
    cfg, _ = resolve_config(cli={})
    passthrough = (
        f"FACE1_E2E_ROOT={ROOT},"
        f"FACE1_E2E_URLS={';'.join(urls)},"
        f"FACE1_E2E_HEADLESS={os.environ.get('FACE1_E2E_HEADLESS', '1')}"
    )
    command = [
        sys.executable, str(ROOT / "bundle_run.py"), str(spec_dir),
        "--db", db_name,
        "--lang", "py",
        "--main-port", str(cfg.main_db_port),
        "--results-port", str(cfg.results_db_port),
        "--run-id", run_id,
        "--runs-root", str(runs_root),
        "--scratch-root", str(scratch_root),
        "--execution-policy-profile", "trusted-local",
        "--candidate-origin", "reviewed-checked-in",
        "--acknowledge-trusted-local", "reviewed checked-in scenario fragments in this repository",
        "--py-executor", str(ROOT / "face1_new" / "e2e" / "py_executor_e2e.py"),
        "--executor-timeout", "900",
        "--sandbox-candidate-env", passthrough,
        "--budget-final-candidates", "512",
        "--budget-mandatory-rows", "512",
        "--analyzer", "correct:max,checks:max,latency_ms:min",
        "--analysis-mode", "formal",
    ]
    return command, run_dir, log_path


def _run_lane(
    lane: int,
    artifact_root: Path,
    flows: tuple[str, ...],
    browsers: tuple[str, ...],
    viewports: tuple[str, ...],
    profiles: tuple[str, ...],
    urls: tuple[str, ...],
) -> LaneResult:
    token = uuid.uuid4().hex[:10]
    db_name = f"face1_e2e_{token}_{lane}"
    run_id = f"face1-e2e-{token}-{lane}"
    lane_root = artifact_root / f"lane-{lane}"
    write_spec(
        lane_root / "spec",
        flows=flows,
        browsers=browsers,
        viewports=viewports,
        data_profiles=profiles,
        title=f"Face 1 dogfood lane {lane}",
    )
    command, run_dir, log_path = _lane_command(lane, artifact_root, db_name, run_id, urls)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with DatabaseSet(db_name):
        with log_path.open("w", encoding="utf-8") as log:
            completed = subprocess.run(
                command,
                cwd=ROOT,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
    state = _read_json(run_dir / "state.json")
    summary = _read_json(run_dir / "executor-summary.json")
    outcomes = summary.get("outcomes") or summary
    return LaneResult(
        lane=lane,
        returncode=completed.returncode,
        state=str(state.get("status") or "MISSING"),
        processed=int(summary.get("processed", outcomes.get("processed", 0)) or 0),
        passed=int(summary.get("pass", outcomes.get("pass", 0)) or 0),
        failed=int(summary.get("fail", outcomes.get("domain_fail", outcomes.get("fail", 0))) or 0),
        broken=int(summary.get("broken", outcomes.get("broken", 0)) or 0),
        timeout=int(summary.get("timeout", outcomes.get("timeout", 0)) or 0),
        infra_fail=int(summary.get("infra_fail", outcomes.get("infra_fail", 0)) or 0),
        run_dir=run_dir,
        log_path=log_path,
    )


def run_dogfood(
    *,
    artifact_root: Path,
    instances: int,
    flows: tuple[str, ...],
    browsers: tuple[str, ...],
    viewports: tuple[str, ...],
    profiles: tuple[str, ...],
    on_lane_complete: Callable[[LaneResult], None] | None = None,
) -> list[LaneResult]:
    partitions = partition_flows(flows, instances)
    with ServerPool(artifact_root, len(partitions)) as servers:
        with ThreadPoolExecutor(max_workers=len(partitions), thread_name_prefix="face1-bundle") as executor:
            futures = {
                executor.submit(
                    _run_lane, lane, artifact_root, partition, browsers, viewports, profiles, servers.urls
                ): lane
                for lane, partition in enumerate(partitions)
            }
            results = []
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                if on_lane_complete is not None:
                    on_lane_complete(result)
    return sorted(results, key=lambda item: item.lane)


def _csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dogfood Face 1 new through parallel Bundle instances")
    parser.add_argument("--instances", type=int, default=2)
    parser.add_argument("--suite", choices=("smoke", "exhaustive", "nested"), default="smoke")
    parser.add_argument("--flows", default="", help="comma-separated flow override for targeted runs")
    parser.add_argument("--browsers", default="chromium")
    parser.add_argument("--viewports", default="", help="comma list; suite default when omitted")
    parser.add_argument("--profiles", default="", help="compact,expanded; suite default when omitted")
    parser.add_argument("--artifact-root", default="")
    parser.add_argument("--keep-artifacts", action="store_true")
    parser.add_argument("--headful", action="store_true")
    args = parser.parse_args(argv)

    if args.flows:
        flows = _csv(args.flows)
        unknown_flows = sorted(set(flows) - set(ALL_FLOW_NAMES))
        if unknown_flows:
            parser.error(f"unsupported flow(s): {unknown_flows}")
    elif args.suite == "smoke":
        flows = SMOKE_FLOWS
    elif args.suite == "nested":
        flows = NESTED_FLOW_NAMES
    else:
        flows = FLOW_NAMES
    browsers = _csv(args.browsers)
    compact_defaults = args.suite in {"smoke", "nested"}
    viewports = _csv(args.viewports) or (("desktop",) if compact_defaults else ("desktop", "compact"))
    profiles = _csv(args.profiles) or (("compact",) if compact_defaults else ("compact", "expanded"))
    unknown_browsers = sorted(set(browsers) - {"chromium", "firefox"})
    if unknown_browsers:
        parser.error(f"unsupported browser(s): {unknown_browsers}")
    if "firefox" in browsers and not (os.environ.get("GECKODRIVER") or shutil.which("geckodriver")):
        parser.error("Firefox requested but geckodriver is unavailable; set GECKODRIVER or install it")
    os.environ["FACE1_E2E_HEADLESS"] = "0" if args.headful else "1"

    owned_root = not args.artifact_root
    artifact_root = Path(args.artifact_root) if args.artifact_root else Path(
        tempfile.mkdtemp(prefix="face1-new-dogfood-")
    )
    artifact_root.mkdir(parents=True, exist_ok=True)
    total = cardinality(flows, browsers, viewports, profiles)
    print(
        f"Face 1 dogfood: {total} candidates · {min(args.instances, len(flows))} Bundle/NiceGUI lanes "
        f"· artifacts {artifact_root}"
    )
    try:
        def report(result: LaneResult) -> None:
            print(
                f"lane {result.lane}: state={result.state} exit={result.returncode} "
                f"processed={result.processed} pass={result.passed} fail={result.failed} "
                f"broken={result.broken} timeout={result.timeout} infra={result.infra_fail} "
                f"log={result.log_path}",
                flush=True,
            )

        results = run_dogfood(
            artifact_root=artifact_root,
            instances=args.instances,
            flows=tuple(flows),
            browsers=browsers,
            viewports=tuple(viewports),
            profiles=tuple(profiles),
            on_lane_complete=report,
        )
        okay = bool(results) and all(result.ok for result in results) and sum(r.processed for r in results) == total
        if not okay:
            print(f"Face 1 dogfood FAILED; artifacts retained at {artifact_root}", file=sys.stderr)
            return 1
        print(f"Face 1 dogfood PASSED: {total}/{total} candidates")
        return 0
    finally:
        if owned_root and not args.keep_artifacts and 'results' in locals() and all(r.ok for r in results):
            shutil.rmtree(artifact_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
