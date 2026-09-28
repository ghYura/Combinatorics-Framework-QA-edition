# SPDX-License-Identifier: BUSL-1.1
"""the AI architect's preregistered finite model; not a runtime implementation or run evidence."""
from collections import Counter
from itertools import product
import json
from pathlib import Path

POLICIES = ("compare_version", "trust_offer", "overwrite_owner")
MODES = ("independent", "after_A_offer")


def enabled(counts, mode):
    return [a for a in "AB" if counts[a] < 2
            and not (a == "B" and counts[a] == 0 and mode == "after_A_offer" and counts["A"] == 0)]


def feasible(word, mode):
    counts = dict.fromkeys("AB", 0)
    for a in word:
        if a not in enabled(counts, mode):
            return False
        counts[a] += 1
    return counts == {"A": 2, "B": 2}


def preemptions(word):
    return sum(word[i] != word[i+1] and word[:i+1].count(word[i]) < 2 for i in range(3))


def trace(word, mode, policy):
    counts = dict.fromkeys("AB", 0)
    offers, allocations, issued = {}, {}, {}
    version = 0
    events = []
    for index, agent in enumerate(word, 1):
        ready = enabled(counts, mode)
        assert agent in ready
        counts[agent] += 1
        kind = "inspect" if counts[agent] == 1 else "commit"
        request = {"id": f"{agent}:{kind}", "agent": agent, "kind": kind, "resource": "R"}
        if kind == "inspect":
            response = {"available": not allocations, "version": version}
            offers[agent] = dict(response)
        else:
            offer = offers[agent]
            request.update(offer_version=offer["version"], offer_available=offer["available"])
            status = "BUSY" if not offer["available"] else "GRANTED"
            if status == "GRANTED" and policy == "compare_version" and (allocations or version != offer["version"]):
                status = "STALE"
            ticket = f"R:{agent}" if status == "GRANTED" else None
            response = {"status": status, "ticket": ticket}
            if ticket:
                if policy == "overwrite_owner":
                    allocations.clear()
                allocations[agent] = ticket
                issued[agent] = ticket
                version += 1
        events.append(json.loads(json.dumps({
            "index": index, "agent": agent, "local_step": counts[agent],
            "message": request["id"], "enabled_agents_before": ready,
            "request": request, "response": response, "offers": offers,
            "version": version, "allocations": allocations, "issued_grants": issued,
        })))
    return events


def derive():
    words = ["".join(w) for w in product("AB", repeat=4)]
    cases, truth = [], []
    stages = Counter()
    for policy, mode, cap, word in product(POLICIES, MODES, range(3), words):
        a = [int(x == "A") for x in word]
        two = sum(a) == 2
        causal = mode == "independent" or a[0] == 1
        expr = int(a[0] != a[1]) + int(a[1] != a[2] and a[0] != a[1]) + int(a[2] != a[3] and a[0] != a[2] and a[1] != a[2])
        bound = expr <= cap
        cid = f"P={policy}|M={mode}|K={cap}|S={word}"
        truth.append({"id": cid, "two_each": two, "causal_ready": causal, "preemption_cap": bound})
        stages["raw"] += 1
        if not two:
            continue
        stages["after_two_each"] += 1
        assert causal == feasible(word, mode)
        assert expr == preemptions(word)
        if not causal:
            continue
        stages["after_causal_ready"] += 1
        if not bound:
            continue
        stages["after_preemption_cap"] += 1
        observed, reference = trace(word, mode, policy), trace(word, mode, "compare_version")
        checks = []
        for got, want in zip(observed, reference):
            checks.append({"index": got["index"], "capacity_ok": len(got["allocations"]) <= 1,
                           "exclusive_promises_ok": len(got["issued_grants"]) <= 1,
                           "commitments_ok": got["allocations"] == got["issued_grants"],
                           "reference_ok": got == want})
        failing = [x["index"] for x in checks if not all(v for k, v in x.items() if k != "index")]
        cases.append({"id": cid, "policy": policy, "mode": mode, "cap": cap, "schedule": word,
                      "preemptions": preemptions(word), "context_switches": sum(word[i] != word[i+1] for i in range(3)),
                      "observed_trace": observed, "reference_trace": reference, "checks": checks,
                      "failing_checkpoints": failing, "predicted_outcome": "DOMAIN_FAIL" if failing else "PASS"})
    assert dict(stages) == {"raw": 288, "after_two_each": 108, "after_causal_ready": 81, "after_preemption_cap": 54}
    totals = dict(Counter(c["predicted_outcome"] for c in cases))
    assert totals == {"PASS": 36, "DOMAIN_FAIL": 18}
    return {"spdx_license_identifier": "BUSL-1.1", "status": "Derived, not run evidence", "stage_targets": dict(stages),
            "outcomes": totals, "by_policy": {p: dict(Counter(c["predicted_outcome"] for c in cases if c["policy"] == p)) for p in POLICIES},
            "by_cap": {k: dict(Counter(c["predicted_outcome"] for c in cases if c["cap"] == k)) for k in range(3)},
            "feasible_schedules": {m: [w for w in words if feasible(w, m)] for m in MODES},
            "raw_bond_truth": truth, "cases": cases}


if __name__ == "__main__":
    target = Path(__file__).with_name("architect-derived.json")
    target.write_text(json.dumps(derive(), indent=2) + "\n")
    print(target)
