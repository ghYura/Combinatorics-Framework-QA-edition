<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D14a results: differential and metamorphic compiler checks

- **Run:** `d14a_20260928T173808Z`. **Databases:** `as0927_d14a_20260928t173808z` on 5433 and 5432 (owner
  role `postgres`; absent on both ports before the run).
  - Retained sizes: main 8,419,007 bytes, results 9,361,087 bytes; the run directory is 10,912,160 bytes;
    `evidence/` 7,403,403 bytes and `archive/` 4,626,404 bytes.
- **Input:** primary `spec/demo.xlsx`; cell-, chain- and message-equivalent to `spec/spec.toml`. No rules,
  no companion, no sieve, no optional axis.
- **Framework build:** accepted v6, no change (checkout `be48836` + the 27 inventoried v6 files; Core jar
  `e705674e…`, Reader jar `71393e9f…`, py_executor `a6820f11…`, unchanged since the run).
- **Contract:** v1 `6957b9a3…7eca8b`; predictions `aa08c2e3…04e757` and `derive.py` `1751ea41…0bff27` unchanged.
- **Envelope:** `generated-default`, one worker, repeat 1, `-Xmx2g`, budgets 500/500/150,000,000 B/1200 s, no
  override. The Bundle took 281.6 s (Core 8.9 s, Reader 13.4 s, Executor 257.4 s).
- **Evidence kind:** Verified/run. `verify.py` passed 31/31 at campaign time (73,008 record fields, 9,504 VM
  transitions) with no post-run change. It gave the same 31/31 from `archive/…/inputs`, and the five named
  replays were byte-identical (both variants each).
  - **Parser preflight:** before the campaign, a fixture test composed a candidate as the Reader renders it
    (including the two-value DECL cell), parsed it with the verifier and ran it.
- **Model:** a local compiler, stack machine and AST interpreter over mathematical integers. No production
  compiler, parser, machine-code ABI, undefined behaviour or external action is involved.

## Construction and stage counts

- **Factors:** mandatory HEAD, IMPL (3 compiler policies, position 2), XVAL, YVAL, SHAPE, OP_A, OP_B, DECL and
  TAIL. Configuration slots use `FW_Combi(1) → FW_Combi(size)`. DECL holds exactly `declare("x");` and
  `declare("y");` under the native `FW_Permut() → FW_Combi(size)`.
- **DECL rows:** Core wrote the two permutations, 216 rows each: `declare("x");declare("y");` and
  `declare("y");declare("x");`. The Reader renders a row's values back to back followed by the DECL ending, so
  the decoded row alone fixes the binding order; no program is catalogued.
- **Decoding:** each rendered candidate equals its Core row joined with the recorded endings, byte for byte;
  each name prefix equals its `combi_id`. Every AST's leaves are x, y, x: the third leaf is the variable x, not
  a separately chosen constant.

| Stage | Count |
|---|---:|
| Plans (XLSX = TOML, one graph `7925230d…`) | mandatory, post-sieve, final **EXACT 432**; optional ×1 |
| Core `fw_final` (1 × 3 × 2 × 2 × 2 × 3 × 3 × 2 × 1) | 432 |
| Reader / Executor / results_v2 | 432 / 432 / 432; one attempt each, repeat_idx 0 |
| Compiled program variants / VM executions / reference evaluations | 864 / 864 / 864 |
| Outcomes | **316 PASS / 116 DOMAIN_FAIL**; zero BROKEN, INFRA_FAIL or TIMEOUT |

- **Plan graph versus the AI architect's shape plan (`ff3d130b…`):** edges and per-slot counts are equal. The one
  difference is the DECL slot's displayed verb: `shape.toml` shows the placeholder `FW_Combi(1)`, while these
  inputs name the effective `FW_Permut()` in the slot as well, so TOML and XLSX share one graph. Both chains
  are `FW_Permut() → FW_Combi(size)`.
- **Budget notes:** non-blocking warnings for 432 rows and candidates (above 250; hard limit 500) and the
  864 s wall estimate (above 600; actual 281.6 s).

## Outcomes and check failures

| Policy | PASS / FAIL | original_differential fails | transformed_differential fails | metamorphic fails |
|---|---|---:|---:|---:|
| faithful | 144 / 0 | 0 | 0 | 0 |
| reverse_sub | 80 / 64 | 64 | 64 | **0** |
| alias_dead_temp | 92 / 52 | **0** | 52 | 52 |

| Policy | XY L | XY R | YX L | YX R |
|---|---|---|---|---|
| faithful | 36/0 | 36/0 | 36/0 | 36/0 |
| reverse_sub | 20/16 | 20/16 | 20/16 | 20/16 |
| alias_dead_temp | 10/26 | 10/26 | 36/0 | 36/0 |

- **Wrong agreements:** all 64 reverse_sub failures pass the metamorphic relation; both variants return the
  same wrong value. The relation alone would miss them; only the differential checks catch them.
- **Original correct, transformed corrupted:** all 52 alias_dead_temp failures pass the original differential
  check and are XY; the transformed VM ends with x = 7.
- **Passing controls kept:** all 72 YX alias_dead_temp candidates pass (the later x declaration restores the
  overwrite). All 20 XY passes are cancellations: for that y the expression's value does not depend on x
  (for example `(x − y) − x = −y`). reverse_sub passes the 64 candidates without subtraction and 16 whose
  swapped operands happen to give the same value.
- **Bytecode alone is diagnostic:** 108 passing candidates (16 reverse_sub, 92 alias_dead_temp) emit bytecode
  that differs from the faithful compiler's; their observable results agree, so they pass.

## Mechanisms (replayed)

| Candidate | Case | Transformed bytecode | Reference / VM (original, transformed) | Verdict |
|---|---|---|---|---|
| `189_0_0` | reverse_sub, XY, L, x=−1, y=2, −, − | … LOAD x, LOAD y, LOAD x, SUB, SUB | −2 / −4, −4 | DOMAIN_FAIL (differentials only) |
| `45_0_0` | faithful, same | … LOAD x, LOAD y, SUB, LOAD x, SUB | −2 / −2, −2 | PASS |
| `329_0_0` | alias_dead_temp, XY, L, +, * | PUSH −1, STORE x, PUSH 7, **STORE x**, PUSH 2, STORE y, … | −1 / −1, **63** | DOMAIN_FAIL |
| `330_0_0` | alias_dead_temp, YX, L, +, * | PUSH 2, STORE y, PUSH 7, **STORE x**, PUSH −1, STORE x, … | −1 / −1, −1 | PASS (x restored) |
| `59_0_0` | faithful, XY, R, +, * | … LOAD x, LOAD y, LOAD x, MUL, ADD | −3 / −3, −3 | PASS (grouping control) |

- **Reversed subtraction:** each SUB node emits its right child first, so `(x − y) − x` becomes `x − (y − x)`,
  giving −4 in both variants.
- **Dead-code placement:** in XY, `STORE z` compiled as `STORE x` overwrites x after its declaration, so
  `(7 + 2) · 7 = 63`. In YX the later `STORE x` restores −1.
- **Literal reference controls** (hand-computed, x = −1, y = 2): L(+,*) = −1, R(+,*) = −3, L(−,−) = −2. They
  are checked in tests and by the verifier independently of any generated expectation.

## Provenance

- **Archive:** all 20 recorded inputs byte for byte (`verify.py` unchanged since the campaign).
- **Checks verified:** frozen hashes; the build record; workbook = run-input copy = Core input workbook;
  XLSX/TOML slots, endings, FW_Seq chains and custom message; the dictionary and DECL rows; source inlining;
  candidate, observation and component hashes; the command envelope and JVM options. The three relations
  are also recomputed from recorded values alone (policy-blind), and the two reference values agree in all
  432 records.

## Limits

Two variables with two constants each, two expression shapes, three operators, one dead binding and two
planted back-end faults in a bounded compiler. There is no claim about production compilers, source parsing,
optimisation passes, machine code or undefined-behaviour detection.
