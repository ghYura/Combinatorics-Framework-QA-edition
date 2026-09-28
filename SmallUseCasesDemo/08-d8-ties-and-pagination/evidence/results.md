<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D8a results: weak orders and stable pagination

- **Run:** `d8a_20260928T000339Z`. **Databases:** `as0927_d8a_20260928t000339z` on 5433 and 5432.
  - Retained sizes: main 8,394,431 bytes, results 9,131,711 bytes; the run directory is 7,167,084 bytes.
- **Input:** primary `spec/demo.xlsx` (cell-equivalent to `spec/spec.toml`). No sieve or optional axes.
- **Framework build:** accepted v6, no change.
- **Contract:** v1 `bc09509b…1d5b`; predictions `8cd37bb6…8637` and `derive.py` unchanged.
- **Envelope:** `generated-default`, one worker, K=1, `-Xmx2g`, budgets 500/500/100 MB/1200 s, no
  override. The Bundle took 288 s.
- **Evidence kind:** Verified/run. `verify.py` passed 24/24, including 14,400 record fields, and gave the
  same 24/24 from `archive/…/inputs`. Replays were 5/5 byte-identical.

## Population and stages

HEAD, IMPL (3 policies), RANKS (75) and DIRECTION (2) are crossed by the Framework, each sheet
through an explicit `FW_Combi(1) → FW_Combi(size)` chain.
- **RANKS:** the builder's catalogue of every rank vector in 0..3 that uses exactly {0..max}. There are
  75: 1 + 14 + 36 + 24 ordered partitions. The verifier re-derived them as surjections onto k levels.
- **Not claimed:** the Framework crosses and executes this catalogue; it does not generate weak orders.

| Stage | Count |
|---|---:|
| Plans (XLSX = TOML graph) | EXACT 450 |
| Core `fw_final` (HEAD 1 × IMPL 3 × RANKS 75 × DIRECTION 2 × TAIL 1) | 450 |
| Reader / Executor / results_v2 | 450 / 450 / 450; one attempt each |
| Outcomes | **330 PASS / 120 DOMAIN_FAIL**; zero BROKEN, INFRA_FAIL or TIMEOUT |

The case sets decoded from `fw_final`, from the Reader AST and from the Executor records each equal
the 450 identities `policy|D=…|R=…`.

## Outcomes

| Policy | asc | desc | Tied ranks (102) | Strict ranks (48) |
|---|---|---|---|---|
| stable_cursor | 75 / 0 | 75 / 0 | 102 / 0 | 48 / 0 |
| score_only_cursor | 54 / 21 | 54 / 21 | 60 / 42 | 48 / 0 |
| alternating_ties | 36 / 39 | 36 / 39 | 24 / 78 | 48 / 0 |

- **Strict orders:** all 24 strict orders per direction pass under every policy. The faults need ties.
- **Failure kinds:**
  - score_only_cursor: 42 omissions.
  - alternating_ties: 42 duplicate-plus-omission cases and 36 cases with every ID present but tie order
    changed.
- **Comparator laws hold everywhere:** in all 1,340 recorded per-request sign matrices (including the
  final empty requests), signs are in {−1, 0, 1} and the comparator is reflexive, antisymmetric,
  transitive for ≤ and orders unequal ranks correctly. So every failure is a pagination defect,
  not an unlawful comparator.

## Mechanisms (observed pages; all five cases replayed byte-identically)

| Case | Candidate | Pages (cursor in → ids → cursor out; or offset) | Output | Verdict |
|---|---|---|---|---|
| score_only_cursor asc 1110 | `231_0_0` | null → D,A → (1); (1) → ∅ | D,A | DOMAIN_FAIL (omits B,C) |
| stable_cursor asc 1110 | `81_0_0` | null → D,A → (1,0); (1,0) → B,C → (1,2); (1,2) → ∅ | D,A,B,C | PASS |
| alternating_ties asc 0000 | `301_0_0` | offset 0 of ABCD → A,B; offset 2 of **DCBA** → B,A; offset 4 → ∅ | A,B,B,A | DOMAIN_FAIL (duplicate, omission) |
| alternating_ties asc 0122 | `329_0_0` | offset 0 of ABCD → A,B; offset 2 of **ABDC** → D,C; offset 4 → ∅ | A,B,D,C | DOMAIN_FAIL (all IDs, unstable tie) |
| stable_cursor desc 0000 | `2_0_0` | null → A,B → (0,1); (0,1) → C,D → (0,3); (0,3) → ∅ | A,B,C,D | PASS |

**score_only_cursor.** The cursor after page 1 is only the primary key (1). The next request asks for
keys strictly greater than 1, and B and C share A's rank, so they are skipped. The composite cursor
(1,0) keeps the position inside the tie.

**alternating_ties.** Each request sorts afresh, and on odd requests the tie-breaker flips. An offset
into a different order can repeat or skip records, or return every ID with the tie reversed. In every
case, each request's comparator is lawful on its own.

**Stable ties in both directions.** stable_cursor desc 0000 returns A,B,C,D. Direction reverses only
the primary rank; ties keep input order.

## Rank-only validity versus the stable-order promise (auxiliary, offline)

`allowed_orders.py` produced `proof/allowed-orders.json`, and the verifier re-derived every row. For
each of the 150 rank vector/direction pairs, it reverses every tie block of the stable sequence.
- **valid_order:** all 150 alternatives have every identity exactly once and are in primary rank order.
- **stable_order:** rejects exactly the 102 alternatives with a tie and accepts the 48 strict ones.
- **Example:** for 0000, D,C,B,A is a valid rank-only order, but it breaks this contract's promise
  that ties keep input order.
- **Not in the campaign counts:** this proof adds no Framework candidates.

**Why a single expected tie permutation needs a stated promise.** Suppose an API promised only rank
order. Then any tie permutation would be correct, and an oracle that fixed one permutation would call
correct outputs wrong. For 0000 that would reject 23 of the 24 valid orders. An oracle may pin a tie
order only when the contract states it, as this fixture's stable-order contract does. Without that
promise the sound check is `valid_order` (with completeness across pages), not equality with one
permutation.

## Limits

These are deterministic static integration models: four records, page size 2, at most three
requests and equal weight per case. They are not a finding against Python's sort or any database,
and they give no production failure rates.
