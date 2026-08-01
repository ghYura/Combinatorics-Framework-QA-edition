# Ternary Kernel Optimization

Bundle dogfooding campaign for the real compiled FX-8320 SSE4.1 ternary kernel.

- 144 bounded candidates: sign/maddubs algorithms plus scheduling parameters.
- Exact equality against torch int32 matmul is the oracle.
- Real median latency over attention, MoE expert, and vocabulary-head shapes.
- Run with one Bundle worker so candidates do not benchmark concurrently.
- Formal Analyzer goals: `latency_ms:min,throughput_mops:max`.

The scenario tunes runtime scheduling parameters only. It does not modify model
weights or checkpoints.
