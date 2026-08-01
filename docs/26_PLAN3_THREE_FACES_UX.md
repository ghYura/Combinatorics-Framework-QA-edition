# 26 — PLAN-3: The Three Faces of Bundle (end-user UX)

**Status (2026-07-21):** roadmap with partial implementation, not a wholly future plan. Face 1 and
its local run/trace surface are implemented in `generator_trunk/intake` (see
[document 29](29_FACE1_INTAKE_AND_REAL_RUN.md)); Face 2 has the constraint editor and exact-impact
mode; Face 3 remains less complete than the roadmap. **Author seed:** Yuri Baranov.
**Scope:** the *presentation* layer — how a non-expert meets the Bundle, drives it, and reads its
verdict. Not the Core/Reader/Executor mechanics (those are proven); this is the **first-impression
usability surface**: three "faces" a stranger touches, in order.

> The Bundle's power is real but its first impression is a separate product problem. A newcomer
> forms an opinion in three moments: **(1)** how easily they can *describe* a combinatorial task,
> **(2)** how intuitively they can *shape* it by drawing allowed/forbidden relations, and **(3)**
> how clearly they can *read* what the whole run concluded. Each is a "face." Each must feel like a
> finished product, independently.

```
FACE 1  describe the task ──► FACE 2  draw the relations ──► [ Core·SIEVE·Reader·Executor·Analyzer ] ──► FACE 3  read the verdict
 (AI-guide / XLSX)               (forbid / require links)            the engine (proven)                    (winners, Pareto, pass/fail)
```

The faces map onto the existing chain: Face 1 feeds **fwgen** (spec intake), Face 2 is the
**`--draw` editor → sieve** seam, Face 3 renders the **Analyzer + Results DB** output.

---

## Face 1 — "Describe your task" (intake)

**Intent.** A user states *what to combine* with zero framework vocabulary — through an
**AI guide/instructor** (conversational) and/or a **spreadsheet** they already know (XLSX). The
system infers slots, verbs, baselines, and goals; the user never writes a verb like `FW_Permut`.

**Current state.**
- `testme5` is the outward-facing Bundle guide/instructor (interpret + generate scenarios, answer
  "what can you do?"); the intended on-ramp for natural-language task description.
- `fwgen` reads `specs/*.toml|*.json|*.yaml`; smart auto-inference already exists (baseline = first
  value, goal direction from the metric lexicon, reduction strength vs budget).
- XLSX lineage is real: the v25 "Pro Data Engine" GUI and `fwgen_gui.py`'s **Batch XLSX→JSON** turn
  a workbook into specs. `constraints/graphspec.py --spec … --sheets-json` already pulls a real
  spec's sheets/values out for Face 2.

**Gaps → TODO.**
1. **One canonical intake doc + wizard.** A single "describe a task" entry that branches to
   *(a)* AI-guide chat or *(b)* "upload an XLSX". Output of both = a validated fwgen spec + a
   human-readable summary ("6 ops permuted × 4 optional headers × … = N candidates").
2. **XLSX template + linter.** A starter `.xlsx` (one sheet per dimension, first row = baseline) and
   a validator that explains, in plain language, what each column became (slot/verb/goal) *before*
   generation — the same "always-show-words" posture as the sieve.
3. **AI-guide → spec contract.** Pin the guide's output to the spec schema (`05_SPEC_V1_*`), with a
   confirmation screen ("here's what I understood; edit before running"). Round-trip editable.
4. **Goal elicitation.** Turn "what does success mean?" into `[[goals]]` (max/min axes) and
   `custom_vars` verdict codes without the user knowing those names.
5. **Pre-run cardinality preview (honest).** Reuse `fwgen.spec_cardinality_plan` to show the
   confidence-tagged count (mandatory → post-sieve **bounded** → ×optional) so the user sees the
   combinatorial wall *before* committing (ties into `06_PLANNING_*`).

**Acceptance.** A non-expert produces a runnable spec from either an English description or an XLSX,
sees a plain-language summary + bounded count, and never types a `FW_` token.

---

## Face 2 — "Draw the relations" (this iteration's build)

**Intent.** The user hand-draws **logical links between values** — both *forbidden* ("never
together", red) and *required/sought* ("only together", green) — with human-intuitive semantics,
and the pipeline applies them automatically. The lines are **logical** (entity↔entity), never
pixels.

**Done in this iteration (the new baseline).**
- **Unified single-file editor** `constraints/editor.py` (zero-dep, offline) merging the three
  earlier demos (bond-matrix / graph-threads / Blockly-`when`) into one screen:
  - **both polarities** — red **forbid**, green **require** (искомое);
  - **gates in the UI** — any / adjacent / within N;
  - **n-ary bonds** — join 3+ value-nodes (a hub), matching the n-ary sieve engine;
  - **params + `when` formula bonds** — the advanced predicate tier, in plain language;
  - **round-trip** — loads the spec's existing constraints/params back onto the canvas;
  - **per-link condition editor** — select any link to edit its *logical conditions* in place:
    polarity (forbid/require), gate (any / adjacent / within N), the `when` formula (inline), and the
    member value **sets** (chips + add → turns a singleton link into a Many:Many one);
  - **nested block formula builder** (option) — a Текст/Блоки toggle in the formula dialog: a typed
    AST of blocks plugged into `＋` slots (compare / and·or / not / arithmetic / sheet·param / number),
    nesting arbitrarily, compiled live to a `when` string (no npm), parallel to the text field;
    **drag-and-drop** from a block palette + drag-to-rearrange (HTML5 DnD), alongside click-to-fill;
  - **exact live impact** (option, `--draw-exact`) — exact removed/kept over the full assembled space
    `fw_final × fw_optX` from the live DB, parallel to the default offline estimate;
  - **live impact** preview ("removes N of M"), per-link plain-language list, RU/EN.
- **Auto-invoke** `constraints/serve.py` + `bundle_run.py --draw`: the chain pauses **before Core**,
  serves the editor, opens **Firefox**, and blocks on **Submit**; the drawn sidecar POSTs back and
  the run resumes. **Empty submit = no-op** (as if `--sieve` was off).
- **Engine** generalized to **n-ary** bonds (`constraints/sieve.py`), 2-sheet path bit-identical;
  schema documented (`constraints/sidecar_schema.md`); tests cover n-ary/require/gates + the server
  round-trip.

**Gaps → TODO (polish to product grade).**
1. **Exact live impact from the real DB** — *now ships as an opt-in* (`bundle_run … --draw-exact`,
   runs after Core). The editor POSTs each change to a local `/impact` endpoint backed by
   `sieve.exact_impact`, which counts removals over the WHOLE assembled space
   `|fw_final| × (1 + Σ|fw_optX|)` — **honest about FW_Optional** (mandatory bonds kill whole
   fw_final rows × the optional multiplier; optional bonds kill assembled candidates), bounded by a
   `cap` (above it → falls back to the estimate). The fw_final/fw_optX rows are **decoded once** per
   draw session (`decode_assembly`) and the live preview reuses them DB-free (`impact_over_rows`) —
   the connection is dropped right after decoding. The default `--draw` (before Core, offline
   co-occurrence estimate) is unchanged.
2. **Curved/role-aware edges.** Straight chords can cross unrelated nodes; route edges around
   columns; show direction/order when a gate implies it.
3. **Templates & presets.** "mutual exclusion", "requires", "at most one of", "pairwise different"
   — one click instead of many; teach the vocabulary by example (ties to `14_SCENARIO_CATALOG`).
4. **Undo/redo + multi-select + drag-rearrange** of value-nodes; large-graph minimap/zoom.
5. **A `when`-formula visual builder** — *ships* as an OPTION in the formula dialog (a **Текст /
   Блоки** toggle): a **nested, typed block builder** (Blockly-grade composition). You click `＋`
   slots and pick blocks (`compare`, `and/or`, `not`, `+ − ×`, `sheet.param`, `number`) that nest
   into a typed AST — bool slots accept comparisons/logic, arith slots accept arithmetic/leaves — and
   it compiles live to a `when` string (e.g. `((A.charge * C.charge) > 0)`). **Drag-and-drop ships**
   too (HTML5 DnD, no npm): a palette of draggable blocks dropped into typed `＋` slots (green/red
   compat highlight), plus drag-to-rearrange existing subtrees — alongside the click-to-fill menu.
   Supersedes the separate `blockly_when/` app and the earlier flat token palette. Inline text editing
   of a formula per link also ships (the per-link condition editor).
6. **Conflict/É coverage hints.** Warn when a `require` is so strong it would empty the space, or
   when two rules contradict; offer known-pass/known-fail controls (the assessment's caveat).
7. **Import/replace an arbitrary `sidecar.json`** from disk; export shareable links.
8. **Accessibility AA**: full keyboard authoring, screen-reader labels for edges, color-blind-safe
   palette (not red/green alone — add icons/patterns), focus management in the dialog.
9. **Mobile/touch** drawing.
10. **Retire the demos.** Fold `bondmatrix.py`/`graphspec.py`/`react_flow/`/`blockly_when/` behind
    `editor.py` (keep their headless cores as tested libraries; one UI to maintain).

**Acceptance.** A first-timer, with no instruction beyond the on-canvas hint, draws a forbidden and
a required relation, sees the impact change, presses Submit, and the run honors exactly those rules.

---

## Face 3 — "Read the verdict" (results & conclusions)

**Intent.** After a run, the user *immediately understands* what happened: which candidates won,
which failed and why, how the goals traded off — without reading raw tables or logs.

**Current state.**
- The **Analyzer** (`11_ANALYZER_GUIDE`) collects `app=…` key/values and aggregates by goals; the
  **Results DB** holds per-candidate verdicts (`FW_VAR`, `results_v2`); the **run journal**
  (`run.json`/`state.json`, STEP 5) records every stage's counts/invariants; `09_READER_EXECUTOR_*`
  documents the verdict surface; `bundle_bred_winners_*` shows the "winners" idea exists.
- Today this is mostly machine-readable / CLI text — strong substance, weak presentation.

**Gaps → TODO.**
1. **A run report page** (same zero-dep, single-file posture as the editor): headline verdict
   (N candidates → P passed / F failed), the **winners** by each goal, and the **goal Pareto front**
   plotted, with drill-down to a candidate's source + its `FW_VAR`/output.
2. **"Why did this fail?"** — surface the TAIL verdict + the candidate's captured `app=…` line and
   stderr, in plain language, per failing candidate.
3. **Sieve provenance in the report.** Show what the drawn bonds removed (the Face-2 → Face-3 loop):
   "your rules pruned X of Y before execution" with the per-rule `matched`/`overlap` stats the sieve
   already records — so the user sees their own drawing reflected in the outcome.
4. **Trends across runs** (resume/`runs-root`): compare two runs, regressions, deltas.
5. **Exports**: CSV/JSON of winners, a shareable static HTML report, links back into the spec/editor
   to iterate ("edit the rules and re-run").
6. **Honesty rails.** Carry forward the bounded-count and coverage caveats (a removed case can hide a
   defect) into the report, not just the plan.

**Acceptance.** A stakeholder opens one page and can state, unaided, what won, what failed and why,
how their drawn rules shaped the space, and what to change next.

---

## Cross-cutting (applies to all three faces)

- **Design system.** One palette/typography/spacing (the editor's CSS variables are the seed:
  `--forbid` red, `--require` green, `--accent`, soft shadows, rounded cards). Shared header/footer,
  shared empty/error/loading states. Zero-dependency, single-file, offline-first — the reliability
  bet behind the `--draw` build.
- **Plain language everywhere** ("always-show-words"): every machine fact has a human sentence.
- **Bilingual RU/EN** with a single i18n dictionary (already in the editor); default RU.
- **Accessibility (WCAG AA):** keyboard-complete, screen-reader labels, never color alone, visible
  focus, respects reduced-motion.
- **Performance budgets:** Face-2 canvas smooth to ~hundreds of nodes; Face-3 report renders large
  result sets via virtualization; intake preview is instant.
- **Reliability & trust:** offline by default; no hidden network; the same numbers shown in
  preview/dry-run reconcile with the real run (the sieve already guarantees this — extend the
  principle to Faces 1 and 3).
- **Telemetry (opt-in, local):** where users stall, so the on-ramp keeps improving.
- **Testing:** headless cores stay unit-tested (as `sieve`/`editor`/`serve` are); add a thin
  Firefox-headless screenshot smoke per face to catch JS/render regressions.

## Suggested milestones

1. **M1 — Face 2 to product grade** (build done; remaining: templates, curved edges, a11y AA,
   exact-DB impact, retire demos).
2. **M2 — Face 1 intake** (XLSX template + linter, AI-guide→spec confirmation screen, cardinality
   preview).
3. **M3 — Face 3 report** (single-file run report: winners, Pareto, why-failed, sieve provenance).
4. **M4 — Unify** the three under one design system + shared shell; cross-links (report → edit rules
   → re-run).

## Open questions

- Face 1: how far should the AI-guide auto-commit vs always require a confirm-and-edit step?
- Face 2: exact live-DB impact (after Core) vs the offline estimate — make it a toggle, or pick one?
- Face 3: ship as static HTML artifacts per run, or a small local viewer server (like `serve.py`)?
- Packaging: one `bundle ui` command that can open any face standalone, decoupled from a full run?
