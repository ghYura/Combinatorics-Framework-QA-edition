<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D3 contract v1 — workflow order and checkpoint observations

Status: ACTIVE for phases A and B. The six-event M3 extension remains required;
The AI architect will freeze phase C after reviewing A/B. Do not advance to D4 or claim D3
complete from A/B alone. Follow ../README.md and AUTHOR_DECISIONS.md.

## Question and finite population

Can a tiny billing service preserve its ledger contract under reordered and
repeated operations, restart, and cache repair? Exhaust all declared structures;
this is deterministic fault detection, with uniform weight per distinct case,
not an estimate of production defect frequency. One attempt per case (K=1).
Case equivalence is exact phase, policy, operation sequence and optional bits;
never merge traces just because they have the same final state.

Three implementations: correct, refund_unchecked, restart_cache. The latter two
are intentional controls. Use fresh state for every candidate and independent
SUT/reference implementations. No imports from previous examples.

## Frozen state machine

Amounts are integer cents. Initial public snapshot:
`epoch=0, captures=[0], refunds=[0], balance=0`.
The lists contain per-epoch counts; all previous entries remain visible.

- C (charge): if captures[epoch] is zero, set it to one and add 100 to balance;
  otherwise no-op. A refunded epoch is not eligible for another charge.
- F (refund): only when captures[epoch]==1 and refunds[epoch]==0, set its refund
  count to one and subtract 100; otherwise no-op.
- N (renew): increment epoch and append zero to both lists. Previous epochs close
  to new operations but remain in the accounting history.
- S (restart): preserve all state. The cache must reload from the durable ledger.
- Q (reconcile): set balance to 100*(sum(captures)-sum(refunds)).

`refund_unchecked` changes F only: always increment refunds[current epoch] and
subtract 100, ignoring both eligibility and duplicate checks.
`restart_cache` changes S only: set balance to zero while preserving the ledger.
All other transitions follow the contract. These are separate fault variants.

After EVERY operation, including S and Q, copy all four fields and compare with
an independent reference. Also check count domains, refunds<=captures for each
epoch, list lengths epoch+1, and ledger/balance equality. Preserve every failure;
never stop at the first one. The main verdict is DOMAIN_FAIL if any checkpoint
fails. Separately compute a final-snapshot-only verdict to expose healed faults.
Unexpected exceptions or malformed records are BROKEN, never domain failures.
The reference must not read policy or call SUT transitions.

## Framework construction and stage counts

Use XLSX as the primary input with matching TOML authoring files and both plans.
Each operation is a self-contained `step("C")` / F / N statement with a newline.
Mandatory sheet order: HEAD, IMPL, OPS, TAIL, with optional sheets S then Q placed
between OPS and TAIL in A. HEAD inlines source; IMPL selects one of three policies;
TAIL finalizes observations. Observe inside step, before executing the next step.
Do not pre-enumerate complete programs or encode the structural cases as a catalogue.

A: OPS uses `FW_Permut() -> FW_Combi(size)` over C,F,N. S and Q each have one
fragment, FW_Optional, explicitly controlled identity passes. They independently
execute after OPS and before the final probe, S before Q when both are present.
Six orders x four optional masks = 24 scenarios per policy, 72 candidates.
Expected Core: OPS=6, IMPL=3, fw_final=18, fw_opt1=2, fw_opt2=1. Reader must consume
all optional sizes including absence, multiplying 18 by four. No sieve is needed.

B: OPS uses `FW_PermutR(3) -> FW_Combi(size)` over C,F,N. No optional sheets.
27 sequences x three policies = 81 fw_final rows/candidates. Explicit second
passes are mandatory: never allow automatic duplication of PermutR.
Additionally plan, without another campaign, `FW_CombiR(3) -> FW_Permut(IDENTICAL)`
using the Framework's full documented identical-duplicates syntax. Independently
show its 10 multisets expand to the same 27 ordered sequences after DISTINCT.
If planning cannot certify this alternative, report its bound/reason and an
independent enumeration; do not present it as measured Core support.

Frozen IDs, literal reference traces, predictions and counts are in
architect-derived.json. They are Derived, awaiting live evidence. Preserve them
unchanged. A predicts 48 PASS / 24 DOMAIN_FAIL, with four failures missed by a
final-only check. B's exact predictions are in that file. Distinguish mandatory
Core rows, optional rows, rendered identities and execution attempts.

## Implementation and review evidence

Implement sut.py, oracle.py, runtime.py, spec builder, bounded runner, independent
offline verifier and replay tool (compact equivalents allowed). Emit ID, policy,
ordered operations, S/Q presence, snapshots at every checkpoint, reference,
invariant results, mismatches, final-only result, Framework verdict and candidate
identity. Use FW_VAR=0/2 for PASS/DOMAIN_FAIL with correct custom-variable mapping;
retain the working IMPL position-2 verdict-carrier convention. Begin TAIL with an
ordinary call before assigning verdict variables.

The verifier must not import SUT/runtime/oracle or execute generated sources.
Enumerate permutations/products independently, derive the reference separately,
compare every trace field and frozen prediction, and reconcile distinct Core,
Reader and Executor IDs. In A, expand Core's mandatory and optional supports for
this comparison; 18 fw_final rows are not 72 executed cases. Check source inlining,
workbook equality, build/input hashes and all stage logs. Never edit predictions
to fit observed output; send a concise discrepancy message first.

Replay these witnesses and one passing control, counting replays separately:
A/refund_unchecked/FCN/S0Q0 (refund before charge),
B/refund_unchecked/CFF/S0Q0 (duplicate refund),
A/restart_cache/CNF/S1Q1 (restart breaks balance; reconcile heals it), and
A/correct/CNF/S1Q1 (positive). Also report the same restart witness with Q0.
Explain why checkpoint coverage and end-state coverage answer different questions.
No actual bank, durable storage, concurrent process, or arbitrary workflow claim
is supported by this local state-machine demonstration.

Run A then B once each, with fresh as0927_d3a_* / as0927_d3b_* databases on both
ports. Preflight free disk and database ownership. Use generated-default, one
worker, K=1, JVM <=2 GB. Each campaign: mandatory-row budget 500, final-candidate
budget 200, disk 100000000 bytes, wall time 600 seconds. Keep live tests opted out;
run only focused DB-free fixture tests. Zero unexpected infrastructure outcomes.
Keep databases and evidence. No full fixture, broad suite, commit, push or cleanup.

Deliver commands, source/input/build snapshots and hashes, plans, complete result
exports, stage reconciliation, all observations, tests and witness replays under
this folder. Apply G1–G7. Necessary Framework fixes remain authorized; first record
a minimal reproducer and scope. Send an EEST-named Markdown delivery and await
The AI architect's phase-C contract. Communicate concisely through files only.
