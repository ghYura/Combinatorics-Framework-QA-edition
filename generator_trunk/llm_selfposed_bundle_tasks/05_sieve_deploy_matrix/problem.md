# Scenario 05_sieve_deploy_matrix — constraint / sieve

**Category:** constraint / sieve (pattern like `generator_trunk/constraints/diff_fuzz_when`).

## Simple-language user problem
"I deploy across regions, plan tiers, and replica counts, but some combinations are illegal before I even run them (the free tier isn't allowed in data-residency-restricted regions). I also want a runtime check that enterprise tiers are sufficiently replicated."

## What Bundle can offer
Bundle declares value attributes ([[params]]) and a binary when-rule ([[constraints]]); the SIEVE deletes the illegal region/tier combinations from the space BEFORE any execution, then the oracle catches the remaining runtime policy (enterprise under-replication).

## Hypothesis
The sieve removes free-tier x restricted-region rows pre-execution; the oracle flags enterprise tier with < 3 replicas at runtime.

## Freedoms -> ZEN verbs
- **region** -> shape *exactly one of a set* -> `FW_Combi(1)` (4).
- **plan tier** -> shape *exactly one of a set* -> `FW_Combi(1)` (3).
- **replica count** -> shape *exactly one of a set* -> `FW_Combi(1)` (3).
- **free-tier-in-restricted-region is FORBIDDEN** -> shape *a bond (pre-execution invalidity)* -> `[[constraints]] sieve (NOT a verb)` (removes 6 rows).

## Oracle (meaning)
sieve removes structurally-invalid combos pre-exec; FW_VAR=2 enterprise under-replicated (replicas<3) at runtime; FW_VAR=0 valid

**Goals:** `replicas:max`.
