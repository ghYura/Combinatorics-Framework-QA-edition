<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D13e contract v1 — context order, reduced coverage and noisy judges

Apply ../README.md and G1–G7. Use deterministic local processors and
pseudorandom judge surrogates. Questions: does context order change a required
decision, does an ordered-triple cover detect a position-specific defect, and
does a noisy judge's accuracy depend on guard position? No external model/API,
live judge, real outbound action or claim about such systems is in scope.

## Context processors and mechanical truth

Each context permutes G,A,B,C,D,E once each. G is a trusted guard; A is an
untrusted marker requesting ALLOW; B–E are inert untrusted chunks. Tokens are
fixture symbols, not natural-language prompts. Task public requires ALLOW;
task secret requires DENY. This policy-blind truth is invariant over all orders.

Each processor starts decision=null and folds the six chunks:

| Policy | G | A | Other chunks |
|---|---|---|---|
| stable | Set the task's correct decision. | Ignore. | Ignore. |
| last_marker | Set the task's correct decision. | Set ALLOW. | Ignore. |
| third_position | Set ALLOW when G is third; otherwise the correct decision. | Ignore. | Ignore. |

Record position, token, origin (G trusted, others untrusted), before and after
at every step. Only the final decision produces an output; transient fold state
is diagnostic. Correct public decisions exclude a deny-all shortcut. A malformed
context is a setup error; never silently omit or duplicate a chunk.

## Coverage certificate and deliberate gap control

The full mathematical universe has 720 orders. coverage.json freezes an
eight-order SCA3 cover found offline by SciPy/HiGHS: each of 120 ordered triples
occurs as a subsequence. Independently verify all obligations; do not claim a
minimum from the feasibility certificate or attribute the solver to Framework.
This particular suite has no order with G in position 3, despite covering all
ordered triples. It misses third_position on secret tasks.

Add exactly ABGCDE as a separate, preregistered position control. It exposes that
miss. Keep the eight-order cover and one-order supplement distinguishable in
all analyses. The supplement was chosen from the known model before any run;
it is not an independently sampled discovery. No global coverage certificate
is conferred by adding this one witness. Do not substitute another cover.

Offline enumeration of all 720 orders predicts stable 0 failures, last_marker
360 and third_position 120 across the two tasks per policy. That is a model
calculation, not 4320 executed cases. Do not estimate full-universe fault rates
from the deliberately selected nine-order suite.

## Twenty internal trials and two judge sensors

One Framework candidate is (policy, task, order). It performs 20 internal trials
numbered 0..19, resetting the processor each time. These are deterministic
processor calls with pseudorandom judge errors. Framework repeat remains 1:
do not describe this as a native --repeat 20 campaign or 20 distinct contexts.

For each trial compute SHA-256 of ASCII
`d13e|{policy}|{task}|{order}|{trial}`. Take the first 16 hexadecimal characters;
let n be that unsigned integer and D=2^64. Record draw_hex, decision, full
context_trace, mechanical_ok=(decision equals task truth), and judge_approvals.
Both judges share this draw within a trial, intentionally pairing their errors.

- calibrated flips the mechanical_ok label iff 10*n < D (nominal 10% error).
- position_biased flips iff 5*n < 3*D when G is in positions 1–3 (early), and
  iff 10*n < D when G is in positions 4–6 (late).
- A judge's approval is mechanical_ok XOR its flip bit. Approval means it
  claims the decision is correct, not that the underlying action is ALLOW.

Implement judge surrogates separately from the mechanical oracle. Supplying
the known mechanical label to this simulated noise channel is intentional;
it is a labelled calibration fixture, not an independent semantic LLM judge.
Judge errors never determine the Framework verdict. A candidate is PASS only
if all 20 processor decisions meet task truth; otherwise DOMAIN_FAIL. Missing
trials, bad draws or malformed traces fail evidence/infrastructure gates.

## Counts, statistics and limitations

Nine orders × two tasks × three policies = **54 Framework candidates**, each
executed once. They contain **1080 processor trials** and **2160 judge readings**.
The SCA3 portion contributes 48 candidates / 960 trials (160 per policy/task
pair); the supplement contributes 6 / 120. Expected outcomes: **49 PASS / 5
DOMAIN_FAIL**. The cover finds four last_marker failures; the supplement finds
one third_position failure. Frozen per-trial values are in architect-derived.json.

For each judge × early/late band report n, TP/FN/FP/TN against mechanical truth,
accuracy, false-approval counts and the nominal error probability. Report task
and processor strata as well. Never use a noisy approval as the correctness
oracle. Compute the paired disagreement table; late-band judges must agree
exactly. Early-band accuracy disagreement has the declared common-draw coupling.

Also report a Wilson interval using z=1.96, p=correct/n:
center=(p+z²/(2n))/(1+z²/n), half=z*sqrt(p(1-p)/n+z²/(4n²))/(1+z²/n).
Compare numeric outputs to frozen values within 1e-12. These are illustrative
sampling-model intervals under a Bernoulli approximation to the pseudorandom
draws. The frozen fixture is deterministic; rerunning it provides no new
independent evidence. Intervals do not establish real-judge accuracy, cover-suite
representativeness or a confidence bound on live-model safety. Do not pool the
paired judges as independent samples or invent a significance acceptance gate.

## Framework mapping and implementation

Use primary demo.xlsx plus equivalent spec.toml. Mandatory HEAD, IMPL (position
2), TASK, ORDER, TAIL. ORDER is the explicitly certified nine-order catalogue,
not 54 prebuilt programs; each atom selects one order. Use Combi(1)→Combi(size).
Plans/Core/Reader/Executor should all show EXACT 54; no sieve or optional axis.
Actual decoded rows determine policy/task/order. Native full FW_Permut sizing
may be demonstrated in a planning-only probe; never execute the full universe.

Preserve CONTRACT.md, coverage.json, derive.py and architect-derived.json.
Provide separate processor, judge, mechanical oracle and runtime; no imports
from another example or derive.py. Offline verifier must not import those
implementation modules or execute candidates. Independently verify coverage,
the missing-position witness, all 4320 model cases, 54 identities, 1080 trial
records, judge draws/readings, aggregate statistics and generated-source mapping.
Verify all input/build hashes and workbook/TOML/Core-input equivalence.

Focused tests: wrong context order or duplicate/missing chunk, wrong task truth,
deny-all, suppressed third-position control, coupled judge draws, wrong threshold,
judge approval used as ground truth, missing trial and tampered calibration.
Preflight the verifier parser on a composed candidate before running.
Replay five complete candidates (each with its 20 trials):

- P=last_marker|T=secret|O=GABEDC — context-order failure.
- P=stable|T=secret|O=GABEDC — matched correct processor.
- P=third_position|T=secret|O=ABGCDE — missed by SCA3, caught by supplement.
- P=stable|T=public|O=ABGCDE — useful ALLOW control.
- P=stable|T=secret|O=ABCDEG — late-band paired-judge control.

Run one fresh as0927_d13e_* campaign on both ports, accepted Framework v6,
generated-default, one worker, repeat=1, JVM <=2 GB. Budgets: mandatory/final 100,
disk 50,000,000 bytes, wall 400 seconds. Preflight disk/ownership and both plans;
record retained sizes. Preserve all evidence/databases, commands, complete
observations, verification, tests and replays. No external calls, cleanup,
canonical fixture, broad tests, commit or push. Necessary evidenced fixes remain
authorized. Deliver EEST Markdown. Do not start D14a.
