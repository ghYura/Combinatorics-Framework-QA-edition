<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D5 phase B — rewrites, reuse, joins and nested scopes

Phase A is accepted. Complete D5's remaining structural demonstrations here,
preserving A's sources, archives and database. Use accepted Framework v6 and the
shared protocol. B1 and B2 below are separate bounded campaigns, in that order.

## Record interpreter and observation

Input is {x:2,y:5}; default current field is x. Reuse A's arithmetic meanings:
A adds 1, M multiplies by 2, S subtracts 3, N negates. An operation updates only
the current field. Scope(field,children) saves the current field, evaluates its
children under field, then restores the previous field. A sequence runs children
left to right. Each tree starts with a fresh record and fresh field context.

Three policies: correct; flatten_scope ignores scope bindings and evaluates all
operations under the incoming field; leak_scope changes field at entry but never
restores it at exit. The policy-blind reference must be independently written.
Compare final records (exact keys and integer values); retain diagnostic traces
but do not use a separate trace verdict. Syntax/stack errors are BROKEN.

The eight target trees have independently chosen z,c in {A,M} and t in {N,S}:

    Sequence(
      Scope(x, [Scope(y, [z, N])]),
      S,
      Scope(x, [c]),
      t
    )

Expected outputs and exact IDs are frozen in architect-derived.json. For
z=A,c=A,t=N: correct={x:0,y:-6}, flatten_scope={x:5,y:5}, leak_scope={x:-3,y:-9}.
The S between scopes makes restoration observable. All eight trees distinguish
both faulty policies from correct; these are illustrative finite fixtures.

## Workbook construction: do not catalogue complete trees

Use primary XLSX inputs and reproducible builders. HEAD, IMPL and TAIL follow
the established self-contained candidate pattern; IMPL is position 2. Primitive
data cells call a stack-based tree builder: op("A");, open_scope("x");,
close_scope();, begin_pipeline();, end_pipeline();, etc. Token sheets contain
one fragment each and must not contribute independent mandatory axes.

E1 supplies A/M leaves and constructs two three-code rows
[OPEN_X,op(z),CLOSE] by this explicit program:

    Combi(1) -> Combi(1) -> Group + ordered ReplaceRE lines -> Combi(1)

The last Combi(1) chooses one prior row as an atom. Apply these code-string
rewrites in the stated order to the grouped string [[opcode]]:

1. Replace prefix ^\[\[ with [[ plus TMP's code plus comma-space.
2. Replace prefix ^\[\[\d+,  with [[ plus OPEN_X's code plus comma-space.
3. Replace suffix \]\]$ with comma-space plus CLOSE's code plus ]].

Use the supported + TOKEN_SHEET + replacement expressions, not hardcoded code
numbers. TMP's fragment is a poison marker that must never reach a valid
candidate. The intermediate strings are [[TMP,op]], [[OPEN_X,op]], then
[[OPEN_X,op,CLOSE]]. Core's bracket removal leaves three codes. Record the actual
FW_ReplaceRE strings, dictionary mapping and independently reproduced stepwise
strings. Reversing lines 1/2 leaves TMP: demonstrate that offline, without a bad
live campaign. This is an actual dependency between rewrites, not an identity edit.

E2's three values, IN ORDER, are OPEN_Y, op("N"), CLOSE. Use
FW_Subsets -> FW_Combi(size): eight first-pass subsets, then seven nonempty
rows because later passes skip the empty row. Their lengths are 1/2/3 with
multiplicities 3/3/1. Only its full three-code row forms a complete scope.
E3 contains op("N") and op("S"), with explicit Combi(1)->Combi(size).

Mark E1 FW_Exclude AND FW_Reuse: both following braces consume its same two-row
operand pool. Selections in the two consumers are independent (z may differ from
c). Preserve other intermediate operands with FW_Reuse where needed for reuse,
nested consumers or evidence. Exclude every intermediate result from fw_final.

Brace order and intended formulas (blank formatting fields stay blank):

    JZIP = FW_(,,E1,,E2,,,,1:1)
    JCAT = FW_(,,E1,,E3,,,,M:N)
    ROOT = FW_(PIPE_OPEN,,JZIP,REL_S,FW_(),,PIPE_CLOSE,,M:N)

JZIP pairs only equal-length rows, then alternates their elements. The two
length-3 E1 rows match only E2's length-3 row: JZIP=2 rows, each six codes:
[OPEN_X,OPEN_Y,op(z),op(N),CLOSE,CLOSE]. This is the nested x/y scope.
The six shorter E2 rows must not participate; 1:1 is not row-number zipping.

JCAT is the row Cartesian join followed by row concatenation: 2x2=4 rows of
four codes [OPEN_X,op(c),CLOSE,op(t)]. FW_Reuse keeps E1 available after JZIP.
ROOT's FW_() resolves the most recent preceding brace, JCAT. Its M:N yields
2x4=8 rows; REL_S inserts S between JZIP and JCAT. PIPE_OPEN/CLOSE delimit a
complete pipeline. ROOT rows have 13 codes each. Verify resolved dependency
edges, row lengths and decoded trees, not only output counts.

## B1 versus grouped nesting B2

B1: ROOT is the only structural mandatory result. Eight trees x three policies
give fw_final=Reader=Executor=24. Predict 8 PASS / 16 DOMAIN_FAIL.

B2 uses the same primitive construction but excludes ROOT and adds, immediately
after ROOT, this final brace:

    BUNDLE = FW_(BUNDLE_OPEN,,FW_()G,,SEAL,,BUNDLE_CLOSE,,M:N)

FW_()G aggregates ALL eight prior ROOT rows into one operand row; it does not
choose one root. SEAL is one no-op validation fragment, seal_bundle();. The
outer markers delimit a bundle. Expect BUNDLE=1 row of 107 codes (104 ROOT codes
plus three bundle markers). BUNDLE is the only structural mandatory result.
One bundle x three policies = 3 candidates: predict 1 PASS / 2 DOMAIN_FAIL.

Retain the actual aggregated ROOT order but compare bundle results by tree ID:
generation order is outside the observation contract. Require exactly the eight
distinct trees, each evaluated on fresh input. Bundle verdict fails if any tree
fails. Report B1/B2 independently: 27 candidate attempts and 48 tree evaluations
across both, not 27 interchangeable single-tree tests. No reduction/minimality
or production-frequency claim is supported. Each declared case has equal weight
within its campaign; B2's observation unit is a whole bundle.

## Evidence and execution

Build and plan both workbooks first. Independently enumerate the eight trees and
validate the intended join/rewriting calculations before execution. Retain all
available Core operand/result tables, dictionary/base rows, effective-program
and nested-resolution logs, source hashes, candidates, observations and commands.
Source flags and decoded outputs must demonstrate E1's retention through both
consumers and exclusion of intermediate axes. Record planner bounds honestly;
live counts must match the frozen population. Do not bypass a budget gate.

The independent verifier must not import SUT/reference/runtime or execute
candidate sources. Decode primitive fragments into trees, interpret them
independently, compare every record and reconcile Core, Reader and Executor IDs.
Certify rewrite ordering, E2 length filtering, both nested forms, and the exact
eight-member bundle. Report source/table provenance as well as final outputs.

Run B1 then B2 once each, fresh as0927_d5b1_* and as0927_d5b2_* databases on both
ports; generated-default, one worker, K=1, JVM <=2 GB. No sieve or optional axes.
Per run: mandatory rows 500, final candidates 500, disk 100000000 bytes, wall
1200 seconds. Preflight disk and ownership. Preserve databases and evidence.
No broad tests, live-test sweeps, full canonical fixture, cleanup, commit or push.

Replay B1 z=A,c=A,t=N under all three policies and B2 correct only (four additional
attempts). Focused DB-free fixture tests suffice. Zero unexpected infrastructure
outcomes. Necessary Framework fixes remain authorized with a minimal reproducer
and bounded scope. Send concise EEST-named Markdown delivery in the D5 folder.
Do not start D6 until the AI architect accepts the complete D5 demonstration.
