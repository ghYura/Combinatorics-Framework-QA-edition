<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D14b contract v1 — SQL ternary partitioning and multiset preservation

Apply ../README.md and G1–G7. Execute actual SELECT queries on a small,
owned PostgreSQL fixture. Test a query-result adapter using the identity
Q = Q[p] UNION ALL Q[NOT p] UNION ALL Q[p IS NULL], comparing bags, not sets.
The planted faults belong to the adapter; do not present them as PostgreSQL bugs.
No NoREC companion or additional SQL shape is included in this campaign.

## Frozen fixture and query families

Schema fixture contains items(id integer primary key, grp text not null,
val integer null, flag boolean null) and tags(item_id integer referencing
items(id), tag text not null). Exact rows are in architect-derived.json:

| id | grp | val | flag |
|---|---|---|---|
| 1 | a | NULL | TRUE |
| 2 | a | 0 | FALSE |
| 3 | a | 1 | NULL |
| 4 | b | 1 | TRUE |
| 5 | b | 2 | FALSE |
| 6 | b | NULL | NULL |

Tags: (1,p), (1,q), (3,p), (4,p), (4,q), (5,p). No other data, indexes beyond
the primary key, or triggers. Duplicate projected values and join multiplicity
are deliberate. All query variants project only i.val, retaining multiplicity.

Four base shapes: scan all items; filtered scan with i.grp='a'; inner join tags
on item_id=id; left join tags on the same key. Their row counts are 6/3/6/8.
Six predicates, named gt0/eq1/flag/and/or/is_null:
i.val>0; i.val=1; i.flag; (i.val>0) AND i.flag; (i.val=1) OR i.flag;
i.val IS NULL. The last predicate is total even on NULL inputs.

Use the exact parenthesized query construction in derive.py. Execute four
separate data queries per candidate, in order base, true, false, unknown. The
true branch adds p, false adds NOT(p), unknown adds (p) IS NULL to the base WHERE.
Retain the base filter in every branch. No DISTINCT, LIMIT, ordering requirement,
aggregation or volatile expressions. Each result is a list of one-column rows;
NULL becomes None. Canonical ordering for evidence: NULL first, then integers.

## Adapters and independent oracle

All three policies execute all four real SQL queries. They then recombine rows:

- union_all concatenates true, false and unknown, preserving duplicates.
- omit_unknown concatenates true and false, discarding the collected unknown rows.
- dedup_union concatenates all three, then erroneously deduplicates result tuples.

The policy-blind oracle compares base and recombined bags, counting every tuple,
including NULL. It also independently checks base/partition bags against the
frozen fixture's small three-valued logic model. Implement that model independently;
do not import derive.py or obtain expected outputs from another SQL query.
SQL uses TRUE/FALSE/UNKNOWN: do not map UNKNOWN to false before applying NOT.
Check all four query bags against model data. A well-formed query result that
differs from the model, or an adapter's bag discrepancy, is DOMAIN_FAIL. Missing
query observations, malformed records, SQL errors or failed connections fail
infrastructure gates. PASS requires correct query results
and tlp_ok. Report set_equal as a diagnostic only, never the oracle.

Record policy/query/predicate, four exact SQL strings, canonical query_rows and
query_bags, combined_rows/bag, tlp_ok, set_equal, independent query checks,
verdict and source/candidate identity. Include real database provenance separately
from these frozen mathematical fields. Preserve all source rows in fixture exports.

Concrete controls: scan has bag NULL×2, 0×1, 1×2, 2×1. For scan/flag the true
branch is [NULL,1], false [0,2], unknown [NULL,1]. omit_unknown has equal SETS
but unequal bags here. All filtered results are distinct, so dedup_union passes
there. Unknown is empty for is_null everywhere and for or on filtered/inner_join;
omit_unknown legitimately passes those cases.

## Execution environment and stable snapshots

Keep generated candidates sandboxed. Use networked-api-probe with origin
generated and an allowlist naming ONLY a new owned fixture container. Do not
misclassify generated code as locally-authored to enable trusted-local.

Read-only preparation found cached postgres:16.9-alpine and python:3-slim images.
Create an isolated PostgreSQL fixture container named as0927_d14b_sql_<stamp>,
on an owned internal Docker network, with no published host ports. Set its
application database to the same as0927_* name. Keep system bootstrap databases
untouched; issue application DDL only in that named database. Do not attach or
reconfigure shared services, alter their roles, or pull/download images.
Pin cached image IDs/digests and record actual SELECT version() output; this
fixture may differ from the shared servers' PostgreSQL version.

Initialize the tables once using docker exec or an equivalent local bootstrap.
Create a fixture-only login as0927_d14b_reader with SELECT on the two tables,
schema usage and connection to this database; default_transaction_read_only=on.
Use password pass for this isolated fixture. Generated clients get these fixture
credentials only. Use statement/connection timeouts, and no concurrent writer.

Build a small local client image from the cached python:3-slim, copying only
pure-Python dependencies from this workspace's venv (with licenses/versions):
pg8000 1.31.5, scramp 1.4.17, asn1crypto 1.5.1, python-dateutil 2.9.0.post0,
six 1.17.0. No package downloads. Use BUNDLE_SANDBOX_IMAGE to select it and the
supported sandbox network allowlist setting to reach the fixture by container
name on port 5432. The Executor provisions its internal network and attaches
the allowlisted target. Verify driver import and one real sandboxed probe before
the campaign. Do not replace actual queries with prerecorded results.

Every candidate opens a fresh connection and a REPEATABLE READ, READ ONLY
transaction for its four data queries. In that transaction record current_database,
current_user, transaction_isolation, transaction_read_only, backend PID and the
transaction snapshot. Assert database/role match the owned fixture and settings
match the contract. Record one transaction's begin/data/provenance/end sequence.
Use application_name containing the case identity; preserve fixture server SQL
logs to corroborate queries. Hash/export fixture rows before and after; they
must match. Cap fixture memory at 256 MiB with small shared_buffers/max_connections.

Core/results continue using fresh as0927_d14b_<stamp> databases on shared ports
5433/5432. The subject fixture is a third isolated database, not a change to
those services. Preserve its container, data, local client image and owned
network; record their names and retained sizes. No automatic cleanup.

## Framework population and denominators

Primary demo.xlsx plus matching spec.toml. Mandatory HEAD, IMPL (legacy position
2), QUERY, PREDICATE, TAIL; Combi(1)→Combi(size) on each. Factors are three
adapters × four query shapes × six predicates = **72 candidates**, EXACT at
plan/Core/Reader/Executor. No sieve or optional axes. Derive selections from
actual decoded rows, not prebuilt complete-case programs. Identity
P=policy|Q=query|F=predicate. Framework repeat=1.

There are **24 distinct shape/predicate families**, executed under each adapter:
24×4=96 data SELECTs per policy, **288 data SELECTs overall**. Transaction,
provenance, setup, preflight and replay SQL are additional and reported separately.
Every candidate executes the unknown query even when omit_unknown discards it.
Derived: **36 PASS / 36 DOMAIN_FAIL**: union_all 24/0; each faulty adapter 6/18.
No SQL has yet run for these predictions. Preserve derive.py/architect-derived.json.

## Review, witnesses and envelope

Separate query construction/adapter, independent logical oracle and runtime.
Offline verifier must not import implementation/oracle/runtime/derive, execute
candidates or contact a database. Rebuild fixture joins, three-valued truth and
all bags independently; verify every field, live provenance/logs, row mapping,
plans, counts and hashes. Preflight its parser on a composed candidate.
Tests should cover NULL truth tables, duplicate projection/join rows, missing
unknown, deduplication, falsely passing set comparison, passing total predicates,
lost base filters, malformed SQL results and transaction/role guards. Include
both DB-free tests and the small real sandbox connectivity probe.

Replay five cases against the retained immutable fixture (20 extra data SELECTs):

- P=omit_unknown|Q=scan|F=flag — sets agree, bags differ.
- P=union_all|Q=scan|F=flag — includes unknown multiplicity.
- P=dedup_union|Q=inner_join|F=eq1 — destroys join multiplicity.
- P=omit_unknown|Q=filtered|F=or — no UNKNOWN rows, passes.
- P=dedup_union|Q=filtered|F=is_null — distinct projected rows, passes.

One campaign on accepted v6; networked-api-probe, one worker, repeat=1,
JVM <=2 GB. Bundle budgets: mandatory/final 100, disk 200,000,000 bytes,
wall 600 seconds. Also keep total NEW fixture/client/run storage under 200 MB,
excluding already cached base images; measure before and after. Preflight both
inputs, ownership, driver/image/network access and free space. If actual sandbox
access is blocked, report a minimal reproducer; never weaken its policy.
Archive all commands, source/input/build/image hashes, plans, Core tables,
candidates, SQL logs, fixture exports, observations, verification, tests and
replays. Preserve accepted examples and the checkout. No external calls, pull,
canonical fixture, broad tests, cleanup, commit or push. Necessary evidenced
fixes remain authorized. Deliver EEST Markdown. Do not start D14c.
