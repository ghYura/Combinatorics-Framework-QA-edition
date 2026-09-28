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

"""D14b runtime: rebuild the case from the rendered atoms, run its four real SELECTs, emit one record.

A candidate runs, in order:
  HEAD       begin()                  a fresh case (after the inlined sources are checked)
  IMPL       impl("<policy>");
  QUERY      query("<shape>");
  PREDICATE  predicate("<name>");
  TAIL       finish()
finish() opens a fresh pg8000 connection to the owned fixture named by the D14B_FIXTURE environment
variable (host = database = container name; fixture-only SELECT role), then runs ONE transaction:
  BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY; provenance; base; true; false; unknown; COMMIT
The provenance row (database, role, isolation, read-only flag, backend PID, snapshot, version,
application_name, statement_timeout) must match the owned fixture and the contract. The adapter
recombines the actual partition rows and the oracle judges. A connection/SQL error, a guard violation
or a malformed result raises, so the Executor records BROKEN (an infrastructure error), never a
domain verdict. One stdout line:

  app=d14b_sql FW_VAR=<0|2> case=<id> verdict=<PASS|DOMAIN_FAIL> rec=<base64url(JSON)> rec_sha256=<hex>

FW_VAR 2 is the IMPL position's legacy carrier, not a statement of cause.
"""
import base64
import hashlib
import json
import os
import re

import adapter
import oracle

APP = "d14b_sql"
CARRIER = 2
READER, PASSWORD, PORT = "as0927_d14b_reader", "pass", 5432       # fixture-only SELECT role (isolated container)
FIXTURE_ENV = "D14B_FIXTURE"
FIXTURE_RE = re.compile(r"^as0927_d14b_sql_[0-9a-z]+$")
BEGIN = "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY"
PROVENANCE = ("SELECT current_database(), current_user, current_setting('transaction_isolation'), "
              "current_setting('transaction_read_only'), pg_backend_pid(), pg_current_snapshot()::text, version(), "
              "current_setting('application_name'), current_setting('statement_timeout')")
PROVENANCE_KEYS = ("database", "user", "transaction_isolation", "transaction_read_only", "backend_pid", "snapshot",
                   "version", "application_name", "statement_timeout")
SOURCE_SHA256 = {}               # filled by the candidate HEAD after it checks the inlined sources
_connect = None                  # test hook: a callable(fixture, application_name) -> connection with .run/.close
_state = {}


def begin():
    if _state:
        raise RuntimeError("begin() called twice in one candidate")
    _state.update(policy=None, query=None, predicate=None)


def impl(policy):
    if not _state or _state["policy"] is not None or policy not in adapter.POLICIES:
        raise ValueError(f"impl({policy!r}) out of order or unknown")
    _state["policy"] = policy


def query(name):
    if not _state or _state["policy"] is None or _state["query"] is not None or name not in adapter.QUERIES:
        raise ValueError(f"query({name!r}) out of order or unknown")
    _state["query"] = name


def predicate(name):
    if not _state or _state["query"] is None or _state["predicate"] is not None or name not in adapter.PREDICATES:
        raise ValueError(f"predicate({name!r}) out of order or unknown")
    _state["predicate"] = name


def _open(fixture, application_name):
    import pg8000.native
    return pg8000.native.Connection(user=READER, host=fixture, database=fixture, port=PORT, password=PASSWORD, timeout=10,
                                    application_name=application_name,
                                    startup_params={"statement_timeout": "5000", "idle_in_transaction_session_timeout": "10000"})


def _result_rows(rows):
    if not isinstance(rows, list):
        raise ValueError(f"query returned {type(rows).__name__}, not a row list")
    out = []
    for r in rows:
        if not isinstance(r, (list, tuple)) or len(r) != 1 or not (r[0] is None or type(r[0]) is int):
            raise ValueError(f"malformed result row {r!r}")
        out.append([r[0]])
    return out


def guard(prov, fixture, application_name):
    want = {"database": fixture, "user": READER, "transaction_isolation": "repeatable read", "transaction_read_only": "on",
            "application_name": application_name}
    bad = {k: (prov.get(k), v) for k, v in want.items() if prov.get(k) != v}
    if bad or type(prov.get("backend_pid")) is not int or not re.fullmatch(r"\d+:\d+:[\d,]*", str(prov.get("snapshot"))):
        raise RuntimeError(f"transaction/role guard failed: {bad or prov}")


def execute(fixture, case, sql):
    """The four data queries in one REPEATABLE READ READ ONLY transaction; (results, provenance)."""
    if not isinstance(fixture, str) or not FIXTURE_RE.fullmatch(fixture):
        raise RuntimeError(f"{FIXTURE_ENV}={fixture!r} does not name an owned as0927_d14b_sql_* fixture")
    application_name = ("d14b:" + case)[:63]
    con = (_connect or _open)(fixture, application_name)
    sequence, results = [], {}
    try:
        def run(kind, text):
            rows = con.run(text)
            sequence.append({"kind": kind, "sql": text, "rows": None if rows is None else len(rows)})
            return rows
        run("begin", BEGIN)
        prov = run("provenance", PROVENANCE)
        if not isinstance(prov, list) or len(prov) != 1 or len(prov[0]) != len(PROVENANCE_KEYS):
            raise ValueError(f"malformed provenance row {prov!r}")
        prov = dict(zip(PROVENANCE_KEYS, prov[0]))
        guard(prov, fixture, application_name)
        for b in adapter.BRANCHES:
            results[b] = _result_rows(run("data:" + b, sql[b]))
        run("end", "COMMIT")
    finally:
        con.close()
    return results, {"fixture": fixture, **prov, "statements": sequence}


def finish():
    if not _state or _state["predicate"] is None:
        raise RuntimeError("finish() before the case is complete")
    policy, name, pred = _state["policy"], _state["query"], _state["predicate"]
    case = f"P={policy}|Q={name}|F={pred}"
    sql = adapter.build_sql(name, pred)
    results, provenance = execute(os.environ.get(FIXTURE_ENV), case, sql)
    query_rows = {b: oracle.canonical(results[b]) for b in adapter.BRANCHES}
    combined = oracle.canonical(adapter.recombine(policy, results))
    j = oracle.judge(name, pred, query_rows, combined)
    fw_var = 0 if j["verdict"] == "PASS" else CARRIER
    rec = {"schema": "d14b.observation/v1", "contract": "v1", "id": case, "policy": policy, "query": name, "predicate": pred,
           "sql": sql, "query_rows": query_rows, "query_bags": {b: oracle.bag(query_rows[b]) for b in adapter.BRANCHES},
           "combined_rows": combined, "combined_bag": oracle.bag(combined), "tlp_ok": j["tlp_ok"], "set_equal": j["set_equal"],
           "query_checks": j["query_checks"], "verdict": j["verdict"], "fw_var": fw_var,
           "carrier_slot": "IMPL position 2 (legacy positional, not causal)", "source_sha256": dict(SOURCE_SHA256),
           "provenance": provenance}
    raw = json.dumps(rec, sort_keys=True, separators=(",", ":")).encode("ascii")
    print(" ".join(["app=%s" % APP, "FW_VAR=%d" % fw_var, "case=%s" % case, "verdict=%s" % j["verdict"],
                    "rec=%s" % base64.urlsafe_b64encode(raw).decode("ascii"),
                    "rec_sha256=%s" % hashlib.sha256(raw).hexdigest()]), flush=True)
    return fw_var
