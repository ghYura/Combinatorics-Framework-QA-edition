# Face 1 new — Core workbook spreadsheet composer and run center

This is the canonical active **Face 1** implementation. The earlier
plain-language prototype at `../intake/` remains runnable for compatibility
and historical comparison, but it is superseded. The rejected first mockup was
backed up by the user as `bkup15072026.zip`; that archive is untouched.

The active workspace deliberately looks and behaves like an XLSX sheet rather than a card canvas:

- uniform row/column grid with Excel coordinates;
- horizontal and vertical scrolling;
- one UI cell equals one physical `FW_Seq` workbook cell;
- draggable verb cells in a templates pane;
- 55 compact, source-verified Core verb variants with full syntax available on hover;
- drop into an exact empty directive cell;
- single-click selects a cell and exposes its exact value in the formula bar;
- double-click expands the editor for that particular cell;
- double-click column A to edit the target name, prefix/suffix, and its source data sheet;
- add rows and directive columns without changing existing placement;
- download the validated workbook as `.xlsx`.

New compositions start with a minimal FW_Seq row, trailing blank grid rows, and all six Core control sheets. They do **not** clone the 208-sheet `example150726.xlsx`; importing a full workbook is explicit.

## Guided start

The first tab is an invitation coach shared with the original Face 1. It asks for the issue domain, desired outcome, and primary risks; proposes editable factors, value interactions, relationship questions, and deliberately unchecked optional stress actions; then shows exact raw growth and guardrail warnings. Confirming creates ordinary `GridProject` rows and sends them through the existing validator and planner. It never claims that answering a relationship question applies a sieve rule: define real relationships in Face 2 before claiming constrained coverage. The learning route points to the deterministic `combination_thinking_tutor` in the companion SUT repository.

## Positional semantics

Column order and blank cells are first-class state.

For example, this is valid and exports exactly as shown:

```text
B = FW_Exclude
C = <empty>
D = <empty>
E = FW_Reuse
F = <empty>
G = FW_Combi(1)
```

`FW_Reuse` or `FW_ReuseTableOnly` must be the next **non-empty** cell after `FW_Exclude`. Any number of empty cells may occur between them. Empty columns are never compacted during export.

`FW_Group` and a multi-line `FW_Group`/`FW_ReplaceRE` cell may appear in any directive column. They are not forced to the first or last position, and multiple Group cells in the same row are supported.

An `FW_(...)` cell is valid only in the row immediately following two consecutive rows that both contain `FW_Exclude`. Its left and right operands must name those previous two target sheets in order. If the operands use `FW_Reuse` or `FW_ReuseTableOnly`, both rows must use the same mode. The templates pane includes an “Insert valid 3-row brace pattern” action for this grammar.

The brace palette includes all five multiplicities in compact and full nine-field forms, plus nested `FW_()` and grouped `FW_()G` operand forms. Dropping a brace binds `LEFT`/`RIGHT` to the two preceding target rows; nested markers remain intact for Core to resolve.

## Workbook tabs

- `FW_Seq` is the editable composition grid.
- `FW_SheetNames` is derived live from target, prefix, and suffix state.
- `FW_RunMeFirstOnce` edits the canonical Java bootstrap source in physical cell A1.
- `FW_Arguments` edits one Core argument per physical column-A cell.
- `FW_CUSTOM_VAR` edits Java Integer verdict codes in column A and messages in column B.
- `FW_Info` is the live mirror that will be written to the composed workbook.
- `Data sheets` shows source/helper data separately from directives.
- `Example · FW_Info` preserves the real `FW_Info` from `example150726.xlsx` as read-only reference material.

Every project mutation refreshes all live sheets from the same server-side `GridProject`; no tab reload is required. The example tab remains intentionally static and is never copied into a new project.

## Export contract

Export writes these control sheets first:

1. `FW_Seq`
2. `FW_SheetNames`
3. `FW_RunMeFirstOnce`
4. `FW_Arguments`
5. `FW_CUSTOM_VAR`
6. `FW_Info`

Each used grid row also creates its target data sheet. Trailing blank display rows are ignored; a blank row inside the used sequence is an error. Imported runtime controls and helper sheets are preserved.

Validation covers sheet names, missing data/directives, references, reuse and brace positions, Group placement, Java Integer verdict codes, duplicate codes, Excel cell limits, and Core’s expected RunMeFirstOnce/FW_ARGS source pattern.

## Plan & run

The **Plan & run** tab (ninth of the current ten tabs) brings the useful
intentions of the earlier Face 1 into the spreadsheet-first design:

- live mandatory, post-sieve, optional, and final cardinality with EXACT, BOUNDED, or UNKNOWN confidence;
- honest S/B/L/X run classification, workbook validation, and read-only planning;
- essential controls plus the complete tested Bundle option registry for budgets, sandboxing, repeats, infrastructure, and stress;
- an exact launch-command preview with database secrets inherited only from the server environment;
- engine and PostgreSQL readiness checks, with automatic recheck-required state after relevant configuration edits;
- explicit confirmation before any real run, plus cancellation, stage journals, live logs, outcome counts, provenance/Pareto results, and JSON/CSV export;
- a test-suite/scenario picker that runs repository examples without changing
  the current workbook, including seven historical Automation Scheme Studio
  real-SUT tiers, four recursive higher-order feedback scenarios, three
  checked-in AI exact-control scenarios, and a fresh `AIRG` release-gate
  apparatus entry under immutable per-suite launch profiles;
- optional Face 2 handoff through the existing Bundle draw modes.

Inspecting `AIRG` materializes a fresh held-out spec only in a temporary
directory and strictly plans it. Starting the entry materializes a new spec in
the isolated run tree, strips external/prompt-export credentials and controls,
and executes the 2,560-candidate network-disabled local-oracle apparatus. This
is apparatus validation, not a target-AI result; use the platform's separate
exchange exporter for target responses.

Plan only never creates a run or writes a database. Run workbook exports and
validates the current project, then passes that exact XLSX into the existing
Bundle lifecycle. Only the normal generation work is replaced by a
copy-and-validate seam; preflight and budgets, Core, optional seed-bias,
optional sieve, Reader, Executor, optional Analyzer, journals, and results
remain the real Bundle path. No simulated progress or fabricated result data is
used.

Database passwords are deliberately absent from workbook state, browser controls, launch previews, saved metadata, and logs. Configure them in the server environment using BUNDLE_MAIN_DB_PASSWORD and BUNDLE_RESULTS_DB_PASSWORD.

## Run

From `generator_trunk`:

```bash
python3 -m face1_new.app
```

Open `http://127.0.0.1:8088/`. Alternatives:

```bash
python3 face1_new/app.py --no-browser --port 8088
python3 -m face1_new.app --reload
```

Install dependencies on another host with:

```bash
python3 -m pip install -r face1_new/requirements.txt
```

## Verify

```bash
python3 -m py_compile face1_new/*.py
pytest -q face1_new/test_workbook_model.py face1_new/test_grid_model.py face1_new/test_core_templates.py face1_new/test_brace_variants.py face1_new/test_control_sheets.py face1_new/test_runtime_model.py test_face1_control_panel.py
```

The combinatorial browser acceptance package is documented in
[`e2e/README.md`](e2e/README.md). It provides an external selector registry, a
semantic Selenium PageObject, decomposed action flows, Core-safe Bundle
HEAD/inner/TAIL generation, and collision-free parallel dogfooding through
independent NiceGUI, database, scratch, runs, profile, port, and download state.

`grid_model.py` is the NiceGUI-independent composition, positional validation, import, and XLSX export layer. `workbook_model.py` reads existing workbooks and supplies the example/reference model. `app.py` owns only the NiceGUI interaction layer.

runtime_model.py owns planning, validation, command construction, engine readiness, live run sessions, journals, and result parsing. workbook_runner.py injects the exact authored workbook into the existing Bundle runner. run_ui.py owns the compact NiceGUI planning/run surface. grid_model.py and workbook_model.py remain the authoritative composition and import/export layers; app.py coordinates the tabs and shared project state.

The superseded Face 1 directory and the user backup archives remain separate.
The active Face 1 can execute the current workbook and request the existing
Face 2 workflow, while Face 3 remains the Bundle results surface rather than a
duplicate implementation here.
