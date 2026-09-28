<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D14b results: SQL ternary partitioning and multiset preservation

- **Run:** `d14b_20260928T181144Z`. **Core/results databases:** `as0927_d14b_20260928t181144z` on 5433 and 5432
  (owner role `postgres`; absent before). Retained: main 8,378,047 B, results 8,550,079 B; run directory
  1,975,330 B; `evidence/` 2,261,140 B, `archive/` 442,887 B.
- **Subject fixture (owned, isolated, retained):** container and database `as0927_d14b_sql_20260928t180414z` on the
  internal network `as0927_d14b_net_20260928t180414z`, volume `as0927_d14b_sqldata_20260928t180414z`, no published
  ports, 256 MiB, shared_buffers 16MB, max_connections 20, `log_statement=all`. Cached `postgres:16.9-alpine`
  (`7c688148…`); `SELECT version()`: PostgreSQL 16.9 on x86_64-pc-linux-musl. Fixture-only role
  `as0927_d14b_reader` (SELECT on the two tables, `default_transaction_read_only=on`, statement timeout 5 s).
- **Client image:** `as0927_d14b_client:20260928t180414z` (`19658713…`), made offline from cached `python:3-slim`
  (`c845af93…`, Python 3.14.5) by docker create/cp/commit with the venv's pure-Python pg8000 1.31.5, scramp 1.4.17,
  asn1crypto 1.5.1, python-dateutil 2.9.0.post0 and six 1.17.0, their dist-info/licences included (file manifest
  `f1b09cb0…`). Nothing was pulled or downloaded; the builder container is kept.
- **New storage:** 50,347,726 B in Docker (PGDATA 48,369,667; client layer 384,715 compressed; builder
  1,576,960; fixture layer 16,384) + fixture log 323,634 B + run directory 1,975,330 B; far below 200 MB.
  Unchanged from before to after the campaign (the fixture was never written).
- **Framework build:** accepted v6, no change (checkout `be48836` + the 27 inventoried v6 files).
- **Contract:** v1 `8f9fa5cf…289d`; predictions `bb459f09…a9c1` and `derive.py` `fa3fdbbd…7d9d` unchanged.
- **Envelope:** `networked-api-probe`, origin `generated`, `--sandbox-network-allowlist` = the fixture only,
  `--sandbox-candidate-env D14B_FIXTURE=<fixture>`, `BUNDLE_SANDBOX_IMAGE` = the client image, one worker, repeat 1,
  `-Xmx2g`, budgets 100/100/200,000,000 B/600 s, no override. The Bundle took 135.2 s (Core 9.1, Reader 13.8,
  Executor 110.4).
- **Evidence kind:** Verified/run, **with a disclosed post-run verifier fix.** At campaign time `verify.py` passed
  29/32: three checks carried wrong expectations (below) while every observation was already correct. After the
  fix it passes 32/32, also from `archive/…/inputs`. Replays were 5/5 identical in every mathematical field.

## Before the campaign

- **Setup** (`evidence/fixture-20260928t180414z/setup.json`): the bootstrap (`bootstrap.sql`, `1e66c8dd…`) ran once
  by docker exec in the named database only; the exported rows equal the frozen fixture.
- **Real sandboxed probe** through the Framework's own Executor sandbox (networked-api-probe, fixture allowlisted):
  one target attached; role, database, `repeatable read`, read-only `on`; 6 items and 6 tags; a write attempt
  refused (SQLSTATE 25006, read-only transaction); external DNS blocked. The same probe ran again as a fixture
  test in the campaign's preflight (32/32 tests).
- **Parser preflight:** a fixture test composed a candidate as the Reader renders it, parsed it with the verifier and
  ran it against a pg8000 stub.

## Construction and stage counts

| Stage | Count |
|---|---:|
| Plans (XLSX = TOML; graph `13fb807d…` = the AI architect's shape plan) | mandatory, post-sieve, final **EXACT 72**; optional ×1 |
| Core `fw_final` (1 × 3 × 4 × 6 × 1) | 72 |
| Reader / Executor / results_v2 | 72 / 72 / 72; one attempt each, repeat_idx 0 |
| Distinct shape/predicate families | 24 (each under 3 adapters) |
| Campaign data SELECTs (4 per candidate) | **288**, in 72 transactions |
| Outcomes | **36 PASS / 36 DOMAIN_FAIL**; zero BROKEN, INFRA_FAIL or TIMEOUT |

- **Decoding:** the decoded `fw_final` atoms give policy, shape and predicate; each candidate is byte-exactly its
  Core row joined with the recorded endings, and its name prefix equals its `combi_id`. The workbook holds no SQL.
- **Budget notes:** non-blocking warnings for 72 rows and candidates (above 50; hard limit 100).

## Live execution evidence

- **One transaction per candidate:** `BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY`, the provenance query, base,
  true, false, unknown, `COMMIT`, on a fresh connection. In every record: database = the fixture, user
  `as0927_d14b_reader`, isolation `repeatable read`, read-only `on`, statement timeout `5s`, application name
  `d14b:<case>`, the fixture's version, and 72 distinct backend PIDs (169–245). Every snapshot is `744:744:`: no
  transaction was in progress or committed after bootstrap.
- **Server SQL log** (`fixture/campaign-sql.log`, `4afb4825…`, the segment between snapshots taken just before and
  after the Bundle): exactly 504 statements (72 × 7), all by the reader role, zero errors. For each record, the
  statements under its backend PID match its recorded sequence and SQL exactly, within one virtual transaction.
  The 288 data SELECTs equal the recorded SQL as a multiset.
- **Fixture unchanged:** rows, tags and catalog hashes are equal at setup, before and after the campaign, and after
  the replays; the rows equal the frozen fixture. The catalog shows only `items_pkey`, the four internal triggers
  of the required foreign key and the two tables; the reader's grants are exactly SELECT on those two tables (the
  other grants belong to the owner `postgres`).
- **Sandbox:** the persisted policy is networked-api-probe, container backend, `network_allowlist` = [the fixture],
  `D14B_FIXTURE` added to the env allowlist, not trusted; the Executor logged "attached 1 target(s) to the dedicated
  internal network" and ran every candidate in the client image.

## Outcomes

| Adapter | PASS / FAIL | scan | filtered | inner_join | left_join |
|---|---|---|---|---|---|
| union_all | 24 / 0 | 6/0 | 6/0 | 6/0 | 6/0 |
| omit_unknown | 6 / 18 | 1/5 | 2/4 | 2/4 | 1/5 |
| dedup_union | 6 / 18 | 0/6 | **6/0** | 0/6 | 0/6 |

- **Every query result matched the three-valued model:** all 288 query bags pass their independent checks, so every
  failure is an adapter recombination (tlp_ok false), not a PostgreSQL result.
- **omit_unknown** fails exactly where the unknown branch is non-empty and passes the six families where it is empty
  (is_null on all four shapes; or on filtered and inner_join).
- **dedup_union** fails wherever the base has duplicate projected values and passes the six filtered families,
  whose base rows (NULL, 0, 1) are distinct.
- **Sets would hide most failures:** 23 of the 36 failures have equal sets but unequal bags; `set_equal` is reported
  as a diagnostic only.

## Witnesses (replayed)

| Candidate | Case | Base | true / false / unknown | Recombined | Verdict |
|---|---|---|---|---|---|
| `27_0_0` | omit_unknown, scan, flag | NULL,NULL,0,1,1,2 | NULL,1 / 0,2 / NULL,1 | NULL,0,1,2 | DOMAIN_FAIL: sets agree, bags differ |
| `3_0_0` | union_all, scan, flag | NULL,NULL,0,1,1,2 | NULL,1 / 0,2 / NULL,1 | NULL,NULL,0,1,1,2 | PASS: unknown multiplicity kept |
| `62_0_0` | dedup_union, inner_join, eq1 | NULL,NULL,1,1,1,2 | 1,1,1 / 2 / NULL,NULL | NULL,1,2 | DOMAIN_FAIL: join multiplicity lost |
| `35_0_0` | omit_unknown, filtered, or | NULL,0,1 | NULL,1 / 0 / — | NULL,0,1 | PASS: no UNKNOWN rows |
| `60_0_0` | dedup_union, filtered, is_null | NULL,0,1 | NULL / 0,1 / — | NULL,0,1 | PASS: distinct rows |

Replays ran each candidate byte for byte through the same Framework sandbox (20 extra data SELECTs, logged in
`replays/replay-sql-*.log`); every mathematical field equals the campaign record; backend PIDs are new, snapshots
unchanged, and the fixture export is unchanged afterwards.

## Post-run verifier fix (disclosed)

The campaign-time verifier and its output are kept in `evidence/…/campaign-time-verifier/` (its hash equals the
recorded input; rerunning it reproduces 29/32 exactly). The three corrected expectations were:

1. **Sandbox description timing:** the Executor records its description before the dedicated network is created
   (`net=internal:(dedicated, on first use)`); the check required the final network name. Now it requires
   `net=internal:`, and the separate check still requires the logged attachment of exactly one target.
2. **Foreign-key triggers:** PostgreSQL implements the contract's `REFERENCES` constraint with four internal
   `RI_ConstraintTrigger_*` triggers; the check demanded zero triggers. Now it requires exactly those four and no
   other trigger. The catalog export itself is unchanged since setup.
3. **Origin path:** the run records the candidate origin at `settings.execution_authorization.origin`
   (`generated`); the check read a top-level key.

## Limits

Six rows, two tables, four shapes, six predicates and three planted adapter defects on one PostgreSQL 16.9 fixture.
The failures belong to the adapters, not to PostgreSQL. No claim about other engines, optimisers, concurrency,
larger data or NoREC-style companions.
