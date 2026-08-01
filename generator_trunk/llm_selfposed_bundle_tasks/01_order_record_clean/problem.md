# Scenario 01 — Order-sensitive record cleaning (data hygiene)

**Category:** order-sensitive pipeline (TZ#2 category 1; pattern like `usecases/etl_pipeline`).

## Simple-language user problem
"I have a small customer list with messy duplicates (same person typed with different
case/spacing) and some missing emails. I want to clean it: normalize the fields, apply a
null-email policy, and de-duplicate. I suspect the **order** of those three steps changes the
result. Can the Bundle tell me which orders are safe and which silently corrupt the data?"

## What Bundle can offer
Bundle enumerates **every order** of the three cleaning steps (a permutation freedom), crosses that
with the null-policy and the dedupe-key choices, runs each concrete pipeline against a fixed messy
dataset, and judges the output with a **data-quality oracle** (no surviving duplicate id; no leaked
null email when the policy forbids it). The verdict distribution shows exactly which orderings are
correct and which leak — the classic *"dedupe before normalize"* bug.

## Hypothesis
Orders that run **dedupe before normalize** fail to collapse case/spacing variants → a duplicate id
survives (DOMAIN_FAIL, code 2). The canonical order normalize → nullfix → dedupe is clean (PASS).

## Freedoms
- cleaning-step **order** → shape = *an ordering* → `FW_Permut` (3! = 6).
- **null policy** (drop / keep) → shape = *exactly one of a set* → `FW_Combi(1)` (2).
- **dedupe key** (by_id / by_email) → shape = *exactly one of a set* → `FW_Combi(1)` (2).
- Mandatory product = 6 × 2 × 2 = **24** candidates (no optional, no sieve).

## Oracle (meaning)
`FW_VAR = 2` duplicate id survived; `FW_VAR = 3` null email leaked under a non-keep policy;
`FW_VAR = 0` clean, deduped, policy-consistent table. Goal for the Analyzer: `rows_out:max`.
