# 07 — Constraints Guide (the "bonds" layer)

Constraints are the **bonds** layer: a relation-level pass (`constraints/sieve.py`) between Core and
Reader that **deletes invalid combinations from `fw_final`** before expensive reconstruction and
execution. Constraints are **never** expressed with `FW_Exclude` or a brace (those are generative —
they add rows); forbidding a value-combination is the sieve's job.

> The DB **table architecture** the sieve reads (`fw_final`, `fw_final_base_copy`, `fw_optX`,
> `NumberToValue1` — integer codes, delta-against-baseline, factored optional) and the **Reader
> assembly** that reconstructs a candidate from them are documented in
> [27_TABLE_ARCHITECTURE_AND_READER_ASSEMBLY.md](27_TABLE_ARCHITECTURE_AND_READER_ASSEMBLY.md).
> Read it to understand *why* the sieve decodes the way it does and why optional bonds are deferred.

## Sidecar: params + rules

A spec declares value attributes (`[[params]]`) and rules (`[[constraints]]`). The sieve builds a
sidecar `{version, params, constraints}` (also emitted to `sidecar.json` in the run dir).

```toml
[[params]]
sheet = "MODE"
value = 'MODE = "strict"'
tier = 2
[[params]]
sheet = "PAYLOAD"
value = 'PAYLOAD_KIND = "unicode"'
unicode = 1

[[constraints]]
id = "strict_ascii_ingress_policy"
sheets = ["MODE", "PAYLOAD"]
when = "MODE.tier == 2 and PAYLOAD.unicode == 1"
gate = {}
desc = "strict ingress policy excludes Unicode payloads before expensive execution"
```

A row matching `when` (here: strict mode **and** a Unicode payload) is removed. The "chemistry"
analogy (value parameters + a formula + adjacency) maps to ordinary terms: value attributes,
predicates, compatibility rules, pre-execution pruning.

## explain — list rules + quantitative effect (non-destructive)

```bash
python3 bundle_run.py constraints explain tryout_own/spec --db <populated-core-db>
```

Reports, per rule: the rule text, referenced sheets/params, **rows it would remove**, plus the
impact line `scanned / unique_removals / overlap / retained`, **sample rejected combinations**, and
**sample retained boundary cases**. Verified on the bounded 96-row Core DB:

```
strict_ascii_ingress_policy: would remove 24 row(s)
impact: scanned 96  unique_removals 24  overlap 0  retained 72
sample rejected combinations: …    sample retained (boundary) cases: …
```

`explain` requires a populated Core DB (`--db`). Without one it lists the rules only.

## dry-run — count effect, deletes nothing

```bash
python3 bundle_run.py constraints dry-run tryout_own/spec --db <populated-core-db>
```

Reports the same `scanned/unique_removals/overlap/retained` statistics **and changes nothing**:
verified the `fw_final` row count is identical before and after (96 → 96). The destructive sieve
stage (run with `--sieve`) records the **same** statistics and reduces the table in place (96 → 72).

## Per-rule / overlap statistics

- `matched[rule_id]` — rows each rule matched.
- `overlap` — rows removed by more than one rule (counted once in `unique_removals`).
- `unique_removals` — distinct rows removed.
- `retained` — rows left after the sieve.

The actual sieve stage prints each rule's `matched` count and the overlap, then the new `fw_final`
size — so the explain/dry-run estimate reconciles with the real run.

## Examples & limitations

- The flagship's single rule removes exactly 24 of 96 (overlap 0 → 72 retained), then the optional
  ×4 expansion yields 288 candidates.
- Sieve selectivity is **not** known ahead of a run, so `bundle plan` reports post-sieve as
  **BOUNDED `[0, mandatory]`**, not a point estimate (see [06](06_PLANNING_BUDGETS_AND_COUNTS.md)).
- The sieve evaluates predicates over **finite value metadata** (`params`); it does not execute
  candidates. Constraints that depend on runtime behavior belong in the oracle (the TAIL verdict),
  not the sieve.
- An incorrect constraint can remove the very cases that would expose a defect — treat constraint
  coverage as something to validate (known-pass/known-fail controls), as the assessment notes.

## The full bond vocabulary — polarity, gate, arity

A constraint is a **bond** over two or more sheets. The complete shape (schema:
[`constraints/sidecar_schema.md`](../generator_trunk/constraints/sidecar_schema.md)):

- **polarity** — `forbid` (default; the holding tuple removes the row, *"never together"*) or
  `require` (the *sought* form; a gated tuple that does **not** hold removes the row,
  *"only together"*).
- **gate** (positional) — `{}` any co-occurrence · `{"adjacent": true}` a contiguous run
  (`max−min == k−1`) · `{"within": N}` a window (`max−min ≤ N`). Generalized to any arity; for two
  placements these are exactly `|x−y| == 1` and `|x−y| ≤ N`.
- **arity** — **two** sheets (binary, the common case) or **three+** (n-ary: a forbidden/required
  tuple, or a `when` over all of them). Pair/set/when/mapping rules that relate fewer than two
  referenced sheets are skipped (`--strict` makes that a hard error). A deliberate `assert`
  body is the exception and may enforce a unary condition.

```toml
[[constraints]]                 # n-ary, required ("sought"), gated example
id = "auth_tls_region_triple"
sheets = ["AUTH", "TRANSPORT", "REGION"]
pairs  = [ { AUTH = "token", TRANSPORT = "tls", REGION = "eu" } ]
polarity = "require"
gate = { within = 2 }
desc = "a token over TLS is only kept in the EU region, and only when the three sit within 2 slots"
```

### Rule bodies and contextual conditions

The implementation accepts more than enumerated binary pairs:

- `pairs` enumerates allowed/forbidden n-ary tuples; `sets` describes the Cartesian product of
  per-sheet value sets; `when` evaluates an expression over declared value metadata.
- `mapping` is a dependent allowed-set from source values to target values.
- `assert` uses the structured condition AST as the rule body; `condition` uses that same AST only
  as a context gate around another rule body.
- `orders` declares a sheet as an explicit ordered list, `numeric`, or `date` so ordinal leaves can
  compare a selection with a constant or another sheet.
- Condition leaves cover equality/membership, presence, multi-select counts, cross-sheet
  equality/subset/superset, and ordinal comparisons, composed with `all`/`any`/`not`.

The exact field grammar and absence semantics are in
`generator_trunk/constraints/sidecar_schema.md`. In particular, ordinal and subset comparisons are
vacuously true on absence unless a `present` leaf is composed with them.

## FW_Optional bonds — deferred to candidate assembly

`fw_final` and the `fw_optX` tables are **compact, factored storage**: an `FW_Optional` slot's value
is *not* stored on the mandatory `fw_final` row — it lives in `fw_optX` and is **assembled with the
mandatory combo by the Reader**. So an empty optional cell in `fw_final` means the action is
**absent**, not "the slot's first value." Consequences:

- The sieve does **not** inherit a baseline for optional slots (fixed bug: it used to read the
  optional slot's first value as the baseline, so a bond like `forbid A=a1 with OPT=w1` deleted
  *every* `a1` row — see [`constraints/sieve.py`](../generator_trunk/constraints/sieve.py)
  `build_maps_from_db`).
- A bond that **references an optional sheet cannot be enforced on `fw_final`** (deleting a mandatory
  row would drop it for *every* optional choice, not just the forbidden pairing). It is **deferred**
  to candidate assembly: `sieve_fw_final` reports it under `deferred` / a warning and applies
  nothing to `fw_final`. The bond's *semantics* are correct on the assembled candidate (mandatory +
  chosen optional placement) — that is where it belongs.
- Under `--sieve`, that deferred bond is then **actually enforced at Reader assembly**, scalably: the
  sieve compiles each bond into a compact code-tuple spec and the Reader evaluates it per assembled
  candidate (size `O(bonds)`, not the candidate count). It is opt-in and costs a non-sieving run
  nothing. See [27 §4](27_TABLE_ARCHITECTURE_AND_READER_ASSEMBLY.md).
- The compact Reader gate cannot represent every absence-sensitive or ordinal condition over an
  optional sheet. The compiler enumerates supported contextual domains and **fails closed** when it
  cannot preserve the authored semantics; it does not silently weaken the rule.

## Draw the bonds interactively (`--draw`)

`bundle_run.py <spec> --draw` pauses **before Core**, opens the single-file link editor in Firefox
(`constraints/editor.py` served by `constraints/serve.py`), and waits for **Submit**. The user
draws value-to-value links — **red = forbid, green = require** — sets each link's gate, joins 3+
nodes into an n-ary bond, or adds a `when` formula over value parameters; a live "removes N of M"
preview updates as they draw. On Submit the page POSTs the sidecar back and the chain resumes into
Core → SIEVE → Reader. `--draw` implies `--sieve`. **Submitting an empty canvas is valid** — the
sieve then has nothing to remove (identical to a run without `--sieve`). The editor also LOADS the
spec's existing `[[constraints]]`/`[[params]]` so a re-run edits what is already there. This is the
second of the three user-facing "faces" of the Bundle (see
[`26_PLAN3_THREE_FACES_UX.md`](26_PLAN3_THREE_FACES_UX.md)).

The editor authors `when` formulas by **text or a visual block builder** (a Текст/Блоки toggle), and
lets you **edit each link's conditions in place** (polarity, gate, formula, value sets). Live impact
is an in-browser estimate by default; **`--draw-exact`** (runs after Core) instead shows the **exact**
removed/kept over the whole assembled space `fw_final × fw_optX` from the live DB.
