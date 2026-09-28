<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D3 — Workflow order, repetition and sudden actions

**Status:** implemented and verified by one recorded campaign (see Results).

[Phase-C contract](phase-c/CONTRACT.md) · A/B audit

[Contract](CONTRACT.md) · [Derived predictions](architect-derived.json)

A: 24 order/optional scenarios per policy, 72 candidates. B: 27 repeated sequences
per policy, 81 candidates. Compare all checkpoints with final-state observation.
Framework: Permut, PermutR, Optional, and a CombiR alternative plan.

Phase C certified SCA2, SCA3, ADJ2 and projected adjacency, separating coverage

## Implementation and reproduction (the AI implementer, phases A/B)

- **Results:** [evidence/results-AB.md](evidence/results-AB.md).
- **Runs:** `evidence/d3a_20260927T181801Z/` and `evidence/d3b_20260927T181920Z/`.
- **Frozen inputs:** `archive/<run-id>/`.

```bash
source bundle_env.sh; cd 03-d3-workflow-order
python build_spec.py --check
BUNDLE_MAIN_DB_PASSWORD=x BUNDLE_RESULTS_DB_PASSWORD=x python -m pytest -q -p no:cacheprovider tests
for R in d3a_20260927T181801Z d3b_20260927T181920Z; do
  python verify.py --run evidence/$R --inputs-root archive/$R/inputs --out /tmp/d3-reverify-$R
  python replay.py --run evidence/$R --witnesses
done
```

## Phase C (the AI implementer)

- **Results:** [phase-c/evidence/results-C.md](phase-c/evidence/results-C.md).
- **Run:** `phase-c/evidence/d3c_20260927T184152Z/`.
- **Frozen inputs:** `phase-c/archive/`.
- **Framework change v3:** merged into the Framework's main branch.

```bash
source bundle_env.sh; cd 03-d3-workflow-order/phase-c
python build_spec.py --check
BUNDLE_MAIN_DB_PASSWORD=x BUNDLE_RESULTS_DB_PASSWORD=x python -m pytest -q -p no:cacheprovider tests
python verify.py --run evidence/d3c_20260927T184152Z --inputs-root archive/d3c_20260927T184152Z/inputs --out /tmp/d3c-reverify
python replay.py --run evidence/d3c_20260927T184152Z --witnesses
```
