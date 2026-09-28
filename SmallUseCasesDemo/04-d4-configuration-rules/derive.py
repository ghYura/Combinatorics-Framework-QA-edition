# SPDX-License-Identifier: BUSL-1.1
from pathlib import Path
from itertools import product,combinations
from collections import Counter
import json
p=Path(__file__).resolve().parent
policies=['correct','drops_gzip','ignores_debug_rule']; axes=['env','mode','transport','features','workers','debug']
features=list(combinations(['audit','cache','gzip'],2))
def violations(c):
 return [k for k,bad in [
 ('R1',c['env']=='prod' and c['transport']=='http'),
 ('R2',c['mode']=='live' and 'cache' in c['features']),
 ('R3',c['mode']=='live' and c['workers']<2),
 ('R4',c['env']=='prod' and not set(c['features'])<=set(['audit','gzip'])),
 ('R5',c['mode']=='batch' and 'audit' in c['features'] and c['workers']<2),
 ('R6',c['env']=='prod' and c['debug'])] if bad]
def key(c):
 return '|'.join(f'{k}={"+".join(c[k]) if k=="features" else int(c[k]) if k=="debug" else c[k]}' for k in axes)
mandatory=[dict(zip(axes,(*v,False))) for v in product(['dev','prod'],['batch','live'],['http','https'],features,[1,2])]
expanded=[dict(c,debug=d) for c in mandatory for d in [False,True]]
valid=sorted([c for c in expanded if not violations(c)],key=key)
controls=[next(c for c in sorted(expanded,key=key) if violations(c)==[rule]) for rule in ['R1','R2','R3','R4','R5','R6']]
cases=[]
for phase, configs in [('main',valid),('controls',controls)]:
 for c in configs:
  bad=violations(c)
  for policy in policies:
   accept=not [r for r in bad if not(policy=='ignores_debug_rule' and r=='R6')]
   outcome='DOMAIN_FAIL' if accept==bool(bad) or (accept and policy=='drops_gzip' and 'gzip' in c['features']) else 'PASS'
   cases.append({'id':phase+'|'+policy+'|'+key(c),'phase':phase,'policy':policy,'config':c,'violations':bad,'expected_acceptance':not bad,'predicted_acceptance':accept,'predicted_outcome':outcome})
mandatory_counts=[48*3]; remaining=mandatory[:]
for rule in ['R1','R2','R3','R4','R5']:
 remaining=[c for c in remaining if rule not in violations(c)]; mandatory_counts.append(3*len(remaining))
def obligations(c):
 return {f'{a}={('+'.join(c[a]) if a=='features' else str(int(c[a])) if a=='debug' else str(c[a]))}|{b}={('+'.join(c[b]) if b=='features' else str(int(c[b])) if b=='debug' else str(c[b]))}' for a,b in combinations(axes,2)}
needed=set().union(*(obligations(c) for c in valid)); missing=set(needed); rows=[]
while missing:
 c=min(valid,key=lambda c:(-len(obligations(c)&missing),key(c))); rows.append(key(c)); missing-=obligations(c)
frozen={'spdx_license_identifier':'BUSL-1.1','status':'Derived preregistration; no D4 campaign has run',
 'axes':axes,'policies':policies,'mandatory_rule_order':['R1','R2','R3','R4','R5'],'deferred_rules':['R6'],
 'counts':{'raw_mandatory':144,'raw_with_optional':288,'sequential_mandatory_survivors':mandatory_counts,'per_rule_raw_matches':{r:sum(r in violations(c) for c in mandatory)*3 for r in ['R1','R2','R3','R4','R5']},'post_mandatory_sieve':len(remaining)*3,'reader_expanded':len(remaining)*6,'reader_retained':len(valid)*3,'controls':18},
 'outcomes':{phase:dict(Counter(c['predicted_outcome'] for c in cases if c['phase']==phase)) for phase in ['main','controls']},
 'valid_configurations':valid,'invalid_controls':controls,'cases':cases,
 'pairwise':{'scope':'Feasible pairs across six categorical axes; features is one unordered-pair level','obligations':sorted(needed),'rows':rows,'selection':'Greedy maximum uncovered gain; ties by configuration key; no optimality claim'},
 'wrong_sieve':{'rule':'forbid gzip for both modes','removed_legal_candidates':sum('gzip' in c['config']['features'] for c in cases if c['phase']=='main'),'remaining_candidates':sum('gzip' not in c['config']['features'] for c in cases if c['phase']=='main'),'remaining_domain_fail':sum(c['predicted_outcome']=='DOMAIN_FAIL' and 'gzip' not in c['config']['features'] for c in cases if c['phase']=='main')}}
assert len(valid)==22 and len(cases)==84 and frozen['outcomes']=={'main':{'PASS':48,'DOMAIN_FAIL':18},'controls':{'PASS':17,'DOMAIN_FAIL':1}}
(p/'architect-derived.json').write_text(json.dumps(frozen,indent=2)+'\n')
print(json.dumps({'counts':frozen['counts'],'outcomes':frozen['outcomes'],'pairwise_rows':len(rows),'pairwise_obligations':len(needed)}))
