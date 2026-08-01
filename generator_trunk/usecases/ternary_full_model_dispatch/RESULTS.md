# Full-Model Dispatch Results

Runtime-large checkpoint, exact primary+Medusa outputs versus torch int32.

- Bundle candidates: 32.
- Outcomes: 32 PASS, 0 DOMAIN_FAIL/BROKEN/TIMEOUT/INFRA_FAIL.
- Formal Pareto front: 4 configurations.
- Single-run total champion: threads=1, min_cpp_work=65536, 61.255283 ms.

Repeated confirmation did not reproduce the threshold advantage: threads=1 and
min_cpp_work=0 had the best median total latency (60.290 ms). The default remains
all-maddubs (`min_cpp_work=0`). Thread count remains an operator setting.

End-to-end maddubs versus compiled sign was exact and 1.14x/1.18x/1.23x faster
at sequence lengths 1/16/48. Versus torch int32 it was 1.44x faster at seq=16
and 2.03x at seq=48; tiny seq=1 remains overhead-sensitive.

Evidence is preserved under `evidence_v1/`.
