from __future__ import annotations

import os

from .process import run


def sql_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def sql_identifier(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def psql(port, db, sql, *, host="127.0.0.1", user="postgres", password=""):
    """Run one `psql -tAc` query and return ``(stdout, returncode)``.

    STEP 13/14: host/user/password are parameters always supplied by callers
    from `BundleConfig.main_db_*`/`results_db_*` — never a hardcoded literal
    here (the prior fixed credential this carried via `process.PGPW` is gone;
    ``password=""`` is just "no caller-supplied value", never a usable
    credential). ``PGPASSWORD`` is built fresh per call (never a shared
    module-level env snapshot) so a layered/overridden password actually
    reaches `psql`. ``--no-password`` makes every automation call fail closed
    instead of opening an interactive prompt; passwordless trust authentication
    still works. Connections default to a five-second libpq timeout unless the
    operator explicitly configured ``PGCONNECT_TIMEOUT``.
    """
    env = {**os.environ, "PGPASSWORD": password}
    env.setdefault("PGCONNECT_TIMEOUT", "5")
    r = run(["psql", "--no-password", "-h", host, "-p", str(port),
             "-U", user, "-d", db, "-tAc", sql], env=env)
    return r.stdout.strip(), r.returncode
