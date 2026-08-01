#!/usr/bin/env python3
r"""serve_face1 — the local companion server that makes Face 1's Run button REAL.

Zero-dependency (stdlib only), same posture as ``constraints/serve.py``. It serves the
single-file ``face1.html`` and exposes a tiny JSON API that actually FIRES the real Bundle
pipeline (``bundle_run.py``) and TRACES it live from the real run-directory journal:

    GET  /                 -> face1.html
    GET  /api/ping         -> {ok, backend:"real", db_env, ...}  (page switches to real mode)
    POST /api/plan  {toml} -> runs `bundle_run.py plan` (no DB) and returns the real plan.json
    POST /api/run   {toml,config} -> writes the spec, spawns `bundle_run.py`, returns a token
    GET  /api/poll?token&log=N   -> new stdout/stderr lines + per-stage status/counts read from
                                    state.json + stages/*.json; when finished, the real results
                                    (executor-summary.json outcomes + provenance.json Pareto front
                                    + metrics.kv points)
    POST /api/cancel?token -> terminate the run's process group

Run it from the generator_trunk root (so the DB env is inherited):

    export BUNDLE_MAIN_DB_PASSWORD=$PGPW BUNDLE_RESULTS_DB_PASSWORD=$PGPW
    python3 intake/serve_face1.py            # opens http://127.0.0.1:8765/

Binds to 127.0.0.1 only. Firing a run executes the real pipeline (Core/Reader/Executor/
Analyzer) exactly as `bundle_run.py` would from your shell — nothing is faked. If the DB/stack
is not up, the run fails honestly and the failure (with the real log tail) is shown in the UI.
"""
from __future__ import annotations

import argparse

import http.server
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from pathlib import Path

# Make `import bundle` work when launched as `python3 intake/serve_face1.py` from
# any cwd: without this only intake/ is on sys.path[0] and the bundle package (in
# the repo root, this file's grandparent) is invisible → ModuleNotFoundError at
# import, the server never binds, and the page's engine probe waits forever.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bundle.gateway.engine import GatewayConfig, GatewayEngine, GatewayLimits
from bundle import capabilities as capability_registry
from bundle.policy import profile_choices
from invitation_wizard import propose
from intake.scenario_library import (
    REPOSITORY_LAUNCH_PROFILES,
    load_scenarios,
    scenario_environment,
    scenario_run_config,
    scenario_spec_document,
)

HERE = Path(__file__).resolve().parent
GEN_DIR = HERE.parent                     # generator_trunk/ (holds bundle_run.py)
FACE1 = HERE / "face1.html"
INVITATION_JS = HERE / "invitation_wizard.js"
BASE = Path(tempfile.mkdtemp(prefix="face1_"))   # per-server scratch for specs + run dirs

_ID_RE = re.compile(r"[^A-Za-z0-9_.-]")
_DB_RE = re.compile(r"[^a-z0-9_]")
_KV_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)")

STAGE_ORDER = ["gen", "core", "seed_bias", "sieve", "reader", "executor", "analyzer"]

# A 1x1 transparent GIF served at /api/alive.gif. A file:// page can load this via
# `new Image()` (no CORS needed for images) to detect that the engine is up and then
# navigate to the served app — more robust than a cross-origin fetch from file://.
_ALIVE_GIF = (b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04"
              b"\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;")

_ITER_DIR_RE = re.compile(r"-it(\d+)$")

# ---------------------------------------------------------------------------
# The FULL bundle_run.py control surface Face 1 drives in LOCAL (direct) mode.
# This registry is the single source of truth for "which run parameter maps to
# which CLI flag": the direct-command builder iterates it, /api/ping advertises
# it, and test_face1_control_panel.py cross-checks it against the real cli.py
# run parser (minus the env-inherited DB secrets) so NO controllable parameter
# can silently go missing — that guarantee is the point. Kinds: "value" emits
# `--flag VALUE` when the field is set; "bool" emits `--flag` when truthy.
# camelCase keys match face1.html's S.run.* control-panel fields exactly.
# ---------------------------------------------------------------------------
_RUN_FLAG_SPECS = [
    # run mode
    ("runMode", "--mode", "value"),
    # constraints / sieve / seed bias
    ("sieve", "--sieve", "bool"),
    ("draw", "--draw", "bool"),
    ("drawExact", "--draw-exact", "bool"),
    ("seedFrom", "--seed-from", "value"),
    ("seedOutput", "--seed-output", "bool"),
    ("explorationFloor", "--exploration-floor", "value"),
    ("minWinnerSupport", "--min-winner-support", "value"),
    # execution policy / sandbox
    ("profile", "--execution-policy-profile", "value"),
    # Audit F1: the two fields that make an unsandboxed run an explicit, recorded
    # decision rather than a silent default.
    ("candidateOrigin", "--candidate-origin", "value"),
    ("trustedLocalAcknowledgement", "--acknowledge-trusted-local", "value"),
    ("sandboxNetworkAllowlist", "--sandbox-network-allowlist", "value"),
    ("sandboxCandidateEnv", "--sandbox-candidate-env", "value"),
    ("executorTolerateOutcomes", "--executor-tolerate-outcomes", "value"),
    ("sandboxPolicy", "--sandbox-policy", "value"),
    ("executorCompiler", "--executor-compiler", "value"),
    # timeouts
    ("coreTimeout", "--core-timeout", "value"),
    ("readerTimeout", "--reader-timeout", "value"),
    ("executorTimeout", "--executor-timeout", "value"),
    # DB ports (host/user/password stay env-inherited — see ENV_INHERITED_FLAGS)
    ("mainPort", "--main-port", "value"),
    ("resultsPort", "--results-port", "value"),
    # budget ceilings + accountability
    ("budgetMandatoryRows", "--budget-mandatory-rows", "value"),
    ("budgetFinalCandidates", "--budget-final-candidates", "value"),
    ("budgetDiskBytes", "--budget-disk-bytes", "value"),
    ("budgetInodes", "--budget-inodes", "value"),
    ("budgetWallTimeSeconds", "--budget-wall-time-seconds", "value"),
    ("budgetRequests", "--budget-requests", "value"),
    ("budgetMonetaryCost", "--budget-monetary-cost", "value"),
    ("budgetWarnFraction", "--budget-warn-fraction", "value"),
    ("costPerCandidate", "--cost-per-candidate", "value"),
    ("overrideBudget", "--override-budget", "value"),
    ("allowExtreme", "--allow-extreme", "bool"),
    ("unleash", "--unleash-initial-productivity-power", "bool"),
    # repeat policy (Plan-1)
    ("repeat", "--repeat", "value"),
    ("repeatPolicy", "--repeat-policy", "value"),
    ("repeatScope", "--repeat-scope", "value"),
    ("repeatEnvironments", "--repeat-environments", "value"),
    # infra paths / commands
    ("scratchRoot", "--scratch-root", "value"),
    ("coreJar", "--core-jar", "value"),
    ("readerJar", "--reader-jar", "value"),
    ("coreProps", "--core-props", "value"),
    ("readerProps", "--reader-props", "value"),
    ("pyExecutor", "--py-executor", "value"),
    ("javaExecutorJar", "--java-executor-jar", "value"),
    ("javaJarsDir", "--java-jars-dir", "value"),
    ("javaCmd", "--java-cmd", "value"),
    ("javacCmd", "--javac-cmd", "value"),
    ("pythonCmd", "--python-cmd", "value"),
    ("configFile", "--config-file", "value"),
    # run-dir compatibility / diagnostics
    ("legacyScratch", "--legacy-scratch", "bool"),
    ("legacyHandoff", "--legacy-handoff", "bool"),
    ("debug", "--debug", "bool"),
]

# Stress-mode (`--mode stress`) knobs — only forwarded when runMode == "stress".
_STRESS_FLAG_SPECS = [
    ("baseUrl", "--base-url"),
    ("workers", "--workers"),
    ("duration", "--duration"),
    ("ramp", "--ramp"),
    ("sloP99", "--slo-p99"),
    ("errBudget", "--err-budget"),
]

# camelCase UI key -> gateway config_overrides key (mirrors
# bundle.gateway.engine._SAFE_CONFIG_OVERRIDES). Only these caller-safe knobs
# reach the multi-tenant GATEWAY backend; the rest are LOCAL-mode only.
_GW_OVERRIDE_KEYS = {
    "executorCompiler": "executor_compiler",
    "explorationFloor": "exploration_floor",
    "minWinnerSupport": "min_winner_support",
    "executorTolerateOutcomes": "executor_tolerate_outcomes",
    "budgetMandatoryRows": "budget_mandatory_rows",
    "budgetFinalCandidates": "budget_final_candidates",
    "budgetDiskBytes": "budget_disk_bytes",
    "budgetInodes": "budget_inodes",
    "budgetWallTimeSeconds": "budget_wall_time_seconds",
    "budgetRequests": "budget_external_requests",
    "budgetMonetaryCost": "budget_monetary_cost",
    "budgetWarnFraction": "budget_warn_fraction",
    "costPerCandidate": "cost_per_candidate",
}

# Identity/transport/analysis flags the direct builder emits via bespoke logic
# (pairing, defaults, java/K dependencies) rather than the flat table above.
_SPECIAL_RUN_FLAGS = {
    "--db", "--run-id", "--runs-root", "--lang", "--analyzer", "--analysis-mode",
    "--candidate-sink", "--grpc-host", "--grpc-port", "--executor-pool", "--iterations",
}

# Every flag Face 1 (local mode) can emit — the "control panel for everything"
# contract, cross-checked against cli.py by test_face1_control_panel.py.
SUPPORTED_RUN_FLAGS = (
    {flag for _k, flag, _kind in _RUN_FLAG_SPECS}
    | {flag for _k, flag in _STRESS_FLAG_SPECS}
    | _SPECIAL_RUN_FLAGS
)

# Deliberately env-inherited (never a browser field): DB credentials/hosts.
ENV_INHERITED_FLAGS = {
    "--main-db-host", "--main-db-user", "--main-db-password",
    "--results-db-host", "--results-db-user", "--results-db-password",
}

_CAPS_CACHE: "dict | None" = None


def _int_or_none(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


SESS: "dict[str, dict]" = {}              # token -> session
SESS_LOCK = threading.Lock()
FACE_ENGINE = GatewayEngine(GatewayConfig(
    gen_dir=GEN_DIR,
    runs_root=BASE / "gateway_runs",
    limits=GatewayLimits(max_concurrent_jobs=1, max_worker_units=4, max_executor_pool=4, max_iterations=5),
))


def _slug_id(s: str, default: str) -> str:
    s = _ID_RE.sub("-", (s or "").strip())
    s = s.strip("-.") or default
    if not re.match(r"^[A-Za-z0-9]", s):
        s = "r-" + s
    return s[:120]


def _slug_db(s: str, default: str) -> str:
    s = _DB_RE.sub("_", (s or "").strip().lower()).strip("_") or default
    if s[0].isdigit():
        s = "d_" + s
    return s[:48]


def _read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _stage_counts(run_dir: Path, stage: str) -> dict:
    """counts list in stages/<stage>.json -> {name: actual}."""
    d = _read_json(run_dir / "stages" / f"{stage}.json")
    out = {}
    if isinstance(d, dict):
        for c in d.get("counts", []) or []:
            if isinstance(c, dict) and c.get("name") is not None:
                out[c["name"]] = c.get("actual")
        errs = d.get("errors") or []
        if errs:
            out["_errors"] = errs
    return out


def _collect_progress(run_dir: Path) -> dict:
    """Read state.json + stages/*.json into a compact, page-friendly progress dict."""
    state = _read_json(run_dir / "state.json") or {}
    stages_state = state.get("stages", {}) if isinstance(state, dict) else {}
    stages = {}
    for name in STAGE_ORDER:
        st = stages_state.get(name)
        if not st:
            continue
        stages[name] = {"status": st.get("status"), "counts": _stage_counts(run_dir, name)}
    return {"run_status": state.get("status"), "stages": stages}


def _collect_results(run_dir: Path) -> dict:
    """Read the REAL results after completion: executor-summary + provenance + metrics.kv."""
    summ = _read_json(run_dir / "executor-summary.json") or {}
    prov = _read_json(run_dir / "provenance.json") or {}
    prog = _collect_progress(run_dir)
    stages = prog.get("stages", {})

    def scount(stage, key):
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

    # optional: all candidate points for the scatter, parsed from the harvested corpus
    points = []
    kv = run_dir / "metrics.kv"
    if kv.exists() and goals:
        gkeys = [g["metric"] for g in goals]
        try:
            for ln in kv.read_text(encoding="utf-8", errors="replace").splitlines():
                toks = dict((m.group(1), float(m.group(2))) for m in _KV_RE.finditer(ln))
                pt = {k: toks[k] for k in gkeys if k in toks}
                if len(pt) == len(gkeys):
                    points.append({"objectives": pt})
        except Exception:
            points = []

    outcomes = summ.get("outcomes") or {}
    return {
        "real": True,
        "outcomes": outcomes,
        "processed": summ.get("processed", scount("executor", "processed")),
        "pass": summ.get("pass", scount("executor", "pass")),
        "fail": summ.get("fail", scount("executor", "fail")),
        "inserted": summ.get("inserted"),
        "counts": {
            "mandatory": scount("core", "fw_final"),
            "post_sieve": scount("sieve", "post_sieve"),
            "candidates": scount("reader", "candidates"),
        },
        "goals": goals,
        "front": front,
        "points": points,
        "provenance_ok": prov.get("provenance_ok"),
        "analysis_mode": prov.get("mode"),
    }


def _iteration_dirs(sess) -> "list[tuple[int, Path]]":
    """The iterate driver's per-iteration run dirs (<run-id>-itN), sorted by N."""
    root, base = sess.get("runs_root"), sess.get("run_id", "")
    if not root:
        return []
    out = []
    for p in Path(root).glob(f"{base}-it*"):
        m = _ITER_DIR_RE.search(p.name)
        if m and p.is_dir():
            out.append((int(m.group(1)), p))
    return sorted(out)


def _resolve_run_dir(sess) -> Path:
    """The run dir to read progress/results from. Single runs: the run dir itself.
    Iterate runs: the LATEST per-iteration dir (live per-stage tracing follows the
    loop; final results come from the last completed iteration)."""
    if not sess.get("iterate"):
        return sess["run_dir"]
    dirs = _iteration_dirs(sess)
    return dirs[-1][1] if dirs else sess["run_dir"]


def _iterate_summary(sess) -> "dict | None":
    """Compact view of the iterate lineage artifact (<run-id>-iterate.json)."""
    if not sess.get("iterate"):
        return None
    lineage = _read_json(Path(sess["runs_root"]) / f"{sess['run_id']}-iterate.json") or {}
    entries = lineage.get("iterations") or []
    return {
        "status": lineage.get("status"),
        "requested": lineage.get("iterations_requested", sess.get("iterations")),
        "completed": len(entries),
        "candidates": [e.get("candidate_count") for e in entries],
        "front_sizes": [len(e.get("front_ids") or []) for e in entries],
        "plan_statuses": [e.get("plan_status") for e in entries],
    }


def _face_job(toml_text: str, cfg: dict) -> dict:
    """Project the UI config onto the GATEWAY (multi-tenant EaaS) job contract.
    The gateway OWNS db_name / run-id / grpc-port and accepts only the caller-safe
    subset (see bundle.gateway.engine); LOCAL mode (_spawn_run_direct) is the
    full-control path. db_name is intentionally NOT sent — the gateway derives it
    and rejects a supplied one with PERMISSION_DENIED (that was the run-breaking
    bug). executor_pool reads the UI's real key; the safe overrides carry the
    budget/exploration/compiler knobs the gateway whitelist allows."""
    iterations = _int_or_none(cfg.get("iterations")) or 1
    executor_pool = _int_or_none(cfg.get("executorPool") or cfg.get("executor_pool")) or 1
    transport = str(cfg.get("transport") or "loose-files").strip() or "loose-files"
    mode = str(cfg.get("mode") or "").strip()
    if mode not in ("exploratory", "formal"):
        mode = "exploratory"
    overrides = {}
    for ui_key, gw_key in _GW_OVERRIDE_KEYS.items():
        v = cfg.get(ui_key)
        if v not in (None, "", []):
            overrides[gw_key] = str(v)
    # grpc_port is NOT forwarded in gateway mode: the gateway allocates a fresh
    # loopback port per job itself (SSRF-safe) — the UI port is advisory here.
    return {
        "spec_toml": toml_text,
        "language": cfg.get("lang") or "py",
        "analyzer_goals": (cfg.get("analyzer") or "").strip(),
        "iterations": iterations,
        "executor_pool": executor_pool,
        "candidate_sink": transport,
        "analysis_mode": mode,
        # Audit F1: pass the operator's choice through unchanged. Substituting
        # "trusted-local" here is exactly how a UI silently granted unsandboxed
        # host execution; an empty value now reaches the launcher, which refuses.
        "execution_policy_profile": cfg.get("profile") or "",
        "candidate_origin": cfg.get("candidateOrigin") or "",
        "trusted_local_acknowledgement": cfg.get("trustedLocalAcknowledgement") or "",
        "config_overrides": overrides,
    }

def _spawn_run(toml_text: str, cfg: dict) -> dict:
    handle = FACE_ENGINE.submit("face1", _face_job(toml_text, cfg))
    token = handle["job_id"]
    rec = FACE_ENGINE.get_record("face1", token)
    sess = {"engine": True, "job_id": token, "run_id": token, "db": rec.get("db_name"),
            "done": False, "exit": None, "iterate": int(rec.get("iterations") or 1) > 1,
            "iterations": int(rec.get("iterations") or 1), "runs_root": Path(rec["tenant_root"])}
    with SESS_LOCK:
        SESS[token] = sess
    return {"token": token, "run_id": token, "db": rec.get("db_name")}


def _direct_command(cfg: dict, spec_dir: Path, db: str, run_id: str, runs_root: Path) -> list:
    """Build the FULL bundle_run.py command for LOCAL (direct) mode from the UI
    config. Every run flag Face 1 exposes is emitted from _RUN_FLAG_SPECS plus the
    bespoke identity/transport/analysis logic here; unset fields are omitted so
    the launcher's own defaults / env / --config-file layers still win. This is
    the "control panel for everything" path — nothing the run parser accepts is
    unreachable (secrets excepted, see ENV_INHERITED_FLAGS)."""
    iterations = _int_or_none(cfg.get("iterations")) or 1
    cmd = [sys.executable, str(GEN_DIR / "bundle_run.py")]
    if iterations > 1:
        # BundleSeed feedback loop: `iterate` runs N journaled passes, iteration
        # i+1's space biased by iteration i's Pareto winners. Goals are REQUIRED
        # (the launcher fails closed without them; the UI surfaces that honestly).
        cmd.append("iterate")
    cmd += [str(spec_dir), "--db", db, "--run-id", run_id, "--runs-root", str(runs_root)]
    if iterations > 1:
        cmd += ["--iterations", str(iterations)]
    lang = str(cfg.get("lang") or "py").strip()
    if lang in ("py", "python", "java"):
        cmd += ["--lang", lang]
    analyzer = str(cfg.get("analyzer") or "").strip()
    if analyzer:
        cmd += ["--analyzer", analyzer]
        mode = str(cfg.get("mode") or "").strip()
        if mode in ("formal", "exploratory"):
            cmd += ["--analysis-mode", mode]
    transport = str(cfg.get("transport") or "loose-files").strip()
    if transport and transport != "loose-files":
        cmd += ["--candidate-sink", transport]
    if transport == "grpc":
        host = str(cfg.get("grpcHost") or "").strip()
        if host:
            cmd += ["--grpc-host", host]
        port = _int_or_none(cfg.get("grpcPort"))
        if port:
            cmd += ["--grpc-port", str(port)]
    pool = _int_or_none(cfg.get("executorPool"))
    if pool and pool > 1:
        cmd += ["--executor-pool", str(pool)]
    for key, flag, kind in _RUN_FLAG_SPECS:
        v = cfg.get(key)
        if kind == "bool":
            if v:
                cmd.append(flag)
        elif v not in (None, "", []):
            cmd += [flag, str(v)]
    if str(cfg.get("runMode") or "").strip() == "stress":
        for key, flag in _STRESS_FLAG_SPECS:
            v = cfg.get(key)
            if v not in (None, "", []):
                cmd += [flag, str(v)]
    return cmd


def _spawn_run_direct(
    toml_text: str,
    cfg: dict,
    environment: dict[str, str] | None = None,
    launch_cwd: Path | None = None,
) -> dict:
    """LOCAL (full-control) backend: drive bundle_run.py directly with the whole
    flag surface. Traced live from the same run journal the gateway path reads."""
    token = os.urandom(6).hex()
    run_id = _slug_id(cfg.get("runId") or "r1", "r1")
    db = _slug_db(cfg.get("db") or "", "task")
    work = BASE / token
    spec_dir = work / "spec"
    runs_root = work / "runs"
    spec_dir.mkdir(parents=True, exist_ok=True)
    runs_root.mkdir(parents=True, exist_ok=True)
    (spec_dir / f"{db}.toml").write_text(toml_text, encoding="utf-8")
    iterations = _int_or_none(cfg.get("iterations")) or 1
    iterate = iterations > 1
    cmd = _direct_command(cfg, spec_dir, db, run_id, runs_root)
    proc = subprocess.Popen(
        cmd, cwd=str(launch_cwd or GEN_DIR), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
        env=dict(os.environ if environment is None else environment),
        start_new_session=True,
    )
    sess = {"proc": proc, "run_dir": runs_root / run_id, "run_id": run_id, "db": db,
            "cmd": cmd, "log": [f"$ {' '.join(cmd)}"], "done": False, "exit": None,
            "started": time.time(),
            "iterate": iterate, "iterations": iterations, "runs_root": runs_root}
    with SESS_LOCK:
        SESS[token] = sess

    def _reader():
        try:
            for line in proc.stdout:                # blocks until EOF
                sess["log"].append(line.rstrip("\n"))
        except Exception as exc:                    # pragma: no cover
            sess["log"].append(f"[serve] reader error: {exc}")
        finally:
            proc.wait()
            sess["exit"] = proc.returncode
            sess["done"] = True
            sess["log"].append(f"[serve] process exited with code {proc.returncode}")

    threading.Thread(target=_reader, daemon=True).start()
    return {"token": token, "run_id": run_id, "db": db}


def _capabilities() -> dict:
    """Cached gateway capabilities (limits, grpc availability, supported enums,
    component inventory) — advertised to the page so the panel can validate."""
    global _CAPS_CACHE
    if _CAPS_CACHE is None:
        try:
            _CAPS_CACHE = FACE_ENGINE.capabilities()
        except Exception as exc:
            _CAPS_CACHE = {"error": str(exc)}
    return _CAPS_CACHE


def _db_info() -> dict:
    """Read-only DB host/user/port resolved from the server env (no network, no
    passwords) so the panel can DISPLAY the bound cluster without a browser field."""
    try:
        from bundle.config import resolve_config
        cfg, _sources = resolve_config(cli={})
        return {
            "main_host": cfg.main_db_host, "main_user": cfg.main_db_user, "main_port": cfg.main_db_port,
            "results_host": cfg.results_db_host, "results_user": cfg.results_db_user,
            "results_port": cfg.results_db_port,
        }
    except Exception:
        return {}


def _ping_payload() -> dict:
    return {
        "ok": True, "backend": "real",
        "db_env": bool(os.environ.get("BUNDLE_MAIN_DB_PASSWORD")),
        "results_env": bool(os.environ.get("BUNDLE_RESULTS_DB_PASSWORD")),
        "cwd": str(GEN_DIR), "python": sys.executable,
        "capabilities": _capabilities(),
        "db": _db_info(),
        "supported_run_flags": sorted(SUPPORTED_RUN_FLAGS),
        "env_inherited_flags": sorted(ENV_INHERITED_FLAGS),
        # Face 1 Old is a static browser document, so the local backend hands it
        # the same canonical registry used by argparse and Face 1 New. The HTML
        # deliberately contains no second list of real profile names.
        "execution_policy_profiles": list(profile_choices()),
        "capability_dimensions": {
            dimension.id: {"values": list(dimension.values), "default": dimension.default,
                           "enumerated": dimension.enumerated}
            for dimension in capability_registry.DIMENSIONS
        },
    }


def _run_plan(toml_text: str) -> dict:
    work = BASE / ("plan_" + os.urandom(4).hex())
    spec_dir = work / "spec"
    out_dir = work / "out"
    spec_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "spec.toml").write_text(toml_text, encoding="utf-8")
    try:
        p = subprocess.run([sys.executable, "bundle_run.py", "plan", str(spec_dir), "--out", str(out_dir)],
                           cwd=str(GEN_DIR), capture_output=True, text=True, timeout=120, env=dict(os.environ))
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    plan = _read_json(out_dir / "plan.json")
    return {"ok": p.returncode == 0, "returncode": p.returncode,
            "stdout": p.stdout, "stderr": p.stderr, "plan": plan}


def _load_examples() -> list:
    """The verified-green scenario library the UI offers as runnable examples.
    Read fresh each call (cheap) so regenerating intake/verified_examples.json
    updates the gallery without a server restart. Only entries whose spec file
    still exists under the repo are returned."""
    return load_scenarios(GEN_DIR)


def _example_run(ex_id: str) -> dict:
    """Fire a verified example through the SAME real pipeline as a composed run:
    resolve its catalog id, read or freshly materialize the trusted TOML, and hand
    it to _spawn_run_direct, which isolates it in its own spec directory."""
    ex = next((e for e in _load_examples() if e.get("id") == ex_id), None)
    if not ex:
        raise ValueError(f"unknown example {ex_id!r}")
    toml_text, _filename = scenario_spec_document(ex, GEN_DIR)
    analyzer = str(ex.get("analyzer") or "").strip()
    cfg = scenario_run_config(
        ex,
        GEN_DIR,
        {
            "backend": "local",
            "db": _slug_db(ex_id, "example"),
            "runId": "r1",
            "lang": "py",
            # Checked-in, reviewed example scenarios. The catalog states the
            # origin and the reason explicitly rather than relying on a default,
            # so the run manifest records why unsandboxed execution was accepted.
            "profile": "trusted-local",
            "candidateOrigin": "reviewed-checked-in",
            "trustedLocalAcknowledgement":
                "reviewed checked-in example scenario launched from the Face 1 catalog",
            "analyzer": analyzer,
            "mode": "formal" if analyzer else "",
        },
    )
    environment = scenario_environment(ex, GEN_DIR.parent)
    launch_cwd = (
        GEN_DIR.parent if ex.get("run_profile") in REPOSITORY_LAUNCH_PROFILES else None
    )
    return _spawn_run_direct(toml_text, cfg, environment, launch_cwd)


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        # Allow a file:// page to probe /api/ping cross-origin so it can detect a
        # just-launched engine and redirect itself to the served app. 127.0.0.1 only.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            return json.loads(raw or b"{}")
        except Exception:
            return {}

    def _query(self):
        from urllib.parse import urlparse, parse_qs
        return parse_qs(urlparse(self.path).query)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html", "/face1.html"):
            try:
                self._send(200, FACE1.read_text(encoding="utf-8"), "text/html; charset=utf-8")
            except Exception as exc:
                self._send(500, f"cannot read face1.html: {exc}", "text/plain; charset=utf-8")
        elif path == "/invitation_wizard.js":
            self._send(200, INVITATION_JS.read_text(encoding="utf-8"), "application/javascript; charset=utf-8")
        elif path == "/api/ping":
            self._send(200, _ping_payload())
        elif path == "/api/poll":
            self._poll()
        elif path == "/api/alive.gif":
            self._send(200, _ALIVE_GIF, "image/gif")
        elif path == "/api/examples":
            self._send(200, _load_examples())
        elif path == "/favicon.ico":
            self._send(204, b"")
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/invitation":
            body = self._body()
            draft = propose(str(body.get("domain") or "learn"), str(body.get("goal") or ""), body.get("risks") or ())
            self._send(200, draft.as_dict())
            return
        if path == "/api/plan":
            self._send(200, _run_plan(self._body().get("toml", "")))
        elif path == "/api/run":
            b = self._body()
            if b.get("example"):                       # run a verified example by id (server reads its spec)
                try:
                    self._send(200, _example_run(str(b.get("example"))))
                except ValueError as exc:
                    self._send(404, {"error": str(exc)})
                except Exception as exc:
                    self._send(500, {"error": str(exc)})
                return
            toml_text = b.get("toml", "")
            if not toml_text.strip():
                self._send(400, {"error": "empty spec"})
                return
            cfg = b.get("config", {}) or {}
            backend = str(cfg.get("backend") or "local").strip().lower()
            try:
                # LOCAL (direct) = full control of every flag (default). GATEWAY =
                # the multi-tenant EaaS engine (safe subset, gateway-owned db/ports).
                spawn = _spawn_run if backend == "gateway" else _spawn_run_direct
                self._send(200, spawn(toml_text, cfg))
            except Exception as exc:
                self._send(500, {"error": str(exc)})
        elif path == "/api/cancel":
            self._cancel()
        else:
            self._send(404, {"error": "not found"})

    def _poll(self):
        q = self._query()
        token = (q.get("token") or [""])[0]
        log_from = int((q.get("log") or ["0"])[0])
        with SESS_LOCK:
            sess = SESS.get(token)
        if not sess:
            self._send(404, {"error": "unknown token"})
            return
        if sess.get("engine"):
            status = FACE_ENGINE.status("face1", sess["job_id"])
            rec = FACE_ENGINE.get_record("face1", sess["job_id"])
            run_dir = FACE_ENGINE.resolve_run_dir(rec)
            tail = FACE_ENGINE.tail_log("face1", sess["job_id"], log_from)
            progress = _collect_progress(run_dir)
            done = status.get("state") in {"SUCCEEDED", "FAILED", "CANCELLED"}
            sess["done"] = done
            sess["exit"] = 0 if status.get("state") == "SUCCEEDED" else (1 if done else None)
            resp = {"done": done, "exit": sess["exit"],
                    "log": tail["log"], "log_cursor": tail["log_cursor"],
                    "run_status": status.get("state"), "stages": progress.get("stages", {})}
        else:
            run_dir = _resolve_run_dir(sess)
            log = sess["log"]
            new = log[log_from:]
            progress = _collect_progress(run_dir)
            resp = {"done": sess["done"], "exit": sess["exit"],
                    "log": new, "log_cursor": log_from + len(new),
                    "run_status": progress.get("run_status"), "stages": progress.get("stages", {})}
        if sess.get("iterate"):
            dirs = _iteration_dirs(sess)
            resp["iteration"] = dirs[-1][0] if dirs else 0
            resp["iterations_total"] = sess.get("iterations")
        if sess["done"]:
            resp["results"] = _collect_results(run_dir)
            it = _iterate_summary(sess)
            if it is not None:
                resp["results"]["iterate"] = it
            resp["ok"] = (sess["exit"] == 0)
        self._send(200, resp)

    def _cancel(self):
        token = (self._query().get("token") or [""])[0]
        with SESS_LOCK:
            sess = SESS.get(token)
        if not sess:
            self._send(404, {"error": "unknown token"})
            return
        if sess.get("engine"):
            FACE_ENGINE.cancel("face1", sess["job_id"])
            self._send(200, {"ok": True})
            return
        proc = sess["proc"]
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except Exception:
            try:
                proc.terminate()
            except Exception:
                pass
        sess["log"].append("[serve] cancel requested (SIGTERM)")
        self._send(200, {"ok": True})


def _register_scheme_handler() -> str:
    """Best-effort: register `combframework://` -> engine_launcher.sh so the file://
    page's "Start the engine" button can launch this server on its own. Idempotent —
    safe to call on every startup. Returns a short status string for the banner; a
    silent no-op (returns "") when the desktop tooling / platform isn't present."""
    try:
        launcher = HERE / "engine_launcher.sh"
        if not launcher.exists():
            return ""
        try:
            launcher.chmod(0o755)
        except OSError:
            pass
        apps = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")) / "applications"
        apps.mkdir(parents=True, exist_ok=True)
        desktop = apps / "combframework-engine.desktop"
        desktop.write_text(
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=Combinatorics Framework Engine\n"
            "Comment=Starts the Face 1 real backend (serve_face1.py)\n"
            f'Exec="{launcher}" %u\n'
            "Terminal=false\n"
            "NoDisplay=true\n"
            "MimeType=x-scheme-handler/combframework;\n",
            encoding="utf-8",
        )
        try:
            desktop.chmod(0o755)
        except OSError:
            pass
        for cmd in (["update-desktop-database", str(apps)],
                    ["xdg-mime", "default", "combframework-engine.desktop", "x-scheme-handler/combframework"]):
            try:
                subprocess.run(cmd, check=False, capture_output=True, timeout=10)
            except (OSError, subprocess.SubprocessError):
                pass
        return f"combframework:// -> {launcher.name} (armed the file:// page's Start button)"
    except Exception:
        return ""


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="serve_face1",
        description="Serve the Face 1 UI and real Bundle backend on loopback.",
    )
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true",
                        help="serve without opening the system web browser")
    args = parser.parse_args(argv)
    host = "127.0.0.1"
    port = args.port
    open_browser = not args.no_browser
    if not FACE1.exists():
        print(f"error: {FACE1} not found", file=sys.stderr)
        return 2
    httpd = http.server.ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}/"
    print(f"Face 1 (REAL backend) at {url}")
    print(f"  bundle_run.py cwd : {GEN_DIR}")
    print(f"  run scratch base  : {BASE}")
    _reg = _register_scheme_handler()
    if _reg:
        print(f"  {_reg}")
    if not os.environ.get("BUNDLE_MAIN_DB_PASSWORD"):
        print("  ⚠ BUNDLE_MAIN_DB_PASSWORD not set — a real run needs the DB env "
              "(export it before launching, or runs will fail honestly).")
    print("  Ctrl-C to stop.")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            print(f"  open this URL in your browser: {url}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping…")
    finally:
        httpd.shutdown()
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
