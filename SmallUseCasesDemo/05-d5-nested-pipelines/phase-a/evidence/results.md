<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D5 phase A results: an ordered pipeline, then a field binding

- **Run:** `d5a_20260927T195647Z`. **Databases:** `as0927_d5a_20260927t195647z` on 5433 and 5432.
- **Input:** primary `spec/demo.xlsx`, compiled by fwgen from `spec/spec.toml`. No sieve and no
  companion.
- **Framework build:** accepted v6 (D4 inventory `6a182a7e…`), checked unchanged before the run.
- **Contract:** A `6337389c…842e`; frozen predictions `abbf88f4…ec03`, unchanged.
- **Envelope:** `generated-default`, one worker, K=1, `-Xmx2g`. Budgets: 500 mandatory rows, 500 final
  candidates, 100 MB disk, 1200 s wall; no override. The Bundle took 68 s.
- **Evidence kind:** Verified/run.
  - `verify.py` passed 24/24, including 1,728 record fields checked against its own model. It passed
    the same 24/24 again from the archived inputs.
  - Replays were 4/4 byte-identical.

## How the Framework built each tree

The OPS sheet holds four fragments, `push_op("A")` … `push_op("N")`. FIELD (`FW_Exclude`) holds
`bind("x")` and `bind("y")`, with the explicit chain `FW_Combi(1) → FW_Combi(size)`. OPS's effective
row is `FW_Combi(2) → FW_Permut() → FW_Group → FW_Cartes(FIELD)`.

Core's own pass log (`chain-log.txt`, lines `[DIAG-PASS]` for OPS key 3) records these counts:

| Directive | What it does | Core rows after it |
|---|---|---:|
| `FW_Combi(2)` | 6 unordered pairs of distinct operations | `fw_3` = **6** |
| `FW_Permut()` | per-row pass: both orders of each pair | `fw2_3` = **12**, then swapped into `fw_3` |
| `FW_Group` | makes each of the 12 rows one atom (no rewrite lines) | `fw_3` = 12 |
| `FW_Cartes(FIELD)` | grouped: 12 rows × 2 FIELD values | `fw2_3` = **24**, 24 after DISTINCT |

**Derived versus retained counts.**
- 6 and 12 are derived by the verifier's enumeration. Core also logged them as pass counts, but it
  does not keep those tables after the run.
- What Core retains is `fw_final` (72 rows), its base row and the dictionary.
- The 24 OPS rows are recovered from `fw_final`'s OPS column.

**How a grouped row is written.** Core renders each grouped result as `[[op1, op2], [field]]` and
strips every bracket when it parses the result back. So each OPS row is the three codes op1, op2,
field.
- Dictionary codes: 10 = A, 11 = M, 12 = S, 13 = N, 15 = x, 16 = y.
- Example row: `[10, 11, 15]` = `push_op("A")`, `push_op("M")`, `bind("x")`.
- The verifier decoded all 24 distinct rows, and each is op, op, bind. They equal the independent
  enumeration P(4,2) × 2. All 24 encoded rows with codes and values are in
  `verification.json → extra.encoded_ops_rows`.

**The excluded axis did not multiply again.** `fw_final` has exactly the columns HEAD, IMPL, OPS and
TAIL (no FIELD column), and it holds 1 × 3 × 24 × 1 = 72 rows. FIELD reaches the candidates only
through OPS.

## Stages

| Stage | Count |
|---|---:|
| Plans, XLSX and TOML | EXACT 72; OPS EXACT 24 (`FW_Combi(2)(n=4) → FW_Permut() → FW_Group → FW_Cartes(FIELD)`) |
| Core `fw_final` | 72 (HEAD 1 × IMPL 3 × OPS 24 × TAIL 1); no optional tables |
| Reader / Executor / results_v2 | 72 / 72 / 72; one attempt each |
| Outcomes | **32 PASS / 40 DOMAIN_FAIL**: correct 24/0, reverse_pair 8/16, wrong_field 0/24 |

- **Identity sets:** the tree/policy sets decoded from `fw_final`, from the Reader AST (fragment
  order impl, push_op, push_op, bind) and from the Executor records each equal the 72 frozen IDs.
- **Infrastructure:** zero BROKEN, INFRA_FAIL or TIMEOUT outcomes.

## Witnesses (replayed, byte-identical)

Input `{x:2, y:5}`.

| Case | Candidate | Applied steps | Final record | Verdict |
|---|---|---|---|---|
| correct / AM / x | `1_0_0` | A x→3, M x→6 | `{x:6, y:5}` | PASS |
| reverse_pair / AM / x | `25_0_0` | M x→4, A x→5 | `{x:5, y:5}` | DOMAIN_FAIL |
| wrong_field / AM / x | `49_0_0` | A y→6, M y→12 | `{x:2, y:12}` | DOMAIN_FAIL |
| reverse_pair / AS / x | `27_0_0` | S x→−1, A x→0 | `{x:0, y:5}` | PASS |

`reverse_pair` passes exactly the 8 commuting cases (AS, SA, MN, NM on either field). Its execution
trace still differs from the reference trace in all 8. That is output equivalence for this input,
not evidence that the implementation is correct. Candidate identity stays the tree and policy, never
the output.

## Framework observation (no change made)

The TOML plan's dependency graph has no edges. The XLSX plan (the run input) shows the Cartes edge
OPS → FIELD that the chain row declares.
- Both plans have the same nodes and the same EXACT sizing (OPS 24, total 72).
- The TOML graph seems to be built from slots and brace rows only, so it omits a Cartes dependency
  declared in a `seq_extra` chain.
- The runner checks the XLSX edge and that the TOML graph adds no edge beyond it; it does not require
  the two graphs to be equal. No Framework change was needed for this phase.

## Provenance

- **Input archive:** `archive/d5a_20260927T195647Z/inputs`, laid out like the D5 folder; every hash
  equals the manifest.
- **Post-run verifier fix:** after the Bundle finished, the campaign's call to `verify.py` crashed
  serialising the chain-log detail (integer dictionary keys). The archived copy is the one the
  campaign executed; the fixed copy is a post-run tool.

## Limits

This covers only one fixed input record, four integer operations, ordered pairs of distinct
operations, two fields and three planted policies, with uniform weights. It makes no efficiency
claim against a flat model that is handed the same 24 constructed trees, and no claim about Group
rewrites, `FW_Reuse`, braces or nested scopes. Those belong to the next D5 phase.
