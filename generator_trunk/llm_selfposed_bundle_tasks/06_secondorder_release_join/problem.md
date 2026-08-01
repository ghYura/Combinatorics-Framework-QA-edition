# Scenario 06_secondorder_release_join — second-order composition (brace)

**Category:** second-order composition (brace) (pattern like `generator_trunk/brace_demo`).

## Simple-language user problem
"I want to build candidate pairs of migration steps (choose 2 of 3) and then JOIN each pair with a target region to get composed release plans."

## What Bundle can offer
Bundle's brace FW_(...) is a second-order JOIN of two PRIOR result tables: operand A = choose-2-of-3 steps (its result table is 3 pairs), operand B = choose-1-of-2 regions (2 rows); the M:N brace joins those result tables into 6 composed plans.

## Hypothesis
The brace consumes the combination-RESULTS of earlier rows (not raw sheets); the join yields 3 x 2 = 6 plans.

## Freedoms -> ZEN verbs
- **choose 2 of 3 migration steps** -> shape *k of n, order irrelevant* -> `FW_Combi(2) (FW_Exclude'd operand)` (C(3,2)=3 pairs).
- **choose 1 of 2 regions** -> shape *exactly one of a set* -> `FW_Combi(1) (FW_Exclude'd operand)` (2).
- **join the two prior result tables** -> shape *join two prior results* -> `brace FW_(,,A,,B,,,,M:N)` (3 x 2 = 6 (UNKNOWN to planner -> class X)).

## Oracle (meaning)
FW_VAR=0 (this scenario demonstrates the second-order join shape, not a pass/fail oracle)

**Goals:** `steps:max`.
