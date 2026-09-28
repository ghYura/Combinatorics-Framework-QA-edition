# SPDX-License-Identifier: BUSL-1.1
"""the AI architect preregistration; no Framework or SUT execution."""
from pathlib import Path
from itertools import product
from collections import Counter
import json

def op(code,v):
    return {'A':v+1,'M':2*v,'S':v-3,'N':-v}[code]
def scope(field,*children):
    return {'scope':field,'children':list(children)}
def tree(z,c,t):
    return [scope('x',scope('y',z,'N')),'S',scope('x',c),t]
def evaluate(nodes,policy):
    record={'x':2,'y':5}; current='x'
    def walk(items,field):
        nonlocal current
        for node in items:
            if isinstance(node,str):
                target=current if policy=='leak_scope' else field
                record[target]=op(node,record[target])
            elif policy=='flatten_scope':
                walk(node['children'],field)
            elif policy=='leak_scope':
                current=node['scope']; walk(node['children'],current)
            else:
                walk(node['children'],node['scope'])
    walk(nodes,'x')
    return record

if __name__=='__main__':
    policies=['correct','flatten_scope','leak_scope']; trees=[]; cases=[]
    for z,c,t in product('AM','AM','NS'):
        tid=f'ZIP={z}|CAT={c}|TAIL={t}'; ast=tree(z,c,t); expected=evaluate(ast,'correct')
        trees.append({'id':tid,'tree':ast,'expected':expected})
        for policy in policies:
            observed=evaluate(ast,policy)
            cases.append({'id':f'B1|{policy}|{tid}','policy':policy,'tree_id':tid,'tree':ast,'expected':expected,'predicted':observed,'predicted_outcome':'PASS' if observed==expected else 'DOMAIN_FAIL'})
    bundles=[]
    for policy in policies:
        predictions={t['id']:evaluate(t['tree'],policy) for t in trees}
        bundles.append({'id':f'B2|{policy}|BUNDLE=all8','policy':policy,'predicted':predictions,'predicted_outcome':'PASS' if all(predictions[t['id']]==t['expected'] for t in trees) else 'DOMAIN_FAIL'})
    data={'spdx_license_identifier':'BUSL-1.1','status':'Derived; no phase-B runs yet','input':{'x':2,'y':5},'trees':trees,'B1_cases':cases,'B2_cases':bundles,
          'counts':{'E1':2,'E2_after_subsets':8,'E2_after_identity':7,'E3':2,'JZIP':2,'JCAT':4,'ROOT':8,'B1_candidates':24,'BUNDLE':1,'B2_candidates':3},
          'outcomes':{'B1':dict(Counter(c['predicted_outcome'] for c in cases)),'B2':dict(Counter(c['predicted_outcome'] for c in bundles))}}
    assert data['outcomes']=={'B1':{'PASS':8,'DOMAIN_FAIL':16},'B2':{'PASS':1,'DOMAIN_FAIL':2}}
    Path(__file__).with_name('architect-derived.json').write_text(json.dumps(data,indent=2)+'\n')
    print(json.dumps({'counts':data['counts'],'outcomes':data['outcomes']}))
