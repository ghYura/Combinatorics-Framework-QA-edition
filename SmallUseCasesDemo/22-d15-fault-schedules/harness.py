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

"""D15 harness: owns three worker processes, speaks bounded JSON-line IPC, injects faults, takes snapshots.

CONTRACT.md v1. The coordinator writes to every reachable replica, serially in node order; two successful
replies give ACK, fewer give TIMEOUT (partial writes are kept). Faults happen only at quiescent boundaries:
  crash      SIGKILL of the selected Popen-owned workers, then wait/reap (expected return code -9); reopen
             starts a NEW worker (generation 1) on the same WAL file
  partition  a deterministic gate on coordinator writes to the selected nodes; workers stay alive
Snapshots come from worker replies (accepted records, effects, value) and, independently, from the WAL files
on disk (keys in file order, byte hashes). A down node exposes only its WAL and generation. Missing or
malformed replies, unexpected exits, bounded-wait timeouts and bad hashes raise InfraError. Only processes
this harness started are ever signalled.
"""
import hashlib
import json
import os
import select
import signal
import subprocess
import sys

OPS = {"o1": 1, "o2": 10, "o3": 100}
WAIT_SECONDS = 5.0


class InfraError(RuntimeError):
    pass


def sha256(data):
    return hashlib.sha256(data).hexdigest()


class Node:
    def __init__(self, index, wal_path):
        self.index, self.wal_path = index, wal_path
        self.proc, self.generation, self.running, self.buf = None, -1, False, b""


class Cluster:
    def __init__(self, policy, workdir, worker_source, worker_sha256, python=sys.executable):
        if sha256(worker_source.encode("utf-8")) != worker_sha256:
            raise InfraError("worker source does not match its recorded SHA-256")
        self.policy, self.workdir, self.python = policy, workdir, python
        self.worker_path = os.path.join(workdir, "worker.py")
        with open(self.worker_path, "w", encoding="utf-8") as fh:
            fh.write(worker_source)
        with open(self.worker_path, "rb") as fh:
            if sha256(fh.read()) != worker_sha256:
                raise InfraError("written worker entry script differs from its source")
        self.nodes = [Node(i, os.path.join(workdir, f"n{i}.wal")) for i in range(3)]
        self.blocked, self.events, self.owned_pids = set(), [], set()

    # ---- processes ----
    def start(self, i, generation):
        node = self.nodes[i]
        if node.running:
            raise InfraError(f"node {i} is already running")
        argv = [self.python, "-u", self.worker_path, str(i), str(generation), self.policy, node.wal_path]
        wal_before = self.wal_bytes(i)
        node.proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=self.workdir)
        node.buf, node.running, node.generation = b"", True, generation
        self.owned_pids.add(node.proc.pid)
        ready = self._read(i)
        if not ready.get("ready") or ready.get("node") != i or ready.get("pid") != node.proc.pid or ready.get("generation") != generation:
            raise InfraError(f"node {i} sent a bad ready line {ready!r}")
        self.events.append({"event": "start", "node": i, "generation": generation, "pid": node.proc.pid, "argv": argv,
                            "wal_sha256_at_start": sha256(wal_before), "loaded_effects": ready["loaded_effects"]})

    def kill(self, i):
        node = self.nodes[i]
        proc = node.proc
        if proc is None or not node.running or proc.pid not in self.owned_pids or proc.poll() is not None:
            raise InfraError(f"refusing to signal node {i}: not a running owned worker")
        proc.send_signal(signal.SIGKILL)
        try:
            rc = proc.wait(timeout=WAIT_SECONDS)
        except subprocess.TimeoutExpired:
            raise InfraError(f"node {i} did not exit after SIGKILL")
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            stream.close()
        if rc != -signal.SIGKILL:
            raise InfraError(f"node {i} returned {rc} after SIGKILL")
        node.running = False
        self.events.append({"event": "kill", "node": i, "generation": node.generation, "pid": proc.pid, "signal": "SIGKILL",
                            "returncode": rc, "wal_sha256_after": sha256(self.wal_bytes(i))})

    def shutdown(self):
        """Stop every still-running owned worker with an exit request (no flush) and reap it."""
        for i, node in enumerate(self.nodes):
            if node.running:
                reply = self.request(i, {"op": "exit"})
                rc = node.proc.wait(timeout=WAIT_SECONDS)
                for stream in (node.proc.stdin, node.proc.stdout, node.proc.stderr):
                    stream.close()
                node.running = False
                self.events.append({"event": "exit", "node": i, "generation": node.generation, "pid": node.proc.pid,
                                    "returncode": rc, "reply_ok": reply.get("ok")})
                if rc != 0:
                    raise InfraError(f"node {i} exited with {rc}")

    def reap_all(self):
        """Last-resort cleanup after an error: kill and wait only processes this harness started."""
        for node in self.nodes:
            if node.proc is not None and node.proc.poll() is None and node.proc.pid in self.owned_pids:
                node.proc.kill()
                node.proc.wait(timeout=WAIT_SECONDS)

    # ---- IPC ----
    def _read(self, i):
        node = self.nodes[i]
        fd = node.proc.stdout.fileno()
        while b"\n" not in node.buf:
            ready, _, _ = select.select([fd], [], [], WAIT_SECONDS)
            if not ready:
                raise InfraError(f"node {i}: no reply within {WAIT_SECONDS} s")
            chunk = os.read(fd, 65536)
            if not chunk:
                err = node.proc.stderr.read().decode(errors="replace")[-300:] if node.proc.poll() is not None else ""
                raise InfraError(f"node {i} exited unexpectedly (rc={node.proc.poll()}): {err}")
            node.buf += chunk
        line, node.buf = node.buf.split(b"\n", 1)
        try:
            reply = json.loads(line)
        except json.JSONDecodeError:
            raise InfraError(f"node {i}: malformed reply {line[:80]!r}")
        if not isinstance(reply, dict):
            raise InfraError(f"node {i}: reply is not an object")
        return reply

    def request(self, i, msg):
        node = self.nodes[i]
        if not node.running or node.proc.poll() is not None:
            raise InfraError(f"node {i} is not running")
        node.proc.stdin.write((json.dumps(dict(msg, node=i)) + "\n").encode())
        node.proc.stdin.flush()
        reply = self._read(i)
        if not reply.get("ok"):
            raise InfraError(f"node {i} rejected {msg.get('op')}: {reply.get('error')}")
        return reply

    # ---- coordinator ----
    def attempt(self, op, key, phase):
        record = {"key": key, "op": op, "delta": OPS[op]}
        targets = [i for i in range(3) if self.nodes[i].running and i not in self.blocked]
        ok = sum(1 for i in targets if self.request(i, {"op": "put", "record": record})["ok"])
        return {"op": op, "key": key, "phase": phase, "targets": targets, "status": "ACK" if ok >= 2 else "TIMEOUT"}

    def crash(self, failed):
        for i in failed:
            self.kill(i)

    def reopen(self, failed):
        for i in failed:
            self.start(i, self.nodes[i].generation + 1)

    def repair(self):
        """Key-sorted union of accepted records from all workers, merged into each worker in node order, then flushed."""
        union = {}
        for i in range(3):
            for rec in self.request(i, {"op": "snapshot"})["accepted"]:
                if union.setdefault(rec["key"], rec) != rec:
                    raise InfraError(f"conflicting payloads for {rec['key']} across replicas")
        records = [union[k] for k in sorted(union)]
        for i in range(3):
            self.request(i, {"op": "merge", "records": records})
        return records

    def flush_all(self):
        for i in range(3):
            self.request(i, {"op": "flush"})

    # ---- observation ----
    def wal_bytes(self, i):
        path = self.nodes[i].wal_path
        if not os.path.exists(path):
            return b""
        with open(path, "rb") as fh:
            return fh.read()

    def wal_records(self, i):
        out = []
        for line in self.wal_bytes(i).decode("utf-8").splitlines(keepends=True):
            rec = json.loads(line)
            if not line.endswith("\n") or line != json.dumps(rec, sort_keys=True, separators=(",", ":")) + "\n":
                raise InfraError(f"node {i}: non-canonical WAL line {line[:60]!r}")
            if sorted(rec) != ["delta", "key", "op"] or OPS.get(rec["op"]) != rec["delta"] or rec["key"].split(":")[0] != rec["op"]:
                raise InfraError(f"node {i}: malformed WAL record {rec!r}")
            out.append(rec)
        return out

    def snapshot(self, label):
        states = []
        for i, node in enumerate(self.nodes):
            wal = [r["key"] for r in self.wal_records(i)]
            state = {"node": i, "running": node.running, "reachable": node.running and i not in self.blocked,
                     "generation": node.generation, "accepted": None, "wal": wal, "effects": None, "counts": None, "value": None}
            if node.running:
                snap = self.request(i, {"op": "snapshot"})
                effects = snap["effects"]
                if any(d != OPS.get(op) for op, d in zip(effects, snap["deltas"])) or len(effects) != len(snap["deltas"]):
                    raise InfraError(f"node {i}: effect payloads disagree with their operations")
                counts = {op: effects.count(op) for op in OPS}
                if snap["value"] != sum(OPS[op] * n for op, n in counts.items()):
                    raise InfraError(f"node {i}: reported value {snap['value']} disagrees with its effects")
                state.update(accepted=[r["key"] for r in snap["accepted"]], effects=effects, counts=counts, value=snap["value"])
            states.append(state)
        return {"checkpoint": label, "nodes": states}

    def wal_evidence(self):
        return {f"n{i}": {"sha256": sha256(self.wal_bytes(i)), "lines": self.wal_bytes(i).decode("utf-8").splitlines()} for i in range(3)}
