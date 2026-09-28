<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D2 — Streaming decoder boundaries and EOF

**Status:** implemented and verified by one recorded campaign (see Results).

[Contract](CONTRACT.md) · [Preregistered cases](architect-derived.json)

Verified: 1152 raw combinations → 480 valid cases; 332 PASS / 148 DOMAIN_FAIL.

## Implementation and reproduction (the AI implementer)

- **Campaign:** `evidence/d2_20260927T154330Z/`.
- **Frozen inputs:** `archive/d2_20260927T154330Z/`.

```bash
source bundle_env.sh; cd 02-d2-stream-boundaries
python build_spec.py --check
BUNDLE_MAIN_DB_PASSWORD=x BUNDLE_RESULTS_DB_PASSWORD=x python -m pytest -q -p no:cacheprovider tests
python verify.py --run evidence/d2_20260927T154330Z --inputs-root archive/d2_20260927T154330Z/inputs --out /tmp/d2-reverify
python replay.py --run evidence/d2_20260927T154330Z --witnesses
```
