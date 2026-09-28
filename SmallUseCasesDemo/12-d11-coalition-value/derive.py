# SPDX-License-Identifier: BUSL-1.1
"""the AI architect preregistration: six-module value game and exact Shapley allocation."""
from itertools import product, permutations
from fractions import Fraction as F
from math import factorial
from pathlib import Path
import json

PLAYERS = 'ABCDEF'
BASE = [2, 2, 1, 1, 4, 0]
TERMS = [('AB', 12), ('ACD', 5), ('BCD', 5)]


def key(s):
    return ''.join(str(int(p in s)) for p in PLAYERS)


def rational(x):
    x = F(x)
    return {'n': str(x.numerator), 'd': str(x.denominator)}


def evaluate(s):
    base = sum(BASE[i] for i, p in enumerate(PLAYERS) if p in s)
    bonuses = {t: v if set(t) <= s else 0 for t, v in TERMS}
    return {'id': 'C=' + key(s), 'mask': key(s), 'members': [p for p in PLAYERS if p in s],
            'standalone_value': base, 'interaction_bonuses': bonuses, 'value': base + sum(bonuses.values()),
            'predicted_outcome': 'PASS'}


if __name__ == '__main__':
    coalitions = [set(p for p, b in zip(PLAYERS, bits) if b) for bits in product((0, 1), repeat=6)]
    cases = [evaluate(s) for s in coalitions]
    values = {r['mask']: r['value'] for r in cases}
    phi = {p: F(0) for p in PLAYERS}
    marginal_rows = []
    for p in PLAYERS:
        for s in coalitions:
            if p not in s:
                w = F(factorial(len(s)) * factorial(5-len(s)), factorial(6))
                marginal = values[key(s | {p})] - values[key(s)]
                phi[p] += w * marginal
                marginal_rows.append({'player': p, 'coalition': key(s), 'weight': rational(w), 'marginal': marginal})
    orders, sums = [], {p: 0 for p in PLAYERS}
    for perm in permutations(PLAYERS):
        s, increments = set(), []
        for p in perm:
            change = values[key(s | {p})] - values[key(s)]
            sums[p] += change; increments.append(change); s.add(p)
        orders.append({'order': ''.join(perm), 'marginals': increments})
    dividends = {}
    for s in sorted(coalitions, key=lambda s: (len(s), key(s))):
        dividends[key(s)] = values[key(s)] - sum(v for bits, v in dividends.items()
                                               if {p for p, b in zip(PLAYERS, bits) if b == '1'} < s)
    from_dividends = {p: sum((F(v, bits.count('1')) for bits, v in dividends.items()
                             if bits[PLAYERS.index(p)] == '1'), F(0)) for p in PLAYERS}
    assert phi == from_dividends == {p: F(sums[p], 720) for p in PLAYERS}
    assert [phi[p] for p in PLAYERS] == [F(29,3), F(29,3), F(13,3), F(13,3), F(4), F(0)]
    assert sum(phi.values()) == values['111111'] == 32 and values['000000'] == 0
    for s in coalitions:
        if 'F' not in s: assert values[key(s | {'F'})] == values[key(s)]
        if 'E' not in s: assert values[key(s | {'E'})] - values[key(s)] == 4
    doc = {'spdx_license_identifier': 'BUSL-1.1', 'status': 'Derived predictions; no D11 run yet',
           'players': list(PLAYERS), 'base_values': BASE, 'interaction_terms': TERMS,
           'cases': cases, 'outcomes': {'PASS': 64}, 'shapley': {p: rational(v) for p, v in phi.items()},
           'marginals': marginal_rows, 'permutations': orders, 'permutation_sums': sums,
           'dividends': dividends,
           'standalone': {p: values[key({p})] for p in PLAYERS},
           'leave_one_out': {p: 32-values[key(set(PLAYERS)-{p})] for p in PLAYERS},
           'uniform_subset_marginals': {p: rational(F(sum(r['marginal'] for r in marginal_rows if r['player']==p),32)) for p in PLAYERS}}
    Path(__file__).with_name('architect-derived.json').write_text(json.dumps(doc, indent=2)+'\n')
    print(json.dumps({'cases':len(cases),'shapley':doc['shapley'],'grand_value':32}))
