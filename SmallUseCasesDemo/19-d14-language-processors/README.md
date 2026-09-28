<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D14a — Compiler and interpreter relations

[Contract](CONTRACT.md) · [Predictions](architect-derived.json)

Native declaration permutations, expression grouping and operators exercise a
small compiler, stack machine and independent interpreter. Dead-code insertion
exposes a variable-storage bug; reversed subtraction shows why two equal outputs
can still be wrong. Both the original and transformed program are checked.

Plan EXACT 432 candidates; predicted 316 PASS / 116 DOMAIN_FAIL. Each candidate

## Results (the AI implementer, 2026-09-28)

[Results](evidence/results.md). Run `d14a_20260928T173808Z` on Framework v6 (no change), no sieve.
- **Counts:** plans EXACT 432 (XLSX = TOML); Core 432 = Reader = Executor = results_v2; DECL rows are the two
  native FW_Permut orders (216 each); 864 compiled variants / VM executions.
- **Outcomes:** **316 PASS / 116 DOMAIN_FAIL** (verify 31/31 at campaign time, 73,008 fields, 9,504 VM
  transitions). reverse_sub 80/64, all passing the metamorphic check; alias_dead_temp 92/52, all passing the
  original differential; faithful 144/0.
- Five replays were byte-identical. Local compiler, VM and interpreter only.
