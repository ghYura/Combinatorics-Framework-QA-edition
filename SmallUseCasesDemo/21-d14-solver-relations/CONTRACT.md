<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D14c — Tiny auction solver verification, contract v1

Implement independently in this folder. Preserve this contract, derive.py and
architect-derived.json. They are pre-run predictions, never candidate inputs.
Framework v6 supplies the finite instance/edit/permutation space; the local
solver and exhaustive oracle perform the optimization. No external solver or
service is needed. This is synthetic testing, not a real auction.

## Question and population

Detect missed exact optima and invalid allocations, and measure a deterministic
heuristic's gap. Cross 3 policies × 4 instances × 6 resource relabellings × 2
edits = 144 equally weighted structural cases. Every candidate independently
solves three inputs: canonical base, relabelled base, then edited relabelled
base. Report 432 solver calls separately from 144 Framework attempts.
There is no sampling, reduction, optional axis, sieve or metric-only repeat.
No statistical generalization beyond this finite population is claimed.

The decision problem is weighted set packing over goods {0,1,2}, each of
capacity one. Each bid is independent, has a nonempty item set and positive
integer value, and can be accepted at most once. Feasible allocations contain
pairwise disjoint item sets. Maximize the sum of accepted bid values; the empty
allocation is allowed. No bidder XOR, budget, reserve, payment or externality
constraint exists. Call this total accepted value, not mechanism revenue.

Four input lists, in b0,b1,b2,b3 order; notation items:value:

| Instance | b0 | b1 | b2 | b3 | Exact optimum |
|---|---|---|---|---|---:|
| bundle_trap | {0,1}:7 | {0}:4 | {1}:4 | {2}:2 | 10 |
| tie | {0,1}:8 | {0}:4 | {1}:4 | {2}:2 | 10 |
| disjoint | {0}:5 | {1}:4 | {2}:3 | {0,1,2}:6 | 12 |
| overlap | {0,1}:6 | {1,2}:5 | {0,2}:4 | {2}:2 | 8 |

Each bid is `{id, items, value}`; items are sorted unique integers. A permutation
R=[r0,r1,r2] maps every original item i to ri, preserves bid IDs/order/values,
and sorts each transformed item set. All six permutations, including identity,
are distinct cases even when objectives agree; do not quotient them away.

Edits: `none` leaves the relabelled list unchanged; `dominated` appends b4 with
the same item set as transformed b0 and value b0.value−1. b4 has an independent
bidder. This relation is valid because b0 is nonempty: b0 and b4 cannot coexist
in a feasible allocation, and replacing b4 by b0 preserves feasibility and
strictly improves value. Adding b4 therefore preserves the exact optimum.
Relabelling also preserves the exact optimum by a bijection of allocations.
Never generalize dominance to unspecified feasibility constraints.

## Actual solver implementations

`exact_dp`: dynamic programming over occupied-item bitmasks. Process bids in
input order. Initially mask 0 has value 0 and empty selection. For each bid,
copy skip states and add take states only if its mask is disjoint from the
occupied mask. Store the best (value, sorted selected-ID tuple) per resulting
mask; choose the maximum pair at the end. Ties use the lexicographically
largest ID tuple. Update from the previous iteration, never reuse the same bid.

`greedy_value`: scan bids by descending value, then ascending ID; accept a bid
iff all its actual goods remain free. Return sorted selected IDs and their
sum. This is a heuristic, without an optimality guarantee. Its DOMAIN_FAIL
means it misses this campaign's exact-optimum target, not an implementation
bug in that heuristic.

`min_only_dp`: the same DP as exact_dp, but form each resource mask using only
the smallest numeric item in that bid. Keep the original full bid and value in
the returned observation. This planted feasibility bug can produce impossible
allocations, and relabelling can change its output value. Do not precompute
results or hard-code case IDs in any solver.

DP tie rules are for reproducibility. The oracle accepts every feasible optimum
on ties, not just the DP's preferred allocation. In `tie`, exact_dp returns
[b1,b2,b3] and greedy returns [b0,b3]; both have value 10 and must pass.

## Independent oracle and records

Implement a policy-blind oracle by enumerating all subsets of the actual input
bids and checking pairwise set intersections directly. Do not use DP, import
solver code, read predictions, or branch on policy. Recompute the selected
allocation's feasibility and sum, and obtain the optimum, number of feasible
subsets and sorted list of all optimal allocations. These calculations belong
to the oracle, not the Framework. Each campaign needs 8064 subset checks
(16+16+16 per none case, 16+16+32 per dominated case), excluding tests/verifier.

At each of base/relabeled/edited record the full bid list, sorted selected IDs,
reported_value, actual_value, feasible, value_correct, optimum,
feasible_subsets, optimal_allocations, optimal and gap. `optimal` means feasible
and actual_value==optimum. Gap=optimum−actual_value only for feasible results;
otherwise null. An infeasible value above optimum is not a negative gap.

Record four relations: reference_relabel/reference_edit compare adjacent true
optima; solver_relabel/solver_edit compare adjacent reported objective values.
PASS requires all three results feasible, value_correct and optimal, and all
four relations true. Feasibility/optimality cannot be replaced by equal outputs:
54 predicted failing cases pass both output relations. A legitimate wrong
allocation or integer score is DOMAIN_FAIL. Missing/malformed records, unknown
or duplicate IDs, wrong types, exceptions, timeouts and failed setup are
infrastructure errors; never silently coerce them into a domain verdict.

Identity: `P=<policy>|I=<instance>|R=<three digits>|E=<edit>`.
Emit one deterministic record per candidate, with the case factors, all three
observations, four relations, verdict, source hashes and FW_VAR. FW_VAR=0 on
PASS, 2 on DOMAIN_FAIL (IMPL position 2 is the legacy carrier, not causal blame).
Provide a digest over canonical record JSON. The offline export additionally
maps Core row, candidate/source hash, result row, attempt and repeat index.

Frozen predictions: 72 PASS / 72 DOMAIN_FAIL. exact_dp 48/0, greedy_value 24/24,
min_only_dp 0/48. All greedy allocations are feasible: gaps are 1 on bundle_trap,
6 on disjoint, 0 on tie/overlap. All min_only_dp cases fail at least at the base
checkpoint. Recompute every field independently; totals alone are insufficient.

## Framework mapping and implementation work

Provide primary spec/demo.xlsx and equivalent spec/spec.toml. Mandatory slots:
HEAD, IMPL, INSTANCE, RELABEL, EDIT, TAIL. Catalogue chains are explicitly
FW_Combi(1) → FW_Combi(size); RELABEL is FW_Permut() → FW_Combi(size) over
`label(0);`, `label(1);`, `label(2);`. Capture their rendered order to construct
R. Do not substitute a Python permutation loop or a six-row permutation catalogue
for this Framework operation. HEAD initializes a fresh case; TAIL runs three
solves. IMPL/INSTANCE/EDIT are typed selection atoms. Runtime validates order,
arity and uniqueness. Inline local source with hashes in HEAD as appropriate.

Expected mathematical/Core DISTINCT/post-sieve/final/Reader/Executor counts are
all 144; one attempt, repeat=1. Three internal solves do not triple Core rows.
Preserve raw plan graphs and reconcile effective chains and the generated row
identities. planning/shape.toml is for sizing only, never execute it.

Separate solver.py, oracle.py, runtime.py and transformation helpers; add
build_spec.py, explore.py, run_demo.py, verify.py, replay.py and focused tests.
File names may vary if responsibilities remain explicit. Standalone offline
verify must not import solver/oracle/runtime/derive, execute candidates, or
contact a database. It independently reconstructs the population, transforms,
allocations, both DP-policy predictions via exhaustive feasible subsets (using
the planted mask rule only for its prediction), and the greedy scan. Compare
all fields, plans, Core dictionaries/rows, rendered atoms, Executor records,
inlined hashes and archive inputs. Preflight on a composed candidate.

Tests must cover tied optima accepted with different selections; greedy gaps;
infeasible min-only selections even when objectives are invariant; an actual
symmetry failure; dominated-bid assumptions/feasible replacement; empty feasible
allocation; lost/duplicated labels; wrong objective; malformed results; tampering
and independent imports. Test DP against exhaustive enumeration on all frozen
inputs before launching. Do not freeze expectations from observed campaigns.

Replay these five archived candidates and retain exact record digests:

- P=exact_dp|I=tie|R=210|E=dominated
- P=greedy_value|I=tie|R=210|E=dominated
- P=greedy_value|I=disjoint|R=012|E=dominated
- P=min_only_dp|I=disjoint|R=102|E=none
- P=min_only_dp|I=bundle_trap|R=012|E=dominated

## Execution, delivery and acceptance

One campaign on accepted Framework v6. Source ../bundle_env.sh. New owned main
and results databases as0927_d14c_<stamp>, verified absent on both ports. Use
generated-default with generated origin, no network or external dependencies,
one worker, repeat=1, JAVA_TOOL_OPTIONS=-Xmx2g. Mandatory/final row budgets 200,
disk 150,000,000 bytes, wall 600 seconds, no overrides. Preflight actual XLSX
and TOML plans/equivalence, free disk, sandbox and parser; record run storage.

Keep commands, plans, exact source/build/input hashes, full Core/Reader/Executor
counts and identities, logs, candidates, observations, offline verification,
tests and replays, plus immutable archived inputs. Delivery must distinguish
structural coverage, solver feasibility, exact objective, heuristic gap and
metamorphic checks, with a short practical walkthrough and finite limitations.
G1–G7 in ../README.md must all pass before acceptance.

Preserve accepted folders and all historical artifacts. No canonical run,
external calls, cleanup, broad Framework tests, pull, commit or push. Necessary
evidenced fixes remain authorized; report them before changing frozen semantics.
Communicate only by EEST-named Markdown files here. Do not start D15.
