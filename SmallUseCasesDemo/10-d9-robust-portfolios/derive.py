# SPDX-License-Identifier: BUSL-1.1
"""the AI architect preregistration of the atlas's illustrative costs; no campaign execution."""
from fractions import Fraction as F
from itertools import product
from pathlib import Path
import hashlib
import json

MODULES = ['cache', 'quota', 'network_backup', 'disk_replica', 'staff_reserve', 'cross_region']
COSTS = [3, 2, 5, 6, 4, 8]
DEMAND_LOSS = [4, 11, 22, 15]
DISRUPTION_LOSS = [0, 14, 19, 9]
WORLDS = list(product(range(4), repeat=2))
PROFILES = {'uniform': ([1, 1, 1, 1], [1, 1, 1, 1]),
            'calm': ([6, 2, 1, 1], [7, 1, 1, 1]),
            'stress': ([1, 1, 6, 2], [1, 2, 6, 1])}
SOURCE = Path(__file__).resolve().parent / 'planning' / 'atlas-robust-planning-spec.toml'


def rational(x):
    x = F(x)
    return {'n': str(x.numerator), 'd': str(x.denominator)}


def benefit(d, x):
    return [(0, 3, 8, 6)[d], (0, 2, 6, 7)[d], 11 * (x == 1),
            14 * (x == 2), 6 * (x == 3), 8 * (x in (1, 2))]


def evaluate(bits, d, x):
    reductions = [b * v for b, v in zip(bits, benefit(d, x))]
    fixed = sum(b * c for b, c in zip(bits, COSTS))
    gross = DEMAND_LOSS[d] + DISRUPTION_LOSS[x]
    raw = gross - sum(reductions)
    design = ''.join(map(str, bits))
    return {'id': f'P={design}|D={d}|X={x}', 'design': design,
            'selected': [m for m, b in zip(MODULES, bits) if b], 'demand': d, 'disruption': x,
            'fixed_cost': fixed, 'gross_loss': gross, 'reductions': reductions,
            'raw_loss': raw, 'residual_loss': max(0, raw), 'total_cost': fixed + max(0, raw),
            'predicted_outcome': 'PASS'}


if __name__ == '__main__':
    cases = [evaluate(b, d, x) for b in product((0, 1), repeat=6) for d, x in WORLDS]
    matrix = {c['design']: [] for c in cases}
    for c in cases:
        matrix[c['design']].append(c['total_cost'])
    weights = {p: [F(dw[d] * xw[x], sum(dw) * sum(xw)) for d, x in WORLDS]
               for p, (dw, xw) in PROFILES.items()}
    expected = lambda b, w: sum((F(c) * q for c, q in zip(matrix[b], w)), F(0))
    minimax = sorted(matrix, key=lambda b: (max(matrix[b]), expected(b, weights['uniform']), b))
    rankings = {p: sorted(matrix, key=lambda b: (expected(b, w), max(matrix[b]), b)) for p, w in weights.items()}
    summaries = [{'design': b, 'world_count': 16, 'worst_cost': max(cs),
                  'worst_worlds': [list(w) for w, c in zip(WORLDS, cs) if c == max(cs)],
                  'expected': {p: rational(expected(b, w)) for p, w in weights.items()}}
                 for b, cs in matrix.items()]
    sensitivity = []
    for k in range(11):
        alpha = F(k, 10)
        w = [(1-alpha)*a + alpha*b for a, b in zip(weights['calm'], weights['stress'])]
        order = sorted(matrix, key=lambda b: (expected(b, w), max(matrix[b]), b))
        sensitivity.append({'alpha': rational(alpha), 'ranking': order, 'winner': order[0],
                            'winner_expected': rational(expected(order[0], w))})
    naive = min(cases, key=lambda c: (c['total_cost'], c['design'], c['demand'], c['disruption']))
    assert len(cases) == 1024 and len(matrix) == 64 and all(len(v) == 16 for v in matrix.values())
    assert minimax[0] == '110000' and rankings['calm'][0] == '000000' and rankings['stress'][0] == '110100'
    assert [r['winner'] for r in sensitivity] == ['000000','010000','010000','110000','110000','110000','110000','110100','110100','110100','110100']
    data = {'spdx_license_identifier': 'BUSL-1.1', 'status': 'Derived predictions; no D9 run yet',
            'payoff_source': {'path': 'planning/atlas-robust-planning-spec.toml', 'sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                              'note': 'Historical proposal costs only; no old run is reused.'},
            'modules': MODULES, 'fixed_costs': COSTS, 'demand_loss': DEMAND_LOSS,
            'disruption_loss': DISRUPTION_LOSS, 'worlds': WORLDS,
            'benefits_by_world': [benefit(d, x) for d, x in WORLDS],
            'profiles': {p: {'demand_weights': dw, 'disruption_weights': xw,
                             'world_weights': [rational(q) for q in weights[p]]} for p, (dw, xw) in PROFILES.items()},
            'cases': cases, 'outcomes': {'PASS': 1024}, 'summaries': summaries,
            'minimax_ranking': minimax, 'expected_rankings': rankings, 'sensitivity': sensitivity,
            'naive_best_row': naive['id'],
            'minimax_primary_ties': [b for b in minimax if max(matrix[b]) == max(matrix[minimax[0]])]}
    Path(__file__).with_name('architect-derived.json').write_text(json.dumps(data, indent=2)+'\n')
    print(json.dumps({'cases': len(cases), 'minimax': minimax[0], 'primary_ties': data['minimax_primary_ties'],
                      'expected_winners': {p: r[0] for p, r in rankings.items()}}))
