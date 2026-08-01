# Scenario 03_pareto_cache_design — design-space / Pareto

**Category:** design-space / Pareto (pattern like `generator_trunk/usecases/perf_opt`).

## Simple-language user problem
"I'm choosing a cache layer: eviction policy, size, TTL, and whether to prefetch. Every choice is valid; I want the best trade-offs of hit-rate, memory, and tail latency."

## What Bundle can offer
Bundle enumerates the full design space (one choice per axis), evaluates each with a deterministic surrogate cost model, and the Analyzer returns the non-dominated (Pareto) configs over three conflicting objectives.

## Hypothesis
No single config wins all three objectives; a Pareto front of trade-offs exists.

## Freedoms -> ZEN verbs
- **eviction policy** -> shape *exactly one of a set* -> `FW_Combi(1)` (3).
- **cache size** -> shape *exactly one of a set* -> `FW_Combi(1)` (3).
- **entry TTL** -> shape *exactly one of a set* -> `FW_Combi(1)` (2).
- **prefetch toggle** -> shape *exactly one of a set* -> `FW_Combi(1)` (2).

## Oracle (meaning)
FW_VAR=0 for every config (optimization, not pass/fail); the Analyzer selects, it does not reject

**Goals:** `hit_rate:max`, `memory_mb:min`, `p99_latency_ms:min`.
