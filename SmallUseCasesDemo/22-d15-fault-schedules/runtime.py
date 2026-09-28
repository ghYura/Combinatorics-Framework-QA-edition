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

"""D15 runtime: rebuild the case from the rendered atoms, run the fault schedule on three real workers, emit one record.

A candidate runs, in order:
  HEAD   begin()                          a fresh case (after the inlined sources are checked)
  IMPL   impl("<implementation>");
  FAIL   fail(i);...                      one native FW_Subsets row: the failed-node subset, in rendered order
  CUT    cut(<0..3>);
  KIND   fault("crash"|"partition");
  RETRY  retry("stable"|"fresh");
  TAIL   finish()
finish() runs CONTRACT.md's schedule: initial; o1..oc (prefix); inject the fault (faulted); o(c+1):a1 against
the reachable complement if c<3 (window); reopen or remove the gate (reopened); merge the key-sorted union and
flush (repaired); retry a timed-out window once against all nodes, stable o:a1 or fresh o:a2 (retry); the
remaining operations; flush (final). The oracle's seven checks decide the verdict. Worker processes live in a
fresh directory under TMPDIR and are reaped before the record is printed. Any IPC, file, ownership or evidence
error raises (BROKEN), never a domain verdict. One stdout line:

  app=d15_faults FW_VAR=<0|2> case=<id> verdict=<PASS|DOMAIN_FAIL> rec=<base64url(JSON)> rec_sha256=<hex>

semantic_sha256 digests the deterministic portion (factors, attempts, trace, acknowledged, checks, verdict);
live PIDs and paths sit in `provenance`. FW_VAR 2 is the IMPL position's legacy carrier, not a cause.
"""
import base64
import hashlib
import json
import os
import shutil
import sys
import tempfile

import harness
import oracle

APP = "d15_faults"
CARRIER = 2
IMPLEMENTATIONS = ("durable", "volatile_ack", "replay_twice")
SOURCE_SHA256 = {}               # filled by the candidate HEAD after it checks the inlined sources
SOURCES = {}                     # the inlined source texts (the worker entry script is written from here)
SEMANTIC_KEYS = ("id", "policy", "failed", "cut", "kind", "retry", "attempts", "trace", "acknowledged", "checks", "verdict")
_state = {}


def begin():
    if _state:
        raise RuntimeError("begin() called twice in one candidate")
    _state.update(policy=None, failed=[], cut=None, kind=None, retry=None)


def impl(name):
    if not _state or _state["policy"] is not None or name not in IMPLEMENTATIONS:
        raise ValueError(f"impl({name!r}) out of order or unknown")
    _state["policy"] = name


def fail(node):
    if not _state or _state["policy"] is None or _state["cut"] is not None:
        raise RuntimeError("fail() must follow impl() and precede cut()")
    if type(node) is not int or node not in (0, 1, 2) or node in _state["failed"]:
        raise ValueError(f"fail({node!r}) after {_state['failed']}: nodes 0..2, each at most once")
    _state["failed"].append(node)


def cut(c):
    if not _state or not _state["failed"] or _state["cut"] is not None or type(c) is not int or c not in (0, 1, 2, 3):
        raise ValueError(f"cut({c!r}) out of order or outside 0..3 (failed {_state.get('failed')})")
    _state["cut"] = c


def fault(kind):
    if not _state or _state["cut"] is None or _state["kind"] is not None or kind not in ("crash", "partition"):
        raise ValueError(f"fault({kind!r}) out of order or unknown")
    _state["kind"] = kind


def retry(policy):
    if not _state or _state["kind"] is None or _state["retry"] is not None or policy not in ("stable", "fresh"):
        raise ValueError(f"retry({policy!r}) out of order or unknown")
    _state["retry"] = policy


def worker_source():
    if "worker" in SOURCES:
        return SOURCES["worker"], SOURCE_SHA256["worker"]
    path = os.path.join(os.path.dirname(os.path.abspath(harness.__file__)), "worker.py")      # local tests only
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    return text, hashlib.sha256(text.encode("utf-8")).hexdigest()


def schedule(policy, failed, c, kind, retry_policy, workdir):
    """CONTRACT.md's seven steps on real workers; (attempts, trace, final payloads, cluster)."""
    source, digest = worker_source()
    cl = harness.Cluster(policy, workdir, source, digest)
    try:
        attempts, trace = [], []
        for i in range(3):
            cl.start(i, 0)
        trace.append(cl.snapshot("initial"))
        for k in range(1, c + 1):
            attempts.append(cl.attempt(f"o{k}", f"o{k}:a1", "prefix"))
        trace.append(cl.snapshot("prefix"))
        cl.blocked.update(failed)
        if kind == "crash":
            cl.crash(failed)
        trace.append(cl.snapshot("faulted"))
        timed_out = False
        if c < 3:
            window = cl.attempt(f"o{c + 1}", f"o{c + 1}:a1", "window")
            attempts.append(window)
            timed_out = window["status"] == "TIMEOUT"
            trace.append(cl.snapshot("window"))
        if kind == "crash":
            cl.reopen(failed)
        cl.blocked.clear()
        trace.append(cl.snapshot("reopened"))
        cl.repair()
        trace.append(cl.snapshot("repaired"))
        if timed_out:
            again = cl.attempt(f"o{c + 1}", f"o{c + 1}:{'a1' if retry_policy == 'stable' else 'a2'}", "retry")
            attempts.append(again)
            if again["status"] != "ACK":
                raise harness.InfraError("the retry against all nodes did not ACK")
            trace.append(cl.snapshot("retry"))
        for k in range(c + 2, 4):
            attempts.append(cl.attempt(f"o{k}", f"o{k}:a1", "suffix"))
        cl.flush_all()
        trace.append(cl.snapshot("final"))
        payloads = [{"node": i, "accepted": cl.request(i, {"op": "snapshot"})["accepted"], "wal": cl.wal_records(i)} for i in range(3)]
        cl.shutdown()
        return attempts, trace, payloads, cl
    except BaseException:
        cl.reap_all()
        raise


def finish():
    if not _state or _state["retry"] is None:
        raise RuntimeError("finish() before the case is complete")
    policy, rendered, c, kind, retry_policy = _state["policy"], list(_state["failed"]), _state["cut"], _state["kind"], _state["retry"]
    failed = sorted(rendered)
    case = f"P={policy}|F={''.join(map(str, failed))}|C={c}|K={kind}|R={retry_policy}"
    workdir = tempfile.mkdtemp(prefix="d15-", dir=os.environ.get("TMPDIR"))
    attempts, trace, payloads, cl = schedule(policy, failed, c, kind, retry_policy, workdir)
    acknowledged, result = oracle.checks(attempts, trace, payloads)
    verdict = oracle.verdict(result)
    fw_var = 0 if verdict == "PASS" else CARRIER
    semantic = {"id": case, "policy": policy, "failed": failed, "cut": c, "kind": kind, "retry": retry_policy, "attempts": attempts,
                "trace": trace, "acknowledged": acknowledged, "checks": result, "verdict": verdict}
    canon = json.dumps(semantic, sort_keys=True, separators=(",", ":")).encode("ascii")
    evidence = cl.wal_evidence()
    rec = {"schema": "d15.observation/v1", "contract": "v1", **semantic, "semantic_sha256": hashlib.sha256(canon).hexdigest(),
           "fail_rendered": rendered, "fw_var": fw_var, "carrier_slot": "IMPL position 2 (legacy positional, not causal)",
           "wal_evidence": evidence, "final_payloads": payloads,
           "provenance": {"workdir": workdir, "python": sys.executable, "worker_script": cl.worker_path, "events": cl.events,
                          "worker_starts": sum(e["event"] == "start" for e in cl.events),
                          "injected_kills": sum(e["event"] == "kill" for e in cl.events)},
           "source_sha256": dict(SOURCE_SHA256)}
    shutil.rmtree(workdir, ignore_errors=True)       # the sandbox scratch is discarded anyway; the evidence is in rec
    raw = json.dumps(rec, sort_keys=True, separators=(",", ":")).encode("ascii")
    print(" ".join(["app=%s" % APP, "FW_VAR=%d" % fw_var, "case=%s" % case, "verdict=%s" % verdict,
                    "rec=%s" % base64.urlsafe_b64encode(raw).decode("ascii"),
                    "rec_sha256=%s" % hashlib.sha256(raw).hexdigest()]), flush=True)
    return fw_var


def control(policy):
    """Fault-free preflight control (outside the campaign denominator): o1..o3 against all three workers, flush."""
    if policy not in IMPLEMENTATIONS:
        raise ValueError(f"unknown implementation {policy!r}")
    workdir = tempfile.mkdtemp(prefix="d15-control-", dir=os.environ.get("TMPDIR"))
    source, digest = worker_source()
    cl = harness.Cluster(policy, workdir, source, digest)
    try:
        for i in range(3):
            cl.start(i, 0)
        attempts = [cl.attempt(f"o{k}", f"o{k}:a1", "prefix") for k in (1, 2, 3)]
        cl.flush_all()
        final = cl.snapshot("final")
        cl.shutdown()
    except BaseException:
        cl.reap_all()
        raise
    ok = all(a["status"] == "ACK" for a in attempts) and all(s["counts"] == {"o1": 1, "o2": 1, "o3": 1} and s["value"] == 111
                                                              and s["wal"] == ["o1:a1", "o2:a1", "o3:a1"] for s in final["nodes"])
    rec = {"schema": "d15.control/v1", "policy": policy, "attempts": attempts, "final": final, "ok": ok, "wal_evidence": cl.wal_evidence(),
           "events": cl.events, "source_sha256": dict(SOURCE_SHA256)}
    shutil.rmtree(workdir, ignore_errors=True)
    raw = json.dumps(rec, sort_keys=True, separators=(",", ":")).encode("ascii")
    print("app=d15_control ok=%s rec=%s rec_sha256=%s" % (ok, base64.urlsafe_b64encode(raw).decode("ascii"), hashlib.sha256(raw).hexdigest()), flush=True)
    return 0 if ok else 2
