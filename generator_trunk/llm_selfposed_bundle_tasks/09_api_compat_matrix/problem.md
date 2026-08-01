# Scenario 09_api_compat_matrix — API compatibility matrix

**Category:** API compatibility matrix (pattern like `generator_trunk/API/client/payload contract matrix`).

## Simple-language user problem
"I maintain an API with v1/v2/v3 versions and several client SDK generations. I need to test which client/auth/payload combinations are compatible, which pairs are structurally unsupported, and which trade-offs are best for compatibility, latency, and migration effort."

## What Bundle can offer
Bundle enumerates API version, client SDK, auth scheme, and payload shape; the binary sieve removes unsupported legacy-SDK/v3 pairs before execution; the TAIL oracle catches executable but incompatible payload/auth cases; the Analyzer returns a compatibility/latency/migration-effort Pareto front.

## Hypothesis
The sieve removes 9 legacy-SDK/v3 rows from 81 raw combinations; the oracle catches v1+bulk payloads and beta-SDK JWT legacy payloads; Analyzer exposes the compatibility/latency/migration trade-off.

## Freedoms -> ZEN verbs
- **API version** -> shape *exactly one of a set* -> `FW_Combi(1)` (3).
- **client SDK generation** -> shape *exactly one of a set* -> `FW_Combi(1)` (3).
- **auth scheme** -> shape *exactly one of a set* -> `FW_Combi(1)` (3).
- **payload shape** -> shape *exactly one of a set* -> `FW_Combi(1)` (3).
- **legacy SDK against v3 API is forbidden** -> shape *a binary pre-execution contract bond* -> `[[constraints]] sieve v1` (removes 9).

## Oracle (meaning)
sieve removes legacy_sdk+v3 API pre-execution; FW_VAR=2 for v1 API with bulk_json payload; FW_VAR=3 for beta_sdk+jwt+legacy_json; FW_VAR=0 compatible combination

**Goals:** `compat_score:max`, `latency_ms:min`, `migration_effort:min`.
