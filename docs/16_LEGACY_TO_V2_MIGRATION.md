# 16 — Legacy → v2 Migration

The refactor is additive: legacy behavior is preserved as fallback, and removing it is a separate
explicit decision. This guide maps old behavior to the new equivalents.

## CLI / launcher

| Old | New | Status |
|---|---|---|
| `bundle_run.py <spec> [opts]` (one-shot) | same, now backed by the `bundle` package; `bundle_run.py` is a thin shim (`from bundle.cli import main`) | **non-deprecated** (compatible) |
| ad-hoc preflight gotcha-fixes baked into the launcher | typed config + preflight + per-stage invariants | improved, compatible |
| (none) | new subcommands: `plan/iterate/doctor/resume/cancel/cleanup/constraints/bench/deploy/inventory/hygiene` | additive |

## Configuration

| Old | New | Status |
|---|---|---|
| hardcoded ports/paths + a hardcoded default DB password in code/properties | typed `BundleConfig`, precedence **CLI > env > config file > defaults**; secrets from env, never defaulted | hardcoded default removed; **`fw.properties` still rendered from config** |
| `/mnt/F` implicit scratch auto-probe | default `/tmp/fw_work/<db>`; `/mnt/F` only if `scratch_root` explicitly set | behavior change (no implicit `/mnt/F`) |

## Handoff (Reader → Executor)

| Old | New | Status |
|---|---|---|
| weakly-typed file handshake (`resultsDbURL.properties`, `insert.sql`, `arguments`, `fwVar.shift`, `runmefirstonce.first`) | versioned **Handoff v2 manifest** (`bundle.handoff/v2`), atomically written, checksum/count-verified; `execution_policy_ref` stamped in | v2 is default; **legacy files still written** |
| launcher repaired an empty `fwVar.shift` | v2 refuses an empty `shift` (P6); the repair lives only in the legacy adapter | improved |
| — | `--legacy-handoff` makes the file handshake authoritative (manifest skipped) | **compatibility fallback** |
| loose candidate directory | Handoff-v2 transports `loose-files`, `sharded`, or live `grpc` | gRPC is Java/verdict/trusted-local only and has no legacy fallback |

`handoff_from_legacy` converts legacy handshake content into the v2 model, so existing artifacts map
forward.

## Outcomes & results

| Old | New | Status |
|---|---|---|
| boolean `status` (+ a conflated "broken" bucket) | canonical outcomes `PASS/DOMAIN_FAIL/BROKEN/TIMEOUT/INFRA_FAIL/SKIPPED/CANCELLED` | `status = (outcome == PASS)` kept as a **compatibility projection** |
| single legacy per-run results table | **additive** `public.results_v2` (five-column sample identity, policy id/hash, provenance) alongside the legacy table | legacy table + consumers **unchanged** |
| green run on subprocess exit code | green run on **cross-stage invariants**; broken/timeout/infra fail by default | improved; tolerances via `--executor-tolerate-outcomes` |

## Run state / lifecycle

| Old | New | Status |
|---|---|---|
| flat scratch tree, no manifest | run directory with `run.json`/`state.json`/per-stage JSON, atomic writes, resume/cancel/cleanup | `--legacy-scratch` keeps the flat tree (**no resume**) |
| re-running could duplicate results | `results_v2` immutable sample idempotency and read-time latest-attempt selection; no-op resume | improved |

## Specs

Legacy specs (no `spec_version`) load unchanged (compatibility mode warns on unknown fields; strict
mode rejects them). Advanced verbs/braces/`FW_Group` are preserved; aliases are additive.

## Analyzer

Old auto-discovery is preserved as the **exploratory** mode (inferred axes labelled). The new
**formal** mode (explicit goals, corpus count, provenance) is opt-in via `--analysis-mode formal`.
Repeat-aware corpora are aggregated by candidate before ranking, and `--seed-output` can emit a
schema-v1 BundleSeed for `--seed-from` or `bundle iterate`.

## Repeat-aware results migration

Current Executors add `repeat_idx integer NOT NULL DEFAULT 0` and
`env_id text NOT NULL DEFAULT ''`, retire the old `(run_id,candidate_id,attempt)` index, and create
`results_v2_sample_uk` over
`(run_id,candidate_id,attempt,repeat_idx,env_id)`. Existing K=1 rows preserve their identity through
the defaults. `results_v2_schema_meta` is stamped at version 2, and both Executors fail closed with
`RESULTS_V2_SCHEMA_CAPABILITY_MISMATCH` if the stamp, columns, or five-column index do not match.
There is no selected-final partial index: consumers select the highest attempt at read time for
each candidate/repeat/environment sample.

## Deprecation / non-deprecation

- **Non-deprecated (compatible):** `bundle_run.py` entry point, legacy results table + boolean
  status, legacy handshake (via `--legacy-handoff`), legacy scratch (via `--legacy-scratch`),
  pre-v1 specs.
- **Behavior changes:** no implicit `/mnt/F` scratch; no hardcoded default DB password; secure runs are
  fail-closed (no silent local fallback); a green run now requires invariants, not just exit codes.
  The overall execution-policy default is nevertheless `trusted-local` (unsandboxed), so select a
  secure profile explicitly for untrusted code.

## Rollback guidance

- Force the legacy data plane: add `--legacy-handoff` (file handshake) and/or `--legacy-scratch`
  (no run dir). The legacy results table keeps populating regardless.
- Old reporting that reads the legacy table or boolean `status` continues to work — `results_v2` is
  purely additive.
- To pin component artifacts, capture a `bundle inventory --out baseline.json` and compare with
  `--baseline baseline.json --policy block` (note: maven jars are not byte-reproducible, so a
  rebuild will differ — see [13](13_BENCHMARKS_AND_SCALE_CLAIMS.md)).
