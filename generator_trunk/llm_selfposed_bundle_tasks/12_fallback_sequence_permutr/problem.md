# Scenario 12_fallback_sequence_permutr — service fallback sequence (FW_PermutR)

**Category:** service fallback sequence (FW_PermutR) (pattern like `generator_trunk/service fallback repeated sequence`).

## Simple-language user problem
"I design a service fallback strategy with three ordered probe slots. Each slot can probe cache, replica, or primary, and repeats are allowed. I need to know which repeated sequences are deployable for interactive and critical traffic, and compare availability, latency, and cost."

## What Bundle can offer
Bundle models the fallback probe sequence as FW_PermutR(3): an ordered length-3 sequence where the same probe may repeat. It crosses the repeated sequence with request class, runs a TAIL oracle for deployability, and returns an availability/latency/cost Pareto front with PASS-aware front annotations.

## Hypothesis
Three probes over three positions produce 3^3 = 27 ordered sequences with repetition; crossing two request classes produces 54 candidates. Critical traffic fails without a primary probe, interactive traffic fails when it starts with primary, and all-identical or over-budget sequences fail policy.

## Freedoms -> ZEN verbs
- **three-step fallback probe sequence** -> shape *a sequence with repetition* -> `FW_PermutR(3)` (3^3 = 27).
- **request class** -> shape *exactly one of a set* -> `FW_Combi(1)` (2).
- **fallback deployability policy** -> shape *runtime domain policy* -> `TAIL oracle (FW_VAR)` (oracle DOMAIN_FAIL).

## Oracle (meaning)
FW_VAR=2 critical sequence never probes primary; FW_VAR=3 interactive sequence starts with expensive primary; FW_VAR=4 sequence has no diversity or exceeds latency budget; FW_VAR=0 deployable

**Goals:** `availability_score:max`, `latency_ms:min`, `cost_units:min`.
