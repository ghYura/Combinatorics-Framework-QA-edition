# Scenario 15_secondorder_group_rewrite — second-order recombination (FW_Group + FW_ReplaceRE + FW_Separator)

**Category:** second-order recombination (FW_Group + FW_ReplaceRE + FW_Separator) (pattern like `generator_trunk/group_sep_demo + ZEN canonical FW_Group`).

## Simple-language user problem
"I want to take audit-tag subsets and RE-COMBINE those results into groups, rewriting the codes and gluing tokens between elements -- combinations of combinations. What does Bundle do, and can I run it safely?"

## What Bundle can offer
Bundle's UNARY second-order operator: FW_Group re-combines a sheet's PRIOR result rows (combinations of combinations), FW_ReplaceRE rewrites the Core code-string, and FW_Separator weaves a glue token. Authored with fwgen first-class group_replace= and separator= fields. Like the brace, it is a second-order verb the planner cannot estimate, so it is PLAN + GRAPH only in the safe path.

## Hypothesis
FW_Subsets over 3 tags -> 8 result rows; FW_Group recombines them into the second-order space (the planner under-estimates this), so a forced full run trips the reader_emitted_eq_expected invariant.

## Freedoms -> ZEN verbs
- **tag subsets (prior result rows)** -> shape *any subset* -> `FW_Subsets` (2^3 = 8 rows).
- **re-combine + rewrite those prior rows** -> shape *re-combine + rewrite a prior result* -> `FW_Group + FW_ReplaceRE` (second-order (UNKNOWN to planner)).
- **glue token between elements** -> shape *weave a glue token* -> `FW_Separator(GLUE)` (row-preserving modifier).

## Oracle (meaning)
FW_VAR=0 (this scenario demonstrates the second-order recombination shape, not a pass/fail oracle)

**Goals:** `groups:max`.
