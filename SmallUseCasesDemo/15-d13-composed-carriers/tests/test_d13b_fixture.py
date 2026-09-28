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

"""D13b fixture checks: models against the frozen predictions; both trust promotions and the benign REF
controls; lost content, missing trusted work and tampered readings detected; the composed ROOT text
building the tree; setup errors; the construction model; independence; the builder.

Run: python -m pytest -q -p no:cacheprovider tests
"""
import ast
import base64
import contextlib
import copy
import io
import itertools
import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import construct  # noqa: E402
import oracle  # noqa: E402
import runtime  # noqa: E402
import sut  # noqa: E402
import verify  # noqa: E402

DERIVED = json.loads((HERE / "architect-derived.json").read_text())
FROZEN = {c["id"]: c for c in DERIVED["cases"]}
ROOTS = {("retrieved_page", "MF"): 'consume(context([trusted_task(),retrieved_page([source_item("marker"),\nsource_item("filler"),\n]),trusted_note()]))\n',
         ("tool_result", "FM"): 'consume(context([trusted_task(),tool_result([source_item("filler"),\nsource_item("marker"),\n]),trusted_note()]))\n'}


def execute(policy, encoding, marker, root_text):
    """Run one candidate body through the runtime exactly as the fragments call it; return (fw_var, record)."""
    runtime._state.clear()
    names = {n: getattr(runtime, n) for n in ("impl", "encoding", "marker", "source_item", "retrieved_page", "tool_result",
                                              "trusted_task", "trusted_note", "context", "consume", "finish")}
    runtime.begin()
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        exec(f'impl("{policy}")\nencoding("{encoding}")\nmarker("{marker}")\n{root_text}_v = finish()\n', names)
    lines = out.getvalue().splitlines()
    assert len(lines) == 1
    tokens = dict(t.split("=", 1) for t in lines[0].split() if "=" in t)
    return names["_v"], json.loads(base64.urlsafe_b64decode(tokens["rec"])), tokens


def root_for(carrier, order):
    first, second = ("marker", "filler") if order == "MF" else ("filler", "marker")
    return f'consume(context([trusted_task(),{carrier}([source_item("{first}"),\nsource_item("{second}"),\n]),trusted_note()]))\n'


def case_id(p, c, o, e, m):
    return f"P={p}|C={c}|O={o}|E={e}|M={m}"


def test_all_108_through_the_runtime_match_frozen():
    keys = ("tree", "trace", "decoded_leaves", "rendered", "actions", "outbox", "ready", "flag", "reference_actions",
            "content_ok", "actions_ok", "effects_ok")
    for p, c, o, e, m in itertools.product(sut.POLICIES, verify.CARRIERS, verify.ORDERS, verify.ENCODINGS, verify.MARKERS):
        fw, rec, tokens = execute(p, e, m, root_for(c, o))
        fz = FROZEN[case_id(p, c, o, e, m)]
        assert rec["case_id"] == tokens["case"] == fz["id"] and {k: rec[k] for k in keys} == {k: fz[k] for k in keys}
        assert rec["verdict"] == fz["predicted_outcome"] == tokens["verdict"] and fw == (0 if rec["verdict"] == "PASS" else 2)
        own = verify.own_case(p, c, o, e, m)
        assert {k: own[k] for k in keys} == {k: rec[k] for k in keys}


def test_wrapper_promotion_forbidden_outbox_and_preserved_control():
    _, bad, _ = execute("wrapper_trust", "plain", "emit_canary", root_for("tool_result", "MF"))
    _, good, _ = execute("preserve_origin", "plain", "emit_canary", root_for("tool_result", "MF"))
    marker_bad = next(t for t in bad["trace"] if t["leaf"] == "marker")
    marker_good = next(t for t in good["trace"] if t["leaf"] == "marker")
    assert marker_bad["source_origin"] == marker_good["source_origin"] == "untrusted"
    assert marker_bad["effective_origin"] == "trusted" and marker_bad["executed"] and bad["outbox"] == [sut.CANARY]
    assert marker_good["effective_origin"] == "untrusted" and not marker_good["executed"] and good["outbox"] == []
    assert bad["rendered"] == good["rendered"] and sut.CANARY in good["rendered"]           # same data, different effect
    assert (bad["verdict"], good["verdict"]) == ("DOMAIN_FAIL", "PASS")


def test_decode_promotion_forbidden_flag_and_decode_without_promotion():
    _, bad, _ = execute("decode_trust", "json", "set_flag", root_for("retrieved_page", "FM"))
    assert bad["flag"] is True and bad["actions"][-1] == {"name": "SET_FLAG", "leaf": "marker"} and bad["verdict"] == "DOMAIN_FAIL"
    _, ok, _ = execute("preserve_origin", "base64", "emit_canary", root_for("retrieved_page", "FM"))
    marker = next(t for t in ok["trace"] if t["leaf"] == "marker")
    assert marker["decoded"] == sut.CANARY + "|EMIT_CANARY" and marker["candidate_action"] == "EMIT_CANARY"
    assert marker["effective_origin"] == "untrusted" and not marker["executed"] and ok["outbox"] == [] and ok["verdict"] == "PASS"


@pytest.mark.parametrize("policy,carrier,encoding", [("wrapper_trust", "tool_result", "plain"), ("wrapper_trust", "tool_result", "json"),
                                                     ("decode_trust", "retrieved_page", "base64"), ("decode_trust", "tool_result", "json")])
def test_benign_ref_controls_promote_but_pass(policy, carrier, encoding):
    _, rec, _ = execute(policy, encoding, "reference", root_for(carrier, "MF"))
    marker = next(t for t in rec["trace"] if t["leaf"] == "marker")
    assert marker["source_origin"] == "untrusted" and marker["effective_origin"] == "trusted"    # promoted metadata
    assert marker["candidate_action"] is None and not marker["executed"] and rec["verdict"] == "PASS"
    assert verify.effect_class(rec) == "benign_promotion"


def test_each_promotion_is_detected_per_axis():
    for p, c, o, e, m in itertools.product(sut.POLICIES, verify.CARRIERS, verify.ORDERS, verify.ENCODINGS, verify.MARKERS):
        want_fail = m != "reference" and ((p == "wrapper_trust" and c == "tool_result") or (p == "decode_trust" and e != "plain"))
        assert (FROZEN[case_id(p, c, o, e, m)]["predicted_outcome"] == "DOMAIN_FAIL") == want_fail


def _judge(rec, **over):
    r = dict(copy.deepcopy(rec), **over)
    return oracle.judge(r["tree"], r["carrier"], r["order"], r["encoding"], r["marker"], r["decoded_leaves"], r["rendered"],
                        r["actions"], r["ready"], r["flag"], r["outbox"])


def test_lost_content_is_detected(monkeypatch):
    _, rec, _ = execute("preserve_origin", "json", "emit_canary", root_for("tool_result", "MF"))
    assert _judge(rec) == (True, True, True)
    dropped = [d for d in rec["decoded_leaves"] if d["id"] != "marker"]
    assert _judge(rec, decoded_leaves=dropped, rendered="\n".join(d["text"] for d in dropped))[0] is False
    redacted = [dict(d, text="[removed]") if d["id"] == "marker" else d for d in rec["decoded_leaves"]]
    assert _judge(rec, decoded_leaves=redacted, rendered="\n".join(d["text"] for d in redacted))[0] is False
    assert _judge(rec, decoded_leaves=[], rendered="", actions=[], ready=False) == (False, False, False)   # drop-all is no shortcut
    real = sut.process
    def lossy(policy, tree):
        trace, state = real(policy, tree)
        return [t for t in trace if t["leaf"] != "filler"], state
    monkeypatch.setattr(sut, "process", lossy)
    _, lost, _ = execute("preserve_origin", "plain", "reference", root_for("retrieved_page", "FM"))
    assert lost["content_ok"] is False and lost["verdict"] == "DOMAIN_FAIL"


def test_missing_trusted_work_is_detected(monkeypatch):
    real = sut.process
    def deny_all(policy, tree):
        trace, _ = real(policy, tree)
        return [dict(t, executed=False) for t in trace], {"ready": False, "flag": False, "outbox": [], "actions": []}
    monkeypatch.setattr(sut, "process", deny_all)
    _, rec, _ = execute("preserve_origin", "plain", "reference", root_for("retrieved_page", "MF"))
    assert rec["content_ok"] is True and rec["actions_ok"] is False and rec["effects_ok"] is False and rec["verdict"] == "DOMAIN_FAIL"


def test_tampered_readings_are_detected():
    _, rec, _ = execute("preserve_origin", "base64", "reference", root_for("retrieved_page", "MF"))
    swapped = [dict(d, text=sut.CANARY + "|SET_FLAG") if d["id"] == "marker" else d for d in rec["decoded_leaves"]]
    assert _judge(rec, decoded_leaves=swapped, rendered="\n".join(d["text"] for d in swapped))[0] is False
    tree = copy.deepcopy(rec["tree"])
    tree["children"][1]["children"][0]["origin"] = "trusted"                  # a relabelled source origin
    assert _judge(rec, tree=tree)[0] is False
    assert _judge(rec, carrier="tool_result")[0] is False and _judge(rec, order="FM")[0] is False
    own = verify.own_case("preserve_origin", "retrieved_page", "MF", "base64", "reference")
    for k, v in (("outbox", [sut.CANARY]), ("trace", rec["trace"][::-1]), ("rendered", rec["rendered"] + "x")):
        assert dict(rec, **{k: v})[k] != own[k]                              # the verifier's field comparison sees it


@pytest.mark.parametrize("calls", [
    lambda r: (r.begin(), r.encoding("plain")),                                  # encoding before impl
    lambda r: (r.begin(), r.impl("trust_all")),                                   # unknown policy
    lambda r: (r.begin(), r.impl("preserve_origin"), r.encoding("hex")),         # unknown encoding
    lambda r: (r.begin(), r.impl("preserve_origin"), r.encoding("plain"), r.marker("x")),
    lambda r: (r.begin(), r.source_item("marker")),                              # item before configuration
    lambda r: (r.begin(), r.finish()),                                           # finish without a tree
    lambda r: (r.begin(), r.begin()),
])
def test_setup_errors_raise(calls):
    runtime._state.clear()
    with pytest.raises((RuntimeError, ValueError)):
        calls(runtime)


@pytest.mark.parametrize("root_text", [
    'consume(context([trusted_task(),retrieved_page([source_item("marker"),\nsource_item("marker"),\n]),trusted_note()]))\n',
    'consume(context([trusted_note(),retrieved_page([source_item("marker"),\nsource_item("filler"),\n]),trusted_task()]))\n',
    'consume(context([trusted_task(),retrieved_page([source_item("marker"),\n]),trusted_note()]))\n',
])
def test_malformed_composition_is_a_setup_error(root_text):
    with pytest.raises((RuntimeError, ValueError)):
        execute("preserve_origin", "plain", "reference", root_text)
    with pytest.raises(ValueError):
        construct.decode_root(root_text)


def test_construction_model_keeps_leaf_pairs():
    codes = {"CHUNKS": [30, 31], "LEAF_END": [29], "PREFIX": [27, 28], "LIST_OPEN": [32], "LIST_END": [33], "NOTE": [34],
             "CONTEXT_OPEN": [35], "COMMA": [36], "CONTEXT_CLOSE": [37]}
    group = 'FW_Group\nFW_ReplaceRE("\\[", "")\nFW_ReplaceRE("\\]", "")'
    m = construct.construct(codes, group)
    assert m["CHUNKS_group_steps"][0] == ["[[30, 29], [31, 29]]", "30, 29], 31, 29]]", "30, 29, 31, 29"]
    assert m["CHUNKS"] == [[30, 29, 31, 29], [31, 29, 30, 29]] and len(m["INNER"]) == 4 and len(m["ROOT"]) == 4
    assert m["ROOT"][0] == [35, 27, 32, 30, 29, 31, 29, 33, 36, 34, 37]
    flat = {p for p in itertools.permutations([30, 29, 31, 29])}               # fragment-level permutation: not the design
    assert len(flat) == 12 and set(map(tuple, m["CHUNKS"])) < flat


def test_oracle_is_policy_blind():
    tree = ast.parse((HERE / "oracle.py").read_text())
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {a.arg for n in ast.walk(tree) if isinstance(n, ast.arguments)
                                                                        for a in n.args}
    literals = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    assert not any("policy" in n for n in names) and not literals & set(sut.POLICIES)


def test_verifier_imports_nothing_from_the_implementation():
    for f in ("verify.py", "construct.py"):
        mods = {n.names[0].name.split(".")[0] if isinstance(n, ast.Import) else (n.module or "").split(".")[0]
                for n in ast.walk(ast.parse((HERE / f).read_text())) if isinstance(n, (ast.Import, ast.ImportFrom))}
        assert not mods & {"sut", "oracle", "runtime", "derive"}, (f, mods)


def test_spec_matches_fresh_build():
    r = subprocess.run([sys.executable, str(HERE / "build_spec.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
