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

"""D15 system under test: one replica worker process with a tiny write-ahead log (stdlib only).

CONTRACT.md v1. Launched as `python -u worker.py <node> <generation> <policy> <wal_path>`; it loads its state
from the WAL, prints one ready line, then serves JSON-line requests on stdin with one JSON-line reply each:
  put {record}       record = {key, op, delta}; a known key with the same payload succeeds without effect,
                     a conflicting payload is rejected
  snapshot           accepted records (key-sorted), materialized effects in application order, value, pending
  merge {records}    key-sorted union: put the missing keys in that order, then flush
  flush              write pending records (acceptance order), fsync; never applies an effect
  exit               reply and exit (no flush)
Policies:
  durable       new key: append the canonical record, flush, fsync; then accept, apply once, reply.
                Startup: unique accepted keys, every WAL record applied once in file order.
  volatile_ack  accept/apply/reply without writing; flush writes pending records. A crash loses pending memory.
  replay_twice  like durable, but startup applies the complete WAL twice (two full passes); keys accepted once.
WAL lines are canonical JSON (sorted keys, compact), one newline each, no timestamps. Nothing here knows the
schedule, the oracle or an expected result.
"""
import json
import os
import re
import sys

OPS = {"o1": 1, "o2": 10, "o3": 100}
POLICIES = ("durable", "volatile_ack", "replay_twice")
KEY_RE = re.compile(r"^(o[123]):a[12]$")


def canon(record):
    return json.dumps(record, sort_keys=True, separators=(",", ":"))


def check_record(record):
    if not isinstance(record, dict) or sorted(record) != ["delta", "key", "op"]:
        raise ValueError(f"malformed record {record!r}")
    m = KEY_RE.match(record["key"]) if isinstance(record["key"], str) else None
    if not m or record["op"] != m.group(1) or type(record["delta"]) is not int or record["delta"] != OPS[record["op"]]:
        raise ValueError(f"inconsistent record {record!r}")
    return record


class Replica:
    def __init__(self, policy, wal_path):
        if policy not in POLICIES:
            raise ValueError(f"unknown policy {policy!r}")
        self.policy, self.wal_path = policy, wal_path
        self.accepted, self.effects, self.pending = {}, [], []
        self.load()

    def load(self):
        records = []
        if os.path.exists(self.wal_path):
            with open(self.wal_path, "r", encoding="utf-8") as fh:
                for line in fh:
                    rec = check_record(json.loads(line))
                    if line != canon(rec) + "\n":
                        raise ValueError("non-canonical WAL line")
                    records.append(rec)
        for rec in records:
            if rec["key"] in self.accepted and self.accepted[rec["key"]] != rec:
                raise ValueError(f"conflicting WAL records for {rec['key']}")
            self.accepted.setdefault(rec["key"], rec)
        for _ in range(2 if self.policy == "replay_twice" else 1):
            for rec in records:
                self.effects.append(rec)
        return len(records)

    def _append(self, records):
        with open(self.wal_path, "a", encoding="utf-8") as fh:
            for rec in records:
                fh.write(canon(rec) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def put(self, record):
        rec = check_record(record)
        known = self.accepted.get(rec["key"])
        if known is not None:
            if known != rec:
                raise ValueError(f"conflicting payload for {rec['key']}")
            return {"ok": True, "duplicate": True}
        if self.policy != "volatile_ack":
            self._append([rec])                                  # durable before the acknowledgement
        self.accepted[rec["key"]] = rec
        self.effects.append(rec)
        if self.policy == "volatile_ack":
            self.pending.append(rec["key"])
        return {"ok": True, "duplicate": False}

    def flush(self):
        n = len(self.pending)
        if n:
            self._append([self.accepted[k] for k in self.pending])
            self.pending = []
        return {"ok": True, "flushed": n}

    def merge(self, records):
        keys = [check_record(r)["key"] for r in records]
        if keys != sorted(set(keys)):
            raise ValueError("merge input must be key-sorted and unique")
        added = sum(1 for r in records if not self.put(r)["duplicate"])
        return {"ok": True, "added": added, "flushed": self.flush()["flushed"]}

    def snapshot(self):
        keys = sorted(self.accepted)
        return {"ok": True, "accepted": [self.accepted[k] for k in keys], "effects": [e["op"] for e in self.effects],
                "deltas": [e["delta"] for e in self.effects], "value": sum(e["delta"] for e in self.effects), "pending": list(self.pending)}


def serve(node, generation, policy, wal_path, stdin=sys.stdin, stdout=sys.stdout):
    replica = Replica(policy, wal_path)
    stdout.write(json.dumps({"ready": True, "node": node, "generation": generation, "pid": os.getpid(), "policy": policy,
                             "loaded_effects": len(replica.effects)}) + "\n")
    stdout.flush()
    for line in stdin:
        try:
            req = json.loads(line)
            if not isinstance(req, dict) or req.get("node") != node:
                raise ValueError(f"request not addressed to node {node}: {line.strip()[:80]}")
            op = req.get("op")
            if op == "put":
                reply = replica.put(req.get("record"))
            elif op == "merge":
                if not isinstance(req.get("records"), list):
                    raise ValueError("merge needs a record list")
                reply = replica.merge(req["records"])
            elif op == "flush":
                reply = replica.flush()
            elif op == "snapshot":
                reply = replica.snapshot()
            elif op == "exit":
                stdout.write(json.dumps({"ok": True, "exit": True}) + "\n")
                stdout.flush()
                return 0
            else:
                raise ValueError(f"unknown request {op!r}")
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            reply = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        stdout.write(json.dumps(reply, sort_keys=True) + "\n")
        stdout.flush()
    return 0


if __name__ == "__main__":
    node_, generation_, policy_, wal_ = sys.argv[1:5]
    sys.exit(serve(int(node_), int(generation_), policy_, wal_))
