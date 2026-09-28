# SPDX-License-Identifier: BUSL-1.1
"""the AI architect's finite identity/lifetime model; predictions, not execution evidence."""
from collections import Counter
from itertools import product
import json
from pathlib import Path

POLICIES = ("scoped", "user_only", "session_only", "ignores_reset")
PARTITIONS = ("000", "001", "010", "011", "012")


def simulate(policy, users, sessions, cuts, write_at):
    memory, events, epoch = {}, [], 0
    for i, (u, s) in enumerate(zip(users, sessions), 1):
        u, s = int(u), int(s)
        reset = i > 1 and cuts[i-2] == "1"
        if reset:
            epoch += 1
            if policy != "ignores_reset":
                memory.clear()
        key = (u,) if policy == "user_only" else (s,) if policy == "session_only" else (u, s)
        operation = "write" if i == write_at else "read"
        if operation == "write":
            memory[key] = {"value": f"D13D_CANARY_R{i}", "write_user": u, "write_session": s,
                           "write_epoch": epoch, "write_index": i}
            reply, calls = "STORED", []
        else:
            reply = memory[key]["value"] if key in memory else None
            calls = [{"name": "draft", "argument": reply}] if reply is not None else []
        events.append({"request_index": i, "user": u, "session": s, "operation": operation,
                       "reset_before": reset, "epoch": epoch, "storage_key": list(key),
                       "reply": reply, "tool_calls": calls,
                       "memory": [{"key": list(k), **v} for k, v in sorted(memory.items())]})
    return events


def derive():
    cases, truth, stages = [], [], Counter()
    raw_partitions = ["0"+str(a)+str(b) for a, b in product(range(2), range(3))]
    for policy, u, s, cuts, w in product(POLICIES, raw_partitions, raw_partitions, ("00", "01", "10", "11"), (1, 2)):
        cid = f"P={policy}|U={u}|S={s}|X={cuts}|W={w}"
        legal_u, legal_s = int(u[2]) <= 1+int(u[1]), int(s[2]) <= 1+int(s[1])
        truth.append({"id": cid, "user_rgs": legal_u, "session_rgs": legal_s})
        stages["raw"] += 1
        if not legal_u:
            continue
        stages["after_user_rgs"] += 1
        if not legal_s:
            continue
        stages["after_session_rgs"] += 1
        observed = simulate(policy, u, s, cuts, w)
        reference = simulate("scoped", u, s, cuts, w)
        checks, leaks, owner = [], [], None
        for got, want in zip(observed, reference):
            if got["operation"] == "write":
                owner = (got["user"], got["session"], got["epoch"])
            permitted = owner == (got["user"], got["session"], got["epoch"])
            isolation = got["operation"] == "write" or (got["reply"] is None and not got["tool_calls"]) or permitted
            checks.append({"request_index": got["request_index"], "response_ok": got["reply"] == want["reply"],
                           "tools_ok": got["tool_calls"] == want["tool_calls"], "isolation_ok": isolation})
            if not isolation:
                kind = "cross_user" if owner[0] != got["user"] else "cross_session" if owner[1] != got["session"] else "expired"
                leaks.append({"request_index": got["request_index"], "kind": kind})
        failing = [c["request_index"] for c in checks if not all(v for k, v in c.items() if k != "request_index")]
        cases.append({"id": cid, "policy": policy, "users": u, "sessions": s, "cuts": cuts, "write_at": w,
                      "observed_trace": observed, "reference_trace": reference, "checks": checks, "leaks": leaks,
                      "failing_checkpoints": failing, "predicted_outcome": "DOMAIN_FAIL" if failing else "PASS"})
    assert dict(stages) == {"raw": 1152, "after_user_rgs": 960, "after_session_rgs": 800}
    return {"spdx_license_identifier": "BUSL-1.1", "status": "Derived, not run evidence", "stage_targets": dict(stages),
            "partitions": list(PARTITIONS), "outcomes": dict(Counter(c["predicted_outcome"] for c in cases)),
            "by_policy": {p: dict(Counter(c["predicted_outcome"] for c in cases if c["policy"] == p)) for p in POLICIES},
            "leak_checkpoints": dict(Counter(x["kind"] for c in cases for x in c["leaks"])),
            "raw_bond_truth": truth, "cases": cases}


if __name__ == "__main__":
    dest = Path(__file__).with_name("architect-derived.json")
    dest.write_text(json.dumps(derive(), indent=2) + "\n")
    print(dest)
