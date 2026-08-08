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
# (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
# Ukraine
#
# See LICENSE and NOTICE.md for the binding terms.

"""Plan-2 scale-demo worker — a real, isolated "environment" (Executor stand-in).

Reads its assigned (candidate_id, repeat_idx, iters) units from a file, does REAL
CPU work per unit (a busy arithmetic loop), measures REAL wall-clock latency, and
writes a real `results_v2` row tagged with its env_id. Launched once per env,
pinned to a core with `taskset` so parallel envs don't share a core (Plan-1 §4.4
perf isolation). The Plan-2 control plane then collects these rows by the
(candidate_id, repeat_idx, env_id) identity.

Usage: cp_demo_worker.py <env_id> <units_file> <host> <port> <db> <user> <password>
"""
import sys
import time

import psycopg2


def main() -> int:
    env_id, units_file, host, port, db, user, pw = sys.argv[1:8]
    conn = psycopg2.connect(host=host, port=int(port), dbname=db, user=user, password=pw)
    conn.autocommit = True
    cur = conn.cursor()
    n = 0
    with open(units_file) as f:
        for line in f:
            parts = line.split()
            if len(parts) != 3:
                continue
            cand, rep, iters = parts[0], int(parts[1]), int(parts[2])
            t0 = time.perf_counter()
            s = 0
            for i in range(iters):           # real CPU work — the "candidate"
                s = (s + i * i) % 1_000_003
            lat_ms = (time.perf_counter() - t0) * 1000.0
            cur.execute(
                "INSERT INTO results_v2 (candidate_id, repeat_idx, env_id, fw_var, lat) "
                "VALUES (%s,%s,%s,0,%s) ON CONFLICT DO NOTHING",
                (cand, rep, env_id, lat_ms),
            )
            n += 1
    sys.stderr.write("worker %s: %d units, sink=%d\n" % (env_id, n, s & 0xffff))
    return 0


if __name__ == "__main__":
    sys.exit(main())
