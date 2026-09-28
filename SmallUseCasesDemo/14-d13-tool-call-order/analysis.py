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

"""D13a offline analysis of the observed traces: counts by policy and axis, and failure-mechanism timelines.

    python analysis.py --run evidence/<run-id>      # write evidence/<run-id>/analysis.json

Input guard: exactly one observation for each of the 480 identities, known identities only. Reports
outcomes by policy and by every configured axis (N, read mode, revocation cut, order), violation kinds,
and keeps send REQUESTS, outbox EFFECTS and Framework execution ATTEMPTS as separate counts. For each
witness it lists the event timeline with the faulty policy's local state next to the oracle's prefix
evidence (authoritative approval and taint derived from earlier events only).
"""
import argparse
import itertools
import json
import re
from collections import Counter
from pathlib import Path

POLICIES = ("guarded", "sticky_approval", "success_only_taint", "no_dedup")
ID_RE = re.compile(r"P=(\w+)\|O=([ARS]{3})\|N=([12])\|F=([01])\|X=(none|[0-3])")
WITNESSES = ["P=sticky_approval|O=ASR|N=1|F=0|X=1", "P=guarded|O=ASR|N=1|F=0|X=1",
             "P=success_only_taint|O=ARS|N=1|F=1|X=none", "P=no_dedup|O=ASR|N=2|F=0|X=none", "P=guarded|O=ASR|N=2|F=1|X=3"]


class AnalysisInputError(ValueError):
    pass


def expected_ids():
    return sorted(f"P={p}|O={''.join(o)}|N={n}|F={f}|X={x}" for p in POLICIES for o in itertools.permutations("ARS")
                  for n in (1, 2) for f in (0, 1) for x in ("none", "0", "1", "2", "3"))


def load(run):
    rows = {}
    for line in (run / "observations.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if not ID_RE.fullmatch(r.get("case_id", "")):
            raise AnalysisInputError(f"unknown identity {r.get('case_id')!r}")
        if r["case_id"] in rows:
            raise AnalysisInputError(f"duplicate {r['case_id']}")
        rows[r["case_id"]] = r
    if sorted(rows) != expected_ids():
        raise AnalysisInputError(f"{len(set(expected_ids()) - set(rows))} identities missing")
    return rows


def timeline(r):
    approved, tainted, out = False, False, []
    for e in r["trace"]:
        k = e["event"]
        approved = True if k == "approve" else False if k == "revoke" else approved
        tainted = tainted or k == "read_chunk"
        label = k + (f"({e['cut']})" if k == "revoke" else f"#{e['request']}" if "request" in e else "")
        if k == "send_result":
            label += f" -> {e['action']}({e['reason']}) payload={e['payload']}"
        out.append({"event": label, "local_state": {x: e["state"][x] for x in ("approved", "tainted", "sent_once")},
                    "buffer": e["state"]["buffer"], "prefix_evidence": {"approved": approved, "tainted": tainted},
                    "outbox_size": e["outbox_size"]})
    return out


def analyse(rows):
    def tally(key):
        out = {}
        for r in rows.values():
            out.setdefault(key(r), Counter())[r["verdict"]] += 1
        return {str(k): dict(v) for k, v in sorted(out.items(), key=lambda kv: str(kv[0]))}
    return {"schema": "d13a.analysis/v1", "source": "observed traces of all 480 cases",
            "by_policy": tally(lambda r: r["policy"]),
            "by_policy_repetitions": tally(lambda r: (r["policy"], r["send_repetitions"])),
            "by_policy_read_failure": tally(lambda r: (r["policy"], r["fail_read"])),
            "by_policy_revoke_cut": tally(lambda r: (r["policy"], "none" if r["revoke_cut"] is None else r["revoke_cut"])),
            "by_policy_order": tally(lambda r: (r["policy"], r["order"])),
            "violation_kinds": {p: dict(Counter(v["kind"] for r in rows.values() if r["policy"] == p for v in r["violations"])) for p in POLICIES},
            "counts": {"framework_attempts": len(rows), "send_requests": sum(len(r["send_results"]) for r in rows.values()),
                       "outbox_effects": sum(len(r["outbox"]) for r in rows.values()),
                       "emit_responses": sum(1 for r in rows.values() for s in r["send_results"] if s["action"] == "emit")},
            "timelines": {w: timeline(rows[w]) for w in WITNESSES}}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", required=True, type=Path)
    a = ap.parse_args()
    doc = analyse(load(a.run))
    (a.run / "analysis.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"by_policy": doc["by_policy"], "violations": doc["violation_kinds"], "counts": doc["counts"]}))


if __name__ == "__main__":
    main()
