# Scenario 14_control_pair_combi2 — security control pair selection (FW_Combi(2))

**Category:** security control pair selection (FW_Combi(2)) (pattern like `generator_trunk/security control choose-k pair`).

## Simple-language user problem
"I need to choose exactly two security controls from rate_limit, captcha, waf, and review_queue. Order does not matter and repeats are not allowed. Which pairs are safe for public API and admin API traffic, and how do coverage, friction, and cost trade off?"

## What Bundle can offer
Bundle models the control pair as FW_Combi(2): choose exactly two distinct controls, order irrelevant. It crosses the pair with traffic profile, uses a TAIL oracle for admin-without-WAF and public excessive-friction policies, and returns a coverage/friction/cost Pareto front with PASS-aware annotations.

## Hypothesis
Four controls choose two gives C(4,2)=6 pairs; crossing public/admin traffic gives 12 candidates. Admin traffic fails without WAF, public traffic fails for captcha+review_queue, and the remaining pairs form a coverage/friction/cost trade-off.

## Freedoms -> ZEN verbs
- **choose exactly two security controls** -> shape *k of n, order irrelevant, no repetition* -> `FW_Combi(2)` (C(4,2) = 6).
- **traffic profile** -> shape *exactly one of a set* -> `FW_Combi(1)` (2).
- **control-pair policy** -> shape *runtime domain policy* -> `TAIL oracle (FW_VAR)` (oracle DOMAIN_FAIL).

## Oracle (meaning)
FW_VAR=2 admin traffic pair is missing WAF; FW_VAR=3 public traffic pair has excessive friction; FW_VAR=0 safe

**Goals:** `coverage_score:max`, `friction_score:min`, `cost_units:min`.
