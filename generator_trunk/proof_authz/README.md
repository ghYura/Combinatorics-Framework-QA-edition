# proof_authz — the third study: the framework's full vocabulary

The first two studies ([proof_billing](../proof_billing), [proof_fulfilment](../proof_fulfilment))
proved a structural claim about pairwise and exercised order, repetition, interleaving and chaos.
An audit of both showed they used **five of roughly fifteen verbs** and **none of the sieve's five
bond tiers**. Not because those are weak, but because a billing account and a message bus gave them
nothing to bite on: no ordinal domain, no dependent allowed-sets, no nested structure.

This study picks a system under test where they are the natural way to say what is true, and writes
the SUT independently of them.

**The consolidated evidence across all three studies:**
[../../docs/43_COMBINATORIAL_TESTING_EVIDENCE.md](../../docs/43_COMBINATORIAL_TESTING_EVIDENCE.md)

## The system under test

`sut/authz.py` — 351 lines, sha256 `d1a5a16e…`, frozen read-only before the first campaign.

An authorization policy engine: roles with a seniority **rank**, roles that **include** other roles,
permissions as `(action, resource-pattern)`, explicit allow/deny **rules with conditions**, and a
resolver answering `can(principal, action, resource, context)`. Deny overrides allow; allow
overrides an inherited grant; anything else is denied.

Seven invariants form the external oracle (`audit()`, which the engine never consults):

| | |
|---|---|
| A1 | every effective permission traces to a grant or an allow rule |
| A2 | an applicable deny wins, wherever the allow came from |
| A3 | role expansion terminates and is idempotent |
| A4 | `revoke` returns the principal to its state before `assign` |
| A5 | seniority alone never confers a permission |
| A6 | a resource pattern never matches across a path-segment boundary |
| A7 | a rule's conditions are conjunctive |

## Why this domain fits the unused vocabulary

| the domain says | the framework says |
|---|---|
| a policy has *exactly two* grants, *one or two* rules, *at most one* condition | `FW_Subsets_EXACT/RANGE/BEFORE` |
| two roles can carry the *same* grant | `FW_CombiR` — a multiset, not a set |
| assign/revoke is tested *in both orders* | `FW_Permut(k)` — ordered pairs from k |
| a clause is built from clauses | `FW_Group` over produced rows, `FW_Separator` as the AND glue |
| seniority is **ordinal** | `orders` + `assert { geSheet }` |
| a role may only hold certain actions | `mapping` — a dependent allowed set |
| deleting is out of scope *in production only* | `condition` — a contextual guard |
| sensitivity is a property of the **value** | `params` + a `when` predicate |

## Campaigns

| dir | mandatory | post-sieve | what it exercises |
|---|---|---|---|
| `e1_bounded` | 648 | 648 | `FW_Subsets_EXACT(2)`, `_RANGE(1,2)`, `_BEFORE(2)` |
| `e2_multiset` | 72 | 72 | `FW_CombiR(2)` multisets, `FW_Permut(2)` k-permutations |
| `e3_secondorder` | ≤6 | ≤6 | `FW_Group` + `FW_Separator` + brace — second order |
| `e4_bonds` | 288 | **133** | `orders`, `assert/geSheet`, `mapping`, `condition`, `when` |

Every count above was predicted before running: 648 = 3 × C(4,2) × (C(3,1)+C(3,2)) × (C(2,0)+C(2,1)) × 2,
and 72 = 2 × C(3+2−1,2) × P(3,2). E4's post-sieve **133 of 288** was produced by the sieve pre-count
and independently reproduced by a hand-written model of the four bonds — the first time that
pre-count has faced `assert`, `mapping`, `condition` and `when` together rather than plain `sets`.

`e3_secondorder` is BOUNDED rather than exact on purpose: a grouped brace operand's row count is
data-dependent (see [../../docs/42_RESULT_TRIAGE.md](../../docs/42_RESULT_TRIAGE.md) and the
`FW_Group` note in the estimator), so the planner states a provable ceiling instead of a number.

## Results

All four campaigns ran the full chain. Every predicted count was delivered.

| campaign | candidates | failing | findings after triage |
|---|---|---|---|
| `e1_bounded` | 648 | 432 | **3** — `A6`, `A6+A7`, `A7` |
| `e2_multiset` | 72 | 36 | **1** — `A6` saturates |
| `e3_secondorder` | 6 | 6 | **1** — `A6+A7` |
| `e4_bonds` | 133 (of 288) | **0** | — |

`e4` is the result worth reading twice. The sieve removed 155 of 288 rows, leaving exactly the 133
the pre-count predicted and a hand model of the four bonds independently reproduced. All 133 pass:
the bonds carve the space down to the legally reachable region of an authorization model, and inside
that region the engine holds.

`e3` needed **no** budget override in the end — the bounded ceiling from the grouped operand was
enough for the gate to size it. And `FW_Group` is confirmed by the assembled content rather than by
the count: `FW_Combi(2)` over three predicates gives three pairs, and each candidate carries *four*
tokens — those pairs recombined as atoms, C(3,2)=3 groups — with `AND` woven between every element.
The count 6 = 3 × 2 would have looked identical with no grouping at all.

### What the campaigns found in the framework itself

`e2` printed its fragments, and `FW_CombiR(2)` produced two while `FW_Permut(2)` produced three.
`PermutationsSimpleG` takes no size argument: `FW_Permut(k)` emits all n! orderings and the k is
inert, while the estimator reported the smaller `P(n, k)`. It was live in a shipped scenario whose
plan claimed `EXACT 530,841,600,000` for a slot that alone emits 16!. Corrected in the estimator
with a spec-load warning; the engine semantics are the owner's call. See
[../../docs/43_COMBINATORIAL_TESTING_EVIDENCE.md](../../docs/43_COMBINATORIAL_TESTING_EVIDENCE.md).

`e3` also broke the triage stage: failing on 100% of candidates, it returned six findings from six
failures — no reduction, exactly where a saturated run needs it. Fixed by falling back to balance
when there is no passing set to compare against.

## Reproducing

```bash
cd generator_trunk
python3 bundle_run.py proof_authz/e4_bonds --db bauthz4 --lang py --sieve \
  --main-db-user postgres --main-db-password pass \
  --results-db-user postgres --results-db-password pass \
  --execution-policy-profile trusted-local \
  --candidate-origin reviewed-checked-in \
  --acknowledge-trusted-local "authz study"

python3 bundle_run.py triage /tmp/fw_work/bauthz4 --write
```

## What is already known about the SUT

Three defects were confirmed by driving the module directly, before any campaign ran. They are
recorded here so the campaigns' findings can be told apart from what was already visible:

```
assign("alice","editor") x2 then revoke once  ->  holds []      (A4: revoke does not invert assign)
match_resource("docs/*", "docs-shadow/x")     ->  True          (A6: the pattern crosses a segment boundary)
conditions {mfa,vpn}, context {mfa} only      ->  True          (A7: conditions are disjunctive)
```

A6 is a property of the matcher rather than of a scenario, so it will fire on nearly every candidate
and saturate the first campaign. That is the expected shape of a first run: mask the explained
finding — with a bond or a config flag — and read the residue. `bundle triage` reduces the pile
either way.
