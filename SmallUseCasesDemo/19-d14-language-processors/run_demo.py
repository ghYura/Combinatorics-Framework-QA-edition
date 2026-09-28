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

"""Guarded Bundle launcher for D14a: one campaign of 432 candidates (no sieve, no optional axis), then the verifier.

    python $PWD/run_demo.py              # source SmallUseCasesDemo/bundle_env.sh first; use the absolute path
    python $PWD/run_demo.py --dry-run    # every check and the exact command; no DB, no run

Guards, in order: the frozen contract, prediction and derivation hashes, spec/ equal to a fresh build,
the fixture tests (including the literal reference controls and the verifier's parser on a locally
composed candidate), the independent exploration (explore.py --precheck: the literal controls, the two
FW_Permut declaration orders, all 432 cases field by field against the frozen predictions, the tallies),
the Framework commit and status (recorded), free disk and ownership
of the example and scratch folders, the sandbox image, an XLSX/TOML pair without rules or companion,
both plans (EXACT 432 at every stage within the 500 budgets; TOML and XLSX with one graph, which differs
from the AI architect's shape plan only in the DECL slot's displayed verb) and absence of `as0927_d14a_<stamp>` on
both ports. A name collision stops the run; nothing is ever dropped. The Bundle runs Core, Reader and
Executor; afterwards this script reads the owned databases (read-only), records retained sizes, writes
evidence/<run-id>/ and runs the verifier.
"""
import argparse
import base64
import datetime
import gzip
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
REPO = Path(__file__).resolve().parents[2]
GEN = REPO / "generator_trunk"
SCRATCH = Path(os.environ.get("BUNDLE_SCRATCH_ROOT") or Path(__file__).resolve().parents[1] / "_work")
EVIDENCE = HERE / "evidence"
CONTRACT = HERE / "CONTRACT.md"
DERIVED = HERE / "architect-derived.json"
DERIVE = HERE / "derive.py"
CONTRACT_SHA256 = "02c07e48b20310c2987d960c6c46bc5f09fa142b45b3b38354d75d2208e5ffde"
DERIVED_SHA256 = "aa08c2e3ea09442a14c4b422959c1e19d41089a01c7dd0191240af272204e757"
DERIVE_SHA256 = "1751ea419c1e849103aa1e97e2f27db35051323439878401bc9f11f73f0bff27"
EXPECTED = 432
SHAPE_PLAN = HERE / "planning" / "plan" / "plan.json"
PORTS = {"main": int(os.environ.get("BUNDLE_MAIN_DB_PORT", "5433")), "results": int(os.environ.get("BUNDLE_RESULTS_DB_PORT", "5432"))}
DB_RE = re.compile(r"^as0927_d14a_[0-9a-z_]+$")
BUDGETS = ["--budget-mandatory-rows", "500", "--budget-final-candidates", "500",
           "--budget-disk-bytes", "150000000", "--budget-wall-time-seconds", "1200"]
JVM_OPTIONS = "-Xmx2g"
MIN_FREE_BYTES = 2_000_000_000
SANDBOX_IMAGE = os.environ.get("BUNDLE_SANDBOX_IMAGE", "python:3-slim")
SOURCES = ("compiler.py", "vm.py", "interpreter.py", "oracle.py", "runtime.py", "build_spec.py", "explore.py", "run_demo.py",
           "verify.py", "replay.py", "tests/test_d14a_fixture.py", "spec/build.json", "spec/spec.toml", "spec/demo.xlsx",
           "precheck/precheck.json", "planning/shape.toml", "planning/plan/plan.json", "CONTRACT.md", "architect-derived.json",
           "derive.py")


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
    if isinstance(v, (list, tuple)):
        return [jsonable(x) for x in v]
    return v


def run_checked(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    return r.returncode, (r.stdout + r.stderr)


def preflight(a):
    checks = {}
    for path, want in ((CONTRACT, CONTRACT_SHA256), (DERIVED, DERIVED_SHA256), (DERIVE, DERIVE_SHA256)):
        if sha256_file(path) != want:
            fail(f"{path.name} does not match its frozen hash")
    checks["contract_sha256"], checks["derived_sha256"], checks["derive_sha256"] = CONTRACT_SHA256, DERIVED_SHA256, DERIVE_SHA256
    rc, out = run_checked([sys.executable, str(HERE / "build_spec.py"), "--check"], cwd=HERE)
    checks["build_spec_check"] = out.strip()
    if rc != 0:
        fail(f"spec/ drifted from a fresh build: {out.strip()}")
    if not a.skip_tests:
        rc, out = run_checked([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"], cwd=HERE)
        checks["tests"] = out.strip().splitlines()[-1] if out.strip() else ""
        if rc != 0:
            fail(f"fixture tests failed:\n{out}")
    rc, out = run_checked([sys.executable, str(HERE / "explore.py"), "--precheck"], cwd=HERE)
    checks["explore_precheck"] = out.strip().splitlines()
    pre = json.loads((HERE / "precheck" / "precheck.json").read_text())
    if rc != 0 or not pre["cases_equal_frozen"] or pre["decl_permutations"] != ["XY", "YX"] or not pre["tallies_equal_frozen"] \
            or pre["literal_controls"] != {"L(+,*)": -1, "R(+,*)": -3, "L(-,-)": -2} or pre["counts"]["cases"] != EXPECTED:
        fail(f"the independent model exploration failed: {out}")
    rc, out = run_checked(["git", "-C", str(REPO), "status", "--porcelain", "--untracked-files=no"])
    checks["framework_git_status"] = [l for l in out.rstrip("\n").splitlines() if l.strip()]      # recorded, not gated
    rc, out = run_checked(["git", "-C", str(REPO), "rev-parse", "HEAD"])
    checks["framework_head"] = out.strip()
    SCRATCH.mkdir(parents=True, exist_ok=True)                    # the scratch root is created on first use
    owned = {str(p): p.is_dir() and p.stat().st_uid == os.getuid() and os.access(p, os.W_OK) for p in (HERE, SCRATCH)}
    checks["ownership"] = {"uid": os.getuid(), "owned_writable": owned}
    if not all(owned.values()):
        fail(f"example or scratch folder not owned/writable by this user: {owned}")
    free = shutil.disk_usage(HERE).free
    checks["disk_free_bytes_before"] = free
    if free < MIN_FREE_BYTES:
        fail(f"only {free} bytes free on /; need {MIN_FREE_BYTES}")
    rc, out = run_checked(["docker", "image", "inspect", "--format", "{{.Id}}", SANDBOX_IMAGE])
    if rc != 0:
        fail(f"sandbox image {SANDBOX_IMAGE} is not available: {out.strip()}")
    checks["sandbox_image"] = {"name": SANDBOX_IMAGE, "id": out.strip()}
    return checks


def resolve_input():
    sys.path.insert(0, str(GEN))
    import fwgen as fg
    xlsx, toml = fg.load_spec(HERE / "spec" / "demo.xlsx"), fg.load_spec(HERE / "spec" / "spec.toml")
    if xlsx.constraints or toml.constraints or xlsx.params or toml.params or xlsx.sidecar_path:
        fail("D14a carries no rules, params or companion", code=3)
    return HERE / "spec" / "demo.xlsx"


def normal_graph(graph):
    """Nodes and edges with each brace node renamed after the sheet it produces (ids differ by input)."""
    name = {e["dst"]: "brace->" + e["src"] for e in graph["edges"] if e["kind"] == "produces"}
    def node(n):
        attrs = dict(n.get("attrs") or {})
        if attrs.get("is_join_result"):
            attrs.pop("verb", None)        # TOML shows the slot's placeholder verb, XLSX the effective brace
        return json.dumps(dict(n, id=name.get(n["id"], n["id"]), attrs=attrs), sort_keys=True)
    nodes = sorted(node(n) for n in graph["nodes"])
    edges = sorted((name.get(e["src"], e["src"]), e["kind"], name.get(e["dst"], e["dst"])) for e in graph["edges"])
    return {"nodes": nodes, "edges": edges}


DECL_VERB_ONLY = {"DECL": {"verb": ["FW_Combi(1)", "FW_Permut()"]}}


def architect_difference(plan):
    """Node attributes that differ between this plan and the AI architect's shape plan (edges and per-slot counts must match)."""
    architect = json.loads(SHAPE_PLAN.read_text())
    if sorted(map(json.dumps, architect["dependency_graph"]["graph"]["edges"])) != sorted(map(json.dumps, plan["dependency_graph"]["graph"]["edges"])) \
            or architect["cardinality"]["per_slot"] != plan["cardinality"]["per_slot"]:
        return {"edges_or_per_slot": "differ"}
    a = {n["id"]: n for n in architect["dependency_graph"]["graph"]["nodes"]}
    b = {n["id"]: n for n in plan["dependency_graph"]["graph"]["nodes"]}
    out = {}
    for k in sorted(set(a) | set(b)):
        na, nb = a.get(k) or {}, b.get(k) or {}
        if {x: y for x, y in na.items() if x != "attrs"} != {x: y for x, y in nb.items() if x != "attrs"}:
            out[k] = {"node": [na, nb]}
            continue
        d = {x: [na["attrs"].get(x), nb["attrs"].get(x)] for x in set(na["attrs"]) | set(nb["attrs"]) if na["attrs"].get(x) != nb["attrs"].get(x)}
        if d:
            out[k] = d
    return out


def plans(dest: Path):
    """Plan both inputs under the campaign budgets."""
    dest.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, BUNDLE_BUDGET_MANDATORY_ROWS=BUDGETS[1], BUNDLE_BUDGET_FINAL_CANDIDATES=BUDGETS[3],
               BUNDLE_BUDGET_DISK_BYTES=BUDGETS[5], BUNDLE_BUDGET_WALL_TIME_SECONDS=BUDGETS[7])
    out = {}
    for kind, name in (("toml", "spec.toml"), ("xlsx", "demo.xlsx")):
        r = subprocess.run([sys.executable, str(GEN / "bundle_run.py"), "plan", str(HERE / "spec" / name),
                            "--out", str(dest / f"plan-{kind}")], cwd=REPO, env=env, capture_output=True, text=True)
        (dest / f"plan-{kind}.log").write_text(r.stdout + r.stderr, encoding="utf-8")
        if r.returncode != 0:
            fail(f"plan of {name} failed")
        out[kind] = json.loads((dest / f"plan-{kind}" / "plan.json").read_text(encoding="utf-8"))
    card = {k: {c: [p["cardinality"][c]["mode"], p["cardinality"][c]["value"], p["cardinality"][c].get("lower"),
                    p["cardinality"][c].get("upper")] for c in ("mandatory", "post_sieve", "optional_multiplier", "final")}
            for k, p in out.items()}
    reasons = {k: {c: p["cardinality"][c].get("reasons") for c in ("mandatory", "post_sieve", "final")} for k, p in out.items()}
    per_slot = {k: p["cardinality"]["per_slot"] for k, p in out.items()}
    graph = {k: p["dependency_graph"].get("sha256") or hashlib.sha256(json.dumps(p["dependency_graph"]["graph"],
             sort_keys=True).encode()).hexdigest() for k, p in out.items()}
    g = {k: p["dependency_graph"]["graph"] for k, p in out.items()}
    summary = {"cardinality": card, "per_slot": per_slot, "constraints_present": {k: p["constraints_present"] for k, p in out.items()},
               "budget_blocking": {k: p["budget_blocking"] for k, p in out.items()},
               "dependency_graph_sha256": graph, "same_dependency_graph": graph["toml"] == graph["xlsx"],
               "normal_graph": {k: normal_graph(v) for k, v in g.items()}, "reasons": reasons,
               "warnings": {k: p.get("warnings") for k, p in out.items()},
               "graph_hash": {k: p["dependency_graph"]["graph_hash"] for k, p in out.items()},
               "architect_shape_plan_graph_hash": json.loads(SHAPE_PLAN.read_text())["dependency_graph"]["graph_hash"],
               "difference_from_architect_shape_plan": architect_difference(out["xlsx"]),
               "note": ("EXACT 432 at every stage; no rules and no optional axis. the AI architect's shape.toml shows the DECL slot's placeholder "
                        "verb FW_Combi(1); these inputs name the effective FW_Permut() in the slot too, so TOML and XLSX share one graph.")}
    for k in ("toml", "xlsx"):
        c = card[k]
        if any(c[x] != ["EXACT", EXPECTED, EXPECTED, EXPECTED] for x in ("mandatory", "post_sieve", "final")) \
                or c["optional_multiplier"][:2] != ["EXACT", 1] or out[k]["constraints_present"] != 0 or out[k]["budget_blocking"] \
                or summary["graph_hash"][k] != summary["graph_hash"]["xlsx"] or summary["difference_from_architect_shape_plan"] != DECL_VERB_ONLY:
            fail(f"{k} plan is outside the contract: {c} graph={summary['graph_hash'][k]} "
                 f"architect-diff={summary['difference_from_architect_shape_plan']} blocking={out[k]['budget_blocking']}")
    summary["same_normal_graph"] = summary["normal_graph"]["toml"] == summary["normal_graph"]["xlsx"]
    if card["toml"] != card["xlsx"] or not summary["same_normal_graph"]:
        fail(f"the TOML and XLSX plans describe different programs: {summary['normal_graph']}")
    (dest / "plan-comparison.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def bundle_command(input_path: Path, db: str, run_id: str, runs_root: Path):
    return [sys.executable, str(GEN / "bundle_run.py"), str(input_path), "--db", db, "--lang", "py",
            "--run-id", run_id, "--runs-root", str(runs_root), *BUDGETS,
            "--execution-policy-profile", "generated-default", "--candidate-origin", "generated",
            "--executor-workers", "1", "--repeat", "1"]


def deterministic_tar(src_dir: Path, out: Path):
    """tar.gz of the candidate sources with fixed metadata, so its hash depends on content only."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for f in sorted(src_dir.iterdir()):
            data = f.read_bytes()
            info = tarfile.TarInfo(name=f"src/{f.name}")
            info.size, info.mtime, info.mode = len(data), 0, 0o644
            tar.addfile(info, io.BytesIO(data))
    out.write_bytes(gzip.compress(buf.getvalue(), mtime=0))


CHAIN_RE = re.compile(r"\[DIAG(?:-PASS)?\] Sheet ")


def export(run_dir: Path, ev: Path, db: str, run_id: str):
    """Copy compact run artifacts and read the owned databases into evidence/<run-id>/."""
    logs = ev / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    copied = {}
    for rel in ("run.json", "state.json", "resolved_config.json", "processes.json",
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
    for b in sorted((run_dir / "wb").glob("*.xlsx")):
        shutil.copy2(b, ev / "run" / f"core_input__{b.name}")
        copied[f"wb/{b.name}"] = sha256_file(b)
    core_log = run_dir / "core.log"
    if core_log.is_file():                       # the effective program: per-sheet pass lines
        chain = [l for l in core_log.read_text(errors="replace").splitlines() if CHAIN_RE.search(l) and "Sheet HEAD" not in l]
        (ev / "chain-log.txt").write_text("\n".join(chain) + "\n", encoding="utf-8")
    src_dir = run_dir / "src"
    deterministic_tar(src_dir, ev / "candidates.tar.gz")
    candidates = {f.name: sha256_file(f) for f in sorted(src_dir.iterdir())}

    main, res = PORTS["main"], PORTS["results"]
    names = [r["table_name"] for r in query(main, db, "SELECT table_name FROM information_schema.tables "
                                                      "WHERE table_schema = 'public' ORDER BY table_name")]
    tables = {t: [{k: jsonable(v) for k, v in r.items()} for r in query(main, db, f'SELECT * FROM "{t}" ORDER BY 1')]
              for t in names}
    results_v2 = query(res, db, "SELECT * FROM results_v2 WHERE run_id = %s ORDER BY candidate_id, attempt, repeat_idx",
                       (run_id,))
    legacy = query(res, db, f'SELECT * FROM public."{db}" ORDER BY 1')
    dump = {"main_db": {"port": main, "database": db, "table_row_counts": {t: len(rows) for t, rows in tables.items()},
                        "tables": tables},
            "results_db": {"port": res, "database": db,
                           "results_v2": [{k: jsonable(v) for k, v in r.items()} for r in results_v2],
                           "legacy_table": [{k: jsonable(v) for k, v in r.items()} for r in legacy]}}
    (ev / "db-export.json").write_text(json.dumps(dump, indent=1, sort_keys=True) + "\n", encoding="utf-8")

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
    ap.add_argument("--dry-run", action="store_true", help="run every check and print the command; no DB, no run")
    ap.add_argument("--skip-tests", action="store_true")
    a = ap.parse_args()

    checks = preflight(a)
    input_path = resolve_input()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id, db = f"d14a_{stamp}", f"as0927_d14a_{stamp.lower()}"
    ev = EVIDENCE / run_id
    if ev.exists():
        fail(f"evidence directory {ev} already exists")
    if not a.dry_run:                    # exact copies of the run inputs, taken before the run
        (ev / "inputs").mkdir(parents=True)
        for name in ("spec.toml", "demo.xlsx"):
            shutil.copy2(HERE / "spec" / name, ev / "inputs" / name)
    checks["plans"] = plans(ev if not a.dry_run else Path(tempfile.gettempdir()) / f"d14a-dry-{stamp}")
    if not DB_RE.match(db):
        fail(f"database name {db!r} outside the owned as0927_d14a_* namespace")
    runs_root = SCRATCH / db / "runs"
    cmd = bundle_command(input_path, db, run_id, runs_root)
    env = dict(os.environ, JAVA_TOOL_OPTIONS=JVM_OPTIONS)
    if a.dry_run:
        print(json.dumps({"checks": checks, "input": str(input_path), "run_id": run_id, "db": db, "command": cmd,
                          "env": {"JAVA_TOOL_OPTIONS": JVM_OPTIONS}}, indent=2))
        return
    absent = {}
    for role, port in PORTS.items():
        if db_exists(port, db):
            fail(f"database {db} already exists on port {port}; choose a new stamp (nothing was dropped)")
        absent[role] = {"port": port, "exists_before": False}

    (ev / "logs").mkdir(parents=True, exist_ok=False)
    inputs_copy = {n: sha256_file(ev / "inputs" / n) for n in sorted(os.listdir(ev / "inputs"))}
    inputs = {rel: sha256_file(HERE / rel) for rel in SOURCES}                # keys relative to this folder
    manifest = {"schema": "d14a.run-manifest/v1", "example": "D14a — 19-d14-language-processors", "contract": "v1",
                "contract_sha256": CONTRACT_SHA256, "run_id": run_id, "input_kind": "xlsx",
                "input_path": str(input_path),
                "databases": {"name": db, "absence_checked": absent, "owner": "the AI implementer (D14a)"},
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
    manifest["databases"]["retained_bytes"] = {role: query(port, "postgres", "SELECT pg_database_size(%s) AS b", (db,))[0]["b"]
                                               for role, port in PORTS.items() if manifest["databases"]["exists_after"][role]}
    manifest["databases"]["owner_role"] = {role: query(port, "postgres", "SELECT pg_get_userbyid(datdba) AS o FROM pg_database "
                                                                         "WHERE datname = %s", (db,))[0]["o"]
                                           for role, port in PORTS.items() if manifest["databases"]["exists_after"][role]}
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
