# Scenario 17_qa_pub_joke_promo — promo/demo (QA tester walks into a pub)

**Category:** promo/demo (QA tester walks into a pub) (pattern like `generator_trunk/boundary/type/domain + order abuse demo`).

## Simple-language user problem
"Turn the classic 'a QA tester walks into a pub and orders 1, 0, -1, 999999999, abcd beers, a lizard...' joke into a real Bundle test: different entries, weird quantities, weird targets, and permuted action order; the bar must never crash."

## What Bundle can offer
Bundle makes boundary/type/domain abuse FIRST-CLASS values and generates invalid action orders ON PURPOSE (FW_Permut), not by chance; the oracle separates clean rejection from a crash or silent accept. A one-minute Bundle explainer. Motto: 'Bundle walks into the pub before your users do.'

## Hypothesis
Acting before entering is an order bug; non-numeric/negative/huge quantities must be rejected cleanly (never crash/overflow); a lizard is an invalid target; normal and zero-no-op orders pass.

## Freedoms -> ZEN verbs
- **entry mode** -> shape *exactly one of a set* -> `FW_Combi(1)` (3).
- **action order** -> shape *an ordering* -> `FW_Permut` (3! = 6).
- **order quantity (boundary/type/domain)** -> shape *exactly one of a set* -> `FW_Combi(1)` (5).
- **order target** -> shape *exactly one of a set* -> `FW_Combi(1)` (3).

## Oracle (meaning)
FW_VAR=2 acted before entering; FW_VAR=3 invalid quantity rejected cleanly (type/domain/huge); FW_VAR=4 invalid target (lizard); FW_VAR=0 accepted (normal or zero no-op)

**Goals:** `accepted:max`.
