# SPDX-License-Identifier: BUSL-1.1
"""Preregistered tiny-language compiler/interpreter experiment, not run evidence."""
from collections import Counter
from itertools import product
import json
from pathlib import Path

POLICIES = ("faithful", "reverse_sub", "alias_dead_temp")


def expression(shape, a, b):
    x, y = {"var": "x"}, {"var": "y"}
    node = lambda op,l,r: {"op":op,"left":l,"right":r}
    return node(b,node(a,x,y),x) if shape == 'L' else node(a,x,node(b,y,x))


def interpret(program):
    env = {d['name']:d['value'] for d in program['bindings']}
    def visit(n):
        if 'var' in n:
            return env[n['var']]
        l,r=visit(n['left']),visit(n['right'])
        return l+r if n['op']=='+' else l-r if n['op']=='-' else l*r
    return visit(program['expr'])


def compile_program(program, policy):
    code=[]
    for d in program['bindings']:
        name='x' if policy=='alias_dead_temp' and d['name']=='z' else d['name']
        code += [['PUSH',d['value']],['STORE',name]]
    def emit(n):
        if 'var' in n:
            code.append(['LOAD',n['var']]);return
        sides=('right','left') if policy=='reverse_sub' and n['op']=='-' else ('left','right')
        for side in sides:
            emit(n[side])
        code.append([{'+':'ADD','-':'SUB','*':'MUL'}[n['op']]])
    emit(program['expr']);return code+[['RETURN']]


def execute(code):
    stack,env,trace,result=[],{},[],None
    for ip,ins in enumerate(code):
        op=ins[0]
        if op=='PUSH':stack.append(ins[1])
        elif op=='STORE':env[ins[1]]=stack.pop()
        elif op=='LOAD':stack.append(env[ins[1]])
        elif op=='RETURN':
            assert len(stack)==1 and ip==len(code)-1
            result=stack.pop()
        else:
            r,l=stack.pop(),stack.pop()
            stack.append(l+r if op=='ADD' else l-r if op=='SUB' else l*r)
        trace.append({'ip':ip,'instruction':ins,'stack':list(stack),'locals':dict(env),'returned':result})
    return result,trace


def derive():
    cases=[]
    for policy,order,shape,x,y,a,b in product(POLICIES,('XY','YX'),('L','R'),(-1,2),(-1,2),'+-*','+-*'):
        env={'x':x,'y':y};bindings=[{'name':v.lower(),'value':env[v.lower()]} for v in order]
        expr=expression(shape,a,b)
        programs={'original':{'bindings':bindings,'expr':expr},
                  'transformed':{'bindings':[bindings[0],{'name':'z','value':7},bindings[1]],'expr':expr}}
        observations={}
        for kind,program in programs.items():
            code=compile_program(program,policy);value,trace=execute(code)
            observations[kind]={'program':program,'reference_value':interpret(program),'bytecode':code,'vm_value':value,'vm_trace':trace}
        o,t=observations['original'],observations['transformed']
        assert o['reference_value']==t['reference_value']
        checks={'original_differential':o['vm_value']==o['reference_value'],
                'transformed_differential':t['vm_value']==t['reference_value'],
                'metamorphic':o['vm_value']==t['vm_value']}
        cases.append({'id':f'P={policy}|O={order}|H={shape}|X={x}|Y={y}|A={a}|B={b}',
                      'policy':policy,'order':order,'shape':shape,'x':x,'y':y,'op_a':a,'op_b':b,
                      'observations':observations,'checks':checks,'predicted_outcome':'PASS' if all(checks.values()) else 'DOMAIN_FAIL'})
    assert len(cases)==432
    totals=dict(Counter(c['predicted_outcome'] for c in cases))
    return {'spdx_license_identifier':'BUSL-1.1','status':'Derived, not execution evidence','cases':cases,'outcomes':totals,
            'by_policy':{p:dict(Counter(c['predicted_outcome'] for c in cases if c['policy']==p)) for p in POLICIES},
            'failed_checks':{p:{k:sum(not c['checks'][k] for c in cases if c['policy']==p) for k in ('original_differential','transformed_differential','metamorphic')} for p in POLICIES}}


if __name__=='__main__':
    Path(__file__).with_name('architect-derived.json').write_text(json.dumps(derive(),indent=2)+'\n')
