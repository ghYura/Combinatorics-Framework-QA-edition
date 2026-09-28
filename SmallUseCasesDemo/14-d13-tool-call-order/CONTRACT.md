<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D13a contract v1 — bounded tool-call policy traces

Frozen before implementation; apply ../README.md and G1–G7. Question:
which local orchestrators violate approval, sensitive-data or idempotence rules
under changes in operation order, partial tool failure and an approval interrupt?
Every tool is an inert Python stub. A send appends to an in-memory outbox only;
no network, external model, real message or persistent business action is allowed.
The canary is the fixture string D13A_LOCAL_CANARY, not an actual secret.
These are deterministic orchestration tests, not an agent-safety certificate.

## Trace universe

The three base operations are A (approve), R (read), S (send block). Generate all
six permutations with each appearing once. Choose N=1 or 2 send requests in the
S block, and a read mode success/failure (F=0/1). An optional revocation occurs
at exactly one base-block boundary X=0,1,2,3, or is absent (X=none): 0 precedes
the first block, k follows block k. A repeated send pair stays together; no
revocation is inserted between its two requests. This bounded space does not
claim every arbitrary repeated-call interleaving.

Initially approved=false, tainted=false, sent_once=false, buffer=PUBLIC. A grants
approval. Revocation removes current approval; a later A grants it again.
R always records read_start, yields a read_chunk containing the canary, then
records read_ok or read_error. The expected error happens AFTER the chunk is
delivered. The stub must deliver that chunk through a callback before raising
its controlled error; the orchestrator catches it and continues. Never turn
this expected tool failure into an uncaught Executor failure.

Every S request has the same message ID notice-1, numbered 1..N. On a permitted
emission its payload is the current buffer, and the stub appends exactly one
{message_id,payload} entry. Record request, decision and all effects. No implicit
later retries, queueing or fallback actions exist.

Four policies differ only as follows:

| Policy | Behavior |
|---|---|
| guarded | Clear approval on revocation; taint immediately on read_chunk; deduplicate. |
| sticky_approval | Ignore revocation when updating the local approval flag; otherwise guarded. |
| success_only_taint | Buffer the chunk immediately, but set tainted only on read_ok; otherwise guarded. |
| no_dedup | Ignore sent_once when choosing to emit; otherwise guarded. |

In every policy the send decision checks, in order: no approval -> block
(reason no_approval); tainted -> block (reason tainted); already sent -> dedup
(reason duplicate), except no_dedup; otherwise emit (reason allowed), then set
sent_once=true. Only emit has a payload; block/dedup payload is null.

Identity: `P=policy|O=three_letters|N=1_or_2|F=0_or_1|X=none_or_cut`.
There are 120 configurations per policy, **480 total**, one attempt each (K=1).
Derived outcomes: guarded 120 PASS; sticky_approval 116/4;
success_only_taint 106/14; no_dedup 112/8. Total **454 PASS / 26 DOMAIN_FAIL**.
No suite reduction or statistical generalization is claimed.

## Observable contract and oracle

Keep SUT/controller, inert tools, independent oracle, runtime and analysis separate.
Neither SUT nor oracle reads preregistered outcomes. Record inputs and the full
trace using architect-derived.json's event names and field meanings: approve,
revoke(cut), read_start, read_chunk(payload), read_ok/read_error, send_request,
send_result. Every event contains a snapshot of the four local state fields and
outbox_size. Every send result records request, action, reason, payload and
message_id. Save send_results, outbox, final_state, reference_sends,
reference_outbox, decisions_ok, outbox_ok, violations, verdict and source identity.

The oracle is policy-blind. Derive authoritative approval from the latest A or
revocation in the EVENT PREFIX, and taint from receipt of read_chunk regardless
of the tool's eventual success. Never trust the SUT's approved/tainted flags as
authorization evidence. Every emitted effect must have current approval, precede
taint, and use a message ID not previously emitted. Record unsafe emissions as
unapproved_emit, tainted_emit or duplicate_emit with the request number.

Also independently derive the guarded responses to the requested trace. A
currently approved, untainted, unsent request must emit once; its immediate
repeat must deduplicate. This functionality condition prevents a deny-all
implementation from passing vacuously. Compare (request, action, payload) and
outbox to the reference. Reasons and internal flags are diagnostic observations,
not additional behavioral obligations; a wrong internal flag with no wrong
response/effect is not a DOMAIN_FAIL in this bounded trace. The verifier still
checks that every snapshot matches the declared policy's execution.

PASS requires decisions_ok, outbox_ok and no unsafe emission. A violation is
DOMAIN_FAIL; malformed setup, escaped tool errors or missing records fail the
campaign's infrastructure gates. Later read errors, taint or revocation must
not retroactively invalidate an earlier authorized PUBLIC emission. Checkpoints
and event order matter; final flags alone are an unsound oracle.

## Framework mapping and stage counts

Primary demo.xlsx with equivalent spec.toml. Mandatory HEAD, IMPL (position 2),
REPETITIONS, READ_MODE, ORDER, TAIL. Add a single optional REVOKE sheet before
ORDER, containing four set_revoke(cut) fragments. Default is no revocation.
Use FW_Optional on REVOKE, Combi(1)->Combi(size) on configuration sheets, and
explicit FW_Permut()->FW_Combi(size) on ORDER's A/R/S fragments. ORDER appends
the generated base operations; TAIL executes that plan after configuration.
The runtime expands S to N requests. This is a controlled adjacent repetition,
not a claim that Core enumerates every four-action word.

Mandatory Core support is 4*2*2*6=96; REVOKE has four rows in fw_opt1; optional
multiplier is 1+4=5. With no sieve, post-Core mandatory support remains 96;
Reader/unique rendered cases/Executor original attempts are 480. Both plans must
report mandatory EXACT 96 and final EXACT 480. Preserve optional absence and all
four cuts. Reconcile the mandatory/optional assembly to complete identities;
do not call 480 the raw mandatory Core count. Positional verdict carrier 2 is
IMPL, not causal attribution. No Framework repeats beyond K=1.

## Independent review and witnesses

Preserve CONTRACT.md, derive.py and architect-derived.json. The offline verifier
must not import SUT/tools/oracle/runtime/derive.py or execute candidate sources.
Independently enumerate identities, reconstruct all policy traces and guarded
responses, check prefix predicates and every frozen field, and reconcile all
stage identities. Verify source inlining, hashes and XLSX/TOML/Core input equality.
Focused tests must check partial-read taint, revocation/reapproval, duplicate
effects, denial of an eligible request, and the non-retroactive prefix rule.

Show a small event timeline for each failing mechanism, including the state
observed by the faulty policy and the oracle's prefix evidence. Explain that
the read tool failing does not undo an already delivered chunk. Report counts
by policy and all configured axes; distinguish requests, outbox effects and
Framework execution attempts. Replay exactly these five cases as extra attempts:

- P=sticky_approval|O=ASR|N=1|F=0|X=1 — sends PUBLIC after revocation.
- P=guarded|O=ASR|N=1|F=0|X=1 — blocks that request.
- P=success_only_taint|O=ARS|N=1|F=1|X=none — emits the canary after a failed read.
- P=no_dedup|O=ASR|N=2|F=0|X=none — two effects for one message ID.
- P=guarded|O=ASR|N=2|F=1|X=3 — emit/dedup before later taint and revocation; PASS.

Archive commands, inputs/source/build hashes, plans, Core tables/dictionary,
all sources/records, verifier output and concise results.md. Run once on fresh
as0927_d13a_* databases on both ports, generated-default, one worker, K=1,
JVM <=2 GB. Budgets: mandatory rows 150, final candidates 500, disk 100000000
bytes, wall 1200 seconds. Preflight disk/ownership and record retained sizes.
Preserve databases and prior artifacts. No broad/live-test sweep, full fixture,
external calls, cleanup, commit or push. Necessary evidenced Framework fixes
remain authorized; otherwise preserve v6. Deliver EEST-named Markdown here.
**Do not start D13b.**
