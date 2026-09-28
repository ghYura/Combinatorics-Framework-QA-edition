# SPDX-License-Identifier: BUSL-1.1
"""the AI architect's pure transition model; no workers, files, SUT imports or Framework."""
from collections import Counter
from itertools import combinations, product
import copy
import json
from pathlib import Path

POLICIES = ('durable', 'volatile_ack', 'replay_twice')
KINDS = ('crash', 'partition')
RETRIES = ('stable', 'fresh')
SUBSETS = [list(s) for size in (1, 2, 3) for s in combinations(range(3), size)]
OPS = {'o1': 1, 'o2': 10, 'o3': 100}


def model(policy, failed, cut, kind, retry):
    nodes = [{'running': True, 'generation': 0, 'accepted': [], 'wal': [], 'effects': []} for _ in range(3)]
    trace, attempts = [], []
    blocked = set()

    def put(n, key):
        if key in n['accepted']:
            return
        if policy != 'volatile_ack':
            n['wal'].append(key)
        n['accepted'].append(key)
        n['effects'].append(key.split(':')[0])

    def flush(n):
        n['wal'].extend(k for k in n['accepted'] if k not in n['wal'])

    def attempt(i, phase, suffix='a1'):
        op, key = f'o{i}', f'o{i}:{suffix}'
        targets = [j for j in range(3) if nodes[j]['running'] and j not in blocked]
        for j in targets:
            put(nodes[j], key)
        status = 'ACK' if len(targets) >= 2 else 'TIMEOUT'
        attempts.append({'op': op, 'key': key, 'phase': phase, 'targets': targets, 'status': status})
        return status

    def snap(label):
        states = []
        for i, n in enumerate(nodes):
            counts = {op: n['effects'].count(op) for op in OPS} if n['running'] else None
            states.append({'node': i, 'running': n['running'], 'reachable': n['running'] and i not in blocked,
                           'generation': n['generation'], 'accepted': sorted(n['accepted']) if n['running'] else None,
                           'wal': list(n['wal']), 'effects': list(n['effects']) if n['running'] else None,
                           'counts': counts, 'value': sum(OPS[k] * v for k, v in counts.items()) if counts is not None else None})
        trace.append({'checkpoint': label, 'nodes': states})

    snap('initial')
    for i in range(1, cut + 1):
        attempt(i, 'prefix')
    snap('prefix')
    blocked.update(failed)
    if kind == 'crash':
        for j in failed:
            nodes[j].update(running=False, accepted=[], effects=[])
    snap('faulted')
    timed_out = False
    if cut < 3:
        timed_out = attempt(cut + 1, 'window') == 'TIMEOUT'
        snap('window')
    if kind == 'crash':
        for j in failed:
            n = nodes[j]
            n.update(running=True, generation=1, accepted=list(n['wal']),
                     effects=[k.split(':')[0] for k in n['wal']] * (2 if policy == 'replay_twice' else 1))
    blocked.clear()
    snap('reopened')
    union = sorted({k for n in nodes for k in n['accepted']})
    for n in nodes:
        for key in union:
            put(n, key)
        flush(n)
    snap('repaired')
    before_recovery_acks = sorted({a['op'] for a in attempts if a['status'] == 'ACK'})
    if timed_out:
        attempt(cut + 1, 'retry', 'a1' if retry == 'stable' else 'a2')
        snap('retry')
    for i in range(cut + 2, 4):
        attempt(i, 'suffix')
    for n in nodes:
        flush(n)
    snap('final')
    acknowledged = sorted({a['op'] for a in attempts if a['status'] == 'ACK'})
    final, repaired = trace[-1]['nodes'], next(t['nodes'] for t in trace if t['checkpoint'] == 'repaired')
    ref = {k: 1 for k in OPS}
    checks = {
        'all_logical_ops_acknowledged': acknowledged == list(OPS),
        'acknowledged_survive_repair': all(s['counts'][op] >= 1 for s in repaired for op in before_recovery_acks),
        'acknowledged_effects_once': all(s['counts'][op] == 1 for s in final for op in acknowledged),
        'accepted_logical_ops_once': all(Counter(k.split(':')[0] for k in s['accepted']) == ref for s in final),
        'replicas_agree': all((s['accepted'], s['counts'], s['value']) == (final[0]['accepted'], final[0]['counts'], final[0]['value']) for s in final),
        'matches_fault_free_reference': all(s['counts'] == ref and s['value'] == 111 for s in final),
        'final_wal_matches_accepted': all(len(s['wal']) == len(set(s['wal'])) and sorted(s['wal']) == s['accepted'] for s in final),
    }
    return {'id': f'P={policy}|F={"".join(map(str, failed))}|C={cut}|K={kind}|R={retry}',
            'policy': policy, 'failed': failed, 'cut': cut, 'kind': kind, 'retry': retry,
            'attempts': attempts, 'trace': trace, 'acknowledged': acknowledged, 'checks': checks,
            'predicted_outcome': 'PASS' if all(checks.values()) else 'DOMAIN_FAIL'}


def derive():
    cases = [model(p, f, c, k, r) for p, f, c, k, r in product(POLICIES, SUBSETS, range(4), KINDS, RETRIES)
             if not (k == 'partition' and len(f) == 3)]
    return {'spdx_license_identifier': 'BUSL-1.1', 'status': 'Derived; no campaign run',
            'raw_framework_cases': 336, 'sieve_rejected': 24, 'valid_cases': len(cases),
            'structural_schedules_per_policy': 104,
            'outcomes': dict(Counter(c['predicted_outcome'] for c in cases)),
            'by_policy': {p: dict(Counter(c['predicted_outcome'] for c in cases if c['policy'] == p)) for p in POLICIES},
            'attempts': sum(len(c['attempts']) for c in cases),
            'worker_starts': sum(3 + (len(c['failed']) if c['kind'] == 'crash' else 0) for c in cases),
            'injected_kills': sum(len(c['failed']) if c['kind'] == 'crash' else 0 for c in cases),
            'cases': cases}


if __name__ == '__main__':
    out = derive()
    Path(__file__).with_name('architect-derived.json').write_text(json.dumps(out, indent=2) + '\n')
    print(json.dumps({k: v for k, v in out.items() if k != 'cases'}, indent=2))
