# Scenario 11_db_config_cartes — DB-config tuning / FW_Cartes workload matrix

**Category:** DB-config tuning / FW_Cartes workload matrix (pattern like `generator_trunk/database config workload matrix`).

## Simple-language user problem
"I tune PostgreSQL-like database configs across workload classes and data sizes. I need to cross config profiles with OLTP/analytics/mixed workloads, catch under-provisioned combinations, and compare p95 latency, cost, and stability."

## What Bundle can offer
Bundle models DB config profile as FW_Cartes(WORKLOAD), crossing each config profile with each workload class, then crosses that matrix with data size. The TAIL oracle catches workload-specific under-provisioning and the Analyzer exposes p95/cost/stability trade-offs.

## Hypothesis
The 3 config profiles x 3 workload classes x 2 data sizes produce 18 candidates; analytics workloads fail when work_mem is below 64 MB, OLTP workloads fail when pool_size is below 32, and the remaining candidates form a p95/cost/stability trade-off set.

## Freedoms -> ZEN verbs
- **DB config profile crossed with workload class** -> shape *cross another sheet* -> `FW_Cartes(WORKLOAD)` (3 x 3 = 9 matrix cells).
- **workload class operand** -> shape *exactly one of a set, set aside as the Cartes operand* -> `FW_Combi(1) + FW_Exclude` (3 operand values).
- **data size** -> shape *exactly one of a set* -> `FW_Combi(1)` (2).
- **workload/config compatibility** -> shape *runtime domain policy* -> `TAIL oracle (FW_VAR)` (oracle DOMAIN_FAIL).

## Oracle (meaning)
FW_VAR=2 analytics workload under-provisioned when work_mem < 64 MB; FW_VAR=3 OLTP workload under-provisioned when pool_size < 32; FW_VAR=0 acceptable

**Goals:** `p95_ms:min`, `cost_units:min`, `stability_score:max`.
