# Face 1 new combinatorial browser acceptance

This package turns the NiceGUI page into a testable object for Bundle itself.
It separates four responsibilities:

1. `selectors.toml` is the auxiliary selector/label inventory. It names all
   tabs, buttons, fields, checkboxes, expansions, dialog headings, icon-only
   controls and dynamic grid/template/advanced-field patterns.
2. `page_object.py` is the Selenium Page Object. Tests call semantic operations
   such as `open_tab`, `set_field`, `grid_cell`, `drag_template`,
   `open_expansion`, `visible_dialog`, and `wait_download`; tests do not contain
   their own XPath strings.
3. `actions.py` contains independent user journeys. Each journey starts from a
   new workbook, performs one coherent interoperability experiment, and returns
   a classified `FlowResult` instead of crashing the Executor.
4. `spec.py` and `specs/face1_dogfood.toml` compose those journeys as the
   canonical Bundle structure:

       HEAD × BROWSER × VIEWPORT × FLOW × DATA_PROFILE × TAIL

The current canonical Chromium matrix is 1 × 2 × 13 × 2 = 52 candidates.
HEAD imports the Page Object runtime. The inner sheets assign the selected
browser, viewport, action flow and data profile. TAIL assembles the two verdict
global names at runtime and emits one Analyzer-compatible K=V metric line.
Generated inner cells therefore never contain the contiguous Core-reserved
prefix; real control-sheet values remain exact Core syntax.

## What the flows cover

- `grid_data_sync`: target/data editing and live propagation into Data sheets,
  FW_SheetNames and the cardinality plan;
- `grid_structure`: rows, columns, row movement, brace-trio insertion and
  validation classification;
- `template_catalog`: all 55 source-verified template labels, clear/edit and
  HTML5 drag/drop into exact XLSX coordinates;
- `control_sheets`: FW_RunMeFirstOnce clear/restore, FW_Arguments add/delete,
  FW_CUSTOM_VAR add/delete, and FW_Info synchronization;
- `runtime_essentials`: run fields/selects, readiness invalidation/recheck,
  draw-mode mutual exclusion, plan, run confirmation and Face 2 confirmation;
- six `runtime_advanced_*` slices cover every non-essential field in the tested
  Bundle control registry exactly once: budgets, sandboxing, repeat policy,
  infrastructure paths, infrastructure commands, and stress controls;
- `modal_guardrails`: import boundary, helper validation/save, scenario plan and
  real-example confirmation without starting a destructive run;
- `download_import`: XLSX download followed by upload/import and state recovery.

Three deliberately separate nested flows test real side effects: workbook
execution (including Core, Reader, Executor, formal Analyzer, live UI state and
exports), cancellation, and a verified repository scenario. They are excluded
from the 52-candidate standard matrix so routine browser coverage does not
silently execute nested pipelines.

`surface_contract.py` parses `app.py` and `run_ui.py` with Python's AST. It fails
when an interactive NiceGUI call is added or removed without updating the
selector inventory, when a static label is not registered, when an icon-only
button is unknown, or when a dynamic advanced section is unaccounted for.

## Collision-free parallel design

`orchestrator.py` starts multiple NiceGUI servers and multiple real Bundle runs
in parallel. Every lane gets a unique:

- NiceGUI port and server log;
- PostgreSQL database name on both configured endpoints;
- specification directory, scratch root and runs root;
- Bundle run ID and journal;
- Chromium/Firefox profile, WebDriver service port and download directory.

NiceGUI project state is per browser client, so several candidates can safely
share a server. Mutable Bundle state is never shared. The source tree and built
JARs are immutable inputs during a run, therefore copying the entire repository
to `Combinatorics-Framework1`, `Combinatorics-Framework2`, and so on is unnecessary for this suite and
would create slower, harder-to-audit replicas. Failed-run artifacts are retained;
successful temporary runs are removed unless requested.

The command-line orchestrator reports only startup and lane-terminal state
changes. Long healthy runs therefore stay quiet; a failed or completed lane
wakes the caller immediately with its classified counts and artifact path.

## Commands

Model and selector contract tests (no browser, Core or database mutation):

```bash
pytest -q face1_new/test_e2e_support.py -k 'not two_face1_servers'
```

Two live NiceGUI instances with two browser flows, without Bundle/Core/DB:

```bash
FACE1_E2E_LIVE=1 pytest -q face1_new/test_e2e_support.py \
  -k two_face1_servers -s
```

Small real dogfood run: two parallel Bundle/NiceGUI lanes and four candidates:

```bash
python3 -m face1_new.e2e.orchestrator --instances 2 --suite smoke --keep-artifacts
```

Full 52-candidate Chromium matrix:

```bash
python3 -m face1_new.e2e.orchestrator --instances 4 --suite exhaustive --keep-artifacts
```

Real nested workflows, isolated across three Bundle/NiceGUI lanes:

```bash
python3 -m face1_new.e2e.orchestrator --instances 3 --suite nested --keep-artifacts
```

A decomposed journey can be selected without replaying the rest:

```bash
python3 -m face1_new.e2e.orchestrator --instances 1 \
  --flows runtime_real_run --keep-artifacts
```

Passwords are read only from the existing Bundle server environment. They are
never placed in selectors, generated candidates, TOML specs, browser profiles,
commands or logs.

## Firefox

Firefox is supported by the Page Object but requires GeckoDriver. Install a
version matching the local Firefox and either place it at
`/usr/local/bin/geckodriver` or set `GECKODRIVER=/path/to/geckodriver`. Then run:

```bash
python3 -m face1_new.e2e.orchestrator --instances 4 --suite exhaustive \
  --browsers chromium,firefox --keep-artifacts
```

Selenium Server is not required for these local lanes.
