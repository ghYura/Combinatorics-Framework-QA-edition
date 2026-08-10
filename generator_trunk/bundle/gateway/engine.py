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

from __future__ import annotations

import importlib.util
import json
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .. import inventory
from ..config import ConfigError, resolve_config
from ..database import psql, sql_identifier
from ..jsonio import write_json_atomic
from ..stages import CORE_JAR, JAVA_EXECUTOR_JAR, JAVA_JARS_DIR, PY_EXECUTOR, READER_JAR
from .registry import JobRegistry, RegistryError, now_iso, slug_tenant


class JobState:
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

    TERMINAL = {SUCCEEDED, FAILED, CANCELLED}


class GatewayError(Exception):
    def __init__(self, code: str, message: str, *, http_status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


@dataclass(frozen=True)
class GatewayLimits:
    max_concurrent_jobs: int = 1
    max_worker_units: int = 4
    max_executor_pool: int = 4
    max_iterations: int = 5
    default_timeout_seconds: float = 24 * 3600


@dataclass(frozen=True)
class GatewayConfig:
    gen_dir: Path
    runs_root: Path
    limits: GatewayLimits = GatewayLimits()
    transport: str = "http-json"
    retention_seconds: float = 0.0


_ID_RE = re.compile(r"[^A-Za-z0-9_.-]")
_DB_RE = re.compile(r"[^a-z0-9_]")
_KV_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)")
_ITER_DIR_RE = re.compile(r"-it(\d+)$")

STAGE_ORDER = ["gen", "core", "seed_bias", "sieve", "reader", "executor", "analyzer"]

_SUPPORTED_LANGUAGES = {"java", "python", "py"}
_SUPPORTED_SINKS = {"loose-files", "sharded", "grpc"}
_SUPPORTED_POLICIES = {"trusted-local", "generated-default", "networked-api-probe"}

_SAFE_CONFIG_OVERRIDES = {
    "analyzer_goals": "--analyzer",
    "analysis_mode": "--analysis-mode",
    "executor_compiler": "--executor-compiler",
    "exploration_floor": "--exploration-floor",
    "min_winner_support": "--min-winner-support",
    "executor_tolerate_outcomes": "--executor-tolerate-outcomes",
    "budget_mandatory_rows": "--budget-mandatory-rows",
    "budget_final_candidates": "--budget-final-candidates",
    "budget_disk_bytes": "--budget-disk-bytes",
    "budget_inodes": "--budget-inodes",
    "budget_wall_time_seconds": "--budget-wall-time-seconds",
    "budget_external_requests": "--budget-requests",
    "budget_monetary_cost": "--budget-monetary-cost",
    "budget_warn_fraction": "--budget-warn-fraction",
    "cost_per_candidate": "--cost-per-candidate",
}

# candidate_sink=grpc is an internal execution option (§3 of the gateway handoff: "the client
# never sees them"). grpc_host/grpc_port are deliberately NOT in _SAFE_CONFIG_OVERRIDES: letting
# a tenant pick the host would let it redirect the gateway's own Reader->Executor connection to
# an arbitrary network address (SSRF-ish). The gateway allocates a fresh loopback port per job
# itself (see _allocate_free_port) so concurrent grpc-sink jobs never collide either.

_DENIED_OVERRIDE_FRAGMENTS = (
    "main_db_", "results_db_", "scratch_root", "_jar", "_props",
    "py_executor", "java_jars_dir", "sandbox_candidate_env",
    "sandbox_network_allowlist", "password", "token", "secret", "credential",
)


def _allocate_free_port(host: str = "127.0.0.1") -> int:
    """Bind-probe a free loopback port for a job's internal candidate_sink=grpc hop.

    Same idiom as this package's own test_grpc_capabilities_smoke: bind to port 0, read back
    the OS-assigned port, release it immediately. There is an inherent TOCTOU race between
    releasing the probe socket and the Java Executor binding it, but each job gets its own
    freshly probed port rather than everyone sharing one hardcoded default, so two concurrent
    grpc-sink jobs no longer collide by construction.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, 0))
        return sock.getsockname()[1]
    finally:
        sock.close()


def _slug_id(s: str, default: str) -> str:
    s = _ID_RE.sub("-", (s or "").strip()).strip("-.") or default
    if not re.match(r"^[A-Za-z0-9]", s):
        s = "r-" + s
    return s[:120]


def _slug_db(s: str, default: str) -> str:
    s = _DB_RE.sub("_", (s or "").strip().lower()).strip("_") or default
    if s[0].isdigit():
        s = "d_" + s
    return s[:48]


def _read_json(p: Path) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _stage_counts(run_dir: Path, stage: str) -> dict:
    data = _read_json(run_dir / "stages" / f"{stage}.json")
    out: dict[str, Any] = {}
    if isinstance(data, dict):
        for c in data.get("counts", []) or []:
            if isinstance(c, dict) and c.get("name") is not None:
                out[str(c["name"])] = c.get("actual")
        errs = data.get("errors") or []
        if errs:
            out["_errors"] = errs
    return out


def collect_progress(run_dir: Path) -> dict:
    state = _read_json(run_dir / "state.json") or {}
    stages_state = state.get("stages", {}) if isinstance(state, dict) else {}
    stages = {}
    for name in STAGE_ORDER:
        st = stages_state.get(name)
        if not st:
            continue
        stages[name] = {"status": st.get("status"), "counts": _stage_counts(run_dir, name)}
    return {"run_status": state.get("status"), "stages": stages}


def collect_results(run_dir: Path) -> dict:
    summ = _read_json(run_dir / "executor-summary.json") or {}
    prov = _read_json(run_dir / "provenance.json") or {}
    prog = collect_progress(run_dir)
    stages = prog.get("stages", {})

    def scount(stage: str, key: str):
        return (stages.get(stage, {}).get("counts", {}) or {}).get(key)

    goals = []
    for g in (prov.get("goals") or []):
        mode = str(g.get("mode", "")).upper()
        goals.append({"metric": g.get("key"), "dir": "min" if mode == "MINIMIZE" else "max"})

    front = []
    for c in (prov.get("candidates") or []):
        front.append({
            "id": c.get("candidate_id"),
            "source_ref": c.get("source_ref"),
            "objectives": c.get("objectives") or {},
            "outcome": c.get("outcome"),
            "reason": c.get("reason_non_dominated") or "",
            "dimensions": c.get("dimensions") or {},
        })

    points = []
    kv = run_dir / "metrics.kv"
    if kv.exists() and goals:
        gkeys = [g["metric"] for g in goals]
        try:
            for line in kv.read_text(encoding="utf-8", errors="replace").splitlines():
                toks = {m.group(1): float(m.group(2)) for m in _KV_RE.finditer(line)}
                pt = {k: toks[k] for k in gkeys if k in toks}
                if len(pt) == len(gkeys):
                    points.append({"objectives": pt})
        except Exception:
            points = []

    outcomes = summ.get("outcomes") or {}
    seed = run_dir / "bundle_seed.json"
    return {
        "real": True,
        "outcomes": outcomes,
        "processed": summ.get("processed", scount("executor", "processed")),
        "pass": summ.get("pass", scount("executor", "pass")),
        "fail": summ.get("fail", scount("executor", "fail")),
        "inserted": summ.get("inserted", scount("executor", "inserted")),
        "counts": {
            "mandatory": scount("core", "fw_final"),
            "post_sieve": scount("sieve", "post_sieve"),
            "candidates": scount("reader", "candidates"),
            "processed": summ.get("processed", scount("executor", "processed")),
            "inserted": summ.get("inserted", scount("executor", "inserted")),
        },
        "goals": goals,
        "front": front,
        "points": points,
        "provenance_ok": prov.get("provenance_ok"),
        "analysis_mode": prov.get("mode"),
        "seed_json": seed.read_text(encoding="utf-8") if seed.exists() else "",
    }


def _iteration_dirs(runs_root: Path, base_run_id: str) -> list[tuple[int, Path]]:
    out = []
    for p in runs_root.glob(f"{base_run_id}-it*"):
        m = _ITER_DIR_RE.search(p.name)
        if m and p.is_dir():
            out.append((int(m.group(1)), p))
    return sorted(out)


def _iterate_summary(runs_root: Path, base_run_id: str) -> dict | None:
    lineage = _read_json(runs_root / f"{base_run_id}-iterate.json")
    if not isinstance(lineage, dict):
        return None
    entries = lineage.get("iterations") or []
    return {
        "status": lineage.get("status"),
        "requested": lineage.get("iterations_requested"),
        "completed": len(entries),
        "candidates": [e.get("candidate_count") for e in entries],
        "front_sizes": [len(e.get("front_ids") or []) for e in entries],
        "plan_statuses": [e.get("plan_status") for e in entries],
    }


def _proc_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="ascii", errors="replace")
        state = raw.rsplit(")", 1)[1].split()[0]
        if state == "Z":
            return False
    except Exception:
        pass
    return True


def _proc_start_ticks(pid: int) -> int | None:
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="ascii", errors="replace")
        return int(raw.rsplit(")", 1)[1].split()[19])
    except Exception:
        return None


def _wait_for_exit(pid: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _proc_alive(pid):
            return True
        time.sleep(0.1)
    return not _proc_alive(pid)


def _parse_iso(ts: str | None) -> float | None:
    if not ts:
        return None
    try:
        return time.mktime(time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ"))
    except Exception:
        return None


class GatewayEngine:
    def __init__(self, config: GatewayConfig):
        self.config = config
        self.registry = JobRegistry(config.runs_root)
        self._lock = threading.RLock()
        self._admission = threading.Condition(self._lock)
        self._active_jobs = 0
        self._active_units = 0
        self._threads: dict[str, threading.Thread] = {}
        self.reconcile_on_boot()
        if self.config.retention_seconds > 0:
            self.prune_retention(self.config.retention_seconds)
        self._start_queued_jobs()

    def reconcile_on_boot(self) -> None:
        for job in self.registry.all_jobs():
            state = job.get("state")
            if state == JobState.QUEUED:
                continue
            if state != JobState.RUNNING:
                continue
            pid = job.get("pid")
            if isinstance(pid, int) and _proc_alive(pid):
                self._terminate_record(job, reason="gateway restart reconciliation")
            self.registry.mark_state(
                str(job["tenant"]), str(job["job_id"]), JobState.FAILED,
                error="gateway restart reconciled RUNNING job to FAILED; resubmit with the same idempotency_key to inspect the prior job_id",
            )

    def _start_queued_jobs(self) -> None:
        for job in self.registry.all_jobs():
            if job.get("state") == JobState.QUEUED:
                self._ensure_worker(str(job["tenant"]), str(job["job_id"]))

    def submit(self, tenant: str, job: Mapping[str, Any]) -> dict:
        tenant = slug_tenant(tenant)
        norm = self._normalize_job(tenant, job)
        record, created = self.registry.create(tenant, norm)
        if created:
            self._ensure_worker(tenant, str(record["job_id"]))
        return {"job_id": record["job_id"], "state": record["state"], "created": created}

    def _normalize_job(self, tenant: str, job: Mapping[str, Any]) -> dict:
        spec_toml = str(job.get("spec_toml") or "")
        if not spec_toml.strip():
            raise GatewayError("INVALID_ARGUMENT", "spec_toml is required and must not be empty")
        language = str(job.get("language") or "python").strip().lower()
        if language not in _SUPPORTED_LANGUAGES:
            raise GatewayError("INVALID_ARGUMENT", f"language={language!r} is not supported; use java or python")
        iterations = int(job.get("iterations") or 1)
        if iterations < 1:
            raise GatewayError("INVALID_ARGUMENT", "iterations must be >= 1")
        if iterations > self.config.limits.max_iterations:
            raise GatewayError(
                "RESOURCE_EXHAUSTED",
                f"iterations={iterations} exceeds max_iterations={self.config.limits.max_iterations}",
                http_status=429,
            )
        executor_pool = int(job.get("executor_pool") or 1)
        if executor_pool < 1:
            raise GatewayError("INVALID_ARGUMENT", "executor_pool must be >= 1")
        if executor_pool > self.config.limits.max_executor_pool:
            raise GatewayError(
                "RESOURCE_EXHAUSTED",
                f"executor_pool={executor_pool} exceeds max_executor_pool={self.config.limits.max_executor_pool}",
                http_status=429,
            )
        if executor_pool > self.config.limits.max_worker_units:
            raise GatewayError(
                "RESOURCE_EXHAUSTED",
                f"executor_pool={executor_pool} exceeds max_worker_units={self.config.limits.max_worker_units}",
                http_status=429,
            )
        candidate_sink = str(job.get("candidate_sink") or "loose-files").strip()
        if candidate_sink not in _SUPPORTED_SINKS:
            raise GatewayError("INVALID_ARGUMENT", f"candidate_sink={candidate_sink!r} is not supported")
        overrides = self._validate_overrides(job.get("config_overrides") or {})
        analysis_mode = str(job.get("analysis_mode") or overrides.get("analysis_mode") or "exploratory").strip()
        if analysis_mode not in {"exploratory", "formal"}:
            raise GatewayError("INVALID_ARGUMENT", "analysis_mode must be exploratory or formal")
        policy = str(job.get("execution_policy_profile") or "").strip()
        if not policy:
            raise GatewayError(
                "INVALID_ARGUMENT",
                "execution_policy_profile is required: a submitted job must name the policy "
                "its candidates run under. There is no default.")
        if policy not in _SUPPORTED_POLICIES:
            raise GatewayError("INVALID_ARGUMENT", f"execution_policy_profile={policy!r} is not supported")
        analyzer_goals = str(job.get("analyzer_goals") or overrides.get("analyzer_goals") or "").strip()
        if iterations > 1 and not analyzer_goals:
            raise GatewayError("INVALID_ARGUMENT", "iterations>1 requires analyzer_goals")
        if job.get("db_name"):
            raise GatewayError("PERMISSION_DENIED", "db_name is gateway-owned and cannot be supplied")
        job_id = _slug_id(str(job.get("job_id") or ""), "") if job.get("job_id") else ""
        tenant_root = self.registry.tenant_root(tenant)
        timeout = float(overrides.pop("gateway_timeout_seconds", self.config.limits.default_timeout_seconds))
        return {
            "job_id": job_id or None,
            "spec_toml": spec_toml,
            "language": "py" if language == "python" else language,
            "analyzer_goals": analyzer_goals,
            "iterations": iterations,
            "executor_pool": executor_pool,
            "candidate_sink": candidate_sink,
            "analysis_mode": analysis_mode,
            "execution_policy_profile": policy,
            # Audit F1: carried through the normalized job so the spawned
            # bundle_run.py can satisfy the trusted-local gate. Without these the
            # launcher refuses -- which is the correct behaviour, but the caller's
            # justification must actually reach it.
            "candidate_origin": str(job.get("candidate_origin") or "").strip(),
            "trusted_local_acknowledgement":
                str(job.get("trusted_local_acknowledgement") or "").strip(),
            "config_overrides": overrides,
            "idempotency_key": str(job.get("idempotency_key") or ""),
            "tenant_root": str(tenant_root),
            "run_dir": "",
            "db_name": "",
            "timeout_seconds": timeout,
        }

    def _validate_overrides(self, overrides: Mapping[str, Any]) -> dict:
        if not isinstance(overrides, Mapping):
            raise GatewayError("INVALID_ARGUMENT", "config_overrides must be an object")
        out = {}
        for key, value in overrides.items():
            k = str(key)
            low = k.lower()
            if any(fragment in low for fragment in _DENIED_OVERRIDE_FRAGMENTS):
                raise GatewayError("PERMISSION_DENIED", f"config_overrides[{k!r}] is not caller-safe")
            if k == "gateway_timeout_seconds":
                out[k] = str(value)
                continue
            if k not in _SAFE_CONFIG_OVERRIDES:
                allowed = ", ".join(sorted(_SAFE_CONFIG_OVERRIDES))
                raise GatewayError("INVALID_ARGUMENT", f"config_overrides[{k!r}] is not allowed; allowed keys: {allowed}")
            out[k] = str(value)
        return out

    def _ensure_worker(self, tenant: str, job_id: str) -> None:
        key = f"{tenant}/{job_id}"
        with self._lock:
            if key in self._threads and self._threads[key].is_alive():
                return
            t = threading.Thread(target=self._run_job, args=(tenant, job_id), daemon=True)
            self._threads[key] = t
            t.start()

    def _run_job(self, tenant: str, job_id: str) -> None:
        units = 1
        admitted = False
        try:
            job = self.registry.get(tenant, job_id)
            units = max(1, int(job.get("executor_pool") or 1))
            with self._admission:
                while (self._active_jobs >= self.config.limits.max_concurrent_jobs
                       or self._active_units + units > self.config.limits.max_worker_units):
                    self._admission.wait(timeout=1.0)
                    latest = self.registry.get(tenant, job_id)
                    if latest.get("state") == JobState.CANCELLED:
                        return
                self._active_jobs += 1
                self._active_units += units
                admitted = True
            self._spawn_and_wait(tenant, job_id)
        except Exception as exc:
            try:
                self.registry.mark_state(tenant, job_id, JobState.FAILED, error=str(exc))
            except Exception:
                pass
        finally:
            if admitted:
                with self._admission:
                    self._active_jobs -= 1
                    self._active_units -= units
                    self._admission.notify_all()

    def _spawn_and_wait(self, tenant: str, job_id: str) -> None:
        job = self.registry.get(tenant, job_id)
        tenant_root = Path(str(job["tenant_root"]))
        job_scratch = tenant_root / "_jobs" / job_id
        spec_dir = job_scratch / "spec"
        spec_dir.mkdir(parents=True, exist_ok=True)
        db_name = _slug_db(f"{tenant}_{job_id}", "gateway_job")
        spec_path = spec_dir / f"{db_name}.toml"
        spec_path.write_text(str(job["spec_toml"]), encoding="utf-8")
        log_path = job_scratch / "bundle.log"
        cmd = self._command_for(job, spec_dir, tenant_root, db_name)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("$ " + " ".join(cmd) + "\n")
        run_dir = self._canonical_run_dir(tenant_root, job_id, int(job.get("iterations") or 1))
        self.registry.update(
            tenant, job_id,
            state=JobState.RUNNING,
            run_dir=str(run_dir),
            spec_path=str(spec_path),
            log_path=str(log_path),
            db_name=db_name,
            cmd=cmd,
            started_at=now_iso(),
        )
        proc = subprocess.Popen(
            cmd, cwd=str(self.config.gen_dir), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, env=dict(os.environ), start_new_session=True,
        )
        pgid = os.getpgid(proc.pid)
        proc_start_ticks = _proc_start_ticks(proc.pid)
        self.registry.update(tenant, job_id, pid=proc.pid, pgid=pgid, start_ticks=proc_start_ticks)

        reader = threading.Thread(target=self._read_stdout, args=(proc, log_path), daemon=True)
        reader.start()
        deadline = time.monotonic() + float(job.get("timeout_seconds") or self.config.limits.default_timeout_seconds)
        timed_out = False
        while proc.poll() is None:
            latest = self.registry.get(tenant, job_id)
            if latest.get("state") == JobState.CANCELLED:
                self._signal_process_group(proc.pid, signal.SIGTERM, proc_start_ticks)
                break
            if time.monotonic() > deadline:
                timed_out = True
                self._cancel_bundle(tenant, job_id, reason="TIMEOUT")
                self._signal_process_group(proc.pid, signal.SIGTERM, proc_start_ticks)
                break
            time.sleep(0.25)
        try:
            rc = proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._signal_process_group(proc.pid, signal.SIGKILL, proc_start_ticks)
            rc = proc.wait(timeout=10)
        reader.join(timeout=2)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[gateway] process exited with code {rc}\n")
        latest = self.registry.get(tenant, job_id)
        if latest.get("state") == JobState.CANCELLED:
            return
        if timed_out:
            self.registry.mark_state(tenant, job_id, JobState.FAILED, error="TIMEOUT: job exceeded gateway timeout")
        elif rc == 0:
            self.registry.mark_state(tenant, job_id, JobState.SUCCEEDED)
        else:
            self.registry.mark_state(tenant, job_id, JobState.FAILED, error=f"bundle_run.py exited with code {rc}")

    def _command_for(self, job: Mapping[str, Any], spec_dir: Path, tenant_root: Path, db_name: str) -> list[str]:
        iterations = int(job.get("iterations") or 1)
        cmd = [sys.executable, "bundle_run.py"]
        if iterations > 1:
            cmd.append("iterate")
        cmd += [str(spec_dir), "--db", db_name, "--run-id", str(job["job_id"]), "--runs-root", str(tenant_root)]
        if iterations > 1:
            cmd += ["--iterations", str(iterations)]
        cmd += ["--lang", str(job.get("language") or "py")]
        analyzer = str(job.get("analyzer_goals") or "").strip()
        if analyzer:
            cmd += ["--analyzer", analyzer, "--analysis-mode", str(job.get("analysis_mode") or "exploratory")]
        pool = int(job.get("executor_pool") or 1)
        if pool > 1:
            cmd += ["--executor-pool", str(pool)]
        sink = str(job.get("candidate_sink") or "loose-files")
        if sink != "loose-files":
            cmd += ["--candidate-sink", sink]
        if sink == "grpc":
            # Gateway-owned, not caller-owned (see _SAFE_CONFIG_OVERRIDES comment above):
            # always loopback, always a freshly allocated port so concurrent grpc-sink jobs
            # never collide and no tenant can redirect this internal hop off-host.
            cmd += ["--grpc-host", "127.0.0.1", "--grpc-port", str(_allocate_free_port())]
        cmd += ["--execution-policy-profile", str(job.get("execution_policy_profile"))]
        for _key, _flag in (("candidate_origin", "--candidate-origin"),
                            ("trusted_local_acknowledgement", "--acknowledge-trusted-local")):
            _value = str(job.get(_key) or "").strip()
            if _value:
                cmd += [_flag, _value]
        overrides = dict(job.get("config_overrides") or {})
        for key, value in overrides.items():
            flag = _SAFE_CONFIG_OVERRIDES.get(key)
            if not flag or key in {"analyzer_goals", "analysis_mode"}:
                continue
            cmd += [flag, str(value)]
        return cmd

    def _canonical_run_dir(self, tenant_root: Path, job_id: str, iterations: int) -> Path:
        if iterations > 1:
            dirs = _iteration_dirs(tenant_root, job_id)
            return dirs[-1][1] if dirs else tenant_root / f"{job_id}-it1"
        return tenant_root / job_id

    def _read_stdout(self, proc: subprocess.Popen, log_path: Path) -> None:
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                assert proc.stdout is not None
                for line in proc.stdout:
                    f.write(line)
                    f.flush()
        except Exception:
            pass

    def _signal_process_group(self, pid: int, sig: int, expected_start_ticks: int | None = None) -> bool:
        if expected_start_ticks is not None and _proc_start_ticks(pid) != expected_start_ticks:
            return False
        try:
            os.killpg(os.getpgid(pid), sig)
            return True
        except Exception:
            try:
                os.kill(pid, sig)
                return True
            except Exception:
                return False

    def _cancel_bundle(self, tenant: str, job_id: str, *, reason: str = "cancel requested") -> None:
        try:
            job = self.registry.get(tenant, job_id)
        except RegistryError:
            return
        tenant_root = Path(str(job.get("tenant_root") or self.registry.tenant_root(tenant)))
        cmd = [sys.executable, "bundle_run.py", "cancel", job_id, "--runs-root", str(tenant_root)]
        try:
            subprocess.run(cmd, cwd=str(self.config.gen_dir), stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=20, env=dict(os.environ))
        except Exception:
            pass
        log_path = Path(str(job.get("log_path") or tenant_root / "_jobs" / job_id / "bundle.log"))
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[gateway] {reason}\n")

    def _terminate_record(self, job: Mapping[str, Any], *, reason: str) -> None:
        pid = job.get("pid")
        if isinstance(pid, int) and _proc_alive(pid):
            self._cancel_bundle(str(job["tenant"]), str(job["job_id"]), reason=reason)
            self._signal_process_group(pid, signal.SIGTERM, job.get("start_ticks"))
            if not _wait_for_exit(pid, 5):
                self._signal_process_group(pid, signal.SIGKILL, job.get("start_ticks"))

    def _job_owner(self, job_id: str) -> str:
        for record in self.registry.all_jobs():
            if str(record.get("job_id") or "") == str(job_id):
                return str(record.get("tenant") or "")
        return ""

    def get_record(self, tenant: str, job_id: str) -> dict:
        try:
            return self.registry.get(tenant, job_id)
        except RegistryError as exc:
            owner = self._job_owner(job_id)
            if owner and slug_tenant(owner) != slug_tenant(tenant):
                raise GatewayError("PERMISSION_DENIED", f"job_id={job_id!r} belongs to a different tenant", http_status=403) from exc
            raise GatewayError("NOT_FOUND", str(exc), http_status=404) from exc

    def status(self, tenant: str, job_id: str) -> dict:
        job = self.get_record(tenant, job_id)
        run_dir = self.resolve_run_dir(job)
        progress = collect_progress(run_dir) if run_dir.exists() else {"run_status": None, "stages": {}}
        state = str(job.get("state") or JobState.QUEUED)
        run_status = progress.get("run_status")
        iterations = int(job.get("iterations") or 1)
        if iterations <= 1 and run_status in JobState.TERMINAL and state not in JobState.TERMINAL:
            state = str(run_status)
            self.registry.mark_state(tenant, job_id, state)
        stages = []
        for name, st in (progress.get("stages") or {}).items():
            counts = {}
            for k, v in (st.get("counts") or {}).items():
                if isinstance(v, bool):
                    continue
                if isinstance(v, int):
                    counts[k] = v
            stages.append({"name": name, "status": st.get("status") or "", "counts": counts})
        return {
            "job_id": job_id,
            "state": state,
            "stages": stages,
            "current_iteration": self._current_iteration(job),
            "error": str(job.get("error") or self._stage_error(progress) or ""),
        }

    def _stage_error(self, progress: Mapping[str, Any]) -> str:
        for st in (progress.get("stages") or {}).values():
            counts = st.get("counts") or {}
            errs = counts.get("_errors")
            if errs:
                return json.dumps(errs, ensure_ascii=False)
        return ""

    def _current_iteration(self, job: Mapping[str, Any]) -> str:
        iterations = int(job.get("iterations") or 1)
        if iterations <= 1:
            return ""
        tenant_root = Path(str(job["tenant_root"]))
        dirs = _iteration_dirs(tenant_root, str(job["job_id"]))
        current = dirs[-1][0] if dirs else 0
        return f"{current}/{iterations}"

    def resolve_run_dir(self, job: Mapping[str, Any]) -> Path:
        tenant_root = Path(str(job["tenant_root"]))
        return self._canonical_run_dir(tenant_root, str(job["job_id"]), int(job.get("iterations") or 1))

    def results(self, tenant: str, job_id: str) -> dict:
        status = self.status(tenant, job_id)
        if status["state"] not in JobState.TERMINAL:
            raise GatewayError(
                "FAILED_PRECONDITION",
                f"job_id={job_id!r} is {status['state']}; GetResults is terminal-only",
                http_status=409,
            )
        if status["state"] != JobState.SUCCEEDED:
            raise GatewayError(
                "FAILED_PRECONDITION",
                f"job_id={job_id!r} ended {status['state']}; no successful results contract is available",
                http_status=409,
            )
        job = self.get_record(tenant, job_id)
        run_dir = self.resolve_run_dir(job)
        results = collect_results(run_dir)
        results["job_id"] = job_id
        results["state"] = status["state"]
        it = _iterate_summary(Path(str(job["tenant_root"])), job_id)
        if it is not None:
            results["iterate"] = it
        return results

    def cancel(self, tenant: str, job_id: str) -> dict:
        job = self.get_record(tenant, job_id)
        if job.get("state") in JobState.TERMINAL:
            return self.status(tenant, job_id)
        self.registry.mark_state(tenant, job_id, JobState.CANCELLED, error="cancelled by gateway client")
        self._cancel_bundle(tenant, job_id)
        pid = job.get("pid")
        if isinstance(pid, int) and _proc_alive(pid):
            self._signal_process_group(pid, signal.SIGTERM, job.get("start_ticks"))
            if not _wait_for_exit(pid, 5):
                self._signal_process_group(pid, signal.SIGKILL, job.get("start_ticks"))
        with self._admission:
            self._admission.notify_all()
        return self.status(tenant, job_id)

    def list_jobs(self, tenant: str, state: str | None = None) -> dict:
        if state and state not in {JobState.QUEUED, JobState.RUNNING, *JobState.TERMINAL}:
            raise GatewayError("INVALID_ARGUMENT", f"state={state!r} is not a known JobState")
        jobs = []
        for job in self.registry.list(tenant, state):
            jobs.append({
                "job_id": job.get("job_id"),
                "state": job.get("state"),
                "submitted_at": job.get("submitted_at"),
                "terminal_at": job.get("terminal_at"),
            })
        return {"jobs": jobs}

    def tail_log(self, tenant: str, job_id: str, cursor: int = 0) -> dict:
        job = self.get_record(tenant, job_id)
        path = Path(str(job.get("log_path") or ""))
        lines: list[str] = []
        if path.exists():
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        cursor = max(0, int(cursor or 0))
        return {"log": lines[cursor:], "log_cursor": len(lines)}

    def capabilities(self) -> dict:
        inv = inventory.build_inventory()
        components = {}
        for comp in inv.get("components", []):
            components[str(comp.get("name"))] = str(comp.get("sha256") or ("present" if comp.get("exists") else "missing"))
        limits = self.config.limits
        return {
            "transport": self.config.transport,
            "grpc_python_available": bool(importlib.util.find_spec("grpc") and importlib.util.find_spec("grpc_tools")),
            "supported_languages": sorted(_SUPPORTED_LANGUAGES),
            "supported_candidate_sinks": sorted(_SUPPORTED_SINKS),
            "supported_execution_policy_profiles": sorted(_SUPPORTED_POLICIES),
            "limits": {
                "max_concurrent_jobs": limits.max_concurrent_jobs,
                "max_worker_units": limits.max_worker_units,
                "max_executor_pool": limits.max_executor_pool,
                "max_iterations": limits.max_iterations,
                "default_timeout_seconds": int(limits.default_timeout_seconds),
                "retention_seconds": int(self.config.retention_seconds),
            },
            "components": components,
        }

    def _db_health(self, label: str, host: str, port: int, user: str, password: str) -> str:
        try:
            ready = subprocess.run(["pg_isready", "-h", host, "-p", str(port)],
                                   capture_output=True, text=True, timeout=5)
        except Exception as exc:
            return f"missing:pg_isready failed: {exc}"
        if ready.returncode != 0:
            return f"missing:{label} PostgreSQL not accepting on {host}:{port}"
        if not password:
            return f"missing:{label} DB password not configured"
        out, rc = psql(port, "postgres", "select 1;", host=host, user=user, password=password)
        if rc != 0 or out.strip() != "1":
            return f"missing:{label} PostgreSQL auth/query failed on {host}:{port}"
        return "ready"

    def _java_health(self, java_cmd: str) -> str:
        try:
            result = subprocess.run([java_cmd, "-version"], capture_output=True, text=True, timeout=10)
        except Exception as exc:
            return f"missing:{java_cmd} -version failed: {exc}"
        text = (result.stderr or result.stdout or "").splitlines()
        first = text[0] if text else ""
        if result.returncode != 0:
            return f"missing:{java_cmd} -version exited {result.returncode}"
        if not re.search(r'\b(?:java|openjdk)?\s*version "25\.|\b25\.', first):
            return f"missing:JDK 25 required, got {first or java_cmd}"
        return first

    def health(self) -> dict:
        try:
            cfg, _sources = resolve_config(cli={})
        except ConfigError as exc:
            return {"live": True, "ready": False, "reasons": [f"config={exc}"], "deps": {"config": f"missing:{exc}"}}
        deps = {
            "main_db": self._db_health("main", cfg.main_db_host, cfg.main_db_port, cfg.main_db_user, cfg.main_db_password),
            "results_db": self._db_health("results", cfg.results_db_host, cfg.results_db_port, cfg.results_db_user, cfg.results_db_password),
            "java": self._java_health(cfg.java_cmd),
            "core_jar": "present" if CORE_JAR.is_file() else f"missing:{CORE_JAR}",
            "reader_jar": "present" if READER_JAR.is_file() else f"missing:{READER_JAR}",
            "java_executor_jar": "present" if JAVA_EXECUTOR_JAR.is_file() else f"missing:{JAVA_EXECUTOR_JAR}",
            "java_jars_dir": "present" if JAVA_JARS_DIR.is_dir() else f"missing:{JAVA_JARS_DIR}",
            "py_executor": "present" if PY_EXECUTOR.is_file() else f"missing:{PY_EXECUTOR}",
        }
        reasons = [f"{k}={v}" for k, v in deps.items() if str(v).startswith("missing")]
        return {"live": True, "ready": not reasons, "reasons": reasons, "deps": deps}

    def _run_dirs_for_job(self, job: Mapping[str, Any]) -> list[Path]:
        tenant_root = Path(str(job["tenant_root"]))
        job_id = str(job["job_id"])
        dirs = []
        single = tenant_root / job_id
        if single.is_dir():
            dirs.append(single)
        dirs.extend(path for _idx, path in _iteration_dirs(tenant_root, job_id) if path.is_dir())
        seen: set[Path] = set()
        out = []
        for path in dirs:
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                out.append(path)
        return out

    def _drop_database(self, *, host: str, port: int, user: str, password: str, db_name: str) -> dict:
        if not db_name:
            return {"db": db_name, "status": "skipped-empty"}
        sql = f"DROP DATABASE IF EXISTS {sql_identifier(db_name)} WITH (FORCE);"
        out, rc = psql(port, "postgres", sql, host=host, user=user, password=password)
        if rc != 0:
            return {"db": db_name, "status": "failed", "detail": out}
        return {"db": db_name, "status": "dropped-or-absent"}

    def cleanup_job(self, tenant: str, job_id: str, *, drop_databases: bool = True) -> dict:
        job = self.get_record(tenant, job_id)
        if job.get("state") not in JobState.TERMINAL:
            raise GatewayError("FAILED_PRECONDITION", f"job_id={job_id!r} is {job.get('state')}; cleanup requires a terminal job", http_status=409)
        tenant_root = Path(str(job["tenant_root"]))
        db_name = str(job.get("db_name") or "")
        cleanup_runs = []
        errors = []
        for run_dir in self._run_dirs_for_job(job):
            cmd = [sys.executable, "bundle_run.py", "cleanup", str(run_dir), "--runs-root", str(tenant_root), "--db", db_name, "--yes"]
            proc = subprocess.run(cmd, cwd=str(self.config.gen_dir), capture_output=True, text=True, timeout=120, env=dict(os.environ))
            cleanup_runs.append({"run_dir": str(run_dir), "returncode": proc.returncode, "stdout": proc.stdout[-2000:], "stderr": proc.stderr[-2000:]})
            if proc.returncode != 0:
                errors.append(f"cleanup failed for {run_dir}: rc={proc.returncode}")
        db_drops = []
        if drop_databases and db_name:
            try:
                cfg, _sources = resolve_config(cli={})
                db_drops.append({"cluster": "main", **self._drop_database(host=cfg.main_db_host, port=cfg.main_db_port, user=cfg.main_db_user, password=cfg.main_db_password, db_name=db_name)})
                db_drops.append({"cluster": "results", **self._drop_database(host=cfg.results_db_host, port=cfg.results_db_port, user=cfg.results_db_user, password=cfg.results_db_password, db_name=db_name)})
                errors.extend(f"drop {d['cluster']} DB {db_name}: {d.get('detail') or d['status']}" for d in db_drops if d.get("status") == "failed")
            except Exception as exc:
                errors.append(f"database drop failed: {exc}")
        report = {
            "job_id": job_id,
            "tenant": tenant,
            "run_cleanups": cleanup_runs,
            "database_drops": db_drops,
            "errors": errors,
            "cleaned_at": now_iso() if not errors else "",
        }
        self.registry.update(tenant, job_id, cleanup=report, cleaned_at=report["cleaned_at"] if not errors else "")
        if errors:
            raise GatewayError("INTERNAL", "; ".join(errors), http_status=500)
        return report

    def prune_retention(self, retention_seconds: float) -> dict:
        pruned = []
        errors = []
        now = time.time()
        for job in self.registry.all_jobs():
            if job.get("state") not in JobState.TERMINAL or job.get("cleaned_at"):
                continue
            terminal = _parse_iso(str(job.get("terminal_at") or job.get("submitted_at") or ""))
            if terminal is None or now - terminal < retention_seconds:
                continue
            try:
                pruned.append(self.cleanup_job(str(job["tenant"]), str(job["job_id"])))
            except GatewayError as exc:
                errors.append({"job_id": job.get("job_id"), "error": exc.message})
        return {"retention_seconds": retention_seconds, "pruned": pruned, "errors": errors}

    def write_access_log(self, tenant: str, event: str, payload: Mapping[str, Any]) -> None:
        root = self.registry.tenant_root(tenant)
        path = root / "_registry" / "access.log.jsonl"
        row = {"ts": now_iso(), "tenant": tenant, "event": event, **dict(payload)}
        redacted = {k: ("***REDACTED***" if "token" in k.lower() or "password" in k.lower() else v)
                    for k, v in row.items()}
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(redacted, sort_keys=True, ensure_ascii=False) + "\n")

    def export_registry_snapshot(self, tenant: str, path: Path) -> None:
        write_json_atomic(path, {"schema": "bundle.gateway.registry-snapshot/v1",
                                 "tenant": tenant, "jobs": self.registry.list(tenant)})
