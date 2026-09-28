# SPDX-License-Identifier: BUSL-1.1
"""the AI architect's preregistration: finite mathematics only, no Framework or SUT execution."""
from itertools import permutations, combinations
from pathlib import Path
import json

UNIVERSE = [''.join(p) for p in permutations('CFNQSV')]
PROJECTION = set('CFQS')
def trigger(p):
    return p.index('C') < p.index('N') < p.index('F') < p.index('S')
def obligations(p, family):
    if family.startswith('SCA'):
        return {''.join(t) for t in combinations(p, int(family[-1]))}
    if family == 'PROJ':
        p = ''.join(c for c in p if c in PROJECTION)
    return {p[i:i+2] for i in range(len(p)-1)}
def greedy(family, allowed):
    masks = {p:obligations(p,family) for p in UNIVERSE}
    remaining = set().union(*masks.values()); required = sorted(remaining); rows=[]
    while remaining:
        chosen = min(allowed, key=lambda p:(-len(masks[p]&remaining),p))
        assert masks[chosen]&remaining
        rows.append(chosen); remaining -= masks[chosen]
    witnesses={o:next(p for p in rows if o in masks[p]) for o in required}
    return {'family':family,'rows':rows,'size':len(rows),'required_obligations':required,
            'certificate':witnesses,'predicted_fault_orders':[p for p in rows if trigger(p)],
            'optimality':'not claimed'}
if __name__ == '__main__':
    suites={f:greedy(f,UNIVERSE) for f in ['SCA2','SCA3','ADJ2','PROJ']}
    suites['SCA3_counterexample']=greedy('SCA3',[p for p in UNIVERSE if not trigger(p)])
    faults=[p for p in UNIVERSE if trigger(p)]
    hidden=[p for p in faults if p.index('Q')>p.index('S')]
    assert len(UNIVERSE)==720 and len(faults)==30 and len(hidden)==6
    data={'spdx_license_identifier':'BUSL-1.1','status':'Derived preregistration, not execution evidence',
          'events':'CFNQSV','projection':'CFQS','universe':UNIVERSE,
          'case_ids':[f'C|{policy}|OPS={p}' for policy in ['correct','late_restart'] for p in UNIVERSE],
          'predicted_fault_orders':faults,'predicted_hidden_orders':hidden,
          'predicted_totals':{'PASS':1410,'DOMAIN_FAIL':30,'hidden_by_final_only':6},
          'suites':suites,'counterexample_selection':'Explicitly excludes the known trigger; logical counterexample, not held-out discovery.'}
    Path(__file__).with_name('architect-derived.json').write_text(json.dumps(data,indent=2)+'\n')
    print(json.dumps({k:{'size':v['size'],'obligations':len(v['required_obligations']),'hits':len(v['predicted_fault_orders'])} for k,v in suites.items()}))
