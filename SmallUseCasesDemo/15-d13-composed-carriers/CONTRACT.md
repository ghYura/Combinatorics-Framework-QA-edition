<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D13b contract v1 — composed untrusted-content boundaries

Frozen before implementation; apply ../README.md and G1–G7. Question:
does a local structured-content processor preserve a leaf's untrusted origin
after wrapping, ordering and decoding? This is a deterministic marker-language
model, not a live LLM test or evidence of general prompt-injection coverage.
Every effect is an in-memory stub: an outbox list, ready boolean or flag boolean.
No network, external model, real message or filesystem mutation is a tool action.

## Inputs and meaning of origin

Root is a trusted context with three children: trusted task, carrier, trusted
note. Task is plain text MARK_READY; note is plain text END. Their leaf IDs are
task/note. Each carrier contains exactly two UNTRUSTED leaves, marker and filler,
in order MF or FM. Filler is plain FILLER. Marker decoded text is
`D13B_LOCAL_CANARY|TOKEN`, where TOKEN is REF, EMIT_CANARY or SET_FLAG, selected
by marker classes reference, emit_canary or set_flag. These are harmless fixture
symbols, not instructions to this assistant or an external service.

Marker encoding is plain, json or base64. Plain retains the text; json uses a
JSON string literal; base64 encodes its ASCII bytes. Only the marker is encoded.
Decoding changes representation, never source authority. A JSON string or base64
value is well formed in every case; decoding errors are unexpected setup failures.

Two carrier constructors differ in their outer origin:

- retrieved_page: an untrusted container around the two untrusted leaves.
- tool_result: a trusted application-created envelope around the same untrusted
  leaves. That envelope does not authorize commands contained in its data.

Use the exact tree shape and field meanings in architect-derived.json. Context
and carrier nodes have kind/origin/children; text leaves have kind=text, id,
origin, encoding, text. Source origin is immutable. Reference processing permits
actions only from trusted leaves, not because an ancestor or decoder is trusted.

## Processors, outputs and oracle

Traverse task, both carrier leaves in their generated order, then note. Decode
each leaf and preserve its full decoded text. Derive a candidate action only
for exact strings MARK_READY, D13B_LOCAL_CANARY|EMIT_CANARY or
D13B_LOCAL_CANARY|SET_FLAG. REF, FILLER and END have no candidate action.

| Policy | Effective origin |
|---|---|
| preserve_origin | Always the leaf's source origin. |
| wrapper_trust | For carrier children, replace leaf origin with carrier origin; task/note unchanged. |
| decode_trust | Non-plain decoding sets origin to trusted; otherwise retain leaf origin. |

Execute a recognized action iff effective origin is trusted. MARK_READY sets
ready=true; EMIT_CANARY appends the canary string to the local outbox; SET_FLAG
sets flag=true. Initially ready/flag are false and outbox empty. Record actions
as {name,leaf}. Source metadata must remain visible even when a faulty policy
uses a different effective origin.

Record policy, carrier, order, encoding, marker, assembled tree, and each leaf's
path, source/effective origin, encoding, decoded text, candidate_action and
executed flag. Also record decoded_leaves, newline-joined rendered text, actions,
outbox, ready, flag, reference_actions, content_ok, actions_ok, effects_ok,
verdict and source/candidate identity. Follow preregistered ordering exactly.

The policy-blind oracle checks the input tree, exact decoded texts in order and
canary preservation. It requires actions=[{name:MARK_READY,leaf:task}], ready=true,
flag=false and outbox=[]. This checks useful trusted work as well as absence of
forbidden effects; dropping all content is not a passing shortcut. PASS requires
all three *_ok checks. Wrong effects or content are DOMAIN_FAIL; malformed input,
missing evidence or escaped exceptions fail infrastructure gates. Promotion with
no consequent wrong output can PASS in this finite trace: effective-origin
metadata is diagnostic, not a separate behavior requirement.

Use independent SUT processor and oracle implementations. Neither reads frozen
outcomes. No implementation or runtime imports from another example.

## Framework composition, not a flat case catalogue

Population: 3 policies × 2 carriers × 2 leaf orders × 3 encodings × 3 marker
classes = **108**, K=1. Identity
`P=policy|C=carrier|O=MF_or_FM|E=encoding|M=marker_class`.
Derived outcomes: preserve_origin 36 PASS; wrapper_trust 24 PASS/12 DOMAIN_FAIL;
decode_trust 20/16. Total **80 PASS / 28 DOMAIN_FAIL**.

Use actual FW_Group and two brace levels. The architecture sizing probe
planning/shape.toml supplies a concrete starting sequence, never a campaign input:

1. CHUNKS has two leaf-open fragments source_item("marker" and source_item("filler".
   FW_Cartes(LEAF_END) pairs each with a common `),` closing fragment: two rows
   of two codes. FW_Group then FW_Permut() permutes these complete rows, retaining
   each open/close pair. Finish with explicit FW_Combi(size); without it, the lone
   combination verb would be auto-duplicated, permuting the fragments again.
   Bracket-removal rewrites expose their code sequences.
   Target: two ordered rows of four codes, not arbitrary fragment permutations.
2. PREFIX has retrieved_page( and tool_result(. An M:N brace joins PREFIX with
   CHUNKS, injecting `[` and `])`, yielding four balanced carrier expressions.
3. A nested M:N brace wraps the latest brace result with trusted_task() and
   trusted_note(), producing `consume(context([trusted_task(), carrier, trusted_note()]))`.
   ROOT has four context expressions. Preserve nested boundaries and source tags.

HEAD, IMPL (position 2), ENCODING, MARKER, ROOT and TAIL are the only mandatory
final factors. Operand/token sheets are FW_Exclude; use FW_Reuse to retain
operand data required for the audit. Configuration slots use explicit
Combi(1)->Combi(size). Copy established brace syntax as needed, without importing
another example's implementation. Validate all four rendered expressions before
running. Do not replace Group/braces with 108 pre-rendered complete programs.

The planner conservatively reports BOUNDED [27,108] for the probe because of the
custom group rewrite, not EXACT. This sound bound is allowed; retain actual
plan modes/reasons. Independently certify the target 2 CHUNKS, 4 INNER, 4 ROOT,
then 108 complete identities. Build primary demo.xlsx and equivalent spec.toml;
check actual-input plans and their budgets. Expected raw/post-Core support,
Reader/rendered cases and Executor original attempts are each 108, no sieve or
optional axes. Carrier/order must come from decoded structural rows, not a
second unrelated runtime selector. Use position 2 only as the legacy verdict carrier.

## Review and demonstration

Preserve CONTRACT.md, derive.py and architect-derived.json. The offline verifier
must not import SUT/oracle/runtime/derive.py or execute candidates. Independently
reconstruct tree and trace semantics, verify all identities/fields and classify
effects. Decode actual group/brace/Core rows and parse generated AST expressions
to prove both leaf orders and carriers survive with boundaries intact. Verify
source inlining, hashes, workbook/TOML/Core-input equivalence and stage counts.
Record planner uncertainty honestly; no bound override or Framework change is
needed merely to replace BOUNDED with an exact label.

Explain why a trusted envelope differs from a trusted leaf, and why decoding is
not authorization. Show the same preserved canary in safe rendered data versus
a forbidden local outbox effect. Focused tests must detect lost content, missing
MARK_READY, tampered readings and each trust promotion, including benign REF
controls. Report outcome tallies across every axis. Replay five cases separately:

- P=wrapper_trust|C=tool_result|O=MF|E=plain|M=emit_canary — forbidden outbox.
- P=preserve_origin|C=tool_result|O=MF|E=plain|M=emit_canary — data preserved, no outbox.
- P=decode_trust|C=retrieved_page|O=FM|E=json|M=set_flag — forbidden flag.
- P=preserve_origin|C=retrieved_page|O=FM|E=base64|M=emit_canary — decode without promotion.
- P=wrapper_trust|C=tool_result|O=MF|E=json|M=reference — benign marker, PASS.

Archive commands, source/input/build hashes, both plans, Core tables/dictionary,
all sources/records, verifier output and concise results.md. One campaign on fresh
as0927_d13b_* databases on both ports, generated-default, one worker, K=1,
JVM <=2 GB. Budgets: mandatory/final 150, disk 50000000 bytes, wall 400 seconds.
Preflight disk/ownership; record retained sizes. Preserve databases and artifacts.
No broad/live-test sweep, full fixture, external calls, cleanup, commit or push.
Necessary evidenced code fixes remain authorized; otherwise preserve v6. Deliver
EEST-named Markdown here. **Do not start D13c.**
