# Full-Model Ternary Dispatch Optimization

Bundle dogfooding over 32 real runtime-large inference configurations.

- Axes: PyTorch thread count and minimum work required for compiled maddubs.
- Oracle: exact full logits/Medusa outputs versus torch int32 fallback.
- Metrics: median end-to-end latency at sequence lengths 1, 16 and 48.
- Run candidates serially (`--workers 1`) for benchmark validity.

## Prerequisites — read before running

> **This scenario cannot run from a clean checkout of the two repositories.** It is kept as a
> reproducible description of a measured experiment, not as a runnable gate. Budget nothing for it
> unless you already hold the checkpoint below.

Two things are required:

1. **PyTorch** — `pip install -r "$BUNDLE_SUT_ROOT/llm_transformer_testme/requirements.txt"`.
2. **A trained checkpoint** at
   `$BUNDLE_SUT_ROOT/llm_transformer_testme/testme5upgraded/weights/bundle_medusa_moe_transformer_large_runtime.pt`.

The checkpoint is **deliberately not distributed** — the SUT repository's `.gitignore` excludes
`weights/`, `*.pt` and `*.pth`, consistent with the QA edition's rule that generators ship as source
while their runtime products stay local. Reproducing it means running the SUT's own
`testme5upgraded/train_bigger.py`, which is a training job and is not deterministic, so a rebuilt
checkpoint will not reproduce the numbers in `RESULTS.md`.

Without the file, every candidate fails with `FileNotFoundError` and the run stops on the
`executor.broken_zero` invariant — that is the expected outcome, not a broken install.

For a scenario that exercises the same SUT and *does* run from a clean checkout, use
[`ternary_kernel_opt`](../ternary_kernel_opt/README.md): it needs PyTorch but no checkpoint.
