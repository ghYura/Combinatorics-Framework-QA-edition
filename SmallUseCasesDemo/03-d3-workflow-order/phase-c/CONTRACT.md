<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D3 phase C — certified coverage versus detection

This supplements the immutable A/B contract. A/B are accepted; D3 remains open.
Implement independently under phase-c/; preserve all A/B sources and evidence.
The shared protocol, author decisions and G1–G7 still apply.

## State machine and population

Use the A/B correct billing rules for C/F/N/S/Q, plus V (read-only view, no state
change). Each of these six events occurs exactly once; all 720 orders are legal
test inputs because ineligible operations are no-ops. Fresh state per candidate.
Two policies: correct and late_restart. Uniform weight per distinct order/policy;
one deterministic attempt per case. No production-frequency inference.

Public state adds Boolean refund_attempted to the A/B snapshot. Initially false;
F sets it true before applying the normal refund rule; N resets it false after
opening the new epoch. C, Q, V and S preserve this flag. Correct S creates a new
service over the retained ledger/flag and reloads balance from the ledger.

late_restart changes S only: if epoch==1, captures==[1,0], refunds==[0,0], and
refund_attempted is true, initialize balance to zero instead of reloading it.
Otherwise behave correctly. This models a faulty recovery branch after a renewal
and an unsuccessful refund attempt. The reference never reads the policy.

Copy/check the entire public snapshot after EVERY event, with the A/B accounting
invariants and Boolean flag validation. Keep all failures and separately report
final-only observation. V must not repair state. Classify unexpected exceptions
as BROKEN. Exact case ID: C|policy|OPS=six letters.

Derived trigger: C precedes N precedes F precedes S. Exactly 30 orders trigger
late_restart; six heal because Q follows S. Predicted totals over 1440 cases:
1410 PASS, 30 DOMAIN_FAIL, six hidden by final-only. Correct passes all 720.
These are predictions in architect-derived.json, not execution evidence.

## Coverage certificates

The universe is lexicographically ordered permutations of CFNQSV. Certify:

- SCA2: every ordered pair occurs as a subsequence, 30 obligations.
- SCA3: every ordered triple occurs as a subsequence, 120 obligations.
- ADJ2: every ordered pair occurs consecutively, 30 obligations.
- PROJ: first delete N and V, then cover adjacency over CFQS, 12 obligations.

Frozen suites use greedy maximum uncovered-obligation gain, with lexicographic
tie breaking. Ordinary suites use all 720 orders and no fault information.
Preregistered sizes are 2, 10, 9 and 5 respectively. Validate the supplied
obligation-to-witness certificates independently by computing positions and
projection from suite rows. Check every obligation, not just aggregate counts.
Do not import derive.py into the verifier. No optimality claim is required.

The additional SCA3_counterexample suite has ten rows, covers all 120 triples,
and excludes every known trigger order by construction. This is an explicitly
selected logical counterexample to coverage implying detection, not an unbiased
effectiveness comparison or held-out discovery. Ordinary SCA3 predicts one
trigger hit; the counterexample predicts none. Report actual detection from
campaign observations for EVERY suite, not from the coverage certificate.

## Framework and implementation

Build TOML and primary XLSX inputs. Mandatory sheets HEAD, IMPL, OPS, TAIL;
OPS has six self-contained step calls and the explicit chain
FW_Permut() -> FW_Combi(size). IMPL has the two policies. No optional sheets or
sieve. Plan both inputs, then run ONE full benchmark: OPS=720, fw_final=1440,
Reader=Executor=1440 unique cases. Preserve separate stage counts and identities.

This full benchmark supplies outcomes for all reduced suites; it does not itself
save execution work. Also build/plan a separate explicit schedule-catalogue XLSX
for the ten-row ordinary SCA3 suite (20 candidates including both policies),
showing how the offline selection becomes executable Framework input. Do not
run that second campaign; report its count as planned only. Framework generates
and executes structures; the offline selector supplies coverage certificates.

Use separate SUT, policy-blind reference, runtime, builder, runner, offline
verifier and replay implementation within this directory. Generic A/B patterns
may be copied with provenance; do not modify archived inputs or depend on other
examples. The verifier independently enumerates all orders, models both policies,
checks every snapshot, compares all three identity sets and validates suite
certificates and measured fault intersections. Retain hashes, commands, sources,
plans, candidates, database exports and all observations.

Replay only four witnesses, recording these as additional attempts: late_restart
CNFSQV (heals), late_restart QCNFSV (persists), late_restart CFNSQV (nontrigger),
and correct CNFSQV (positive). Explain the same ledger state under reordered
operations and why covering all triples need not expose a four-event condition.

Use one fresh as0927_d3c_* database on both ports, generated-default, one worker,
K=1, JVM <=2 GB. Budgets: mandatory rows 1600, final candidates 1600,
disk 200000000 bytes, wall 1800 seconds. Preflight disk and ownership. No broad
tests, live-test sweeps, external services, cleanup, commits or pushes. Preserve
databases. Focused DB-free tests only; zero unexpected infrastructure outcomes.

Deliver a concise EEST-named Markdown report with evidence and limitations. D3
acceptance requires C review; do not start D4. No further permission is needed
within this scope. Necessary Framework fixes remain authorized with a recorded
minimal reproducer and scope.
