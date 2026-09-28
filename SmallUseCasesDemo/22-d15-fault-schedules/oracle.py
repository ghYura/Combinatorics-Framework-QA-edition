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

"""D15 oracle: seven policy-blind checks over observed attempts and snapshots against the fault-free target.

CONTRACT.md v1. Inputs are only the attempt history and the checkpoint snapshots (never the implementation):
  all_logical_ops_acknowledged   ACK history covers o1, o2, o3
  acknowledged_survive_repair    at `repaired`, every node has >= 1 effect of each op ACKed before recovery
  acknowledged_effects_once      final effects count each acknowledged op exactly once
  accepted_logical_ops_once      final accepted records contain each logical op exactly once
  replicas_agree                 final accepted keys, count vectors and values agree across nodes
  matches_fault_free_reference   every final count vector is (1, 1, 1) and every value 111
  final_wal_matches_accepted     no duplicate WAL keys; WAL and accepted maps hold the same keys and, per node,
                                 the same full payloads (final_payloads: accepted records vs WAL records)
PASS requires all seven. Missing checkpoints or malformed snapshots raise (an evidence error, not a verdict).
"""
from collections import Counter

OPS = ("o1", "o2", "o3")
REFERENCE = {"o1": 1, "o2": 1, "o3": 1}
NAMES = ("all_logical_ops_acknowledged", "acknowledged_survive_repair", "acknowledged_effects_once", "accepted_logical_ops_once",
         "replicas_agree", "matches_fault_free_reference", "final_wal_matches_accepted")


def checks(attempts, trace, final_payloads):
    by = {t["checkpoint"]: t["nodes"] for t in trace}
    if "repaired" not in by or trace[-1]["checkpoint"] != "final":
        raise ValueError(f"trace lacks repaired/final checkpoints: {[t['checkpoint'] for t in trace]}")
    final, repaired = by["final"], by["repaired"]
    if any(s["counts"] is None or s["accepted"] is None for s in final + repaired):
        raise ValueError("a node is down at repaired/final")
    acknowledged = sorted({a["op"] for a in attempts if a["status"] == "ACK"})
    before = sorted({a["op"] for a in attempts if a["status"] == "ACK" and a["phase"] in ("prefix", "window")})
    first = final[0]
    return acknowledged, {
        "all_logical_ops_acknowledged": acknowledged == list(OPS),
        "acknowledged_survive_repair": all(s["counts"][op] >= 1 for s in repaired for op in before),
        "acknowledged_effects_once": all(s["counts"][op] == 1 for s in final for op in acknowledged),
        "accepted_logical_ops_once": all(Counter(k.split(":")[0] for k in s["accepted"]) == REFERENCE for s in final),
        "replicas_agree": all((s["accepted"], s["counts"], s["value"]) == (first["accepted"], first["counts"], first["value"]) for s in final),
        "matches_fault_free_reference": all(s["counts"] == REFERENCE and s["value"] == 111 for s in final),
        "final_wal_matches_accepted": all(len(s["wal"]) == len(set(s["wal"])) and sorted(s["wal"]) == s["accepted"] for s in final)
        and all(sorted(p["accepted"], key=lambda r: r["key"]) == sorted(p["wal"], key=lambda r: r["key"]) for p in final_payloads),
    }


def verdict(result):
    return "PASS" if all(result[n] for n in NAMES) else "DOMAIN_FAIL"
