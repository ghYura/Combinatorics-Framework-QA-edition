# Legacy Face 1 — "Describe your task" (superseded intake UI)

> **Status:** compatibility prototype retained for historical comparison and
> existing workflows. The canonical active Face 1 is the spreadsheet-first
> NiceGUI application in `../face1_new/`. This directory is still runnable, but
> new feature and workflow claims must be checked against `face1_new/README.md`.

`face1.html` is the earlier plain-language Face 1 described by
`docs/26_PLAN3_THREE_FACES_UX.md`. It is a single-file, zero-dependency,
offline UI: open it in any browser — nothing is fetched and nothing leaves the
page until the companion server is used.

> **Face 1 describes the task → Face 2 draws the relations → the engine runs → Face 3 reads the verdict.**
> Face 2 (`constraints/editor.py`, the blue drawing canvas) already exists.
> This document describes the legacy Face 1.

## What it does

It lets anyone describe a combinatorial task **in plain language** and generates a valid
`fwgen` spec (TOML) for it — **without ever typing an `FW_` token**. A guided 5-step composer:

1. **Start** — name the task, or pick one of 10 templates that abstract the real sub-folders
   (`usecases/perf_opt`, `usecases/event_order`, `usecases/ml_eval`, `fintech_oot`,
   `llm_loop/redteam`, `model_usecases/nas_micronet`, config/ETL/API, …).
2. **Moving parts** — add as many *dimensions* as you like, list each one's options, and pick
   **how free the choice is** ("pick exactly one", "pick k of them", "any combination",
   "put all in order", plus advanced repetition shapes). Reorder freely by drag (⠿) or ▲ ▼ —
   the order is the `FW_Seq` the engine composes.
3. **Sudden actions** — optional "what-if this *also* happened?" events (`FW_Optional`).
4. **What success means** — goals to optimise (direction auto-inferred from the metric name)
   and the ways a candidate can fail (verdict codes).
5. **Review & export** — a plain-language summary, the generated `.toml`, the full **control panel**
   (rebuilt 2026-07-04: *every* `bundle_run.py` flag across every Bundle component — backend, language,
   transport, executor pool, execution policy & sandbox, budgets, repeat policy, seed bias, timeouts,
   ports, infra paths, stress mode, iterate, diagnostics — in collapsible, dependency-aware sections;
   a **backend selector** picks *Local (full control)* or *Gateway (EaaS safe subset)*; DB credentials
   stay read-only from the server env), the exact CLI command (live), and a huge **Run** button.
   The UI `FIELDS` registry mirrors the server's flag registry, cross-checked by
   `test_face1_control_panel.py` so no parameter goes missing.

### Invitation coach

The Start step now opens with a bilingual, offline-capable invitation coach. It asks what kind of issue this is, what must improve or never fail, and which risks matter; proposes factors and interaction questions; flags missing relationship rules; calculates raw mandatory and optional growth with `BigInt`; and keeps stress actions unchecked until the user chooses a plausible hypothesis. Applying a proposal only fills the existing editable dimensions and sudden-actions steps. Relationship answers remain prompts for Face 2, never silently applied constraints. The learning route corresponds to the deterministic `combination_thinking_tutor` in the companion SUT repository.

A persistent **honesty meter** shows the live candidate count with its confidence tier
(**exact / at most / unknown**) and budget run-class (**S / B / L / X**) — mirroring
`fwgen.spec_cardinality_plan` exactly, so the number reconciles with `bundle_run.py plan`.

## The run flow (Run → progress → logs → Face 3)

Pressing **Run** asks *"Would you like to add constraints on the relations between particular
instances?"* — **Yes** (draw bonds in Face 2 first / apply the sieve) or **No, Combine!** (combine
everything as-is). It then opens:

- a **progress window** showing Plan/Generate/Core/Sieve/Reader/Executor/Analyzer
  with live status and per-stage counts. The server also reads the optional
  `seed_bias` journal stage, but this legacy page's progress rail does not
  render it;
- **Show log** / **Show detailed log** windows — the normal log is the high-level `[i/n]` stage
  trace; the *detailed* log is everything consumed & printed (resolved config, workbook build,
  `fw_final` counts, per-candidate `app=… FW_VAR=…` lines, the invariant check, Pareto summary),
  copyable and downloadable;
- **Face 3 — Results** when done: pass/fail hero, winners per goal, a goal-trade-off **Pareto
  front** plot, "what your rules pruned" provenance, a candidate table, and CSV export.

### Two modes: real backend vs offline preview


The verified-scenario gallery has a test-suite selector backed by the catalog
shared with Face 1 New. It exposes seven historical Automation Scheme Studio
real-SUT tiers, four recursive higher-order feedback scenarios, three
checked-in AI exact-control scenarios, and the `AIRG` advanced sub-suite entry.
Static entries run their reviewed TOML. `AIRG` instead creates a fresh held-out
release-gate spec at real-backend launch and pins its network-disabled,
zero-cost, bounded local-oracle profile rather than inheriting composer
controls. It does not contact a target AI; target-response exchange remains a
separate explicit workflow. Database credentials still come only from the
server environment.

- **Real backend (recommended).** Launch the companion server `serve_face1.py`; the page detects it
  (rail shows **● Real backend**) and the **Run** button *actually fires* `bundle_run.py`. Progress
  is **traced live from the real run journal** (`state.json` + `stages/*.json`), the detailed log is
  the pipeline's real stdout/stderr, and **Face 3 shows real results** (Executor outcomes +
  Analyzer Pareto front & provenance).
- **Offline preview (fallback).** Open `face1.html` directly (`file://`) with no server; the rail
  shows **○ Offline preview** and Run plays a faithful simulation (real counts, illustrative
  verdicts). Use the command in Review for a real run.

### Running the real backend

```bash
cd generator_trunk
# Put the JDK required by the built Bundle artifacts on PATH first:
# export JAVA_HOME=/path/to/jdk
# export PATH="$JAVA_HOME/bin:$PATH"
: "${BUNDLE_MAIN_DB_PASSWORD:?inject the main DB password if required}"
: "${BUNDLE_RESULTS_DB_PASSWORD:?inject the results DB password if required}"
python3 intake/serve_face1.py            # serves http://127.0.0.1:8765/ and opens it
```

`serve_face1.py` is stdlib-only (no deps), binds to `127.0.0.1`, and exposes a tiny JSON API the
page uses: `/api/ping`, `/api/plan` (real `bundle_run.py plan`, no DB), `/api/run` (writes the spec
and spawns the real pipeline with your Run-configuration flags), `/api/poll` (streams new log lines
+ per-stage status/counts from the run directory; returns real results when finished), `/api/cancel`.
Firing a run executes the real pipeline exactly as the CLI would — nothing is faked. If the DB/stack
is down (or a spec has no oracle), the run **fails honestly** and the UI shows the real failure and
log tail rather than a fabricated result.

> Note on specs: the gallery/token specs describe *structure*. A real run fires the whole chain
> (Core really materializes `fw_final`, the sieve really prunes, the Reader really reassembles), but
> a token spec's candidates aren't runnable programs, so the Executor has no oracle — Face 3 says so
> and points you to wire a HEAD/TAIL frame. A runnable spec (e.g. `usecases/perf_opt`) goes fully
> green in the recorded historical campaign — 72 candidates, 72 PASS, formal
> **Pareto front 13**. Re-run it for current evidence.

## Design

Deliberately **distinct from Face 2** (a blue graph/matrix drawing canvas): Face 1 is a
violet + amber *guided composer* with a stepper rail and a live count meter — a different
metaphor for a different job. It shares the product family only in the small (rounded cards,
soft shadows, plain-language everywhere, bilingual **EN/RU**, keyboard-complete, dark mode,
reduced-motion aware). No `red`/`green` as brand color — those stay reserved for Face 2's
forbid/require semantics.

The "shape of freedom" picker maps to fwgen authoring **aliases** (`choose_one`,
`choose_k(k)`, `permute`, `permute(k)`, `feature_subset`) — the same "never type a verb"
contract the spec guide describes — with the two repetition shapes emitting the raw engine
verb (`FW_PermutR(k)`, `FW_CombiR(k)`) behind a "more shapes" reveal.

## Using a generated spec

Download the `.toml`, drop it into its own folder, and:

```bash
python3 bundle_run.py plan my_task/          # honest count + budget class, no DB
python3 bundle_run.py my_task/ --db my_task \
  --execution-policy-profile generated-default \
  --analyzer "latency_ms:min,throughput_rps:max" --analysis-mode formal --run-id r1
```

The downloaded spec and its later-generated candidate bodies are untrusted by default, so the
example uses the fail-closed container profile. The spec plans and enumerates as-is. Wiring the
oracle (the `HEAD`/`TAIL` frame that makes each
candidate print your goal metrics and set its verdict) is the follow-up engineering step —
Face 1's job is to get you a validated spec and an honest count with zero framework vocabulary.

## Historical verification record

The bullets below describe the campaign that accompanied this prototype. They
are not proof of the current checkout: raw browser and Bundle run directories
are not versioned here.

- The embedded cardinality math is cross-checked against `fwgen.spec_cardinality_plan` for all
  10 templates and every shape (`choose_one`/`choose_k`/`feature_subset`/`permute`/`permute(k)`/
  `FW_PermutR`/`FW_CombiR` and mixed specs) — JS count == fwgen count, tier `EXACT`, all specs
  load under `strict=True`.
- Renders headless (Firefox) with no JS errors in light and dark themes — including the confirm
  dialog, the staged progress window, the normal/detailed log windows, and the Face 3 results
  (winners, Pareto plot, provenance) in both themes.
- **Real backend was exercised end-to-end:** `serve_face1.py` serves the page; `/api/plan` runs the real
  planner (no DB); `/api/run` + `/api/poll` fired the real pipeline and traced every stage live
  (gen→core→reader→executor→analyzer) from the run journal; a runnable spec (`usecases/perf_opt`)
  completed green — real outcomes **72 PASS / 0 fail**, real **Pareto front 13** over 72 points —
  and the real Face 3 rendered that data. A DB-down / no-oracle run surfaces the real failure
  honestly instead of a fabricated result.
