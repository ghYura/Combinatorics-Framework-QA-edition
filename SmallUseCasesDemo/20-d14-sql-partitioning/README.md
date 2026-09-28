<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D14b — SQL ternary-logic partitioning

[Contract](CONTRACT.md) · [Predictions](architect-derived.json)

Actual PostgreSQL queries partition rows by TRUE, FALSE and UNKNOWN. Bag
comparison exposes adapters that discard unknown rows or remove duplicates;
set equality can conceal both errors. An independent finite model checks results.

Plan EXACT 72 candidates: 24 SQL families × three adapters, four queries each,
288 data SELECTs. Predicted 36 PASS / 36 DOMAIN_FAIL. The owned PostgreSQL fixture
is reached through allowlisted sandbox networking; shared services stay unchanged.

## Results (the AI implementer, 2026-09-28)

[Results](evidence/results.md). Run `d14b_20260928T181144Z` on Framework v6 (no change), no sieve, networked-api-probe.
- **Fixture:** owned isolated `as0927_d14b_sql_20260928t180414z` (PostgreSQL 16.9, internal network, no published
  ports, SELECT-only read-only role) and offline client image `as0927_d14b_client:20260928t180414z`; a real
  sandboxed probe passed before the campaign. All retained.
- **Counts:** plans EXACT 72 (the AI architect's graph); Core 72 = Reader = Executor = results_v2; 288 data SELECTs in 72
  REPEATABLE READ READ ONLY transactions, all corroborated by the server SQL log; fixture unchanged.
- **Outcomes:** **36 PASS / 36 DOMAIN_FAIL**; union_all 24/0, omit_unknown 6/18, dedup_union 6/18; every query
  bag matched the three-valued model; 23 failures have equal sets.
- **Verification:** 32/32 after a disclosed post-run fix of three verifier expectations (29/32 at campaign time,
  kept in `evidence/…/campaign-time-verifier/`). Five replays identical in every mathematical field.
