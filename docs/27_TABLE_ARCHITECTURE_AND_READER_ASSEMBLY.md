# 27 — DB table architecture & Reader assembly (the basis for constraints "Face 2")

> **Code status (2026-07-21):** this remains the detailed storage/assembly reference. For the
> surrounding end-to-end stage order and current transport/security boundaries, pair it with the
> [current code audit](CURRENT_CODE_AUDIT_2026-07-21.md).

The constraint layer ("bonds" / the **Face‑2** draw‑the‑links surface, [07](07_CONSTRAINTS_GUIDE.md))
sieves `fw_final` **between Core and Reader**. To author and enforce bonds *correctly* you must know
**what the DB tables store** and **how the Reader reassembles a candidate** from them. This is the
verified reference — traced from live Core output and the Reader source
(`Reader_trunk/.../ComboGenerationPipeline.java`, `FinalOptMapOfComb.java`) and mirrored by
`constraints/sieve.py`.

## 1. What the tables store — **codes, not text**

The Core writes a **storage‑economical, integer‑coded, delta‑against‑baseline** form. Nothing stores
the authored value strings inline; every value is interned to an integer **code**.

| table | one row = | columns | holds |
|---|---|---|---|
| **`NumberToValue1`** | one value | `bigint` code, `value` text | the **code book**: every authored value ↔ a globally‑unique integer code (decode by lookup; whitespace‑stripped) |
| **`fw_final`** | one **mandatory** combination | `combi_id`, `combos<pos>_<SHEET> smallint[]` per sheet | per‑sheet **arrays of codes**. **Delta form:** an empty/NULL cell ⇒ inherit the base row's value; a non‑empty cell ⇒ this row's deviating code(s). A 1‑value slot is always baseline ⇒ always empty |
| **`fw_final_base_copy`** (or `…_base`) | the **base row** | same `combos*` columns | the **column shape** (all positions, mandatory **and** optional) + the **baseline codes** per position. The source of truth for what an empty `fw_final` cell means. **Optional columns here are NULL = absent.** |
| **`fw_optX`** | one **optional combination of size X** | same `combos*` columns | only the **optional** columns of that combo are populated (mandatory columns NULL). `fw_opt1` = each single optional action alone; `fw_opt2` = pairs; `fw_opt3` = triples; … Which sizes are materialized = `core.optional.includeOptionalCombiPairsToDBCSVList`. **Multiple `fw_optX` coexist.** |

A multi‑value slot (`FW_Combi(k>1)`, `FW_Subsets`, …) holds **several codes in one cell** — the array
carries every selected value's code.

> These tables are a **maximally compact** factored storage; the actual candidate is **algorithmically
> assembled in the Reader** (Yuri). `fw_final` is the mandatory part; optional actions live, factored
> out, in `fw_optX` and are joined in only at assembly time.

## 2. How the Reader reassembles a candidate (verified)

A candidate is built **by column position** as `base ∪ mandatory ∪ optional`, then decoded. Per
`ComboGenerationPipeline.java` (final‑only pass ≈ L457–503; cartesian pass ≈ L786–877) and
`FinalOptMapOfComb.getMergedMap()` (`mapOfComb1 ∪ mapOfComb2`):

```
clone fw_final_base_copy  →  position → base codes      (optional positions = NULL)
  override mandatory positions  ← this fw_final row's codes      (empty cell ⇒ keep base)
  override optional positions   ← one fw_optX row's codes        (cartesian pass only)
  DROP every NULL position                                       (absent — e.g. optional not in this combo)
  emit positions in column order:  <sheet prefix> + decode(code → NumberToValue1) … + <sheet ending>
```

Two passes produce the full space:

- **FINAL‑ONLY** — each `fw_final` row **alone** (`optLong = null`, optional positions stay NULL →
  dropped): the "no optional actions" candidate.
- **CARTESIAN** — each `fw_final` row **×** each `fw_optX` row, **for each** opt table: the candidates
  that include that optional combo.

```
candidates = |fw_final|  ×  ( 1[absent]  +  Σ_X |fw_optX| )
```

### 2.1 Core/Reader optional-property contract and count reconciliation

The similarly placed properties have different component ownership:

- `core.optional.includeOptionalCombiPairsToDBCSVList=1,2,...,N` tells **Core** which
  `fw_optX` tables to materialize.
- `reader.core.isOptCSVList=1,2,...,N` tells **Reader** which materialized tables to consume.
  The optional path also requires `reader.core.processIsOpt=true`; including both the absent and
  present branches requires `reader.core.processBothFinalAndOpt=true`.

For a normal Bundle launch, `bundle/stages.py` derives one `N` from the scenario and renders the
same `1..N` size list into the two run-private property files. Manually launching the components
requires the operator to keep the producer and consumer lists aligned. Historical values visible
in standalone/template property files are not cross-stage runtime evidence; the run-private
`core_cwd/fw.properties` and `reader_cwd/fw.properties` are authoritative.

Do **not** reconcile Core's `fw_final` count directly to Reader candidates when optional slots are
active. `fw_final` counts mandatory rows only; Reader reports fully assembled candidates. With four
one-valued optional slots, Core materializes `fw_opt1..4` with `4,6,4,1` rows, so:

```text
Reader expected = |fw_final| × (1 + 4 + 6 + 4 + 1)
                = |fw_final| × 16
```

The fail-closed chain is therefore:

```text
Reader actual = Reader stage expected runtime expansion
              = Executor processed = terminal outcomes
```

Core's mandatory count remains a separately checked positive/materialization invariant. A
2026-07-29 AI-platform regression incorrectly asserted `Core fw_final == Reader`; it rejected a
valid `160 × 16 = 2,560` run after every execution stage had succeeded. The reporter now consumes
the Reader stage's declared `expected` count and has a synthetic optional-expansion regression test.

The **column order is the candidate's sequence** — it is the `pos` that constraint gates
(`adjacent`, `within N`) operate on.

## 3. How constraints consume this (Face 2)

`constraints/sieve.py::sieve_fw_final` **reproduces the Reader's mandatory decode** and runs the bond
engine, then `DELETE`s violating `fw_final` rows — **the Core is untouched**, only the table it
produced is filtered.

- `build_maps_from_db` reads the **baseline from `fw_final_base_copy`** (not guessed), `code2val`
  from `NumberToValue1`, and the column order. Each `fw_final` row decodes to ordered placements
  `[{sheet, value, pos}]` exactly as the Reader would for the mandatory part.
- **Optional sheets are excluded from the baseline.** Their base column is NULL (absent) and the
  value is supplied only at Reader assembly. Therefore:
  - the sieve **never hallucinates** an optional value on a mandatory row (this was a fixed bug —
    inheriting the optional slot's first value made `forbid A=a1 with OPT=w1` delete *every* `a1`
    row; see [07 → "FW_Optional bonds"](07_CONSTRAINTS_GUIDE.md));
  - a bond that **references an optional sheet is DEFERRED**: it cannot be enforced by deleting a
    `fw_final` row (that would drop the mandatory combo for *every* optional choice). The sieve
    reports it under `deferred` + a warning and applies nothing. Its semantics are correct on the
    **assembled candidate** (`mandatory ∪ chosen optional combo`), where the engine enforces it —
    the same oracle/assembly tier other "needs the whole candidate" constraints use.
- **Multiple optional tables:** an **optional↔optional** bond can only fire when **both** optional
  actions are present in the **same** assembled candidate — i.e. a **size ≥ 2** combo
  (`fw_opt2`/`fw_opt3`), **never** `fw_opt1` (exactly one optional action present).

### What this means for authoring bonds

- A bond's `pos`/gate is the **column‑order position**; mandatory sheets have fixed positions, so
  gates between them are deterministic.
- Bonds **among mandatory sheets** are enforced at the **sieve** (cheap pre‑Reader pruning of
  `fw_final`).
- Bonds **touching an optional sheet** are **deferred to assembly**; the editor may author them and
  the sieve reports them deferred (it does not corrupt `fw_final`).
- Editor values must match the **interned, whitespace‑stripped** strings (the same `NumberToValue1`
  form the sieve decodes).

## 4. Enforcing optional bonds at assembly (per-candidate bond filter)

A deferred optional bond is **enforced at Reader assembly — scalably**, without porting the
constraint engine into Java. The sieve (Python) **compiles** each deferred bond into a compact
per-bond spec: polarity, a precomputed gate flag, the referenced **sheet names**, and the small set
of `NumberToValue1` **code-tuples** for which it holds — `pairs`, `sets`, and `when` all collapse to
that one tuple set (`constraints/sieve.optional_bond_specs`). It writes them to
`<work>/optional_bonds.txt`; the Reader (`OptionalBondFilter`) loads them once and **evaluates them
per assembled candidate** in the cartesian pass — pure `short`-set membership over the candidate's
per-sheet code arrays — and drops a violating candidate **before** the expensive byte assembly + I/O.

**Why it scales.** The file is `O(bonds × each bond's own tuple space)` — *independent of the
candidate count*; there is no precomputed per-candidate skip-list, and the Reader's memory is
`O(bonds)`.

Design properties:

- **Opt-in, zero cost when off.** Gated behind a single null check; with no bonds file — *any*
  non-sieving run — the cartesian path is unchanged and the **FINAL-only pass is byte-identical /
  untouched**. Verified by a control run: same rebuilt jar, no bonds file → every candidate emitted.
- **No constraint engine in Java.** `pairs`/`sets`/`when` all reduce *in Python* to integer
  code-tuples; the Reader only does `short`-set membership. Matching is on **codes** (no per-candidate
  decode), keyed by **sheet name** (the assembled-candidate map's keys — verified, not the
  `combos*` column names).
- **The gate is precomputed once** (the referenced sheets sit at fixed columns).
- A bond that can't be compiled (e.g. a `when` with no param values) stays deferred-only.

Touch points: `constraints/sieve.py` (`optional_bond_specs`, `_holding_value_tuples`),
`bundle/stages.py` (`stage_sieve` writes `optional_bonds.txt`; `stage_reader` sets
`reader.constraints.bondsFile`), `Reader_trunk/.../OptionalBondFilter.java` (parse + per-candidate
evaluate), `ComboGenerationPipeline.java` (load once + per-candidate check), `ReaderConfig.java`
(the property).

## 5. Verified by tests

- `test_face2_all_link_variations_through_real_bundle` — every link variation on a **verb‑rich**
  `fw_final` (FW_Combi(1)/Combi(2)/Permut/PermutR/Subsets), cross‑checked vs the pure engine + closed
  forms + actual delete.
- `test_optional_*` + `test_multiple_optional_tables_through_real_bundle` — real Core →
  `fw_opt1/2/3` coexisting, baseline excludes every optional sheet, `base_copy` optional cols NULL,
  the sieve defers optional bonds, and a **real `base ∪ final ∪ opt3` assembly** fires an
  optional↔optional bond that never fires on a `fw_opt1` candidate.
- `test_optional_bonds_enforced_in_reader_at_assembly` — end-to-end through the **rebuilt Reader**:
  the compiled bond spec is compact (one line per bond), the per-candidate filter skips exactly the
  engine-forbidden candidates (cross-checked against `row_violations` on every real assembled
  candidate; none leak, exact count), and a control run with the bonds file removed re-emits **every**
  candidate (proves the no-op / non-breaking path).

See also: [07_CONSTRAINTS_GUIDE.md](07_CONSTRAINTS_GUIDE.md),
[`constraints/sidecar_schema.md`](../generator_trunk/constraints/sidecar_schema.md),
[09_READER_EXECUTOR_AND_RESULTS.md](09_READER_EXECUTOR_AND_RESULTS.md),
[26_PLAN3_THREE_FACES_UX.md](26_PLAN3_THREE_FACES_UX.md).
