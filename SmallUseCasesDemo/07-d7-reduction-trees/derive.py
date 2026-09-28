# SPDX-License-Identifier: BUSL-1.1
"""the AI architect's bounded numerical preregistration; no Framework campaign execution."""
from pathlib import Path
from fractions import Fraction as Q
from collections import Counter
import math,json

def trees(lo,hi):
    if hi-lo==1: return [lo]
    return [(a,b) for k in range(lo+1,hi) for a in trees(lo,k) for b in trees(k,hi)]
def name(t):
    return str(t) if isinstance(t,int) else '('+name(t[0])+','+name(t[1])+')'
def fold(t,values):
    return values[t] if isinstance(t,int) else fold(t[0],values)+fold(t[1],values)
def rat(x):
    x=Q(x); return {'n':str(x.numerator),'d':str(x.denominator)}
if __name__=='__main__':
    raw={'small_integers':[1.,2.,3.,4.,5.], 'cancellation':[float(2**53),1.,-float(2**53),1.,1.],
         'swamped':[float(2**54),1.,1.,1.,-float(2**54)], 'decimal_inputs':[0.1,0.2,0.3,0.4,0.5]}
    naive_budgets={'small_integers':Q(0),'cancellation':Q(1,4),'swamped':Q(1),'decimal_inputs':Q(1,2**52)}
    all_trees=sorted(trees(0,5),key=name); cases=[]; vectors={}
    for vid,v in raw.items():
        exact=sum(map(Q,v),Q()); budget={'tree_binary64':naive_budgets[vid],'flat_fsum':Q(math.ulp(float(exact)))/2,'tree_rational':Q(0)}
        vectors[vid]={'hex':[x.hex() for x in v],'exact_sum':rat(exact),'absolute_budgets':{p:rat(b) for p,b in budget.items()}}
        for t in all_trees:
            for policy in budget:
                out=fold(t,v) if policy=='tree_binary64' else math.fsum(v) if policy=='flat_fsum' else fold(t,list(map(Q,v)))
                err=abs(Q(out)-exact); cases.append({'id':f'{policy}|V={vid}|T={name(t)}','policy':policy,'vector':vid,'tree':name(t),'predicted_result':rat(out),'predicted_hex':out.hex() if isinstance(out,float) else None,'absolute_error':rat(err),'budget':rat(budget[policy]),'predicted_outcome':'PASS' if err<=budget[policy] else 'DOMAIN_FAIL'})
    summary={p:dict(Counter(c['predicted_outcome'] for c in cases if c['policy']==p)) for p in ['tree_binary64','flat_fsum','tree_rational']}
    data={'spdx_license_identifier':'BUSL-1.1','status':'Derived host predictions, not Framework execution evidence','trees':[name(t) for t in all_trees],'vectors':vectors,'cases':cases,'outcomes':dict(Counter(c['predicted_outcome'] for c in cases)),'by_policy':summary}
    assert len(all_trees)==14 and len({c['id'] for c in cases})==168
    Path(__file__).with_name('architect-derived.json').write_text(json.dumps(data,indent=2)+'\n')
    print(json.dumps({'outcomes':data['outcomes'],'by_policy':summary,'binary64_by_vector':{v:dict(Counter(c['predicted_outcome'] for c in cases if c['policy']=='tree_binary64' and c['vector']==v)) for v in raw}}))
