<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D1 frozen contract v1

Status: **Proposal / Derived**. Freeze this file before implementation and
record its SHA-256 in every handoff and run manifest. Changes require a new
The AI architect message and version. The following are predictions, not measured results.

## 1. Normative service behaviour

A request is `(transport_id, order_id, operation_id, payload)`. A logical
operation is the pair `(order_id, operation_id)`. Operation IDs are local to
their order; two orders can each have `OP1`. The payload is a value object with
`amount_minor` and `currency`. Equality means equality of the complete canonical
value, without probabilistic hashes.

The normative behaviour is:

1. First use of a logical operation appends exactly one durable ledger effect
   and returns `APPLIED`, its identity and its stable receipt/effect ID.
2. Repeating that logical operation with equal payload returns `REPLAY`, the
   original receipt/effect ID and original logical identity; no effect is added.
3. Repeating it with different payload returns `CONFLICT`; no effect is added
   and no prior receipt/payload is overwritten. This expected rejection passes
   the domain contract; it is not BROKEN or INFRA_FAIL.
4. A new logical operation with equal payload still creates its own effect.
5. A process restart preserves the durable ledger and every policy's durable
   cache; it clears only a cache explicitly declared volatile. A fresh case
   starts with an empty ledger and cache of every kind.

Each handler is atomic in this model. Faults occur only between handlers.
Receipt IDs are sequential ledger positions within a case. No random IDs,
wall-clock values, network calls or sleeping are required.

## 2. Five concrete policies under test

All policies use the same handler skeleton with a selectable cache key and
lifetime. On a cache miss, append an effect and cache its payload and receipt.
On a hit, compare the stored full payload: different means `CONFLICT`; equal
means `REPLAY` of the stored receipt **without repairing its stored identity**.
The three core deliveries and the peer use this same handler.

| Policy | Cache key | Cache lifetime |
|---|---|---|
| `volatile_transport` | transport ID | process only |
| `durable_transport` | transport ID | survives restart |
| `durable_order` | order ID | survives restart |
| `durable_payload` | full canonical payload value | survives restart |
| `durable_operation` | `(order_id, operation_id)` | survives restart |

The effect ledger is durable for **all five**. On restart, preserve the backing
durable state and construct a new process-facing service object. The correct
policy must implement the contract, not return precomputed expected results.

## 3. Candidate space and Framework mapping

Every case has three deliveries of `O1/OP1` with payload
`{"amount_minor":100,"currency":"TST"}`. Delivery i gets transport ID `T<label_i>`.
The label partition says which deliveries share an identity; it does not name
machines, users or capacities.

Use these ordered sheets. HEAD and TAIL are one-value code fragments, and all
other sheets are raw self-contained assignments with `FW_Combi(1)`.

| Sheet | Values / cardinality |
|---|---|
| HEAD | runtime definitions; 1 |
| IMPL | the five policies; 5 |
| L1 | initialise labels with 0; 1 |
| L2 | append 0 or 1; 2 |
| L3 | append 0, 1 or 2; 3 |
| CUT1 | restart before delivery 2: 0 or 1; 2 |
| CUT2 | restart before delivery 3: 0 or 1; 2 |
| CONTROL | `none`, `retry_fresh_transport`, `new_order_equal_payload`, `new_operation_same_order`, `conflicting_retry`; 5 |
| TAIL | execute this case, emit record, set verdict; 1 |

No optional sheets are used in D1. HEAD and TAIL have no hidden enumeration.
`FW_Combi(1)` dual promotion is safe here; its later pass preserves each
singleton. Record the actual effective program in the plan.

Apply two bonds in this order for the explainable intermediate counts:

1. `canonical_identity`: forbid `L2=0 AND L3=2`. The remaining canonical
   restricted-growth strings are exactly `000, 001, 010, 011, 012`.
2. `peer_baseline`: forbid `CONTROL != none` unless
   `labels=000 AND CUT1=0 AND CUT2=0`.

Provide TOML **and an inspectable XLSX**, plus the actual constraint sidecar
and a sheet/flag/verb explanation. XLSX is a first-class input. Verify that its
plan and constraint path preserve these semantics; do not silently run an
unsieved workbook. A format/integration obstacle is reported with evidence.

Derived stage counts:

| Stage | Count and reason |
|---|---|
| Raw mandatory Core support after DISTINCT | `5 × 1 × 2 × 3 × 2 × 2 × 5 = 600` |
| After canonical_identity alone | `5 × Bell(3) × 4 × 5 = 500` |
| Target post-sieve scenarios per policy | `5 partitions × 4 cut sets + 4 baseline peers = 24` |
| Post-sieve cases across policies | `5 × 24 = 120` |
| Optional multiplier | 1 |
| Unique rendered semantic cases | 120, injectivity verified by parsed assignments |
| Executor attempts with K=1 | 120 |

The obligation is full execution of the declared finite case set, not a covering
array. The population is uniform over 24 distinct scenarios **per policy** for
the descriptive pass counts; 20 core and 4 peer controls must also be reported
separately. No operational frequency or production reliability is inferred.

## 4. Peer controls

Execute at most one peer request, **after** the three baseline deliveries.
Every peer uses fresh transport ID `T3`, with no restart before it. A `none`
case has no peer. Core state/observations are captured before the peer runs.

| Control | Request relative to the baseline | Normative response | Effect delta |
|---|---|---|---:|
| retry_fresh_transport | O1/OP1, same payload | REPLAY of original receipt | 0 |
| new_order_equal_payload | O2/OP1, same payload | APPLIED for O2/OP1 | 1 |
| new_operation_same_order | O1/OP2, same payload | APPLIED for O1/OP2 | 1 |
| conflicting_retry | O1/OP1, amount_minor=101, currency=TST | CONFLICT, prior receipt unchanged | 0 |

All policies have one pre-peer effect on this baseline. Expected **control**
verdicts under the concrete policies are:

| Policy | Fresh retry | New order | New operation | Conflict |
|---|---|---|---|---|
| volatile_transport | fail | pass | pass | fail |
| durable_transport | fail | pass | pass | fail |
| durable_order | pass | pass | fail | pass |
| durable_payload | pass | fail | fail | fail |
| durable_operation | pass | pass | pass | pass |

Inspect identities, returned receipt IDs and unchanged prior payload, in
addition to status and effect delta. A wrong-identity replay fails even if
its status string is REPLAY.

## 5. Independent predictions and checkpoints

Let `B = |set(labels)|`. Let epochs be `(0, CUT1, CUT1+CUT2)` and
`E = |set(zip(labels, epochs))|`. On the three core deliveries:

- `volatile_transport` creates E effects;
- `durable_transport` creates B effects;
- each of the other policies creates one effect.

The same formula on each prefix predicts the cumulative effect count after
each delivery. A new key on that prefix gives APPLIED; an already seen key
gives REPLAY of its first receipt. All core payloads are equal. This predicts
checkpoint traces without invoking the service implementation.

Across the 20 core scenarios: B's multiplicities are `{1:4, 2:12, 3:4}`;
E's are `{1:1, 2:7, 3:12}`. These counts were independently enumerated during
architectural preparation; no Framework or SUT campaign has yet produced them.

| Policy | Core PASS / 20 | Peer PASS / 4 | Total PASS / 24 | DOMAIN_FAIL / 24 |
|---|---:|---:|---:|---:|
| volatile_transport | 1 | 2 | 3 | 21 |
| durable_transport | 4 | 2 | 6 | 18 |
| durable_order | 20 | 3 | 23 | 1 |
| durable_payload | 20 | 1 | 21 | 3 |
| durable_operation | 20 | 4 | 24 | 0 |
| Total | 65 / 100 | 12 / 20 | 77 / 120 | 43 / 120 |

This table is a falsifiable expectation. A mismatch triggers investigation of
the fixture, generator, contract and observations; do not adjust the oracle to
force these totals. Totals alone cannot establish agreement.

Required observations per case:

- canonical case ID, implementation, labels, cuts and control;
- each delivery's input, restart epoch, returned status, logical identity,
  receipt/effect ID and cumulative durable effects;
- pre-peer full ledger projection/multiplicities and first receipt;
- peer request/response, effect delta and post-peer ledger projection;
- separate booleans for core at-most-once, receipt identity, peer independence,
  conflict handling and aggregate contract validity (use explicit not-applicable
  values where appropriate);
- the Framework verdict and its legacy carrier, plus run/attempt identity.

Use a canonical ID such as
`durable_transport|L=001|C=00|P=none`. Persist machine-readable full records;
numeric metrics alone are insufficient. Store DB/export and candidate-source
links or hashes so an offline verifier can cross-check them.

## 6. Required review and limits

Independently enumerate the five canonical partitions, four cuts and restricted
peers without importing `sut.py`, `runtime.py`, `oracle.py` or reading the spec's
generated case list. Compare complete semantic identity sets at Reader and
Executor; assert zero duplicates and exactly one attempt per case. Parse
candidate assignments safely (for example AST literal extraction), not `exec`.
Check every required observation, not only the 77/43 aggregate.

Identify at least one replayable witness for each incorrect policy and one
positive control, plus the architecture's four contrasts. These are explanatory
witnesses selected from a complete run, not held-out discovery or a certified
minimum suite. Report zero unexpected BROKEN, INFRA_FAIL and TIMEOUT results.

The result supports only this finite sequential fixture, this key contract and
the recorded Framework build. It cannot certify distributed exactly-once
behaviour, transaction atomicity or real crash recovery.
