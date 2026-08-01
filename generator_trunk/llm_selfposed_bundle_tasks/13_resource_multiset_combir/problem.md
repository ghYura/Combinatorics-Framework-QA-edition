# Scenario 13_resource_multiset_combir — resource allocation multiset (FW_CombiR)

**Category:** resource allocation multiset (FW_CombiR) (pattern like `generator_trunk/resource multiset allocation`).

## Simple-language user problem
"I allocate 3 worker slots from instance types {cpu, gpu, mem}, and I can pick the same type more than once. Which allocation mixes are safe for batch vs serving, and how do diversity and cost trade off?"

## What Bundle can offer
Bundle models the allocation as FW_CombiR(3): a size-3 MULTISET over the instance types (repetition allowed) crossed with the workload class; a resource-mix oracle flags zero-diversity (single point of failure) and serving-without-gpu; the Analyzer returns a diversity-vs-cost Pareto front.

## Hypothesis
All-identical allocations are single points of failure (DOMAIN_FAIL); serving with no gpu slot fails; the rest pass; cost rises with gpu slots.

## Freedoms -> ZEN verbs
- **3 worker slots from 3 instance types, repetition allowed** -> shape *k of n WITH repetition* -> `FW_CombiR(3)` (C(5,3) = 10).
- **workload class** -> shape *exactly one of a set* -> `FW_Combi(1)` (2).
- **resource-mix policy** -> shape *runtime domain policy* -> `TAIL oracle (FW_VAR)` (oracle DOMAIN_FAIL).

## Oracle (meaning)
FW_VAR=2 zero diversity (all slots same type); FW_VAR=3 serving without a gpu slot; FW_VAR=0 safe (codes kept small to fit combo-column capacity)

**Goals:** `diversity:max`, `cost_units:min`.
