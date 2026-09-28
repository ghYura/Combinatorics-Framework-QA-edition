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

"""D1 runtime oracle: judge one observation against the normative contract.

CONTRACT.md v1 §1 and §4. The input is a policy-free observation: requests,
responses, restart markers and ledger projections. The policy selector and
the peer-control name are never read. Expectations come from `normative_trace`,
an executable form of the contract keyed by logical operation
`(order_id, operation_id)`, whose state a restart never clears.

Sensors (True / False / NA):
  core_at_most_once   after each core delivery the ledger holds one effect per
                      logical operation seen so far (here: exactly one).
  receipt_identity    every returned receipt belongs to the request's own
                      logical operation, and the response claims that identity.
  retry_dedup         (peer repeats an operation, equal payload) REPLAY of the
                      operation's first receipt, no effect added.
  peer_independence   (peer is a new logical operation) APPLIED with its own
                      identity and next receipt, exactly one effect added.
  conflict_handling   (peer repeats an operation, different payload) CONFLICT,
                      no effect added, prior ledger entries unchanged.
  contract_valid      every response and ledger checkpoint equals the
                      normative trace; this alone decides the verdict.
"""

NA = "not_applicable"


def _op(msg):
    return (msg["order_id"], msg["operation_id"])


def normative_trace(requests):
    """Expected responses, and ledger after each request, under the contract."""
    ledger, first, responses, ledgers = [], {}, [], []
    for req in requests:
        op = _op(req)
        if op not in first:
            effect = {"receipt_id": len(ledger) + 1, "order_id": op[0],
                      "operation_id": op[1], "payload": dict(req["payload"])}
            ledger.append(effect)
            first[op] = effect
            responses.append({"status": "APPLIED", "receipt_id": effect["receipt_id"],
                              "order_id": op[0], "operation_id": op[1]})
        elif first[op]["payload"] == req["payload"]:
            responses.append({"status": "REPLAY", "receipt_id": first[op]["receipt_id"],
                              "order_id": op[0], "operation_id": op[1]})
        else:
            responses.append({"status": "CONFLICT", "receipt_id": None,
                              "order_id": op[0], "operation_id": op[1]})
        ledgers.append([dict(e, payload=dict(e["payload"])) for e in ledger])
    return responses, ledgers


def _owned_receipt(req, resp, ledger):
    """Receipt identity for one response against the ledger it could refer to."""
    rid = resp.get("receipt_id")
    if rid is None:
        return True
    if not isinstance(rid, int) or not 1 <= rid <= len(ledger):
        return False
    return _op(ledger[rid - 1]) == _op(req) == _op(resp)


def peer_kind(core_requests, peer_request):
    """How the contract classifies the peer relative to the core deliveries."""
    earlier = {_op(r): r["payload"] for r in core_requests}
    op = _op(peer_request)
    if op not in earlier:
        return "new_operation"
    return "retry" if earlier[op] == peer_request["payload"] else "conflict"


def judge(obs):
    """Return the sensor values and the aggregate verdict for one observation."""
    core = obs["deliveries"]
    peer = obs["peer"]
    pre, post = obs["pre_peer_ledger"], obs["post_peer_ledger"]
    core_reqs = [d["request"] for d in core]
    requests = core_reqs + ([peer["request"]] if peer else [])
    exp_resp, exp_ledgers = normative_trace(requests)

    seen = set()
    at_most_once = True
    for d in core:
        seen.add(_op(d["request"]))
        if d["effects_after"] != len(seen):
            at_most_once = False
    counts = {}
    for e in pre:
        counts[_op(e)] = counts.get(_op(e), 0) + 1
    if len(pre) != len(seen) or any(n != 1 for n in counts.values()):
        at_most_once = False

    identity = all(_owned_receipt(d["request"], d["response"], pre) for d in core)
    if peer:
        identity = identity and _owned_receipt(peer["request"], peer["response"], post)

    checks = {"core_at_most_once": at_most_once, "receipt_identity": identity,
              "retry_dedup": NA, "peer_independence": NA, "conflict_handling": NA}
    if peer:
        kind = peer_kind(core_reqs, peer["request"])
        resp, req = peer["response"], peer["request"]
        prior_kept = post[:len(pre)] == pre
        if kind == "retry":
            checks["retry_dedup"] = (resp["status"] == "REPLAY"
                                     and resp["receipt_id"] == core[0]["response"]["receipt_id"]
                                     and _op(resp) == _op(req)
                                     and peer["effect_delta"] == 0 and post == pre)
        elif kind == "new_operation":
            added = post[len(pre):]
            checks["peer_independence"] = (
                resp["status"] == "APPLIED" and _op(resp) == _op(req)
                and resp["receipt_id"] == len(pre) + 1
                and peer["effect_delta"] == 1 and prior_kept and len(added) == 1
                and _op(added[0]) == _op(req) and added[0]["payload"] == req["payload"]
                and added[0]["receipt_id"] == len(pre) + 1)
        else:
            checks["conflict_handling"] = (resp["status"] == "CONFLICT"
                                           and resp["receipt_id"] is None
                                           and peer["effect_delta"] == 0
                                           and prior_kept and post == pre)

    observed = [d["response"] for d in core] + ([peer["response"]] if peer else [])
    valid = (observed == exp_resp
             and all(d["effects_after"] == len(exp_ledgers[i]) for i, d in enumerate(core))
             and pre == exp_ledgers[len(core) - 1]
             and post == exp_ledgers[-1]
             and (peer is None or peer["effect_delta"] == len(exp_ledgers[-1]) - len(pre)))
    checks["contract_valid"] = valid
    applicable = [v for k, v in checks.items() if k != "contract_valid" and v != NA]
    checks["sensors_agree"] = valid == all(applicable)
    return checks
