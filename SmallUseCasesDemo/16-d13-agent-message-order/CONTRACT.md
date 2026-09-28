<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D13c contract v1 — bounded agent-message interleavings

Apply ../README.md and G1–G7. Detection question: can two deterministic
agent stubs receive conflicting reservation promises, or lose a promised
reservation, solely because their messages interleave? This tests a local
resource coordinator and message harness. It makes no live-agent, OS-thread,
distributed-consensus or general linearizability claim.

## State and messages

One resource R has capacity one. Agents A and B each deliver two messages in
local order: inspect, then commit. A word such as ABBA means A.inspect,
B.inspect, B.commit, A.commit. Deliveries execute atomically; each case starts
with version=0, allocations={}, issued_grants={}, offers={}. No release,
cancellation, expiry, retry, real network or external model is present.

Inspect returns {available: allocations is empty, version: current version},
saved as that agent's offer. Commit echoes its own offer's version/availability.
These messages are deterministic stubs with schedule-dependent replies, not a
fixed recording or stochastic population. IDs are A:inspect, A:commit, etc.
Request fields and complete checkpoint schema are frozen in architect-derived.json.
Ticket for a granted commit is R:A or R:B. Refusal ticket is null.

All three coordinators return BUSY if the echoed offer was unavailable. Otherwise:

| Policy | Commit with an available offer |
|---|---|
| compare_version | Grant only if allocations is empty AND current version equals offer version; otherwise STALE. |
| trust_offer | Grant using the cached availability alone; retain existing allocations. |
| overwrite_owner | Grant using the cached availability alone; replace all existing allocations with this agent's allocation. |

Each grant returns GRANTED, adds agent→ticket to issued_grants and increments
version by one. Grant adds the allocation, except overwrite_owner first clears
allocations. Refusals change no state. Never remove issued_grants: there is no
revocation message in this protocol. It is an audit ledger of outstanding
promises, distinct from the coordinator's current allocation map.

## Causality and bounded schedules

Two modes: independent allows both initial inspect messages. after_A_offer
allows B.inspect only after A.inspect has completed and published its offer.
This is a declared negotiation dependency, regardless of offer contents.
Commit becomes enabled after that agent's inspect; all remaining local steps
then stay enabled. Delivery of a disabled or malformed message is a setup
error, never a SUT failure or a silently completed step.

Explore enabledness independently using prefix delivery counts. Independent
mode permits all six two-each words. after_A_offer permits AABB, ABAB, ABBA.
Prove this is equivalent to first letter A for this fixture before using the
simple bond. Use reference/harness state, never faulty allocation state, to
decide feasibility. There are no other delays or hidden choices.

A switch changes adjacent agent letters. A preemption is a switch away from
an agent with an enabled local message still undelivered. Starting an agent
and switching after its second message are free. Examples: AABB has one switch
and zero preemptions; ABBA has two/one; ABAB has three/two. Cap K is 0, 1 or 2.

For independent mode the caps retain 2/4/6 schedules; for after_A_offer 1/2/3.
Cap and mode are part of case identity: the same schedule in several strata
is several declared cases, not several distinct delivery orders. Report each
stratum's denominator. There is no weighting or extrapolated failure frequency,
and no claim that the bounded subset preserves all faults. K=1 attempt per case
(the cap is a separate parameter named CAP, not the repetition count).

## Oracle and required observations

Record every request/reply and state immediately after each delivery, including
enabled_agents_before, offers, allocations, issued_grants and version. The
policy-blind reference processes the same messages under compare_version
semantics. The independent oracle must reconstruct issued promises from observed
GRANTED replies; do not trust a SUT-supplied issued_grants map as its only sensor.
Check that supplied map equals the reconstructed ledger at every prefix.

Each checkpoint must satisfy: capacity_ok (at most one current allocation),
exclusive_promises_ok (at most one outstanding granted agent), commitments_ok
(allocations equal outstanding promises), and reference_ok (full trace state
and responses equal the independent reference). Require useful grants and the
correct STALE/BUSY replies: deny-all fails. Source/candidate identity, complete
observed/reference traces, all four check booleans and failing checkpoint
indices accompany the verdict. For supplied-ledger tampering, fail integrity
before evaluating the four checks; actual campaign records must match the ledger.

Every check must pass for PASS; observed contract violations are DOMAIN_FAIL.
Missing records, malformed input or escaped errors fail infrastructure gates.
trust_offer can double-book R. overwrite_owner still reports only one current
allocation but silently withdraws the first agent's promise; capacity alone
therefore misses that defect. Show both mechanisms with full timelines.

## Framework construction and frozen counts

Primary demo.xlsx with native demo.constraints.json and matching spec.toml.
Only mandatory HEAD, IMPL (position 2), MODE, CAP, S1..S4 and TAIL. Each Si
independently chooses set_step(i,"A"); or set_step(i,"B");. Do not catalogue
six prebuilt schedules. Explicit Combi(1)→Combi(size) controls each slot.
Use whitespace-free parameter atoms consistently; the actual decoded row must
determine the schedule. Optional axes are absent. Run with --sieve.

Raw product is 3 policies × 2 modes × 3 caps × 2^4 = **288**. Apply require-when
bonds in this order (S*.a is A=1/B=0, MODE.wait is independent=0/after_A_offer=1,
CAP.n is the integer cap):

1. two_each: S1.a + S2.a + S3.a + S4.a == 2 → 108.
2. causal_ready: MODE.wait == 0 or S1.a == 1 → 81.
3. preemption_cap, expression below <= CAP.n → **54**.

    int(S1.a != S2.a)
    + int(S2.a != S3.a and S1.a != S2.a)
    + int(S3.a != S4.a and S1.a != S3.a and S2.a != S3.a)

Prove the preemption expression on all six two-each words with a separate
prefix-count calculation. Preserve raw truth tables for all 288 combinations;
report rule matches/overlap separately from sequential removals. The architecture
plan reports raw EXACT 288 and post-sieve/final BOUNDED [0,288]: it does not
evaluate selectivity for these predicates. Preserve that label and its reasons;
independent enumeration predicts 54. Expected actual Core=288, sieve=54,
Reader=Executor original attempts=54. Budgets accommodate the conservative
bound; no override or Framework change merely to obtain an EXACT label.

Identity: P=policy|M=mode|K=cap|S=word. Frozen derive.py/architect-derived.json
predict **36 PASS / 18 DOMAIN_FAIL**: compare_version 18/0; each faulty policy
9/9. Per cap: 0→9/0, 1→12/6, 2→15/12. These are predictions until reconciled
with run evidence. Preserve these architecture files unchanged.

## Implementation, demonstration and review

Implement separate SUT, policy-blind oracle, runtime, builder, runner, replay and
offline verifier. Do not import another example's runtime or this derive.py.
The verifier must independently enumerate enabled schedules, recompute all
fields/checks and decode real Core/Reader rows without importing SUT/oracle/runtime
or executing candidates. Compare every frozen identity and observation.
Check XLSX/TOML/sidecar/Core-input equivalence, source inlining, build hashes,
stage counts and one attempt per original candidate. Preserve unchanged v6
unless a necessary defect has a minimal reproducer.

Focused tests: both conflict mechanisms, correct stale refusal, serial BUSY,
deny-all, missing/mutated promises, dropped replies, wrong offer versions,
disabled B.inspect in after_A_offer, malformed local order, and cap/switch
distinction. Unit-test an invalid message without forcing it into the campaign.
Report policy × mode × cap tallies and six distinct schedule support.
Replay these five cases as additional attempts:

- P=trust_offer|M=independent|K=2|S=ABAB — double allocation.
- P=overwrite_owner|M=independent|K=2|S=ABAB — capacity passes, promises fail.
- P=compare_version|M=independent|K=2|S=ABAB — stale offer correctly refused.
- P=overwrite_owner|M=after_A_offer|K=1|S=ABBA — earlier B promise withdrawn.
- P=trust_offer|M=independent|K=0|S=AABB — serial passing control, B gets BUSY.

Before running, compile/plan both inputs and enumerate the reference population.
One fresh as0927_d13c_* campaign on both ports, generated-default, one worker,
repeat=1, JVM <=2 GB. Budgets: mandatory 350, final 350, disk 50,000,000 bytes,
wall 800 seconds. Preflight disk/ownership; record retained database/run sizes.
Archive commands, plans, sidecar, complete sources, Core dictionary/tables,
candidate sources, observations, tests, verifier and replays. Explain why the
negotiation dependency excludes schedules and why capacity alone is inadequate.
Preserve databases/artifacts; no cleanup, broad tests, canonical fixture,
external actions, commit or push. Deliver EEST Markdown here. Do not start D13d.
