# 28 — Second-order axes of freedom (Core) → nested value-dependencies (sieve)

> **Dated study plus implemented design.** The Core trace is from 2026-06-29. The current Python
> constraint path supports n-ary relations, mappings, assertions, conditions, ordering, and
> deferred optional bonds; the Reader enforces the compiled optional-bond gate during final
> assembly. See the [current code audit](CURRENT_CODE_AUDIT_2026-07-21.md) and
> `generator_trunk/constraints/README.md` for the operative summary.

> **Two halves.** Part A is the **study** the task asked for: the Core's *second and deeper*
> combinatorics — what happens when one axis of freedom is no longer a flat product but is
> **compounded with another through `FW_(…)`** (and re-combined through `FW_Group`). Part B is the
> **design** that falls out of it: a refactor of the sieve/GUI "constraints" layer so it can express
> the **very nested dependencies between values** of a real RESTful telemetry-catalog query (the
> `/api/catalog/lookup` URL), verified against a live System-Under-Test.
>
> Verified against the Core source actually read on 2026-06-29: `SeqParser.java`,
> `BraceOperationHandler.java`, `SheetWorker.java`, `SubsetsG.java`, `CartesianProductG.java`,
> `README_CANONICAL_TRUTH.txt`. Cross-checked against [ZEN_OF_COMBINATORICS.md](../ZEN_OF_COMBINATORICS.md).

---

## Part A — the Core's deeper stages (study notes)

### A.0 The one-line model, restated

`FW_Seq` is a **dataflow of result tables**, not a flat list of value-axes. Each row applies a verb to
a sheet and writes a **result table** (`fw_<k>`, and its dual `fw2_<k>`). The *mandatory* result
tables are Cartesian-combined into `fw_final`. **First-order** verbs combine a sheet's *values*;
**second-order** operators combine *already-produced result tables*. That second tier is the whole
subject of this study.

### A.1 First-order: one axis = one verb (the flat stage)

`FW_Combi(k)`, `FW_CombiR(k)`, `FW_Permut[(k)]`, `FW_PermutR(k)`, `FW_Subsets[...]`, `FW_Cartes(OTHER)`
each turn a sheet's *n values* into a result table whose size is dictated by the *shape of the
freedom* (`C(n,k)`, `n!`, `2ⁿ`, …). The count *falls out*. Nothing here relates one sheet to
another except the final Cartesian — every mandatory sheet's table is multiplied in, independently.
This is the "first stage". The interdependencies the task cares about live **above** it.

### A.2 Second-order operator #1 — the brace `FW_(…)` is a JOIN of two prior result tables

Grammar (9 comma fields): `FW_(start, _, E1, rel, E2, _, end, sep, mult)`.

What the source actually does (`BraceOperationHandler.execute`, lines 48–213):

- `E1`/`E2` (fields 2 & 4) are **sheet names whose RESULT tables are the operands** — resolved by
  `resolveSourceTableForInner`: prefer `fw2_<k>`, else fall back to `fw_<k>`. They **must carry
  `FW_Exclude`** so `SeqParser` moves them out of the mandatory Cartesian and into the exclude map
  (`SeqParser.java:141-157`), and the brace consumes them; `cleanupExcludedTables` (lines 627-655)
  drops them afterwards unless `FW_Reuse`/`FW_ReuseTableOnly` keep the table/rows.
- `mult ∈ {1:1, 1:N, M:1, M:M, M:N}` selects the join cardinality:
  - `1:1` / `M:M` pair operand rows **of equal cardinality** (`readWithCardinality(a.length)`);
  - `1:N` / `M:1` fan one side across the whole other side;
  - `M:N` is the **full cross product** (`processManyToFormula`, lines 245-283).
- `start`/`rel`/`sep`/`end` are **non-excluded 1-value helper sheets**; the brace reads only each
  one's **first value** (`safeFirst`, line 288) and weaves it in: `rel` *between* an A-element and a
  B-element, `sep` *between* groups, `start`/`end` *around* the row (`wrapWithStartEnd`, line 379).
- The brace's **output is itself a result table** (`store.moveFwToFw2` → `fw2_<target>`, lines 181-199)
  that later rows — *including another brace* — can consume.

**Why this is "a second axis of freedom":** the operand rows are *combinations*, not values. The
join's degrees of freedom are *which A-combination pairs with which B-combination*, shaped by `mult`,
`rel`, `sep`. The candidate string reads as a real **structured object**
(`<< a1 -> b1 | a2 -> b1 >>`), not a flat tuple.

### A.3 The deep stage — **nested braces** (`~FWN` / `~FWG`) compound axes

This is the part the task underlines ("*when things start to go way too complicated per axis of
freedom and be compound with other axis of freedom through `FW_(.*)`*"). The Core supports a brace
operand that is **itself a brace** — i.e. *a join of a join*:

- `SeqParser.resolveNestedFwBrace` (lines 344-399) detects an operand position holding `FW_(...)`. It
  rewrites it to point at the **most recent prior brace target** (`priorFwBraceTargets`, a stack of
  earlier brace output keys), tagging it `~FWN` (**plain nested** — consume the prior brace's result
  rows as-is) or `~FWG` (**grouped nested** — flatten all the prior brace's rows into ONE mega-row,
  `array_agg(unnest)` in `preparePgBraceOperand`, lines 576-582 / the Java mega-array path 520-530).
- It also force-adds the prior target to `reuseSet` **and** `reuseTableOnlySet` (lines 394-395), so a
  deeply-referenced intermediate **survives cleanup** for the next join up the tree.
- `BraceOperationHandler` strips the `~FWN`/`~FWG` marks (lines 88-105) and builds the operand
  accordingly.

So you can write `brace₁(A,B) → R₁`, then `brace₂(R₁, C) → R₂`, then `brace₃(R₂, D)` — an arbitrarily
deep **left-leaning tree of joins**. Each level's "axis of freedom" is *which structure from the level
below combines with the next sheet, and how* (cardinality/relation/separator). **That is what
"compound with other axis of freedom through `FW_(.*)`" means in the engine.** The freedom at depth *d*
is no longer "which value" — it is "which *combination-of-combinations* couples with the next axis."

**It is NOT capped at second order — it goes to third order and beyond (Yuri, 2026-06-29).** The
mechanism is the `priorFwBraceTargets` **stack**: each completed brace pushes its output key, and the
*next* nested operand pops the most recent (`idx = priorFwBraceTargets.size() - 1`, lines 363-375). So
the tree depth is bounded only by how many brace rows you write. `FW_Group` stacks on top of all of it
(re-combining a brace's result rows as atoms — §A.4). The order of a candidate is literally *how many
generative tiers it passed through*: values (0) → one verb (1st) → a brace/group over results (2nd) →
a brace/group over THOSE results (3rd) → … There is no architectural ceiling; the canonical-truth
fixture's `fw_opt4` is itself a 4-way optional Cartesian over already-grouped subsets.

**Authoring update (2026-07-25).** TOML specs can express those Core markers directly as brace operands:

```toml
seq_extra = [
  ["R1", "FW_Reuse", "FW_(OPEN1,,A,,B,,CLOSE1,,M:N)"],
  ["R2", "FW_Reuse", "FW_(OPEN2,,FW_(),,C,,CLOSE2,,M:N)"],
  ["R3", "FW_Reuse", "FW_(OPEN3,,FW_()G,,D,,CLOSE3,,M:N)"],
]
```

`FW_()` consumes the newest preceding brace result as ordinary rows; `FW_()G` consumes its grouped form. `fwgen` strict validation accepts both operand forms, and `fwseq_graph` resolves their dependency edges against the same newest-first brace stack instead of treating them as sheet names.

Operand sheets and intermediate targets should carry `FW_Exclude`; only the root target should be mandatory. Otherwise `fw_final` independently multiplies each intermediate result table. The Automation Studio operator smoke demonstrates the difference: three 8-row intermediate/root tables produce 512 redundant final rows when all are mandatory, but exactly 8 meaningful higher-order rows when `R1` and `R2` are excluded assembly temporaries.

The executable examples are `scenarios/automation_scheme_studio/advanced_feedback/01_operator_smoke` (bounded proof), `10_third_order_brace` (third order), and `20_grouped_repetition` (`FW_Group` feeding nested braces).

**The canonical 3rd-order telemetry-catalog construct — `sortBy`.** A real `sortBy` parameter
(`{signal}{relationSign}{ordering}` triples, CSV-joined) is exactly a three-tier build:
  - **1st order:** the value sheets — `SignalClass` values, `relationSign` (`=`), `ordering ∈ {UP,DOWN}`.
  - **2nd order:** one *sort-term* = a brace join weaving `SignalClass · relationSign · ordering` →
    `Radar=DOWN` (`rel`/`sep` woven, §A.2).
  - **3rd order:** `sortBy` = a `FW_Group`/`FW_Subsets` over the *set of sort-terms*, CSV-joined →
    `Radar=DOWN,WeatherStation=UP` — a **combination of (combinations-of-combinations)**.
And it carries a genuinely nested *value*-dependency: the signal classes named in `sortBy` must be a
**subset of `SignalClassList`** (`subOf`, §B.2) — a 3rd-order structure constrained against a
multi-select axis. This is the showcase that ties Part A (deep generation) to Part B (deep forbidding).

### A.4 Second-order operator #2 — `FW_Group` re-combines ONE prior result and rewrites it

`FW_Group` (`SheetWorker.runDirective` line 598; group execution 947-1087) is the **unary** second-order
operator: it re-runs a combinatorial generator over the sheet's **own prior result ROWS treated as
atoms** → *combinations of combinations*. Critical details from the source:

- The source rows are **content-sorted (lex) before enumeration** (Iter4 Step-10, lines 952-987) so the
  index-order the generators use is a **pure function of the data** — the determinism fix recorded in
  `README_CANONICAL_TRUTH.txt` (the 33,674,483 vs 34,368,597 `fw_opt4` split).
- `FW_ReplaceRE("pat","rep")` then does **regex surgery on the code-string** of each group (lines
  1050-1066): literal remap, delete (`""`), or `+`-splice another sheet's first code. It rewrites the
  **`Short` code-string** (`"[47, 48]"`), *not* value text — a textual replacement throws
  `NumberFormatException` and the row is dropped (the quiet trap documented in the Zen, 2026-06-12).
- `FW_Separator` (lines 630-639, 1057-1059) interleaves a single glue code between elements; like the
  brace, it lands in the **`fw2_`/sub-combo** stream a join or group consumes — invisible to a plain
  `fw_final` Cartesian.

`FW_Group` multiplies cardinality genuinely (`2ⁿ` Subsets over n rows, etc.) but `estimate_core_combos`
treats it as row-preserving → the planner estimate is approximate (same caveat as the brace).

### A.5 The third "axis" — `FW_Optional` (present ⊕ absent)

`FW_Optional` (`SeqParser.java:175-183`; assembly per `docs/27`) adds, **orthogonally to the mandatory
product, a `× (one value OR absent)` dimension per optional slot**: `fw_final × Π(nᵢ+1)`. The Reader
assembles `fw_final × (each optional combo OR absent)`, inserting each optional piece at its slot
position. This is the engine's model of **a URL parameter that may simply be omitted** — and it is the
seed of the most important modelling decision in Part B.

### A.6 The takeaway that drives the sieve refactor

The Core's generative tiers (brace nesting, `FW_Group`, `FW_Optional`) build candidates whose
**values are deeply inter-related by construction**: a brace's `rel` is literally a *relation operator*
woven between two axes; a nested brace couples a structure to the next axis; `FW_Optional` makes
presence itself a degree of freedom. Per the Zen's separation of concerns, **the brace/group are
*generative* (they ADD rows); they never *forbid*.** Forbidding an value-combination is the
**sieve's** job.

So if the generator can *produce* candidates with nested, ordinal, presence-coupled, subset-coupled
structure, the sieve must be able to *forbid by* those same relations. Today's sieve can forbid by
value-tuples (`pairs`), cross-products (`sets`), a Python predicate over per-value params (`when`), a
dependent allowed-set (`mapping`), and gate any of those by a `condition` AST
(`eq/ne/has/in/nin/hasAny/eqSheet/neSheet/count/countGe/countLe` under `all/any/not`). **What it
cannot yet say** is exactly the vocabulary a real telemetry-catalog query needs:

| Real dependency (from the task) | Missing sieve primitive |
|---|---|
| `CaptureTimeEnd ≥ CaptureTimeStart`, `offsetEnd ≥ offsetStart` | **ordinal cross-sheet** `geSheet/gtSheet/leSheet/ltSheet` |
| `QualityTier ≥ gold`, `encoding ≥ parquet` (quality tiers) | **ordinal-vs-constant** `ge/gt/le/lt` |
| `IndexedTimestamp` cannot be present with `provisional`; `CaptureTimeEnd` present *requires* `CaptureTimeStart` present | **presence** `present: true/false` |
| `sortBy` may only sort by signal classes that are in `SignalClassList` | **subset cross-sheet** `subOf/supOf` |
| any of the above used as the **rule itself**, not just a gate | **`assert` bond family** (a condition-AST as a require/forbid body) |

These five are the refactor. They are all **value-level relations**, they all **compose under
`all/any/not`** (hence *very nested*), and `assert` lets a relation BE the bond, mirroring how the
Core's `rel` operator *is* the coupling between two generated axes.

---

## Part B — the refactor design

### B.1 The `orders` model (new sidecar section)

Ordinal ops need a rank. Add:

```jsonc
"orders": {
  "QualityTier": ["bronze", "bronze-plus", "silver", "silver-plus", "gold", "gold-plus", "platinum", "platinum-plus", "diamond"],  // explicit rank = index
  "encoding":     ["csv", "parquet", "zarr"],
  "CaptureTimeStart": "numeric",   // rank = float(value)  (epoch ints / integers)
  "CaptureTimeEnd":   "numeric",
  "SourceTimestamp":  "date"        // rank = ISO date, else lexicographic
}
```

`_rank(sheet, value, orders)`: explicit list → `index` (a value not in the list is a **spec error →
fail-closed**, never silent lexicographic — the Zen's quiet-trap lesson); `"numeric"` → `float`;
`"date"` → `datetime.fromisoformat`, falling back to lexicographic. **No order declared for a sheet an
ordinal op references ⇒ validation error.** Explicit beats accidental.

**The orders are load-bearing — they MUST be used, not just declared (Yuri, 2026-06-29).** They drive
*every* ordinal relation in the SUT: `CaptureTimeEnd ≥ CaptureTimeStart` and `offsetEnd ≥ offsetStart`
(cross-sheet, `"numeric"` dates/ints), `QualityTier ≥ gold` and `encoding ≥ parquet` (vs-constant tiers),
and the `sortBy` triples carry `ordering ∈ {UP,DOWN}` — a generated, ordered axis. A telemetry-catalog query
without working orderings is not a telemetry-catalog query; the ordinal tier is the spine of the refactor, not an
ornament.

### B.2 New `condition` leaves (compose under the existing `all/any/not`)

| leaf | meaning over the row's per-sheet selection `sel` |
|---|---|
| `{"sheet": S, "present": true/false}` | `S` has ≥1 selected value / `S` is absent (empty) |
| `{"sheet": S, "ge"/"gt"/"le"/"lt": C}` | scalar rank of `S`'s value `≥/>/≤/<` `rank(C)`; **vacuously true if `S` absent** |
| `{"sheet": S, "geSheet"/"gtSheet"/"leSheet"/"ltSheet": T}` | the whole `S` selection vs the whole `T` selection by rank (see semantics); **vacuously true if either side absent** |
| `{"sheet": S, "subOf"/"supOf": T}` | `set(sel[S]) ⊆ / ⊇ set(sel[T])` |

**Multi-select ordinal semantics (documented, total):** `S geSheet T` ⟺ `min(rank(S)) ≥ max(rank(T))`
("`S` lies entirely at or above `T`"); `leSheet` ⟺ `max(rank(S)) ≤ min(rank(T))`; strict variants
analogous. For single-select sheets (the date / pagination case) this is exactly the scalar
comparison. **Absence is vacuous** for ordinal/subset leaves — pair with a `present` leaf when you also
want "both must be present" (single-purpose, composable primitives).

### B.3 The `assert` bond family (a condition-AST as the bond BODY)

```jsonc
{ "id": "...", "polarity": "require"|"forbid", "assert": <condition-AST>, "condition": <gate-AST?> }
```

Evaluated on `sel` (like `mapping`, NOT like `pairs` — it must see absence):

- if `condition` present and not satisfied → **inert** on this row;
- `require`: row **violates** iff `not eval(assert)`;
- `forbid`:  row **violates** iff `eval(assert)`.

Examples (the exact task dependencies):

```jsonc
{ "id": "capture_range",   "polarity": "require", "assert": {"sheet":"CaptureTimeEnd","geSheet":"CaptureTimeStart"} }
{ "id": "indexed_xor_provisional","polarity": "forbid",  "assert": {"all":[{"sheet":"IndexedTimestamp","present":true},
                                                                  {"sheet":"provisional","present":true}]} }
{ "id": "sort_signal_subset",  "polarity": "require", "assert": {"sheet":"sortBy","subOf":"SignalClassList"} }
{ "id": "zarr_quality",  "polarity": "require", "assert": {"sheet":"QualityTier","ge":"gold"},
                        "condition": {"sheet":"encoding","eq":"zarr"} }   // zarr ⇒ QualityTier ≥ gold
```

`assert` **subsumes** the inequality/presence/subset rules and composes them arbitrarily deep — the
"very nested dependencies" deliverable. It reuses the **same AST and evaluator** as `condition` (one
code path, one validator). Unlike `when`, it sees absence (a `when` over an absent sheet is *skipped*,
never False) and needs no per-value params. `mapping` is kept for back-compat and its GUI, but is
conceptually a special-case `require` `assert`.

**Arity:** the ≥2-sheet "is it really a bond?" gate stays for `pairs/sets/when/mapping` (it catches
accidentally-underspecified tuples). `assert` is the **deliberate-rule** family and is exempt — a unary
threshold (`QualityTier ≥ gold`) is a legitimate, intentional domain restriction.

### B.4 Modelling decision — **mandatory slot with an explicit `(absent)` sentinel**, not `FW_Optional`

A URL parameter is "one value **or omitted**". The Core models *omitted* with `FW_Optional` (§A.5),
but optional values live in `fw_optX` and are **assembled in the Reader** — the `fw_final` sieve cannot
see them, and presence-sensitive bonds over optional sheets are *fail-closed* (can't compile to the
Reader's present-only filter). For a clean, deterministic, **fully fw_final-enforceable** pipeline we
instead model each telemetry-catalog parameter as a **mandatory single-select slot whose FIRST value is the absent
sentinel** (e.g. the cell `IndexedTimestamp = None`, which the TAIL renders by *omitting* the parameter):

- presence becomes ordinary value logic: `present:true` ≡ `ne <absent>`;
- the absent sentinel is the slot **baseline** (empty `fw_final` cell ⇒ absent), so most rows are
  compact and the mandatory `sieve_fw_final` + `DELETE` path enforces **every** nested bond with no
  Reader-optional machinery;
- it is *more faithful* to a URL: each parameter is a single-select over `{absent, v1, v2, …}`.

The `FW_Optional` telemetry-catalog spec
(`generator_trunk/usecases/telemetry_catalog_e2e/telemetry_lookup.toml`) covers the optional path;
the new full SUT uses the sentinel model. (`orders` lists exclude the sentinel; ordinal leaves are
vacuous on it.)

### B.4a The INPUT SPEC is a first-class artifact — critical *even without the sieve* (Yuri, 2026-06-29)

The combinatorial **input spec** — the `FW_Seq` of slots/verbs that *generates* the telemetry-catalog query space —
is a deliverable in its own right, not merely a carrier for the bonds. It must:

1. **Stand alone & run without any sieve.** Every form the spec produces (the *full, unsieved*
   product) must assemble a **syntactically well-formed URL** that the SUT service can parse. The
   sieve only removes the *semantically* invalid ones; remove the sieve and you still have a valid,
   meaningful generator whose every candidate is a real request.
2. **Genuinely exercise the Core's combinatorics studied in Part A**, not just flat single-selects:
   - **multi-select** parameters (`SignalClassList`, `AccessTier` as CSV) are real `FW_Subsets`/`FW_Combi`
     axes — a candidate carries a *set* of values, and the URL renders the CSV;
   - **`sortBy` is the second-order showcase**: a CSV of `{signal}{relationSign}{ordering}`
     triples is exactly a brace/`FW_Group` structure (§A.2–A.4) — a combination-of-combinations woven
     with a relation token, then grouped into one cell. This is where the "compound axis of freedom
     through `FW_(…)`" lands in a real parameter.
   - ordinal (`QualityTier`, `encoding`, dates) and presence (sentinel) axes as above.
3. **Be verified standalone.** Exhaustive live tests send all 576 optional-spec and all 729
   sentinel-spec URLs to the service. Every URL parses as HTTP 200 or a structured HTTP 400 (never a
   500), and every candidate accepted by its embedded model receives HTTP 200. The embedded models
   are deliberately conservative pipeline subsets; they are not claimed to equal the complete
   service 200-set.

Practically the complete service contract spans more richness than the heavy Core→Reader pipeline
can assemble via the statement-as-value bridge (multi-select list assembly and a second-order
`sortBy` cell are the hard parts). Verification is therefore **layered honestly**: the pure
classifier and sampled live-service test compare a full sidecar directly with the external oracle;
the full Bundle pipeline drives the six-axis conservative subset end-to-end through real
Core+Sieve+Reader+Executor; and the exhaustive live tests prove both authored specs generate
parseable requests whose embedded-model-valid subset is accepted by the external service.

### B.5 The System-Under-Test and the verification layers

**The SUT is a real, standalone, DB-free HTTP service** at
`$BUNDLE_SUT_ROOT/telemetry_catalog_service/` — stdlib `http.server`, random free port,
`GET`+`POST /api/catalog/lookup/{locator}?<full param set>`, a hardcoded catalog, `responseFormat=structured|markup` (rendered as JSON or XML). Its
`validate(params) -> broken[]` function encodes the **full 2.1 + invented-2.2 rule set** and is the
**oracle**: 200 + results for a valid query, 400 + the broken-rule list for an invalid one.

Verification (each clause of the task → a runnable assertion):

1. **Pure classifier** (DB-free): over the cartesian of the active parameters, the refactored sieve's
   `row_violations` removes **exactly** the set the oracle flags invalid (`removed==invalid`,
   `kept==valid`) — every new primitive provably fires; negative control rules out over/under-filtering.
2. **Live HTTP service** (DB-free): boot the standalone service; for each candidate assert
   *sieve-kept ⟺ HTTP 200* and *sieve-removed ⟺ HTTP 400 with matching broken rules*. **This is the
   literal "verify it against the System-under-test".**
3. **Whole-spec live interoperability** (DB-free): send all 576 + 729 authored forms to the service;
   each returns 200 or a structured 400, and every embedded-model-valid form returns 200.
4. **Full Bundle pipeline** (PG:5433 + Core/Reader jars): Core fills the sentinel space → `fw_final`;
   the refactored sieve deletes invalid rows; Reader assembles; Executor runs; only valid queries
   execute (FW_VAR=0) and every assembled URL is one the standalone service accepts.

### B.6 Back-compat & blast radius (the invariants this refactor must not break)

- `_eval_condition(cond, sel)` → `_eval_condition(cond, sel, orders=None)`; external 2-arg callers
  (tests) keep working; new leaves only trigger on new keys → existing conditions are byte-identical.
- New leaves are additive in `_COND_LEAF_OPS`, `_condition_error`, `_condition_sheets`, `describe`.
- `assert` is an additive branch in `row_violations`, `_referenced_sheets`/`_constraint_sheets`,
  `validate_sidecar`, `describe`.
- The Reader optional-compile path (`_condition_optional_absence_blocker`) marks every new
  ordinal/presence/subset op **absence-sensitive on optional sheets ⇒ fail-closed** (safe default; the
  new SUT doesn't use optional sheets, so this is belt-and-suspenders for the existing optional telemetry-catalog).
- Existing behavior remains under regression coverage; the current test inventory is recorded below.

### B.7 Increment ledger

`Inc0` this doc · `Inc1` engine + unit tests · `Inc2` standalone SUT service · `Inc3` Bundle SUT object
+ pure & live verification · `Inc4` full pipeline · `Inc5` GUI editor · `Inc6` schema/memory/handoff.
Each lands green before the next. See `docs/27` (table architecture / Reader assembly), `docs/07`
(constraints guide), `constraints/sidecar_schema.md` (the schema this extends).

### B.8 Verified results (2026-06-29)

- **Engine** (`constraints/sieve.py`): `orders`/`_rank`; leaves `present`, `ge/gt/le/lt`,
  `geSheet/gtSheet/leSheet/ltSheet`, `subOf/supOf`; the `assert` family; `orders` threaded through
  `_eval_condition`/`sieve_fw_final`/`impact_over_rows`/`stage_sieve`; fail-closed validation; ordinal
  bonds fail-closed in the optional-compile path. **Input spec first-class**: `fwgen` accepts
  `[orders]` + `assert`, `Spec.orders`, `emit_sidecar` carries it. `test_sieve_nested_bonds.py` (15).
- **Standalone SUT** (`$BUNDLE_SUT_ROOT/telemetry_catalog_service/`): stdlib HTTP, no DB,
  full ~28-param URL, 16 nested rules, structured/markup responses, random port; `selftest.py` = 20/20.
- **Acceptance** (`test_telemetry_catalog_full_e2e.py`, 4 tests):
  - **A** pure classifier == oracle over 4017 curated+random queries (every rule fires);
  - **B** live HTTP service: sieve-kept ⟺ 200, sieve-removed ⟺ 400 with **identical broken-rule sets**;
  - **C** full Core→Sieve→Reader→Executor on the first-class spec `telemetry_lookup_full.toml` (729 forms
    → sieve removes exactly 417 → **312** valid execute, all `FW_VAR=0`, well-formed URLs).
  - **D** exhaustive live interoperability: 729 well-formed requests → 448 HTTP 200 + 281 structured
    HTTP 400; all 312 candidates accepted by the embedded model receive HTTP 200. The companion
    optional-spec test covers all 576 requests (324 HTTP 200 + 252 structured HTTP 400), including
    all 300 embedded-model-valid candidates.
- **GUI** (`constraints/editor.py`): Python + JS mirror for `assert`/`orders`/new leaves
  (round-trip, `describe`, live preview with an ordinal `rank()`); the visual "only when" builder gains
  present/ordinal/subset ops (RU/EN). Round-trip + render tests green; `node --check` clean.
- **Current inventory (2026-07-18):** **649 tests collected**. The focused telemetry/constraint
  verification is green; this collection count is not a claim that the complete suite is green.
