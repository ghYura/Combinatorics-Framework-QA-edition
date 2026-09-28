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


"""Owned, isolated PostgreSQL fixture and offline client image for D14b (setup, export, logs, storage).

    python fixture.py setup                          # new stamp: network, volume, fixture, bootstrap, client image, probe
    python fixture.py export --stamp S --out DIR     # rows, catalog and hashes (superuser via docker exec; not campaign SQL)
    python fixture.py logs --stamp S --out FILE      # the fixture server's SQL log (docker logs)
    python fixture.py storage --stamp S              # sizes of everything this example created

Everything is created fresh and owned (label as0927.owner=implementer-d14b), never removed:
  network    as0927_d14b_net_<stamp>       docker network create --internal (no route out)
  volume     as0927_d14b_sqldata_<stamp>   PGDATA
  container  as0927_d14b_sql_<stamp>       cached postgres:16.9-alpine, no published ports, 256 MiB,
                                            shared_buffers 16MB, max_connections 20, log_statement=all
  database   as0927_d14b_sql_<stamp>       inside that container only; bootstrap DDL runs there once
  role       as0927_d14b_reader            SELECT on fixture.items/tags, default_transaction_read_only=on
  image      as0927_d14b_client:<stamp>    cached python:3-slim + pure-Python pg8000 1.31.5, scramp 1.4.17,
                                            asn1crypto 1.5.1, python-dateutil 2.9.0.post0, six 1.17.0 copied from
                                            this workspace's venv (docker create/cp/commit; nothing downloaded)
The probe runs one small candidate through the Framework's own Executor sandbox (networked-api-probe,
allowlist = the fixture only) before any campaign. Shared servers 5433/5432 are never touched here.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = Path(__file__).resolve().parents[2]
VENV_SITE = Path(__import__("pg8000").__file__).resolve().parent.parent      # site-packages of the running (venv) interpreter
EVIDENCE = HERE / "evidence"
PG_IMAGE, PY_IMAGE = "postgres:16.9-alpine", "python:3-slim"


def _local_image_id(ref):
    """ID of the locally cached image (recorded in setup.json; never pulled). None when it is absent."""
    r = subprocess.run(["docker", "image", "inspect", "--format", "{{.Id}}", ref], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


PG_IMAGE_ID, PY_IMAGE_ID = _local_image_id(PG_IMAGE), _local_image_id(PY_IMAGE)
PACKAGES = {"pg8000": "1.31.5", "scramp": "1.4.17", "asn1crypto": "1.5.1", "python_dateutil": "2.9.0.post0", "six": "1.17.0"}
MODULE_FILES = {"pg8000": "pg8000", "scramp": "scramp", "asn1crypto": "asn1crypto", "python_dateutil": "dateutil", "six": "six.py"}


def package_files():
    """The pure-Python modules plus their dist-info folders (licences, versions) as installed in this venv."""
    out = []
    for dist, module in MODULE_FILES.items():
        infos = sorted(VENV_SITE.glob(f"{dist}-*.dist-info"))
        if len(infos) != 1 or not (VENV_SITE / module).exists():
            raise SystemExit(f"{dist} is not installed once in {VENV_SITE}")
        out += [module, infos[0].name]
    return out
READER = "as0927_d14b_reader"
LABELS = ["--label", "as0927.owner=implementer-d14b"]
LOG_PREFIX = "%m [%p] user=%u db=%d app=%a vxid=%v "
SERVER_ARGS = ["-c", "shared_buffers=16MB", "-c", "max_connections=20", "-c", "log_statement=all", "-c", "log_connections=on",
               "-c", "log_disconnections=on", "-c", f"log_line_prefix={LOG_PREFIX}", "-c", "log_timezone=UTC"]
RUNNER = ("import runpy,sys\n"
          "ns = runpy.run_path(sys.argv[1], run_name='__main__')\n"
          "print('__FWV__ %d %d' % (int(ns.get('FW_VAR', -999)), int(ns.get('FW_CUSTOM_VAR', -999))))\n")


def names(stamp):
    return {"network": f"as0927_d14b_net_{stamp}", "volume": f"as0927_d14b_sqldata_{stamp}", "container": f"as0927_d14b_sql_{stamp}",
            "database": f"as0927_d14b_sql_{stamp}", "image": f"as0927_d14b_client:{stamp}", "builder": f"as0927_d14b_clientbuild_{stamp}"}


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def now():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def docker(*args, check=True, input_=None, log=None):
    r = subprocess.run(["docker", *args], capture_output=True, text=True, input=input_)
    if log is not None:
        log.append({"argv": ["docker", *[("<redacted>" if a.startswith("POSTGRES_PASSWORD=") else a) for a in args]],
                    "rc": r.returncode, "at": now()})
    if check and r.returncode != 0:
        raise SystemExit(f"docker {' '.join(args[:3])} failed: {r.stderr.strip()}")
    return r


def psql(container, db, sql, *, log=None, single=False):
    args = ["exec", "-i", container, "psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", db, "-At", "-F", "\t"]
    return docker(*args, *(["--single-transaction"] if single else []), input_=sql, log=log).stdout


def sql_literal(v):
    return "NULL" if v is None else ("TRUE" if v is True else "FALSE" if v is False else str(v) if isinstance(v, int) else "'" + v + "'")


def bootstrap_sql(db):
    fx = json.loads((HERE / "architect-derived.json").read_text())["fixture"]
    items = ", ".join("(" + ", ".join(sql_literal(r[k]) for k in ("id", "grp", "val", "flag")) + ")" for r in fx["items"])
    tags = ", ".join(f"({t['item_id']}, {sql_literal(t['tag'])})" for t in fx["tags"])
    return "\n".join([
        "CREATE SCHEMA fixture;",
        "CREATE TABLE fixture.items (id integer PRIMARY KEY, grp text NOT NULL, val integer NULL, flag boolean NULL);",
        "CREATE TABLE fixture.tags (item_id integer REFERENCES fixture.items(id), tag text NOT NULL);",
        f"INSERT INTO fixture.items (id, grp, val, flag) VALUES {items};",
        f"INSERT INTO fixture.tags (item_id, tag) VALUES {tags};",
        f"CREATE ROLE {READER} LOGIN PASSWORD 'pass';",
        f"ALTER ROLE {READER} SET default_transaction_read_only = on;",
        f"ALTER ROLE {READER} SET statement_timeout = '5s';",
        f"ALTER ROLE {READER} SET idle_in_transaction_session_timeout = '10s';",
        f"REVOKE ALL ON DATABASE {db} FROM PUBLIC;",
        f"GRANT CONNECT ON DATABASE {db} TO {READER};",
        f"GRANT USAGE ON SCHEMA fixture TO {READER};",
        f"GRANT SELECT ON fixture.items, fixture.tags TO {READER};", ""])


CATALOG_SQL = """SELECT 'index', indexrelid::regclass::text FROM pg_index WHERE indrelid IN ('fixture.items'::regclass, 'fixture.tags'::regclass)
UNION ALL SELECT 'trigger', tgname FROM pg_trigger WHERE tgrelid IN ('fixture.items'::regclass, 'fixture.tags'::regclass)
UNION ALL SELECT 'table', table_schema || '.' || table_name FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
UNION ALL SELECT 'grant', grantee || ':' || table_name || ':' || privilege_type FROM information_schema.role_table_grants WHERE table_schema = 'fixture'
UNION ALL SELECT 'role_setting', coalesce(array_to_string(setconfig, ','), '') FROM pg_db_role_setting WHERE setrole = (SELECT oid FROM pg_roles WHERE rolname = 'as0927_d14b_reader')
UNION ALL SELECT 'reader', rolname || ':super=' || rolsuper || ':createdb=' || rolcreatedb || ':createrole=' || rolcreaterole FROM pg_roles WHERE rolname = 'as0927_d14b_reader'
UNION ALL SELECT 'setting', name || '=' || setting FROM pg_settings WHERE name IN ('shared_buffers', 'max_connections', 'log_statement', 'server_version')
ORDER BY 1, 2;
"""


def export(stamp, out: Path, label: str):
    n = names(stamp)
    out.mkdir(parents=True, exist_ok=True)
    items = psql(n["container"], n["database"], "COPY (SELECT id, grp, val, flag FROM fixture.items ORDER BY id) TO STDOUT WITH (FORMAT csv, HEADER, NULL 'NULL');")
    tags = psql(n["container"], n["database"], "COPY (SELECT item_id, tag FROM fixture.tags ORDER BY item_id, tag) TO STDOUT WITH (FORMAT csv, HEADER, NULL 'NULL');")
    catalog = psql(n["container"], n["database"], CATALOG_SQL)
    version = psql(n["container"], n["database"], "SELECT version();").strip()
    (out / f"items-{label}.csv").write_text(items)
    (out / f"tags-{label}.csv").write_text(tags)
    (out / f"catalog-{label}.tsv").write_text(catalog)
    doc = {"label": label, "at": now(), "container": n["container"], "database": n["database"], "version": version,
           "items_sha256": sha256(items.encode()), "tags_sha256": sha256(tags.encode()), "catalog_sha256": sha256(catalog.encode()),
           "rows": {"items": len(items.splitlines()) - 1, "tags": len(tags.splitlines()) - 1}}
    (out / f"export-{label}.json").write_text(json.dumps(doc, indent=2) + "\n")
    return doc


def fixture_rows_from_export(items_csv, tags_csv):
    """Parse the exported CSV back to the frozen fixture's JSON form (for the equality check)."""
    conv = lambda v, kind: None if v == "NULL" else int(v) if kind == "int" else {"t": True, "f": False}[v] if kind == "bool" else v
    items = [dict(zip(("id", "grp", "val", "flag"), (conv(a, "int"), conv(b, "text"), conv(c, "int"), conv(d, "bool"))))
             for a, b, c, d in (l.split(",") for l in items_csv.splitlines()[1:])]
    tags = [{"item_id": int(a), "tag": b} for a, b in (l.split(",") for l in tags_csv.splitlines()[1:])]
    return {"items": items, "tags": tags}


def storage(stamp):
    n = names(stamp)
    sizes = {}
    for key in ("container", "builder"):
        r = docker("container", "inspect", "--size", "--format", "{{.SizeRw}}", n[key], check=False)
        sizes[f"{key}_writable_bytes"] = int(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip().isdigit() else None
    r = docker("exec", n["container"], "du", "-sb", "/var/lib/postgresql/data", check=False)
    sizes["volume_pgdata_bytes"] = int(r.stdout.split()[0]) if r.returncode == 0 else None
    img = docker("image", "inspect", "--format", "{{.Size}}", n["image"], check=False)
    base = docker("image", "inspect", "--format", "{{.Size}}", PY_IMAGE_ID, check=False)
    if img.returncode == 0 and base.returncode == 0:
        sizes["client_image_total_bytes"] = int(img.stdout.strip())
        sizes["client_image_new_bytes"] = int(img.stdout.strip()) - int(base.stdout.strip())
    sizes["new_docker_bytes"] = sum(v for k, v in sizes.items() if v and k in ("container_writable_bytes", "builder_writable_bytes",
                                                                              "volume_pgdata_bytes", "client_image_new_bytes"))
    return sizes


def build_client(stamp, log):
    n = names(stamp)
    with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as tmp:
        stage = Path(tmp) / "site-packages"
        stage.mkdir()
        files = {}
        for name in package_files():
            src = VENV_SITE / name
            if src.is_dir():
                shutil.copytree(src, stage / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            else:
                shutil.copy2(src, stage / name)
        for f in sorted(stage.rglob("*")):
            if f.is_file():
                files[str(f.relative_to(stage))] = sha256(f.read_bytes())
        if any(f.endswith((".so", ".pyd")) for f in files):
            raise SystemExit("a compiled extension would be copied; only pure-Python packages are allowed")
        docker("create", "--name", n["builder"], "--network", "none", *LABELS, "--label", f"as0927.stamp={stamp}", PY_IMAGE_ID, "true", log=log)
        site = docker("run", "--rm", "--network", "none", PY_IMAGE_ID, "python", "-c",
                      "import sysconfig; print(sysconfig.get_paths()['purelib'])").stdout.strip()      # asked from the image itself
        docker("cp", f"{stage}/.", f"{n['builder']}:{site}/", log=log)
    docker("commit", "--change", "LABEL as0927.owner=implementer-d14b", "--change", f"LABEL as0927.stamp={stamp}",
           n["builder"], n["image"], log=log)
    image_id = docker("image", "inspect", "--format", "{{.Id}}", n["image"]).stdout.strip()
    check = docker("run", "--rm", "--network", "none", n["image"], "python", "-c",
                   "import importlib.metadata as m, pg8000, scramp, asn1crypto, dateutil, six, sys; "
                   "print(sys.version.split()[0], {p: m.version(p) for p in ('pg8000','scramp','asn1crypto','python-dateutil','six')})", log=log)
    manifest = {"image": n["image"], "image_id": image_id, "base_image_id": PY_IMAGE_ID, "builder_container": n["builder"],
                "site_packages": site, "files_sha256": files, "files_manifest_sha256": sha256(json.dumps(files, sort_keys=True).encode()),
                "driver_import_check": check.stdout.strip()}
    if check.returncode != 0 or "'pg8000': '" not in check.stdout:           # installed versions are recorded, not pinned
        raise SystemExit(f"driver import check failed: {check.stdout} {check.stderr}")
    return manifest


PROBE = '''import json, os, socket
import pg8000, pg8000.native
fx = os.environ["D14B_FIXTURE"]
out = {"pg8000": pg8000.__version__, "fixture": fx}
con = pg8000.native.Connection(user="as0927_d14b_reader", host=fx, database=fx, port=5432, password="pass", timeout=10,
                               application_name="d14b:probe")
con.run("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
out["provenance"] = con.run("SELECT current_database(), current_user, current_setting('transaction_isolation'), "
                            "current_setting('transaction_read_only'), version()")[0]
out["counts"] = con.run("SELECT (SELECT count(*) FROM fixture.items), (SELECT count(*) FROM fixture.tags)")[0]
con.run("COMMIT")
try:
    con.run("CREATE TABLE fixture.probe_write (i integer)")
    out["write_refused"] = False
except Exception as exc:
    out["write_refused"] = str(exc)[:160]
con.close()
try:
    socket.getaddrinfo("example.com", 443)
    out["external_dns"] = "resolved"
except OSError as exc:
    out["external_dns"] = "blocked: " + type(exc).__name__
print("D14B_PROBE " + json.dumps(out))
FW_VAR = 0
FW_CUSTOM_VAR = 0
'''


def framework_sandbox(fixture, image):
    """The Executor's own container sandbox under networked-api-probe with the fixture as the only target."""
    sys.path.insert(0, str(REPO / "generator_trunk"))
    sys.path.insert(0, str(REPO / "Executor_trunk"))
    from bundle.policy import policy_to_dict, resolve_policy, with_env_allowlist, with_network_allowlist
    import sandbox as sbx
    policy = with_env_allowlist(with_network_allowlist(resolve_policy("networked-api-probe"), [fixture]), ["D14B_FIXTURE"])
    os.environ["D14B_FIXTURE"] = fixture
    doc = dict(policy_to_dict(policy))
    return sbx.build_sandbox(doc, runner=RUNNER, host_python=sys.executable, image=image), doc


def run_sandboxed(fixture, image, path: Path):
    box, doc = framework_sandbox(fixture, image)
    try:
        attached = box.provision()
        res = box.run(path, [])
        return {"attached_targets": attached, "describe": box.describe(), "policy": doc, "exit_code": res.returncode,
                "timed_out": res.timed_out, "stdout": res.stdout, "stderr_tail": (res.stderr or "")[-800:], "spawn_error": res.spawn_error}
    finally:
        box.close()


def setup():
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dt%H%M%Sz")
    n = names(stamp)
    out = EVIDENCE / f"fixture-{stamp}"
    if out.exists():
        raise SystemExit(f"{out} exists")
    log = []
    for kind, ref, want in (("image", PG_IMAGE, PG_IMAGE_ID), ("image", PY_IMAGE, PY_IMAGE_ID)):
        got = docker("image", "inspect", "--format", "{{.Id}}", ref).stdout.strip()
        if got != want:
            raise SystemExit(f"cached {ref} is {got}, expected {want}; nothing is pulled")
    for key in ("network", "volume", "container", "builder"):
        kind = {"network": "network", "volume": "volume"}.get(key, "container")
        if docker(kind, "inspect", n[key], check=False).returncode == 0:
            raise SystemExit(f"{kind} {n[key]} already exists")
    if docker("image", "inspect", n["image"], check=False).returncode == 0:
        raise SystemExit(f"image {n['image']} already exists")
    out.mkdir(parents=True)
    free_before = shutil.disk_usage(HERE).free
    docker("network", "create", "--internal", *LABELS, "--label", f"as0927.stamp={stamp}", n["network"], log=log)
    docker("volume", "create", *LABELS, "--label", f"as0927.stamp={stamp}", n["volume"], log=log)
    docker("run", "-d", "--name", n["container"], "--network", n["network"], "--memory", "256m", "--memory-swap", "256m",
           *LABELS, "--label", f"as0927.stamp={stamp}", "-e", f"POSTGRES_PASSWORD={secrets.token_hex(16)}", "-e", f"POSTGRES_DB={n['database']}",
           "-v", f"{n['volume']}:/var/lib/postgresql/data", PG_IMAGE_ID, *SERVER_ARGS, log=log)
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        logs = docker("logs", n["container"], check=False)
        if "PostgreSQL init process complete" in logs.stdout + logs.stderr and \
                docker("exec", n["container"], "pg_isready", "-h", "127.0.0.1", "-U", "postgres", "-d", n["database"], check=False).returncode == 0:
            break
        time.sleep(1)
    else:
        raise SystemExit("fixture did not become ready")
    boot = bootstrap_sql(n["database"])
    (out / "bootstrap.sql").write_text(boot)
    psql(n["container"], n["database"], boot, log=log, single=True)
    before = export(stamp, out, "setup")
    frozen = json.loads((HERE / "architect-derived.json").read_text())["fixture"]
    rows_ok = fixture_rows_from_export((out / "items-setup.csv").read_text(), (out / "tags-setup.csv").read_text()) == frozen
    client = build_client(stamp, log)
    probe_path = out / "probe.py"
    probe_path.write_text(PROBE)
    probe = run_sandboxed(n["container"], n["image"], probe_path)
    line = next((l for l in (probe["stdout"] or "").splitlines() if l.startswith("D14B_PROBE ")), None)
    probe["result"] = json.loads(line[len("D14B_PROBE "):]) if line else None
    inspect = {k: json.loads(docker(kind, "inspect", n[k]).stdout)[0] for k, kind in
               (("network", "network"), ("volume", "volume"), ("container", "container"))}
    ports = inspect["container"]["NetworkSettings"]["Ports"] or {}
    doc = {"schema": "d14b.fixture/v1", "stamp": stamp, "created": now(), "names": n, "owner": "the AI implementer (D14b)",
           "images": {"postgres": {"ref": PG_IMAGE, "id": PG_IMAGE_ID}, "python": {"ref": PY_IMAGE, "id": PY_IMAGE_ID}},
           "server_args": SERVER_ARGS, "memory_bytes": inspect["container"]["HostConfig"]["Memory"],
           "published_ports": {k: v for k, v in ports.items() if v}, "network_internal": inspect["network"]["Internal"],
           "container_networks": sorted(inspect["container"]["NetworkSettings"]["Networks"]),
           "bootstrap_sql_sha256": sha256(boot.encode()), "export_setup": before, "rows_equal_frozen_fixture": rows_ok,
           "client": client, "probe": probe, "commands": log, "disk_free_before": free_before,
           "disk_free_after": shutil.disk_usage(HERE).free, "storage": storage(stamp)}
    (out / "setup.json").write_text(json.dumps(doc, indent=2, default=str) + "\n")
    r = probe["result"] or {}
    ok = (rows_ok and not doc["published_ports"] and doc["network_internal"] and doc["memory_bytes"] == 256 * 1024 * 1024
          and probe["exit_code"] == 0 and probe["attached_targets"] == 1 and r.get("provenance", [None])[:4] == [n["database"], READER, "repeatable read", "on"]
          and r.get("counts") == [6, 6] and r.get("write_refused") not in (None, False) and str(r.get("external_dns", "")).startswith("blocked"))
    print(json.dumps({"stamp": stamp, "names": n, "rows_equal_frozen_fixture": rows_ok, "probe": r, "storage": doc["storage"], "ok": ok}, indent=1))
    raise SystemExit(0 if ok else 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup")
    e = sub.add_parser("export"); e.add_argument("--stamp", required=True); e.add_argument("--out", required=True, type=Path)
    e.add_argument("--label", default="after")
    lg = sub.add_parser("logs"); lg.add_argument("--stamp", required=True); lg.add_argument("--out", required=True, type=Path)
    st = sub.add_parser("storage"); st.add_argument("--stamp", required=True)
    a = ap.parse_args()
    if a.cmd == "setup":
        setup()
    elif a.cmd == "export":
        print(json.dumps(export(a.stamp, a.out, a.label), indent=1))
    elif a.cmd == "logs":
        r = docker("logs", names(a.stamp)["container"])
        a.out.write_text(r.stdout + r.stderr)
        print(f"{len((r.stdout + r.stderr).splitlines())} lines -> {a.out}")
    else:
        print(json.dumps(storage(a.stamp), indent=1))


if __name__ == "__main__":
    main()
