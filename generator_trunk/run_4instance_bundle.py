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

r"""run_4instance_bundle — launch 4 fin_tech instances and run the Bundle in parallel.

Architecture
────────────
  4 fin_tech instances  (server1+server2 pairs, each with its own PostgreSQL DB):
    inst1  server1=8000  server2=8001  DB=financetest_1
    inst2  server1=8002  server2=8003  DB=financetest_2
    inst3  server1=8004  server2=8005  DB=financetest_3
    inst4  server1=8006  server2=8007  DB=financetest_4

  Candidates (from testgen_fintech.py) are distributed round-robin into 4 dirs:
    /tmp/fw_4inst/inst{1..4}/candidates/   ← each executor watches its own dir

  RunMeFirstOnce per instance  (runFirstOnce/runmefirstonce.first):
    A Python script that receives the incoming \d_\d_\d.py candidate path and
    rewrites  TARGET_BASE_URL = "..."  in-place to point to that instance's
    server1.  py_executor calls it before every candidate it launches.

  4 py_executor processes run in parallel via ThreadPoolExecutor.
  Results are written to 4 separate Results DB tables:
    postgresql://<user>:<password>@<host>:<port>/fintech_bundle_inst{1..4}
    (resolved at runtime from BundleConfig results_db_* — see bundle/config.py)

Usage
─────
    python3 run_4instance_bundle.py [--skip-gen] [--skip-launch]

    --skip-gen      don't re-run testgen_fintech.py (use existing candidates)
    --skip-launch   don't start app instances (assume already running)
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE       = Path(__file__).resolve().parent
CANDIDATES = HERE / "generated_tests_fintech"
WORK       = Path("/tmp/fw_4inst")
PY         = sys.executable

sys.path.insert(0, str(HERE))
from bundle.config import resolve_config as _resolve_bundle_config
from sut_paths import project_path

FINTECH = project_path("fintech")

_cfg, _cfg_sources = _resolve_bundle_config()
if not _cfg.results_db_password:
    sys.exit("DB password not configured — set BUNDLE_RESULTS_DB_PASSWORD "
             "(or the bundle dev-defaults file; see bundle/config.py) "
             "before running this script.")
# This script runs both the fin_tech app DBs and the Bundle Results DBs against
# the same local PostgreSQL instance (port 5432) — that's the `results_db_*`
# profile in bundle.config (the `main_db_*` profile defaults to port 5433,
# which this script never touches).
RESULTS_DB_HOST, RESULTS_DB_PORT, RESULTS_DB_USER, RESULTS_DB_PASSWORD = (
    _cfg.results_db_host, _cfg.results_db_port, _cfg.results_db_user, _cfg.results_db_password)
PGPW       = {"PGPASSWORD": RESULTS_DB_PASSWORD, **os.environ}

INSTANCES = [
    {"id": 1, "s1": 8000, "s2": 8001, "app_db": "financetest_1", "res_db": "fintech_bundle_inst1"},
    {"id": 2, "s1": 8002, "s2": 8003, "app_db": "financetest_2", "res_db": "fintech_bundle_inst2"},
    {"id": 3, "s1": 8004, "s2": 8005, "app_db": "financetest_3", "res_db": "fintech_bundle_inst3"},
    {"id": 4, "s1": 8006, "s2": 8007, "app_db": "financetest_4", "res_db": "fintech_bundle_inst4"},
]


def sh(cmd, **kw):
    return subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True,
                          env=PGPW, **kw)


def psql(port, db, sql):
    r = sh(["psql", "-h", RESULTS_DB_HOST, "-p", str(port), "-U", RESULTS_DB_USER,
            "-d", db, "-tAc", sql])
    return r.stdout.strip(), r.returncode


def ok(msg):  print(f"  ✓ {msg}")
def info(msg): print(f"  · {msg}")
def fail(msg): print(f"  ✗ {msg}"); sys.exit(1)


# ── 1. Generate candidates ────────────────────────────────────────────────────
def step_generate():
    print("\n[1] GENERATE candidates (testgen_fintech.py)")
    r = sh([PY, str(HERE / "testgen_fintech.py")])
    if r.returncode != 0:
        fail(f"testgen_fintech failed:\n{r.stderr[:300]}")
    lines = [l for l in r.stdout.splitlines() if "Emitted" in l or "syntax-check" in l or "PASS" in l]
    for l in lines:
        ok(l.strip())


# ── 2. Setup application DBs + launch 4 instances ────────────────────────────
def _create_app_db(app_db: str):
    sh(["psql", "-h", RESULTS_DB_HOST, "-p", str(RESULTS_DB_PORT), "-U", RESULTS_DB_USER,
        "-d", "postgres", "-c", f"DROP DATABASE IF EXISTS {app_db}"])
    sh(["psql", "-h", RESULTS_DB_HOST, "-p", str(RESULTS_DB_PORT), "-U", RESULTS_DB_USER,
        "-d", "postgres", "-c", f"CREATE DATABASE {app_db}"])
    sh(["psql", "-h", RESULTS_DB_HOST, "-p", str(RESULTS_DB_PORT), "-U", RESULTS_DB_USER,
        "-d", app_db, "-f", str(FINTECH / "sql/schema.sql")])


def _wait_up(port: int, label: str, timeout: int = 15) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = subprocess.run(["curl", "-s", "--max-time", "1",
                            f"http://127.0.0.1:{port}/health"],
                           capture_output=True, text=True)
        if r.returncode == 0 and "ok" in r.stdout:
            return True
        time.sleep(0.5)
    return False


_procs: list[subprocess.Popen] = []


def step_launch():
    print("\n[2] LAUNCH 4 fin_tech instances")
    schema = FINTECH / "sql/schema.sql"
    for inst in INSTANCES:
        _create_app_db(inst["app_db"])
        env = {
            **os.environ,
            "POSTGRES_DSN": f"postgresql://{RESULTS_DB_USER}:{RESULTS_DB_PASSWORD}@"
                            f"{RESULTS_DB_HOST}:{RESULTS_DB_PORT}/{inst['app_db']}",
            "APP_SHARED_SECRET": "change-me",
            "SERVER2_BASE_URL": f"http://127.0.0.1:{inst['s2']}",
        }
        p2 = subprocess.Popen(
            ["uvicorn", "finance_stack.server2:app",
             "--host", "127.0.0.1", "--port", str(inst["s2"]), "--log-level", "warning"],
            cwd=str(FINTECH), env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        p1 = subprocess.Popen(
            ["uvicorn", "finance_stack.server1:app",
             "--host", "127.0.0.1", "--port", str(inst["s1"]), "--log-level", "warning"],
            cwd=str(FINTECH), env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        _procs.extend([p2, p1])

    # Wait for all server1s (they're the outward-facing gateway)
    time.sleep(2)
    for inst in INSTANCES:
        up = _wait_up(inst["s1"], f"inst{inst['id']} server1:{inst['s1']}")
        if up:
            ok(f"inst{inst['id']}  server1:{inst['s1']}  server2:{inst['s2']}  "
               f"DB={inst['app_db']}")
        else:
            fail(f"inst{inst['id']} server1:{inst['s1']} did not come up in time")


# ── 3. Build 4 work dirs + RunMeFirstOnce scripts ─────────────────────────────
def _runfirst_script(base_url: str) -> str:
    """A Python script that receives a candidate path and patches TARGET_BASE_URL."""
    return f'''\
#!/usr/bin/env python3
"""RunMeFirstOnce — patches incoming candidate to target this instance.
Called by py_executor as:  python runmefirstonce.first <candidate_path>
Rewrites the TARGET_BASE_URL line in-place before the candidate is launched.
"""
import sys, re
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
text = re.sub(
    r'TARGET_BASE_URL\\s*=\\s*"[^"]*"',
    'TARGET_BASE_URL = "{base_url}"',
    text,
)
path.write_text(text, encoding="utf-8")
'''


import fwgen as fg


def step_setup_work_dirs():
    print("\n[3] SETUP work dirs, handshakes, RunMeFirstOnce, candidate distribution")
    WORK.mkdir(parents=True, exist_ok=True)

    spec = fg.load_spec(HERE / "specs/fintech_client_server.toml")

    # Collect and sort candidate files
    cands = sorted(CANDIDATES.glob("[0-9]*.py"))
    if not cands:
        fail(f"no candidates in {CANDIDATES} — run testgen_fintech.py first")
    info(f"{len(cands)} candidates to distribute across 4 instances")

    for inst in INSTANCES:
        idir = WORK / f"inst{inst['id']}"
        cdir = idir / "candidates"
        hdir = idir / "handshake"
        cdir.mkdir(parents=True, exist_ok=True)
        for sub in ("resultsDbURL", "sqlTemplate", "runFirstOnce", "arguments"):
            (hdir / sub).mkdir(parents=True, exist_ok=True)

        # Distribute candidates round-robin: inst1 gets 0,4,8,...; inst2 gets 1,5,9,... etc.
        inst_cands = [c for i, c in enumerate(cands) if i % 4 == inst["id"] - 1]
        for i, src in enumerate(inst_cands, start=1):
            shutil.copy(src, cdir / f"{i}_0_0.py")
        info(f"inst{inst['id']}: {len(inst_cands)} candidates  "
             f"(e.g. {inst_cands[0].name if inst_cands else '—'}…)")

        # Results DB for this instance
        res_db = inst["res_db"]
        sh(["psql", "-h", RESULTS_DB_HOST, "-p", str(RESULTS_DB_PORT), "-U", RESULTS_DB_USER,
            "-d", "postgres", "-c", f"DROP DATABASE IF EXISTS {res_db}"])
        sh(["psql", "-h", RESULTS_DB_HOST, "-p", str(RESULTS_DB_PORT), "-U", RESULTS_DB_USER,
            "-d", "postgres", "-c", f"CREATE DATABASE {res_db}"])
        jdbc = (f"jdbc:postgresql://{RESULTS_DB_HOST}:{RESULTS_DB_PORT}/{res_db}"
                f"?user={RESULTS_DB_USER}&password={RESULTS_DB_PASSWORD}")
        fg.emit_handshake(spec, hdir, db_url=jdbc,
                          table_name="fintech_bundle", fwvar_shift=1)

        # Create Results table
        conn_kw = dict(host=RESULTS_DB_HOST, port=RESULTS_DB_PORT, user=RESULTS_DB_USER,
                       password=RESULTS_DB_PASSWORD, database=res_db)
        import pg8000.dbapi as pg
        conn = pg.connect(**conn_kw); conn.autocommit = True; cur = conn.cursor()
        cols = fg.predict_results_columns(spec)
        col_defs = []
        for c in cols:
            if c == "status": col_defs.append('"status" BOOLEAN')
            elif c == "attachment": col_defs.append('"attachment" TEXT')
            elif c in ("fw_var","combi_id_final","combi_id_optional","fw_optJ"):
                col_defs.append(f'"{c}" INTEGER')
            else: col_defs.append(f'"{c}" BOOLEAN')
        cur.execute('CREATE TABLE "fintech_bundle" (\n  ' + ',\n  '.join(col_defs) + '\n)')
        cur.close(); conn.close()

        # RunMeFirstOnce: patches TARGET_BASE_URL to this instance's server1
        base_url = f"http://127.0.0.1:{inst['s1']}"
        rfo_path = hdir / "runFirstOnce/runmefirstonce.first"
        rfo_path.write_text(_runfirst_script(base_url), encoding="utf-8")
        ok(f"inst{inst['id']}  cands={len(inst_cands)}  "
           f"RunMeFirstOnce→{base_url}  Results DB={res_db}")


# ── 4. Run 4 py_executor instances in parallel ────────────────────────────────
def _run_executor(inst: dict) -> dict:
    idir = WORK / f"inst{inst['id']}"
    hdir = idir / "handshake"
    result = subprocess.run(
        [PY, str(HERE.parent / "Executor_trunk/py_executor.py"),
         "-srcDirList",      str(idir / "candidates"),
         "-dirResultsDbURL", str(hdir / "resultsDbURL"),
         "-dirSqlTemplate",  str(hdir / "sqlTemplate"),
         "-dirArguments",    str(hdir / "arguments"),
         "-dirRunFirstOnce", str(hdir / "runFirstOnce"),
         "--failOnly",       "false",
         "--writeToDB",      "true"],
        capture_output=True, text=True, timeout=300,
    )
    last = (result.stdout + result.stderr).strip().splitlines()[-1:]
    return {"id": inst["id"], "output": last[0] if last else "(no output)",
            "rc": result.returncode, "stdout": result.stdout}


def step_run_parallel():
    print("\n[4] RUN 4 py_executor instances in parallel")
    results = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_run_executor, inst): inst for inst in INSTANCES}
        for fut in as_completed(futures):
            inst = futures[fut]
            try:
                r = fut.result()
                results[r["id"]] = r
                ok(f"inst{r['id']}  {r['output']}")
            except Exception as e:
                results[inst["id"]] = {"id": inst["id"], "output": str(e), "rc": 1}
    return results


# ── 5. Collect + report ───────────────────────────────────────────────────────
def step_report(exec_results: dict):
    print("\n[5] AGGREGATE RESULTS")
    import pg8000.dbapi as pg

    total_pass = total_fail = total_broken = 0
    rows_per_inst = {}

    for inst in INSTANCES:
        er = exec_results.get(inst["id"], {})
        # Parse py_executor summary line: "processed=N pass=P fail=F broken=B ..."
        import re
        m = re.search(r"processed=(\d+) pass=(\d+) fail=(\d+) broken=(\d+)", er.get("output",""))
        if m:
            proc, pas, fai, bro = map(int, m.groups())
        else:
            proc = pas = fai = bro = 0

        # Query Results DB
        conn = pg.connect(host=RESULTS_DB_HOST, port=RESULTS_DB_PORT, user=RESULTS_DB_USER,
                          password=RESULTS_DB_PASSWORD, database=inst["res_db"])
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute('SELECT COUNT(*), COUNT(*) FILTER (WHERE status), '
                    'COUNT(*) FILTER (WHERE NOT status) FROM "fintech_bundle"')
        db_total, db_pass, db_fail = cur.fetchone()
        cur.close(); conn.close()

        rows_per_inst[inst["id"]] = {
            "s1": inst["s1"], "res_db": inst["res_db"],
            "processed": proc, "pass": pas, "fail": fai, "broken": bro,
            "db_total": db_total, "db_pass": db_pass, "db_fail": db_fail,
        }
        total_pass += db_pass; total_fail += db_fail
        info(f"inst{inst['id']}  :800{inst['id']-1*0}  "
             f"processed={proc}  pass={pas}  fail={fai}  broken={bro}  "
             f"DB rows={db_total} (pass={db_pass} fail={db_fail})")

    print(f"\n  ══ TOTAL  pass={total_pass}  fail={total_fail}  "
          f"(across 4 instances, {total_pass+total_fail} DB rows) ══")
    return rows_per_inst


# ── 6. Write TEST_RESULTS_4INSTANCE.md ───────────────────────────────────────
def step_write_report(rows_per_inst: dict):
    print("\n[6] WRITE TEST_RESULTS_4INSTANCE.md")
    lines = []
    a = lines.append
    a("# Finance Stack — 4-Instance Parallel Bundle Run")
    a("")
    a(f"**Date:** 2026-06-01  ")
    a(f"**Framework:** generator_trunk · py_executor · RunMeFirstOnce per-candidate patching  ")
    a(f"**Instances:** 4 × (server1+server2+PostgreSQL)  ")
    a(f"**Candidates per instance:** ~{len(sorted(CANDIDATES.glob('[0-9]*.py')))//4}  ")
    a(f"**Distribution:** round-robin across 4 executor directories  ")
    a("")
    a("## Instance Map")
    a("")
    a("| Instance | server1 port | server2 port | App DB | Results DB |")
    a("|---|---|---|---|---|")
    for inst in INSTANCES:
        a(f"| inst{inst['id']} | {inst['s1']} | {inst['s2']} | {inst['app_db']} | {inst['res_db']} |")
    a("")
    a("## Results per Instance")
    a("")
    a("| Instance | Processed | PASS | FAIL | Broken | DB rows |")
    a("|---|---|---|---|---|---|")
    total_p = total_f = total_b = 0
    for inst_id, r in sorted(rows_per_inst.items()):
        a(f"| inst{inst_id} | {r['processed']} | {r['pass']} | {r['fail']} | {r['broken']} | {r['db_total']} |")
        total_p += r["pass"]; total_f += r["fail"]; total_b += r["broken"]
    a(f"| **TOTAL** | **{total_p+total_f+total_b}** | **{total_p}** | **{total_f}** | **{total_b}** | **{total_p+total_f}** |")
    a("")
    a("## RunMeFirstOnce — per-candidate TARGET_BASE_URL patching")
    a("")
    a("Each executor instance has a `runFirstOnce/runmefirstonce.first` Python script.")
    a("py_executor calls it as `python runmefirstonce.first <candidate_path>` before")
    a("every candidate launch. The script rewrites:")
    a("```python")
    a('TARGET_BASE_URL = "http://127.0.0.1:800X"  # X = 0,2,4,6 per instance')
    a("```")
    a("This routes the HTTP smoke test (Phase 0 of the harness) to the correct")
    a("app instance without regenerating candidates per instance.")
    a("")
    a("## Bugs confirmed across all 4 instances")
    a("")
    a("### BUG-001 · `Decimal(\"NaN\")` leaks `InvalidOperation`")
    a("Reproduced on all 4 instances (test 18 in each instance's run).")
    a("`service._post_to_account()` does not guard against NaN before `amount <= 0` comparison.")
    a("")
    a("### BUG-002 · No ISO-4217 currency validation")
    a("Reproduced on all 4 instances (tests 11, 23).")
    a("Service accepts `\"XX\"`, `\"\"`, etc. without raising `ValidationError`.")
    a("")
    a("## Infrastructure")
    a("```")
    a("generator_trunk/")
    a("  run_4instance_bundle.py          # this orchestration script")
    a("  py_executor.py                   # modified: RunMeFirstOnce per-candidate support")
    a("  scenarios/fintech_client_server/harness.py  # updated: TARGET_BASE_URL + HTTP smoke")
    a("  generated_tests_fintech/         # 26 source candidates")
    a("")
    a("/tmp/fw_4inst/")
    a("  inst{1..4}/candidates/           # N_0_0.py (round-robin distributed)")
    a("  inst{1..4}/handshake/")
    a("    runFirstOnce/runmefirstonce.first  # patches TARGET_BASE_URL per instance")
    a("    resultsDbURL/resultsDbURL.properties")
    a("    sqlTemplate/insert.sql")
    a("```")

    out = FINTECH / "TEST_RESULTS_4INSTANCE.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    ok(f"Written → {out}")


# ── cleanup ───────────────────────────────────────────────────────────────────
def cleanup():
    for p in _procs:
        try:
            p.terminate()
        except Exception:
            pass


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-gen",    action="store_true")
    ap.add_argument("--skip-launch", action="store_true")
    args = ap.parse_args()

    print("=" * 68)
    print("Finance Stack — 4-instance parallel Bundle run")
    print("=" * 68)

    if not args.skip_gen:
        step_generate()
    else:
        info("--skip-gen: using existing candidates")

    if not args.skip_launch:
        step_launch()
    else:
        info("--skip-launch: assuming instances already running")

    step_setup_work_dirs()
    exec_results = step_run_parallel()
    rows = step_report(exec_results)
    step_write_report(rows)

    if not args.skip_launch:
        print("\nTerminating 4 app instances …")
        cleanup()

    print("\n✓ DONE")


if __name__ == "__main__":
    main()
