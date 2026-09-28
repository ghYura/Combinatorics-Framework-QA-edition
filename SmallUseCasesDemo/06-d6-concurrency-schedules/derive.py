# SPDX-License-Identifier: BUSL-1.1
"""the AI architect's finite schedule preregistration, independent of Framework/SUT execution."""
from pathlib import Path
from itertools import product
from collections import Counter
import json

def preempt(seq):
    seen=Counter(); n=0
    for i,t in enumerate(seq):
        seen[t]+=1
        if i+1<len(seq) and seq[i+1]!=t and seen[t]<2: n+=1
    return n

def counter(seq,policy):
    seen=Counter(); local={}; value=0; trace=[]
    for t in seq:
        seen[t]+=1
        if seen[t]==1: local[t]=value; op='read'
        else: value=(value if policy=='atomic_commit' else local[t])+1; op='write'
        trace.append({'thread':t,'op':op,'counter':value,'locals':dict(local)})
    return trace

def queue(seq,policy):
    seen=Counter(); items=[]; published=False; result=None; trace=[]
    for i,t in enumerate(seq):
        seen[t]+=1
        if t=='C' and seen[t]==1 and not items: return None,i+1
        if t=='P' and seen[t]==1: items.append('item'); op='enqueue'
        elif t=='P': published=bool(items); op='publish'
        elif seen[t]==1: op='wait_readable'
        else:
            op='try_pop'
            result=items.pop(0) if items and (policy=='actual_queue' or published) else 'EMPTY'
        trace.append({'thread':t,'op':op,'items':list(items),'published_nonempty':published,'pop_result':result})
    return trace,None

if __name__=='__main__':
    schedules=[''.join(s) for s in product('AB',repeat=4) if s.count('A')==2]; c=[]
    for cap in range(3):
        for seq in schedules:
            if preempt(seq)>cap: continue
            for policy in ['atomic_commit','split_rw']:
                obs=counter(seq,policy); expected=counter(seq,'atomic_commit')
                fails=[i+1 for i,(o,e) in enumerate(zip(obs,expected)) if o['counter']!=e['counter']]
                c.append({'id':f'counter|{policy}|CAP={cap}|SEQ={seq}','policy':policy,'cap':cap,'schedule':seq,'context_switches':sum(a!=b for a,b in zip(seq,seq[1:])),'preemptions':preempt(seq),'predicted_trace':obs,'reference_trace':expected,'failing_checkpoints':fails,'predicted_outcome':'DOMAIN_FAIL' if fails else 'PASS'})
    q=[]; rejected=[]
    for seq in [''.join(s) for s in product('PC',repeat=4) if s.count('P')==2]:
        ref,blocked=queue(seq,'actual_queue')
        if blocked: rejected.append({'schedule':seq,'first_disabled_step':blocked}); continue
        for policy in ['actual_queue','stale_empty']:
            obs,_=queue(seq,policy); fails=[i+1 for i,(o,e) in enumerate(zip(obs,ref)) if (o['items'],o['pop_result'])!=(e['items'],e['pop_result'])]
            q.append({'id':f'queue|{policy}|SEQ={seq}','policy':policy,'schedule':seq,'predicted_trace':obs,'reference_trace':ref,'failing_checkpoints':fails,'predicted_outcome':'DOMAIN_FAIL' if fails else 'PASS'})
    data={'spdx_license_identifier':'BUSL-1.1','status':'Derived predictions; no D6 run yet','counter_schedules':schedules,'counter_counts':{'raw':96,'after_two_each':36,'after_cap':24,'schedules_by_cap':{'0':2,'1':4,'2':6}},'queue_counts':{'raw':32,'after_two_each':12,'after_enabled':6,'feasible_schedules':3},'queue_rejected':rejected,'counter_cases':c,'queue_cases':q,'outcomes':{'counter':dict(Counter(x['predicted_outcome'] for x in c)),'queue':dict(Counter(x['predicted_outcome'] for x in q))}}
    assert len(c)==24 and len(q)==6 and data['outcomes']=={'counter':{'PASS':18,'DOMAIN_FAIL':6},'queue':{'PASS':5,'DOMAIN_FAIL':1}}
    Path(__file__).with_name('architect-derived.json').write_text(json.dumps(data,indent=2)+'\n')
    print(json.dumps({'outcomes':data['outcomes'],'rejected':rejected}))
