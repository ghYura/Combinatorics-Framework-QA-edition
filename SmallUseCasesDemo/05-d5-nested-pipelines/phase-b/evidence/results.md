<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D5 phase B results: rewrites, reuse, joins and nested scopes

| | B1 (ROOT) | B2 (BUNDLE) |
|---|---|---|
| Run | `d5b1_20260927T231419Z` | `d5b2_20260927T231532Z` |
| Databases (5433 and 5432) | `as0927_d5b1_20260927t231419z` | `as0927_d5b2_20260927t231532z` |
| Plan (XLSX = TOML) | BOUNDED [3, 168] | BOUNDED [3, 3] |
| `fw_final` / Reader / Executor / results_v2 | 24 / 24 / 24 / 24 | 3 / 3 / 3 / 3 |
| Outcomes | **8 PASS / 16 DOMAIN_FAIL** | **1 PASS / 2 DOMAIN_FAIL** |
| Tree evaluations | 24 | 24 (8 per bundle) |
| Verifier | 26/26, including 576 record fields | 27/27, including 288 record fields |
| Replays (byte-identical) | 3/3 | 1/1 |

- **Contract:** phase B `09cdd6c1…abdf`; predictions `c82e399b…0aac` and `derive.py` unchanged.
- **Framework:** accepted v6, with no change. Core used `config/core-b.fw.properties`, which is the
  shipped template with two observation-only keys changed: `core.replace.diagnostics=summary` and
  `core.replace.patternPolicy=warn`.
- **Envelope:** `generated-default`, one worker, K=1, `-Xmx2g`, budgets 500/500/100 MB/1200 s; no
  sieve, no optional axes, no override. The Bundle took 40 s for B1 and 28 s for B2.
- **Verification:** both verifiers passed again from `archive/<run>/inputs`.
- **Denominators:** 27 candidate attempts across the two campaigns, but 48 tree evaluations. The
  campaigns are reported separately: B2's unit is a whole bundle.

## Before execution

`construct.py --precheck` (in `precheck/B1.json` and `precheck/B2.json`) independently rebuilt every
row from the workbook's predicted dictionary codes, using Core's semantics as re-implemented there.
- **Rewrites:** the ordered rewrites give `[OPEN_X, op, CLOSE]`.
- **E2:** 8 subsets → 7 rows.
- **Joins:** JZIP 2×6, JCAT 4×4, ROOT 8×13. The ROOT rows decode to exactly the eight frozen trees.
- **BUNDLE:** 107 codes.
- **Guard:** `run_demo.py` refuses to start unless this check passes.

## What Core did

The dictionary was aligned code by code with the Core input workbook (in B1: TMP 20, OPEN_X 21,
CLOSE 22, E1 23–24, E2 25–27, E3 28–29, PIPE_OPEN 30, REL_S 31, PIPE_CLOSE 32). Core's own log lines
confirm each step.

**E1 rewrites, in order.** The rewrite cell is:

```
FW_Group
FW_ReplaceRE("^\[\[", "[[" + TMP + ", ")
FW_ReplaceRE("^\[\[\d+, ", "[[" + OPEN_X + ", ")
FW_ReplaceRE("\]\]$", ", " + CLOSE + "]]")
```

- **Splices:** Core resolved them to `[[20, `, `[[21, ` and `, 22]]`. The independently reproduced
  steps for op A are `[[23]]` → `[[20, 23]]` → `[[21, 23]]` → `[[21, 23, 22]]`.
- **Core's summary line:** rows seen 2, rewritten 2, dropped 0, and each of the three patterns
  changed 2 rows.
- **Reversed order (offline only, no live campaign):** swapping lines 1 and 2 gives `[[23]]` →
  `[[23]]` (line 2 cannot match yet) → `[[20, 23]]` → `[[20, 23, 22]]`. TMP survives. The two
  rewrites depend on each other; neither is an identity edit.
- **Poison marker:** the TMP code appears in no `fw_final` row. Its fragment, `poison_tmp()`, would
  make a candidate BROKEN.

**Pass counts** (Core's `[DIAG-PASS]` and `[DIAG]` lines):

| Sheet | Program | Rows |
|---|---|---|
| E1 | `Combi(1)` → `Combi(1)` → `Group`+3 rewrites → `Combi(1)` | 2 → 2 → 2 → **2** (3 codes each) |
| E2 | `FW_Subsets` → `FW_Combi(size)` | **8** first pass (with the empty row) → **7** |
| E3 | `Combi(1)` → `Combi(size)` | 2 → 2 |
| JZIP | `FW_(,,E1,,E2,,,,1:1)` | **2** rows of 6: `[OPEN_X, OPEN_Y, z, N, CLOSE, CLOSE]` |
| JCAT | `FW_(,,E1,,E3,,,,M:N)` | **4** rows of 4: `[OPEN_X, c, CLOSE, t]` |
| ROOT | `FW_(PIPE_OPEN,,JZIP,REL_S,FW_(),,PIPE_CLOSE,,M:N)` | **8** rows of 13 |
| BUNDLE (B2) | `FW_(BUNDLE_OPEN,,FW_()G,,SEAL,,BUNDLE_CLOSE,,M:N)` | **1** row of 107 |

- **E2 length filter:** E2's lengths are 1, 1, 1, 2, 2, 2, 3. The 1:1 join paired each 3-code E1
  row only with E2's single 3-code row. The six shorter rows did not take part, so this is not
  row-number zipping.
- **Nesting (Core's `resolveNestedFwBrace` lines):**
  - ROOT: `excluded2 nested FW_() → 'JCAT' (grouped=false)`.
  - B2: `excluded1 nested FW_()G → 'ROOT' (grouped=true)`.
  - Core's brace log confirms the operands: JZIP 1:1 (E1, E2); JCAT M:N (E1, E3); ROOT M:N (JZIP,
    JCAT[N]); BUNDLE M:N (ROOT[G], SEAL).
- **Brace rows decode to the model:** Core's actual ROOT rows equal the model's eight rows exactly.
  B2's BUNDLE row is BUNDLE_OPEN, eight distinct ROOT rows (104 codes), SEAL, BUNDLE_CLOSE. The
  aggregated order was retained: ZIP=A|CAT=A|TAIL=N … ZIP=M|CAT=M|TAIL=S, in Core's ROOT row order.
  Results are compared by tree ID, never by position.

**E1 kept for both consumers; intermediates excluded.**
- **Flags:**
  - E1 is `FW_Exclude` + `FW_Reuse`.
  - The single-consumer operands E2, E3, JZIP and SEAL are `FW_ReuseTableOnly`.
  - The nested operands JCAT (and B2's ROOT) are `FW_Reuse`.
  - Every token and intermediate sheet is `FW_Exclude`.
- **Evidence of retention:** both consumers received both E1 rows: each JZIP row and each of JCAT's
  four rows carries an E1 code. The two joins ran concurrently (JCAT's began at 02:14:28.363, JZIP's
  at .374), and that scheduler-dependent order is why E1 needs `FW_Reuse`: either consumer's cleanup
  could otherwise delete rows the other still needs.
- **fw_final columns:** only HEAD, IMPL, the structural result (ROOT or BUNDLE) and TAIL, with
  24 = 1 × 3 × 8 × 1 rows in B1 and 3 = 1 × 3 × 1 × 1 in B2.
- **Tables:** under the accepted Core configuration (`core.precompute=java`), intermediate tables
  live only in the JVM heap. The retained tables are `fw_final`, its base row and the dictionary.
  Intermediate counts come from Core's logs, and intermediate contents from the model checked
  against the decoded final rows.
- **Token sheets:** these are `FW_Exclude`, so they add no mandatory axis. Core resolves brace tokens
  and `+ SHEET +` splices from all source values (`SheetWorker.buildCopy` uses the merged snapshot),
  so no Framework change was needed. The authoring guide's "non-excluded helper sheets" advice is
  stricter than Core requires.

## Witnesses (replayed, byte-identical)

These are B1 z=A, c=A, t=N from input `{x:2, y:5}`.

| Policy | Candidate | Applied steps | Final | Verdict |
|---|---|---|---|---|
| correct | `1_0_0` | A y, N y, S x, A x, N x | `{x:0, y:-6}` | PASS |
| flatten_scope | `9_0_0` | A x, N x, S x, A x, N x | `{x:5, y:5}` | DOMAIN_FAIL |
| leak_scope | `17_0_0` | A y, N y, **S y**, A x, N x | `{x:-3, y:-9}` | DOMAIN_FAIL |

**B2 correct (`1_0_0`):** one bundle, eight distinct trees, each evaluated on a fresh record, all
PASS. Under flatten_scope and leak_scope all 8 trees fail inside their bundle, so each bundle is one
DOMAIN_FAIL. The S placed between the scopes is what exposes leak_scope: it lands on y because the
field was never restored.

## Limits

- This covers eight illustrative trees from one input record, with three planted policies and equal
  weight per case within each campaign.
- It makes no claim about reduction, minimality or production frequency.
- The planner bounds are honest, not exact: JZIP ≤ 14 and ROOT ≤ 56, because the planner models
  neither the rewrite lengths nor the 1:1 length filter. The live counts match the frozen
  population exactly.
