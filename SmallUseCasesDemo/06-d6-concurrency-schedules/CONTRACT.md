<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D6 contract v1 — bounded and enabled schedules

D5 is accepted. Implement two independent deterministic schedule simulations in
this folder, using accepted Framework v6. Follow the shared protocol and retain
all preceding examples. These simulations control operation order explicitly;
they do not test OS scheduling, weak memory or real concurrent processes.

## Counter: thread order and preemption bounds

Threads A and B each perform two steps, read then write. A schedule is a four-letter
word with two occurrences of each thread; its nth occurrence executes that thread's
nth step. Thus local order is preserved by construction. Initial counter=0 and no
read snapshots. Each read saves the current counter into that thread's local.

Two implementations: atomic_commit increments the CURRENT counter at write time;
split_rw writes its SAVED read value plus one. Both retain read snapshots for
diagnostics. The reference at every checkpoint is simply the number of writes
completed in the schedule prefix, so its final counter is two. Compare counter
values after every step; local reads are diagnostic and are not an oracle failure
by themselves. Emit the complete observed trace and all failing checkpoints.

A context switch is a change between adjacent thread letters. A preemption is
such a change when the outgoing thread still has an unexecuted local step.
Starting the first thread is neither. Switching after its second step is not a
preemption. Thus AABB has 1 switch/0 preemptions; ABBA 2/1; ABAB 3/2.

Cross cap={0,1,2}, the six two-each schedules, and both policies, retaining only
preemptions<=cap. The caps retain 2,4,6 schedules respectively: 24 cases overall.
Cases include cap in their identity; repeated schedules across caps are separate
declared cases, not additional distinct schedules. Report outcomes per cap, with
their changed population denominators. No fault-frequency extrapolation.

Derived predictions: cap0 4 PASS/0 DOMAIN_FAIL, cap1 6/2, cap2 8/4; total 18/6.
The two serial schedules pass split_rw; all four interleavings lose an update.

## Queue: enabledness before execution

Initially items=[], published_nonempty=false, pop_result=null. Producer P and
consumer C each have two local steps:

- P1 enqueue the string "item"; always enabled.
- P2 set published_nonempty=bool(items); always enabled after P1.
- C1 wait_readable: complete only when the actual queue is nonempty, without
  changing it. This step is disabled while empty.
- C2 try_pop: always enabled after C1; returns/removes the first item, or returns
  the literal "EMPTY". Neither implementation blocks at C2.

actual_queue inspects the actual queue at C2. stale_empty incorrectly returns
EMPTY when published_nonempty is false, even if an item is present. Otherwise it
uses the same pop logic. P2/C1 behavior is unchanged. A policy-blind reference
uses actual_queue semantics and independently checks enabledness at each prefix.

Exactly PPCC, PCPC and PCCP are feasible. The other three two-each schedules
attempt C1 on the initially empty queue at step 1. Record them as excluded
infeasible schedules, never as PASS, domain failures or execution attempts.
This fixture's feasible space happens to equal "first letter is P"; prove that
equivalence using reference-state exploration, not by assuming it generally.

Two policies x three schedules = six cases, predicted 5 PASS/1 DOMAIN_FAIL.
Only stale_empty/PCCP fails: the item exists before publication, but C2 reports
EMPTY and leaves it queued. Compare items and pop_result after EVERY step.
The publication flag is diagnostic; do not require it to equal queue occupancy
between publication events. Retain full policy-specific traces for verification.
Enabledness filtering must use the reference, not the faulty implementation's
state, so it cannot filter away a useful failure.

## Framework construction and bonds

Use primary XLSX+native companion and matching TOML, no optional axes. Mandatory
HEAD, IMPL (position 2), CAP for counter only, S1..S4, TAIL. Each Si selects its
thread independently through Combi(1)->Combi(size). For example, its atom is
set_step(1,"A"); or set_step(1,"B");; keep atom strings whitespace-free and
consistent with params. Runtime reconstructs the schedule and invokes the harness.
Do not catalogue prebuilt complete schedules.

Counter raw product=2 policies x 3 caps x 2^4=96. A require-when bond over S1..S4
requires their numeric a attributes (A=1,B=0) to sum to two, leaving 36 rows.
A second require-when bond also references CAP.n and limits this expression:

    int(S1.a != S2.a)
    + int(S2.a != S3.a and S1.a != S2.a)
    + int(S3.a != S4.a and S1.a != S3.a and S2.a != S3.a)

to CAP.n, leaving 24. Independently derive the expression from prefix completion
counts and verify all 16 raw words; only two-each words are executable cases.
Record raw per-rule matches, overlap and sequential effects separately.

Queue raw product=2 policies x 2^4=32. A require-when bond requires two P values
(p attributes), leaving 12. A require-assert demands S1 equal its P atom,
leaving six. The independent enabledness explorer must prove this bond retains
exactly the three feasible schedules, and runtime must reject any malformed or
disabled schedule as a setup error rather than forcing it to execute.

Both campaigns use --sieve. Required stage counts: counter 96->36->24, then
Reader=Executor=24; queue 32->12->6, then Reader=Executor=6. All identities,
predicted traces and verdicts are frozen in architect-derived.json. Preserve
them unchanged and distinguish derived counts from observed Framework evidence.

## Verification, witnesses and envelope

Provide independent SUT, reference, runtime, builder, runner, offline verifier
and replay tools. The verifier must not import SUT/reference/runtime or execute
candidate sources. Enumerate schedules independently, check local order,
preemption counts and enabledness, every recorded field, every bond's truth
table, and complete Core/Reader/Executor identities. Reconcile per-cap counts;
keep the queue population separate. Archive commands, source/input/build hashes,
plans, tables, dictionary, candidates, all observations and stage logs.

Replay four witnesses: counter split_rw CAP2/ABAB, counter atomic_commit
CAP2/ABAB, queue stale_empty/PCCP, queue actual_queue/PCCP. Record replays as extra
attempts. Show counter split_rw CAP0/AABB as a passing serial control using its
original observation. Explain why a forced switch after completion is free
under the declared bound, and why an infeasible schedule is not a SUT defect.

Run counter then queue once each, fresh as0927_d6counter_* and as0927_d6queue_*
on both ports, generated-default, one worker, K=1, JVM <=2 GB. Per-run budgets:
mandatory rows 150, final candidates 150, disk 100000000 bytes, wall 600 seconds.
Preflight disk/ownership; preserve databases. No external actions, cleanup,
broad tests, live-test sweeps, canonical fixture, commit or push. Focused DB-free
tests only; zero unexpected infrastructure outcomes. Necessary Framework fixes
remain authorized with a minimal reproducer and scope. Apply G1–G7 and deliver
concise EEST-named Markdown here. Do not start D7 until review accepts D6.
