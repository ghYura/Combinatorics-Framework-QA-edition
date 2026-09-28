# SPDX-License-Identifier: BUSL-1.1
"""the AI architect preregistration: oriented cyclic motifs and population-preserving reduction."""
from itertools import product
from collections import Counter
from fractions import Fraction
from math import gcd
from pathlib import Path
import json

ALPHABET = 'ABC'
COST = [[2, 0, 3], [3, 2, 0], [0, 3, 2]]


def rotations(w):
    return sorted({w[k:] + w[:k] for k in range(6)})


def metrics(w):
    counts = [w.count(c) for c in ALPHABET]
    edge_counts = [[0] * 3 for _ in range(3)]
    edge_costs = []
    for i in range(6):
        u, v = ALPHABET.index(w[i]), ALPHABET.index(w[(i+1) % 6])
        edge_counts[u][v] += 1
        edge_costs.append(COST[u][v])
    balance = sum((n-2)**2 for n in counts)
    orbit = rotations(w)
    return {'id': 'W=' + w, 'word': w, 'counts': counts, 'edge_counts': edge_counts,
            'edge_costs': edge_costs, 'transition_cost': sum(edge_costs),
            'balance_penalty': balance, 'total_cost': sum(edge_costs)+balance,
            'representative': orbit[0], 'orbit_size': len(orbit),
            'period': min(k for k in range(1,7) if w[k:] + w[:k] == w),
            'stabilizer_size': 6 // len(orbit), 'predicted_outcome': 'PASS'}


def q(x):
    return {'n': str(x.numerator), 'd': str(x.denominator)}


if __name__ == '__main__':
    cases = [metrics(''.join(w)) for w in product(ALPHABET, repeat=6)]
    by_word = {c['word']: c for c in cases}
    representatives = sorted({c['representative'] for c in cases})
    orbits = [{'representative': r, 'members': rotations(r), 'size': len(rotations(r)),
               'period': by_word[r]['period'], 'stabilizer_size': by_word[r]['stabilizer_size'],
               'reflected_representative': rotations(r[::-1])[0], 'total_cost': by_word[r]['total_cost']}
              for r in representatives]
    hist_words = Counter(c['total_cost'] for c in cases)
    hist_classes = Counter(by_word[r]['total_cost'] for r in representatives)
    weighted = Counter()
    for o in orbits:
        weighted[o['total_cost']] += o['size']
        assert all(by_word[w]['total_cost'] == o['total_cost'] for w in o['members'])
    burnside = [3**gcd(6,k) for k in range(6)]
    size_hist = Counter(o['size'] for o in orbits)
    mean_words = Fraction(sum(c['total_cost'] for c in cases), len(cases))
    mean_classes = Fraction(sum(by_word[r]['total_cost'] for r in representatives), len(representatives))
    self_reflections = sum(o['representative'] == o['reflected_representative'] for o in orbits)
    assert len(cases)==729 and len(orbits)==130 and sum(burnside)//6==130
    assert size_hist=={1:3,2:3,3:8,6:116} and weighted==hist_words
    assert mean_words==14 and mean_classes==Fraction(942,65) and self_reflections==54
    ranking = sorted(representatives, key=lambda r:(by_word[r]['total_cost'],r))
    assert ranking[0]=='ABCABC' and by_word['ABCABC']['total_cost']==0
    doc = {'spdx_license_identifier':'BUSL-1.1','status':'Derived predictions; no D12 runs yet',
           'alphabet':list(ALPHABET),'edge_cost_matrix':COST,'cases':cases,
           'representatives':representatives,'orbits':orbits,'burnside_fixed_counts':burnside,
           'orbit_size_histogram':dict(size_hist),'self_reflection_classes':self_reflections,'mirror_pairs':38,
           'histograms':{'words':dict(hist_words),'classes_uniform':dict(hist_classes),'classes_weighted':dict(weighted)},
           'means':{'words':q(mean_words),'classes_uniform':q(mean_classes),'classes_weighted':q(mean_words)},
           'ranking':ranking,'best_classes':['ABCABC'],'best_labelled_words':rotations('ABCABC'),
           'outcomes':{'words':{'PASS':729},'classes':{'PASS':130}}}
    Path(__file__).with_name('architect-derived.json').write_text(json.dumps(doc,indent=2)+'\n')
    print(json.dumps({'cases':len(cases),'classes':len(orbits),'means':doc['means'],'best':ranking[0]}))
