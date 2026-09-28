# SPDX-License-Identifier: BUSL-1.1
"""the AI architect preregistration: ordered ties and a deterministic static pagination model."""
from pathlib import Path
from itertools import product
from collections import Counter
import json
IDS='ABCD'; POLICIES=['stable_cursor','score_only_cursor','alternating_ties']
def key(ranks,i,direction,request,policy):
    s=1 if direction=='asc' else -1
    if policy=='score_only_cursor': return (s*ranks[i],)
    return (s*ranks[i],-i if policy=='alternating_ties' and request%2 else i)
def model(ranks,direction,policy):
    pages=[]; cursor=None; collected=[]
    for request in range(3):
        order=sorted(range(4),key=lambda i:key(ranks,i,direction,request,policy))
        if policy=='alternating_ties': page=order[2*request:2*request+2]
        else: page=[i for i in order if cursor is None or key(ranks,i,direction,request,policy)>cursor][:2]
        matrix=[[((key(ranks,i,direction,request,policy)>key(ranks,j,direction,request,policy))-(key(ranks,i,direction,request,policy)<key(ranks,j,direction,request,policy))) for j in range(4)] for i in range(4)]
        out_cursor=key(ranks,page[-1],direction,request,policy) if page and policy!='alternating_ties' else None
        pages.append({'request':request,'cursor_in':list(cursor) if cursor is not None else None,'offset':2*request if policy=='alternating_ties' else None,'full_order':[IDS[i] for i in order],'comparisons':matrix,'ids':[IDS[i] for i in page],'cursor_out':list(out_cursor) if out_cursor is not None else None})
        collected.extend(IDS[i] for i in page)
        if not page: break
        cursor=out_cursor
    expected=[IDS[i] for i in sorted(range(4),key=lambda i:((1 if direction=='asc' else -1)*ranks[i],i))]
    multiset=sorted(collected)==list(IDS)
    ordered=all((ranks[IDS.index(a)]<=ranks[IDS.index(b)] if direction=='asc' else ranks[IDS.index(a)]>=ranks[IDS.index(b)]) for a,b in zip(collected,collected[1:]))
    stable=all(IDS.index(a)<=IDS.index(b) for a,b in zip(collected,collected[1:]) if ranks[IDS.index(a)]==ranks[IDS.index(b)])
    return {'pages':pages,'collected':collected,'expected':expected,'multiset_ok':multiset,'primary_order_ok':ordered,'stable_ties_ok':stable,'terminated':not pages[-1]['ids'],'predicted_outcome':'PASS' if collected==expected and not pages[-1]['ids'] else 'DOMAIN_FAIL'}
if __name__=='__main__':
    weak=[r for r in product(range(4),repeat=4) if set(r)==set(range(max(r)+1))]; cases=[]
    for ranks in weak:
        code=''.join(map(str,ranks))
        for direction in ['asc','desc']:
            for policy in POLICIES:
                cases.append({'id':f'{policy}|D={direction}|R={code}','policy':policy,'direction':direction,'ranks':list(ranks),**model(ranks,direction,policy)})
    data={'spdx_license_identifier':'BUSL-1.1','status':'Derived predictions; no D8a run yet','input_ids':list(IDS),'page_size':2,'rank_vectors':[list(x) for x in weak],'cases':cases,'outcomes':dict(Counter(c['predicted_outcome'] for c in cases)),'by_policy':{p:dict(Counter(c['predicted_outcome'] for c in cases if c['policy']==p)) for p in POLICIES}}
    assert len(weak)==75 and len(cases)==450 and data['outcomes']=={'PASS':330,'DOMAIN_FAIL':120}
    Path(__file__).with_name('architect-derived.json').write_text(json.dumps(data,indent=2)+'\n'); print(json.dumps({'outcomes':data['outcomes'],'by_policy':data['by_policy']}))
