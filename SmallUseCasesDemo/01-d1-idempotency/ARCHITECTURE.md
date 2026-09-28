<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D1 architecture — durable idempotency at an operation boundary

Version 1. Status: **Proposal with Derived counts; ready for implementation.**
Atlas coverage: D1; M1, M2 and M5's independent-model and signature methods.

## Practical question

A service receives three deliveries of one logical operation. Some deliveries
reuse a transport identity, others have new transport identities. The process
may restart between deliveries. Which deduplication key and storage lifetime
preserve one effect, without suppressing a legitimate new operation?

The demonstration compares five explicit policies. It shows why a test of one
duplicate message is insufficient: it cannot separate several wrong policies
from the correct one. Equal payloads and equal order IDs are not necessarily
equal logical operations.

Use a small executable order-service fixture with a durable effect ledger and
a receipt cache. This is a sequential, deterministic example, not a claim that
an existing production service or the Framework contains these defects.

## Component responsibilities

```mermaid
flowchart LR
  S[Spec and inspectable XLSX] --> C[Framework Core: raw structural product]
  C --> B[Sieve: canonical identities and control slice]
  B --> R[Reader: one program per case]
  R --> E[Executor]
  E --> U[Service policy and checkpoint observations]
  U --> O[Contract verdict and structured record]
  O --> V[Independent offline verifier]
  V --> D[Evidence and minimal witness walkthrough]
```

| Component | Responsibility | Must not do |
|---|---|---|
| `build_spec.py` | Compose auditable fragments, TOML and XLSX using the existing generator interface. | Pre-enumerate the final 120 cases and replace the Framework product or sieve. |
| `sut.py` | Handle requests, store receipts/effects, and apply the five key/lifetime strategies. | Consult expected pass/fail tables or the independent verifier. |
| `oracle.py` | Apply the normative operation contract and inspect observed checkpoints. | Read the implementation selector to decide whether a case should pass. |
| `runtime.py` | Reset a service per candidate, replay cuts/deliveries/control, emit observations and legacy verdict. | Hide setup errors as domain failures or share state between candidates. |
| `verify.py` | Independently enumerate structural identities and derive predicted signatures from set cardinalities and the four control rules. | Import the SUT, runtime or runtime oracle, or trust only their reported verdict. |
| `run_demo.py` | Guard DB names, budgets and provenance; invoke the real Bundle stages. | Mutate Framework source, use another AI's database, or suppress a missing stage. |

Small standard-library modules suffice. Self-contained candidates can embed
audited source fragments in HEAD, so the container execution profile needs no
host import path, credentials or network. Source separation between SUT and
oracle must remain reviewable even if generation inlines them.

## Why the Framework matters here

`L1/L2/L3` slots with a canonicalization bond express **partitions of deliveries**;
`CUT1/CUT2` express **chronological lifetime boundaries**. These are different
structures. Catalogue slots choose implementation and a peer control. The sieve
keeps canonical partitions and makes peer controls explicit rather than silently
mixing populations. Reader and Executor exercise each assembled case.

The role of ordinary Python is the local service fixture, independent oracle
and review tooling. It does not stand in for Core, sieve or Reader. The review
requires the Framework's rendered/executed case sets, not a Python-only loop.

## Walkthrough required from the AI implementer

Explain four contrasts using actual candidate IDs and records:

1. `000/00/none`: all five policies pass; one ordinary retry test cannot select
   a sound design.
2. `000/01/none`: only the volatile transport cache loses its protection when
   the process restarts; the durable ledger itself does not reset.
3. `001/00/none`: even a durable transport cache admits a second effect when
   a retry acquires a new transport identity.
4. Baseline peer controls: a payload key suppresses an independent equal-payload
   order; an order key suppresses a second operation of the same order; the
   operation key preserves both and rejects a conflicting retry.

Record returned identities as well as effect counts. A replayed receipt can
belong to the wrong business operation even when a coarse counter looks small.
Do not describe a legacy `FW_VAR` value as a causal diagnosis.

The final report answers a **detection and finite-catalogue identification**
question. It does not rank implementations by PASS-only Analyzer rows and does
not claim an optimal diagnostic suite. M4 receives its own explicit treatment
in the later diagnostic-sensor example.

## Scope and dependencies

Only this folder, this copy of the Framework, local PostgreSQL and the existing
execution backend are needed. No existing SUT modification is required. The
older 44-case another AI assistant dedup study is a read-only methodological reference, not
execution evidence for this new 120-case contract. Its counts are not targets
for this demonstration.

Excluded: real payments, concurrent check-and-set, crash during a handler,
transaction atomicity, cache TTL/eviction, durable-storage loss, collisions,
multi-region consistency and global exactly-once guarantees. The model does
explicitly include multiple legitimate operations within one order.
