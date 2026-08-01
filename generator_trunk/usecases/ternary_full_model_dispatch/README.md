# Full-Model Ternary Dispatch Optimization

Bundle dogfooding over 32 real runtime-large inference configurations.

- Axes: PyTorch thread count and minimum work required for compiled maddubs.
- Oracle: exact full logits/Medusa outputs versus torch int32 fallback.
- Metrics: median end-to-end latency at sequence lengths 1, 16 and 48.
- Run candidates serially (`--workers 1`) for benchmark validity.
