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

"""D6 runtime: rebuild the schedule from the rendered atoms, check it, run it step by step, emit one record.

A candidate runs, in order:
  HEAD   begin()                 a fresh case (after the inlined sources are checked)
  IMPL   impl("<policy>");
  CAP    cap(<n>);               counter only
  S1..S4 set_step(<i>,"<thread>");
  TAIL   finish("counter"|"queue")
The schedule must be four steps, two per thread, S1..S4 in order. A counter schedule must respect
its preemption cap; every queue step must be enabled on the REFERENCE state before it runs (the
faulty implementation's state never decides enabledness). Anything else raises before the SUT
runs, so the Executor records BROKEN (a setup error), never a domain verdict. One stdout line:

  app=d6_schedules FW_VAR=<0|2> case=<id> verdict=<PASS|DOMAIN_FAIL> rec=<base64url(JSON)> rec_sha256=<hex>

FW_VAR 2 is the IMPL position's legacy carrier, not a statement of cause.
"""
import base64
import hashlib
import json

import oracle
import sut

APP = "d6_schedules"
CARRIER = 2
THREADS = {"counter": ("A", "B"), "queue": ("P", "C")}
SOURCE_SHA256 = {}               # filled by the candidate HEAD after it checks the inlined sources
_state = {}


def begin():
    if _state:
        raise RuntimeError("begin() called twice in one candidate")
    _state.update(policy=None, cap=None, steps=[])


def impl(policy):
    if not _state or _state["policy"] is not None or _state["steps"] or _state["cap"] is not None:
        raise RuntimeError("impl() must follow begin() exactly once, first")
    if policy not in sut.COUNTER_POLICIES + sut.QUEUE_POLICIES:
        raise ValueError(f"unknown policy {policy!r}")
    _state["policy"] = policy


def cap(n):
    if not _state or _state["policy"] is None or _state["cap"] is not None or _state["steps"]:
        raise RuntimeError("cap() must follow impl() once, before the steps")
    if n not in (0, 1, 2):
        raise ValueError(f"cap {n!r} outside the contract")
    _state["cap"] = n


def set_step(i, thread):
    if not _state or _state["policy"] is None:
        raise RuntimeError("set_step() before impl()")
    if i != len(_state["steps"]) + 1 or i > 4:
        raise ValueError(f"set_step({i}) out of order after {len(_state['steps'])} steps")
    _state["steps"].append(thread)


def _schedule(campaign):
    threads, s = THREADS[campaign], "".join(_state["steps"])
    policies = sut.COUNTER_POLICIES if campaign == "counter" else sut.QUEUE_POLICIES
    if _state["policy"] not in policies:
        raise ValueError(f"policy {_state['policy']!r} does not belong to the {campaign} campaign")
    if len(s) != 4 or set(s) - set(threads) or any(s.count(t) != 2 for t in threads):
        raise ValueError(f"malformed schedule {s!r}: need two steps of each of {threads}")
    if campaign == "counter":
        if _state["cap"] is None:
            raise ValueError("counter case without cap()")
        if oracle.preemptions(s) > _state["cap"]:
            raise ValueError(f"schedule {s} has {oracle.preemptions(s)} preemptions, above cap {_state['cap']}")
    elif _state["cap"] is not None:
        raise ValueError("queue case with cap()")
    return s


def finish(campaign):
    if campaign not in THREADS or not _state or _state["policy"] is None:
        raise RuntimeError(f"finish({campaign!r}) without a started case")
    s, policy = _schedule(campaign), _state["policy"]
    base = {"schema": "d6.observation/v1", "contract": "v1", "campaign": campaign, "policy": policy, "schedule": s,
            "local_steps": [f"{t}{n}" for t, n in oracle.occurrences(s)],
            "context_switches": oracle.context_switches(s), "preemptions": oracle.preemptions(s)}
    if campaign == "counter":
        machine = sut.Counter(policy)
        expected = oracle.counter_expected(s)
        trace = [machine.step(t) for t in s]
        failing = [k + 1 for k, (o, e) in enumerate(zip(trace, expected)) if o["counter"] != e]
        case = f"counter|{policy}|CAP={_state['cap']}|SEQ={s}"
        rec = {**base, "case_id": case, "cap": _state["cap"], "observed_trace": trace, "reference_counters": expected}
    else:
        reference, disabled = oracle.queue_reference(s)
        if disabled is not None:
            raise ValueError(f"schedule {s} is infeasible: step {disabled} is disabled on the reference state")
        machine = sut.Queue(policy)
        trace = [machine.step(t) for t in s]
        failing = [k + 1 for k, (o, e) in enumerate(zip(trace, reference))
                   if (o["items"], o["pop_result"]) != (e["items"], e["pop_result"])]
        case = f"queue|{policy}|SEQ={s}"
        rec = {**base, "case_id": case, "observed_trace": trace, "reference_trace": reference,
               "enabled_on_reference": [True] * len(s)}
    verdict = "PASS" if not failing else "DOMAIN_FAIL"
    fw_var = 0 if not failing else CARRIER
    rec.update(failing_checkpoints=failing, verdict=verdict, fw_var=fw_var,
               carrier="IMPL position 2 (legacy positional, not causal)", source_sha256=dict(SOURCE_SHA256))
    raw = json.dumps(rec, sort_keys=True, separators=(",", ":")).encode("ascii")
    print(" ".join(["app=%s" % APP, "FW_VAR=%d" % fw_var, "case=%s" % case, "verdict=%s" % verdict,
                    "rec=%s" % base64.urlsafe_b64encode(raw).decode("ascii"),
                    "rec_sha256=%s" % hashlib.sha256(raw).hexdigest()]), flush=True)
    return fw_var
