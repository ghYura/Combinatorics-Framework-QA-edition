# 29 — Face 1 (task intake) + the real Run/trace/results backend

> **Verification status (2026-07-21):** this is a dated implementation report, not a fresh
> end-to-end run record. The current audit verified its backing code through the repository test
> suites; use `generator_trunk/intake/README.md` for present operator instructions and the
> [current code audit](CURRENT_CODE_AUDIT_2026-07-21.md) for component boundaries.

**Status:** built & verified on this machine, 2026-07-02. **Scope:** the newcomer-facing
**Face 1** ("describe your task") from [26_PLAN3_THREE_FACES_UX.md](26_PLAN3_THREE_FACES_UX.md),
plus the full **Run → progress → logs → Face 3** flow and a stdlib companion server that makes
that flow **actually fire and trace the real Bundle pipeline**.

> Faces recap (doc 26): **Face 1** describe the task → **Face 2** draw the relations
> (`constraints/editor.py`, already shipped) → the engine runs → **Face 3** read the verdict.
> This document covers the Face-1 build and the real run/trace/results wiring that also renders a
> first Face-3 surface.

> **Update — 2026-07-04 (control panel for everything).** The Review step's Run-configuration panel
> was rebuilt into a full **control panel** that exposes and drives *every* `bundle_run.py` parameter
> across every Bundle component (identity, language, transport, executor pool, execution policy &
> sandbox, budgets & safety, repeat policy, seed bias, timeouts, ports, infra paths, stress mode,
> iterate loop, diagnostics) — grouped into collapsible, dependency-aware sections, RU/EN, light/dark.
> A **backend selector** picks **Local (full control)** — the default, driving `bundle_run.py`
> directly with the whole flag surface — or **Gateway (EaaS)**, the multi-tenant engine's safe subset.
> DB credentials/hosts stay **read-only, inherited from the server env** (never a browser field). This
> also fixed a **run-breaking bug**: the server projected the gateway-owned `db_name`, which the
> gateway rejects (`PERMISSION_DENIED`), 500-ing every real gateway run; the UI's "Workers" drove a
> stress-only flag and `executor_pool` was never wired. The "no missing parameter" contract is
> enforced by `generator_trunk/test_face1_control_panel.py` (UI `FIELDS` ⇔ server `_RUN_FLAG_SPECS` ⇔
> the real `cli.py` run parser). See the revised Part B/C.

## Deliverables (what landed)

| File | What it is |
|---|---|
| `generator_trunk/intake/face1.html` | Single-file, zero-dependency, offline-capable Face-1 UI + the Run/progress/log/Face-3 flow. |
| `generator_trunk/intake/serve_face1.py` | Stdlib-only local companion server: serves the page and exposes a JSON API that fires **real** `bundle_run.py` and traces it. |
| `generator_trunk/intake/README.md` | Operator/维护 notes for both files (usage, modes, verification). |

Nothing in the proven data plane (Core/Reader/Executor/Analyzer) changed; this is the
presentation + orchestration surface only.

---

## Part A — Face 1 UI (`intake/face1.html`)

### A.1 Purpose

Let a non-expert describe a combinatorial task in plain language and get a **valid `fwgen` spec**
(TOML) out — **without ever typing an `FW_` token** — with an **honest live candidate count**. It is
the on-ramp to `fwgen` (spec intake) named in doc 26.

### A.2 Visual identity (deliberately distinct from Face 2)

Face 2 (`constraints/editor.py`) is a blue graph/matrix **drawing canvas**
(`--forbid` red / `--require` green / `--accent #3b6ef5`). Face 1 is a **guided composer**: a dark
violet **stepper rail**, a **violet + amber** palette, and a persistent **honesty meter** on the
right. Shared product-family traits only: rounded cards, soft shadows, plain-language everywhere,
**RU/EN** (single `T` dictionary; EN default, one-click RU), dark mode, keyboard-complete,
reduced-motion aware, `localStorage` persistence. `red`/`green` stay reserved for Face-2 semantics.

### A.3 The five steps

1. **Start** — name the task; or pick one of 10 **templates** that abstract the real sub-folders.
2. **Moving parts** — add unlimited *dimensions*; per dimension list options (row 0 = baseline) and
   pick a **shape of freedom**; **reorder freely** (drag the `⠿` handle or the `▲ ▼` buttons) — the
   order is the `FW_Seq` the engine composes.
3. **Sudden actions** — optional "what-if this *also* happened?" events (`FW_Optional`).
4. **What success means** — goals to optimise (direction auto-inferred from the metric name) and
   failure verdicts (`custom_vars`).
5. **Review & export** — plain-language summary, generated `.toml`, **Run configuration**, the exact
   CLI command, and the **Run** button.

### A.4 The "shape of freedom" picker (the heart)

Each shape maps to an `fwgen` authoring **alias** (no `FW_` token) or, for the two repetition
shapes, a raw engine verb behind a "more shapes" reveal. Counts mirror `fwgen.verb_output_count`
exactly (computed in JS with `BigInt`):

| Plain-language shape | Emitted spec | Count for n options |
|---|---|---|
| pick exactly one | `alias = "choose_one"` | n |
| pick k of them | `alias = "choose_k(k)"` | C(n,k) |
| any combination | `alias = "feature_subset"` | 2ⁿ |
| put all in order | `alias = "permute"` | n! |
| order k of them (adv.) | `alias = "permute(k)"` | P(n,k) |
| sequence of k, repeats (adv.) | `verb = "FW_PermutR(k)"` | nᵏ |
| pick k, repeats (adv.) | `verb = "FW_CombiR(k)"` | C(n+k−1,k) |
| sudden action | `alias = "optional_action"` | ×(n+1) multiplier |

### A.5 Honest cardinality meter

The right-hand meter mirrors `fwgen.spec_cardinality_plan` stage-for-stage
(raw → per-slot → mandatory → optional → final, `BigInt`) and tags confidence
**exact / at most / unknown** (icon + text, never colour alone). Run class comes from
`bundle/resources.ResourceThresholds` defaults: **S** ≤ 500, **B** ≤ 50 000, **L** ≤ 5 000 000,
else **X**. Because Face-1 specs declare no constraints, post-sieve == mandatory (EXACT), so the
number reconciles with what `bundle_run.py plan` prints.

### A.6 Template gallery (abstractions of the sub-folders)

Ten one-click starting points, each abstracting a real implementation family:
`usecases/perf_opt`, `usecases/event_order`, `usecases/ml_eval`, `tryout_own`/`api_probe`,
`fintech_oot/batches`, `llm_loop/redteam`+`specs`, `llm_transformer_campaign`/`db_config`,
`usecases/etl_pipeline`, `model_usecases/nas_micronet`, and a blank.

### A.7 Emitted spec (example)

```toml
spec_version = "1"
title = "perf tuning"
args  = ["mode=perf_tuning"]

[[goals]]
key = "throughput_rps"
dir = "max"

[[slots]]
sheet = "ALGORITHM"
key   = "algorithm"
alias = "choose_one"
values = ["naive", "blocked", "simd"]
```

The spec loads under `fwgen.load_spec(..., strict=True)` and plans correctly. Wiring the *oracle*
(a HEAD/TAIL frame so each candidate prints goal metrics and sets a verdict) is a later,
expert step — Face 1's job is a validated spec + an honest count with zero framework vocabulary.

### A.8 Checked-in runnable suites

Both Face 1 implementations read the same `intake/automation_scenarios.json` catalog. It currently exposes:

- seven historical Automation Scheme Studio exhaustive tiers;
- four **recursive higher-order feedback** scenarios: the 32-candidate circuit smoke, the 8-candidate `FW_Group`/nested-brace operator smoke, and the two deferred third/fourth-order searches;
- three checked-in AI Combinatorial Testing Platform exact-control scenarios (`AI00`, `AI01`, and `AI70`);
- one advanced `AIRG` release-gate breakpoint entry backed by a reviewed dynamic materializer.

Selecting a static entry runs its checked-in TOML without mutating the current
composer/workbook. The shared Automation profile forces Python, sharded
candidates, the parallel Executor, the seven formal control objectives, and
the sibling-SUT resolver. Runtime-cardinality entries also force
`--allow-extreme` plus a reviewed `--override-budget` reason.

`AIRG` is deliberately not static: inspect or launch creates a fresh
2/4/8/16/32-level held-out spec in an isolated temporary directory and checks
the generator's planted answers against the independent runtime oracle. Its
immutable profile runs 2,560 network-disabled, zero-cost local controls and
removes prompt-export settings plus known provider credentials. That GUI run
validates apparatus only; target-AI response exchange is separate. No profile
places database passwords or other secrets in browser state.

---

## Part B — the Run flow (UI)

The **Review** step carries the full **control panel** (rebuilt 2026-07-04). Every control maps to a
real `bundle_run.py` flag and updates the printed command live; fields are grouped into collapsible
sections and gray out (with the reason) when a dependency is unmet or the chosen backend can't accept
them:

| Group | Controls (→ `bundle_run.py` flag) |
|---|---|
| **Core & backend** | execution **backend** (Local / Gateway), `--lang`, run mode `--mode` (verdict/stress), `--db`¹, `--run-id`¹, `--iterations` (iterate) |
| **Analysis & seed bias** | `--analysis-mode` (goals-gated), `--seed-output`, `--seed-from`, `--exploration-floor`, `--min-winner-support` |
| **Constraints · Sieve (Face 2)** | `--sieve`, `--draw`, `--draw-exact` |
| **Concurrency & transport** | `--candidate-sink`, `--executor-pool`², `--grpc-host`/`--grpc-port` (grpc sink), `--executor-compiler` (java) |
| **Execution policy & sandbox** | `--execution-policy-profile`, `--sandbox-network-allowlist`, `--sandbox-candidate-env`, `--executor-tolerate-outcomes`, `--sandbox-policy` |
| **Budgets & safety** | every `--budget-*`, `--cost-per-candidate`, `--override-budget`, `--allow-extreme`, `--unleash-initial-productivity-power` |
| **Repeat policy** | `--repeat`, `--repeat-policy`, `--repeat-scope`, `--repeat-environments` |
| **Stress mode** | `--base-url`, `--workers`, `--duration`, `--ramp`, `--slo-p99`, `--err-budget` (only when mode = stress) |
| **Timeouts · ports · infra** | `--core/-reader/-executor-timeout`, `--main-port`/`--results-port`, `--scratch-root`, jars/props/executors, `--java-cmd`/`--javac-cmd`/`--python-cmd`, `--config-file` |
| **Compatibility & diagnostics** | `--legacy-scratch`, `--legacy-handoff`, `--debug` |
| **Database connection** | read-only host/user/port from the server env; passwords never leave the server |
| (goals, from step 4) | `--analyzer "k:dir,…"` |

¹ Local mode only — the Gateway backend owns the db name / run id. ² Requires Java + loose-files, K=1.

The panel is a **declarative registry** (`FIELDS` in `face1.html`) mirroring the server's
`_RUN_FLAG_SPECS`; adding a Bundle flag is one row on each side. The `backend` control routes
`/api/run` to the **Local direct** launcher (`serve_face1._spawn_run_direct` → the full command) or
the **Gateway** engine (`_spawn_run` → `GatewayEngine.submit`, safe subset). `/api/ping` advertises
the gateway limits, grpc availability, and the read-only DB coordinates the panel displays.

**Run → confirmation.** The huge **Run** button opens a dialog:
*"Would you like to add constraints on the relations between particular instances?"* —
**Yes** (apply constraints via the sieve / draw in Face 2) or **No, Combine!** (combine as-is).

**Progress window.** A separate window shows every pipeline stage — Generate · Core · Sieve (if
enabled) · Reader · Executor · Analyzer (if goals) — with live status, a progress bar, and a
per-stage summary line.

**Log windows.** **Show log** = the high-level `[stage] …` trace; **Show detailed log** = everything
consumed & printed (in real mode this is the pipeline's actual stdout/stderr). Both copy/download.

**Face 3 — results.** When the run finishes: a pass/fail hero + proportion bar, **winners by goal**,
a **Pareto-front** plot, "what your rules did" provenance, a candidate table, and CSV export.

### Two modes

- **Offline preview** (page opened as a `file://`, no server): Run plays a faithful **simulation** —
  candidate counts are real (same plan), per-candidate verdicts/metrics are illustrative and
  clearly labelled. Fallback so the single file is always useful.
- **Real backend** (server running): Run **actually fires** the pipeline — see Part C.

The page decides automatically by probing `/api/ping` on load (`detectBackend()`); the rail shows
**● Real backend** or **○ Offline preview**.

---

## Part C — the real backend (`intake/serve_face1.py`)

Stdlib only (`http.server`, `subprocess`, `threading`, `json`); binds `127.0.0.1`; same posture as
`constraints/serve.py`. It serves `face1.html` and exposes:

| Endpoint | Method | Purpose |
|---|---|---|
| `/` (`/index.html`, `/face1.html`) | GET | serve the page |
| `/api/ping` | GET | `{ok, backend:"real", db_env, results_env, cwd, python}` — the mode probe |
| `/api/plan` | POST `{toml}` | run real `bundle_run.py plan` (no DB) → `{ok, returncode, stdout, stderr, plan}` |
| `/api/run` | POST `{toml, config}` | write the spec + spawn real `bundle_run.py`; returns `{token, run_id, db}` |
| `/api/poll` | GET `?token=&log=N` | new stdout/stderr lines + per-stage status/counts; real results when finished |
| `/api/cancel` | POST `?token=` | `SIGTERM` the run's process group |

### C.1 How a real run is fired

`/api/run` writes the posted TOML into a fresh spec dir and spawns, from `generator_trunk/`:

```
python3 bundle_run.py <spec_dir> --db <db> --run-id <id> --runs-root <dir> \
  --lang py --execution-policy-profile <profile> [--sieve] \
  [--analyzer "<k:dir,…>" --analysis-mode <mode>] [--workers N]
```

`--runs-root` + `--run-id` are chosen by the server, so it knows exactly where the run directory
will be. The child inherits the server's environment (so `BUNDLE_*` DB creds and `PATH`/`JAVA_HOME`
carry through). A daemon thread drains the merged stdout/stderr into a per-token buffer.

### C.2 How tracing is real (not parsed guesses)

Progress comes from the **run journal** the pipeline writes (see doc 08 / `bundle/journal.py`):
`state.json` (per-stage status: `RUNNING`/`SUCCEEDED`/`FAILED`/…) and `stages/<name>.json`
(the versioned `StageResult` with `counts` such as `fw_final`, `post_sieve`, `candidates`,
`pass`/`fail`). `/api/poll` reads these each tick and returns a compact
`{run_status, stages:{<name>:{status,counts}}}`, plus the new raw log lines since the client's
cursor (the detailed log).

### C.3 How results are real

When the process exits, `/api/poll` returns a `results` object assembled from the real artifacts:

- **outcomes / pass / fail / processed** ← `executor-summary.json` (`outcomes{PASS,DOMAIN_FAIL,…}`).
- **goals + Pareto front** ← `provenance.json` (`goals[{key,mode}]`, and `candidates[]` = the
  non-dominated front with per-candidate `objectives`, `outcome`, `source_ref`,
  `reason_non_dominated`).
- **all-candidate points** for the scatter ← parsed from the harvested corpus `metrics.kv`.
- **counts** (mandatory / post-sieve / candidates) ← the stage `counts` above.

Face 3 renders exactly this; no data is invented.

### C.4 Honesty rails

Firing a run executes the real pipeline exactly as the CLI would — there is no fake path. If the
DB/stack is down, or a spec has no oracle, the run **fails honestly**: `state.json` records the
`FAILED` stage, the UI shows a failure banner + the real log tail, and Face 3 is not fabricated.

---

## How to run it

```bash
cd generator_trunk
# Reader/Executor require Java 25 — put a matching JVM on PATH FIRST (see Limitations):
export JAVA_HOME=/usr/lib/jvm/jdk-25.0.3-oracle-x64 && export PATH="$JAVA_HOME/bin:$PATH"
# If your local Postgres needs a password:
export BUNDLE_MAIN_DB_PASSWORD=$PGPW BUNDLE_RESULTS_DB_PASSWORD=$PGPW
python3 intake/serve_face1.py           # serves http://127.0.0.1:8765/ and opens it
#   --port <N>       choose the port (default 8765)
#   --no-browser     don't auto-open
```

Opening `intake/face1.html` directly (no server) still works — it runs in offline-preview mode.

---

## Limitations & honest notes

- **Java 25 required for a full run.** Reader and Executor target Java 25; Core, Analyzer, and the
  shared library target Java 21. With Java 21 on PATH, Reader/Executor raise
  `UnsupportedClassVersionError`. Point
  `JAVA_HOME`/`PATH` at a Java 25 JVM before launching the server. (On this machine:
  `/usr/lib/jvm/jdk-25.0.3-oracle-x64`; the default `java` was GraalVM 21.)
- **Token specs have no oracle.** The gallery/token specs describe *structure*. A real run still
  fires the whole chain (Core materialises `fw_final`, the sieve prunes, the Reader reassembles),
  but a token spec's candidates aren't runnable programs, so the Executor has nothing to judge —
  Face 3 says so and points to wiring a HEAD/TAIL frame. A runnable spec (e.g. `usecases/perf_opt`)
  goes fully green.
- **Offline preview is a simulation.** Real counts, illustrative verdicts/metrics — labelled as such
  in the progress window and Face 3.
- **`--sieve` on a Face-1 spec is a no-op** until the spec actually carries constraints (draw them in
  Face 2). Post-sieve then equals mandatory — honest, not hidden.
- **Security.** The server binds to localhost only and runs the real Executor (which sandboxes
  candidates per the chosen execution policy). Treat it as a local dev tool.

---

## Verification (observed 2026-07-02)

- **UI:** page JS syntax clean (`node --check`); JS cardinality matches `fwgen.spec_cardinality_plan`
  for all 10 templates and every shape (`choose_one`/`choose_k`/`feature_subset`/`permute`/
  `permute(k)`/`FW_PermutR`/`FW_CombiR` + mixed), all `EXACT`, all load under `strict=True`; headless
  Firefox render (light + dark) with no JS errors across Start / Moving-parts / confirm dialog /
  progress window / normal+detailed logs / Face 3.
- **Server:** `py_compile` clean; `/api/ping` → `backend:"real"`; `/api/plan` ran the real planner
  and wrote `plan.json` (no DB).
- **Real run, structural token spec:** fired and traced live — `gen ✓ → core ✓ (fw_final=12) →
  reader ✗` — the Reader failure surfaced honestly with the real reason.
- **Real run, runnable spec (`usecases/perf_opt`), green end-to-end:** stages traced live
  `gen→core→reader→executor→analyzer` all `SUCCEEDED`; real outcomes **PASS 72 / 0 fail**;
  real goals `throughput_rps:max, latency_ms:min, memory_mb:min`; real **Pareto front 13** over
  **72** candidate points — matching doc 14 / `usecases/README.md`. The real Face 3 rendered that
  data (★ REAL RUN badge, winners, real scatter with 13 highlighted front points).

---

## Cross-references

- [26_PLAN3_THREE_FACES_UX.md](26_PLAN3_THREE_FACES_UX.md) — the Faces plan this implements (Face 1
  intake acceptance; Face 3 report goals).
- [05_SPEC_V1_AUTHORING_GUIDE.md](05_SPEC_V1_AUTHORING_GUIDE.md) — the aliases the shapes compile to.
- [06_PLANNING_BUDGETS_AND_COUNTS.md](06_PLANNING_BUDGETS_AND_COUNTS.md) — the count vocabulary and
  run classes the meter mirrors.
- [08_RUN_CONTRACTS_AND_SCHEMAS.md](08_RUN_CONTRACTS_AND_SCHEMAS.md),
  [09_READER_EXECUTOR_AND_RESULTS.md](09_READER_EXECUTOR_AND_RESULTS.md) — the run journal,
  `executor-summary.json`, and `provenance.json` the server reads for tracing and results.
- [../ZEN_OF_COMBINATORICS.md](../ZEN_OF_COMBINATORICS.md) — "the verb is the shape of the freedom",
  which the shape-picker turns into plain language.

## Follow-ups (not done today)

- Face 2 hand-off from Face 1's "Yes" (open the draw editor pre-Core in real mode, instead of just
  passing `--sieve`).
- Enrich the scatter with per-candidate ids from `metrics.kv`/results DB (currently front points are
  id-linked; background points are anonymous).
- Optional: a first-class `bundle ui` entry point that launches any face standalone (doc 26 open
  question).
