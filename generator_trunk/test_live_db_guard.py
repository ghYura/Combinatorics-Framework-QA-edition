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

"""Live-database test guard: opt-in, owned namespace, exact cleanup -- verified without PostgreSQL.

Every test here runs DB-free: connection, socket and subprocess entry points are spied, and the
server is a fake. It proves that a default run skips the live tests in test_bundle_constraints.py
before contacting anything (even with real credentials configured), that opting in without a
valid prefix fails before contact, and that `OwnedDatabases` creates only fresh prefixed names,
refuses collisions and drops exactly what this invocation created or reserved, on both ports.

Run: `python3 -m pytest test_live_db_guard.py -q`.
"""
import ast
import inspect
import socket
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import live_db_guard as ldb                                    # noqa: E402
import test_bundle_constraints as tbc                          # noqa: E402

DB_MARKERS = ("_connect(", "_connect_port(", "stage_core(", "stage_reader(", '"--db"', "dbs.create(")


def _live_tests():
    """(name, function) for every test in test_bundle_constraints.py that touches a database."""
    out = []
    for name, fn in inspect.getmembers(tbc, inspect.isfunction):
        if name.startswith("test_") and any(m in inspect.getsource(fn) for m in DB_MARKERS):
            out.append((name, fn))
    return out


@pytest.fixture
def spies(monkeypatch):
    """Record (and refuse) every way a test could reach PostgreSQL or spawn a process."""
    calls = []

    def refuse(label):
        def _f(*a, **k):
            calls.append(label)
            raise AssertionError(f"{label} called while live-DB tests are not opted in")
        return _f
    import pg8000.dbapi
    monkeypatch.setattr(pg8000.dbapi, "connect", refuse("pg8000.connect"))
    monkeypatch.setattr(socket, "create_connection", refuse("socket.create_connection"))
    monkeypatch.setattr(socket.socket, "connect", refuse("socket.connect"))
    monkeypatch.setattr(subprocess, "Popen", refuse("subprocess.Popen"))
    return calls


def test_every_live_db_test_starts_with_the_guard():
    live = _live_tests()
    assert len(live) == 8, [n for n, _ in live]
    for name, fn in live:
        body = ast.parse(inspect.getsource(fn)).body[0].body
        stmts = body[1:] if isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) else body
        first = ast.unparse(stmts[0])
        assert first == "dbs = _live_databases_or_skip()", f"{name} starts with {first!r}"
    src = inspect.getsource(tbc)
    assert "CREATE DATABASE" not in src and "DROP DATABASE" not in src and "_drop_db" not in src


@pytest.mark.parametrize("env", [
    {},                                                         # nothing set
    {"BUNDLE_MAIN_DB_PASSWORD": "pass"},                        # real credentials alone
    {"BUNDLE_TEST_DB_PREFIX": "as0927_"},                       # a prefix without the opt-in
    {"BUNDLE_TEST_LIVE_DB": "yes", "BUNDLE_TEST_DB_PREFIX": "as0927_"},   # only "1" opts in
])
def test_default_run_skips_every_live_test_without_contact(monkeypatch, spies, env):
    for var in ("BUNDLE_TEST_LIVE_DB", "BUNDLE_TEST_DB_PREFIX", "BUNDLE_MAIN_DB_PASSWORD"):
        monkeypatch.delenv(var, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(tbc, "_main_db_password", lambda: "pass")   # e.g. a .bundle-dev-defaults.json
    for name, fn in _live_tests():
        with pytest.raises(pytest.skip.Exception):
            fn()
    with pytest.raises(ldb.LiveDbNotEnabled):
        tbc._connect("postgres")                                    # the helper itself refuses
    assert spies == []


@pytest.mark.parametrize("prefix", [None, "", "as0927", "AS0927_", "as0927-_", "_as0927_", "as0927_;drop_",
                                    "as0927__", "a" * 40 + "_"])
def test_opt_in_without_a_valid_prefix_fails_before_contact(monkeypatch, spies, prefix):
    monkeypatch.setenv("BUNDLE_TEST_LIVE_DB", "1")
    if prefix is None:
        monkeypatch.delenv("BUNDLE_TEST_DB_PREFIX", raising=False)
    else:
        monkeypatch.setenv("BUNDLE_TEST_DB_PREFIX", prefix)
    for name, fn in _live_tests():
        with pytest.raises(pytest.fail.Exception):
            fn()
    assert spies == []


def test_valid_prefixes():
    for prefix in ("as0927_", "as0927_t_", "cl0925_", "x1_"):
        assert ldb.live_db_prefix({"BUNDLE_TEST_LIVE_DB": "1", "BUNDLE_TEST_DB_PREFIX": prefix}) == prefix


# ---- a fake two-port server --------------------------------------------------------------
class FakeServer:
    def __init__(self, existing=None, fail_create=()):
        self.dbs = {5433: set(), 5432: set()}
        for port, names in (existing or {}).items():
            self.dbs[port] |= set(names)
        self.fail_create = set(fail_create)
        self.log = []

    def connect(self, port, dbname):
        return FakeConn(self, port)


class FakeConn:
    def __init__(self, server, port):
        self.server, self.port, self.autocommit, self._row = server, port, False, None

    def cursor(self):
        return self

    def execute(self, sql, args=()):
        srv, port = self.server, self.port
        srv.log.append((port, sql, tuple(args)))
        if sql.startswith("SELECT 1 FROM pg_database"):
            self._row = (1,) if args[0] in srv.dbs[port] else None
        elif sql.startswith("CREATE DATABASE"):
            name = sql.split('"')[1]
            if name in srv.fail_create:
                raise RuntimeError("simulated CREATE failure")
            srv.dbs[port].add(name)
        elif sql.startswith("DROP DATABASE"):
            srv.dbs[port].discard(sql.split('"')[1])

    def fetchone(self):
        return self._row

    def close(self):
        pass


def _statements(server, verb):
    return [(port, sql.split('"')[1]) for port, sql, _ in server.log if sql.startswith(verb)]


def test_fresh_names_are_prefixed_unique_and_fit_postgres():
    dbs = ldb.OwnedDatabases("as0927_", FakeServer().connect)
    names = {dbs.fresh_name("rdrbond") for _ in range(50)}
    assert len(names) == 50
    for n in names:
        assert n.startswith("as0927_rdrbond_") and len(n) <= 63 and len(n.rsplit("_", 1)[1]) == 12
    for bad in ("RdrBond", "rdr-bond", "", "x;y"):
        with pytest.raises(ValueError):
            dbs.fresh_name(bad)
    with pytest.raises(ldb.LiveDbConfigError):
        ldb.OwnedDatabases("FW", FakeServer().connect)             # the namespace is validated too


def test_create_refuses_a_collision_and_never_replaces(monkeypatch):
    class U:
        hex = "0123456789ab" + "0" * 20
    monkeypatch.setattr(ldb.uuid, "uuid4", lambda: U)
    srv = FakeServer(existing={5433: {"as0927_step35_0123456789ab"}})
    dbs = ldb.OwnedDatabases("as0927_", srv.connect)
    with pytest.raises(ldb.DatabaseCollision):
        dbs.create("step35", 5433)
    assert dbs.created == [] and _statements(srv, "CREATE") == [] and _statements(srv, "DROP") == []
    dbs.cleanup()
    assert _statements(srv, "DROP") == [] and "as0927_step35_0123456789ab" in srv.dbs[5433]


def test_cleanup_drops_exactly_what_this_invocation_created_on_both_ports(monkeypatch):
    names = iter(["a" * 12, "b" * 12, "c" * 12])

    class U:
        @property
        def hex(self):
            return next(names) + "0" * 20
    monkeypatch.setattr(ldb.uuid, "uuid4", lambda: U())
    foreign = {"as0927_other_ffffffffffff", "fw_rdrbond_66e09215fe8e", "DeBe"}
    srv = FakeServer(existing={5433: foreign, 5432: foreign}, fail_create={"as0927_mopt_" + "b" * 12})
    with ldb.OwnedDatabases("as0927_", srv.connect) as dbs:
        a = dbs.create("opt", 5433)                         # created
        with pytest.raises(RuntimeError):
            dbs.create("mopt", 5433)                        # CREATE failed: never recorded
        c = dbs.create("rdrbond", 5433)
        dbs.reserve(c, 5432)                                # the Reader will create it on 5432 ...
        srv.dbs[5432].add(c)                                # ... and does
        dbs.reserve(a, 5432)                                # reserved but never created
        with pytest.raises(ldb.DatabaseCollision):
            dbs.reserve("as0927_other_ffffffffffff", 5432)  # an existing name is never adopted
        with pytest.raises(ValueError):
            dbs.reserve("fw_rdrbond_66e09215fe8e", 5432)    # outside the owned prefix
    assert sorted(_statements(srv, "DROP")) == sorted([(5433, a), (5433, c), (5432, c)])
    assert srv.dbs[5433] == foreign and srv.dbs[5432] == foreign


def test_drop_refuses_a_name_outside_the_prefix():
    dbs = ldb.OwnedDatabases("as0927_", FakeServer().connect)
    dbs.created.append((5433, "fw_step35_0123456789ab"))    # even if the record were corrupted
    with pytest.raises(RuntimeError, match="outside the owned prefix"):
        dbs.cleanup()
