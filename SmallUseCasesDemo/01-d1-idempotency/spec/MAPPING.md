<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D1 spec: sheets, flags, verbs and bonds

`build_spec.py` writes all four files here from the audited sources:

- `spec.toml` is the authoring source.
- `demo.xlsx` is compiled from `spec.toml` by `generator_trunk/fwgen_cli.py gen`. It is the
  campaign's run input.
- `demo.constraints.json` is the workbook's constraint companion. fwgen writes it beside the
  compact workbook, and it is renamed to the workbook's new stem. It is the sieve's v1 sidecar,
  which the Bundle loads with `demo.xlsx`.
- `build.json` holds the file hashes.

Check for drift with `python build_spec.py --check`. It compares the TOML and companion bytes
and the workbook's cell content; workbook bytes carry zip timestamps.

## Sheets, in `FW_Seq` order

| Sheet | Values (cell text) | Verb | Ending | Meaning |
|---|---|---|---|---|
| HEAD | one fragment: `sut.py`, `oracle.py`, `runtime.py` as string literals, each checked against its SHA-256 and run in its own module namespace; binds `d1` = runtime | `FW_Combi(1)` | none (the value ends with a newline) | runtime definitions; no enumeration |
| IMPL | `IMPL = "volatile_transport"` … `IMPL = "durable_operation"` (5) | `FW_Combi(1)` | `\n` | policy under test |
| L1 | `L = [0]` | `FW_Combi(1)` | `\n` | delivery 1 opens identity class 0 |
| L2 | `L.append(0)`, `L.append(1)` | `FW_Combi(1)` | `\n` | delivery 2: same identity as delivery 1, or a new one |
| L3 | `L.append(0)`, `L.append(1)`, `L.append(2)` | `FW_Combi(1)` | `\n` | delivery 3: class 0, class 1 or a new class 2 |
| CUT1 | `CUT1 = 0`, `CUT1 = 1` | `FW_Combi(1)` | `\n` | process restart before delivery 2 |
| CUT2 | `CUT2 = 0`, `CUT2 = 1` | `FW_Combi(1)` | `\n` | process restart before delivery 3 |
| CONTROL | `CONTROL = "none"`, `"retry_fresh_transport"`, `"new_order_equal_payload"`, `"new_operation_same_order"`, `"conflicting_retry"` | `FW_Combi(1)` | `\n` | at most one peer request after the core |
| TAIL | `_verdict = d1.emit(IMPL, L, [CUT1, CUT2], CONTROL)` / `FW_VAR = _verdict` / `FW_CUSTOM_VAR = FW_VAR` | `FW_Combi(1)` | none | run the case, emit the record, set the verdict |

The `L1 L2 L3` labels say which deliveries share a transport identity. Delivery i uses
`T<label_i>`. `CUT1 CUT2` are lifetime boundaries: a different structure on the same three
deliveries.

**Endings.** A catalogue value is a complete statement without surrounding whitespace.
Its newline is the `FW_SheetNames` ending that Core appends.
- This is deliberate. The sieve strips database values but compares bond values verbatim,
  so a bonded value with a trailing newline would never match.
- See ../blockers/sieve-whitespace/.

**Flags.**
- `spec.toml` declares none.
- fwgen writes `FW_Reuse` on every `FW_Seq` row of `demo.xlsx`; that is its default.
  With no brace, nothing consumes a table, so it has no effect.
- There are no `FW_Optional`, `FW_Exclude` or `FW_Heading` sheets. The optional multiplier is 1.

**Verbs.** Each row has a single `FW_Combi(1)`. Core's dual auto-promotion runs it twice
(`Combi(1)` then `Combi(1)`), and the second pass re-derives each singleton. The XLSX plan
states this: "the dual pass re-derives the same rows".

**Program.** The TOML and XLSX plans have the same sheets, verbs and sizes, and the same
`FW_Seq` dependency graph, SHA-256 `0604f6c2216208afd002a4127015c98661c0a644961d0c5a6c87382f94d6f334`.
Raw Core support is `5 × 1 × 2 × 3 × 2 × 2 × 5 × 1 × 1 = 600` (EXACT).

## Bonds (`demo.constraints.json`; the same two rules as `spec.toml`, applied in this order)

1. **`canonical_identity`** (forbid; `sets`): `L2 = L.append(0)` together with
   `L3 = L.append(2)`.
   - Class 2 cannot open before class 1, so only the restricted-growth strings
     `000 001 010 011 012` remain (Bell(3) = 5).
   - It matches 100 of the 600 raw rows, leaving 500.
2. **`peer_baseline`** (forbid; `assert`): `CONTROL` is one of the four peer controls **and**
   any of `L2 ≠ L.append(0)`, `L3 ≠ L.append(0)`, `CUT1 ≠ CUT1 = 0`, `CUT2 ≠ CUT2 = 0` holds.
   - Peers therefore run only on `labels = 000` with no restart.
   - It matches 460 raw rows, 80 of them also matched by bond 1.
   - Unique removals are 480, leaving **120**.

`python verify.py` recomputes this truth table with its own reading of the sidecar, over the
TOML's actual values. It checks the result against the sieve's logged per-rule counts.

**XLSX input and its companion.**
- Before the author-authorized fix, an XLSX input could not carry a sidecar (see
  ../blockers/xlsx-sidecar/).
- The Bundle now loads `demo.constraints.json` with `demo.xlsx`; the change is inventoried in
  the Framework's main branch.
- Both plans report two rules and EXACT 600 → 120.
- `run_demo.py` still refuses any input that does not load exactly these two rules.

## Verdict carrier

`FW_VAR` and `FW_CUSTOM_VAR` are 0 for PASS and 2 for DOMAIN_FAIL. Position 2 is the IMPL
sheet (HEAD is 1). It is the legacy positional carrier, not a statement that IMPL caused the
failure. The `FW_CUSTOM_VAR` message sends the reader to the observation record (`rec=`) in
the candidate's metrics line.
