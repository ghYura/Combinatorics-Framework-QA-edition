<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D13b results: composed untrusted-content boundaries

- **Run:** `d13b_20260928T094930Z`. **Databases:** `as0927_d13b_20260928t094930z` on 5433 and 5432.
  - Retained sizes: main 8,353,471 bytes, results 8,451,775 bytes; the run directory is 2,378,832 bytes.
- **Input:** primary `spec/demo.xlsx` (cell-equivalent to `spec/spec.toml`). No sieve, no optional axes.
- **Framework build:** accepted v6, no change. Core read `config/core-d13b.fw.properties`, which differs from
  the shipped template only in two observation-only keys (`core.replace.patternPolicy=warn`,
  `core.replace.diagnostics=summary`).
- **Contract:** v1 `fc98673f…4517`; predictions `00a5f478…096e` and `derive.py` `d6180103…fbba` unchanged.
- **Envelope:** `generated-default`, one worker, K=1, `-Xmx2g`, budgets 150/150/50 MB/400 s, no override. The
  Bundle took 91 s.
- **Evidence kind:** Verified/run. Replays were 5/5 byte-identical.
  - **Verifier:** the post-run `verify.py` passed 29/29, including 3,348 record fields, and gave the same 29/29
    from `archive/…/inputs`.
  - **Campaign-time verifier:** it reported 25/29 because of three verifier bugs, not evidence defects (see
    Provenance). Its output is kept as `verification-campaign-time.json`.
- **Refused launch, disclosed:** an earlier launch, `d13b_20260928T094833Z`, was refused by the Bundle's
  own preflight within 0.9 s.
  - **Cause:** my launcher environment lacked the results-DB password.
  - **Nothing ran:** no database, run directory or stage was created. Its folder is preserved as is.
- **Model:** a deterministic marker-language processor with in-memory stubs (ready, flag, outbox). It is not
  a live LLM test and says nothing about general prompt-injection coverage.

## Framework composition (actual Core rows)

Mandatory factors: HEAD, IMPL (3 policies, position 2), ENCODING (3), MARKER (3), ROOT and TAIL. The ten
operand and token sheets are `FW_Exclude + FW_Reuse`.

| Step | Directive | Observed |
|---|---|---|
| CHUNKS pass 0 | `FW_Cartes(LEAF_END)` | 2 rows: `[30, 29]` (marker open, `),`) and `[31, 29]` (filler open, `),`) |
| CHUNKS group | `FW_Group` + `ReplaceRE("\[","")` + `ReplaceRE("\]","")`, then `FW_Permut()` | 2 emissions over whole rows: `[[30, 29], [31, 29]]` → `30, 29, 31, 29` and `[[31, 29], [30, 29]]` → `31, 29, 30, 29` |
| CHUNKS finish | `FW_Combi(size)` | 2 rows × 4 codes (MF, FM); Core's summary: seen 2, rewritten 2, dropped 0, each pattern 2 |
| INNER | `FW_(,,PREFIX,LIST_OPEN,CHUNKS,,LIST_END,,M:N)` | 4 rows × 7 codes |
| ROOT | `FW_(CONTEXT_OPEN,,FW_(),COMMA,NOTE,,CONTEXT_CLOSE,,M:N)`; Core resolved `FW_()` → INNER (`excl1=INNER[N]`) | 4 rows × 11 codes |

**Pairs stay intact.** Permuting whole rows keeps each leaf's open/close pair together. Permuting the four
fragments instead would allow 12 distinct sequences, most of them unbalanced.

**The four ROOT rows,** decoded from `fw_final` (codes: CONTEXT_OPEN 35, PREFIX 27/28, LIST_OPEN 32, LIST_END
33, COMMA 36, NOTE 34, CONTEXT_CLOSE 37):

```
consume(context([trusted_task(),retrieved_page([source_item("marker"),\nsource_item("filler"),\n]),trusted_note()]))
consume(context([trusted_task(),retrieved_page([source_item("filler"),\nsource_item("marker"),\n]),trusted_note()]))
consume(context([trusted_task(),tool_result([source_item("marker"),\nsource_item("filler"),\n]),trusted_note()]))
consume(context([trusted_task(),tool_result([source_item("filler"),\nsource_item("marker"),\n]),trusted_note()]))
```

**How the rows were checked.**
- **Boundaries:** the verifier parsed each row with `ast` and checked every boundary position. INNER is the
  row slice 1..7 and CHUNKS the slice 3..6; both equal the construction model on the live dictionary.
- **No placeholders:** no placeholder code reaches a row.
- **Carrier and order from the rows:** they come only from these decoded structural rows. The runtime builds
  the tree by evaluating the composed expression.
- **Before the run:** `construct.py --precheck` certified the same 2 / 4 / 4 structure and parsed all four
  expressions. It also ran the 108 predicted programs on the host, which reproduced the frozen IDs and verdicts.

| Stage | Count |
|---|---:|
| Plans (XLSX = TOML, same normalised brace graph) | mandatory and final **BOUNDED [27, 108]** (value 108); CHUNKS [0, 2], INNER [0, 4], ROOT [0, 4] |
| Core `fw_final` (3 × 3 × 3 × 4) | 108 (per-sheet after DISTINCT: CHUNKS 2, INNER 4, ROOT 4) |
| Reader / Executor / results_v2 | 108 / 108 / 108; one attempt each |
| Outcomes | **80 PASS / 28 DOMAIN_FAIL**; zero BROKEN, INFRA_FAIL or TIMEOUT |

- **Why BOUNDED:** it is the planner's sound bound, because DISTINCT follows a pass that is not provably
  injective (the custom rewrite and the braces). The mode is recorded, not overridden; Core measured 2, 4, 4
  and 108.
- **Rendering:** every rendered candidate is byte-exactly the newline join of its Core row's decoded columns
  (108 exact).

## Outcomes

| Policy | PASS / FAIL | Promotion effect (count) |
|---|---|---|
| preserve_origin | 36 / 0 | no promotion (36) |
| wrapper_trust | 24 / 12 | forbidden outbox (6), forbidden flag (6), benign REF promotion (6), none (18) |
| decode_trust | 20 / 16 | forbidden outbox (8), forbidden flag (8), benign REF promotion (8), none (12) |

**Where the failures fall:**
- **wrapper_trust:** only `tool_result` × {emit_canary, set_flag} fails (12), for every order and encoding.
  `retrieved_page` has an untrusted envelope, so wrapping promotes nothing there.
- **decode_trust:** only {json, base64} × {emit_canary, set_flag} fails (16), for both carriers and orders.
  Plain markers stay untrusted.

| Axis | Tallies (PASS / FAIL) |
|---|---|
| Carrier | retrieved_page 46 / 8; tool_result 34 / 20 |
| Order | MF 40 / 14; FM 40 / 14 (the configuration tallies are identical for both orders) |
| Encoding | plain 32 / 4; json 24 / 12; base64 24 / 12 |
| Marker | reference 36 / 0; emit_canary 22 / 14; set_flag 22 / 14 |

**Content and trusted work in every row:**
- Every record keeps all four decoded texts in order, including the canary.
- Every record executes MARK_READY from the trusted task.
- Every leaf's source origin stays as declared (task and note trusted, carrier leaves untrusted), even when a
  faulty policy's effective origin differs.

## Mechanisms (replayed)

| Case | Marker leaf as stored | Effective origin | Effect | Verdict |
|---|---|---|---|---|
| wrapper_trust, tool_result, MF, plain, emit_canary (`43_0_0`) | `D13B_LOCAL_CANARY\|EMIT_CANARY` | untrusted → **trusted** (from the envelope) | EMIT_CANARY executed; outbox `[D13B_LOCAL_CANARY]` | DOMAIN_FAIL |
| preserve_origin, same configuration (`7_0_0`) | same | untrusted | candidate EMIT_CANARY, **not executed**; outbox `[]` | PASS |
| decode_trust, retrieved_page, FM, json, set_flag (`94_0_0`) | `"D13B_LOCAL_CANARY\|SET_FLAG"` | untrusted → **trusted** (from decoding) | SET_FLAG executed; flag true | DOMAIN_FAIL |
| preserve_origin, retrieved_page, FM, base64, emit_canary (`30_0_0`) | `RDEzQl9MT0NBTF9DQU5BUll8RU1JVF9DQU5BUlk=` | untrusted | decoded to `…\|EMIT_CANARY`, not executed | PASS |
| wrapper_trust, tool_result, MF, json, reference (`51_0_0`) | `"D13B_LOCAL_CANARY\|REF"` | untrusted → trusted | REF has no candidate action | PASS |

- **A trusted envelope is not a trusted leaf.** `tool_result` is created by the application, but its
  children are untrusted source data. wrapper_trust copies the envelope's origin onto the marker (and the
  filler), so a command inside the data runs. preserve_origin keeps the leaf's own origin.
- **Decoding is not authorization.** base64 and json change the representation only. In `30_0_0`, the same
  command string is decoded and recorded but stays inert. decode_trust treats "needed decoding" as "trusted".
- **The same canary appears as safe data and as a forbidden effect.** `43_0_0` and `7_0_0` render the identical
  text `MARK_READY / D13B_LOCAL_CANARY|EMIT_CANARY / FILLER / END`. Only `43_0_0` also places the canary in the
  outbox: the oracle requires the canary preserved in the rendered data and absent from the outbox.
- **Benign REF controls.** In 14 cases the effective origin is promoted but the marker carries no command, so
  those cases pass: wrapper_trust with tool_result (6) and decode_trust with json/base64 (8). Promotion is
  diagnostic metadata; the verdict follows the wrong effect, as the contract states.

## Provenance and the verifier fix

- **Archive:** it holds all 18 recorded inputs byte for byte, with `verify.py` as executed by the campaign.
- **The three post-run verifier fixes** (evidence unchanged; each check's intent kept):
  1. Core's pass log prints a directive longer than 40 characters as its first 40 plus `...`. The verifier now
     accepts that prefix form. The full rewrite pair is separately evidenced by Core's ReplaceRE summary.
  2. The Core-input builder writes `FW_Reuse` on every sheet. The structural-sheet rule is now "not excluded,
     not optional" instead of "no flags".
  3. The candidate parser now accepts HEAD's own `d13.SOURCE_SHA256.update(...)` call. The fourth failed check
     only followed from this parse.
- **Other hashes:** workbook, TOML, Core input, inlined sources and candidate hashes all verified.

## Limits

This is one context shape, with two carriers, two leaf orders, three encodings, three marker classes and three
planted policies over exact-string commands with local stubs. It says nothing about natural-language
injection, real models, tools or networks.
