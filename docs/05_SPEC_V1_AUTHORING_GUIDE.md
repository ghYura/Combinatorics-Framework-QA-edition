# 05 — Spec v1 Authoring Guide

The public authoring contract is `generator_trunk/bundle-spec-v1.schema.json` (draft 2020-12).
Authored specs may be TOML, JSON, YAML, or YML, and a directory may contain multiple specs. The
directory loader ignores known Bundle-produced JSON artifacts (plans, run state, handoffs, result
cards, sidecars, and graph JSON) rather than mistaking them for authored specs.

## The one principle (from ZEN_OF_COMBINATORICS)

> **The verb is dictated by the shape of the freedom — never chosen to hit a number.** Model the
> real degrees of freedom; the count falls out.

## Top-level fields

| Field | Required | Meaning |
|---|---|---|
| `slots` | **yes** | the combinatorial axes (each a sheet + verb + values) |
| `spec_version` | no | absent → interpreted as `legacy`; declare for v1 strictness |
| `title`, `note`, `args`, `runme` | no | metadata / launcher args / RunMeFirstOnce |
| `goals` | no | Analyzer objectives (`key`, `dir`) |
| `custom_vars` | no | custom verdict code → message map |
| `params` | no | value attributes the sieve reads (e.g. `tier`, `unicode`) |
| `constraints` | no | the bonds layer (sieve rules) — see [07](07_CONSTRAINTS_GUIDE.md) |
| `seq_extra` | no | **top-level** brace/second-order `FW_Seq` rows |

## `runme` / `FW_RunMeFirstOnce` — the run-scoped prologue

`runme` is not a slot and contributes no rows to the combinatorial count. It describes what must be
prepared, observed, or fixed once for one Executor handoff before the candidate family is evaluated.
HEAD and TAIL remain per-candidate code; `FW_Arguments` remain static authored arguments; the
canonical Java `RunMeFirstOnce` may calculate shared `FW_ARGS` that replace those static arguments
for every candidate in its scope.

Use it for deterministic prerequisite checks, runtime observation/calibration, expensive shared
bootstrap, corpus-wide preprocessing, or shared argument derivation. Do not hide candidate-dependent
choices or per-candidate scoring in it: those belong in modeled slots or the candidate oracle and
must retain provenance. Its exact scope, Java/Python differences, resume/idempotency requirements,
and AI-testing mapping are defined in
[RUNMEFIRSTONCE_LOGICAL_CONSTRUCT.md](RUNMEFIRSTONCE_LOGICAL_CONSTRUCT.md).

## Slots, operators, mechanics

Each `[[slots]]` has `sheet`, `key`, `verb`, optional `flags`, `raw`, `values`, `separator`,
`group_replace`. The verb encodes the freedom:

| Freedom | Verb | Output for `n` |
|---|---|---|
| exactly one | `FW_Combi(1)` (default) | `n` |
| k of n (unordered) | `FW_Combi(k)` | `C(n,k)` |
| any subset | `FW_Subsets` (`2ⁿ`) / `FW_Combi(all)` (`2ⁿ−1`) | subsets |
| k of n with repetition | `FW_CombiR(k)` | `C(n+k−1,k)` |
| an ordering | `FW_Permut` / `FW_Permut(k)` | `n!` / `P(n,k)` |
| sequence with repetition | `FW_PermutR(k)` | `nᵏ` |
| size-bounded subsets | `FW_Subsets_EXACT/RANGE/BEFORE/AFTER/GIVEN(…)` | bounded ΣC(n,k) |
| cross another sheet | `FW_Cartes(OTHER)` | `n·\|OTHER\|` |
| weave a glue token | `FW_Separator(GLUE)` (modifier) | row-preserving |
| may or may not happen | `FW_Optional` (flag) | `×(n+1)` per slot |
| join two prior results | brace `FW_(…)` | 2nd-order join |
| re-combine + rewrite a prior result | `FW_Group` + `FW_ReplaceRE` | 2nd-order |

`raw = true` means the values are raw source fragments (e.g. Python lines) spliced into the
candidate; otherwise they are tokens.

## `FW_Optional` — sudden actions (get this right)

An `FW_Optional` slot models an action that **may or may not fire**, in any combination with other
optional actions, **before the probe** (the TAIL). It is routed to the optional bucket, not the
mandatory product. Count: `final = pruned_mandatory × Π(nᵢ + 1)` (each slot: one of its values OR
absent). Verified in the flagship: 2 optional slots (rotate-key, poison-cache) → ×4, turning
post-sieve 72 into 288 candidates. With zero optional slots the path is byte-identical to a plain
run.

## The brace `FW_(…)` — a JOIN of two PRIOR result tables (get this right too)

The brace operands are **NOT raw value sheets** — they are the **result tables earlier `FW_Seq`
rows produced**. Grammar (9 fields): `FW_(start, _, E1, rel, E2, _, end, sep, mult)`.
- `E1`,`E2` name two earlier sheets whose result tables are the operands; they **MUST carry
  `FW_Exclude`** so the join consumes them.
- `start`/`rel`/`sep`/`end` are non-excluded 1-value helper sheets (each contributes its first value).
- `mult ∈ 1:1 | 1:N | M:1 | M:M | M:N` is the join cardinality.
- `seq_extra` **must be a top-level TOML key** (before any `[[slots]]`/`[[goals]]`), or TOML binds
  it to the last table and silently drops it. Verify: `python3 -c "import fwgen as fg;
  print(fg.load_spec(P).seq_extra)"`.

```toml
seq_extra = [["JOINED", "FW_Reuse", "FW_(,,A,,B,,,,M:N)"]]
[[slots]]
sheet="A" verb="FW_Combi(2)" flags=["FW_Exclude"] raw=true values=[...]
[[slots]]
sheet="B" verb="FW_Combi(1)" flags=["FW_Exclude"] raw=true values=[...]
[[slots]]
sheet="JOINED" verb="FW_Combi(1)" raw=true values=["placeholder # overwritten by the brace"]
```

`FW_Group` + `FW_ReplaceRE` (first-class `group_replace = [["pat","rep"], …]`) is the unary
second-order operator: it re-combines a sheet's prior **rows** and rewrites the assembled string.
It concatenates **by index order**, so it is the most order-sensitive verb — rely on the Core's
content-sort for determinism.

> **`group_replace` patterns match value-CODES, not value text.** The rewrite runs against the
> code-string of each produced combination — `"[47, 48]"`, a list of interned `Short` keys — so a
> pattern written against rendered text (a placeholder like `@S@`, a word like `"shape"`) can never
> match and is a silent no-op. While authoring, turn the check on:
> `core.replace.patternPolicy=warn` rejects such patterns up front and
> `core.replace.diagnostics=summary` shows how many rows each pattern actually changed. Both default
> to off, so existing specs are unaffected. See
> [41_FW_REPLACERE_POLICIES.md](41_FW_REPLACERE_POLICIES.md).

## Optional behavior, aliases, separators

- **Aliases** (opt-in, compiled to verbs): `choose_one`, `choose_k`, `permute`, `feature_subset`,
  `optional_action`. An alias spec and the equivalent expert spec produce the **same workbook/count**
  (verified by 44 alias-equivalence tests). You cannot mix a conflicting alias + raw verb on one slot.
- **`separator = "GLUE"`** weaves the glue sheet's first value between elements — but only into the
  `fw2_`/sub-combo output a brace or `FW_Group` consumes, **not** the plain `fw_` table; pair it with
  a brace or `FW_Group`.

## Strict vs compatibility modes

- Legacy specs (no `spec_version`) load unchanged.
- **Compatibility mode** (default): unknown top-level/slot fields are warned and ignored.
- **Strict mode**: unknown fields are rejected (catches typos), including nested slot/dict typos.

## Validation errors & gotchas (each cost real time)

- No data cell may start with `FW_` (parsed as a directive); a TAIL setting `FW_VAR` must lead with
  another statement (e.g. `_n = len(x)` first).
- `estimate_core_combos` ignores brace/`FW_Group` → the plan marks those UNKNOWN (not a failure).
- Brace operands need `fw2_<k>` — provided automatically by the `FW_Combi(1)→dual` auto-promote.
- A bare `FW_Permut` (no dual) is not auto-promoted and may leave a brace/separator consumer with no
  `fw2_` rows. Verify that the operand directive actually produces the dual table your second-order
  operation consumes.

## Safe cardinality design

Run `bundle plan` first ([06](06_PLANNING_BUDGETS_AND_COUNTS.md)). Prefer exactly-one/k-of-n/subset
shapes over flattening everything into a Cartesian product; use `FW_Optional` for sudden actions
instead of mandatory axes; declare constraints to prune impossible states before execution; keep the
final candidate count inside the budget for your run class.
