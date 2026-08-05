# 04 — CLI and Lifecycle Reference

The entry point is `generator_trunk/bundle_run.py` (a shim for `python3 -m bundle` / `bundle.cli`).
Two shapes:

- **A run** — the default parser: `bundle_run.py <spec-dir> [options]`.
- **A subcommand** — `bundle_run.py <verb> ...` for `plan | doctor | resume | cancel | cleanup |
  constraints | iterate | bench | deploy | inventory | hygiene | architecture | coverage |
  capabilities | sut-manifests | release | provenance | report`.

> The verb list above is asserted against `bundle.cli._VERBS` by
> `test_bundle_cli_docs.py`, so a new subcommand cannot ship undocumented and this
> paragraph cannot quietly fall behind the CLI. `bundle_run.py --help` prints the
> same set as its epilog.

All commands resolve config with precedence **CLI > environment > config file > defaults**, render
secrets-free artifacts, and exit non-zero on a typed error (stack trace only with `--debug`).

## Lifecycle at a glance

```
plan ─▶ run ─▶ (interrupted?) ─▶ resume ─▶ ... ─▶ cleanup --dry-run ─▶ cleanup --yes
                    │
                    └▶ cancel   (terminate owned children, mark INTERRUPTED)
doctor / inventory / hygiene / deploy / bench  — side-effect-free or DB-stack lifecycle
iterate ─▶ run₁ ─▶ BundleSeed ─▶ biased run₂ ─▶ ... (bounded, goal-driven feedback)
```

## `plan <spec-dir>` — quantify before running (no Core/DB)

```bash
python3 bundle_run.py plan tryout_own/spec --out /tmp/plan_dir
```

Prints spec identity + sha256, the operator table, per-slot Core rows (each tagged EXACT / BOUNDED /
UNKNOWN), the mandatory product, optional multiplier, post-sieve estimate, final candidate count,
run class (S/B/L/X), resource estimates (Core/Results bytes, inodes, requests, duration — each with
assumptions), the dominant resource, warnings, and an `FW_Seq` graph hash. Writes `plan.json`
(`bundle.plan/v1`). **No PostgreSQL side effects.** Tuning flags: `--class-{smoke,bounded,large}-max`,
`--template-sample-bytes`, `--per-candidate-seconds-{min,max}`. See
[06_PLANNING_BUDGETS_AND_COUNTS.md](06_PLANNING_BUDGETS_AND_COUNTS.md).

## `<spec-dir>` — run the full chain

```bash
export BUNDLE_MAIN_DB_PASSWORD=$PGPW BUNDLE_RESULTS_DB_PASSWORD=$PGPW
python3 bundle_run.py tryout_own/spec \
  --db myrun --sieve \
  --analyzer "security_failures:max,latency_ms:min,correct:max" --analysis-mode formal \
  --execution-policy-profile networked-api-probe \
  --sandbox-network-allowlist secure-app \
  --sandbox-candidate-env TRYOUT_URL=http://secure-app:8025 \
  --run-id myrun-001
```

Key options (full list: `--help`):

| Option | Meaning |
|---|---|
| `--db NAME` | DB name (default: spec name) for main+results |
| `--lang {py,java}` | candidate language; `java` routes to the Java MainWatch Executor (Handoff v2 required; `--mode stress`/`--legacy-handoff`/`--analyzer` are refused for Java) |
| `--executor-compiler {adaptive,janino,ecj,javac}` | pin the Java Executor compiler backend (`-Dfw.exec.compiler`); default adaptive (Janino fast path, ECJ fallback) |
| `--main-port / --results-port` | DB ports (default 5433 / 5432) |
| `--sieve` | apply the spec's constraint sidecar between Core and Reader |
| `--analyzer "k:max,k2:min,..."` | run the Analyzer with these goals (default: off) |
| `--analysis-mode {formal,exploratory}` | formal = explicit goals only, corpus count required |
| `--execution-policy-profile {generated-default,networked-api-probe,trusted-local}` | execution policy; **no default** — a run refuses until one is chosen (`plan` needs none). `trusted-local` is unsandboxed |
| `--candidate-origin {reviewed-checked-in,locally-authored,generated,imported-untrusted,network-facing}` | where the candidate source came from, declared by the operator; required for `trusted-local`, which accepts only the first two |
| `--acknowledge-trusted-local REASON` | non-empty reason for unsandboxed host execution; required by `trusted-local`, persisted in the run manifest and re-verified on resume |
| `--sandbox-network-allowlist TARGETS` | container name(s) a networked-api-probe candidate may reach |
| `--sandbox-candidate-env NAME=VALUE,...` | env forwarded into the sandbox (credential-shaped names refused) |
| `--executor-tolerate-outcomes LIST` | tolerate a subset of BROKEN/TIMEOUT/INFRA_FAIL (WARNING not fail) |
| `--budget-* N\|none`, `--override-budget REASON`, `--allow-extreme` | budget gates (see doc 06) |
| `--unleash-initial-productivity-power` | lift the limiter: budget gate advisory (not blocking), X/extreme needs no `--allow-extreme` — Core at full power (recorded in the manifest; default off; see doc 06) |
| `--run-id ID`, `--runs-root DIR` | run identity / runs root |
| `--legacy-scratch`, `--legacy-handoff` | legacy compatibility paths (doc 16) |
| `--mode {verdict,stress}` | verdict = correctness; stress = load storm |
| `--candidate-sink {loose-files,sharded,grpc}` | Reader→Executor transport; gRPC is Java/verdict/v2/trusted-local only |
| `--grpc-host HOST`, `--grpc-port PORT` | gRPC endpoint; defaults `127.0.0.1:50061` (plaintext, unauthenticated) |
| `--executor-pool N` | N Java Executors; requires loose files, verdict, Handoff v2, and repeat K=1 |
| `--repeat K`, `--repeat-policy {local,disperse,nested}` | per-candidate repeats and placement policy |
| `--repeat-scope {metrics,all}`, `--repeat-environments E` | measurement-only or full-verdict repeat scope; E is required for nested K>1 |
| `--seed-output`, `--seed-from PATH` | write or consume Analyzer `bundle_seed.json` feedback |
| `--exploration-floor F`, `--min-winner-support N` | fail-closed bounds on seed-driven narrowing |
| `--config-file PATH`, `--main-db-* / --results-db-*`, `--*-jar`, `--*-props`, `--*-cmd` | config overrides |

On success: `✓ DONE — <db>: full Bundle chain green. run '<id>' (<dir>)`. Cross-stage invariants
are enforced; a failed CRITICAL invariant fails the run.

### Repeat/runtime compatibility

K=1 preserves the legacy single-sample behavior. For K>1 the launcher currently executes only
Python or Java with `--repeat-policy local` and `--repeat-scope metrics|all`, after probing the
selected Executor's repeat and results-schema capabilities. `metrics` runs the deterministic
verdict once and measures K times; `all` runs K complete verdicts. Disperse/nested are represented
in planning and the standalone Java control-plane seam but are refused by this launcher runtime.
`--executor-pool N` with N>1 is incompatible with K>1. The `--workers` option belongs to stress
mode and is not the Java Executor pool switch.

### Live gRPC compatibility

`--candidate-sink grpc` writes no on-disk candidate corpus. The launcher starts the Java receiver,
runs the streaming Reader, then adopts and waits for the receiver. It refuses Python, stress mode,
legacy handoff, secure policy profiles, and executor pooling. The channel has no TLS/authentication.
Reader targets loopback by default; the receiver separately binds explicit loopback and refuses
wildcard/non-loopback addresses. Firewall/interface isolation remains defense in depth.

## `resume <run-dir|run-id>` — continue without repeating valid stages

```bash
python3 bundle_run.py resume /tmp/fw_work/<db>/runs/<run-id>
```

Reuses each stage only if it `SUCCEEDED`, its critical invariants passed, its input hashes/artifacts
still match, and (DB stages) live counts match. A no-op resume of an unchanged successful run reuses
**all** stages (verified: gen/core/sieve/reader/executor/analyzer all reused, no duplicate rows,
exit 0). A changed spec/missing candidate invalidates that stage and everything downstream. A stage
stuck `RUNNING` (crash) is refused until reconciled. Pass the **full run directory path** when a bare
run-id is ambiguous across scratch roots.

## `cancel <run-dir|run-id>` — stop a running run safely

Marks intent, terminates only this run's owned child processes (identity-checked), sets run/stage
status to INTERRUPTED. Does not touch unrelated processes.

## `cleanup <run-dir|run-id>` — scoped, identity-checked deletion

```bash
python3 bundle_run.py cleanup <run-dir> --dry-run     # enumerate only; deletes nothing
python3 bundle_run.py cleanup <run-dir> --yes         # actually delete (run files + results_v2 rows)
python3 bundle_run.py cleanup <run-dir> --dry-run --retention-seconds 86400
```

Dry-run lists files/bytes, the DB (and whether it matches the manifest), scoped `results_v2` row
count, credential-shaped files, age vs retention. **Refuses** when `--db` does not match the run
manifest's db_name ("does not match run manifest's db_name … refusing to clean up"), refuses
symlink/traversal/shallow paths, and never deletes outside the run root. Verified: dry-run leaves the
tree byte-unchanged.

## `doctor` — environment diagnosis (doc 03)

```bash
python3 bundle_run.py doctor [--deploy] [--json PATH]
```

## `iterate <spec-dir>` — bounded Analyzer feedback

```bash
python3 bundle_run.py iterate tryout_own/spec --iterations 3 \
  --analyzer "latency_ms:min,correct:max" --stop-when-stable 2
```

Every iteration emits/consumes a `bundle_seed.json` with `schemaVersion=1`; the
`<base-run-id>-iterate.json` lineage artifact uses `bundle.iterate/v1` and records the stopping
status. Explicit Analyzer goals are required. `--seed-from` may initialize iteration one, while
`--exploration-floor` and `--min-winner-support` prevent unsupported over-narrowing.

## `deploy {validate,up,down,status}` — local DB stack (doc 03)

A new `deploy/.env` receives checkout-scoped volume names. `up` fails closed and preserves data
if a legacy volume answers on its port but rejects the configured credentials.

```bash
python3 bundle_run.py deploy up        # unique volumes; port + authenticated SQL health
python3 bundle_run.py deploy down       # KEEPS data; --volumes permanently deletes current volumes
```

## `constraints {explain,dry-run} <spec-dir>` — sieve effect, non-destructive (doc 07)

```bash
python3 bundle_run.py constraints explain tryout_own/spec --db <populated-core-db>
```

## `bench --profile 10K --stages ...` — stage benchmark (doc 13)

```bash
python3 bundle_run.py bench --profile 10K --stages generator,sieve,core,reader_loose --out /tmp/bench.json
```

Profiles `10K/1M/10M`; 100M/1B require `--allow-huge` (never auto-run).

## `inventory` / `hygiene` — builds & repo hygiene (doc 17)

```bash
python3 bundle_run.py inventory --out /tmp/inv.json [--baseline FILE --policy {warn,block}] [--sbom]
python3 bundle_run.py hygiene --json /tmp/hygiene.json
```

## `architecture` / `coverage` / `capabilities` / `sut-manifests` / `release` — self-audit gates

All five are **side-effect-free source/registry analyses**: no database, no JAR, no run directory.
They are the project's own evidence generators, and each exits non-zero when its invariant is broken,
so they work as CI gates as well as reports.

```bash
python3 bundle_run.py architecture  [--json PATH]                  # layer model + import-direction gate
python3 bundle_run.py coverage      [--json PATH] [--measurements PATH]
python3 bundle_run.py capabilities  [--json PATH] [--markdown PATH] [--ci-cases PATH] [--check PATH]
python3 bundle_run.py sut-manifests [--json PATH]                  # validate the SUT adapter registry
python3 bundle_run.py release       [--out PATH] [--sbom PATH] [--pytest-output PATH]
```

- **`architecture`** — which layer each tree belongs to and which imports are allowed; fails on any
  dependency-direction violation (doc 30).
- **`coverage`** — the engine's composition vocabulary versus the subset each registered application
  actually exercises, with its role and maximum composition order (doc 31).
- **`capabilities`** — the one generated support matrix; `--check` verifies a stored copy still
  matches, which is how the matrix stays a release artifact rather than a snapshot (doc 33).
- **`sut-manifests`** — schema, capability rows, controls and oracle independence for the canonical
  SUT adapters, including that every referenced test exists.
- **`release`** — release manifest, optional SBOM, and skip classification from a pytest log; an
  unclassified skip is `BLOCKING_UNEXPECTED` unless `--allow-blocking-skips` (doc 34).

## `report <run-dir|run-id>` — read a finished run (Face 3, doc 26)

```bash
python3 bundle_run.py report sp-demo-001 [--out PATH] [--json PATH] [--runs-root DIR]
```

Renders a run as a **single self-contained HTML file** (no external CSS/JS/fonts, so it opens from a
`file://` path or travels as one attachment) and prints a terse summary to stdout. Default output is
`<run-dir>/reports/report.html`; `--json` additionally writes the collected data.

Reads only what the run already recorded — `run.json`, `state.json`, `stages/*.json`,
`executor-summary.json`, `provenance.json` — and **re-executes nothing**: no database, no JAR, no
stage. That is what makes it safe to point at a failed, cancelled or interrupted run, which is
usually when a results view is most wanted.

The page reports **absence as prominently as presence**: an unset `sandbox_backend` renders as
"candidates ran unsandboxed on this host", a missing Analyzer front says the Analyzer did not run,
a declared-vs-actual candidate mismatch is flagged, and an interrupted stage keeps its status. A
results surface that only renders the happy path would let a reader read "not recorded" as "fine".

## Exit behavior

`0` success; non-zero on preflight/budget/stage/invariant failure, a BLOCKING `doctor` check, a
cleanup identity refusal path, or an unclassified executor crash. Concise message by default; full
trace with `--debug`.
