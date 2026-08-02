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

The scenario tunes runtime scheduling parameters only. It does not modify model
weights or checkpoints.
