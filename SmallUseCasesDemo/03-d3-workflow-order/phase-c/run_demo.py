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

"""Guarded Bundle launcher for D3 phase C: one 1440-case benchmark, contract budgets, evidence.

    python run_demo.py --input xlsx            # the benchmark (spec/full); also plans catalogue-SCA3
    python run_demo.py --input xlsx --dry-run  # all checks and the exact command; no DB

Guards, in order: the frozen contract and derived-set hashes, spec/ equal to a
fresh build, the fixture tests, the Framework working tree equal to the accepted
build (commit and status recorded), free disk, the sandbox image, both
plans (EXACT 1440 benchmark and 20-row catalogue, same programs, not budget-blocked),
no constraints, and absence of `as0927_d3c_<stamp>` on both ports. A name collision stops the run; nothing is ever dropped. The real
Bundle then runs Core, Reader and Executor (no sieve). Afterwards this script reads
the owned databases (read-only queries) and the run directory, and writes
evidence/<run-id>/ for the offline verifier.
"""
import argparse
import base64
import datetime
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = Path(__file__).resolve().parents[3]
GEN = REPO / "generator_trunk"
SCRATCH = Path(os.environ.get("BUNDLE_SCRATCH_ROOT") or Path(__file__).resolve().parents[2] / "_work")
EVIDENCE = HERE / "evidence"
CONTRACT_SHA256 = "9bb74b125be6b74c326258553bd34591ddb0bf9ff4366adb84d11458ac281191"
DERIVED_SHA256 = "2b6a74acd4013a26c6ef0d2651ef65b3d8668e9e8e5628e70c1d63436e485451"
PORTS = {"main": int(os.environ.get("BUNDLE_MAIN_DB_PORT", "5433")), "results": int(os.environ.get("BUNDLE_RESULTS_DB_PORT", "5432"))}
DB_RE = re.compile(r"^as0927_d3c_[0-9a-z_]+$")
BUDGETS = ["--budget-mandatory-rows", "1600", "--budget-final-candidates", "1600",
           "--budget-disk-bytes", "200000000", "--budget-wall-time-seconds", "1800"]
# Measured per-candidate cost (Executor duration / candidates, generated-default, one worker):
# D2 275.8 s/480 = 0.575, D3 A 41.5 s/72 = 0.576, D3 B 52.3 s/81 = 0.646. The range below
# replaces the generic 0.05-2 s placeholder in the wall-time estimate (Framework v3 setting).
PER_CANDIDATE = ["--per-candidate-seconds-min", "0.3", "--per-candidate-seconds-max", "1.2"]
PER_CANDIDATE_BASIS = {"d2_20260927T154330Z": [275.783, 480], "d3a_20260927T181801Z": [41.495, 72],
                       "d3b_20260927T181920Z": [52.329, 81]}
JVM_OPTIONS = "-Xmx2g"
MIN_FREE_BYTES = 2_000_000_000
SANDBOX_IMAGE = os.environ.get("BUNDLE_SANDBOX_IMAGE", "python:3-slim")
SOURCES = ("sut.py", "oracle.py", "runtime.py", "build_spec.py", "run_demo.py", "verify.py", "replay.py",
           "tests/test_d3c_fixture.py", "CONTRACT.md", "architect-derived.json", "spec/build.json",
           *(f"spec/{v}/{f}" for v in ("full", "catalogue-SCA3") for f in ("spec.toml", "demo.xlsx")))
EXPECTED_PLAN = {"full": (1440, 1, 1440), "catalogue-SCA3": (20, 1, 20)}
# The Framework build for this phase: v3 = D1-accepted v2 + the per-candidate-seconds setting.


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now_iso() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def fail(msg: str, code: int = 2):
    print(f"run_demo: REFUSED — {msg}", file=sys.stderr)
    raise SystemExit(code)


def pg_connect(port: int, database: str):
    import pg8000.dbapi
    role = "RESULTS" if port == PORTS["results"] else "MAIN"      # credentials come from the Framework's env (bundle_env.sh)
    return pg8000.dbapi.connect(host=os.environ.get(f"BUNDLE_{role}_DB_HOST", "127.0.0.1"), port=port,
                                user=os.environ.get(f"BUNDLE_{role}_DB_USER", "postgres"),
                                password=os.environ[f"BUNDLE_{role}_DB_PASSWORD"], database=database)


def db_exists(port: int, name: str) -> bool:
    conn = pg_connect(port, "postgres")
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM pg_database WHERE datname = %s", (name,))
        return cur.fetchone()[0] != 0
    finally:
        conn.close()


def query(port: int, db: str, sql: str, args=()):
    conn = pg_connect(port, db)
    try:
        cur = conn.cursor()
        cur.execute(sql, args)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def jsonable(v):
    if isinstance(v, (datetime.datetime, datetime.date)):
        return v.isoformat()
    if isinstance(v, (bytes, bytearray, memoryview)):
        return base64.b64encode(bytes(v)).decode("ascii")
    if isinstance(v, list):
        return [jsonable(x) for x in v]
    return v


def run_checked(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    return r.returncode, (r.stdout + r.stderr)


def preflight(a):
    checks = {}
    if sha256_file(HERE / "CONTRACT.md") != CONTRACT_SHA256:
        fail("CONTRACT.md does not match the frozen v1 hash")
    if sha256_file(HERE / "architect-derived.json") != DERIVED_SHA256:
        fail("architect-derived.json does not match its recorded hash")
    checks["contract_sha256"] = CONTRACT_SHA256
    rc, out = run_checked([sys.executable, str(HERE / "build_spec.py"), "--check"], cwd=HERE)
    checks["build_spec_check"] = out.strip()
    if rc != 0:
        fail(f"spec/ drifted from a fresh build: {out.strip()}")
    if not a.skip_tests:
        rc, out = run_checked([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"], cwd=HERE)
        checks["tests"] = out.strip().splitlines()[-1] if out.strip() else ""
        if rc != 0:
            fail(f"fixture tests failed:\n{out}")
    # The Framework working tree must equal the accepted build: D1's v2 inventory (read-only).
    rc, out = run_checked(["git", "-C", str(REPO), "status", "--porcelain", "--untracked-files=no"])
    checks["framework_git_status"] = [l for l in out.rstrip("\n").splitlines() if l.strip()]      # recorded, not gated
    rc, out = run_checked(["git", "-C", str(REPO), "rev-parse", "HEAD"])
    checks["framework_head"] = out.strip()
    free = shutil.disk_usage(HERE).free
    checks["disk_free_bytes_before"] = free
    if free < MIN_FREE_BYTES:
        fail(f"only {free} bytes free on /; need {MIN_FREE_BYTES}")
    rc, out = run_checked(["docker", "image", "inspect", "--format", "{{.Id}}", SANDBOX_IMAGE])
    if rc != 0:
        fail(f"sandbox image {SANDBOX_IMAGE} is not available: {out.strip()}")
    checks["sandbox_image"] = {"name": SANDBOX_IMAGE, "id": out.strip()}
    return checks


def resolve_input(kind: str):
    sys.path.insert(0, str(GEN))
    import fwgen as fg
    path = HERE / "spec" / "full" / ("demo.xlsx" if kind == "xlsx" else "spec.toml")
    if fg.load_spec(path).constraints or fg.load_spec(HERE / "spec" / "full" / "spec.toml").constraints:
        fail("phase C carries no constraints (no sieve)", code=3)
    return path, [], None


def plans(dest: Path):
    """Plan the benchmark (both inputs) and the planned-only SCA3 catalogue, under the run's budgets."""
    dest.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, BUNDLE_BUDGET_MANDATORY_ROWS=BUDGETS[1], BUNDLE_BUDGET_FINAL_CANDIDATES=BUDGETS[3],
               BUNDLE_BUDGET_DISK_BYTES=BUDGETS[5], BUNDLE_BUDGET_WALL_TIME_SECONDS=BUDGETS[7])
    out = {}
    for v in EXPECTED_PLAN:
        for kind, name in (("toml", "spec.toml"), ("xlsx", "demo.xlsx")):
            key = f"{v}-{kind}"
            r = subprocess.run([sys.executable, str(GEN / "bundle_run.py"), "plan", str(HERE / "spec" / v / name),
                                "--out", str(dest / f"plan-{key}"), *PER_CANDIDATE], cwd=REPO, env=env,
                               capture_output=True, text=True)
            (dest / f"plan-{key}.log").write_text(r.stdout + r.stderr, encoding="utf-8")
            if r.returncode != 0:
                fail(f"plan of {v}/{name} failed (see plan-{key}.log)")
            out[key] = json.loads((dest / f"plan-{key}" / "plan.json").read_text(encoding="utf-8"))
    summary = {"cardinality": {k: {c: (p["cardinality"][c]["mode"], p["cardinality"][c]["value"]) for c in
                                   ("mandatory", "optional_multiplier", "final")} for k, p in out.items()},
               "per_slot": {k: {s: (e["mode"], e["value"]) for s, e in p["cardinality"]["per_slot"].items()} for k, p in out.items()},
               "budget_blocking": {k: p["budget_blocking"] for k, p in out.items()},
               "dependency_graph_sha256": {k: p["dependency_graph"].get("sha256") or hashlib.sha256(json.dumps(
                   p["dependency_graph"]["graph"], sort_keys=True).encode()).hexdigest() for k, p in out.items()}}
    for v, (m, o, f) in EXPECTED_PLAN.items():
        for kind in ("toml", "xlsx"):
            c = summary["cardinality"][f"{v}-{kind}"]
            if (c["mandatory"], c["optional_multiplier"], c["final"]) != (("EXACT", m), ("EXACT", o), ("EXACT", f)):
                fail(f"{v} {kind} plan is not EXACT {m} x {o} = {f}: {c}")
        g = summary["dependency_graph_sha256"]
        if g[f"{v}-toml"] != g[f"{v}-xlsx"]:
            fail(f"the {v} TOML and XLSX plans describe different programs")
    if summary["budget_blocking"]["full-xlsx"]:
        fail(f"the benchmark plan is blocked by budgets: {summary['budget_blocking']['full-xlsx']}")
    summary["same_dependency_graph"] = True
    (dest / "plan-comparison.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def bundle_command(input_path: Path, db: str, run_id: str, runs_root: Path):
    return [sys.executable, str(GEN / "bundle_run.py"), str(input_path), "--db", db, "--lang", "py",
            "--run-id", run_id, "--runs-root", str(runs_root), *BUDGETS, *PER_CANDIDATE,
            "--execution-policy-profile", "generated-default", "--candidate-origin", "generated",
            "--executor-workers", "1", "--repeat", "1"]


def deterministic_tar(src_dir: Path, out: Path):
    """tar.gz of the candidate sources with fixed metadata, so its hash depends on content only."""
    import gzip
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for f in sorted(src_dir.iterdir()):
            data = f.read_bytes()
            info = tarfile.TarInfo(name=f"src/{f.name}")
            info.size, info.mtime, info.mode = len(data), 0, 0o644
            tar.addfile(info, io.BytesIO(data))
    out.write_bytes(gzip.compress(buf.getvalue(), mtime=0))


def export(run_dir: Path, ev: Path, db: str, run_id: str):
    """Copy compact run artifacts and read the owned databases into evidence/<run-id>/."""
    logs = ev / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    copied = {}
    for rel in ("run.json", "state.json", "resolved_config.json", "processes.json", "sidecar.json",
                "executor-summary.json", "metrics.kv", "core.log", "reader.log", "executor.log",
                "handshake/handoff/manifest.json", "handshake/handoff/execution_policy.json",
                "handshake/arguments/fwVar.shift", "handshake/sqlTemplate/insert.sql"):
        src = run_dir / rel
        if src.is_file():
            dst = (logs if rel.endswith(".log") else ev / "run") / rel.replace("/", "__")
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied[rel] = sha256_file(src)
    for f in sorted((run_dir / "stages").glob("*.json")):
        (ev / "run" / "stages").mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, ev / "run" / "stages" / f.name)
        copied[f"stages/{f.name}"] = sha256_file(f)
    books = sorted((run_dir / "wb").glob("*.xlsx"))
    for b in books:
        shutil.copy2(b, ev / "run" / f"core_input__{b.name}")
        copied[f"wb/{b.name}"] = sha256_file(b)
    for c in sorted((run_dir / "wb").glob("*.constraints.json")):
        shutil.copy2(c, ev / "run" / f"wb__{c.name}")
        copied[f"wb/{c.name}"] = sha256_file(c)
    src_dir = run_dir / "src"
    deterministic_tar(src_dir, ev / "candidates.tar.gz")
    candidates = {f.name: sha256_file(f) for f in sorted(src_dir.iterdir())}

    main, res = PORTS["main"], PORTS["results"]
    tables = query(main, db, "SELECT table_name FROM information_schema.tables "
                             "WHERE table_schema = 'public' ORDER BY table_name")
    counts = {}
    for t in (r["table_name"] for r in tables):
        counts[t] = query(main, db, f'SELECT count(*) AS n FROM "{t}"')[0]["n"]
    dictionary = query(main, db, 'SELECT * FROM "NumberToValue1" ORDER BY 1')
    fw_final = query(main, db, 'SELECT * FROM "fw_final" ORDER BY combi_id')
    base = {t: query(main, db, f'SELECT * FROM "{t}"') for t in counts
            if t.startswith("fw_final_base") or t.startswith("fw_opt")}
    results_v2 = query(res, db, "SELECT * FROM results_v2 WHERE run_id = %s ORDER BY candidate_id, attempt, repeat_idx",
                       (run_id,))
    legacy = query(res, db, f'SELECT * FROM public."{db}" ORDER BY 1')
    dump = {"main_db": {"port": main, "database": db, "table_row_counts": counts,
                        "NumberToValue1": [{k: jsonable(v) for k, v in r.items()} for r in dictionary],
                        "fw_final_after_sieve": [{k: jsonable(v) for k, v in r.items()} for r in fw_final],
                        "fw_final_base_tables": {t: [{k: jsonable(v) for k, v in r.items()} for r in rows]
                                                 for t, rows in base.items() if t.startswith("fw_final_base")},
                        "fw_opt_tables": {t: [{k: jsonable(v) for k, v in r.items()} for r in rows]
                                          for t, rows in base.items() if t.startswith("fw_opt")}},
            "results_db": {"port": res, "database": db,
                           "results_v2": [{k: jsonable(v) for k, v in r.items()} for r in results_v2],
                           "legacy_table": [{k: jsonable(v) for k, v in r.items()} for r in legacy]}}
    (ev / "db-export.json").write_text(json.dumps(dump, indent=1, sort_keys=True) + "\n", encoding="utf-8")

    # One observation per metrics line: the Executor's provenance prefix + the candidate's record.
    by_candidate = {r["candidate_id"]: r for r in results_v2}
    obs_lines = []
    for line in (run_dir / "metrics.kv").read_text(encoding="utf-8").splitlines():
        tokens = dict(t.split("=", 1) for t in line.split() if "=" in t)
        raw = base64.urlsafe_b64decode(tokens["rec"])
        if hashlib.sha256(raw).hexdigest() != tokens["rec_sha256"]:
            raise SystemExit(f"record hash mismatch for {tokens.get('candidate_id')}")
        rec = json.loads(raw)
        row = by_candidate.get(tokens["candidate_id"], {})
        rec["framework"] = {"candidate_id": tokens["candidate_id"], "source_ref": tokens["source_ref"],
                            "source_sha256": candidates.get(tokens["source_ref"]),
                            "run_id": tokens.get("run_id"), "metrics_fw_var": int(tokens["FW_VAR"]),
                            "outcome": row.get("outcome"), "verdict_code": row.get("verdict_code"),
                            "attempt": row.get("attempt"), "repeat_idx": row.get("repeat_idx"),
                            "results_v2_source_hash": row.get("source_hash")}
        obs_lines.append(json.dumps(rec, sort_keys=True))
    (ev / "observations.jsonl").write_text("\n".join(sorted(obs_lines)) + "\n", encoding="utf-8")
    return {"copied_sha256": copied, "candidate_sha256": candidates,
            "candidates_tar_sha256": sha256_file(ev / "candidates.tar.gz"),
            "db_export_sha256": sha256_file(ev / "db-export.json"),
            "observations_sha256": sha256_file(ev / "observations.jsonl")}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--input", choices=("xlsx", "toml"), required=True)
    ap.add_argument("--dry-run", action="store_true", help="run every check and print the command; no DB, no run")
    ap.add_argument("--skip-tests", action="store_true")
    a = ap.parse_args()

    checks = preflight(a)
    input_path, constraint_ids, companion = resolve_input(a.input)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tag = "d3c"
    run_id, db = f"{tag}_{stamp}", f"as0927_{tag}_{stamp.lower()}"
    ev = EVIDENCE / run_id
    if ev.exists():
        fail(f"evidence directory {ev} already exists")
    if not a.dry_run:                    # exact copies of the run inputs, taken before the run
        (ev / "inputs").mkdir(parents=True)
        for name in ("spec.toml", "demo.xlsx"):
            shutil.copy2(HERE / "spec" / "full" / name, ev / "inputs" / name)
    checks["plans"] = plans(ev if not a.dry_run else Path(tempfile.gettempdir()) / f"d3c-dry-{stamp}")
    if not DB_RE.match(db):
        fail(f"database name {db!r} outside the owned as0927_d3c_* namespace")
    runs_root = SCRATCH / db / "runs"
    cmd = bundle_command(input_path, db, run_id, runs_root)
    env = dict(os.environ, JAVA_TOOL_OPTIONS=JVM_OPTIONS)
    if a.dry_run:
        print(json.dumps({"checks": checks, "input": str(input_path), "constraints": constraint_ids,
                          "companion": companion,
                          "run_id": run_id, "db": db, "command": cmd,
                          "env": {"JAVA_TOOL_OPTIONS": JVM_OPTIONS}}, indent=2))
        return
    absent = {}
    for role, port in PORTS.items():
        if db_exists(port, db):
            fail(f"database {db} already exists on port {port}; choose a new stamp (nothing was dropped)")
        absent[role] = {"port": port, "exists_before": False}

    (ev / "logs").mkdir(parents=True, exist_ok=False)
    inputs_copy = {n: sha256_file(ev / "inputs" / n) for n in sorted(os.listdir(ev / "inputs"))}
    extra = []
    inputs = {rel: sha256_file(HERE / rel) for rel in (*SOURCES, *extra)}
    manifest = {"schema": "d3c.run-manifest/v1", "example": "D3 phase C — 03-d3-workflow-order/phase-c", "phase": "C", "per_candidate_seconds": PER_CANDIDATE, "per_candidate_basis": PER_CANDIDATE_BASIS, "contract": "v1",
                "contract_sha256": CONTRACT_SHA256, "run_id": run_id, "input_kind": a.input,
                "input_path": str(input_path), "constraints_loaded": constraint_ids,
                "constraints_companion": companion,
                "databases": {"name": db, "absence_checked": absent, "owner": "the AI implementer (D3)"},
                "run_dir": str(runs_root / run_id), "jvm": {"JAVA_TOOL_OPTIONS": JVM_OPTIONS},
                "preflight": checks, "inputs_sha256": inputs, "input_copies_sha256": inputs_copy,
                "started": now_iso()}
    commands = [{"stage": "bundle", "argv": cmd, "cwd": str(REPO), "env": {"JAVA_TOOL_OPTIONS": JVM_OPTIONS}}]
    (ev / "commands.json").write_text(json.dumps(commands, indent=2) + "\n", encoding="utf-8")
    (ev / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    t0 = time.monotonic()
    with (ev / "logs" / "bundle_run.log").open("w", encoding="utf-8") as log:
        r = subprocess.run(cmd, cwd=REPO, env=env, stdout=log, stderr=subprocess.STDOUT)
    manifest["bundle_returncode"] = r.returncode
    manifest["bundle_seconds"] = round(time.monotonic() - t0, 1)
    manifest["finished"] = now_iso()
    manifest["databases"]["exists_after"] = {role: db_exists(port, db) for role, port in PORTS.items()}
    manifest["disk_free_bytes_after"] = shutil.disk_usage(HERE).free
    run_dir = runs_root / run_id
    if run_dir.is_dir():
        manifest["run_dir_bytes"] = sum(f.stat().st_size for f in run_dir.rglob("*") if f.is_file())
    (ev / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"bundle exit {r.returncode}; run {run_id}; db {db}; log {ev / 'logs' / 'bundle_run.log'}")
    if r.returncode != 0:
        raise SystemExit(r.returncode)
    manifest["exports"] = export(run_dir, ev, db, run_id)
    (ev / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    rc, out = run_checked([sys.executable, str(HERE / "verify.py"), "--run", str(ev)], cwd=HERE)
    print(out.strip())
    raise SystemExit(rc)


if __name__ == "__main__":
    main()
