# Scenario 07_constraint_arity — constraint arity (binary vs ternary)

**Category:** constraint arity (binary vs ternary) (pattern like `generator_trunk/constraints/diff_fuzz_when`).

## Simple-language user problem
"I deploy across region, tier, and replicas. One forbidden rule is binary (free tier in a restricted region), but another is a true 3-way rule (enterprise tier in a restricted region with a single replica). What can Bundle enforce before execution, and what can't it?"

## What Bundle can offer
Bundle's sieve v1 executes BINARY [[constraints]] (two sheets) and prunes them before execution; a true ternary (3-sheet) bond is REPORTED as unsupported (never silently skipped) and must be decomposed into binary rules or enforced by the TAIL oracle at runtime.

## Hypothesis
The binary free-tier rule removes 6 rows in the sieve; the ternary rule is reported unsupported, and the oracle catches the enterprise+restricted+single-replica candidates as DOMAIN_FAIL.

## Freedoms -> ZEN verbs
- **region** -> shape *exactly one of a set* -> `FW_Combi(1)` (4).
- **tier** -> shape *exactly one of a set* -> `FW_Combi(1)` (3).
- **replicas** -> shape *exactly one of a set* -> `FW_Combi(1)` (3).
- **binary bond (free x restricted)** -> shape *a bond, arity 2* -> `[[constraints]] sieve v1 (executable)` (removes 6).
- **ternary bond (ent x restricted x single replica)** -> shape *a bond, arity 3* -> `reported unsupported -> decompose or oracle` (oracle DOMAIN_FAIL).

## Oracle (meaning)
sieve v1 applies the binary bond (36->30); the ternary bond is reported unsupported and the TAIL oracle sets FW_VAR=2 for enterprise+restricted+single-replica; else 0

**Goals:** `replicas:max`.
