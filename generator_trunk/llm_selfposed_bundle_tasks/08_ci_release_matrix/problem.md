# Scenario 08_ci_release_matrix — CI/CD release matrix

**Category:** CI/CD release matrix (pattern like `generator_trunk/release-engineering safety matrix`).

## Simple-language user problem
"I run releases across services. I can vary deployment strategy, database migration kind, test scope, and feature flag state. Which combinations are structurally unsafe before execution, and which risky release plans should the oracle catch?"

## What Bundle can offer
Bundle enumerates the release matrix, applies a binary sieve rule to remove direct deploys with breaking database migrations before execution, runs each surviving release plan through a deterministic safety oracle, and returns a Pareto front over risk, duration, and rollback strength.

## Hypothesis
The sieve removes 12 direct+breaking-migration rows from 108 raw combinations; the oracle catches smoke-tested breaking migrations and smoke-tested canary+feature-flag releases; Analyzer exposes the risk/duration/rollback tradeoff.

## Freedoms -> ZEN verbs
- **service** -> shape *exactly one of a set* -> `FW_Combi(1)` (3).
- **release strategy** -> shape *exactly one of a set* -> `FW_Combi(1)` (3).
- **database migration kind** -> shape *exactly one of a set* -> `FW_Combi(1)` (3).
- **test scope** -> shape *exactly one of a set* -> `FW_Combi(1)` (2).
- **feature flag state** -> shape *exactly one of a set* -> `FW_Combi(1)` (2).
- **direct deploy with breaking migration is forbidden** -> shape *a binary pre-execution bond* -> `[[constraints]] sieve v1` (removes 12).

## Oracle (meaning)
sieve removes direct+breaking migration pre-execution; FW_VAR=2 for breaking migration with smoke tests only; FW_VAR=3 for canary+feature-flag with smoke tests only; FW_VAR=0 accepted release plan

**Goals:** `risk_score:min`, `duration_min:min`, `rollback_score:max`.
