<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D7 contract v1 — numeric reduction-tree sensitivity

D6 is accepted. Implement independently here using Framework v6 and the shared
protocol. This is a bounded numerical demonstration, not a claim about arbitrary
summation algorithms or a production accuracy recommendation.

## Population, policies and observation

Enumerate all full binary trees whose five leaves occur in the fixed order
0,1,2,3,4: Catalan(4)=14 bracketings. A tree is a leaf index or a pair of children;
its canonical ID uses parentheses/commas without spaces. Do not permute leaves.
Cross each tree with four vectors and three policies: 168 distinct cases.
Uniform weight per tree within each vector/policy; K=1. Observe the final sum
against an explicit accuracy contract. Different trees remain distinct cases
even when they return identical values; no quotienting or suite reduction.

Vectors, shown here for readability, are AUTHORITATIVELY encoded as binary64
hex strings in architect-derived.json:

| Vector | Five input values | tree_binary64 absolute-error budget |
|---|---|---|
| small_integers | 1,2,3,4,5 | 0 |
| cancellation | 2^53,1,-2^53,1,1 | 1/4 |
| swamped | 2^54,1,1,1,-2^54 | 1 |
| decimal_inputs | 0.1,0.2,0.3,0.4,0.5 | 2^-52 |

Load with float.fromhex; the reference is the EXACT rational sum of those
represented binary64 inputs. In particular, decimal_inputs is not the sum of
ideal decimal fractions. Do not use printed decimal approximations as inputs
or an oracle, and do not compare only against one floating-point fold.

Policies:

- tree_binary64: recursively evaluate both children and use one ordinary
  binary64 addition at each internal node. Retain all four internal results.
- flat_fsum: traverse the tree's leaves left to right, then make ONE math.fsum
  call over all five floats. It deliberately discards grouping after recovering
  the leaves; it is the shape-independent alternative, not per-node fsum.
- tree_rational: convert each represented input to Fraction and recursively add
  exact rational children following the same tree; retain internal results.

The policy-blind oracle computes a linear exact rational sum from the original
five input hex values. For each policy, compare absolute rational error with its
frozen budget, inclusively (error <= budget is PASS). tree_binary64 uses the table
above; tree_rational requires zero error. flat_fsum allows half an ulp of the
correctly rounded reference: respectively 2^-50, 2^-52, 2^-52, 2^-53 for the four
vectors. These exact rational budgets are frozen in architect-derived.json.
They are illustrative acceptance limits, not discovered or fitted from the run.

Finite errors within budget pass even when nonzero. Exceeding the budget or
returning a nonfinite result is DOMAIN_FAIL. Malformed trees, missing/duplicate/
reordered leaves or unsupported environment are setup errors, not numeric defects.
Use binary64 (radix 2, mantissa 53) and record host/container Python versions.

Derived predictions: tree_binary64 44 PASS/12 DOMAIN_FAIL; flat_fsum 56/0;
tree_rational 56/0. Total 156/12. Binary64 failures: cancellation 5/14, swamped
7/14; all other cases pass. Preserve the frozen identities, results and budgets.

## Framework mapping and implementation

Primary XLSX with matching TOML. Mandatory HEAD, IMPL (position 2), VECTOR, TREE,
TAIL, each selected through explicit Combi(1)->Combi(size). TREE is the 14-entry
Catalan catalogue produced by the builder; VECTOR is the four-entry catalogue.
The Framework crosses and executes the catalogues; do not claim it natively
generates Catalan trees. No constraints, sieve or optional axes are needed.
Expected fw_final=Reader=Executor=168, with exact policy/vector/tree identities.

Generated programs are self-contained. Separate SUT evaluation, independent
reference, runtime, builder, bounded runner, verifier and replay tools. The SUT
must use the generated tree: an arbitrary sequential sum is not tree_binary64.
Record each tree, leaf order, input hex, policy, final result, internal-node
results where applicable, exact reference, exact absolute error, budget, verdict
and source/candidate identity. Floating results use float.hex(); every rational
uses numerator/denominator decimal STRINGS, never JSON floating approximations.
Retain decimal rendering only as an optional display convenience.

The offline verifier must not import SUT/reference/runtime/derive.py or execute
candidate sources. Certify all 14 valid unique bracketings and complete identities,
then independently check outputs and every error/budget decision. For the binary64
tree checker, add represented child values as Fractions then round that exact
sum to float at each node; this supplies a separate route from native float '+'.
For flat_fsum, check against the rounded exact reference and the declared budget;
do not reuse math.fsum as the sole oracle. Exact-tree results must equal the linear
rational reference. Verify node traces, inlined source and all stage counts.

## Demonstration, evidence and witnesses

Report per-vector/per-policy counts, distinct numeric outputs and maximum exact
absolute error across the 14 trees. Show the SAME leaves with different bracketings
yielding different binary64 results. Also show a nonzero error that passes its
budget, and the represented-input versus ideal-decimal distinction. Do not call
every rounding difference a defect; DOMAIN_FAIL means this fixture's declared
accuracy limit was exceeded. flat_fsum's results do not establish a general theorem
about all platforms or all floating-point inputs.

Choose witnesses deterministically from the frozen table: lexicographically first
failing tree_binary64 cancellation case; first passing case for that vector;
first swamped tree_binary64 case with nonzero error within budget; and flat_fsum
plus tree_rational on the first failing cancellation tree. Replay only these five,
recording extra attempts separately. Use original observations to illustrate
decimal_inputs. Preserve all predictions and evidence if a mismatch is found;
do not relax a tolerance to obtain the expected count.

Archive source/input/build hashes, commands, both plans, tables/dictionary,
candidate sources, observations, verifier output and concise results.md.
Run once on fresh as0927_d7_* databases on both ports, generated-default, one
worker, K=1, JVM <=2 GB. Budgets: mandatory rows 200, final candidates 200,
disk 100000000 bytes, wall 600 seconds. Preflight disk/ownership. No broad tests,
live-test sweeps, full fixture, external calls, cleanup, commit or push. Preserve
databases; focused DB-free tests only, zero unexpected infrastructure outcomes.

Necessary Framework fixes remain authorized with a minimal reproducer and scope.
Apply G1–G7, deliver concise EEST-named Markdown in this folder and await review.
Do not start D8a before D7 is accepted.
