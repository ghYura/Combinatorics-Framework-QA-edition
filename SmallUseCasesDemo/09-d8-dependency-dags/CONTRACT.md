<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D8b contract v1 — incremental DAG evaluation

Frozen before implementation; apply ../README.md and gates G1–G7.
Detection question: after one input edit, which update policies leave a dependency
cache inconsistent with fresh evaluation? All 64 graphs, four edits and three
policies have equal weight, one attempt per case (K=1). This is a deterministic
local model of a spreadsheet/build dependency engine, not a production system.
No reduced suite or probability claim is involved.

## Graph, values and edit semantics

Nodes A,B,C,D have indices 0,1,2,3. Six bits select edges in the fixed order
AB, AC, AD, BC, BD, CD, where edge u->v means v depends on u. All edges point
forward, so every subset is acyclic. There are 2^6=64 graphs compatible with
this one topological order; do not describe these as all labelled four-node DAGs.
Retain the empty and complete graphs. No graph isomorphism quotient is taken:
node identities, base inputs and the edited node matter.

For every node v, `value[v] = base[v] + sum(value[u] for edge u->v)`.
Initial base inputs are [1,2,4,8]. Build the initial cache in A,B,C,D order.
Each case starts fresh, then increases exactly one base input by 10. The four
edits are A, B, C or D; graph structure stays fixed during the campaign case.
Changing a base input does not itself change the cache. Record that checkpoint.

Policies select dirty nodes and recompute each selected node exactly once,
reading its parents' CURRENT cached values:

| Policy | Dirty nodes | Evaluation order |
|---|---|---|
| closure_forward | edited node plus all its reachable descendants | Increasing node index. |
| direct_only | edited node plus its direct outgoing neighbours | Increasing node index. |
| closure_reverse | edited node plus all reachable descendants | Decreasing node index. |

The first policy is the positive control. direct_only misses transitive
dependents unless they also have direct edges from the edited node.
closure_reverse invalidates enough nodes but reads stale parents due to its
evaluation order. No second pass, lazy repair, cache reset or oracle injection
is allowed. At most four node evaluations follow the edit.

Identity: `policy|G=six_bits|U=node_letter`. Frozen predictions and all expected
traces are in architect-derived.json; derive.py is the AI architect's preregistration,
not an implementation dependency. Derived totals: **768 cases, 604 PASS /
164 DOMAIN_FAIL**. closure_forward 256/0; direct_only 228/28;
closure_reverse 120/136. These are predictions until reconciled with execution.

## Oracle and observations

Separate SUT, policy-blind oracle, runtime, builder, runner, verifier and replay.
The SUT initializes its own cache and executes the policy. The oracle independently
evaluates the graph from base inputs, without reusing incremental state or reading
policy names/predictions to select a verdict. Recursive evaluation with fresh
memoization is suitable; a path-count reference is another route.

For independent verification, count all directed paths from u to v (one length-zero
path when u=v). A fresh value at v equals sum(base[u] * path_count[u][v]). Thus
the edit's expected change is exactly 10*path_count[edited][v]. Enumerating all
increasing intermediate-node subsets gives an independent route from the SUT's
cache recurrence. Multiple paths contribute multiple times; reachability alone
does not determine the numerical change. Arithmetic is exact integer arithmetic.

Record bits, decoded edges, edit, policy, initial and edited base inputs, initial
cache, cache immediately after the base edit, affected nodes, chosen dirty nodes,
evaluation order and final cache. Follow the frozen field names and ordering:
node lists use A,B,C,D order unless explicitly recording evaluation order;
edges use the six-bit order; all value arrays use A,B,C,D positions.
Each update records node, base, parent_reads in node order, previous value, new
value and the complete cache after writing it. Record path_counts, reference,
expected_delta, mismatched_nodes, verdict and source/candidate identity.

PASS requires the observed initial cache to equal its independent fresh reference
and the final cache to equal the edited reference at ALL four nodes. Checking only
the edited node or one sink is insufficient. Wrong cache values are DOMAIN_FAIL.
Malformed graph/input, missing trace, an exception, timeout or infrastructure
failure is unexpected and does not count as a demonstrated invalidation defect.
Intermediate stale values during the update are observations, not by themselves
violations of the final-state contract. Verify every update against its policy.

## Framework construction and review

Primary demo.xlsx with cell-equivalent spec.toml. Mandatory HEAD, IMPL (position
2), six binary EDGE_AB...EDGE_CD slots, EDIT, TAIL. Each binary slot emits an
explicit edge(u,v,0_or_1) call; EDIT selects exactly one node. Use explicit
Combi(1)->Combi(size) chains. The six independent choices generate edge subsets
including the empty graph without an empty fragment disappearing in later passes.
No sieve, bonds or optional axes are necessary; acyclicity holds by construction.

Both plans must report EXACT 768. Raw Core after DISTINCT = post-Core support =
Reader/rendered cases = Executor original attempts = 768, optional multiplier 1.
The Framework crosses these structural choices and executes the resulting programs;
reachability, fresh evaluation and path-count checking belong to the harness.
Do not import another example's runtime. Candidates must be self-contained.

The offline verifier must not import SUT/oracle/runtime/derive.py or execute
candidate sources. Independently enumerate 64 graphs and 768 identities, verify
all six edge axes and empty/full cases survive, derive path counts and policy
traces, and compare every frozen observation field. Reconcile Core dictionary
and rows, Reader source identities, Executor observations and one attempt per
identity. Verify source inlining, archive hashes, XLSX/TOML/Core workbook equality,
both plans and resource settings. Preserve unexpected mismatches; request an
The AI architect revision instead of changing the contract to fit results.

## Partial-order relation and demonstration

As a separate offline proof, enumerate all 24 node permutations for each graph
and retain exactly those satisfying every edge. There are 315 graph/order pairs.
For every absent forward edge u->v already implied by a nonempty path, add it
and compare the COMPLETE sets of valid topological orders. All 31 eligible
graph/edge additions preserve that set. Save a checkable proof, re-derived by
the verifier; these are not extra campaign candidates or attempts.

For graph 100010 (AB,BD), adding AD gives 101010. Both ABCD and CABD are valid
before and after. Without a fixed tie-breaking promise, equality of one chosen
ordering is not required. With a specified lexicographic-minimum rule, equal
order sets imply equal selected minima. This relation concerns order validity:
adding a transitive edge generally CHANGES this fixture's additive values, so
do not claim numerical equivalence from topological redundancy.

Report outcomes by policy and edited node, connect stale cache entries to missing
invalidation or wrong evaluation order, and show the empty graph passes all
policies. Replay exactly these five identities as separately recorded attempts:

- direct_only|G=100100|U=A: AB,BC chain; C remains stale.
- closure_forward|G=100100|U=A: same chain, correct propagation.
- closure_reverse|G=100100|U=A: enough dirty nodes, stale parent reads.
- direct_only|G=110100|U=A: adding AC includes C in the dirty set and this case passes.
- closure_forward|G=111111|U=A: four A-to-D paths; D changes by 40.

Show trace checkpoints and exact reference deltas. The added AC example changes
both graph and formula; do not attribute equal numerical outputs to it.

Archive source/input/build hashes, commands, both plans, Core tables/dictionary,
all generated sources and records, verifier output, proof and concise results.md.
Run one campaign on fresh as0927_d8b_* databases on both ports, generated-default,
one worker, K=1, JVM <=2 GB. Budgets: mandatory rows 1000, final candidates 1000,
disk 100000000 bytes, wall 1800 seconds. Preflight disk/ownership and record retained
sizes. Preserve databases and prior artifacts. Focused DB-free tests only; no
broad/live-test sweep, full fixture, external calls, cleanup, commit or push.
Necessary evidenced Framework fixes remain authorized; otherwise preserve v6.
Deliver EEST-named Markdown here for review. **Do not start D9.**
