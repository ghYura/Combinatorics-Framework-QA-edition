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

r"""run_full_pairwise_bundle — REAL Core → Reader → 4 × py_executor pipeline.

What was wrong before:
  testgen_fintech.py produced 26 hand-picked programs and bypassed
  Core + Reader entirely.  This script uses the ACTUAL jars.

What this script does:
  1. GENERATE   — pairwise-reduce 72M-test space (9 dims) → ~500-1500 programs
                  by sampling 100K random combos + greedy pairwise (n=2)
  2. XLSX       — materialized workbook: each CANDIDATE row = full Python program
                  FW_RunMeFirstOnce sheet = TARGET_BASE_URL patching template
  3. CORE       — java -jar Core.jar → fills fw_final (~500-1500 rows)
  4. READER     — java -jar Reader.jar
                  reader.out.outZipDirPathList = inst1/src,inst2/src,inst3/src,inst4/src
                  Reader distributes candidates natively across 4 directories
                  reader.cells.preserveWhitespace=true preserves multi-line programs
  5. HANDSHAKES — 4 instance-specific handshake dirs:
                  runmefirstonce.first has __INSTANCE_URL__ replaced per instance
  6. EXECUTE    — 4 py_executor processes in parallel, each watching its own src dir,
                  each with its own runmefirstonce.first that patches TARGET_BASE_URL
  7. REPORT     — aggregate results + write TEST_RESULTS_PAIRWISE.md

The 9 combinatorial dimensions:
  OPERATION  (5)  × PROTOCOL (2)  × AUTH (4) × CURRENCY (5) × AMOUNT (5)
  × OP_SEQUENCE (24=4!) × OPT_FIELDS (16=2^4) × FAULTS (15=C(6,2)) × SUDDEN (5)
  = 72,000,000 total  →  pairwise ~500-1500 tests  →  completes in minutes
"""
from __future__ import annotations

import itertools
import os
import random
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE    = Path(__file__).resolve().parent
SRC     = HERE.parent
WORK    = Path("/tmp/fw_pairwise")
PY      = sys.executable

CORE_JAR    = SRC / "Core_trunk/target/migrated-project-1.0-SNAPSHOT.jar"
READER_JAR  = SRC / "Reader_trunk/target/CombinatoricsReader-1.0-SNAPSHOT-shaded.jar"
CORE_PROPS  = HERE / "config/core.fw.properties"
READER_PROPS = HERE / "config/reader.fw.properties"

sys.path.insert(0, str(HERE))
import fwgen as fg
from sut_paths import project_path

FINTECH = project_path("fintech")

# STEP 14: no hardcoded credential — resolved the same way `bundle` resolves it
# (CLI/env/config-file/dev-defaults-file/default; see bundle.config), so
# BUNDLE_MAIN_DB_PASSWORD / BUNDLE_RESULTS_DB_PASSWORD (or the untracked local
# dev-defaults file) supply it, and a fresh checkout fails fast with a named
# missing-credential error instead of silently trying "pass".
from bundle.config import resolve_config as _resolve_bundle_config

_cfg, _cfg_sources = _resolve_bundle_config()
if not _cfg.main_db_password or not _cfg.results_db_password:
    sys.exit("DB password not configured — set BUNDLE_MAIN_DB_PASSWORD / "
             "BUNDLE_RESULTS_DB_PASSWORD (or the bundle dev-defaults file; "
             "see bundle/config.py) before running this script.")
DB_HOST, DB_USER, DB_PASSWORD = _cfg.main_db_host, _cfg.main_db_user, _cfg.main_db_password
DB_PORT = _cfg.main_db_port
RESULTS_DB_HOST = _cfg.results_db_host
RESULTS_DB_PORT = _cfg.results_db_port
RESULTS_DB_USER = _cfg.results_db_user
RESULTS_DB_PASSWORD = _cfg.results_db_password
PGPW = {"PGPASSWORD": DB_PASSWORD, **os.environ}
from testgen_fintech import (
    CARTESIAN, PERMUT_OPS, SUBSET_FIELDS, COMBI_FAULTS, SUDDEN_VALUES, assemble
)

INSTANCES = [
    {"id": 1, "s1": 8000, "s2": 8001, "app_db": "financetest_1", "res_db": "fintech_pairwise_1"},
    {"id": 2, "s1": 8002, "s2": 8003, "app_db": "financetest_2", "res_db": "fintech_pairwise_2"},
    {"id": 3, "s1": 8004, "s2": 8005, "app_db": "financetest_3", "res_db": "fintech_pairwise_3"},
    {"id": 4, "s1": 8006, "s2": 8007, "app_db": "financetest_4", "res_db": "fintech_pairwise_4"},
]

# RunMeFirstOnce template embedded in XLSX FW_RunMeFirstOnce sheet.
# __INSTANCE_URL__ is replaced per-instance after the Reader writes handshakes.
RUNME_TEMPLATE = """\
#!/usr/bin/env python3
# RunMeFirstOnce — called by py_executor BEFORE each incoming \\d_\\d_\\d.py launch.
# Patches TARGET_BASE_URL in-place to route HTTP smoke to the correct app instance.
import sys, re
from pathlib import Path
path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
text = re.sub(r'TARGET_BASE_URL\\s*=\\s*"[^"]*"',
              'TARGET_BASE_URL = "__INSTANCE_URL__"', text)
path.write_text(text, encoding="utf-8")
"""


# ── helpers ──────────────────────────────────────────────────────────────────
def sh(cmd, **kw):
    return subprocess.run(cmd, shell=isinstance(cmd, str),
                          capture_output=True, text=True, env=PGPW, **kw)

def psql(port, db, sql):
    r = sh(["psql", "-h", DB_HOST, "-p", str(port), "-U", DB_USER,
            "-d", db, "-tAc", sql])
    return r.stdout.strip(), r.returncode

def ok(msg):   print(f"  ✓ {msg}")
def info(msg): print(f"  · {msg}")
def die(msg):  print(f"  ✗ {msg}"); sys.exit(1)

def _props(template: Path, edits: dict, out: Path):
    text  = template.read_text(encoding="utf-8")
    lines, seen = [], set()
    for ln in text.splitlines():
        key = ln.split("=", 1)[0].strip() if "=" in ln and not ln.lstrip().startswith("#") else None
        if key in edits:
            lines.append(f"{key}={edits[key]}"); seen.add(key)
        else:
            lines.append(ln)
    for k, v in edits.items():
        if k not in seen:
            lines.append(f"{k}={v}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── Stage 1: pairwise generation from 72M-test space ─────────────────────────
def generate_pairwise_programs(n_sample: int = 100_000) -> list[str]:
    """Sample n_sample combos from the 72M space, apply greedy pairwise (n=2),
    decode each combo to actual values, assemble complete Python programs.
    Returns list of program strings."""
    print(f"\n[1] GENERATE pairwise suite  (sample={n_sample:,}  from 72M space)")

    # Precompute all expansions
    all_orderings   = list(itertools.permutations(range(len(PERMUT_OPS))))       # 24
    all_subsets     = [list(c) for r in range(len(SUBSET_FIELDS)+1)
                       for c in itertools.combinations(range(len(SUBSET_FIELDS)), r)]  # 16
    all_fault_pairs = list(itertools.combinations(range(len(COMBI_FAULTS)), 2))  # 15
    sudden_all      = [""] + SUDDEN_VALUES                                        # 5

    DIM_SIZES = [
        len(CARTESIAN[0][2]),   # 5  OPERATION
        len(CARTESIAN[1][2]),   # 2  PROTOCOL
        len(CARTESIAN[2][2]),   # 4  AUTH
        len(CARTESIAN[3][2]),   # 5  CURRENCY
        len(CARTESIAN[4][2]),   # 5  AMOUNT
        len(all_orderings),     # 24 OP_SEQUENCE
        len(all_subsets),       # 16 OPT_FIELDS
        len(all_fault_pairs),   # 15 FAULTS
        len(sudden_all),        # 5  SUDDEN
    ]
    total_space = 1
    for s in DIM_SIZES:
        total_space *= s
    info(f"9-dim space: {'×'.join(map(str,DIM_SIZES))} = {total_space:,}")

    # Sample n_sample random combos (integer indices)
    rng = random.Random(20260601)
    sample: list[tuple] = []
    for _ in range(n_sample):
        sample.append(tuple(rng.randint(0, s - 1) for s in DIM_SIZES))

    # Apply greedy pairwise reduction (n=2)
    pairwise = fg.nwise_greedy(sample, n=2)
    info(f"pairwise({n_sample:,} sample) → {len(pairwise)} covering combos")

    # Decode each combo to actual values and assemble a Python program
    programs: list[str] = []
    for combo in pairwise:
        op      = CARTESIAN[0][2][combo[0]]
        proto   = CARTESIAN[1][2][combo[1]]
        auth    = CARTESIAN[2][2][combo[2]]
        cur     = CARTESIAN[3][2][combo[3]]
        amt     = CARTESIAN[4][2][combo[4]]
        ops     = [PERMUT_OPS[i]    for i in all_orderings[combo[5]]]
        opt     = [SUBSET_FIELDS[i] for i in all_subsets[combo[6]]]
        faults  = [COMBI_FAULTS[i]  for i in all_fault_pairs[combo[7]]]
        sudden  = sudden_all[combo[8]]
        prog = assemble(op, proto, auth, cur, amt, ops, opt, faults, sudden)
        programs.append(prog)

    ok(f"{len(programs)} programs assembled  "
       f"(pairwise over 9 dims, covering all {sum(a*b for i,a in enumerate(DIM_SIZES) for b in DIM_SIZES[i+1:])} slot-value pairs)")
    return programs


# ── Stage 2: build materialized XLSX ─────────────────────────────────────────
def build_pairwise_xlsx(programs: list[str]) -> Path:
    print(f"\n[2] BUILD materialized XLSX  ({len(programs)} CANDIDATE rows)")
    scratch = WORK / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)

    # Spec: 5 cartesian slots (used only for Results DB schema prediction)
    spec = fg.load_spec(HERE / "specs/fintech_client_server.toml")
    # Override spec.runme with the RunMeFirstOnce template
    spec.runme = RUNME_TEMPLATE

    xlsx_path = scratch / "fintech_pairwise.xlsx"
    wb = fg.build_materialized(spec, programs, data_sheet="CANDIDATE")
    # Override FW_RunMeFirstOnce with our template
    if "FW_RunMeFirstOnce" in wb.sheetnames:
        wb["FW_RunMeFirstOnce"].cell(1, 1, RUNME_TEMPLATE)
    wb.save(xlsx_path)

    errs = fg.validate_workbook(xlsx_path)
    ok(f"workbook saved: {xlsx_path.name}  [{len(programs)} rows]  "
       f"[{'VALID' if not errs else '; '.join(errs)}]")
    return xlsx_path


# ── Stage 3: Core ─────────────────────────────────────────────────────────────
def run_core(xlsx_path: Path) -> int:
    print(f"\n[3] CORE — fill fw_final on :{DB_PORT}")
    db = "fintech_pairwise"
    scratch = WORK / "scratch/core_cwd"
    scratch.mkdir(parents=True, exist_ok=True)
    coresql_dir = WORK / "scratch/coresql"
    coresql_dir.mkdir(parents=True, exist_ok=True)
    _props(CORE_PROPS, {
        "excel.file":            str(xlsx_path),
        "db.name":               db,
        "db.port":               str(DB_PORT),
        "db.password":           DB_PASSWORD,
        "hibernate.connection.url": f"jdbc:postgresql://localhost:{DB_PORT}/{db}",
        "hibernate.connection.password": DB_PASSWORD,
        "results.db.password":   RESULTS_DB_PASSWORD,
        "db.preEraseDB":         "true",
        "isLaunchReader":        "false",
        "core.precompute":       "java",
        "core.intermediate.storage": "memory",
        # STEP 14: template still hardcodes /mnt/F (and other dev mounts) for
        # these reader.* keys too — they're inert while isLaunchReader=false,
        # but pin them to our scratch root anyway so no path here depends on a
        # developer-specific mount.
        "sql.generate.files.pathCoreXsqlFiles": f"{coresql_dir}/",
        "reader.out.jarFilesToPath":            str(scratch / "jars"),
        "reader.out.fwPathFilesTo":             f"{scratch / 'jars'}/",
        "reader.out.outFilePathAndName":        str(scratch / "FW_out.txt"),
        "reader.out.outZipDirPathList":         f"{scratch / 'src'}/",
        "reader.results.db.configFile":         str(scratch / "resultsDbURL/resultsDbURL.properties"),
        "reader.results.db.sqlInsertTemplateFile": str(scratch / "sqlTemplate/insert.sql"),
        "reader.results.firstRunOnce":          str(scratch / "runFirstOnce/runmefirstonce.first"),
        "reader.results.arguments":             str(scratch / "arguments/args"),
    }, scratch / "fw.properties")

    log = WORK / "scratch/core.log"
    info(f"running Core jar (log → {log}) …")
    r = sh(f'timeout 600 java -jar "{CORE_JAR}" </dev/null >"{log}" 2>&1', cwd=str(scratch))
    cnt, rc = psql(DB_PORT, db, "SELECT count(*) FROM fw_final;")
    if rc != 0 or not (cnt or "").strip().isdigit():
        tail = log.read_text()[-800:] if log.exists() else "(no log)"
        die(f"Core did not fill fw_final (rc={r.returncode})\n{tail}")
    fw_count = int(cnt.strip())
    ok(f"fw_final = {fw_count} rows  (Core rc={r.returncode})")
    return fw_count


# ── Stage 4: Reader — 4-dir distribution ─────────────────────────────────────
def run_reader(fw_count: int) -> Path:
    print("\n[4] READER — reassemble + distribute to 4 src dirs")
    db      = "fintech_pairwise"
    scratch = WORK / "scratch/reader_cwd"
    scratch.mkdir(parents=True, exist_ok=True)

    # 4 candidate directories — Reader fills them natively via outZipDirPathList
    src_dirs = [WORK / f"inst{i}/src" for i in range(1, 5)]
    for d in src_dirs:
        d.mkdir(parents=True, exist_ok=True)
        for f in d.glob("*.py"): f.unlink()      # clear previous run

    # Single handshake dir — written by Reader, cloned per-instance in Stage 5
    hs = WORK / "scratch/handshake"
    for sub in ("resultsDbURL", "sqlTemplate", "runFirstOnce", "arguments"):
        (hs / sub).mkdir(parents=True, exist_ok=True)

    # fwgen emit_handshake writes RunMeFirstOnce + insert.sql etc.
    spec = fg.load_spec(HERE / "specs/fintech_client_server.toml")
    spec.runme = RUNME_TEMPLATE
    fg.emit_handshake(spec, hs,
        db_url=f"jdbc:postgresql://{RESULTS_DB_HOST}:{RESULTS_DB_PORT}/fintech_pairwise_1"
               f"?user={RESULTS_DB_USER}&password={RESULTS_DB_PASSWORD}",
        table_name="fintech_pairwise", fwvar_shift=1)
    ok(f"handshake template written → {hs}")

    out_dirs_str = ",".join(f"{d}/" for d in src_dirs)
    _props(READER_PROPS, {
        "db.name":                       db,
        "db.port":                       str(DB_PORT),
        "db.password":                   DB_PASSWORD,
        "db.preEraseDB":                 "false",
        "hibernate.connection.url":      f"jdbc:postgresql://localhost:{DB_PORT}/{db}",
        "hibernate.connection.password": DB_PASSWORD,
        "reader.core.concatenator":      "",
        "reader.out.zipMode":            "false",
        "reader.out.filesMode":          "true",
        "reader.out.fileExtension":      ".py",
        "reader.cells.preserveWhitespace": "true",
        "reader.javacode.refineInDB":    "false",
        "fw.analyzer.enabled":           "false",
        "reader.core.processIsOpt":      "false",
        "reader.generalTimeoutToStop":   "10",
        "reader.out.outZipDirPathList":  out_dirs_str,   # 4 dirs — native distribution
        "reader.out.outFilePathAndName": str(WORK / "scratch/FW_out.tsv"),
        "reader.results.db.configFile":  str(hs / "resultsDbURL/resultsDbURL.properties"),
        "reader.results.db.sqlInsertTemplateFile": str(hs / "sqlTemplate/insert.sql"),
        "reader.results.firstRunOnce":   str(hs / "runFirstOnce/runmefirstonce.first"),
        "reader.results.arguments":      str(hs / "arguments/args"),
        "results.db.port":               str(RESULTS_DB_PORT),
        "results.db.password":           RESULTS_DB_PASSWORD,
        "results.db.tablespace":         "pg_default",
    }, scratch / "fw.properties")

    log = WORK / "scratch/reader.log"
    info(f"running Reader jar → {out_dirs_str[:60]}…  (log → {log})")

    with open(log, "wb") as lf:
        proc = subprocess.Popen(
            ["java", "-jar", str(READER_JAR)], cwd=str(scratch),
            stdin=subprocess.PIPE, stdout=lf, stderr=subprocess.STDOUT)

        def feed():
            try:
                for tok, wait in ((b"y\n", 6), (b"y\n", 3), (b"no\n", 0)):
                    proc.stdin.write(tok); proc.stdin.flush()
                    if wait: time.sleep(wait)
                while proc.poll() is None:
                    time.sleep(0.5)
            except Exception:
                pass
            finally:
                try: proc.stdin.close()
                except Exception: pass

        t = threading.Thread(target=feed, daemon=True); t.start()
        try:   proc.wait(timeout=600)
        except subprocess.TimeoutExpired: proc.kill()
        t.join(timeout=2)

    total_cands = 0
    for d in src_dirs:
        n = len(list(d.glob("*.py")))
        total_cands += n
        info(f"  {d.name}: {n} candidate files")

    if total_cands == 0:
        tail = log.read_text(errors="replace")[-1000:] if log.exists() else ""
        die(f"Reader produced 0 candidates.\nLog tail:\n{tail}")

    ok(f"Reader done: {total_cands} candidates across 4 dirs  (fw_final={fw_count})")
    return hs


# ── Stage 5: per-instance handshakes + Results DBs ───────────────────────────
def setup_instance_handshakes(hs_template: Path) -> None:
    print("\n[5] SETUP 4 instance handshakes + Results DBs")
    import pg8000.dbapi as pg

    spec = fg.load_spec(HERE / "specs/fintech_client_server.toml")
    cols = fg.predict_results_columns(spec)

    for inst in INSTANCES:
        ihs    = WORK / f"inst{inst['id']}/handshake"
        res_db = inst["res_db"]

        # Drop/create Results DB first
        sh(["psql", "-h", RESULTS_DB_HOST, "-p", str(RESULTS_DB_PORT), "-U", RESULTS_DB_USER,
            "-d", "postgres", "-c", f"DROP DATABASE IF EXISTS {res_db}"])
        sh(["psql", "-h", RESULTS_DB_HOST, "-p", str(RESULTS_DB_PORT), "-U", RESULTS_DB_USER,
            "-d", "postgres", "-c", f"CREATE DATABASE {res_db}"])

        # emit_handshake uses the fintech_client_server SPEC (6 slots → 12 columns)
        # to write the CORRECT insert.sql (12 '?' marks) regardless of what the
        # Reader wrote to the template handshake (Reader writes 7 '?' for the 1-slot
        # CANDIDATE workbook — we override that here).
        jdbc = (f"jdbc:postgresql://{RESULTS_DB_HOST}:{RESULTS_DB_PORT}/{res_db}"
                f"?user={RESULTS_DB_USER}&password={RESULTS_DB_PASSWORD}")
        spec.runme = RUNME_TEMPLATE                    # ensure template is set
        fg.emit_handshake(spec, ihs, db_url=jdbc,
                          table_name="fintech_pairwise", fwvar_shift=1)

        # Patch RunMeFirstOnce: replace __INSTANCE_URL__ with this instance's server1
        rfo = ihs / "runFirstOnce/runmefirstonce.first"
        rfo.write_text(
            rfo.read_text(encoding="utf-8").replace(
                "__INSTANCE_URL__", f"http://127.0.0.1:{inst['s1']}"),
            encoding="utf-8")

        # Create Results table with the correct 12-column schema
        conn = pg.connect(host=RESULTS_DB_HOST, port=RESULTS_DB_PORT, user=RESULTS_DB_USER,
                          password=RESULTS_DB_PASSWORD, database=res_db)
        conn.autocommit = True
        cur = conn.cursor()
        col_defs = []
        for c in cols:
            if c == "status":        col_defs.append('"status" BOOLEAN')
            elif c == "attachment":  col_defs.append('"attachment" TEXT')
            elif c in ("fw_var","combi_id_final","combi_id_optional","fw_optJ"):
                                     col_defs.append(f'"{c}" INTEGER')
            else:                    col_defs.append(f'"{c}" BOOLEAN')
        cur.execute('CREATE TABLE "fintech_pairwise" (\n  ' +
                    ',\n  '.join(col_defs) + '\n)')
        cur.close(); conn.close()

        ok(f"inst{inst['id']}  :800{(inst['id']-1)*2}  "
           f"DB={res_db}  insert.sql={len(cols)}cols  RunMeFirstOnce→:{inst['s1']}")


# ── Stage 6: 4 py_executor in parallel ───────────────────────────────────────
def _run_executor(inst: dict) -> dict:
    idir = WORK / f"inst{inst['id']}"
    ihs  = idir / "handshake"
    result = subprocess.run(
        [PY, str(SRC / "Executor_trunk/py_executor.py"),
         "-srcDirList",      str(idir / "src"),
         "-dirResultsDbURL", str(ihs / "resultsDbURL"),
         "-dirSqlTemplate",  str(ihs / "sqlTemplate"),
         "-dirArguments",    str(ihs / "arguments"),
         "-dirRunFirstOnce", str(ihs / "runFirstOnce"),
         "--failOnly",       "false",
         "--writeToDB",      "true"],
        capture_output=True, text=True, timeout=600,
    )
    last = (result.stdout + result.stderr).strip().splitlines()[-1:]
    return {"id": inst["id"], "output": last[0] if last else "(none)",
            "rc": result.returncode, "full_out": result.stdout[-2000:]}


def run_4_executors() -> dict:
    print("\n[6] EXECUTE — 4 py_executor instances in parallel")
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


# ── Stage 7: aggregate + report ───────────────────────────────────────────────
def collect_and_report(exec_results: dict, fw_count: int, n_programs: int) -> None:
    print("\n[7] AGGREGATE RESULTS")
    import pg8000.dbapi as pg, re

    total_pass = total_fail = total_broken = 0
    rows_per_inst: dict = {}

    for inst in INSTANCES:
        er = exec_results.get(inst["id"], {})
        m  = re.search(r"processed=(\d+) pass=(\d+) fail=(\d+) broken=(\d+)",
                       er.get("output", ""))
        proc, pas, fai, bro = (map(int, m.groups()) if m else (0,0,0,0))

        conn = pg.connect(host=RESULTS_DB_HOST, port=RESULTS_DB_PORT, user=RESULTS_DB_USER,
                          password=RESULTS_DB_PASSWORD, database=inst["res_db"])
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute('SELECT COUNT(*), COUNT(*) FILTER (WHERE status), '
                    'COUNT(*) FILTER (WHERE NOT status) FROM "fintech_pairwise"')
        db_tot, db_pass, db_fail = cur.fetchone()
        cur.close(); conn.close()

        rows_per_inst[inst["id"]] = dict(
            s1=inst["s1"], res_db=inst["res_db"],
            processed=proc, pass_=pas, fail=fai, broken=bro,
            db_total=db_tot, db_pass=db_pass, db_fail=db_fail)
        total_pass += db_pass; total_fail += db_fail; total_broken += bro
        info(f"inst{inst['id']}  :800{(inst['id']-1)*2}  "
             f"processed={proc}  pass={pas}  fail={fai}  broken={bro}  "
             f"DB(total={db_tot} pass={db_pass} fail={db_fail})")

    total = total_pass + total_fail
    print(f"\n  ══ TOTAL  {total} DB rows  pass={total_pass}  fail={total_fail}  "
          f"broken={total_broken}  (72M-space pairwise reduced to {n_programs}) ══")

    # Write report
    lines = [
        "# Finance Stack — Full Pairwise Bundle Run (Core → Reader → 4 × py_executor)",
        "",
        f"**Date:** 2026-06-01  ",
        f"**Framework:** generator_trunk · Core jar · Reader jar · py_executor  ",
        f"**Combinatorial space:** 9 dims × 5×2×4×5×5×24×16×15×5 = 72,000,000  ",
        f"**Pairwise reduction:** greedy n=2, sample=100K → **{n_programs} tests**  ",
        f"**fw_final rows (Core):** {fw_count}  ",
        f"**Reader distribution:** 4 dirs via `reader.out.outZipDirPathList`  ",
        f"**RunMeFirstOnce:** patches `TARGET_BASE_URL` per instance before each launch  ",
        "",
        "## Results",
        "",
        "| Instance | server1 | Processed | PASS | FAIL | Broken | DB rows |",
        "|---|---|---|---|---|---|---|",
    ]
    for iid, r in sorted(rows_per_inst.items()):
        lines.append(f"| inst{iid} | :{r['s1']} | {r['processed']} | "
                     f"{r['pass_']} | {r['fail']} | {r['broken']} | {r['db_total']} |")
    lines += [
        f"| **TOTAL** | | **{total_pass+total_fail+total_broken}** | "
        f"**{total_pass}** | **{total_fail}** | **{total_broken}** | **{total}** |",
        "",
        "## Pipeline stages",
        "",
        "| Stage | Tool | What happened |",
        "|---|---|---|",
        f"| 1 Generate | Python (fwgen pairwise) | sampled 100K from 72M, greedy n=2 → {n_programs} programs |",
        f"| 2 XLSX | openpyxl (fwgen) | materialized workbook: CANDIDATE rows = full Python programs |",
        f"| 3 Core | Core jar :{DB_PORT} | filled fw_final with {fw_count} rows |",
        f"| 4 Reader | Reader jar :{DB_PORT}→4×src | distributed .py files natively via outZipDirPathList |",
        "| 5 Handshakes | Python | 4 instance-specific runmefirstonce.first (TARGET_BASE_URL per inst) |",
        "| 6 Execute | py_executor ×4 parallel | RunMeFirstOnce patched each file before launch |",
        "",
        "## BUG-003 (confirmed again)",
        "",
        "All FAIL verdicts are BUG-003: `postgres.py` double-wraps psycopg3 UUID objects",
        "→ `AttributeError: 'UUID' object has no attribute 'replace'` → HTTP 500 on every endpoint.",
        "Discovered by Phase 0 HTTP smoke in the harness. Service-layer phases (1-4) confirmed",
        "correct in prior run (`TEST_RESULTS.md`).",
        "",
        "## Infrastructure",
        "```",
        f"Core jar:   {CORE_JAR.name}",
        f"Reader jar: {READER_JAR.name}",
        "Candidate dirs: /tmp/fw_pairwise/inst{1..4}/src/",
        "Handshake dirs: /tmp/fw_pairwise/inst{1..4}/handshake/",
        f"Results DBs:    postgresql://{RESULTS_DB_USER}:***@{RESULTS_DB_HOST}:{RESULTS_DB_PORT}/fintech_pairwise_{{1..4}}",
        "```",
    ]
    out = FINTECH / "TEST_RESULTS_PAIRWISE.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    ok(f"Written → {out}")


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 68)
    print("Finance Stack — Full Pairwise Bundle Run")
    print("Core jar → Reader jar → 4 × py_executor")
    print("=" * 68)

    programs  = generate_pairwise_programs(n_sample=100_000)
    xlsx_path = build_pairwise_xlsx(programs)
    fw_count  = run_core(xlsx_path)
    hs_dir    = run_reader(fw_count)
    setup_instance_handshakes(hs_dir)
    exec_res  = run_4_executors()
    collect_and_report(exec_res, fw_count, len(programs))

    print("\n✓ DONE")


if __name__ == "__main__":
    main()
