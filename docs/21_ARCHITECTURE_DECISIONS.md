# 21 — Architecture Decisions (ADRs)

Current ADRs, their rationale and consequences, and the confirmed deviations from the original
high-level plan. The ADRs restate the plan's `Bundle_Refactoring_High_Level_Plan_07062026.md §8` and
record what the implementation actually did.

> **Current-code note (2026-07-21):** the decisions below are reconciled with the implementation
> as audited on this date. Dated plan/review documents remain useful history, but the
> [current code audit](CURRENT_CODE_AUDIT_2026-07-21.md) is the concise operational truth.

## ADR-1 — Generator owns the control plane
**Decision:** the `bundle` package and CLI live in `generator_trunk`. **Rationale:** the Generator
already owned spec parsing, planning context, and `bundle_run`. **Consequence:** one entry point
(`bundle_run.py` shim → `bundle.cli`); the control plane is Python.

## ADR-2 — Components remain independently runnable
**Decision:** each of the five trunks stays a standalone process; the control plane spawns them and
exchanges only files/manifests. **Rationale:** lower migration risk, preserved diagnostic value.
**Consequence:** clean process/failure boundaries; the launcher never runs candidate code in-process.

## ADR-3 — JSON contracts, language-specific implementations
**Decision:** Python and Java components share **schemas**, not a runtime. **Rationale:** no forced
shared dependency. **Consequence:** mirrored logic on both sides (e.g. `results_v2`
DDL/writer in `py_executor.py` and Java `ResultsV2SchemaMigrator`/`ResultsV2Writer`; the handoff
model). Touch a contract on one side → mirror it on the other.

## ADR-4 — Additive DB migration
**Decision:** add `public.results_v2` alongside the legacy table; never drop legacy rows.
**Rationale:** legacy queries and consumers must keep working. **Consequence:** boolean `status`
survives as a compatibility projection; migration is repeatable/idempotent. The current immutable
sample identity is the five-column
`(run_id, candidate_id, attempt, repeat_idx, env_id)` key. The retired three-column unique index is
dropped during migration, and writes use `ON CONFLICT ... DO NOTHING`.

## ADR-5 — Explicit formal vs exploratory Analyzer modes
**Decision:** formal mode uses declared goals only (no auto axes) and requires a corpus count;
exploratory keeps auto-discovery, labelled. **Rationale:** auto-discovery is useful for exploration
but dangerous for formal conclusions. **Consequence:** a formal Pareto front is reproducible and
provenanced; the corpus-count check is fail-closed (it caught BUG-1).

## ADR-6 — Sandbox is pluggable and fail-closed
**Decision:** generated code runs only via a `SandboxBackend` (Local/Bubblewrap/Container); a secure
profile fails closed if its backend is unavailable — never silently falls back to local execution.
**Rationale:** one backend is not available on every host, but secure mode must not degrade silently.
**Consequence:** rootless-Docker container backend with read-only root, resource limits, and
local-only internal networking; the launcher verifies the recorded backend. **BUG-1 was a violation
of this ADR** (the Analyzer metric step re-ran candidates locally) and was fixed. The CLI default is
nevertheless `trusted-local`, which is deliberately **unsandboxed**; callers must choose
`generated-default` or `networked-api-probe` when isolation is required.

## ADR-7 — Scale optimizations follow contract stabilization
**Decision:** stabilize run/candidate/result/handoff/outcome contracts before scaling Reader/Executor.
**Rationale:** distributed ambiguity is costlier than local ambiguity. **Consequence:** sinks
(loose files, shards, and a constrained live gRPC path), deterministic worker pools, backpressure,
repeat fan-out, and standalone Java control-plane seams are built on stable contracts. These are not
a claim of general remote orchestration: the Bundle launcher exposes a narrower set of combinations,
and gRPC is currently Java-only, verdict/Handoff-v2-only, plaintext, and trusted-local.

## ADR-8 — Repeats are experiments; attempts are retries
**Decision:** `repeat_idx`/`env_id` identify intentional samples, while `attempt` records retry or
recovery history. **Rationale:** mixing those dimensions corrupts both idempotency and statistics.
**Consequence:** the Executor preserves raw samples; the Analyzer owns median/order-statistic
aggregation and confidence intervals. A selected/latest result is a read-time projection, not a
second uniqueness constraint.

## Confirmed deviations from the original plan

- **No standalone `bundle status` for runs.** Run/stage status lives in `state.json` and the
  per-stage JSON; the only `status` subcommand belongs to `bundle deploy`. (The plan listed `status`
  among lifecycle verbs; the implementation exposes status as machine-readable state instead of a
  command.)
- **The launcher defaults to Python (`--lang py`) and can route `--lang java`.** Java has additional
  compiler, pool, precompiled-container, and live-gRPC paths, but not every language/transport/pool/
  repeat combination is valid. In particular, the launcher constrains gRPC to Java +
  `trusted-local`, and executor pools to Java loose-files with K=1.
- **Maven artifacts are not byte-reproducible.** "Reproducible build" means same source → same
  *version*, freshly hashed per build (zip timestamps differ); identity is captured via
  `bundle inventory` (`--baseline --policy block` will flag every rebuild).
- **Build/record ordering for policy-stamped manifests.** The handoff manifest is finalized by the
  policy stamp *after* the Reader writes it; the reader stage records the manifest hash after that
  stamp (BUG-2 fix) so resume reuse is correct.
- **Analyzer corpus is harvested in-sandbox, not by re-execution.** The metric channel no longer
  re-runs candidates on the host (BUG-1 fix); `collect_kv` remains only as the trusted-local/legacy
  fallback.

## Decisions deliberately out of scope (this release)

Full Core rewrite; new combinatorial verbs; replacing PostgreSQL; general remote/Kubernetes
orchestration; GUI redesign; multi-million/full canonical runs after each step; mass
deletion of backups without explicit approval; changing canonical truth numbers to pass a test.
