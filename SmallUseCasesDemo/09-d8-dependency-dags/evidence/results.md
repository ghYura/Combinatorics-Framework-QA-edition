<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D8b results: incremental DAG evaluation

- **Run:** `d8b_20260928T002104Z`. **Databases:** `as0927_d8b_20260928t002104z` on 5433 and 5432.
  - Retained sizes: main 8,476,351 bytes, results 9,557,695 bytes; the run directory is 11,365,216 bytes.
- **Input:** primary `spec/demo.xlsx` (cell-equivalent to `spec/spec.toml`). No sieve, bonds or
  optional axes.
- **Framework build:** accepted v6, no change.
- **Contract:** v1 `4add35e0…71fe`; predictions `51df8408…853e` and `derive.py` unchanged.
- **Envelope:** `generated-default`, one worker, K=1, `-Xmx2g`, budgets 1000/1000/100 MB/1800 s, no
  override. The Bundle took 472 s.
- **Evidence kind:** Verified/run. `verify.py` passed 23/23, including 34,560 record fields, and gave the
  same 23/23 from `archive/…/inputs`. Replays were 5/5 byte-identical.

## Population and stages

HEAD, IMPL (3 policies), six binary slots EDGE_AB … EDGE_CD and EDIT (A..D) are crossed by the
Framework, each through an explicit `FW_Combi(1) → FW_Combi(size)` chain.
- **Edges:** every edge slot has the two explicit values `edge(u,v,0)` and `edge(u,v,1)`. So the empty
  graph 000000 and the complete graph 111111 are ordinary selections; no fragment disappears.
- **Graphs:** these are the 2⁶ = 64 graphs compatible with the order A,B,C,D, not all labelled
  four-node DAGs.
- **Division of work:** the Framework crosses the structural choices and executes the programs.
  Reachability, fresh evaluation and path counts belong to the harness.

| Stage | Count |
|---|---:|
| Plans (XLSX = TOML graph) | EXACT 768 |
| Core `fw_final` (1 × 3 × 2⁶ × 4 × 1) | 768 |
| Reader / Executor / results_v2 | 768 / 768 / 768; one attempt each |
| Outcomes | **604 PASS / 164 DOMAIN_FAIL**; zero BROKEN, INFRA_FAIL or TIMEOUT |

The case sets decoded from `fw_final`, from the Reader AST and from the Executor records each equal
the 768 identities. All six edge axes carry both values, and the empty and complete graphs are
present.

## Outcomes by policy and edited node (64 graphs each)

| Policy | Edit A | Edit B | Edit C | Edit D | Total |
|---|---|---|---|---|---|
| closure_forward | 64 / 0 | 64 / 0 | 64 / 0 | 64 / 0 | **256 / 0** |
| direct_only | 44 / 20 | 56 / 8 | 64 / 0 | 64 / 0 | **228 / 28** |
| closure_reverse | 8 / 56 | 16 / 48 | 32 / 32 | 64 / 0 | **120 / 136** |

- **Empty graph:** passes under all policies and all four edits.
- **How verdicts were checked:** the verifier re-derived path counts by enumerating increasing
  intermediate-node subsets. Fresh values are Σ base[u] · paths[u][v], and each node changes by
  exactly 10 · paths[edit][v]. A case passes only if the initial cache equals the fresh reference and
  the final cache matches at all four nodes.

## Mechanisms

**direct_only: missing invalidation.** All 28 failures leave at least one reachable node out of the
dirty set.
- In 26 of them every wrong node is one that was never recomputed.
- In 2 of them (`G=101101|U=A` and `G=101111|U=A`, both containing the chain A→B→C→D and the edge A→D; the second
  also has B→D), D is dirty and recomputed,
  but it reads the never-invalidated C. So D is wrong too, together with C. The verifier checks that
  every wrong node is either non-dirty or read a missed node.
- With edit C or D, direct successors are the only descendants, so direct_only passes all 128 of
  those cases.

**closure_reverse: stale parent reads.** In all 136 failures the dirty set equals the full reachable
set; the order is what goes wrong. A node is recomputed before its parents, so it reads their old
cached values. With edit D there is nothing downstream, so all 64 pass.

**Witnesses** (base inputs 1, 2, 4, 8, then +10 on A; post-edit cache equals the initial cache):

| Case | Candidate | Initial cache | Updates (node: parent reads → new value) | Final | Reference (Δ) | Verdict |
|---|---|---|---|---|---|---|
| direct_only 100100 (AB, BC) | `401_0_0` | 1, 3, 7, 8 | A: → 11; B: A=11 → 13 | 11, 13, **7**, 8 | 11, 13, 17, 8 (10, 10, 10, 0) | DOMAIN_FAIL (C stale) |
| closure_forward 100100 | `145_0_0` | 1, 3, 7, 8 | A → 11; B: A=11 → 13; C: B=13 → 17 | 11, 13, 17, 8 | same | PASS |
| closure_reverse 100100 | `657_0_0` | 1, 3, 7, 8 | C: B=**3** → 7; B: A=**1** → 3; A → 11 | 11, **3**, **7**, 8 | 11, 13, 17, 8 | DOMAIN_FAIL (B, C stale; dirty set complete) |
| direct_only 110100 (AB, AC, BC) | `465_0_0` | 1, 3, 8, 8 | A → 11; B: A=11 → 13; C: A=11, B=13 → 28 | 11, 13, 28, 8 | 11, 13, 28, 8 (10, 10, **20**, 0) | PASS |
| closure_forward 111111 | `253_0_0` | 1, 3, 8, 20 | … D: A=11, B=13, C=28 → 60 | 11, 13, 28, 60 | Δ = 10, 10, 20, **40** | PASS |

- **Adding AC:** it puts C among A's direct successors, so direct_only recomputes C and passes. It
  also changes the graph and the formula: C's delta is 20 (two A→C paths), not 10. So the passing
  result is not "the same values as the chain".
- **Complete graph:** A reaches D along four paths (AD, ABD, ACD, ABCD), so D changes by 40.
  Reachability alone would not predict this; path multiplicity does.

## Topological orders under redundant edges (auxiliary, offline)

`topo_orders.py` produced `proof/topological-orders.json`, and the verifier re-derived it, including
agreement with the frozen proof.
- **Order sets:** across the 64 graphs there are 315 graph/order pairs. For each of the 31 absent
  forward edges already implied by a path, adding the edge leaves the complete set of valid orders
  unchanged, so the lexicographic minima are equal too.
- **Example:** 100010 (AB, BD) plus AD gives 101010. Its orders ABCD, ABDC, ACBD and CABD are all valid
  before and after.
- **Tie-breaking:** without a tie-breaking promise no single order is required. With a
  lexicographic-minimum rule, equal sets give an equal choice.
- **Values change:** this is about order validity only. The transitive edge changes this fixture's
  additive values, so topological redundancy does not imply numerical equivalence.
- **Not in the campaign counts:** the proof adds no Framework candidates.

## Limits

This is a deterministic local model: four nodes in a fixed topological order, one +10 edit, three
planted policies and equal weight per case. It says nothing about production spreadsheet or build
engines, or about failure rates.
