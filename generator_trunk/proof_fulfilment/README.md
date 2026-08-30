# proof_fulfilment — the second study: does a genuinely complex SUT change the answer?

The first study ([../proof_billing](../proof_billing)) proved a structural claim about pairwise
using a 426-line single-class module. That SUT was ideal for the claim — its parameter model could
be **exhausted** — but an audit showed it exercised only 5 of ~15 verbs and never touched the
second-order operators, the Analyzer, sharding, gRPC or the Java path. A single in-process class
has no topology, so composition had nothing to compose.

This study uses a SUT built to have somewhere for those to bite.

**The consolidated evidence across all three studies:**
[../../docs/43_COMBINATORIAL_TESTING_EVIDENCE.md](../../docs/43_COMBINATORIAL_TESTING_EVIDENCE.md)

## The system under test

`sut/fulfilment.py` — 475 lines, sha256 `470c7570…4fd26b`, frozen read-only before the first campaign.

Five services exchanging messages over a bus: **gateway** (owns an order saga with compensation),
**inventory**, **payment**, **shipping**, **ledger**. Idempotency keys, retries, timeouts, and
compensation ordering are all real. Eight invariants (J1–J8) over money, stock and shipments form
the external oracle.

It is a **deterministic simulation**: no sockets, no threads, no wall clock. The test decides which
in-flight message is delivered next, which is duplicated, which is lost, and when a service
restarts. That is the design decision that matters — it makes the **delivery schedule a data
structure a test can enumerate**, so interleaving becomes a first-class combinatorial axis instead
of a source of flakiness.

## Campaigns

| dir | space | candidates | failing | result |
|---|---|---|---|---|
| `d1_schedule` | `FW_PermutR(4)` over 4 scheduler moves × compensation order × 2 `FW_Optional` restarts | 2,048 | 2,048 (100%) | **G1** — saturated |
| `d2_brace` | brace `FW_(,,MIX,,FAULTS,,,,M:N)` — 3 computed order-pairs ⋈ 6 computed fault-pairs | 18 | 18 | the brace's first real use |
| `d3_masked` | D1 with the dominant defect masked at config level (`retry=False`) | 2,048 | 572 (27.9%) | **G2** |

## Findings

**G1 — a retry re-executes the business operation.** Every service dedupes on the *transport
message id* (`seen`), never on the operation. A timeout resends the current state's message with a
**new** id, so idempotency never sees it and the work happens again.

```
retry ON,  one tick mid-saga  -> shipped=['o1','o1']  balance=200  audit=['J4','J5']
retry OFF, same schedule      -> shipped=['o1']       balance=100  audit=clean
```

**G2 — the saga orchestrator has no idempotency guard at all.** Every downstream service opens with
`if m.id in self.seen: return`. The gateway does not. A single redelivered *reply* advances the
state machine a second time — two captures, two shipments, for one order.

```python
s = System(timeout=99, retry=False)      # retries masked out entirely
s.submit("o1", "widget", 2, 100)
s.deliver(0)                              # inventory replies `reserved` -> addressed to the GATEWAY
s.duplicate(0)                            # at-least-once: that reply arrives twice
s.drain()
# shipped ['o1','o1']   balance 200 for one $1.00 order   audit ['J4','J5']
```

Duplication is **necessary**: of 648 candidates whose schedule contained no redelivery, **zero**
failed. Adding a service restart roughly quadruples the rate (12.0% → 50.5%), because a restart
empties the in-memory dedupe sets that would otherwise absorb some redeliveries.

| | no crash | crash |
|---|---|---|
| **no duplication** | 0 / 162 (0%) | 0 / 486 (0%) |
| **duplication** | 42 / 350 (12.0%) | 530 / 1050 (50.5%) |

## What this study added about the framework itself

**The brace finally earned its place.** `MIX = FW_Combi(2)` over three order submissions → 3
computed pairs; `FAULTS = FW_Combi(2)` over four fault injections → 6 computed pairs; joined M:N →
**exactly 18**, as hand-computed. Both operands are *results of earlier verbs*, which is precisely
what a flat cartesian cannot express. The first study had no use for this because it had one object
and no topology.

**The estimator flagged its own limitation honestly:** `fw_final = 18 (fwgen est 1 — note: rich
verbs make est approximate)`. Documented behaviour, visible in the run.

**The Analyzer reported success over an empty corpus.** The stage printed `✓ analyzer ran` while
`metrics.kv` was empty and no `provenance.json` was written. This is exactly the trap the project's
own documentation warns about — *do not infer a formal run from overall stage success* — observed
live. Candidate `print()` output is not automatically harvested as the K=V corpus.

**A new authoring trap, found the hard way.** The first D1 run produced 2,048 candidates that all
failed with `SyntaxError`. Cause: `FW_PermutR` emits **several values from one sheet**, joined by
that sheet's concatenator, which defaults to empty — so single-line code fragments glue onto one
line. In the billing study the permutation values happened to be multi-line and already
newline-terminated, so the trap never fired. It is loud here only by luck; a variant producing
*valid but wrong* code would be silent.

**Saturation is the recurring practical problem.** D1 was 100% failing on one defect and told me
nothing about interleaving. Masking that defect took it to 27.9% and made G2 visible — the same
lesson the sieve's bond-as-hypothesis workflow teaches in the first study, here applied at the
config level.

## Running these specs

Every campaign resolves its system under test as
`os.environ.get("PROOF_SUT_ROOT", "<this dir>/sut")`, so run `bundle_run.py` from
`generator_trunk` (as the commands below do) and the relative default resolves. From anywhere else,
point `PROOF_SUT_ROOT` at the `sut/` directory:

```bash
export PROOF_SUT_ROOT=/abs/path/to/generator_trunk/proof_fulfilment/sut
```

## Run it

```bash
cd generator_trunk
python3 bundle_run.py proof_fulfilment/d3_masked --db bd3 --lang py \
  --main-db-user postgres --main-db-password pass \
  --results-db-user postgres --results-db-password pass \
  --execution-policy-profile trusted-local \
  --candidate-origin reviewed-checked-in \
  --acknowledge-trusted-local "reviewed spec fragments vs frozen SUT"

# the brace campaign needs an explicit budget decision: a brace is not statically estimable
python3 bundle_run.py proof_fulfilment/d2_brace --db bd2 --lang py ... \
  --allow-extreme --override-budget "hand-computed 3 x 6 = 18"

python3 proof_billing/analyze_run.py /tmp/fw_work/bd3
```
