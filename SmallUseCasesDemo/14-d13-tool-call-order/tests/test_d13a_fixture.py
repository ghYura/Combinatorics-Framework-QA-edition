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

"""D13a fixture checks: models against the frozen traces; partial-read taint; revocation and reapproval;
duplicate effects; denial of an eligible request (a deny-all controller must fail); the non-retroactive
prefix rule; the controlled read error never escaping; setup errors; independence; the builder.

Run: python -m pytest -q -p no:cacheprovider tests
"""
import ast
import base64
import contextlib
import importlib
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import oracle  # noqa: E402
import sut  # noqa: E402
import tools  # noqa: E402
import verify  # noqa: E402

DERIVED = json.loads((HERE / "architect-derived.json").read_text())


def run(policy, order, n, fail, cut):
    o = sut.Orchestrator(policy)
    o.run(order, n, fail, cut)
    return o


def test_models_match_frozen():
    for c in DERIVED["cases"]:
        o = run(c["policy"], c["order"], c["send_repetitions"], c["fail_read"], c["revoke_cut"])
        assert (o.trace, o.send_results, o.outbox, o.state) == (c["trace"], c["send_results"], c["outbox"], c["final_state"])
        assert oracle.violations(o.trace) == c["violations"] == verify.prefix_violations(o.trace)
        assert oracle.reference(c["order"], c["send_repetitions"], c["revoke_cut"]) == (c["reference_sends"], c["reference_outbox"])


def test_read_stub_delivers_chunk_before_its_error():
    seen = []
    with pytest.raises(tools.ControlledReadError):
        tools.read(seen.append, True)
    assert seen == [tools.CANARY]


def test_partial_read_taints():
    o = run("guarded", "ARS", 1, True, None)
    assert [e["event"] for e in o.trace][:4] == ["approve", "read_start", "read_chunk", "read_error"]
    assert o.send_results[0]["action"] == "block" and o.send_results[0]["reason"] == "tainted" and o.outbox == []
    bad = run("success_only_taint", "ARS", 1, True, None)
    assert bad.outbox == [{"message_id": "notice-1", "payload": tools.CANARY}]
    assert oracle.violations(bad.trace) == [{"request": 1, "kind": "tainted_emit"}]


def test_revocation_then_reapproval():
    o = run("guarded", "ASR", 1, False, 0)            # revoke before the first block, then A grants again
    assert [e["event"] for e in o.trace][:2] == ["revoke", "approve"] and o.send_results[0]["action"] == "emit"
    assert oracle.violations(o.trace) == []
    blocked = run("guarded", "ASR", 1, False, 1)      # revoke after A: the send is blocked
    assert blocked.send_results[0]["action"] == "block"
    sticky = run("sticky_approval", "ASR", 1, False, 1)
    assert oracle.violations(sticky.trace) == [{"request": 1, "kind": "unapproved_emit"}]


def test_duplicate_effects():
    o = run("no_dedup", "ASR", 2, False, None)
    assert len(o.outbox) == 2 and oracle.violations(o.trace) == [{"request": 2, "kind": "duplicate_emit"}]
    g = run("guarded", "ASR", 2, False, None)
    assert [r["action"] for r in g.send_results] == ["emit", "dedup"] and len(g.outbox) == 1


def test_deny_all_controller_does_not_pass():
    ref, box = oracle.reference("ASR", 1, None)
    deny_all = [{"request": 1, "action": "block", "payload": None}]
    assert ref == [{"request": 1, "action": "emit", "payload": "PUBLIC"}] and deny_all != ref and box != []


def test_non_retroactive_prefix_rule():
    o = run("guarded", "ASR", 2, True, 3)             # emit + dedup, then taint and revocation later
    assert [r["action"] for r in o.send_results] == ["emit", "dedup"]
    assert oracle.violations(o.trace) == [] == verify.prefix_violations(o.trace)
    assert o.state == {"approved": False, "tainted": True, "sent_once": True, "buffer": tools.CANARY}   # final flags alone mislead


def test_runtime_record_and_no_escaped_error():
    import runtime
    rt = importlib.reload(runtime)
    rt.begin(); rt.impl("guarded"); rt.repetitions(1); rt.read_mode(1)
    for op in "RAS":
        rt.plan(op)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert rt.finish() == 0
    rec = json.loads(base64.urlsafe_b64decode(dict(t.split("=", 1) for t in buf.getvalue().split() if "=" in t)["rec"]))
    assert rec["case_id"] == "P=guarded|O=RAS|N=1|F=1|X=none" and any(e["event"] == "read_error" for e in rec["trace"])


@pytest.mark.parametrize("calls", [[("plan", "A"), ("plan", "A")], [("repetitions", 3)], [("read_mode", 2)], [("set_revoke", 4)],
                                   [("set_revoke", 1), ("set_revoke", 2)]])
def test_setup_errors_raise(calls):
    import runtime
    rt = importlib.reload(runtime)
    rt.begin()
    rt.impl("guarded")
    with pytest.raises((RuntimeError, ValueError)):
        for fn, arg in calls:
            getattr(rt, fn)(arg)


def test_oracle_is_policy_blind():
    tree = ast.parse((HERE / "oracle.py").read_text())
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {a.arg for a in ast.walk(tree) if isinstance(a, ast.arg)}
    imports = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} | \
        {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert "policy" not in names and not imports


def test_verifier_imports_nothing_from_the_implementation():
    tree = ast.parse((HERE / "verify.py").read_text())
    imports = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imports |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not imports & {"tools", "sut", "oracle", "runtime", "analysis", "derive"}


def test_spec_matches_fresh_build():
    r = subprocess.run([sys.executable, str(HERE / "build_spec.py"), "--check"], capture_output=True, text=True, cwd=HERE)
    assert r.returncode == 0, r.stdout + r.stderr
