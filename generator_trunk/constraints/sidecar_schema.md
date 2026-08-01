# Constraint sidecar — schema (v1)

The **sidecar** is the single declarative artifact the constraint layer ("bonds") speaks. Every
authoring surface — the spec's `[[params]]`/`[[constraints]]` tables (`fwgen.emit_sidecar`), the
bond-matrix, the graph/threads editor, the Blockly `when` builder, and the unified `editor.html` —
compiles to *this* shape, and the sieve (`constraints/sieve.py`) is the *only* thing that consumes
it. It is written to `sidecar.json` in the run/scratch dir for the record and for a standalone
re-run.

```jsonc
{
  "version": 1,
  "params": { "<sheet>": { "<value>": { "<attr>": <number|str|bool>, ... }, ... }, ... },
  "constraints": [ <constraint>, ... ]
}
```

## `params` — value metadata (only needed for `when` predicates)

`params[sheet][value]` is a flat bag of named attributes for one value-cell (the "atom's"
properties, in the chemistry analogy). Authored in a spec as repeated `[[params]]` tables:

```toml
[[params]]
sheet = "REGION"
value = 'region = "r2"'   # the EXACT, whitespace-stripped value string the sieve decodes
cost  = 2                 # -> params["REGION"]['region = "r2"'] = {"cost": 2}
```

Inside a `when` string every attribute is reachable as `Sheet.attr`; two attributes are always
injected automatically: **`value`** (the value string) and **`pos`** (its position in the assembled
sequence). A pairs-only sidecar needs no `params` at all.

## `constraints[]` — the bonds

A normal bond is a relation over the values of **two or more** referenced
sheets. A well-formed constraint carries exactly one primary body:
`pairs` (enumerated tuples), `sets` (Many:Many cross product), `when`
(predicate), `mapping` (dependent allowed set), or `assert` (condition-AST
relation). `condition` is a contextual guard, not a sixth body. An `assert`
is deliberately allowed to be unary.

| field | type | meaning |
|---|---|---|
| `id` | str | stable identifier; appears in every per-rule statistic and in `explain` |
| `sheets` | `[str, …]` | the **≥2** referenced sheets (arity). Optional — derived from the `pairs` keys or `sets` keys when omitted; useful to fix order for a `when` bond |
| `pairs` | `[{sheet: value, …}, …]` | **enumerated (disjunction)** form: each entry is one full tuple over `sheets`. A row trips the rule if some gated combination equals an entry across *all* referenced sheets. `[{A:a1,C:c1},{A:a3,C:c2}]` = **2** specific combos |
| `sets` | `{sheet: [value, …], …}` | **Many:Many (cross product)** form: a value SET per sheet; the rule's tuple space is their **cartesian product**. A row trips it if some gated combination has *every* sheet's value inside that sheet's set. `{A:[a1,a3], C:[c1,c2]}` = **4** combos in one rule — distinct from `pairs` (a disjunction). Works for 2+ sheets (n-ary) |
| `when` | str | **predicate** form: a boolean expression over `Sheet.attr` (see safety below). A row trips the rule if some gated combination makes it evaluate per `polarity` |
| `mapping` | obj | **dependent allowed-set** form (the `key={v1:v2,v1:v3}` shape): `{source, target, allow}` where `allow` maps a source value → the target values it permits. A row trips it when, for the chosen source value, the target selection escapes that value's allowed set. A *require-style* relation (a source value absent from `allow` is unconstrained) |
| `assert` | obj | **relation/assert** form: a `condition`-AST **as the bond body** (not just a gate), evaluated over `sel`. With `polarity:"require"` (the default for `assert`) the row trips when the assertion is **false**; with `"forbid"` when it is **true**. This is the home of the *nested* value-dependencies — ordinal (`geSheet`, `ge`), presence (`present`), subset (`subOf`) — composed under `all`/`any`/`not`. Exempt from the ≥2-sheet arity floor (a deliberate rule, e.g. a unary threshold). |
| `gate` | obj | positional restriction (see below); `{}` = any co-occurrence |
| `condition` | obj | **contextual guard** (see below): a boolean over *other* columns' values that gates whether this bond applies at all — "only in this context". Absent ⇒ unconditional |
| `polarity` | `"forbid"` \| `"require"` | default `"forbid"` |
| `desc` | str | one human sentence (the always-show-words UX) |

`pairs` vs `sets` is the disjunction/cross-product distinction: to forbid *exactly* `(a1,c1)` and
`(a3,c2)` use `pairs`; to forbid *every* pairing of `{a1,a3}` with `{c1,c2}` use `sets`.

### `condition` — the contextual / conditional tier

Any bond (`pairs`/`sets`/`when`/`mapping`) may carry a `condition`: a small boolean AST over the
row's **per-sheet selections** (`sel`: sheet → list of chosen values; length 1 for an ordinary slot,
>1 for a multi-select `FW_Subsets` slot). It is evaluated **once per row**; if false the bond is
*inert* on that row (so a `forbid` becomes "never together **when** …" and a `require` becomes "only
together **when** …"). It also counts toward **arity**, so a single-target bond gated by a condition
over another sheet is a valid bond. This re-expresses, on the flat `fw_final`, the staged
interconnection the Core builds via `FW_(…)` brace-joins of prior result tables (what is legal
downstream depends on an upstream result) — the provenance is gone but every column's value survives
in the row. Grammar:

| leaf | holds when |
|---|---|
| `{sheet:S, eq:v}` / `{ne:v}` | S's selection is exactly `[v]` / is not |
| `{sheet:S, has:v}` / `{hasnt:v}` | the selection contains / lacks `v` |
| `{sheet:S, in:[…]}` / `{nin:[…]}` | selection ⊆ set / selection ∩ set = ∅ |
| `{sheet:S, hasAny:[…]}` | selection ∩ set ≠ ∅ |
| `{sheet:S, eqSheet:T}` / `{neSheet:T}` | selection(S) == / != selection(T)  (cross-column `VX=VY`) |
| `{sheet:S, count:n}` / `{countGe:n}` / `{countLe:n}` | `|selection|` tests (multi-select cardinality) |
| `{sheet:S, present:true}` / `{present:false}` | S **is** selected (≥1 value) / **is** absent (empty). *(In the `(absent)`-sentinel model use `ne`/`eq <sentinel>` instead.)* |
| `{sheet:S, ge:c}` / `{gt:c}` / `{le:c}` / `{lt:c}` | **ordinal vs a constant**: S's value ranked (via `orders`) `≥ / > / ≤ / <` `rank(c)`. **Vacuous (true) if S absent.** |
| `{sheet:S, geSheet:T}` / `{gtSheet:T}` / `{leSheet:T}` / `{ltSheet:T}` | **ordinal cross-field**: the whole S selection vs the whole T selection by rank — `geSheet` ⟺ `min(rank S) ≥ max(rank T)`, `leSheet` ⟺ `max(rank S) ≤ min(rank T)` (single-select = scalar compare). **Vacuous if either side absent.** |
| `{sheet:S, subOf:T}` / `{supOf:T}` | set(S) ⊆ / ⊇ set(T)  (cross-field subset — e.g. `sortBy ⊆ SignalClass`) |
| `{all:[…]}` / `{any:[…]}` / `{not:…}` | AND / OR / NOT |

**Examples.** Conditional forbid: `{sets:{SignalClass:["Radar"]}, condition:{sheet:"DatasetFamily",
eq:"Mobility"}}` = forbid Radar when the dataset family is Mobility. Specific-combination context (the
`KeyXY={(VX=Y)and(…)}` shape): `{sets:{encoding:["zarr"]}, condition:{all:[{sheet:"DatasetFamily",
eq:"Climate"},{sheet:"SignalClass",eq:"Radar"}]}}`. Dependent allowed-set via `mapping`:
`{mapping:{source:"DatasetFamily", target:"SignalClass", allow:{Mobility:["Trajectory"],
Climate:["Radar","WeatherStation"]}}}` — equivalent to one conditional-`require` per source key.
Capture ranges (`CaptureStart ≤ CaptureEnd`) stay in the `when` tier over an ordinal param, not `condition`.

### `orders` — ordinal ranks (top-level, sibling of `params`/`constraints`)

The ordinal leaves (`ge/gt/le/lt`, `geSheet/gtSheet/leSheet/ltSheet`) need a rank per value. Declare it
per sheet:

```jsonc
"orders": {
  "QualityTier": ["bronze", "silver", "gold", "platinum", "diamond"], // a LIST → rank = index
  "encoding":    ["csv", "parquet", "zarr"],
  "CaptureStart": "numeric",                                         // → rank = float(value)
  "CaptureEnd":   "numeric",                                         // → rank = float(value)
  "SourceTimestamp":   "date"                                  // → rank = ISO yyyy-mm-dd
}
```

A value not in a declared list, a non-number under `"numeric"`, a non-ISO under `"date"`, or an
ordinal op on a sheet with **no** declared order → a **fail-closed** validation error (never a silent
lexicographic guess). Authorable in a spec as a top-level `[orders]` table; flows verbatim into the
sidecar (`fwgen.emit_sidecar`). Cross-field ordinal compares the whole left selection vs the whole
right (`min`/`max` of ranks). See `docs/28_SECOND_ORDER_AXES_AND_NESTED_BONDS.md`.

### `assert` — examples

```jsonc
{"id":"capture_range", "polarity":"require", "assert":{"sheet":"CaptureEnd","geSheet":"CaptureStart"}}
{"id":"indexed_xor_provisional","polarity":"forbid","assert":{"all":[{"sheet":"IndexedTimestamp","present":true},
                                                                    {"sheet":"provisional","present":true}]}}
{"id":"sort_subset",   "polarity":"require", "assert":{"sheet":"sortBy","subOf":"SignalClass"}}
{"id":"zarr_quality",  "polarity":"require", "assert":{"sheet":"QualityTier","ge":"gold"},
                      "condition":{"sheet":"encoding","eq":"zarr"}} // zarr ⇒ QualityTier ≥ gold
```

### Polarity

- **`forbid`** (default for `pairs/sets/when/mapping`; an `assert` defaults to **`require`**): a gated tuple that **holds** removes the row. *"never together."*
- **`require`** (the "искомый"/sought form): a gated tuple that **does not hold** removes the row —
  i.e. every gated combination is required to hold. *"only together."*

### Gate (positional) — generalized to n-ary

`pos` is the index of a placement in the assembled output sequence (slot order; an ordered
`FW_Permut` sheet's array order *is* the sequence). For the *k* placements a bond selects:

| gate | meaning (k placements) | reduces (k=2) to |
|---|---|---|
| `{}` | any co-occurrence | any co-occurrence |
| `{"adjacent": true}` | a **contiguous run**: `max(pos) − min(pos) == k − 1` | `\|pos_x − pos_y\| == 1` |
| `{"within": N}` | a **window of N**: `max(pos) − min(pos) ≤ N` | `\|pos_x − pos_y\| ≤ N` |

Two placements that share a position are never paired (a sheet at one slot is one placement).

### Arity

- For `pairs`/`sets`/`when`/`mapping`, **≥2 referenced sheets** means
  the bond is evaluated. Two is the common binary case; three or more is n-ary.
  Sheets mentioned by `condition` count toward this arity, so one target plus
  one contextual sheet is valid.
- A non-`assert` rule with **<2 referenced sheets** is unsupported:
  `validate_sidecar` reports it and the sieve skips it. `--strict` /
  `strict=True` turns the report into a hard error.
- An `assert` is evaluated with one or more referenced sheets. A zero-sheet
  assertion is invalid. This exception is intentional so a unary threshold or
  presence assertion is expressible without disguising it as a bond.

### `when` safety

Evaluated in a restricted sandbox (`sieve._eval_pred`): no builtins, a whitelist of
`abs/min/max/round/len/int/float/bool`, and a reject-regex banning
`__ / import / lambda / := / exec / eval / open / globals / locals`. The sieve operates on **finite
value metadata only** — it does not execute candidates. Constraints that depend on runtime behavior
belong in the Executor oracle (the TAIL `FW_VAR` verdict), not here.

## Examples

**Enumerated pair (binary):**
```json
{ "id": "ban_a11_c11", "polarity": "forbid", "sheets": ["A", "C"],
  "pairs": [{ "A": "a11", "C": "c11" }], "gate": {},
  "desc": "a11 never together with c11" }
```

**Predicate (binary, with params):**
```json
{ "id": "no_like_charge_adjacency", "polarity": "forbid", "sheets": ["A", "C"],
  "when": "A.charge * C.charge > 0", "gate": { "adjacent": true },
  "desc": "A next to C is forbidden when their charges share a sign" }
```

**Enumerated triple (n-ary):**
```json
{ "id": "ban_a1_b1_c1", "polarity": "forbid", "sheets": ["A", "B", "C"],
  "pairs": [{ "A": "a1", "B": "b1", "C": "c1" }], "gate": {},
  "desc": "the a1+b1+c1 triple is forbidden" }
```

**Required pair (the "sought" polarity):**
```json
{ "id": "auth_needs_tls", "polarity": "require", "sheets": ["AUTH", "TRANSPORT"],
  "pairs": [{ "AUTH": "token", "TRANSPORT": "tls" }], "gate": {},
  "desc": "a token auth is only kept when paired with TLS transport" }
```

**Many:Many cross product (forbid every pairing of two value sets):**
```json
{ "id": "ban_legacy_regions", "polarity": "forbid", "sheets": ["AUTH", "REGION"],
  "sets": { "AUTH": ["basic", "none"], "REGION": ["eu", "uk"] }, "gate": {},
  "desc": "neither basic nor none auth is allowed in either the EU or UK region (2×2 = 4 combos)" }
```

**Many:Many required ("sought" — keep only these groupings, n-ary):**
```json
{ "id": "premium_only", "polarity": "require", "sheets": ["TIER", "REGION", "TRANSPORT"],
  "sets": { "TIER": ["gold", "platinum"], "REGION": ["eu", "us"], "TRANSPORT": ["tls"] }, "gate": {},
  "desc": "only gold/platinum tiers, in EU/US, over TLS, are kept" }
```

## How the sieve consumes it (the boundary it sits on)

```
author → sidecar.json → SIEVE (between Core and Reader) → deletes violating fw_final rows
```

In a live run `sieve_fw_final` decodes each `fw_final` row into ordered placements
`[{sheet, value, pos}, …]`, runs `row_violations` against the sidecar, and `DELETE`s the violators
by `combi_id` — **the Core is untouched**, only the table it produced is filtered. The decode is a
**delta-against-baseline** form: an empty `combos*` cell inherits the slot's baseline (first) value,
a non-empty cell carries the deviating value's code (decoded via `NumberToValue1`). See
`07_CONSTRAINTS_GUIDE.md` for the CLI (`constraints explain` / `dry-run` / `--sieve`), and
`docs/27_TABLE_ARCHITECTURE_AND_READER_ASSEMBLY.md` for the full table architecture (`fw_final` /
`fw_final_base_copy` / `fw_optX` / `NumberToValue1`) and the Reader's `base ∪ mandatory ∪ optional`
candidate assembly that the sieve mirrors.

**FW_Optional sheets are the exception:** their value is factored into
`fw_optX` and assembled in the Reader, so an empty optional cell means
*absent* (no baseline is inherited). A bond referencing an optional sheet
cannot be enforced on `fw_final` and is **deferred** (reported under
`deferred` with a warning). The launcher compiles supported deferred rules
into compact Reader `OptionalBondFilter` lines, which are evaluated per
assembled candidate.

Plain enumerable `pairs`/`sets`/`when` bodies use the compact tuple form.
Contextual `condition`, `mapping`, and `assert` bodies require finite
referenced domains and are compiled by enumerating their violating tuples.
Ordinal operations and absence-sensitive optional predicates are not generally
compilable at that boundary. A blocker must fail the launch closed; it must not
silently drop or weaken the authored rule. See `07_CONSTRAINTS_GUIDE.md` →
"FW_Optional bonds".
