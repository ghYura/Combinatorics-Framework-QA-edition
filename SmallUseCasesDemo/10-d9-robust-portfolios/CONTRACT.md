<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D9 contract v1 — robust contingency portfolios

Frozen before implementation. Apply ../README.md and G1–G7. Question:
RANK a portfolio selected before its operating world is known. Each generated
row is an evaluation, not a complete decision. Population: all 64 subsets of six
modules, each evaluated in all 16 worlds, K=1. No sampling or feasibility pruning;
all portfolios are admissible. Costs are illustrative units, not calibrated
prices or a real operational recommendation. No network service is required.

## Frozen payoff model

Module order and fixed costs:

| Bit | Module | Cost | Loss reduction |
|---:|---|---:|---|
| 0 | cache | 3 | [0,3,8,6] indexed by demand. |
| 1 | quota | 2 | [0,2,6,7] indexed by demand. |
| 2 | network_backup | 5 | 11 when disruption=1, otherwise 0. |
| 3 | disk_replica | 6 | 14 when disruption=2, otherwise 0. |
| 4 | staff_reserve | 4 | 6 when disruption=3, otherwise 0. |
| 5 | cross_region | 8 | 8 when disruption is 1 or 2, otherwise 0. |

Worlds are demand d in 0..3 crossed with disruption x in 0..3, in lexicographic
(d,x) order. Gross loss = [4,11,22,15][d] + [0,14,19,9][x]. Sum reductions of
selected modules, subtract from gross loss, then clamp ONCE to zero. Total cost
= sum(selected fixed costs) + residual loss. A fixed cost is charged once per
world evaluation; a weighted average with weights summing to one charges that
same portfolio cost once. All raw arithmetic is integer arithmetic.

The table is the atlas's historical proposal, attributed and hashed in
architect-derived.json. It supplies assumptions only; no historical execution
is reused. derive.py and architect-derived.json are the AI architect preregistration, not
SUT/oracle/runtime dependencies. All **1,024 evaluations predict PASS**: positive
residual loss or high cost is not a software defect. Numerical disagreement with
the independent model is DOMAIN_FAIL; malformed inputs, missing evidence or an
exception is unexpected setup/infrastructure failure.

Identity: `P=six_bits|D=d|X=x`; empty design is 000000 and full is 111111. Record
design, selected modules in canonical order, demand, disruption, fixed_cost,
gross_loss, reductions (six entries; zero for unselected), raw_loss,
residual_loss, total_cost, verdict and source/candidate identity. SUT computes
the named rules; the independent oracle uses a separately declared per-module,
per-world benefit table or another independent formulation. Neither reads frozen
case results. Preserve raw negative loss to demonstrate the final clamp.

## Framework mapping, including the empty subset

Mandatory HEAD, DESIGN (position 2), DEMAND, DISRUPTION, TAIL. HEAD initializes
an empty selection; DESIGN contains six enable(module) fragments. Use explicit
`FW_Subsets -> FW_Subsets` for DESIGN and `Combi(1)->Combi(size)` for other
slots. Do not substitute a combination identity pass after Subsets: it would
lose the empty input row. The second Subsets pass regenerates empty outputs
from nonempty inputs, preserving all 64 subsets after DISTINCT. Derived work:
64 first-pass outputs; sum(nonempty S, 2^|S|)=3^6-1=728 second-pass emissions
under the documented empty-input skip, then 64 distinct results. Report derived
work separately from observed table counts.

[The architecture sizing probe](planning/plan/plan.json) reports EXACT 1024;
planning/shape.toml is a non-executable sizing input, not the campaign workbook.
The AI implementer must build primary demo.xlsx with equivalent spec.toml and verify both
plans using actual inlined sources and campaign budgets. Expected DESIGN fw/fw2
support 64 each, including one empty subset. Raw mandatory Core after DISTINCT
= post-Core = Reader/rendered = Executor original attempts = 1024; no sieve or
optional axes (multiplier 1). Reconcile all 64 designs and all 16 worlds per
design, including empty-design candidates with no enable() calls. Missing the
empty design is a blocker, not permission to reduce the denominator to 1008.

Separate SUT, reference, runtime, builder, bounded runner, offline ranking,
verifier and replay. Candidates are self-contained, independent of other examples.
Use DESIGN position 2 only as the legacy verdict carrier, not causal attribution.
The Framework generates evaluations; design-level aggregation is an offline
analysis over OBSERVED costs, not the single-row Analyzer.

## Design-level objectives and world weights

Require exactly one observed record for every design/world pair before ranking.
Reject missing worlds, duplicates, unknown identities or non-PASS observations;
never silently fill, average duplicates or renormalize an incomplete denominator.

1. Minimax: sort by (maximum total cost over all 16 worlds, uniform mean cost,
   design bit string). Retain ties on the primary objective separately.
2. Expected cost: for each profile below, sort by (weighted expected total cost,
   maximum total cost, bit string). World weight is the product of the normalized
   demand and disruption weights. Every world has positive weight.

| Profile | Demand weights | Disruption weights |
|---|---|---|
| uniform | 1,1,1,1 | 1,1,1,1 |
| calm | 6,2,1,1 | 7,1,1,1 |
| stress | 1,1,6,2 | 1,2,6,1 |

Use exact rational arithmetic; serialize fractions as numerator/denominator
decimal strings. Decimal displays may supplement them. Save all 64 summaries,
worst-world identities, objective values and complete rankings. For sensitivity,
evaluate alpha=0,1/10,...,1 using the mixture of JOINT distributions
(1-alpha)*calm + alpha*stress, with the same expected-cost tie-breakers. Do not
multiply mixed marginals or claim grid transitions are exact continuous breakpoints.

Predictions: minimax chooses 110000 (cache+quota), worst 32, uniform mean 41/2.
110001 also has worst 32 but mean 49/2 and loses the tie-break. Expected-cost
winners: uniform 110000 (41/2), calm 000000 (25/2), stress 110100 (239/10;
worst 33). The 11 sensitivity winners are 000000,010000,010000, then four
110000 entries, then four 110100 entries. Preserve all preregistered scores.

## Verification, demonstration and execution

The offline verifier must not import SUT/oracle/runtime/ranking/derive.py or
execute candidate sources. Independently enumerate every identity, recompute
payoffs and exact aggregate rankings, verify source inlining and archive hashes,
workbook/TOML/Core-input equivalence, all stage populations and original attempts.
Check numerical totals, ranking completeness and sensitivity from observed rows,
then compare with frozen predictions. Focused tests must show the ranking input
guard rejects a missing world and a duplicate, and cost verification detects an
altered total. These corruption controls are offline, not campaign cases.

Walk through why ranking the cheapest individual row is insufficient: 000000 in
world (0,0) costs 4, but its worst cost is 41; minimax's winner has worst cost 32.
The empty portfolio is nevertheless the legitimate calm-profile winner. Explain
that changing the objective or weights can change the decision without any SUT
failure. Illustrate the clamp and fixed-cost tradeoff. No universal best design
is implied by these toy assumptions.

Replay exactly these five evaluations as separate extra attempts:

- P=000000|D=0|X=0 — cheapest isolated row, total 4.
- P=000000|D=2|X=2 — same design's worst world, total 41.
- P=110000|D=2|X=2 — minimax winner's worst world, total 32.
- P=110100|D=2|X=2 — stress-profile winner, total 24 in this world.
- P=111111|D=3|X=1 — raw loss -3, residual 0, fixed/total cost 28.

Archive source/input/build hashes, commands, both plans, Core tables/dictionary,
all sources and records, observed-cost rankings, verifier output and results.md.
Run once on fresh as0927_d9_* databases on both ports, generated-default, one
worker, K=1, JVM <=2 GB. Budgets: mandatory rows 1100, final candidates 1100,
disk 100000000 bytes, wall 2400 seconds. Preflight disk/ownership and record retained
sizes. Preserve databases and prior artifacts; no broad/live-test sweep, full
fixture, external calls, cleanup, commit or push. Necessary evidenced Framework
fixes remain authorized; otherwise preserve v6. Send EEST-named Markdown here
for review. **Do not start D10.**
