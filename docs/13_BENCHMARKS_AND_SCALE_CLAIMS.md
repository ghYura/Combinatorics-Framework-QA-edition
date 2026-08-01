# 13 — Benchmarks and Scale Claims

> **Evidence status (2026-07-21):** the benchmark figures below are preserved measurements from
> 2026-06-11, not results from the current documentation audit. Their referenced `bench_*.json`
> reports are run artifacts and are not committed in this checkout. See the
> [current code audit](CURRENT_CODE_AUDIT_2026-07-21.md) for the toolchain and tests re-run on this
> host. Do not present these dated, single-host figures as current throughput or an SLA.

## Methodology

`bundle bench` (`bundle.benchmark/v1`) measures each stage **independently** at a chosen profile.
Setup (workbook, Core fill, candidate prep) is **untimed**; only the stage under test is timed.
Throughput is computed on **actual processed rows**, not planned counts. Profiles `10K/1M/10M`;
`100M`/`1B` require an explicit `--allow-huge` and are **never auto-run**. The harness makes **no
"end-to-end billion executions" claim**.

## Environment capture

Each report records hardware (CPU count, RAM), OS/kernel, toolchain (Python/Java/PostgreSQL),
component hashes, and DB settings — so a number is interpretable. Verified capture keys:
`hardware`, `os_kernel`, `toolchain`, `component_hashes`, `db_settings`.

## Stage isolation

Stages: `generator`, `sieve` (infra-free, always run for real); `core`, `reader_loose`,
`reader_shard`, `executor_local`, `executor_sandbox`, `executor_workers`, `analyzer` (measured when
their backend is available, else recorded **SKIPPED** with a reason — the report never overstates
what was measured).

## Dated measured results (Gate 2.8, 2026-06-11 host)

Profile **10K**, host: 8 CPU (AMD FX-8320), 31 GiB RAM, Linux 6.17, Python 3.12.3, Java 21,
PostgreSQL 18.4. Each stage processed **10,000** rows:

| stage | wall_s | cpu_s | peak MB | throughput (rows/s) |
|---|---:|---:|---:|---:|
| generator | 0.118 | 0.118 | 0.9 | 85,056 |
| sieve | 2.075 | 2.075 | 0.5 | 4,819 |
| core | 9.052 | 12.312 | 353.6 | 1,105 |
| reader_loose | 14.380 | 15.684 | 459.7 | 695 |

(`executor_*`/`analyzer` not included in this run — executing 10,000 candidates is out of scope for
a gate; the bounded 288 end-to-end run is the executor evidence.) Report: `bench_10k.json`.

## Measured scale: 10K → 100K → 1M generation (2026-06-11 addendum)

Generation path (`generator,sieve,core` [+ `reader_shard` at 100K]) measured at three sizes on the
same 2012-era 8-core host. **Core generation throughput rises with scale** (JVM/PostgreSQL fixed
costs amortize), and the **constraint sieve is the scale bottleneck** (≈constant ~4.8K rows/s):

| stage | 10K rows/s | 100K rows/s | 1M rows/s |
|---|---:|---:|---:|
| generator | 85,056 | 83,333 | 84,517 |
| sieve | 4,819 | 4,727 | 4,769 |
| core | 1,105 | 9,207 | **58,925** |
| reader_shard | — | 5,764 | (skipped: peak ~1.8 GB at 100K → memory) |
| reader_loose | 695 | — | — |

Headline: **Core filled 1,000,000 rows in 17 s (≈58.9K rows/s, peak 800 MB)** — and `reader_shard`
ran **~8× faster than `reader_loose`** at comparable size (5,764 vs 695 rows/s), confirming the
sharded sink for L-class. At 1M, `sieve` dominates wall time (210 s) — the next optimization target
(batch the per-row predicate / push into SQL). Reports: `bench_100k.json`, `bench_1M.json`. Not run:
10M+ (the 2012 box is the limit, not Core; `reader_loose` at 1M would create 1M inodes — use shards).

## Distributed execution: worker-pool speedup (measured)

`executor_workers` vs `executor_local` at 500 candidates on 8 cores:

| variant | wall_s | throughput (cand/s) |
|---|---:|---:|
| executor_local (1 process) | 176.9 | 2.83 |
| executor_workers (8) | 31.9 | **15.66** (~5.5×) |

Near-linear scaling via deterministic id-hash sharding; 1-worker and N-worker runs produce the same
outcome set (`test_worker_pool`) and the same harvested metrics corpus
(`merge_worker_metrics`, sorted/deduped/crash-tolerant — `test_py_executor_outcomes`). Report:
`bench_wp.json`.

## Interpretation cautions

- These are **single-host, single-run** numbers on a 2012-era 8-core CPU; treat as order-of-magnitude
  for this hardware, not a product SLA.
- Generation, execution, and analysis have **different scaling laws** — a space cheap to *generate*
  may be infeasible to *execute*. Always state which stage a number refers to.
- `core`/`reader_loose` throughput is dominated by PostgreSQL writes and per-file/inode I/O; the
  shard sink changes the reader profile. Replace the planner's generic per-unit assumptions with
  these measured values for tighter resource estimates ([06](06_PLANNING_BUDGETS_AND_COUNTS.md)).

## Proven vs estimated vs unverified (honest ledger)

| Claim | Status | Evidence |
|---|---|---|
| Bounded 288 secure end-to-end | **proven (measured)** | gate-final run; 288/150/138/0; container backend |
| 10K / 100K / 1M per-stage **generation** throughput | **proven (measured)** | `bench_10k.json`, `bench_100k.json`, `bench_1M.json` (above) — Core 1M rows in 17 s |
| Worker-pool execution speedup (~5.5× on 8 cores) | **proven (measured)** | `bench_wp.json` |
| Core canonical invariants `fw_final=4,644,864`, `fw_opt4=33,674,483` | **source-confirmed fixture** | `Core_trunk/README_CANONICAL_TRUTH.txt`; **not re-run this session** |
| 10M / 100M / 1B per-stage throughput | **unverified** | not run (2012 host is the limit; the engine's limiter can be lifted with `unleash_initial_productivity_power`, but 10M+ needs the right hardware — see [06](06_PLANNING_BUDGETS_AND_COUNTS.md)) |
| "billion candidate end-to-end execution" | **explicitly NOT claimed** | architecture-credible only; generation ≠ execution |

Per the prompts and the original assessment, scale claims are **stage-specific** and every number
names its stage and its evidence. Generation scale must never be presented as end-to-end execution
throughput.

## Build reproducibility note

Maven jars are **not byte-reproducible** (zip entry timestamps), so a component's artifact sha256
changes across rebuilds even with identical source; `bundle inventory` captures the **per-build**
hash. Plan accordingly when using `--baseline --policy block` (it will flag every rebuild).
