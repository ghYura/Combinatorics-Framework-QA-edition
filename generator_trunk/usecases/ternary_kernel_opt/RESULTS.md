# Ternary Kernel Optimization Results

Hardware: AMD FX-8320, 8 logical CPUs, SSSE3/SSE4.1, no AVX2.

## Baselines

| Backend | Composite latency | Relative to torch |
|---|---:|---:|
| scalar C++ add/sub | 131.37 ms | 0.09x |
| torch int32 fallback | 11.85 ms | 1.00x |
| SSE4.1 sign backend | 5.94 ms | 2.00x |
| SSSE3 maddubs backend | 2.70 ms | 4.39x |

## Bundle Campaigns

- v1: 54 sign scheduling candidates, 54 PASS, 0 failures.
- v2: 144 sign/maddubs+scheduling candidates, 144 PASS, 0 failures.
- Every candidate compared output exactly with torch int32 before reporting latency.
- Formal v2 champion: maddubs, threads=1, unroll=2, threshold=262144,
  grain_ops=131072, 2.686571 ms.

Repeated interleaved confirmation put top 1/2/4/8-thread configurations inside
measurement noise. The production change is therefore maddubs, not a noisy
single-run scheduling winner.

Evidence is preserved under `evidence_v1/` and `evidence_v2/`.
