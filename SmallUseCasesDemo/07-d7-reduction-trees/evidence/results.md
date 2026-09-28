<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D7 results: numeric reduction-tree sensitivity

- **Run:** `d7_20260927T234722Z`. **Databases:** `as0927_d7_20260927t234722z` on 5433 and 5432.
- **Input:** primary `spec/demo.xlsx`, compiled by fwgen from `spec/spec.toml`. No sieve or optional
  axes.
- **Framework build:** accepted v6, no change.
- **Contract:** v1 `8a38aa71…f1c4`; predictions `bcb5139a…ff37` and `derive.py` unchanged.
- **Envelope:** `generated-default`, one worker, K=1, `-Xmx2g`, budgets 200/200/100 MB/600 s, no
  override. The Bundle took 129 s.
- **Python:** host 3.14.0 and container 3.14.5, both binary64 (radix 2, 53-bit mantissa). Each record
  carries its own environment.
- **Evidence kind:** Verified/run. `verify.py` passed 24/24, including 4,032 record fields, and gave
  the same 24/24 from `archive/…/inputs`. Replays were 5/5 byte-identical.

## Mapping

HEAD, IMPL (3 policies), VECTOR (4) and TREE (14) are crossed by the Framework, each sheet through
an explicit `FW_Combi(1) → FW_Combi(size)` chain.
- **TREE:** the builder generates the 14 Catalan bracketings of leaves 0..4, in fixed order, as a
  catalogue. The Framework crosses and executes that catalogue; it does not generate the trees.
- **VECTOR:** each cell carries the vector's five authoritative binary64 hex strings and its three
  frozen exact budgets, as numerator/denominator strings.

| Stage | Count |
|---|---:|
| Plans (XLSX = TOML graph) | EXACT 168 |
| Core `fw_final` (HEAD 1 × IMPL 3 × VECTOR 4 × TREE 14 × TAIL 1) | 168 |
| Reader / Executor / results_v2 | 168 / 168 / 168; one attempt each |
| Outcomes | **156 PASS / 12 DOMAIN_FAIL**; zero BROKEN, INFRA_FAIL or TIMEOUT |

The case sets decoded from `fw_final`, from the Reader AST and from the Executor records each equal
the 168 frozen IDs. The VECTOR cells decode to exactly the frozen hex and budgets.

## Per vector and policy (14 trees each)

| Vector | Policy | PASS / FAIL | Distinct outputs | Max exact abs. error | Budget |
|---|---|---|---|---|---|
| small_integers | tree_binary64 | 14 / 0 | 15 | 0 | 0 |
| | flat_fsum | 14 / 0 | 15 | 0 | 2⁻⁵⁰ |
| | tree_rational | 14 / 0 | 15 | 0 | 0 |
| cancellation | tree_binary64 | **9 / 5** | 2, 3 | 1 | 1/4 |
| | flat_fsum | 14 / 0 | 3 | 0 | 2⁻⁵² |
| | tree_rational | 14 / 0 | 3 | 0 | 0 |
| swamped | tree_binary64 | **7 / 7** | 0, 2, 4 | 3 | 1 |
| | flat_fsum | 14 / 0 | 3 | 0 | 2⁻⁵² |
| | tree_rational | 14 / 0 | 3 | 0 | 0 |
| decimal_inputs | tree_binary64 | 14 / 0 | 1.5 (`0x1.8p+0`) | 2⁻⁵⁵ | 2⁻⁵² |
| | flat_fsum | 14 / 0 | 1.5 | 2⁻⁵⁵ | 2⁻⁵³ |
| | tree_rational | 14 / 0 | 54043195528445953/2⁵⁵ | 0 | 0 |

**How the results were checked.**
- **Reference:** the exact rational sum of the five represented inputs, read from the hex strings.
- **Errors:** exact rationals, compared with the budget inclusively.
- **Binary64 trees:** the verifier re-derived each result by adding the represented children as
  Fractions and rounding that exact sum to binary64 at each node (not native `+`). All four internal
  node values in every trace match.
- **flat_fsum:** checked against the correctly rounded exact reference, not `math.fsum`.
- **Exact trees:** equal the linear reference, and their node traces are the exact partial sums.

## Demonstrations

**Same leaves, different bracketings, different binary64 results.** On cancellation
(2⁵³, 1, −2⁵³, 1, 1) the 14 trees give 2 or 3. On swamped they give 0, 2 or 4.
- **flat_fsum and tree_rational** give one value per vector across all 14 trees: flat_fsum discards
  the grouping, and exact addition is associative.
- **Distinct IDs:** trees that return the same value remain distinct cases.

**Witnesses** (chosen deterministically from the frozen table; node results in post-order):

| Witness | Candidate | Nodes | Result | Error / budget | Verdict |
|---|---|---|---|---|---|
| binary64 cancellation, first failing `((((0,1),2),3),4)` | `15_0_0` | 2⁵³ (2⁵³+1 rounds to even), 0, 1, 2 | 2 | 1 / ¼ | DOMAIN_FAIL |
| binary64 cancellation, first passing `(((0,(1,2)),3),4)` | `16_0_0` | −(2⁵³−1) (exact), 1, 2, 3 | 3 | 0 / ¼ | PASS |
| binary64 swamped, first nonzero within budget `((0,((1,2),3)),4)` | `33_0_0` | 2, 3, 2⁵⁴+4 (2⁵⁴+3 rounds up), 4 | 4 | **1 / 1** | PASS (inclusive) |
| flat_fsum on the first failing tree | `71_0_0` | — | 3 | 0 / 2⁻⁵² | PASS |
| tree_rational on the first failing tree | `127_0_0` | 2⁵³+1, 1, 2, 3 (exact) | 3 | 0 / 0 | PASS |

**A nonzero error that passes.** The swamped witness has error 1 against budget 1. In total, 35 cases
pass with a nonzero exact error: 7 binary64 swamped cases, and 28 decimal_inputs cases (binary64 and
flat_fsum). DOMAIN_FAIL means this fixture's declared limit was exceeded; a rounding difference alone
is not a defect.

**Represented inputs versus ideal decimals** (illustrated from the original observations,
`tree_binary64|V=decimal_inputs|T=((((0,1),2),3),4)`, `43_0_0`).
- **The inputs:** the five hex inputs are the binary64 values nearest 0.1 … 0.5.
- **Their exact sum:** 54043195528445953/36028797018963968, which is **3/2 + 2⁻⁵⁵**, not 3/2.
- **The float results:** every binary64 and flat_fsum result is 1.5, so its exact error against the
  represented reference is 2⁻⁵⁵, within both budgets.
- **Why it matters:** comparing against the ideal decimal sum 3/2 would instead report zero error. The
  oracle deliberately uses the represented inputs.

## Limits

This covers five-leaf trees with the leaf order fixed, four vectors, one binary64 environment (host
3.14.0, container 3.14.5) and illustrative budgets frozen before the run. It is no statement about
other summation algorithms, other inputs or platforms, general properties of `math.fsum`, or
production accuracy.
