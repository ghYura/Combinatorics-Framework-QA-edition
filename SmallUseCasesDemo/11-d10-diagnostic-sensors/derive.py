# SPDX-License-Identifier: BUSL-1.1
"""the AI architect preregistration: synthetic status sensors and exact diagnosis certificates."""
from itertools import product, combinations
from functools import lru_cache
from pathlib import Path
import json

CODES = [0, 1, 2, 4, 8, 7, 15]


def sensors(code):
    a, b, c, d = [(code >> i) & 1 for i in range(4)]
    return [a, b, c, d, a ^ b ^ d, a ^ c ^ d, b ^ c ^ d, a ^ b ^ c]


SIG = [sensors(c) for c in CODES]


@lru_cache(None)
def optimum(belief):
    if len(belief) == 1:
        return (0, None)
    choices = []
    for s in range(8):
        branches = [tuple(c for c in belief if SIG[c][s] == b) for b in (0, 1)]
        if all(branches):
            choices.append((1 + max(optimum(b)[0] for b in branches), s))
    return min(choices)


def tree(belief):
    cost, s = optimum(belief)
    if s is None:
        return {'class': belief[0], 'cost': 0}
    return {'sensor': s, 'cost': cost,
            'branches': {str(b): tree(tuple(c for c in belief if SIG[c][s] == b)) for b in (0, 1)}}


if __name__ == '__main__':
    classes = [{'class': i, 'code': c, 'signature': SIG[i],
                'members': ['H0'] if i == 0 else [f'F{2*i-1:02}', f'F{2*i:02}']} for i, c in enumerate(CODES)]
    cases, suites = [], []
    for bits in product((0, 1), repeat=8):
        mask = ''.join(map(str, bits))
        selected = [i for i, b in enumerate(bits) if b]
        projected = [''.join(str(s[i]) for i in selected) for s in SIG]
        distances = [{'classes': [i, j], 'distance': sum(a != b for a, b in zip(projected[i], projected[j]))}
                     for i, j in combinations(range(7), 2)]
        md = min(x['distance'] for x in distances)
        detect = all(p != projected[0] for p in projected[1:])
        suites.append({'mask': mask, 'cost': len(selected), 'signatures': projected,
                       'distances': distances, 'min_distance': md,
                       'detect': detect, 'separate': md >= 1, 'erasure': md >= 2, 'error': md >= 3})
        for f in range(1, 13):
            cl = (f + 1) // 2
            cases.append({'id': f'S={mask}|H=F{f:02}', 'mask': mask, 'selected': selected,
                          'sensor_cost': len(selected), 'fault': f'F{f:02}',
                          'latent_bits': [(CODES[cl] >> i) & 1 for i in range(4)],
                          'readings': [SIG[cl][i] for i in selected], 'signature': projected[cl],
                          'predicted_outcome': 'PASS'})
    winners = {}
    for goal in ('detect', 'separate', 'erasure', 'error'):
        feasible = sorted((s for s in suites if s[goal]), key=lambda s: (s['cost'], s['mask']))
        winners[goal] = {'mask': feasible[0]['mask'], 'cost': feasible[0]['cost'], 'feasible_count': len(feasible),
                         'minimum_cost_masks': [s['mask'] for s in feasible if s['cost'] == feasible[0]['cost']]}
    dp = []
    for flags in product((0, 1), repeat=7):
        belief = tuple(i for i, b in enumerate(flags) if b)
        if belief:
            cost, sensor = optimum(belief)
            dp.append({'belief': list(belief), 'cost': cost, 'sensor': sensor})
    adaptive = tree(tuple(range(7)))
    paths = []
    for cl in range(7):
        node, steps = adaptive, []
        while 'sensor' in node:
            s = node['sensor']; value = SIG[cl][s]
            steps.append({'sensor': s, 'reading': value})
            node = node['branches'][str(value)]
        assert node['class'] == cl
        paths.append({'class': cl, 'steps': steps, 'cost': len(steps)})
    noise = {}
    for goal in ('erasure', 'error'):
        suite = next(s for s in suites if s['mask'] == winners[goal]['mask'])
        rows = []
        for cl, word in enumerate(suite['signatures']):
            for pos in [-1, *range(len(word))]:
                observed = list(word)
                if pos >= 0:
                    observed[pos] = '?' if goal == 'erasure' else str(1-int(observed[pos]))
                if goal == 'erasure':
                    possible = [c for c, w in enumerate(suite['signatures'])
                                if all(a == '?' or a == b for a, b in zip(observed, w))]
                else:
                    possible = [c for c, w in enumerate(suite['signatures']) if sum(a != b for a, b in zip(observed, w)) <= 1]
                assert possible == [cl]
                rows.append({'class': cl, 'position': pos, 'observed': ''.join(observed), 'decoded': possible})
        noise[goal] = rows
    assert len(cases) == 3072 and len(dp) == 127
    assert [winners[g]['cost'] for g in winners] == [2, 4, 6, 7] and adaptive['cost'] == 3
    assert [winners[g]['feasible_count'] for g in winners] == [201, 149, 37, 9]
    assert len(noise['erasure']) == 49 and len(noise['error']) == 56
    data = {'spdx_license_identifier': 'BUSL-1.1', 'status': 'Derived predictions; no D10 run yet',
            'classes': classes, 'cases': cases, 'outcomes': {'PASS': 3072}, 'suites': suites,
            'winners': winners, 'adaptive': {'tree': adaptive, 'dp': dp, 'paths': paths}, 'noise': noise}
    Path(__file__).with_name('architect-derived.json').write_text(json.dumps(data, indent=2)+'\n')
    print(json.dumps({'cases': len(cases), 'winners': {g: {k:v for k,v in w.items() if k != 'minimum_cost_masks'} for g,w in winners.items()},
                      'adaptive_cost': adaptive['cost']}))
