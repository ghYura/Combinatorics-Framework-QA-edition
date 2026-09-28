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


"""D15 sandbox preflight: real worker subprocesses, persistence and restart under generated-default.

    python preflight.py              # writes evidence/preflight-<stamp>/preflight.json

Runs, through the Framework's own Executor sandbox (generated-default: container, network none, read-only
root, tmpfs scratch, python:3-slim, the Executor's runner shape), candidates composed exactly as the Reader
renders them from spec/ (HEAD + atoms + TAIL, a FAIL row's values back to back):
  * three fault-free controls, one per implementation: all ACK, every node counts (1,1,1), value 111, WAL
    o1:a1, o2:a1, o3:a1 (outside the campaign denominator);
  * the largest restart cases (all three replicas killed and reopened), whose semantic fields must equal the
    frozen predictions: P=replay_twice|F=012|C=2|K=crash|R=fresh and P=volatile_ack|F=012|C=3|K=crash|R=stable.
Each record carries the inlined source hashes, so run_demo.py can check the preflight used today's code.
"""
import base64
import datetime
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
import build_spec  # noqa: E402

RUNNER = ("import runpy,sys\n"
          "ns = runpy.run_path(sys.argv[1], run_name='__main__')\n"
          "print('__FWV__ %d %d' % (int(ns.get('FW_VAR', -999)), int(ns.get('FW_CUSTOM_VAR', -999))))\n")
CASES = ("P=replay_twice|F=012|C=2|K=crash|R=fresh", "P=volatile_ack|F=012|C=3|K=crash|R=stable")
SEMANTIC = ("id", "policy", "failed", "cut", "kind", "retry", "attempts", "trace", "acknowledged", "checks")


def compose(pick=None, control=None):
    sources = {m: (HERE / f"{m}.py").read_text(encoding="utf-8") for m in build_spec.MODULES}
    head, digests = build_spec.head_value(sources)
    slots, _ = build_spec.layout(head)
    if control:
        return head + f"FW_VAR = d13.control({control!r})\nFW_CUSTOM_VAR = FW_VAR\n", digests
    cells = [[v for v in s[1] if s[0] not in pick or v in pick[s[0]]] if s[0] in pick else [s[1][0]] for s in slots]
    parts = []
    for i, (vals, s) in enumerate(zip(cells, slots)):
        parts += ["".join(vals), s[2] if (s[2] or i == len(slots) - 1) else "\n"]
    return "".join(parts), digests


def pick_for(cid):
    f = dict(x.split("=", 1) for x in cid.split("|"))
    return {"IMPL": [f'impl("{f["P"]}");'], "FAIL": [f"fail({n});" for n in f["F"]], "CUT": [f"cut({f['C']});"],
            "KIND": [f'fault("{f["K"]}");'], "RETRY": [f'retry("{f["R"]}");']}


def sandbox():
    sys.path.insert(0, str(REPO / "generator_trunk"))
    sys.path.insert(0, str(REPO / "Executor_trunk"))
    from bundle.policy import policy_to_dict, resolve_policy
    import sandbox as sbx
    doc = dict(policy_to_dict(resolve_policy("generated-default")))
    return sbx.build_sandbox(doc, runner=RUNNER, host_python=sys.executable, image=os.environ.get("BUNDLE_SANDBOX_IMAGE", "python:3-slim")), doc


def run(box, text, tmp, name):
    path = Path(tmp) / name
    path.write_text(text, encoding="utf-8")
    path.chmod(0o644)
    res = box.run(path, [])
    line = next((l for l in (res.stdout or "").splitlines() if l.startswith("app=")), "")
    tokens = dict(t.split("=", 1) for t in line.split() if "=" in t)
    rec = json.loads(base64.urlsafe_b64decode(tokens["rec"])) if "rec" in tokens else None
    return {"candidate": name, "candidate_sha256": hashlib.sha256(text.encode()).hexdigest(), "exit_code": res.returncode,
            "timed_out": res.timed_out, "spawn_error": res.spawn_error, "stderr_tail": (res.stderr or "")[-600:],
            "rec_sha256": tokens.get("rec_sha256"), "record": rec}


def main():
    frozen = {c["id"]: c for c in json.loads((HERE / "architect-derived.json").read_text())["cases"]}
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = HERE / "evidence" / f"preflight-{stamp}"
    out.mkdir(parents=True)
    box, policy = sandbox()
    results, digests = {"controls": [], "restart_cases": []}, None
    try:
        with tempfile.TemporaryDirectory(dir=HERE) as tmp:
            for impl in ("durable", "volatile_ack", "replay_twice"):
                text, digests = compose(control=impl)
                r = run(box, text, tmp, f"control_{impl}.py")
                r["ok"] = r["exit_code"] == 0 and bool(r["record"]) and r["record"]["ok"] is True
                results["controls"].append(r)
            for cid in CASES:
                text, digests = compose(pick=pick_for(cid))
                r = run(box, text, tmp, cid.replace("|", "_").replace("=", "-") + ".py")
                rec = r["record"] or {}
                r["semantic_equals_frozen"] = all(rec.get(k) == frozen[cid][k] for k in SEMANTIC) and rec.get("verdict") == frozen[cid]["predicted_outcome"]
                r["restarts"] = sum(e["event"] == "start" and e["generation"] == 1 for e in rec.get("provenance", {}).get("events", []))
                r["kills"] = [e["returncode"] for e in rec.get("provenance", {}).get("events", []) if e["event"] == "kill"]
                r["ok"] = r["exit_code"] == 0 and r["semantic_equals_frozen"] and r["restarts"] == 3 and r["kills"] == [-9, -9, -9]
                results["restart_cases"].append(r)
    finally:
        box.close()
    doc = {"schema": "d15.preflight/v1", "stamp": stamp, "sandbox": box.describe(), "policy": policy, "module_sha256": digests,
           "ok": all(r["ok"] for part in results.values() for r in part), **results,
           "note": "outside the campaign denominator; three controls + two all-node restart cases"}
    (out / "preflight.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"stamp": stamp, "ok": doc["ok"], "controls": [(r["candidate"], r["ok"]) for r in results["controls"]],
                      "restart_cases": [(r["candidate"], r["ok"], r["restarts"], r["kills"]) for r in results["restart_cases"]]}, indent=1))
    raise SystemExit(0 if doc["ok"] else 1)


if __name__ == "__main__":
    main()
