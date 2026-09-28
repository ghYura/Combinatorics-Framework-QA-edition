<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D13d contract v1 — session identity and memory lifetime

Apply ../README.md and G1–G7. Detection question: can a deterministic
agent-memory adapter expose a canary to another user/session, or retain it past
a required memory reset? All requests, replies and draft tools are local stubs.
No external model, message, file-writing tool or network action is involved.

## Identity, lifetime and requests

Three ordered requests have user labels U1..U3 and session labels S1..S3.
Each triple is an independent canonical restricted-growth string (RGS):
000, 001, 010, 011 or 012. Labels preserve equality, not a real user's identity.
Session labels are user-local names: two users may legitimately use session 0.
The security/memory principal is the pair (user, session), so neither component
alone suffices. User and session partitions are independent; do not constrain
equal session labels to imply equal users. Equivalence is independent renaming
of each label alphabet, with request positions fixed. Make no extra quotient of
cases merely because their observed outputs happen to agree.

X is a two-bit cut string: X[0] resets all memory before request 2; X[1] resets
all memory before request 3. Epoch starts at 0 and increases at each cut, even
for a faulty adapter that fails to erase storage. A reset has no reply/tool call.
It is a required memory-clear event, not a process crash or durable-storage test.

W is 1 or 2. Request W writes D13D_CANARY_R{W}; both other requests read. Exactly
one write occurs per case. A write replaces the selected memory entry, replies
STORED without echoing the canary, and emits no tool call. A read replies with
its selected value, or null when absent. Non-null reads also append one inert
tool call {name: draft, argument: value}; null reads emit none. Keep both channels.

Every case begins empty. The reference preserves a value only for the same
(user, session) within the same epoch. Reads before the write, from another
principal, or after a cut return null. A same-principal read in the write epoch
must return the canary: erase-all/deny-all is not a passing implementation.

## Four adapters and evidence

| Policy | Storage key | Reset |
|---|---|---|
| scoped | (user, session) | Clear all entries. |
| user_only | (user,) | Clear all entries. |
| session_only | (session,) | Clear all entries. |
| ignores_reset | (user, session) | Retain entries. |

Each stored value retains write_user, write_session, write_epoch and write_index
as diagnostic provenance. Those fields do not authorize a read; buggy adapters
simply look up their declared key. Logical epoch comes from the harness.
Record after each request: request_index, user, session, operation, reset_before,
epoch, storage_key, reply, tool_calls and the memory snapshot. Snapshots are
sorted lists of {key, value, write_user, write_session, write_epoch, write_index}.
Use the exact schema in architect-derived.json. Preserve its full observed and
reference traces in the record, plus input factors, checks, leaks, failing
checkpoint indices, verdict and source/candidate identity.

Use a separate policy-blind oracle. Derive the canary's owner and live epoch from
input requests/cuts, never the SUT key or supplied provenance. For every request,
check response_ok and tools_ok against reference outputs. isolation_ok requires
that every canary in either read channel belongs to the reading principal and
current epoch. A write acknowledgement is exempt because it contains no canary.
Diagnostic memory/key differences alone are not domain failures: a faulty key
may pass when its collision is not exercised. Verify diagnostic fields against
the preregistered policy model offline, without feeding them into authorization.

Classify violating read checkpoints as cross_user, else cross_session, else
expired, in that precedence. A case may have two violating reads; distinguish
failed-case totals, leaking checkpoints and output/tool occurrences. PASS means
all three checks pass at every request. Missing/malformed evidence and escaped
exceptions fail infrastructure gates; wrong observed outputs are DOMAIN_FAIL.

## Native Framework construction

Primary demo.xlsx plus demo.constraints.json and matching spec.toml. Mandatory
HEAD, IMPL (legacy verdict position 2), WRITE_AT, U1..U3, S1..S3, R12, R23, TAIL.
Use explicit Combi(1)→Combi(size) for every slot. WRITE_AT chooses write_at(1);
or write_at(2);. Ui values call user_at(i,label);, Si session_at(i,label);;
R12/R23 call reset_cut(1,bit); / reset_cut(2,bit);. Use whitespace-free atoms.
U1 and S1 select only 0; U2/S2 select 0 or 1; U3/S3 select 0, 1 or 2. Do not
catalogue complete partitions or cases. Decode real rows to recover all axes.

Each label has numeric attribute n. With --sieve, apply require-when bonds:

1. user_rgs: U3.n <= 1 + U2.n.
2. session_rgs: S3.n <= 1 + S2.n.

The other RGS conditions hold by the slot domains. Raw 4 policies × 6 user
triples × 6 session triples × 4 cuts × 2 write positions = **1152**. First bond
leaves **960**; second **800**. Valid support equals 4 × Bell(3)^2 × 4 × 2.
All 25 partition pairs must survive. Record each raw rule match, overlap and
sequential removal separately. Reader=Executor=800 original attempts, repeat=1;
no optional axes. Identity P=policy|U=uuu|S=sss|X=xx|W=position.

Preregistered predictions and all raw bond truth rows are in derive.py and
architect-derived.json; preserve both unchanged. Prediction totals become run
evidence only after reconciliation. Derived outcomes: **718 PASS / 82 DOMAIN_FAIL**.
scoped is 200/0; user_only and session_only are each 172/28; ignores_reset is
174/26. There are 88 leaking read checkpoints (30 cross_user, 30 cross_session,
28 expired), each exposing the canary in two output channels: 176 occurrences.
Report all policy, cut and write-position
strata; this is an enumerated finite population with no empirical user weights.
There is no suite reduction or claim of coverage of live-agent behavior.

## Implementation and review

Implement independent SUT, oracle, self-contained runtime, builder, guarded
runner, offline verifier and replay tool. No runtime imports from another
example or derive.py. The verifier must not import SUT/oracle/runtime/derive or
execute candidate programs. Independently reconstruct all valid identities,
every field, raw bond truth, stage counts, input/source/build hashes, workbook/
TOML/sidecar equivalence and the Core→Reader→Executor mapping. Test its candidate
parser against a locally composed candidate BEFORE the campaign.

Focused tests must cover each defect, useful same-principal retention, reset
before a write versus after it, read-before-write, rejection of noncanonical
labels, wrong cut indexing, a wrong/omitted tool output, tampered provenance,
and an erase-all adapter. Verify the oracle still detects a leaked tool argument
when the user-facing reply is redacted. Do not merely trust final memory state.

Replay these five cases separately as extra attempts:

- P=session_only|U=010|S=000|X=00|W=1 — another user sees the canary at request 2.
- P=user_only|U=000|S=010|X=00|W=1 — another session sees it at request 2.
- P=ignores_reset|U=000|S=000|X=10|W=1 — expired memory survives the first cut.
- P=scoped|U=000|S=000|X=10|W=2 — reset precedes the write; request 3 retains it.
- P=scoped|U=000|S=000|X=01|W=1 — request 2 retains it; second cut clears request 3.

Explain how changing just one identity component or reset cut changes permitted
outputs. Show that a reset can correctly remove memory without an isolation
defect, and that permitted retention rules out an always-empty implementation.

Plan both input forms and check resource estimates before one fresh
as0927_d13d_* campaign on both ports. The architecture plan reports mandatory
EXACT 1152 and post-sieve/final BOUNDED [0,1152]; retain modes/reasons and use the independent
800-case certificate. No override or Framework change just for an EXACT label.
Use accepted v6, --sieve, generated-default, one worker, repeat=1, JVM <=2 GB.
Budgets: mandatory/final 1200, disk 150,000,000 bytes, wall 3000 seconds.
Preflight ownership/free space; record retained sizes. Archive commands, plans,
all source/input files, tables/dictionary, observations, verification, tests and
replays. Preserve databases/artifacts; no cleanup, canonical fixture, broad
tests, external calls, commit or push. Necessary evidenced fixes remain authorized.
Deliver EEST Markdown here. Do not start D13e.
