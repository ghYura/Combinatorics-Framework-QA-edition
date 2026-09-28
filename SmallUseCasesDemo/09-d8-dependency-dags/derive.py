# SPDX-License-Identifier: BUSL-1.1
"""the AI architect preregistration; no Framework run or implementation dependency."""
from itertools import combinations, product, permutations
from collections import Counter
from pathlib import Path
import json

IDS = 'ABCD'
EDGES = list(combinations(range(4), 2))
BASE = [1, 2, 4, 8]
POLICIES = ['closure_forward', 'direct_only', 'closure_reverse']


def path_matrix(edges):
    paths = [[int(u == v) for v in range(4)] for u in range(4)]
    for u, v in EDGES:
        middle = list(range(u + 1, v))
        for flags in product((0, 1), repeat=len(middle)):
            chain = [u] + [x for x, flag in zip(middle, flags) if flag] + [v]
            paths[u][v] += int(all((a, b) in edges for a, b in zip(chain, chain[1:])))
    return paths


def fresh(base, paths):
    return [sum(base[u] * paths[u][v] for u in range(4)) for v in range(4)]


def model(bits, edit, policy):
    edges = {e for e, bit in zip(EDGES, bits) if bit}
    paths = path_matrix(edges)
    before = fresh(BASE, paths)
    base = BASE.copy()
    base[edit] += 10
    reference = fresh(base, paths)
    affected = [v for v in range(4) if paths[edit][v]]
    dirty = sorted({edit} | {v for u, v in edges if u == edit}) if policy == 'direct_only' else affected
    order = dirty[::-1] if policy == 'closure_reverse' else dirty[:]
    cache = before[:]
    updates = []
    for v in order:
        reads = [{'node': IDS[u], 'value': cache[u]} for u in range(4) if (u, v) in edges]
        old = cache[v]
        cache[v] = base[v] + sum(r['value'] for r in reads)
        updates.append({'node': IDS[v], 'base': base[v], 'parent_reads': reads,
                        'previous': old, 'new': cache[v], 'cache': cache[:]})
    wrong = [IDS[v] for v in range(4) if cache[v] != reference[v]]
    return {'id': f'{policy}|G={"".join(map(str,bits))}|U={IDS[edit]}',
            'policy': policy, 'bits': list(bits), 'edges': [list(e) for e in EDGES if e in edges],
            'edit': IDS[edit], 'before_inputs': BASE, 'after_inputs': base,
            'before_values': before, 'post_edit_cache': before,
            'path_counts': paths, 'reference': reference,
            'expected_delta': [10 * paths[edit][v] for v in range(4)],
            'affected': [IDS[v] for v in affected], 'dirty': [IDS[v] for v in dirty],
            'evaluation_order': [IDS[v] for v in order], 'updates': updates,
            'after_values': cache, 'mismatched_nodes': wrong,
            'predicted_outcome': 'DOMAIN_FAIL' if wrong else 'PASS'}


def topology(edges):
    return [''.join(IDS[v] for v in p) for p in permutations(range(4))
            if all(p.index(u) < p.index(v) for u, v in edges)]


if __name__ == '__main__':
    cases, graphs, redundant = [], [], []
    for bits in product((0, 1), repeat=6):
        code = ''.join(map(str, bits))
        edges = {e for e, bit in zip(EDGES, bits) if bit}
        paths = path_matrix(edges)
        orders = topology(edges)
        graphs.append({'bits': code, 'topological_orders': orders})
        for index, (u, v) in enumerate(EDGES):
            if (u, v) not in edges and paths[u][v]:
                after = list(bits)
                after[index] = 1
                assert topology(edges | {(u, v)}) == orders
                redundant.append({'before': code, 'after': ''.join(map(str, after)),
                                  'added_edge': [u, v], 'topological_orders': orders})
        for edit in range(4):
            for policy in POLICIES:
                cases.append(model(bits, edit, policy))
    outcomes = dict(Counter(c['predicted_outcome'] for c in cases))
    by_policy = {p: dict(Counter(c['predicted_outcome'] for c in cases if c['policy'] == p)) for p in POLICIES}
    assert len(cases) == 768 and outcomes == {'PASS': 604, 'DOMAIN_FAIL': 164}
    assert by_policy == {'closure_forward': {'PASS': 256},
                         'direct_only': {'PASS': 228, 'DOMAIN_FAIL': 28},
                         'closure_reverse': {'PASS': 120, 'DOMAIN_FAIL': 136}}
    assert len(redundant) == 31 and sum(len(g['topological_orders']) for g in graphs) == 315
    data = {'spdx_license_identifier': 'BUSL-1.1', 'status': 'Derived predictions; no D8b run yet',
            'nodes': list(IDS), 'edge_bit_order': EDGES, 'before_inputs': BASE, 'edit_delta': 10,
            'cases': cases, 'outcomes': outcomes, 'by_policy': by_policy,
            'topology_proof': {'graphs': graphs, 'redundant_edge_additions': redundant}}
    Path(__file__).with_name('architect-derived.json').write_text(json.dumps(data, indent=2) + '\n')
    print(json.dumps({'cases': len(cases), 'outcomes': outcomes, 'by_policy': by_policy,
                      'redundant_edge_additions': len(redundant)}))
