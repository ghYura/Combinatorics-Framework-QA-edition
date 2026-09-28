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

"""D1 runtime: execute one isolated case, observe it, judge it, emit a record.

A candidate program assigns IMPL, L, CUT1, CUT2 and CONTROL, then calls
`emit`. Each call builds a fresh `DurableState`, so no state is shared between
cases. The oracle receives the observation without the policy selector.
Invalid inputs raise, so the Executor records BROKEN rather than a domain
verdict. One stdout line carries the full record:

  app=d1_idempotency FW_VAR=<0|2> case=<id> verdict=<PASS|DOMAIN_FAIL>
      ... rec=<base64url(JSON)> rec_sha256=<hex of the JSON bytes>

FW_VAR 2 is the IMPL slot's position, the legacy carrier for "the contract
failed in this case". It is not a claim about which factor caused it.
"""
import base64
import hashlib
import json

import oracle
import sut

APP = "d1_idempotency"
CARRIER = 2                      # IMPL position (HEAD=1, IMPL=2, ...); 0 = PASS
CONTROLS = ("none", "retry_fresh_transport", "new_order_equal_payload",
            "new_operation_same_order", "conflicting_retry")
_PEERS = {"retry_fresh_transport": ("O1", "OP1", 100),
          "new_order_equal_payload": ("O2", "OP1", 100),
          "new_operation_same_order": ("O1", "OP2", 100),
          "conflicting_retry": ("O1", "OP1", 101)}
SOURCE_SHA256 = {}               # filled by the candidate HEAD after it checks the inlined sources


def case_id(impl, labels, cuts, control):
    return "%s|L=%s|C=%s|P=%s" % (impl, "".join(map(str, labels)), "".join(map(str, cuts)), control)


def _request(transport_id, order_id, operation_id, amount_minor):
    return {"transport_id": transport_id, "order_id": order_id, "operation_id": operation_id,
            "payload": {"amount_minor": amount_minor, "currency": "TST"}}


def _check_inputs(impl, labels, cuts, control):
    if impl not in sut.POLICIES:
        raise ValueError("unknown IMPL %r" % (impl,))
    if (len(labels) != 3 or labels[0] != 0 or labels[1] not in (0, 1)
            or labels[2] not in (0, 1, 2)):
        raise ValueError("labels outside the contract domain: %r" % (labels,))
    if len(cuts) != 2 or any(c not in (0, 1) for c in cuts):
        raise ValueError("cuts outside the contract domain: %r" % (cuts,))
    if control not in CONTROLS:
        raise ValueError("unknown CONTROL %r" % (control,))


def observe(impl, labels, cuts, control):
    """Run the three core deliveries, then at most one peer. Returns a policy-free observation."""
    labels, cuts = list(labels), list(cuts)
    _check_inputs(impl, labels, cuts, control)
    durable = sut.DurableState()
    service = sut.Service(impl, durable)
    epoch = 0
    deliveries = []
    for i, label in enumerate(labels):
        restart = i > 0 and cuts[i - 1] == 1
        if restart:                      # new process object over the same durable state
            service = sut.Service(impl, durable)
            epoch += 1
        req = _request("T%d" % label, "O1", "OP1", 100)
        resp = service.handle(req)
        deliveries.append({"index": i + 1, "label": label, "restart_before": restart,
                           "epoch": epoch, "request": req, "response": resp,
                           "effects_after": len(durable.ledger)})
    pre = service.ledger_view()          # core checkpoint, captured before any peer
    peer = None
    if control != "none":
        order_id, operation_id, amount = _PEERS[control]
        req = _request("T3", order_id, operation_id, amount)
        before = len(durable.ledger)
        resp = service.handle(req)       # same process: no restart before the peer
        peer = {"restart_before": False, "request": req, "response": resp,
                "effect_delta": len(durable.ledger) - before}
    post = service.ledger_view()
    multiplicity = {}
    for e in pre:
        k = "%s/%s" % (e["order_id"], e["operation_id"])
        multiplicity[k] = multiplicity.get(k, 0) + 1
    return {"deliveries": deliveries, "pre_peer_ledger": pre,
            "pre_peer_multiplicity": multiplicity,
            "first_receipt": deliveries[0]["response"]["receipt_id"],
            "peer": peer, "post_peer_ledger": post}


def run_case(impl, labels, cuts, control):
    """Observe and judge one case; return the full structured record."""
    obs = observe(impl, labels, cuts, control)
    checks = oracle.judge(obs)           # policy-free: IMPL and CONTROL are not passed
    fw_var = 0 if checks["contract_valid"] else CARRIER
    return {"schema": "d1.observation/v1", "contract": "v1",
            "case_id": case_id(impl, labels, cuts, control), "impl": impl,
            "labels": "".join(map(str, labels)), "cuts": "".join(map(str, cuts)),
            "control": control, "population": "core" if control == "none" else "peer",
            "observation": obs, "checks": checks,
            "verdict": "PASS" if fw_var == 0 else "DOMAIN_FAIL",
            "fw_var": fw_var, "carrier": "IMPL position 2 (legacy positional, not causal)",
            "source_sha256": dict(SOURCE_SHA256)}


def _flag(v):
    return "ok" if v is True else ("FAIL" if v is False else "na")


def emit(impl, labels, cuts, control):
    """Run one case, print its metrics line and return the FW_VAR verdict code."""
    rec = run_case(impl, labels, cuts, control)
    raw = json.dumps(rec, sort_keys=True, separators=(",", ":")).encode("utf-8")
    parts = ["app=%s" % APP, "FW_VAR=%d" % rec["fw_var"], "case=%s" % rec["case_id"],
             "verdict=%s" % rec["verdict"]]
    parts += ["%s=%s" % (k, _flag(v)) for k, v in rec["checks"].items()]
    parts += ["rec=%s" % base64.urlsafe_b64encode(raw).decode("ascii"),
              "rec_sha256=%s" % hashlib.sha256(raw).hexdigest()]
    print(" ".join(parts), flush=True)
    return rec["fw_var"]
