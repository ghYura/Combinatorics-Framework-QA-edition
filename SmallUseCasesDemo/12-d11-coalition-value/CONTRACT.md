<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D11 contract v1 — coalition value and exact allocation

Frozen before implementation; apply ../README.md and G1–G7. Question:
allocate an explicitly defined cooperative value among six modules, accounting
for complementarity. All 64 coalitions are feasible and evaluated once (K=1).
This is a synthetic transferable-value model, not causal attribution, measured
human contribution or a compensation recommendation. The allocation rule and
value function are assumptions, fixed before observing results.

## Frozen value function

Players, in mask order, are A,B,C,D,E,F. Standalone values are [2,2,1,1,4,0].
For a coalition S, add its standalone values, plus 12 if A and B are present,
plus 5 if A,C,D are all present, plus 5 if B,C,D are all present. All bonuses
can apply simultaneously and exactly once. Thus v(empty)=0 and v(ABCDEF)=32.
Every coalition, including those with equal values, retains its own identity.

Identity: `C=six_bits`. Record mask, members in canonical order, standalone_value,
interaction_bonuses with keys AB/ACD/BCD (including zero entries), value, oracle
agreement, verdict and source/candidate identity. The SUT applies named module
and interaction rules. Use an independent reference implementation based on a
separate term table or multilinear indicator expression; neither may read frozen
case results. A correct evaluation is PASS even for zero value or a useless
player. Arithmetic disagreement is DOMAIN_FAIL; missing/malformed observations
and exceptions are unexpected setup/infrastructure failures. Derived: **64 PASS**.

architect-derived.json preregisters every value and allocation certificate;
derive.py is the AI architect's model, not a SUT/runtime/oracle dependency. Preserve both.

## Framework construction

Primary demo.xlsx and equivalent spec.toml. Mandatory HEAD, COALITION (position
2), TAIL. HEAD initializes the empty set; COALITION has enable(A)..enable(F).
Use explicit `FW_Subsets -> FW_Subsets` for COALITION and `Combi(1)->Combi(size)`
for HEAD/TAIL. The second Subsets pass regenerates empty outputs; an identity
combination pass would lose the empty input. Derived work: 64 first-pass rows,
3^6-1=728 second-pass emissions, then 64 after DISTINCT. Keep observed support
distinct from unmeasured theoretical work. Both actual-input plans must be EXACT
64, with no sieve, optional axes or repeats. Raw/post-Core support, Reader cases,
Executor original attempts and results must each be 64, including exactly one
empty coalition with no enable() calls and all coalitions differing only by F.
Use position 2 only as the legacy verdict carrier, not causal attribution.

Separate SUT, reference, runtime, builder, bounded runner, allocation analysis,
verifier and replay. Generated candidates must be self-contained and independent
of other examples. The Framework evaluates coalitions; allocation is an offline
calculation from OBSERVED values. Reject missing/duplicate/unknown/non-PASS rows
before allocation; never infer missing coalitions or discard equal-value rows.

## Allocation and independent certificates

Use the six-player Shapley rule, with exact fractions:

`phi_i = sum_{S subset N\{i}} |S|! (5-|S|)! / 6! * (v(S union {i}) - v(S))`.

Save all 192 marginal terms with coalition identity, integer difference and
exact weight. The 32 weights for each player sum to one. This weights the
predecessor sets induced by uniformly weighted player ORDERS; it is not a
uniform average of the 32 subsets.

Independently enumerate all 720 player permutations, record their six sequential
marginals and average each player's marginal over the orders. Every order must
telescope to 32. These 4320 marginal observations are offline arithmetic from
the 64 measured values, not Framework candidates, executions or repeated trials.

As a third certificate, derive all coalition dividends by subset inversion:
`d(S)=v(S)-sum_{T proper subset S} d(T)`. Only singleton A=2, B=2, C=1, D=1,
E=4 and interactions AB=12, ACD=5, BCD=5 are nonzero. Dividing each nonempty
dividend equally among its members must reproduce the allocation.

Frozen allocation: A=B=29/3; C=D=13/3; E=4; F=0. Check efficiency (sum=32),
symmetry under A/B and C/D exchange over all relevant contexts, constant
marginal 4 for E, and zero marginal for F over all 32 contexts each. Explain
E as an additive dummy and F as a null player. Use exact numerator/denominator
decimal strings in artifacts, with optional decimal displays.

Report standalone values [2,2,1,1,4,0] (sum 10) and grand-coalition leave-one-out
differences [19,19,11,11,4,0] (sum 64). Neither equals the declared allocation:
standalone scores miss interactions; leave-one-out differences count shared
bonuses multiple times. For a weighting control, the unweighted mean of each
player's 32 marginals is [37/4,37/4,7/2,7/2,4,0], summing to 59/2. It is a
different value rule; do not label it Shapley or claim every alternative rule is
an arithmetic error. The main allocation is fixed by this contract.

## Review, demonstration and execution

The offline verifier must not import SUT/reference/runtime/analysis/derive.py or
execute candidate sources. Independently recompute all case values, complete
identities, marginal weights, permutation sums, dividends and allocation facts
from observed records; compare saved certificates and preregistration. Verify
source inlining/hashes, XLSX/TOML/Core workbook equality, all stage counts and one
attempt per identity. Focused tests must reject missing/duplicate rows and detect
an altered value, in addition to empty, null-player and symmetry controls.

Explain conditional contribution using observed coalitions: A alone adds 2,
adding A to B adds 14, and adding A to C,D adds 7. The same module's marginal
depends on its context. E has the largest standalone score (4), but A/B receive
the largest Shapley shares. Show exact interaction shares and the efficiency
check, without converting this allocation convention into causal blame.

Replay exactly five evaluations as separately recorded extra attempts:

- C=000000 — empty, value 0.
- C=100000 — A, value 2.
- C=110000 — A,B, value 16.
- C=001100 — C,D, value 2.
- C=101100 — A,C,D, value 9.

Archive commands, inputs/source/build hashes, both plans, Core tables/dictionary,
all generated sources and observations, allocation certificates, verifier output
and concise results.md. Run once on fresh as0927_d11_* databases on both ports,
generated-default, one worker, K=1, JVM <=2 GB. Budgets: mandatory rows 100,
final candidates 100, disk 50000000 bytes, wall 300 seconds. Preflight current
disk/ownership and record retained sizes. Preserve databases and prior artifacts.
Focused DB-free tests only; no broad/live-test sweep, full fixture, external calls,
cleanup, commit or push. Necessary evidenced Framework fixes remain authorized;
otherwise preserve v6. Send EEST-named Markdown here. **Do not start D12.**
