# Core — quick understanding for an AI cold-start

> **Read this first when you're asked to touch `Core_trunk/`.** It is the fast map: the mental model,
> where each load-bearing class lives, the data representation, the verbs, the two second-order
> operators, the stores, and the traps that have cost real time. Then read the source for the part you
> touch — **do not guess Core internals; cite the `.java`** (Yuri challenges unverified claims).
>
> Companion docs (authoritative, verified): the verb vocabulary is **`../ZEN_OF_COMBINATORICS.md`**;
> the table architecture + Reader assembly is **`../docs/27_TABLE_ARCHITECTURE_AND_READER_ASSEMBLY.md`**;
> the output invariants are **`README_CANONICAL_TRUTH.txt`**; the deeper-order/nesting study is
> **`../docs/28_SECOND_ORDER_AXES_AND_NESTED_BONDS.md`**.

---

## 1. The one-paragraph model

The Core is a **combinatorial GENERATOR**, not a constraint language. Its standalone input can be
XLSX, JSON, TOML, or YAML (the Bundle normally supplies generated XLSX). The parsed workbook is an
**`FW_Seq`**: an ordered list of operations, one row per sheet. Each row applies a **verb** to its
sheet's values and produces a **result table**; the mandatory result tables are **Cartesian-combined
into `fw_final`**. Everything travels as **16-bit `Short` codes**, never value text. The Core has **no
verb to forbid** a value-combination (forbidding is a *separate* layer — the Python sieve, see §10).
Two **second-order** operators lift it above a flat product: the **brace `FW_(…)`** (a JOIN of two
prior result tables, nestable to 3rd order and beyond) and **`FW_Group`** (re-combine one prior
result's rows as atoms + regex-rewrite). A third axis, **`FW_Optional`**, makes *presence* a degree of
freedom (`× (one value OR absent)`), assembled later in the Reader.

## 2. The 30-second lifecycle (who calls whom)

```
Bootstrap.main                              # entry; AppConfig.load(); → MainRefactored.main
 └─ MainRefactored.main
     ├─ WorkbookParser → ParsedWorkbook     # sheets, value→Short code maps, FW_Seq rows
     ├─ SeqParser.parse(workbook, …, cfg.seq)
     │     # splits sheets into mandatory / optional(FW_Optional) / excluded(FW_Exclude) maps;
     │     # parses each row's verb(s); resolves NESTED braces; auto-promotes a lone combo verb to dual
     ├─ new SheetWorker(...).processAll(...) # ONE virtual thread per sheet; applies each row's verb,
     │     #   writes fw_<key> (+ dual fw2_<key>); runs FW_Group; the brace runs via BraceOperationHandler
     ├─ (move FW_Optional keys → key2tableMapOptional)
     └─ new FinalTableAssembler(...).assemble(key2tableMap, key2tableMapOptional, …)
           ├─ runFnlThread  → fw_final  (+ fw_final_base / _base_copy baseline; producer/consumer COPY)
           └─ runOptsThread → fw_opt1..N (optional combos of each size; cartesian)
# fw_final + fw_optX are COMPACT, factored storage. The Reader_trunk ASSEMBLES the actual candidates
# (clone base row → override per-position codes from a fw_final row and a fw_optX combo → drop nulls).
```

## 3. Where things live (load-bearing classes)

| file | what it does | read it when… |
|---|---|---|
| `SeqParser.java` | turns `FW_Seq` rows into the mandatory/optional/exclude maps + per-sheet directive lists; **nested-brace resolution** (`priorFwBraceTargets`, `~FWN`/`~FWG`); auto-promote-to-dual | changing how a verb/flag is recognized, or brace nesting |
| `SheetWorker.java` | `processAll` (vthread per sheet) → `processSheet` → `runDirective`; runs the generators; **`FW_Group` + `FW_ReplaceRE` + `FW_Separator`**; writes `fw_`/`fw2_` | changing per-sheet generation, group/separator/replace |
| `BraceOperationHandler.java` | the brace `FW_(start,_,E1,rel,E2,_,end,sep,mult)` JOIN of two prior result tables; cardinalities `1:1 1:N M:1 M:M M:N`; weaves rel/sep/start/end | changing join semantics |
| `combinatorics/*G.java` | the generators: `CombinationsDistinctG`, `CombinationsWithRepetitionsG`, `PermutationsSimpleG`, `PermutationsWithRepetitionsG`, `SubsetsG`, `CartesianProductG` (dpaukov / ghYura-parallel libs) | changing a verb's enumeration |
| `FinalTableAssembler.java` | builds `fw_final` (baseline + producer/consumer COPY) and `fw_opt1..N` (optional cartesian); final distinctify | changing fw_final/optional assembly |
| `MainRefactored.java` | orchestration (above), the HeapWatchdog ABORT wiring | changing the top-level flow |
| `store/IntermediateTableStore.java` (+ `Pg…`, `Java…`, `Switchable…`) | where `fw_/fw2_` rows live: PG tables OR in-JVM lists, hot-swappable on heap pressure | changing storage/drain |
| `helpers/TableDataDistinctor*.java` | `SELECT DISTINCT` determinism (MIN(combi_id) ordering) | a distinct-count drift |
| `models/NumberToValue1.java`, `FW`, `FW2` | the `Short`-code ↔ value table; the row entities | decoding codes back to values |
| `Bootstrap.java`, `config/AppConfig.java`, `fw.properties` | entry + config flags (storage mode, precompute, optional list, distinctify) | flipping a behavior flag |

## 4. The data representation (critical)

- Every value is a **`Short`** (16-bit int code). The combinatorics store is `Map<Short, List<Short>>`
  (`SheetWorker.java`). A produced combination is a **list of codes**. `NumberToValue1` is the
  code→value-text table; the **Reader** turns codes back into bytes.
- Tables: **`fw_<key>`** = a sheet's first-order result; **`fw2_<key>`** = its *dual / sub-combo* output
  (what a brace or `FW_Group` consumes — a lone combo verb is **auto-promoted to a dual** so `fw2_` is
  populated, else joiners read 0 rows). **`fw_final`** = the mandatory Cartesian (stored as a
  *delta against `fw_final_base`*: an empty `combos*` cell ⇒ the slot's **baseline = first value**).
  **`fw_optX`** = optional combos of size X (one populated column per size-1 row, …).
- ⚠ `FW_ReplaceRE` rewrites the **code-string** (e.g. `"[47, 48]"`), NOT value text, and the result must
  stay integer-parseable (else `NumberFormatException` → row dropped). See ZEN's 2026-06-12 correction.
  Both failure modes are silent by default; `core.replace.*` in `fw.properties` makes them visible or
  fatal at your choice, changing nothing unless set (`AppConfig.ReplacePatternPolicy` &c.,
  `SheetWorker.applyReplaceAuthoringPolicies` / `reportReplaceOutcome`).
  See [../docs/41_FW_REPLACERE_POLICIES.md](../docs/41_FW_REPLACERE_POLICIES.md).

## 5. The verbs (pointer) and the two second-order operators

First-order verbs (one axis of freedom each) — full table in **`../ZEN_OF_COMBINATORICS.md`**:
`FW_Combi(k)` / `FW_CombiR(k)` / `FW_Permut[(k)]` / `FW_PermutR(k)` / `FW_Subsets[_EXACT/RANGE/…]` /
`FW_Cartes(OTHER)`; modifiers `FW_Separator(GLUE)`, `FW_Concatenator=`.

Second-order (combine *prior result tables* — this is where "deeper stages" live):
- **Brace `FW_(…)`** — a binary JOIN of two prior results (operands carry `FW_Exclude`; read `fw2_`
  else `fw_`). It **nests**: an operand position holding `FW_(…)` is resolved by `SeqParser` to the most
  recent prior brace target (`~FWN` plain / `~FWG` grouped-flatten) → an arbitrarily deep tree of joins
  = **3rd order and beyond**. `mult` ∈ `1:1|1:N|M:1|M:M|M:N`; `rel`/`sep`/`start`/`end` weave tokens.
- **`FW_Group` (+ `FW_ReplaceRE`)** — a unary re-combination of one sheet's *prior result rows* as atoms
  (combinations of combinations), then regex surgery on the code-string. Source rows are **content-sorted
  first** (determinism — §8).

`FW_Optional` is the orthogonal *present ⊕ absent* axis: `fw_final × Π(nᵢ+1)`, assembled in the Reader.

## 6. Stores (storage mode)

`fw_/fw2_` rows live behind `IntermediateTableStore`: **`PgIntermediateTableStore`** (real PG tables) or
**`JavaIntermediateTableStore`** (in-heap lists), chosen by config. **`SwitchableIntermediateTableStore`**
starts in Java and, on a HeapWatchdog HIGH/CRITICAL event, **drains Java→PG and swaps** mid-run
(`SheetWorker.coordinateDrain` quiesces sheets at a barrier). Most code is mode-agnostic via the store
interface (`isPgBacked()` gates the few divergent paths, e.g. the brace operand prep).

The packaged standalone Core defaults and the Bundle's generated Core configuration are not the
same operational profile: standalone use is PostgreSQL-oriented, while the Bundle template selects
the in-memory Java intermediate store. Always inspect the resolved `fw.properties` rather than
assuming one mode.

## 7. Output invariants (don't "fix" a number blindly)

On `test14042026.xlsx`, with default distinctify, the engine **must** produce `fw_final = 4,644,864`
and `fw_opt4 = 33,674,483`, invariant across storage mode / PG version / JDK / lib version. A different
number means the **input changed**, a **distinctify flag changed**, or a **regression** — investigate,
don't overwrite `README_CANONICAL_TRUTH.txt`. (The historical `34,368,597` was a *different valid
ordering* of the same emissions, closed by the Iter4 Step-10 content-sort.)

## 8. Determinism — the one subtle place

`FW_Group`'s `SubsetsG` enumerates source rows **by INDEX** and concatenates in index order, so the
output depended on store/PG-plan ordering. **Iter4 Step-10 content-sorts the source rows** (lex by combo
content) so the result is a pure function of the data. `FW_Group` is the most order-sensitive verb; rely
on the content-sort.

## 9. Traps that cost real time

- **Lone combo verb won't join.** A single `FW_Combi(k)` writes only `fw_`; joiners read `fw2_`. The
  Core auto-promotes to a dual — but a bare `FW_Permut` (no parenthesized dual) or a Cartes/Group/Separator
  row is **not** promoted. If a brace reports 0 rows, the operand's `fw2_` is empty.
- **`seq_extra` (brace row) must be a TOP-LEVEL toml key** — after a table it binds to that table and is
  silently dropped (the `fw_final` then shows the un-joined placeholder).
- **Brace operands need `FW_Exclude`**; without it the Core double-counts the operand in the Cartesian.
- **`FW_Separator`/`FW_ReplaceRE` land in `fw2_`** (the sub-combo a join/group reads), invisible to the
  plain `fw_final` Cartesian — pair them with a brace or `FW_Group`.
- **`FW_ReplaceRE` is a code-string transform, not text** (§4) — a textual replacement is a silent no-op
  (or drops the row).
- **No data cell may start with `FW_`** (parsed as a directive); a TAIL setting `FW_VAR` must lead with
  another statement.
- **`estimate_core_combos` ignores brace/`FW_Group`** effects → the estimate is the mandatory product;
  the real `fw_final` is the second-order size (`bundle_run` warns, doesn't fail).
- **A sheet whose table ends up empty is dropped** from the key maps → `fw_final` silently MISSES that
  column (a partial result). Watch the `[fail-honest]` warn in `SheetWorker`.
- **Core owns and recreates its working schema objects.** A run can drop/recreate framework tables,
  and final assembly removes intermediate `fw_*` tables (including the working final-base table)
  when they are no longer needed. Use a dedicated run database, never an application database.
- **Standalone Reader auto-launch is fire-and-forget.** Core can spawn Reader after generation, but
  that launch is not an end-to-end success contract. The Bundle launcher supplies the journalled,
  checked lifecycle when stage completion matters.

## 10. What the Core does NOT do

It does **not** forbid value-combinations. Allowed/forbidden **bonds** are a separate, non-invasive
layer: the **Python sieve** (`../generator_trunk/constraints/sieve.py`) runs **between Core and Reader**
and deletes violating `fw_final` rows (and compiles optional bonds for the Reader). The brace is
*generative* (it ADDS joined rows), never a filter. Constraint shapes (pairs/sets/when/mapping/condition
+ the new ordinal/presence/subset/`assert` tier) live in `../generator_trunk/constraints/sidecar_schema.md`.

## 11. How to look / verify

- Build: `mvn -o -DskipTests package` in `Core_trunk` (shaded jar in `target/`).
- End-to-end on this machine: `cd ../generator_trunk && python3 bundle_run.py <spec>` (drives Generator
  → Core (Java+PG) → Sieve → Reader → Executor → Analyzer). Dev PG on `:5433`.
- Inspect a run: the `fw_<k>`, `fw2_<k>`, `fw_final`, `fw_opt*` tables in the run DB; `NumberToValue1`
  for the code→value map.
- Demos that exercise the second-order operators: `../generator_trunk/constraints/.../brace_demo`,
  `brace_full_demo`, `group_sep_demo` (listed at the end of `../ZEN_OF_COMBINATORICS.md`).

*Reconciled 2026-07-21 — verified first-hand against `SeqParser` / `BraceOperationHandler` /
`SheetWorker` / `SubsetsG` / `CartesianProductG`, and the orchestration of `MainRefactored` /
`FinalTableAssembler` / `store/*`.*
