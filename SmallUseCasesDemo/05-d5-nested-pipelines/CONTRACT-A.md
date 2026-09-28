<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D5 phase A — compose an ordered pipeline and bind its field

D4 is accepted. Implement this phase only, using Framework v6. D5 remains open
until a subsequent contract covers ordered Group rewrites, FW_Reuse, equal-length
and M:N braces, and nested FW_()/FW_()G. Do not advance to D6 after phase A.
Follow the shared protocol; earlier examples and their evidence remain independent.

## Finite question and oracle

Can a record adapter execute a generated two-operation pipeline on the selected
field, preserving operation order and field scope? Input is always {x:2,y:5}.
Operations on integer v: A=v+1, M=2*v, S=v-3, N=-v. Choose two DISTINCT operations
in order: P(4,2)=12. Bind that pair to x or y: 24 distinct trees.
The tree schema is {field:"x"|"y",ops:[op1,op2]}; order matters in ops.

The correct adapter copies the record, applies op1 then op2 to the selected field,
and preserves the other field. Separate variants: reverse_pair reverses the two
operations; wrong_field executes them on the other field. No other differences.
The independent reference reads the tree and performs the specified fold; it
must not read the policy or call SUT code.

Verdict compares the FINAL two-field record, including exact keys and integer
values. Diagnostic execution traces may differ without causing a failure when
the operations commute. In particular, reverse_pair passes both orders of A/S
and M/N. This is output equivalence for these inputs, not proof of implementation
correctness. Candidate identity remains the exact tree/policy, never final output.
Use uniform case weights and K=1; malformed generated syntax/tree is BROKEN.

Three policies x 24 trees = 72 cases. Derived predictions in
architect-derived-A.json: correct 24/0, reverse_pair 8/16, wrong_field 0/24;
total 32 PASS / 40 DOMAIN_FAIL. Preserve the preregistration unchanged.

## Framework construction

Primary XLSX, with a reproducible builder and plan. TOML is optional here because
the example demonstrates the original workbook program. Mandatory outputs HEAD,
IMPL, OPS, TAIL; keep IMPL at position 2 for the legacy verdict carrier.

OPS contains four self-contained fragments push_op("A"); etc. FIELD contains
bind("x"); and bind("y"); and is FW_Exclude so it contributes through OPS only.
Give FIELD an explicit Combi(1) -> Combi(size) chain. OPS's single effective row:

    FW_Combi(2) -> FW_Permut() -> FW_Group -> FW_Cartes(FIELD)

Combi first forms six unordered pairs; the per-row permutation produces twelve
ordered pairs. The Group boundary makes each preceding ROW one operand; grouped
Cartes combines twelve rows with TWO FIELD values, producing 24 OPS rows.
Do not replace the chain with Permut(2): that parameter is ignored and would
produce 4!=24 full operation orders. Do not prebuild complete pipeline rows.
The grouped operation must append FIELD, not multiply prior rows by themselves.

HEAD initializes a fresh tree builder. push_op appends one opcode; bind requires
exactly two opcodes, closes the pipeline and records its target. TAIL validates
the tree, invokes SUT/reference, emits observations and assigns FW_VAR=0/2.
Fragments execute in decoded row order. No Group rewrites are required in A;
the subsequent phase supplies the rewrite and nested-scope demonstrations.

Independently enumerate the 24 ordered-pair/field tuples and compare them with
decoded Core OPS rows before execution. Require the first two fragments to be
operations and the last to bind a field. Retain encoded rows, dictionary codes
and decoded fragments so the Group boundary and FIELD contribution are visible.
Export available initial/final operand tables and effective chain logs. Distinguish
derived intermediate counts (6,12) from tables/counts actually retained by Core.
No row-count-only or rendered-program-only completeness claim is sufficient.

Expected final OPS=24 and fw_final=72; no optional sheets or sieve. Require 72
unique trees/policies at Reader and Executor. Verify the excluded FIELD axis has
not multiplied fw_final again. Plans may be honestly bounded; live support must
match the frozen identities exactly. Do not bypass a budget gate.

## Evidence, witnesses and execution

Implement independent SUT, reference, runtime, workbook builder, bounded runner,
offline verifier and replay tool. The verifier must not import the SUT/reference/
runtime or execute candidate sources. Decode fragments, independently interpret
each tree and check every observed record against the frozen predictions.
Retain input/source/build hashes, actual commands, plans, stage logs, dictionary/
table exports, candidate sources and observations. Each record includes ID,
tree, input record, expected/observed output, policy, verdict and source identity.
ID: A|policy|OPS=two letters|FIELD=x or y, as frozen.

Replay four cases: correct/AM/x; reverse_pair/AM/x; wrong_field/AM/x;
reverse_pair/AS/x. AM on x should yield 6, while reversing it yields 5; writing
the other field yields {x:2,y:12}. AS commutes and is a passing comparison.
Count these as additional attempts. Explain how the Framework constructed the
ordered pair and then bound a field; make no efficiency claim against a flat
model that has already been given those constructed values.

Run one campaign, fresh as0927_d5a_* on both PostgreSQL ports, generated-default,
one worker, K=1, JVM <=2 GB. Budgets: mandatory rows 500, final candidates 500,
disk 100000000 bytes, wall 1200 seconds. Preflight free disk and ownership.
No external calls, cleanup, broad tests, live-test sweeps, full fixture, commit
or push. Preserve databases; use focused DB-free tests. Zero unexpected
infrastructure outcomes. Necessary Framework fixes remain authorized with a
minimal reproducer and bounded scope.

Deliver concise EEST-named Markdown evidence under this folder, applying G1–G7.
Await the AI architect's next D5 contract. This phase alone does not complete D5.
