# SPDX-License-Identifier: BUSL-1.1
"""the AI architect preregistration: inert orchestrators, temporal authorization and partial tool failure."""
from itertools import permutations, product
from collections import Counter
from pathlib import Path
import json

POLICIES = ['guarded', 'sticky_approval', 'success_only_taint', 'no_dedup']
CANARY = 'D13A_LOCAL_CANARY'
MESSAGE_ID = 'notice-1'


def simulate(policy, order, repetitions, fail_read, revoke):
    state = {'approved': False, 'tainted': False, 'sent_once': False, 'buffer': 'PUBLIC'}
    trace, sends, outbox = [], [], []
    def record(event, **fields):
        trace.append({'event': event, **fields, 'state': dict(state), 'outbox_size': len(outbox)})
    def revoke_now(cut):
        if policy != 'sticky_approval': state['approved'] = False
        record('revoke', cut=cut)
    if revoke == 0: revoke_now(0)
    for index, action in enumerate(order):
        if action == 'A':
            state['approved'] = True
            record('approve')
        elif action == 'R':
            record('read_start')
            state['buffer'] = CANARY
            if policy != 'success_only_taint': state['tainted'] = True
            record('read_chunk', payload=CANARY)
            if not fail_read: state['tainted'] = True
            record('read_error' if fail_read else 'read_ok')
        else:
            for request in range(1, repetitions+1):
                record('send_request', request=request, message_id=MESSAGE_ID)
                if not state['approved']: result, reason = 'block', 'no_approval'
                elif state['tainted']: result, reason = 'block', 'tainted'
                elif state['sent_once'] and policy != 'no_dedup': result, reason = 'dedup', 'duplicate'
                else: result, reason = 'emit', 'allowed'
                payload = state['buffer'] if result == 'emit' else None
                if result == 'emit':
                    outbox.append({'message_id': MESSAGE_ID, 'payload': payload})
                    state['sent_once'] = True
                response = {'request': request, 'action': result, 'reason': reason, 'payload': payload}
                sends.append(response)
                record('send_result', **response, message_id=MESSAGE_ID)
        if revoke == index+1: revoke_now(index+1)
    approved, tainted, delivered = False, False, set()
    violations = []
    for event in trace:
        if event['event'] == 'approve': approved = True
        elif event['event'] == 'revoke': approved = False
        elif event['event'] == 'read_chunk': tainted = True
        elif event['event'] == 'send_result' and event['action'] == 'emit':
            for name, bad in [('unapproved_emit', not approved), ('tainted_emit', tainted),
                              ('duplicate_emit', event['message_id'] in delivered)]:
                if bad: violations.append({'request': event['request'], 'kind': name})
            delivered.add(event['message_id'])
    return {'trace': trace, 'send_results': sends, 'outbox': outbox, 'final_state': state, 'violations': violations}


def public_results(rows):
    return [{k:r[k] for k in ('request','action','payload')} for r in rows]


if __name__ == '__main__':
    cases=[]
    for order_tuple, n, failed, cut in product(permutations('ARS'), (1,2), (0,1), (None,0,1,2,3)):
        order=''.join(order_tuple)
        ref=simulate('guarded',order,n,failed,cut)
        for policy in POLICIES:
            actual=simulate(policy,order,n,failed,cut)
            ok=public_results(actual['send_results'])==public_results(ref['send_results']) and actual['outbox']==ref['outbox'] and not actual['violations']
            cases.append({'id':f'P={policy}|O={order}|N={n}|F={failed}|X={"none" if cut is None else cut}',
                          'policy':policy,'order':order,'send_repetitions':n,'fail_read':bool(failed),'revoke_cut':cut,
                          **actual,'reference_sends':public_results(ref['send_results']), 'reference_outbox':ref['outbox'],
                          'decisions_ok':public_results(actual['send_results'])==public_results(ref['send_results']),
                          'outbox_ok':actual['outbox']==ref['outbox'],'predicted_outcome':'PASS' if ok else 'DOMAIN_FAIL'})
    outcomes=dict(Counter(c['predicted_outcome'] for c in cases))
    by_policy={p:dict(Counter(c['predicted_outcome'] for c in cases if c['policy']==p)) for p in POLICIES}
    assert len(cases)==480 and outcomes=={'PASS':454,'DOMAIN_FAIL':26}
    assert by_policy=={'guarded':{'PASS':120},'sticky_approval':{'PASS':116,'DOMAIN_FAIL':4},
                      'success_only_taint':{'PASS':106,'DOMAIN_FAIL':14},'no_dedup':{'PASS':112,'DOMAIN_FAIL':8}}
    data={'spdx_license_identifier':'BUSL-1.1','status':'Derived predictions; no D13a run yet',
          'cases':cases,'outcomes':outcomes,'by_policy':by_policy,
          'population':{'mandatory_core':96,'optional_revoke_rows':4,'optional_multiplier':5,'reader_executor':480}}
    Path(__file__).with_name('architect-derived.json').write_text(json.dumps(data,indent=2)+'\n')
    print(json.dumps({'cases':len(cases),'outcomes':outcomes,'by_policy':by_policy}))
