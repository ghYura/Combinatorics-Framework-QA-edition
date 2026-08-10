# Application-direction use-cases

Bounded, runnable demonstrations that "pull up" the Bundle in the Tier-2/Tier-3 application
directions. Self-contained specs need no SUT, network, or Docker; the ML and fintech
fixtures use local SUT processes with no external egress.

The result column is a dated record of earlier campaigns, not a claim that those
runs were reproduced in the current checkout. Most raw run directories are not
versioned. Re-run the relevant command and retain its journal, summaries, metrics,
and Analyzer output when current evidence is required.

| # | Direction | Spec | Mechanism | Recorded result (historical) |
|---|---|---|---|---|
| 7 | **Performance / design-space optimization** | `perf_opt/` | algo×threads×batch×cache, deterministic surrogate cost model | 72 PASS → formal **Pareto front 13** (latency/memory/throughput tradeoff), provenance_ok |
| 10 | **Real ternary-kernel microarchitecture tuning** | `ternary_kernel_opt/` | sign vs maddubs × threads × SIMD unroll × parallel threshold × grain; exact int32 oracle | 144 PASS → maddubs ~4.4x vs torch int32 microbenchmark; formal Pareto 1 |
| 11 | **Full-model ternary dispatch tuning** | `ternary_full_model_dispatch/` | runtime-large forward × threads × C++ dispatch threshold; exact logits/Medusa oracle | 32 PASS → formal Pareto 4; confirmation keeps all-maddubs default |
| 6 | **ETL / data-pipeline validation** | `etl_pipeline/` | FW_Permut transform-order × null-policy × dedup-mode; data-quality oracle | 36 → **21 PASS / 15 DOMAIN_FAIL** (catches dedup-before-normalize / by_full leaks) |
| 8 | **ML/LLM eval — deterministic baseline** | `ml_eval/` | preprocessing-order × quant × decode; quality-gate oracle | 54 → **43 PASS / 11 DOMAIN_FAIL** (int4 below gate), formal **Pareto 7** |
| 8b | **ML/LLM eval — two REAL local surrogates (differential)** | `ml_eval_surrogate/` | MODEL A/B × style × temp, queries `advanced_surrogate{,2}` (sklearn, chat-API-compatible) over local HTTP | 12 PASS, real latency/tokens, formal **Pareto 2** (A vs B) |
| 5 | **Event-order / distributed workflow (saga)** | `event_order/` | FW_Permut step-order + FW_Optional sudden actions; saga invariant oracle | 24 → **2 PASS / 22 DOMAIN_FAIL** (8 charge-before-reserve, 12 ship-before-charge, 2 double-charge) |
| 9 | **Fintech / business-rules (REAL bank cluster)** | `../fintech_oot/batches/{auth_matrix,intra_transfer}` | signed-HMAC transfers against the live `finance_stack` banks (AURUM:8121 ↔ NORD:8122) | auth 16 PASS, transfer 90 PASS; candidate source POSTs signed `/transfer` to both nodes |
| 4 | **API / integration testing** | covered by `tryout_own/spec` (flagship: HTTP API, order via FW_Permut, ascii/unicode encoding, optional actions, oracle) + the fintech transfer APIs + #5's idempotency invariant | — | see flagship 288 (150/138) |
| 12 | **Telemetry catalog contract validation** | `telemetry_catalog_e2e/`, `telemetry_catalog_full/` | contextual optional bonds + sentinel nested bonds against a local standalone HTTP SUT | 576 → 300 embedded-valid; 729 → 312 embedded-valid; every authored URL parses and every embedded-valid URL receives HTTP 200 |

## Running them

```bash
cd generator_trunk
: "${BUNDLE_MAIN_DB_PASSWORD:?inject the main DB password}"
: "${BUNDLE_RESULTS_DB_PASSWORD:?inject the results DB password}"
# self-contained (no SUT):
python3 bundle_run.py usecases/perf_opt   --db perfopt --execution-policy-profile trusted-local \
    --candidate-origin reviewed-checked-in \
    --acknowledge-trusted-local 'reviewed checked-in perf_opt fixture' \
    --analyzer "throughput_rps:max,latency_ms:min,memory_mb:min" --analysis-mode formal --run-id p1
python3 bundle_run.py usecases/ternary_kernel_opt --db ternary_kernel_opt_v2 \
    --execution-policy-profile trusted-local --workers 1 \
    --candidate-origin reviewed-checked-in \
    --acknowledge-trusted-local 'reviewed checked-in ternary kernel fixture' \
    --analyzer "latency_ms:min,throughput_mops:max" --analysis-mode formal --run-id tk2
python3 bundle_run.py usecases/ternary_full_model_dispatch --db ternary_full_model_dispatch \
    --execution-policy-profile trusted-local --workers 1 \
    --candidate-origin reviewed-checked-in \
    --acknowledge-trusted-local 'reviewed checked-in ternary dispatch fixture' \
    --analyzer "latency_ms:min,seq1_ms:min,seq48_ms:min" --analysis-mode formal --run-id tf1
python3 bundle_run.py usecases/etl_pipeline --db etlpipe --execution-policy-profile trusted-local \
    --candidate-origin reviewed-checked-in \
    --acknowledge-trusted-local 'reviewed checked-in ETL fixture' --run-id e1
python3 bundle_run.py usecases/ml_eval      --db mleval --execution-policy-profile trusted-local \
    --candidate-origin reviewed-checked-in \
    --acknowledge-trusted-local 'reviewed checked-in ML evaluation fixture' \
    --analyzer "accuracy:max,latency_ms:min,cost_usd:min" --analysis-mode formal --run-id m1
python3 bundle_run.py usecases/event_order  --db evorder --execution-policy-profile trusted-local \
    --candidate-origin reviewed-checked-in \
    --acknowledge-trusted-local 'reviewed checked-in event-order fixture' --run-id v1

# ML against two local surrogate SUTs (offline, no external egress):
(cd "$BUNDLE_SUT_ROOT/advanced_surrogate"  && python3 -m uvicorn app:app --host 127.0.0.1 --port 8055 &)
(cd "$BUNDLE_SUT_ROOT/advanced_surrogate2" && python3 -m uvicorn app:app --host 127.0.0.1 --port 8056 &)
python3 bundle_run.py usecases/ml_eval_surrogate --db mlsurr --execution-policy-profile trusted-local \
    --candidate-origin reviewed-checked-in \
    --acknowledge-trusted-local 'reviewed checked-in local-surrogate fixture; NO SANDBOX' \
    --analyzer "answered:max,latency_ms:min,cost_usd:min" --analysis-mode formal --run-id s1
```

For fintech, inject one ephemeral local-test secret into both terminals. Do not
put it in the command line, this file, or source control.

```bash
# terminal A: local two-node SUT; remains in the foreground
: "${OOT_SECRET:?inject an ephemeral local-test secret}"
export APP_SHARED_SECRET="$OOT_SECRET"
export FINANCE_STACK_REGISTRY=/tmp/fs_oot_reg
cd "$BUNDLE_SUT_ROOT/fin_tech_to_test"
python3 -m finance_stack.node --bank AURUM --alias toBank1 --port 8121 &
python3 -m finance_stack.node --bank NORD  --alias toBank2 --port 8122 &
wait
```

```bash
# terminal B: same OOT_SECRET supplied by the same secret source
cd generator_trunk
: "${OOT_SECRET:?inject the same ephemeral local-test secret}"
python3 bundle_run.py fintech_oot/batches/auth_matrix --db fin_auth \
    --execution-policy-profile trusted-local \
    --candidate-origin reviewed-checked-in \
    --acknowledge-trusted-local 'reviewed checked-in local fintech fixture; NO SANDBOX' --run-id a1
```

## External SUT root

`BUNDLE_SUT_ROOT` names the parent directory containing the mapped projects,
not an individual project checkout. For example, it must contain
`advanced_surrogate/`, `fin_tech_to_test/`, and
`telemetry_catalog_service/` for the examples that use them. Relative values
are resolved from the repository root. Export it before starting
`bundle_run.py` (and before importing `bundle.stages` in an embedded Python
caller), because that module installs the repository-local `suts/` default
when the variable is absent.

## Telemetry catalog verification

```bash
export BUNDLE_SUT_ROOT=/path/to/systems-under-test
python3 -m pytest -q test_telemetry_catalog_e2e.py test_telemetry_catalog_full_e2e.py
```

The two DB-free whole-space tests cover all 576 optional and 729 sentinel forms against
`$BUNDLE_SUT_ROOT/telemetry_catalog_service`. The two Core→Reader pipeline tests additionally need
the built Java artifacts and configured PostgreSQL credentials.

## Notes

- **Determinism = benchmark rigor**: `perf_opt`/`ml_eval` use deterministic surrogate cost models so
  the Pareto front is exactly reproducible; a real study swaps the model for measured numbers (stage
  benchmark harness / a local model server) keeping the spec/oracle/analysis identical.
- **External endpoints stay blocked**: ML uses LOCAL surrogates only; fintech uses the LOCAL bank
  cluster only — no external egress.
- Some fixtures are deliberately faulty so the oracle has failures to discover.
  In particular, `tryout_own/secure_pipeline_app.py` contains documented legacy
  defects, and the pricing fixture explores `fast`/`legacy` modes. Do not
  promote those SUT modes as production implementations.
- Files such as `plan.json`, generated sidecars, metrics corpora, and Analyzer
  fronts are run artifacts or snapshots. Regenerate them from the current spec
  before treating them as evidence. `tryout_own/pricing/collect_front.py`
  performs HTTP work and rewrites `pricing_metrics.kv` at module import time;
  execute it intentionally rather than importing it as a utility.
- The Reader can emit candidates into **multiple locations** (multi-sink fan-out) — the substrate for
  multi-instance / distributed execution (`run_4instance_bundle.py` fans a corpus across instances).
