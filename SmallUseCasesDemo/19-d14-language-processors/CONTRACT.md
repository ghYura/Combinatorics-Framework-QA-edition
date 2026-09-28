<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D14a contract v1 — differential and metamorphic compiler checks

Apply ../README.md and G1–G7. Build a small compiler to a stack machine,
an independent AST interpreter and an independent mechanical verifier. This
tests a bounded compiler back end and a dead-code relation, not a production
compiler, source parser, machine-code ABI or undefined-behavior detector.

## Language and structural population

A program declares x and y, each choosing -1 or 2, in order XY or YX. These
assignments are independent constants. It then returns one expression:

- L: (x A y) B x.
- R: x A (y B x).

A and B independently select +, - or *. Arithmetic is over mathematical
integers, implemented with Python integers; no overflow, division, mutation
inside expressions, side effects or uninitialized reads. Distinct syntax and
binding order remain distinct cases even when they evaluate to the same number.
Use AST dictionaries and ordered binding lists as in architect-derived.json.

Transformation T inserts `z=7` immediately AFTER the first declaration. z is
fresh and never read, so the source-language result must remain unchanged.
XY becomes x,z,y; YX becomes y,z,x. T has no other effect on the AST. Every
candidate evaluates both original and transformed programs from fresh state.

## Compiler variants and machine

Emit PUSH value; STORE name for each binding, then expression code, then RETURN.
A variable emits LOAD name. A binary node normally emits left child, right child,
then ADD/SUB/MUL. Compiler policies:

| Policy | Deliberate change |
|---|---|
| faithful | None. |
| reverse_sub | Emit the right child before the left child for each subtraction node only. |
| alias_dead_temp | Compile STORE z as STORE x; all other emission stays faithful. |

The shared VM is correct and policy-blind. PUSH appends; STORE pops and assigns;
LOAD pushes the bound value. Binary instructions pop right, then left, and
push left op right. RETURN must be final, consume the only stack item and
produce its integer. An invalid instruction, stack underflow, unbound variable
or invalid return is a setup/compiler-execution error, not a numeric verdict.
These declared faulty compilers still produce well-formed bytecode.

Record both program ASTs, independent interpreter results, bytecode, VM results
and the stack/locals/returned snapshot AFTER every instruction, with zero-based
ip and the instruction itself. Exact schema is frozen in architect-derived.json.
The interpreter must not compile or execute bytecode. The VM must not inspect
compiler policy or expected results. A policy-blind oracle compares outputs:

1. original_differential: original VM equals original interpreter.
2. transformed_differential: transformed VM equals transformed interpreter.
3. metamorphic: both VM outputs agree.

Independently verify that the two reference outputs agree; a violation means
the transformation/reference fixture is wrong. PASS requires all three checks.
Numeric discrepancies are DOMAIN_FAIL. Missing evidence or execution failures
fail infrastructure gates. Include input factors, observations, checks, verdict
and source/candidate identity in every record. Diagnostic bytecode differences
alone are not defects if observable results agree.

reverse_sub can give two equal but wrong outputs: the dead-code relation passes
while differential checks fail. alias_dead_temp leaves the original correct but
can corrupt the transformed result. In YX order the later x declaration repairs
the temporary overwrite; in XY order it can survive. An expression may also
cancel the erroneous value. Retain these passing controls; do not classify a
policy name itself as failure. All behavior is deterministic, repeat=1.

## Framework construction and denominators

Use primary demo.xlsx and matching spec.toml, no sidecar/sieve/optional axes.
Mandatory HEAD, IMPL (legacy position 2), XVAL, YVAL, SHAPE, OP_A, OP_B, DECL,
TAIL. Configuration slots use Combi(1)→Combi(size). DECL contains exactly
`declare("x");` and `declare("y");`, processed by native FW_Permut() followed
by explicit FW_Combi(size). The actual decoded DECL row determines binding
order; do not catalogue complete programs or independently choose order later.
Runtime configuration atoms set the two constant values and expression shape/
operators, then collect the generated declarations and construct the two ASTs.

Three policies × two declaration orders × two shapes × four constant pairs ×
nine operator pairs = **432 candidates**, with no filtering. Plan, Core, Reader
and Executor originals must agree on EXACT 432. This is **864 compiled program
variants / VM executions** and 864 reference evaluations, not 864 Framework
attempts. No weighted population, repeats or reduced-suite claim is involved.
Identity: P=policy|O=XY_or_YX|H=L_or_R|X=x|Y=y|A=operator|B=operator.

Keep derive.py and architect-derived.json unchanged. Their totals and complete
field predictions are Derived until reconciled with a run. Report policy ×
binding order × shape tallies and each check's failures separately, including
agreements that are wrong. Show actual DECL rows as two permutations and verify
that the third leaf always refers to x, not an independently selected constant.

Derived totals: **316 PASS / 116 DOMAIN_FAIL**. faithful 144/0; reverse_sub
80/64; alias_dead_temp 92/52. The 64 reverse_sub failures pass the metamorphic
check; the 52 alias_dead_temp failures pass the original differential check.

## Implementation and review

Separate compiler, VM, interpreter, oracle and runtime responsibilities. No
runtime imports from another example or derive.py. Offline verifier must not
import any of these implementation modules or execute candidates; independently
reconstruct all 432 cases, bytecode transitions and outputs. Verify source/input/
build hashes, workbook/TOML/Core-input equivalence, generated-row mapping and
every observation. Preflight its parser on a composed candidate before running.

Literal reference controls at x=-1,y=2: L with A=+,B=* gives -1; R with the same
operators gives -3; L with A=-,B=- gives -2. Test these independently of generated
expectations. Focused tests must also cover reversed SUB operands, both dead-code
placement outcomes, a cancelling expression, statement-order invariance, fresh
state, malformed AST/bytecode and tampered reference or result records. Avoid
host-language eval/exec as the language interpreter; candidate execution by the
Framework is the separate, intended step.

Replay five candidates (both variants each):

- P=reverse_sub|O=XY|H=L|X=-1|Y=2|A=-|B=- — both -4, reference -2; relation alone misses it.
- P=faithful|O=XY|H=L|X=-1|Y=2|A=-|B=- — both -2.
- P=alias_dead_temp|O=XY|H=L|X=-1|Y=2|A=+|B=* — original -1, transformed 63.
- P=alias_dead_temp|O=YX|H=L|X=-1|Y=2|A=+|B=* — later declaration restores x; both -1.
- P=faithful|O=XY|H=R|X=-1|Y=2|A=+|B=* — grouping control, both -3.

One fresh as0927_d14a_* campaign on both ports, accepted v6 checkout,
generated-default, one worker, repeat=1, JVM <=2 GB. Budgets: mandatory/final
500, disk 150,000,000 bytes, wall 1200 seconds. Preflight both plans, ownership
and free space; record retained sizes. Archive commands, all sources/inputs,
plans, Core dictionary/tables, candidates, observations, verification, tests and
replays. Preserve accepted examples and the existing checkout; no pull, cleanup,
canonical fixture, external action, broad tests, commit or push. Necessary new
evidenced fixes remain authorized. Deliver EEST Markdown. Do not start D14b.
