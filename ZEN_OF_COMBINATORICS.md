# The Zen of the Combinatorics Framework — verbs, bonds, meaning

> One engine, three layers. **Mechanics** (the verbs build the space) × **bonds** (the sieve prunes
> combinations) × **meaning** (the verdict judges each candidate). This doc is the verb-vocabulary
> reference + the two corrections that are easy to get wrong (`FW_Optional`, the brace). Verified
> against the Core source (`SeqParser` / `SheetWorker` / `BraceOperationHandler` / `FinalTableAssembler`)
> and end-to-end through `bundle_run`. Reconciled with the current code on 2026-07-21; historical
> demo counts below retain their original evidence date.

## The one principle

**The verb is dictated by the shape of the freedom — never chosen to hit a number.** Model the
problem's real degrees of freedom; the count *falls out*. Ask of each piece of a problem: *what kind
of freedom is this?* — and the verb is forced:

| The freedom looks like… | Verb | Output for `n` values | Example |
|---|---|---|---|
| **exactly one** of a set | `FW_Combi(1)` (default) | `n` | which backend / region |
| **k of n**, order irrelevant | `FW_Combi(k)` | `C(n,k)` | choose 2 resources to touch |
| **any subset** (incl. none) | `FW_Combi(all)` | `2ⁿ−1` (non-empty) / `FW_Subsets` `2ⁿ` | feature flags |
| **k of n with repetition** | `FW_CombiR(k)` | `C(n+k−1,k)` | multiset of statuses |
| **an ordering** (order *is* the variable) | `FW_Permut` / `FW_Permut(k)` | `n!` / `P(n,k)` | pipeline stage order |
| **a sequence with repetition** | `FW_PermutR(k)` | `nᵏ` | k-length code over an alphabet |
| **size-bounded subsets** | `FW_Subsets_EXACT/RANGE/BEFORE/AFTER/GIVEN(…)` | bounded sums of `C(n,k)` | "1 to 3 add-ons" |
| **cross another sheet** | `FW_Cartes(OTHER)` | `n·|OTHER|` | matrix of A×B |
| **weave a glue token between pieces** | `FW_Separator(GLUE)` (modifier) | row-preserving | a connector/delimiter between combined elements |
| **may or may not happen** | `FW_Optional` (flag) | `×(n+1)` per slot | *sudden actions* (below) |
| **join two prior results** | brace `FW_(…)` | 2nd-order join (below) | merge two computed result tables |
| **re-combine + rewrite a prior result** | `FW_Group` + `FW_ReplaceRE` | 2nd-order (≈2ⁿ / n! over rows) | combinations of combinations, then regex surgery |

A spec lays these out as **`FW_Seq`** — an ordered sequence of operations, one row per sheet. Each
row applies its verb to its sheet and produces a **result table**; the mandatory results are
Cartesian-combined into `fw_final`. (`FW_Combi(1)` auto-promotes to a dual verb so `fw2_<k>` is also
written — joiners read `fw2_`.)

The other two layers (separate docs): **bonds** = the constraint **sidecar → `sieve.py`** between
Core and Reader (`constraints/`, chemistry analogy: params on values + a formula + adjacency); the
**meaning** = the Executor's `FW_VAR` oracle (correctness / divergence / speed / dynamics / quality).

---

## `FW_Optional` — the "sudden actions" verb  (analyzed in Core)

A `FW_Optional` slot models a freedom the others can't: **an action that may or may not fire, in any
combination with the other optional actions.** Perfect for *sudden actions* — a failure injected
mid-flow, a retry, a replay/attack step, an interrupt — that should run **before the probe** and let
the verdict catch the consequence.

**How the Core handles it (source of truth):**
1. **`SeqParser`** (`v.endsWith("FW_Optional")`): the sheet is **removed from the mandatory map**
   (`toCombi.remove`) and placed in the **optional bucket** (`toCombiOpt` → `toCombinatoricsHMoptional`).
   Structurally parallel to `FW_Exclude`, but routed to the optional path, not a brace.
2. **`SheetWorker.processAll`** still applies the slot's verb (it iterates mandatory **and** optional
   **and** excluded keys), so the optional sheet's own result table is built.
3. **`MainRefactored`** moves optional keys from `key2tableMap` → `key2tableMapOptional`; the
   mandatory `fw_final` is built **without** them.
4. **`FinalTableAssembler`** runs a separate `optsThread` / `runOptionalInsert` cartesian: with
   `core.optional.includeOptionalCombiPairsToDBCSVList=1..N` it materializes optional combos of
   **every size 1..N** (which subset of sudden actions co-fire) into `fw_opt<i>` tables.
5. **Reader** (`reader.core.processIsOpt=true` + `processBothFinalAndOpt=true` + `isOptCSVList=1..N`)
   reassembles `fw_final × (each optional combo OR absent)`, **inserting each optional piece at its
   slot position (before the TAIL)** — so a sudden action executes *before* the probe and `FW_VAR`
   is set correctly.

**Count:** `fw_final × Π(nᵢ + 1)` over optional slots — each sudden action contributes *one of its
values OR absent*. (`bundle_run.py` auto-detects `FW_Optional` and computes/verifies exactly this.)

**Worked, tested:** `llm_loop/redteam3/` — 3 `FW_Optional` slots → `fw_final 8 × 2³ = 64` candidates
(56/64 breach against the live surrogate). With `n_opt = 0` the path is byte-identical to a plain run.

**Zen:** `FW_Optional` is the *× (present ⊕ absent)* dimension — it lets you bolt "what if this also
happened?" onto any base space **without** exploding the mandatory product, and across all subsets.

---

## The brace `FW_(…)` — a JOIN of two PRIOR result tables  (corrected)

> **Correction (Yuri, 2026-06-06):** the brace operands are **NOT raw value sheets** — they are the
> **combination-RESULT tables that earlier `FW_Seq` rows produced**. `FW_Seq` is a *dataflow of
> result tables*; the brace is a **join node** over two upstream results that writes a new one.

Grammar — 9 fields: `FW_(start, _, E1, rel, E2, _, end, sep, mult)`
A brace is **more than a join** — it has its OWN beginning, relation operator, separator, and ending
(four formatting sheets), each contributing its **first value**:
- `E1`,`E2` (positions 2 & 4) = the **names of two earlier sheets whose result tables** (`fw2_<k>`,
  else `fw_<k>`) are the operands — read via `BraceOperationHandler.resolveSourceTableForInner`.
- `start` (0) = **beginning** prepended to each row; `rel` (3) = **relation operator** woven between an
  A-element and B; `sep` (7) = **separator** woven between the per-element groups; `end` (6) = **ending**
  appended (`wrapWithStartEnd` + `build{OneToN,ManyToMany,…}`). All four are optional; each uses only the
  sheet's first value. (field usage varies by `mult`: `1:1`/`1:N`/`M:1` weave `sep`; `M:M`/`M:N` use `rel`.)
- `mult` (8) ∈ `1:1 | 1:N | M:1 | M:M | M:N` — the join cardinality (`process{One,Many}ToFormula`):
  `M:N` = full cross product; `1:1`/`M:M` pair by equal cardinality; etc.
- Operands `E1`/`E2` **MUST carry `FW_Exclude`** so they're consumed by the join (`cleanupExcludedTables`
  drops them after — unless kept, see flags); `start`/`rel`/`sep`/`end` are **non-excluded** 1-value
  helper sheets (just read). fwgen's `verb_sheet_operands` now validates **all six** sheet fields exist.
  The brace's **output** is itself a result table (`fw2_<target>`) that later rows / `fw_final` consume.
- **Verified full-field** (`brace_full_demo/`, full Bundle): `FW_(START,,A,REL,B,,END,SEP,1:N)` with
  `A=FW_Combi(2)` over 3 ⋈ `B=FW_Combi(1)` over 2 → e.g. `<< a1 -> b1 | a2 -> b1 >>` — START/REL/SEP/END
  all woven in.

**Authoring (fwgen):**
```toml
# TOP-LEVEL key — MUST precede every [[slots]]/[[goals]] table, or TOML binds it to the
# last table and it is silently dropped from FW_Seq (this bites — verify with load_spec).
seq_extra = [["JOINED", "FW_Reuse", "FW_(,,A,,B,,,,M:N)"]]

[[slots]]            # operands carry FW_Exclude
sheet="A"  verb="FW_Combi(2)"  flags=["FW_Exclude"]  raw=true  values=[...]
[[slots]]
sheet="B"  verb="FW_Combi(1)"  flags=["FW_Exclude"]  raw=true  values=[...]
[[slots]]            # the brace TARGET must be a declared slot (placeholder value) so it has a key
sheet="JOINED" verb="FW_Combi(1)" raw=true values=["pass  # overwritten by the brace"]
```

**Verified end-to-end** (`brace_demo/`, full Bundle, green): `A=FW_Combi(2)` over 3 steps → result
`{audit,migrate},{audit,backup},{migrate,backup}` (3 pairs); `B=FW_Combi(1)` over 2 regions → 2;
brace `M:N` → **6 plans** — each = *(an A-pair) + (a B-value)*, e.g. `audit|migrate|region:eu`. The
join consumed **A's `FW_Combi(2)` result**, proving operands are prior result tables, not raw sheets.

---

## `FW_Separator(GLUE)` — the glue modifier  (analyzed in Core)

A **modifier** (not a standalone generator) on a sheet that *also* carries a combinatorial verb. It
weaves a single fixed token — the **first value of the named `GLUE` sheet** — between every pair of
elements of each produced row. **Cardinality-preserving**: only the row *content* changes, not the count.

- **Core** (`SheetWorker`): `separatorValue = srcMap.get(separatorKey).get(0)`. The weave happens in the
  **sub-combo / dual (`fw2_`) generation** (`combo[i*2+1] = sep`), and inside `FW_Group` via
  `curStr.replaceAll(", ", ", SEP, ")`. Only the separator sheet's **first** value is ever used.
- **⚠ Where the weave lands (verified):** it goes into the sheet's **`fw2_` / sub-combo output, which a
  brace or `FW_Group` consumes — NOT the plain `fw_` table that the `fw_final` cartesian reads.** So
  `FW_Separator` on a *plain* slot is invisible in `fw_final`; pair it with a **brace** (the join reads
  `fw2_`) or **`FW_Group`**. Also: the separator must be set **before** the generating pass, so the
  verb should **auto-promote to a dual** (parenthesized `FW_Combi(k)`/`FW_Permut(k)`/… or bare
  `FW_Subsets`) — a bare `FW_Permut` (no dual) won't weave.
- **Authoring (fwgen, first-class):** `[[slots]] … separator = "GLUE"` (fwgen emits `FW_Separator(GLUE)`
  after the verb and validates that `GLUE` is a declared sheet). **Verified end-to-end** in
  `group_sep_demo/`: `A = FW_Combi(2)` over 3 steps with `separator = "GLUE"`, joined `M:N` with `B` →
  every plan reads `audit|GLUE|migrate|region:eu` — the glue woven into the join operand.
- **Zen:** the *connective tissue* — drop a fixed operator / delimiter / `AND` / `→` between combined
  pieces so an assembled candidate reads as a real **sequence**, not a bare list.

## `FW_Group` + `FW_ReplaceRE` — second-order combinatorics + rewrite  (studied carefully in Core)

`FW_Group` is a **higher-order** operator: it re-runs a combinatorial generator (the row's `algoType`
— `Combi/CombiR/Permut/PermutR/Subsets/Cartes`, size via the arg) **over the sheet's PRIOR RESULT ROWS
treated as atoms**. A first-order verb combines a sheet's *values*; `FW_Group` combines its already
produced *rows* → **combinations of combinations** (nested/structured objects).

`FW_ReplaceRE("pattern","replacement")` (embedded in the directive) then does **regex surgery** on each
group's assembled string — three modes (verified in `SheetWorker`):
1. **literal** — `FW_ReplaceRE("X","Y")` → replace matches of `X` with `Y`;
2. **delete** — `FW_ReplaceRE("X","")` → strip matches of `X`;
3. **splice another sheet** — a replacement containing `+` (e.g. `"OTHER + ..."`) → resolve `OTHER`'s
   first value and splice it in (a templated cross-sheet substitution).
Then `FW_Separator` (if present) interleaves, and the string is parsed back to codes → `fw2_<key>`.

**Canonical worked example** (`Core_trunk/README_CANONICAL_TRUTH.txt`): sheet `E` → `FW_Subsets` →
`fw_53` = 4 rows `{[], [489], [490], [489,490]}`; then **`FW_Subsets` over `fw_53` in `FW_Group` mode**
enumerates the **16 subsets of those 4 ROWS**, each subset's rows concatenated *in index order* with the
`FW_Separator` value `515` — e.g. subset `{row_b,row_d}` → `[489, 515, 489, 515, 490]`.

- **⚠ Order-sensitivity (the spec hole the Core guards):** `FW_Group` enumerates by **INDEX** into the
  source-row list and concatenates in index order, so the output depends on source-row **ordering**.
  Different stores (PG HashAggregate vs JVM LinkedHashMap) gave different orderings → different byte
  strings → different distinct counts (14 vs 13 of the 15 non-empty subsets). The Core's **Iter4 Step-10
  fix content-sorts the source rows** so ordering is a pure function of the data → one deterministic
  result. Lesson: `FW_Group` is the most order-sensitive verb; rely on the content-sort, and remember
  grouping concatenates **by index order**.
- **Cardinality:** `FW_Group` genuinely multiplies (`2ⁿ` for Subsets over `n` rows, etc.), but
  `estimate_core_combos` treats it as row-preserving → the estimate is **approximate** for `FW_Group`
  (same caveat as the brace).
- **Authoring (fwgen, first-class):** `[[slots]] … group_replace = [["pat","rep"], ...]` — fwgen emits
  the multi-line `FW_Group` + `FW_ReplaceRE(...)` directive after the verb (byte-identical to the proven
  `testgen_api.py` pattern; `validate_workbook` accepts it). The `FW_ReplaceRE` rewrite operates on the
  **code-string** representation pre-parse-back, so keep patterns parse-back-safe; the canonical
  *render* use (strip brackets, quote tokens) lives in `testgen_api.py`.

**Zen:** the brace and `FW_Group` are the engine's **two second-order operators** — the brace **joins**
two prior results (binary); `FW_Group` **re-combines one** prior result and **rewrites** it (unary +
transform). Together they lift `FW_Seq` from "a product of value-axes" into a genuine **combinatorial
dataflow algebra**: build atoms → group/join them → rewrite the token stream.

---

## Flags around the brace

| flag | effect (Core) |
|---|---|
| `FW_Exclude` / `FW_Heading` | move a sheet OUT of the mandatory cartesian into the exclude map (sheet-level, **not** a per-combination filter) — required for brace operands |
| `FW_Reuse` | through brace cleanup, **keep the operand TABLE** (skip `dropTable`) |
| `FW_ReuseTableOnly` | through brace cleanup, **keep its ROWS** (skip `deleteRows`) |
| (both) | preserve table **and** rows for reuse by a later join (nested operands need both) |
| `FW_Concatenator=X` | set the per-sheet concatenator |
| `FW_Optional` | route to the optional path (sudden actions, above) — **not** a brace operand |

Constraints/bonds are **never** expressed with `FW_Exclude` or a brace (the brace is *generative* — it
adds joined rows; it does not *forbid*). Forbidding a value-combination → the **sidecar/sieve**.

---

## Authoring gotchas (each cost real time — don't regress)

- **`seq_extra` must be a TOP-LEVEL toml key** (before any `[[slots]]`/`[[goals]]`). After a table it
  binds to that table and is dropped — `fw_final` then shows the un-joined placeholder. Verify:
  `python3 -c "import fwgen as fg; print(fg.load_spec(P).seq_extra)"`.
- **No data cell may start with `FW_`** (parsed as a directive). A TAIL that sets `FW_VAR` must lead
  with another statement (e.g. `_n = len(x)` first).
- **`estimate_core_combos` ignores brace/join AND `FW_Group` effects** — for a brace or `FW_Group` spec
  the estimate is the mandatory product (often 1/n); the real `fw_final` is the second-order size.
  `bundle_run` warns, doesn't fail.
- **`FW_Group` concatenates by INDEX order** of the source rows → output is order-sensitive; rely on the
  Core's content-sort (Iter4 Step-10) for determinism. `FW_Separator` uses only the glue sheet's FIRST value.
- **Brace operands need `fw2_<k>`** — provided automatically by the `FW_Combi(1)→dual` auto-promote.
- **Analyzer fallback is not full optimization.** Missing remote Analyzer configuration can use the
  inline compatibility path. Check the analyzer stage/provenance artifacts rather than inferring a
  full formal run from overall stage success; the canonical offline verifier is
  `bash Analyzer_trunk/run-tests.sh`.

## The demos (run them)

- `generator_trunk/model_usecases/gpt4lite_variants.py` — `FW_Combi(1)` × 4 axes; hardware-optimal kernel set (81).
- `generator_trunk/constraints/scale_demo/scenario_scale.py` — `FW_Permut × FW_Subsets × FW_Combi(2) × FW_Combi(1)²`
  + the **sieve at 10⁴→10⁶** (exact integrity, linear throughput).
- `generator_trunk/brace_demo/` — the corrected brace, joining two prior result tables (M:N → 6), full Bundle green.
- `generator_trunk/brace_full_demo/` — the **full brace** `FW_(START,,A,REL,B,,END,SEP,1:N)`: beginning / relation /
  separator / ending all woven (`<< a1 -> b1 | a2 -> b1 >>`), full Bundle green.
- `generator_trunk/group_sep_demo/` — `FW_Separator` (first-class `separator=` field) woven into a **brace operand**
  (`audit|GLUE|migrate|region:eu`), proving the glue lands in the `fw2_`/sub-combo a join consumes.

Authoring the second-order/modifier verbs in fwgen (now first-class): a slot takes `separator = "GLUE"`
and `group_replace = [["pat","rep"], …]`; the brace is a top-level `seq_extra` row.


---

## ⚠ `FW_ReplaceRE` rewrites the Core **short key = `Short`** (a code-string), NOT value text  (verified 2026-06-12)

> **Correction (added 2026-06-12, verified against `Core_trunk/.../SheetWorker.java`):** the Core's
> "short key" is a **`Short`** — a 16-bit integer value-code. The combinatorics store is
> `Map<Short, List<Short>>` (`SheetWorker.java:600`): every value travels as a `Short` code, and a
> produced combination is a *list of those codes*.

`FW_ReplaceRE` inside `FW_Group` is therefore a **code-string** transform, **not** a value-text one:

- Per produced group the Core builds `curStr = w.toString()` where `w` is a combination of `Short`
  **codes** — e.g. `"[47, 48]"` — and runs `curStr = curStr.replaceAll(pattern, replacement)` for each
  `FW_ReplaceRE` (`SheetWorker.java:1051-1055`).
- The rewritten string is parsed **straight back to `short[]` via `Integer.parseInt`** (`:1062-1066`) and
  written to **`fw2_<k>`** — the dual/sub-combo table (like `FW_Separator`), *not* the plain `fw_` that the
  `fw_final` cartesian reads (`:1082`).
- So a pattern matches **numeric codes + structural chars** (`{ } [ ] , ` and space), and the replacement
  **must stay integer-parseable**. All three modes (`:604-621`) are code-level: **remap**
  `FW_ReplaceRE("<code>","<code>")`; **`+`-splice** `FW_ReplaceRE("<pat>","OTHER + …")` → resolves
  `srcMap.get(joinKey).get(0)`, the **first `Short` code of sheet `OTHER`** (`:605-614`); **delete**
  `FW_ReplaceRE("<pat>","")` (`:617-618`). A *textual* replacement (e.g. `"shape"`) that matched would
  throw `NumberFormatException`, and the row is **dropped** (`:1083`).
- **Practical lesson (cost real time on 2026-06-12, an LLM-transformer test campaign):** you cannot use
  `FW_ReplaceRE` to rewrite *text inside a value* — e.g. a placeholder `@S@` → `shape` in
  `sel.append("@S@")`. That whole cell is **one** value with **one** `Short` code; the rewrite sees the
  code-string `"[47, 48]"`, never the literal `@S@`, so it is a silent **no-op** and the token passes
  through verbatim (the green run still "passes," but the intended substitution never happened — a quiet
  trap). Author `FW_ReplaceRE` against the **codes / structure**, not the rendered token; the canonical
  render use ("strip brackets, quote tokens") rewrites exactly those structural characters of the
  code-string. The "internal short key" is the `Short` code, and the transform is *in-between* the
  grouping and the parse-back.
- **This trap is now detectable at authoring time, opt-in.** `core.replace.patternPolicy=warn|strict`
  rejects a pattern that provably cannot match a code-string — it would have caught the `@S@` case
  above before the campaign ran. `core.replace.unmatchedPolicy` catches the pattern that *could*
  match but never does, and `core.replace.diagnostics=summary` prints per-pattern hit counts so a
  no-op is visible without changing behaviour. All five keys default to the historical behaviour and
  restrict nothing; operating on the short **keys** is the capability, not the bug. See
  [docs/41_FW_REPLACERE_POLICIES.md](docs/41_FW_REPLACERE_POLICIES.md).
