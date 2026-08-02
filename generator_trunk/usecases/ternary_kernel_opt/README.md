# Ternary Kernel Optimization

Bundle dogfooding campaign for the real compiled FX-8320 SSE4.1 ternary kernel.

- 144 bounded candidates: sign/maddubs algorithms plus scheduling parameters.
- Exact equality against torch int32 matmul is the oracle.
- Real median latency over attention, MoE expert, and vocabulary-head shapes.
- Run with one Bundle worker so candidates do not benchmark concurrently.
- Formal Analyzer goals: `latency_ms:min,throughput_mops:max`.

## Prerequisites

This scenario imports `llm_transformer_testme/testme5upgraded/benchmark_ternary_kernel.py` from the
SUT checkout, which needs **PyTorch**. Without it every candidate is `BROKEN` and the run stops on
the `executor.broken_zero` invariant:

```bash
pip install -r "$BUNDLE_SUT_ROOT/llm_transformer_testme/requirements.txt"
# CPU-only host — much smaller download:
pip install --index-url https://download.pytorch.org/whl/cpu \
            -r "$BUNDLE_SUT_ROOT/llm_transformer_testme/requirements.txt"
```

Equivalently, the Framework's own `test-full` extra carries the same `torch>=2.1` floor. Everything
else this scenario needs is in the SUT checkout — no model checkpoint is required, unlike
[`ternary_full_model_dispatch`](../ternary_full_model_dispatch/README.md).

The 144 candidates are real benchmarks measured serially, so a full run takes appreciably longer
than the other use cases. Silence while a candidate benchmarks is normal.

**Raise the Executor timeout on a CPU-only host.** `--executor-timeout` is a ceiling for the whole
Executor *stage*, not per candidate, and it defaults to 3600 s. On a machine without the compiled
SSE4.1 kernel — where every candidate falls back to a plain PyTorch matmul — 144 serial benchmarks
overrun that budget and the run stops on the `executor.timeout_zero` invariant with 144 timeouts and
no results. Measured here: the default was not enough on an eight-core CPU host.

```bash
python generator_trunk/bundle_run.py generator_trunk/usecases/ternary_kernel_opt \
  --db ternary_kernel --lang py --workers 1 \
  --executor-timeout 21600 \
  --execution-policy-profile trusted-local \
  --candidate-origin reviewed-checked-in \
  --acknowledge-trusted-local 'reviewed checked-in ternary scenario'
```

A wall of `TIMEOUT` outcomes here means the budget was too small, not that the SUT is broken.

The scenario tunes runtime scheduling parameters only. It does not modify model
weights or checkpoints.
