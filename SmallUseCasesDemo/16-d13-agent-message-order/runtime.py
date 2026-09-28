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

"""D13c runtime: rebuild the schedule from the rendered atoms, drive two agent stubs, judge, emit one record.

A candidate runs, in order:
  HEAD    begin()                     a fresh case (after the inlined sources are checked)
  IMPL    impl("<policy>");
  MODE    mode("independent"|"after_A_offer");
  CAP     cap(<0|1|2>);
  S1..S4  set_step(<i>,"A"|"B");
  TAIL    finish()
The four steps must give each agent exactly two messages (inspect, then commit), the schedule's
preemptions must not exceed the cap, and every delivery must be enabled on the HARNESS state
(delivery counts and the mode's negotiation dependency), never on the coordinator's allocations.
Anything else raises before or during delivery, so the Executor records BROKEN (a setup error),
never a domain verdict. A ledger that disagrees with the observed GRANTED replies also raises
(integrity fails before the four checks). One stdout line:

  app=d13c_messages FW_VAR=<0|2> case=<id> verdict=<PASS|DOMAIN_FAIL> rec=<base64url(JSON)> rec_sha256=<hex>

FW_VAR 2 is the IMPL position's legacy carrier, not a statement of cause.
"""
import base64
import hashlib
import json

import oracle
import sut

APP = "d13c_messages"
CARRIER = 2
MODES = ("independent", "after_A_offer")
CHECKS = ("capacity_ok", "exclusive_promises_ok", "commitments_ok", "reference_ok")
SOURCE_SHA256 = {}               # filled by the candidate HEAD after it checks the inlined sources
_state = {}


def begin():
    if _state:
        raise RuntimeError("begin() called twice in one candidate")
    _state.update(policy=None, mode=None, cap=None, steps=[])


def impl(policy):
    if not _state or _state["policy"] is not None or _state["mode"] is not None:
        raise RuntimeError("impl() must follow begin() exactly once, first")
    if policy not in sut.POLICIES:
        raise ValueError(f"unknown policy {policy!r}")
    _state["policy"] = policy


def mode(name):
    if not _state or _state["policy"] is None or _state["mode"] is not None or _state["cap"] is not None:
        raise RuntimeError("mode() must follow impl() once")
    if name not in MODES:
        raise ValueError(f"unknown mode {name!r}")
    _state["mode"] = name


def cap(n):
    if not _state or _state["mode"] is None or _state["cap"] is not None or _state["steps"]:
        raise RuntimeError("cap() must follow mode() once, before the steps")
    if type(n) is not int or n not in (0, 1, 2):
        raise ValueError(f"cap {n!r} outside the contract")
    _state["cap"] = n


def set_step(i, agent):
    if not _state or _state["cap"] is None:
        raise RuntimeError("set_step() before cap()")
    if i != len(_state["steps"]) + 1 or i > 4 or agent not in sut.AGENTS:
        raise ValueError(f"set_step({i},{agent!r}) out of order or unknown after {len(_state['steps'])} steps")
    _state["steps"].append(agent)


def _enabled(delivered, mode_):
    """Harness readiness: an agent has a next local message, and B.inspect waits for A's offer if so declared."""
    return [a for a in sut.AGENTS if delivered[a] < 2
            and not (a == "B" and mode_ == "after_A_offer" and delivered["B"] == 0 and delivered["A"] == 0)]


def switches_and_preemptions(schedule):
    switches = preemptions = 0
    for i in range(len(schedule) - 1):
        if schedule[i] != schedule[i + 1]:
            switches += 1
            preemptions += schedule[: i + 1].count(schedule[i]) < 2      # the outgoing agent still has its commit
    return switches, preemptions


def _run(policy, schedule, mode_):
    coordinator, delivered, offers, trace = sut.Coordinator(policy), {"A": 0, "B": 0}, {}, []
    for index, agent in enumerate(schedule, 1):
        before = _enabled(delivered, mode_)
        if agent not in before:
            raise ValueError(f"delivery {index} ({agent}) is disabled in {mode_} mode: enabled {before}")
        delivered[agent] += 1
        kind = "inspect" if delivered[agent] == 1 else "commit"
        request = {"id": f"{agent}:{kind}", "agent": agent, "kind": kind, "resource": sut.RESOURCE}
        if kind == "commit":
            request.update(offer_version=offers[agent]["version"], offer_available=offers[agent]["available"])
        response = coordinator.deliver(request)
        if kind == "inspect":
            offers[agent] = dict(response)             # the agent stub keeps its own offer
        snap = coordinator.snapshot()
        trace.append({"index": index, "agent": agent, "local_step": delivered[agent], "message": request["id"],
                      "enabled_agents_before": before, "request": request, "response": response,
                      "offers": {k: dict(v) for k, v in offers.items()}, "version": snap["version"],
                      "allocations": snap["allocations"], "issued_grants": snap["issued_grants"]})
    return trace


def finish():
    if not _state or _state["policy"] is None or _state["mode"] is None or _state["cap"] is None:
        raise RuntimeError("finish() without a configured case")
    policy, mode_, cap_, schedule = _state["policy"], _state["mode"], _state["cap"], "".join(_state["steps"])
    if len(schedule) != 4 or schedule.count("A") != 2 or schedule.count("B") != 2:
        raise ValueError(f"malformed local order {schedule!r}: each agent needs inspect then commit")
    switches, preemptions = switches_and_preemptions(schedule)
    if preemptions > cap_:
        raise ValueError(f"schedule {schedule} has {preemptions} preemptions, above cap {cap_}")
    observed = _run(policy, schedule, mode_)
    reference = oracle.reference_trace(schedule, mode_)
    j = oracle.judge(observed, reference)
    if not j["integrity_ok"]:
        raise RuntimeError(f"issued_grants disagrees with the GRANTED replies at {j['integrity_failures']}")
    failing = j["failing_checkpoints"]
    verdict = "PASS" if not failing else "DOMAIN_FAIL"
    fw_var = 0 if not failing else CARRIER
    case = f"P={policy}|M={mode_}|K={cap_}|S={schedule}"
    rec = {"schema": "d13c.observation/v1", "contract": "v1", "case_id": case, "policy": policy, "mode": mode_, "cap": cap_,
           "schedule": schedule, "preemptions": preemptions, "context_switches": switches,
           "observed_trace": observed, "reference_trace": reference, "reconstructed_ledgers": oracle.reconstructed_ledgers(observed),
           "integrity_ok": True, "checks": j["checks"], "all_checks": {k: all(c[k] for c in j["checks"]) for k in CHECKS},
           "failing_checkpoints": failing, "verdict": verdict, "fw_var": fw_var,
           "carrier_slot": "IMPL position 2 (legacy positional, not causal)", "source_sha256": dict(SOURCE_SHA256)}
    raw = json.dumps(rec, sort_keys=True, separators=(",", ":")).encode("ascii")
    print(" ".join(["app=%s" % APP, "FW_VAR=%d" % fw_var, "case=%s" % case, "verdict=%s" % verdict,
                    "rec=%s" % base64.urlsafe_b64encode(raw).decode("ascii"),
                    "rec_sha256=%s" % hashlib.sha256(raw).hexdigest()]), flush=True)
    return fw_var
