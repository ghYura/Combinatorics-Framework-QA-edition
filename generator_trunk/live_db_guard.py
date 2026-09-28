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

"""Guard for tests that need a live PostgreSQL: explicit opt-in, an owned name prefix, exact cleanup.

A live-database test runs only when BOTH variables are set; credentials alone never enable it:

    BUNDLE_TEST_LIVE_DB=1                  explicit opt-in
    BUNDLE_TEST_DB_PREFIX=<namespace>_     the database-name namespace this invocation owns
                                           (lowercase, ends with "_", e.g. as0927_)

Without the opt-in, `live_db_prefix` raises `LiveDbNotEnabled` and the caller skips BEFORE any
connection or subprocess. Opting in without a valid prefix raises `LiveDbConfigError` (a test
failure, not a silent skip). `OwnedDatabases` then creates only fresh `<prefix><purpose>_<hex>`
names, refuses a name that already exists (never replaces a database), tracks each (port, name)
it created -- or reserved for another component such as the Reader's results DB -- and drops
exactly those, on every port, at cleanup. Nothing outside that record is ever dropped.
"""
import os
import re
import uuid

OPT_IN_ENV = "BUNDLE_TEST_LIVE_DB"
PREFIX_ENV = "BUNDLE_TEST_DB_PREFIX"
MAX_PREFIX_LEN = 32
PG_MAX_IDENTIFIER = 63
_PREFIX_RE = re.compile(r"[a-z][a-z0-9]*_(?:[a-z0-9]+_)*")
_PURPOSE_RE = re.compile(r"[a-z][a-z0-9]*")


class LiveDbNotEnabled(Exception):
    """Live-database tests were not opted into: skip without contacting PostgreSQL."""


class LiveDbConfigError(Exception):
    """Opted in, but the owned namespace is missing or invalid: fail before any connection."""


class DatabaseCollision(Exception):
    """A fresh name already exists on the server: refuse rather than replace or adopt it."""


def live_db_prefix(environ=None) -> str:
    """The validated owned prefix, or raise; reads the environment only (no I/O)."""
    env = os.environ if environ is None else environ
    if env.get(OPT_IN_ENV) != "1":
        raise LiveDbNotEnabled(f"live-database test skipped: opt in with {OPT_IN_ENV}=1 and "
                               f"{PREFIX_ENV}=<owned database-name prefix>")
    prefix = env.get(PREFIX_ENV, "")
    if not prefix:
        raise LiveDbConfigError(f"{OPT_IN_ENV}=1 requires {PREFIX_ENV}: the database-name "
                                f"namespace this run owns (e.g. as0927_)")
    if len(prefix) > MAX_PREFIX_LEN or not _PREFIX_RE.fullmatch(prefix):
        raise LiveDbConfigError(f"{PREFIX_ENV}={prefix!r} is not a valid owned namespace: lowercase "
                                f"letters/digits in '_'-separated words, ending with '_', at most "
                                f"{MAX_PREFIX_LEN} characters")
    return prefix


def require_opt_in(environ=None) -> None:
    """Raise unless live-database tests are opted into with a valid prefix."""
    live_db_prefix(environ)


class OwnedDatabases:
    """Fresh prefixed databases this invocation creates, and the exact cleanup of those.

    `connect(port, dbname)` returns a DB-API connection; it is only called by `create`,
    `reserve` and `cleanup`, never at construction."""

    def __init__(self, prefix: str, connect):
        live_db_prefix({OPT_IN_ENV: "1", PREFIX_ENV: prefix})       # validate the namespace
        self.prefix = prefix
        self._connect = connect
        self.created: list = []      # (port, name) created here, in order
        self.reserved: list = []     # (port, name) another component may create

    def fresh_name(self, purpose: str) -> str:
        if not _PURPOSE_RE.fullmatch(purpose):
            raise ValueError(f"database purpose {purpose!r} must be lowercase letters/digits")
        name = f"{self.prefix}{purpose}_{uuid.uuid4().hex[:12]}"
        if len(name) > PG_MAX_IDENTIFIER:
            raise ValueError(f"database name {name!r} exceeds {PG_MAX_IDENTIFIER} characters")
        return name

    def _admin(self, port):
        conn = self._connect(port, "postgres")
        conn.autocommit = True
        return conn

    @staticmethod
    def _exists(cur, name) -> bool:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,))
        return cur.fetchone() is not None

    def create(self, purpose: str, port: int) -> str:
        """Create a fresh `<prefix><purpose>_<hex>` on `port`; record it only once created."""
        name = self.fresh_name(purpose)
        conn = self._admin(port)
        try:
            cur = conn.cursor()
            if self._exists(cur, name):
                raise DatabaseCollision(f"database {name!r} already exists on port {port}; refusing to reuse it")
            cur.execute(f'CREATE DATABASE "{name}"')
            self.created.append((port, name))
        finally:
            conn.close()
        return name

    def reserve(self, name: str, port: int) -> None:
        """Claim `name` on `port` for a database another component will create (e.g. the Reader
        creates its results DB under the run's name). It must be ours and absent now; cleanup
        drops it only if it then exists, i.e. was created during this invocation."""
        if not name.startswith(self.prefix):
            raise ValueError(f"database {name!r} is outside the owned prefix {self.prefix!r}")
        conn = self._admin(port)
        try:
            if self._exists(conn.cursor(), name):
                raise DatabaseCollision(f"database {name!r} already exists on port {port}; refusing to adopt it")
            self.reserved.append((port, name))
        finally:
            conn.close()

    def _drop(self, port, name, *, only_if_exists=False):
        if not name.startswith(self.prefix):
            raise ValueError(f"refusing to drop {name!r}: outside the owned prefix {self.prefix!r}")
        conn = self._admin(port)
        try:
            cur = conn.cursor()
            if only_if_exists and not self._exists(cur, name):
                return
            cur.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = %s AND pid <> pg_backend_pid()", (name,))
            cur.execute(f'DROP DATABASE IF EXISTS "{name}"')
        finally:
            conn.close()

    def cleanup(self) -> None:
        """Drop exactly the recorded databases; attempt all, then report any failure."""
        errors = []
        for port, name in reversed(self.created):
            try:
                self._drop(port, name)
            except Exception as exc:                  # noqa: BLE001 - finish the others first
                errors.append(f"{name}@{port}: {exc}")
        for port, name in self.reserved:
            try:
                self._drop(port, name, only_if_exists=True)
            except Exception as exc:                  # noqa: BLE001
                errors.append(f"{name}@{port}: {exc}")
        self.created.clear()
        self.reserved.clear()
        if errors:
            raise RuntimeError("live-database cleanup failed: " + "; ".join(errors))

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.cleanup()
        return False
