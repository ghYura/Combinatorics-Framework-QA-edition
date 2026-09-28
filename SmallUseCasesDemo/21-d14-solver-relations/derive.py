# SPDX-License-Identifier: BUSL-1.1
"""the AI architect's bounded auction derivation; never imported by candidates or verifier."""
from collections import Counter
from itertools import permutations, product
import json
from pathlib import Path

INSTANCES = {
    'bundle_trap': [([0, 1], 7), ([0], 4), ([1], 4), ([2], 2)],
    'tie': [([0, 1], 8), ([0], 4), ([1], 4), ([2], 2)],
    'disjoint': [([0], 5), ([1], 4), ([2], 3), ([0, 1, 2], 6)],
    'overlap': [([0, 1], 6), ([1, 2], 5), ([0, 2], 4), ([2], 2)],
}
POLICIES = ('exact_dp', 'greedy_value', 'min_only_dp')
EDITS = ('none', 'dominated')


def bids_for(name, perm=(0, 1, 2), edit='none'):
    bids = [{'id': f'b{i}', 'items': sorted(perm[x] for x in items), 'value': v}
            for i, (items, v) in enumerate(INSTANCES[name])]
    if edit == 'dominated':
        bids.append({'id': 'b4', 'items': bids[0]['items'][:], 'value': bids[0]['value'] - 1})
    return bids


def allocations(bids, first_only=False):
    out = []
    for bits in product((0, 1), repeat=len(bids)):
        selected = [b for b, bit in zip(bids, bits) if bit]
        used = [x for b in selected for x in (b['items'][:1] if first_only else b['items'])]
        if len(used) == len(set(used)):
            out.append((sum(b['value'] for b in selected), tuple(b['id'] for b in selected)))
    return out


def observe(bids, policy):
    ref = allocations(bids)
    optimum = max(v for v, _ in ref)
    if policy == 'greedy_value':
        chosen, used = [], set()
        for b in sorted(bids, key=lambda b: (-b['value'], b['id'])):
            if not used.intersection(b['items']):
                chosen.append(b['id']); used.update(b['items'])
        selected = sorted(chosen)
    else:
        selected = list(max(allocations(bids, policy == 'min_only_dp'))[1])
    value = sum(b['value'] for b in bids if b['id'] in selected)
    feasible = (value, tuple(selected)) in ref
    return {'bids': bids, 'selected': selected, 'reported_value': value, 'actual_value': value,
            'feasible': feasible, 'value_correct': True, 'optimum': optimum,
            'feasible_subsets': len(ref),
            'optimal_allocations': [list(ids) for v, ids in sorted(ref) if v == optimum],
            'optimal': feasible and value == optimum, 'gap': optimum - value if feasible else None}


def derive():
    cases = []
    for policy, name, perm, edit in product(POLICIES, INSTANCES, permutations(range(3)), EDITS):
        variants = {k: observe(bids_for(name, p, e), policy) for k, p, e in
                    [('base', (0, 1, 2), 'none'), ('relabeled', perm, 'none'), ('edited', perm, edit)]}
        a, b, c = (variants[k] for k in ('base', 'relabeled', 'edited'))
        relations = {'reference_relabel': a['optimum'] == b['optimum'],
                     'reference_edit': b['optimum'] == c['optimum'],
                     'solver_relabel': a['reported_value'] == b['reported_value'],
                     'solver_edit': b['reported_value'] == c['reported_value']}
        ok = all(v['optimal'] and v['value_correct'] for v in variants.values()) and all(relations.values())
        cases.append({'id': f'P={policy}|I={name}|R={"".join(map(str, perm))}|E={edit}',
                      'policy': policy, 'instance': name, 'permutation': list(perm), 'edit': edit,
                      'variants': variants, 'relations': relations, 'predicted_outcome': 'PASS' if ok else 'DOMAIN_FAIL'})
    return {'spdx_license_identifier': 'BUSL-1.1', 'status': 'Derived; not run evidence',
            'framework_cases': len(cases), 'solver_calls': len(cases) * 3,
            'reference_subset_checks': sum(2 ** len(v['bids']) for c in cases for v in c['variants'].values()),
            'outcomes': dict(Counter(c['predicted_outcome'] for c in cases)),
            'by_policy': {p: dict(Counter(c['predicted_outcome'] for c in cases if c['policy'] == p)) for p in POLICIES},
            'cases': cases}


if __name__ == '__main__':
    result = derive()
    Path(__file__).with_name('architect-derived.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'cases'}, indent=2))
