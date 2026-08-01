# Scenario 04_ml_rerank_eval — ML/LLM outer-structure evaluation

**Category:** ML/LLM outer-structure evaluation (pattern like `generator_trunk/usecases/ml_eval`).

## Simple-language user problem
"For a text classifier I can vary the preprocessing order, the retrieval chunk size, and whether to use a reranker. Which outer structures clear my quality bar, and what do they cost?"

## What Bundle can offer
Bundle treats the discrete OUTER structure as the freedom (preprocessing order is a permutation; chunk and reranker are exactly-one choices), evaluates each with a LOCAL deterministic surrogate, applies a quality-gate oracle, and Pareto-ranks accuracy vs latency vs cost.

## Hypothesis
Some preprocessing orders and the smallest chunk without a reranker fall below the 0.75 accuracy gate (DOMAIN_FAIL).

## Freedoms -> ZEN verbs
- **preprocessing order** -> shape *an ordering* -> `FW_Permut` (3! = 6).
- **retrieval chunk size** -> shape *exactly one of a set* -> `FW_Combi(1)` (3).
- **reranker on/off** -> shape *exactly one of a set* -> `FW_Combi(1)` (2).

## Oracle (meaning)
FW_VAR=4 below the 0.75 quality gate (DOMAIN_FAIL); FW_VAR=0 passes

**Goals:** `accuracy:max`, `latency_ms:min`, `cost_usd:min`.
