# Scenario 10_feature_flag_interaction — feature-flag interaction (FW_Subsets)

**Category:** feature-flag interaction (FW_Subsets) (pattern like `generator_trunk/secure_pipeline FW_Subsets features`).

## Simple-language user problem
"My service has several feature flags; ANY subset can be enabled, and some flag combinations interact badly. I also roll out in stages. Which flag sets are safe, and which interactions break?"

## What Bundle can offer
Bundle models WHICH flags are enabled as FW_Subsets (any subset, 2^n) crossed with the rollout stage; the TAIL oracle catches flag interactions (a dependency, a conflicting pair) because a within-subset bond is not a binary 2-sheet sieve rule; the Analyzer returns a capability-vs-risk Pareto front.

## Hypothesis
Subsets enabling experimental_ui without new_router fail a dependency; audit+cache in canary conflict; the rest pass.

## Freedoms -> ZEN verbs
- **which feature flags are enabled** -> shape *any subset (incl. none)* -> `FW_Subsets` (2^4 = 16).
- **rollout stage** -> shape *exactly one of a set* -> `FW_Combi(1)` (2).
- **flag dependency / conflicting pair** -> shape *a within-subset bond (not a binary sieve rule)* -> `TAIL oracle (FW_VAR)` (oracle DOMAIN_FAIL).

## Oracle (meaning)
FW_VAR=2 experimental_ui without new_router (dependency); FW_VAR=3 audit+cache in canary (conflict); FW_VAR=0 safe

**Goals:** `enabled_flags:max`, `risk_score:min`.
