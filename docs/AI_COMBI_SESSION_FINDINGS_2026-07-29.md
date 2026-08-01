# AI-combinatorial testing: engineering and empirical findings

**Date:** 2026-07-29
**Scope:** the release-gate breakpoint sub-suite, its Bundle evidence boundary, one anonymized
terminal target cell, and unsuccessful browser acquisition attempts.

## Bottom line

This session moved the AI-testing claim from apparatus-only plausibility to a bounded empirical
proof of concept. A simple clean-prompt sample made the anonymized target look fully reliable; the
Bundle-constructed high-contrast variants exposed a repeatable semantic error on the same canonical
task. That is useful evidence for combinatorial prompt-response robustness testing, but it is not a
universal model ranking or a statistically mature benchmark.

## 1. Optional expansion and the reconciliation defect

Four independent one-valued `FW_Optional` atoms do not become ordinary `fw_final` factors. Core
keeps mandatory and optional materialization factored, while Reader assembles the Cartesian result.
The two relevant run-private properties are:

| Component | Property | Meaning |
|---|---|---|
| Core | `core.optional.includeOptionalCombiPairsToDBCSVList=1,2,3,4` | materialize `fw_opt1..4` |
| Reader | `reader.core.isOptCSVList=1,2,3,4` | consume those optional tables |

The launcher derives both lists from the same number of optional slots. For the five-level
release-gate apparatus:

```text
Core fw_final = 160 mandatory rows
optional rows by size = C(4,1)+C(4,2)+C(4,3)+C(4,4) = 4+6+4+1
Reader = 160 × (1 absent branch + 15 present combinations) = 2,560
```

The AI-platform reporter incorrectly required `Core fw_final == Reader candidates`. Every Bundle
stage could succeed, yet exchange packaging failed during post-run reconciliation. The fix replaces
that invalid equality with `Reader actual == Reader stage expected`; the latter is already computed
and enforced as post-sieve mandatory rows multiplied by the exact optional multiplier. Reader is
then reconciled with Executor processed count, terminal outcomes, metrics, and Analyzer provenance.

This is a reporting/export-closure bug, not a Core or Reader enumeration bug. Manually configured
component launches must still keep the producer and consumer optional-size lists aligned.

Post-fix verification covered the complete reconciliation path with synthetic regression data. A
live safe-profile rerun also reached Core `160` and Reader actual/expected `2,560`. The secure
per-candidate Executor replay was intentionally stopped because container startup made completing
all 2,560 candidates impractical in this environment; cleanup then verified zero remaining
ephemeral databases. Consequently, this session does not claim a new successful full-chain live
closure.

## 2. Anonymized terminal target observation

The target identity is intentionally abstracted as **Target A**. The invocation used a local
terminal client and a fresh ephemeral session for every prompt, at the target's lowest supported
reasoning-effort setting. “Local terminal” describes the client surface; it does not claim that
inference occurred on the local machine.

Controls applied to every designed call:

- no browser, pasted API key, or direct API integration;
- read-only empty working directory;
- approval mode disabled and zero tool calls;
- one fresh ephemeral session per prompt;
- the same exact packaged oracle used for strict and semantic adjudication.

| Phase | Design | Strict PASS | Semantic PASS |
|---|---|---:|---:|
| Endpoint phase | five task levels × clean/max-stress | 9/10 | 9/10 |
| Fixed-task follow-up | ten-row strength-two design, weights 0..9 | 7/10 | 7/10 |
| Designed total | 20 fresh sessions | **16/20** | **16/20** |

One additional preflight smoke call passed, making 21 real target calls in total. Across the 20
designed calls, terminal event records contained zero tool calls and zero terminal errors. Recorded
usage was 235,341 input tokens, including 199,680 cached input tokens, plus 2,276 output tokens and
1,720 reasoning-output tokens.

### High-contrast result

All five clean endpoint prompts passed. On a fixed two-check canonical task, the clean endpoint
passed in both phases (`2/2`) while the maximal construction endpoint failed in both (`0/2`). In
the strength-two follow-up, weights 0 through 6 passed and weights 7 through 9 failed. Because each
interior row was sampled once, this is an observed boundary requiring repetition, not an estimated
failure probability.

The failure was semantic, not formatting. Target A returned:

```text
DECISION HOLD; FAILED RG-001,RG-002
```

The exact answer was:

```text
DECISION HOLD; FAILED RG-001
```

`RG-002` required an observed count of at least 56; the task supplied 58. The extra failed check was
therefore objectively wrong. Repetition at both endpoints makes the contrast more informative than
a single accidental format miss, while still being too small for a general reliability claim.

## 3. What the combinatorics contributed

The useful contribution was experiment construction, not testing whether the target could reason
about combinatorics. Bundle made it possible to:

- freeze canonical task truth before rendering;
- hold task identity fixed while changing nine construction factors;
- compare clean and maximal endpoints before spending calls on an interior design;
- use a strength-two design that covers every binary factor pair in ten rows;
- separate format failure from exact semantic failure; and
- locate accumulated interaction pressure that a clean-only sample concealed.

A clean-only evaluation would have observed `5/5` and missed the failure. The combined evidence is
therefore a concrete proof of concept that structured combinatorial contrasts can reveal prompt
robustness defects which ordinary spot checks do not.

## 4. Browser acquisition was non-evidence

Attempts through two provider web interfaces repeatedly reached anti-bot/CAPTCHA verification. No
complete response corpus was accepted from those attempts, and no CAPTCHA event was scored as a
model failure. Such challenges are infrastructure outcomes. Browser automation should abort or
fall back to an authorized manual/API/terminal acquisition route; it must not claim reasoning
evidence from a blocked session or preserve account/profile data as test source.

The practical acquisition order is an authorized terminal client or official API with
environment-only credentials and explicit budgets, then a human-operated fresh-session exchange,
with browser automation last. Acquisition remains separate from adjudication: responses are bound
to target/session/task identities and scored offline by the exact oracle. No API key belongs in a
prompt, generated candidate, response package, or committed configuration.

## 5. Claim limits and next experiments

The evidence covers one anonymized target, one effort setting, one campaign, and one canonical task
at the replicated endpoint boundary. It supports “Bundle can expose a real prompt-construction
robustness defect,” not “Bundle ranks all models” or “difficulty grows exponentially with factor
weight.” Stronger evidence needs:

1. repeated trials for every interior row and randomized execution order;
2. additional anonymized target cells and effort settings;
3. more exact-oracle task families;
4. single-factor and interaction ablations around weights 6–9;
5. retained, sanitized machine evidence or an independently replayable evidence bundle; and
6. preregistered thresholds for prompt CI or routing decisions.

Raw prompts, responses, event streams, browser state, credentials, generated candidates, databases,
and run directories are runtime evidence and are not committed with this document.
