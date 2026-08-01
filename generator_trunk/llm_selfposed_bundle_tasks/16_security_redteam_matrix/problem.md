# Scenario 16_security_redteam_matrix — security red-team (order + sudden attacks)

**Category:** security red-team (order + sudden attacks) (pattern like `generator_trunk/tryout_own/spec (secure pipeline) + event_order`).

## Simple-language user problem
"A request passes security checks (authn, authz, ratelimit) in some order, and an attacker may fire sudden steps (token replay, privilege escalation). Which check orders and which attacks cause a breach?"

## What Bundle can offer
Bundle runs the security checks in every order (FW_Permut) and bolts on optional sudden attacks (FW_Optional: token replay, privilege escalation); a breach oracle reports which order+attack combinations slip through -- the engine's strongest story (interactions, order, sudden state-changes).

## Hypothesis
Authorizing before authenticating is broken access control; a replay slips through when authn is not bound first; escalation slips through when ratelimit precedes authz.

## Freedoms -> ZEN verbs
- **security check order** -> shape *an ordering* -> `FW_Permut` (3! = 6).
- **token-replay attack may or may not fire** -> shape *may-or-may-not (sudden action)* -> `FW_Optional` (x2).
- **privilege-escalation attack may or may not fire** -> shape *may-or-may-not (sudden action)* -> `FW_Optional` (x2).

## Oracle (meaning)
FW_VAR=2 authz before authn; FW_VAR=3 token replay (authn not first); FW_VAR=4 privilege escalation (ratelimit before authz); FW_VAR=0 secure

**Goals:** `breach:max`.
