<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D1 — Choosing a durable idempotency key

**Status:** implemented and verified by one recorded campaign (see Results).

This example demonstrates how transport identity, process lifetime, business
operation identity and equal payloads produce different deduplication behaviour.
Five small service policies are tested through the actual Framework pipeline.

- [Architecture](ARCHITECTURE.md): the service, components and demonstration.
- [Frozen contract v1](CONTRACT.md): 600 raw combinations, 120 valid cases,
  independent expectations and precise scope.
- [Implementation instructions](IMPLEMENTATION.md): files, sequence and commands.
- Review record: acceptance gates, initially pending.
- [Architect-derived case set](architect-derived.json): the 120 expected
  semantic identities and predicted aggregate signatures, before any run.
- [Collaboration protocol](../README.md) and
  portfolio.

Messages live directly in this folder as `architect-to-implementer-*.md` and
`implementer-to-architect-*.md`, with EEST timestamps. The AI implementer starts from the latest the AI architect
IMPLEMENT/REVISION message and responds here. Later examples remain queued.

Current decision: .
The author's authorization covers necessary codebase
changes for both AIs. The AI architect independently ran the fixture's 19 tests;
all passed. These are local
fixture checks, not evidence that the Framework campaign has passed review.

## Implementation and reproduction (the AI implementer)

**Campaign:** `evidence/d1_20260927T141430Z/`.
- results and walkthrough
- verification
- witnesses
- replays

**Sources:**
- fixture: `sut.py`, `oracle.py`, `runtime.py`
- `build_spec.py`, which writes `spec/` ([mapping](spec/MAPPING.md))
- tools: `run_demo.py`, `verify.py`, `replay.py`
- `tests/`

The Framework change this example motivated (XLSX sidecar support) is part of the Framework's main branch.
Reproducers are in blockers/.

```bash
source bundle_env.sh
cd 01-d1-idempotency
python build_spec.py --check                     # spec/ equals a fresh build
BUNDLE_MAIN_DB_PASSWORD=x BUNDLE_RESULTS_DB_PASSWORD=x python -m pytest -q -p no:cacheprovider tests
python verify.py --run evidence/d1_20260927T141430Z      # offline: no DB, no candidate execution
python replay.py --run evidence/d1_20260927T141430Z --witnesses   # extra attempts in python:3-slim
python run_demo.py --input xlsx                  # a NEW campaign with fresh as0927_d1_* databases
```

Latest: . The earlier 19 fixture tests and later
120-case Framework campaign are distinct evidence; the campaign passed its
behavioural checks, while source/workspace corrections remain open.

