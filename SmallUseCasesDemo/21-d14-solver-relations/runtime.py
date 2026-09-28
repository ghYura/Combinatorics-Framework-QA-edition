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

"""D14c runtime: rebuild the case from the rendered atoms, run the three solves, emit one record.

A candidate runs, in order:
  HEAD      begin()                     a fresh case (after the inlined sources are checked)
  IMPL      impl("<policy>");
  INSTANCE  instance("<name>");
  RELABEL   label(a);label(b);label(c);  one native FW_Permut row: R = [a, b, c] in rendered order
  EDIT      edit("none"|"dominated");
  TAIL      finish()
finish() solves, in order, the canonical base, the relabelled base and the edited relabelled base, checks
each result with the exhaustive oracle, compares the four relations and sets the verdict. A missing,
duplicated or out-of-order atom, an unknown value or a malformed solver result raises, so the Executor
records BROKEN (an infrastructure error), never a domain verdict. One stdout line:

  app=d14c_solver FW_VAR=<0|2> case=<id> verdict=<PASS|DOMAIN_FAIL> rec=<base64url(JSON)> rec_sha256=<hex>

rec_sha256 is the digest over the canonical record JSON. FW_VAR 2 is the IMPL position's legacy carrier,
not a statement of cause.
"""
import base64
import hashlib
import json

import oracle
import solver
import transform

APP = "d14c_solver"
CARRIER = 2
SOURCE_SHA256 = {}               # filled by the candidate HEAD after it checks the inlined sources
_state = {}


def begin():
    if _state:
        raise RuntimeError("begin() called twice in one candidate")
    _state.update(policy=None, instance=None, labels=[], edit=None)


def impl(policy):
    if not _state or _state["policy"] is not None or policy not in solver.POLICIES:
        raise ValueError(f"impl({policy!r}) out of order or unknown")
    _state["policy"] = policy


def instance(name):
    if not _state or _state["policy"] is None or _state["instance"] is not None or name not in transform.INSTANCES:
        raise ValueError(f"instance({name!r}) out of order or unknown")
    _state["instance"] = name


def label(good):
    if not _state or _state["instance"] is None or _state["edit"] is not None:
        raise RuntimeError("label() must follow instance() and precede edit()")
    if type(good) is not int or good not in transform.GOODS or good in _state["labels"] or len(_state["labels"]) == 3:
        raise ValueError(f"label({good!r}) after {_state['labels']}: need 0, 1, 2 once each")
    _state["labels"].append(good)


def edit(name):
    if not _state or len(_state["labels"]) != 3 or _state["edit"] is not None or name not in transform.EDITS:
        raise ValueError(f"edit({name!r}) out of order or unknown (labels {_state.get('labels')})")
    _state["edit"] = name


def finish():
    if not _state or _state["edit"] is None:
        raise RuntimeError("finish() before the case is complete")
    policy, name, perm, edit_ = _state["policy"], _state["instance"], list(_state["labels"]), _state["edit"]
    base = transform.base_bids(name)
    relabeled = transform.relabel(base, perm)
    inputs = {"base": base, "relabeled": relabeled, "edited": transform.apply_edit(relabeled, edit_)}
    variants, checks = {}, {}
    for kind, bids in inputs.items():
        variants[kind], checks[kind] = oracle.observe(bids, solver.solve(policy, bids))
    rels = oracle.relations(variants["base"], variants["relabeled"], variants["edited"])
    verdict = oracle.verdict(variants, rels)
    fw_var = 0 if verdict == "PASS" else CARRIER
    case = f"P={policy}|I={name}|R={''.join(map(str, perm))}|E={edit_}"
    rec = {"schema": "d14c.observation/v1", "contract": "v1", "id": case, "policy": policy, "instance": name, "permutation": perm,
           "edit": edit_, "variants": variants, "relations": rels, "verdict": verdict, "fw_var": fw_var,
           "solver_calls": 3, "oracle_subset_checks": checks, "carrier_slot": "IMPL position 2 (legacy positional, not causal)",
           "source_sha256": dict(SOURCE_SHA256)}
    raw = json.dumps(rec, sort_keys=True, separators=(",", ":")).encode("ascii")
    print(" ".join(["app=%s" % APP, "FW_VAR=%d" % fw_var, "case=%s" % case, "verdict=%s" % verdict,
                    "rec=%s" % base64.urlsafe_b64encode(raw).decode("ascii"),
                    "rec_sha256=%s" % hashlib.sha256(raw).hexdigest()]), flush=True)
    return fw_var
