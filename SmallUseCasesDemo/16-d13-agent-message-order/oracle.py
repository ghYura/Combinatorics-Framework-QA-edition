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

"""D13c oracle: a policy-blind reference and promise ledger rebuilt from observed replies.

The reference replays the same schedule and mode under compare_version semantics with its own
coordinator and agent stubs, emitting the frozen event schema. The promise ledger is reconstructed
only from GRANTED replies (agent -> ticket); the observed issued_grants map must equal it at every
prefix, and a mismatch is an integrity failure reported BEFORE any of the four checks. Each
checkpoint then requires:
  capacity_ok            at most one current allocation
  exclusive_promises_ok  at most one outstanding promise (reconstructed ledger)
  commitments_ok         current allocations equal outstanding promises
  reference_ok           the whole event (request, reply, offers, version, allocations, ledger,
                         enabledness) equals the reference event
A deny-all coordinator keeps the first three but fails reference_ok: useful grants are required.
"""


def enabled(counts, mode):
    """Agents whose next local message may be delivered, from delivery counts alone."""
    out = []
    for agent in ("A", "B"):
        if counts[agent] >= 2:
            continue
        if agent == "B" and counts["B"] == 0 and mode == "after_A_offer" and counts["A"] == 0:
            continue                                   # B.inspect waits for A's published offer
        out.append(agent)
    return out


def reference_trace(schedule, mode):
    counts, offers, allocations, promises, version, events = {"A": 0, "B": 0}, {}, {}, {}, 0, []
    for index, agent in enumerate(schedule, 1):
        before = enabled(counts, mode)
        if agent not in before:
            raise ValueError(f"step {index} ({agent}) is not enabled in {mode} mode")
        counts[agent] += 1
        kind = ("inspect", "commit")[counts[agent] - 1]
        request = {"id": f"{agent}:{kind}", "agent": agent, "kind": kind, "resource": "R"}
        if kind == "inspect":
            reply = {"available": len(allocations) == 0, "version": version}
            offers[agent] = {"available": reply["available"], "version": reply["version"]}
        else:
            request["offer_version"], request["offer_available"] = offers[agent]["version"], offers[agent]["available"]
            if not request["offer_available"]:
                reply = {"status": "BUSY", "ticket": None}
            elif allocations or version != request["offer_version"]:
                reply = {"status": "STALE", "ticket": None}
            else:
                reply = {"status": "GRANTED", "ticket": "R:" + agent}
                allocations[agent] = promises[agent] = reply["ticket"]
                version += 1
        events.append({"index": index, "agent": agent, "local_step": counts[agent], "message": request["id"],
                       "enabled_agents_before": before, "request": request, "response": reply,
                       "offers": {k: dict(v) for k, v in offers.items()}, "version": version,
                       "allocations": dict(allocations), "issued_grants": dict(promises)})
    return events


def reconstructed_ledgers(trace):
    """The outstanding promises after each event, from GRANTED replies only (no revocation exists)."""
    ledger, out = {}, []
    for e in trace:
        reply = e.get("response") or {}
        if reply.get("status") == "GRANTED":
            ledger[e["agent"]] = reply.get("ticket")
        out.append(dict(ledger))
    return out


def judge(observed, reference):
    """{integrity_ok, integrity_failures, checks, failing_checkpoints}; checks are None when integrity fails."""
    ledgers = reconstructed_ledgers(observed)
    broken = [e.get("index") for e, led in zip(observed, ledgers) if e.get("issued_grants") != led]
    broken += [e.get("index") for e in observed if (e.get("response") or {}).get("status") == "GRANTED"
               and e["response"].get("ticket") != "R:" + str(e.get("agent"))]
    if broken or len(observed) != len(reference):
        return {"integrity_ok": False, "integrity_failures": sorted(set(broken)) or ["length"], "checks": None,
                "failing_checkpoints": None}
    checks = [{"index": want["index"], "capacity_ok": len(got["allocations"]) <= 1,
               "exclusive_promises_ok": len(led) <= 1, "commitments_ok": got["allocations"] == led,
               "reference_ok": got == want}
              for got, want, led in zip(observed, reference, ledgers)]
    failing = [c["index"] for c in checks if not all(c[k] for k in ("capacity_ok", "exclusive_promises_ok", "commitments_ok", "reference_ok"))]
    return {"integrity_ok": True, "integrity_failures": [], "checks": checks, "failing_checkpoints": failing}
