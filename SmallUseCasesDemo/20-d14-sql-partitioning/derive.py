# SPDX-License-Identifier: BUSL-1.1
"""Independent finite SQL three-valued-logic/bag model; no database execution."""
from collections import Counter
from itertools import product
import json
from pathlib import Path

ITEMS = [
    {'id':1,'grp':'a','val':None,'flag':True},
    {'id':2,'grp':'a','val':0,'flag':False},
    {'id':3,'grp':'a','val':1,'flag':None},
    {'id':4,'grp':'b','val':1,'flag':True},
    {'id':5,'grp':'b','val':2,'flag':False},
    {'id':6,'grp':'b','val':None,'flag':None},
]
TAGS = [{'item_id':i,'tag':t} for i,t in ((1,'p'),(1,'q'),(3,'p'),(4,'p'),(4,'q'),(5,'p'))]
PREDICATES = {'gt0':'i.val > 0','eq1':'i.val = 1','flag':'i.flag',
              'and':'(i.val > 0) AND i.flag','or':'(i.val = 1) OR i.flag','is_null':'i.val IS NULL'}
QUERIES = ('scan','filtered','inner_join','left_join')
POLICIES = ('union_all','omit_unknown','dedup_union')


def truth(item, predicate):
    v,f=item['val'],item['flag']
    gt=None if v is None else v>0;eq=None if v is None else v==1
    if predicate=='gt0':return gt
    if predicate=='eq1':return eq
    if predicate=='flag':return f
    if predicate=='is_null':return v is None
    pair=(gt,f) if predicate=='and' else (eq,f)
    if predicate=='and':return False if False in pair else None if None in pair else True
    return True if True in pair else None if None in pair else False


def rows(query):
    if query=='scan':return ITEMS
    if query=='filtered':return [r for r in ITEMS if r['grp']=='a']
    out=[]
    for r in ITEMS:
        n=sum(t['item_id']==r['id'] for t in TAGS)
        out.extend([r]* (max(1,n) if query=='left_join' else n))
    return out


def canonical(values):
    return sorted([[v] for v in values],key=lambda row:(row[0] is not None,row[0] or 0))


def bag(rows_):
    counts=Counter(tuple(r) for r in rows_)
    return [{'row':list(k),'count':v} for k,v in sorted(counts.items(),key=lambda kv:(kv[0][0] is not None,kv[0][0] or 0))]


def sql(query,predicate):
    joins={'inner_join':' JOIN fixture.tags AS t ON t.item_id=i.id','left_join':' LEFT JOIN fixture.tags AS t ON t.item_id=i.id'}
    prefix='SELECT i.val FROM fixture.items AS i'+joins.get(query,'')
    base="i.grp = 'a'" if query=='filtered' else 'TRUE'
    p=PREDICATES[predicate]
    conditions={'base':base,'true':f'({base}) AND ({p})','false':f'({base}) AND NOT ({p})','unknown':f'({base}) AND (({p}) IS NULL)'}
    return {k:prefix+' WHERE '+v for k,v in conditions.items()}


def derive():
    cases=[]
    for policy,query,predicate in product(POLICIES,QUERIES,PREDICATES):
        source=rows(query)
        results={'base':canonical(r['val'] for r in source)}
        for name,value in (('true',True),('false',False),('unknown',None)):
            results[name]=canonical(r['val'] for r in source if truth(r,predicate) is value)
        selected=('true','false') if policy=='omit_unknown' else ('true','false','unknown')
        merged=[r[0] for name in selected for r in results[name]]
        if policy=='dedup_union':merged=set(merged)
        combined=canonical(merged);ok=bag(results['base'])==bag(combined)
        cases.append({'id':f'P={policy}|Q={query}|F={predicate}','policy':policy,'query':query,'predicate':predicate,
                      'sql':sql(query,predicate),'query_rows':results,'query_bags':{k:bag(v) for k,v in results.items()},
                      'combined_rows':combined,'combined_bag':bag(combined),'tlp_ok':ok,
                      'set_equal':{tuple(x) for x in results['base']}=={tuple(x) for x in combined},
                      'predicted_outcome':'PASS' if ok else 'DOMAIN_FAIL'})
    totals=dict(Counter(c['predicted_outcome'] for c in cases));assert totals=={'PASS':36,'DOMAIN_FAIL':36}
    return {'spdx_license_identifier':'BUSL-1.1','status':'Derived; no SQL has run','fixture':{'items':ITEMS,'tags':TAGS},
            'framework_cases':72,'families':24,'data_queries':288,'outcomes':totals,
            'by_policy':{p:dict(Counter(c['predicted_outcome'] for c in cases if c['policy']==p)) for p in POLICIES},'cases':cases}


if __name__=='__main__':
    Path(__file__).with_name('architect-derived.json').write_text(json.dumps(derive(),indent=2)+'\n')
