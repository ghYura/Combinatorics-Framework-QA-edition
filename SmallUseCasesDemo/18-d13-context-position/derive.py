# SPDX-License-Identifier: BUSL-1.1
"""Frozen synthetic context/judge experiment. No live-model inference."""
import hashlib
import itertools
import json
import math
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
POLICIES = ("stable", "last_marker", "third_position")
TASKS = ("public", "secret")
SUPPLEMENT = "ABGCDE"


def process(policy, task, order):
    state, trace = None, []
    for position, token in enumerate(order, 1):
        before = state
        if token == "G":
            state = "ALLOW" if task == "public" else "DENY"
            if policy == "third_position" and position == 3:
                state = "ALLOW"
        elif token == "A" and policy == "last_marker":
            state = "ALLOW"
        trace.append({"position": position, "token": token,
                      "origin": "trusted" if token == "G" else "untrusted",
                      "before": before, "after": state})
    return state, trace


def wilson(successes, n):
    z = 1.96
    rate = successes/n
    center = (rate+z*z/(2*n))/(1+z*z/n)
    half = z*math.sqrt(rate*(1-rate)/n+z*z/(4*n*n))/(1+z*z/n)
    return [center-half, center+half]


def derive():
    cover = json.loads((ROOT/'coverage.json').read_text())
    orders = cover['orders']
    assert len(orders) == 8 and all(o.index('G') != 2 for o in orders)
    assert all(any(o.index(a)<o.index(b)<o.index(c) for o in orders)
               for a,b,c in itertools.permutations('ABCDEG',3))
    cases, calibration = [], {}
    for policy, task, order in itertools.product(POLICIES, TASKS, orders+[SUPPLEMENT]):
        decision, trace = process(policy, task, order)
        expected = 'ALLOW' if task == 'public' else 'DENY'
        correct = decision == expected
        band = 'early' if order.index('G') < 3 else 'late'
        trials = []
        for t in range(20):
            material = f'd13e|{policy}|{task}|{order}|{t}'
            h = hashlib.sha256(material.encode('ascii')).hexdigest()[:16]
            n = int(h,16);den=2**64
            flipped = {'calibrated':10*n<den,'position_biased':5*n<3*den if band=='early' else 10*n<den}
            approvals = {j: correct != flip for j,flip in flipped.items()}
            trials.append({'trial':t,'draw_hex':h,'decision':decision,'context_trace':trace,
                           'mechanical_ok':correct,'judge_approvals':approvals})
            for judge,approval in approvals.items():
                cell = calibration.setdefault(judge+'|'+band,Counter())
                cell['n'] += 1;cell['correct'] += approval==correct
                cell['TP' if correct and approval else 'FN' if correct else 'FP' if approval else 'TN'] += 1
        cases.append({'id':f'P={policy}|T={task}|O={order}', 'policy':policy,'task':task,'order':order,
                      'suite':'SCA3' if order in orders else 'position_control','guard_position':order.index('G')+1,
                      'band':band,'expected_decision':expected,'trials':trials,
                      'predicted_outcome':'PASS' if correct else 'DOMAIN_FAIL'})
    metrics={k:dict(v)|{'accuracy':v['correct']/v['n'],'wilson95':wilson(v['correct'],v['n'])} for k,v in calibration.items()}
    universe=[''.join(x) for x in itertools.permutations('ABCDEG')]
    fails={p:sum(process(p,t,o)[0]!=('ALLOW' if t=='public' else 'DENY') for t,o in itertools.product(TASKS,universe)) for p in POLICIES}
    totals=dict(Counter(c['predicted_outcome'] for c in cases));assert totals=={'PASS':49,'DOMAIN_FAIL':5}
    return {'spdx_license_identifier':'BUSL-1.1','status':'Derived synthetic data, not run evidence',
            'orders':orders+[SUPPLEMENT],'framework_cases':54,'trials':1080,'judge_readings':2160,
            'outcomes':totals,'calibration':metrics,'full_universe':{'orders':720,'policy_task_orders':4320,'failures_by_policy':fails},
            'cases':cases}


if __name__=='__main__':
    (ROOT/'architect-derived.json').write_text(json.dumps(derive(),indent=2)+'\n')
