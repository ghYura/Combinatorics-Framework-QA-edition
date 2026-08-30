# Combinatorics Framework — assessment (short version)

Written after a full empirical study: 13 campaigns, 16 runs, 11,648 candidates through the real
chain (fwgen → Core Java+PG → Sieve → Reader → Executor), against a billing engine frozen by
sha256 before the first campaign. Long version: [ASSESSMENT_FULL.md](ASSESSMENT_FULL.md).
Evidence and method: [README.md](README.md) · report: https://claude.ai/code/artifact/be7fe9f6-673c-4d57-b721-4f63bf2315cb

---

## Verdict in three lines

1. **It works, and it finds a class of defect that classic technique structurally cannot.** Not
   because it runs more cases — because it can *express* cases the classic model has no words for.
2. **It is not a proof of concept.** It is a working instrument with production-grade guardrails
   and researcher-grade ergonomics. The engineering is mature; the authoring surface assumes an expert.
3. **It multiplies inputs, not judgment.** The oracle stays yours. That limit is real and permanent.

## What was actually proven

| | Classic (pairwise, 24 cases) | Classic (model **exhausted**, 525,312 cases) | Framework (11,648 candidates) |
|---|---|---|---|
| Invariants reached | I4, I8 | **I4, I8 — the same two** | I4, I5, I8 + 5 defect classes with no invariant |
| Distinct defects found | 2 | **2** | 10 |

Exhausting the classic model bought **nothing**. Twenty-four cases and half a million cases find
the same two defects, so the gap is not sampling — it is the model. Eight of the ten defects lie
outside what a parameter model can say. Six of them survive a build whose classic suite is green
at 87/87 with 100% verified 2-way coverage — including one that lets anyone who can reach the
webhook endpoint bill any customer, arbitrarily.

**Pairwise also found real bugs.** This is not a replacement for classic technique; it is a
different axis of coverage.

## Why it finds them — the one idea that matters

The unit of combination is an **action**, not a value. Slot values are fragments of a program, so a
candidate is a generated program rather than a filled-in parameter row. Once that is true, four
things stop being separate disciplines and become ordinary axes of one product:

| | Covering array | Verb algebra |
|---|---|---|
| Order | none — a canonical order is forced | `FW_Permut` — n! orderings |
| Multiplicity | one value per parameter | `FW_PermutR`, `FW_CombiR` |
| Interleaving | no notion of "during" | `FW_Optional` at slot position |
| What is combined | parameter values | fragments of a program |

Everything else in the study — chaos events, transport distortion, fault injection, mid-flight
config mutation, concurrency — is a consequence of that fourth line.

## Is it a proof of concept? No — and here is the evidence

**Signals of a mature system, observed directly:**

- Five trunks built clean offline with Maven; the chain ran 16 times with zero infrastructure failures.
- `fwgen`'s closed-form row estimate matched `fw_final` **exactly in every campaign**.
- Sieve removal counts matched hand-computed predictions exactly (161→464, then 261→364).
- **It fails closed where it counts.** It refused `--candidate-origin generated` under
  `trusted-local` with the correct reasoning ("an acknowledgement records a decision; it cannot
  authorize"). It refused to start a brace campaign it could not statically bound, demanding an
  explicit reason. The sieve *raises* rather than silently keeping rows when a bond names a
  non-materialized sheet — "an unenforceable bond has to be visible."
- `README_CANONICAL_TRUTH.txt` documents a real determinism hole, its fix, *and why the old number
  was not wrong*. Only a mature project writes that document.

**Signals it is not a finished product:**

- `estimate_core_combos` cannot bound the brace or `FW_Group` — so the two most powerful operators
  are exactly the ones that force a budget override.
- `--executor-pool` requires Java; the Python path is single-process.
- Authoring is raw and trap-rich (`seq_extra` must be top-level; no cell may start with `FW_`;
  `FW_ReplaceRE` rewrites code-strings, not text). All documented — still traps.
- Result triage is not built in. A campaign yielding 2,304 failures from one cause is a pile,
  not a report, until you add minimal-witness and axis-enrichment analysis yourself.
- One doc/implementation gap found: a positional gate resolves `pos` per *axis*, so a single
  `FW_Permut` sheet's internal order is invisible to a bond — despite a docstring implying otherwise.

## When to reach for it — and when not

**Reach for it when all four hold:** the failure you fear is *shape*-shaped (order, multiplicity,
interleaving, co-occurrence) rather than value-shaped; you have a cheap mechanical oracle
(invariant, differential reference, metamorphic relation, crash); a candidate is cheap to run; and
you can govern the space.

**Don't, when:** the oracle is human judgment; a candidate is expensive and the space won't prune;
the bug is value-shaped (pairwise is cheaper and sufficient); or the SUT can't be decomposed into
composable fragments.

## Other areas of application

Ranked by how well the engine's actual shape fits.

| Area | Why it fits | The verb that carries it |
|---|---|---|
| **Protocol & state-machine conformance** | loss, duplication, reorder, delay *are* the test space | `FW_Permut`, `FW_Optional`, `FW_Subsets` |
| **Distributed-systems consistency** | generate operation histories; an external checker is the oracle | `FW_PermutR` + sieve gates |
| **Compiler / optimizer testing** | pass-ordering bugs are notoriously order-shaped | `FW_Permut` over passes, `FW_Group` for nested pipelines |
| **Upgrade & migration paths** | not "which versions" but "in what order", with rollback injected mid-sequence | `FW_Permut` × `FW_Optional` |
| **Deployment / IaC plans** | app rollout ⋈ DB migration as two independently generated plans | the brace `FW_(…M:N)` |
| **Security testing** | authorization matrices are n-ary; attack chains are ordered | sieve n-ary bonds + `FW_Permut` |
| **LLM & agent evaluation** | multi-turn *order*, tool-call sequences, adversarial turns as sudden actions | `FW_Optional`, Analyzer Pareto front |
| **Regulatory / benefits rule engines** | eligibility is n-ary under hard legal constraints, and needs *auditable* coverage evidence | sieve `mapping`/`assert`/ordinal tier |
| **Scientific experimental design** | choosing which factor combinations to run when each costs real money | budget gate + sieve |

The engine is not really a test tool. It is a **governed generator of executable configurations
with a verdict and a selection front** — anything of that shape is in scope.

## My opinion

I went in expecting pairwise-plus. What it actually is is a **test-design algebra with an execution
engine attached**, and the verb table is a forcing function: *"the verb is dictated by the shape of
the freedom"* made me model the problem more honestly than I would have on my own.

The most valuable thing it gave me was not the 11,648 candidates. It was that **asking a hard
question became cheap**. Four campaigns came back clean — the lifecycle machine sound across 256
sequences, no concurrency divergence, no lost update, atomicity holding across 120 fault-and-retry
combinations. I would never have paid to ask those by hand, and each negative is a thing I now
know rather than assume.

Its sharpest single feature is one I did not expect: the sieve's bonds used as **hypotheses**
rather than filters. Each bond asserts "this shape is already explained"; the residue is what your
model does not account for. When my adjacency hypothesis was wrong, twenty survivors said so, and
following them produced a real refinement. That is a falsification loop, and I have not seen
another test tool that offers one.

Its permanent limit is the oracle. The framework put me in a state where the invoice numbers were
duplicated and the system's own audit said *clean*. It multiplies the inputs; it does not invent
the judgment. Whoever holds the lamp, the road is still chosen by a person — which is exactly what
the project's own documentation says, and it earned the right to say it.

---

## Addendum — was the first SUT complex enough?

**No, and the audit is unambiguous:** across all 13 campaigns the study used 5 of ~15 verbs and
never touched `FW_Group`, `FW_Cartes`, `FW_CombiR`, the bounded subset modes, `FW_Separator`,
`FW_ReplaceRE`, the Analyzer, sharding, gRPC or the Java executor path. A 426-line single-class
module has no topology, so the composition operators had nothing to compose.

But the study's two claims need *different* SUTs, and conflating them would be an error:

| claim | what it needs | verdict on SUT v1 |
|---|---|---|
| pairwise has a **structural** blind spot | a model small enough to **exhaust** | **ideal** — 663,552 cases in 47s is only possible because it was small |
| the framework's **ceiling** is high | topology, protocol, real faults | **inadequate** |

The anti-pairwise result therefore stands, and is arguably *stronger* on a simple SUT: exhausting
the model removes sampling from the argument entirely, and that control is impossible on a complex
system. What v1 could not do is show the framework at full stretch.

**A second study was run to close that gap** — [../proof_fulfilment](../proof_fulfilment): a
475-line, five-service order pipeline with a saga, compensation, idempotency keys, retries and
timeouts, as a deterministic simulation so the delivery schedule is enumerable data. 4,114 further
candidates. It found two severe distributed-systems defects (a retry that re-executes the business
operation; a saga orchestrator with no idempotency guard at all, where every downstream service has
one), gave the **brace its first genuine use** (3 computed order-pairs ⋈ 6 computed fault-pairs =
exactly 18, a construct no flat cartesian can express), and surfaced three further observations
about the framework: the estimator honestly flagging its own limits, the Analyzer reporting success
over an empty corpus, and a concatenator trap that broke 2,048 candidates at once.

**Net effect on this assessment:** the verdicts above are unchanged, and two are reinforced —
*authoring is the immature surface* (the concatenator trap cost a whole run) and *saturation is the
main practical obstacle* (the second study's first campaign was 100% failing on a single defect and
told me nothing until it was masked). The framework's ceiling is higher than the first study showed;
its ergonomics are exactly as rough as the first study suggested.

---

## Advice

### If you are using it

1. **Start with the oracle, not the space.** Your findings are capped by what you can judge
   mechanically. The framework put me in a state where invoice numbers were duplicated and the
   system's own audit said *clean* — the state was free, the judgement was not. Before designing any
   space, write down what "wrong" looks like as an invariant, a differential reference, a
   metamorphic relation, or a crash.
2. **Model the freedom, let the count fall out.** Never pick a verb to hit a number. Ask what kind
   of freedom each piece is — one of a set, an ordering, a subset, a repetition, a may-or-may-not —
   and the verb is forced. This is the project's own rule and it is the best advice in its docs.
3. **Expect your first campaign to be saturated.** It happened in both studies: one dominant defect
   at 100% or 27% of candidates, drowning everything else. That is normal, not failure. Mask the
   explained shape — with a sieve bond, or a config flag — and re-run. The residue is the finding.
4. **Cross the disciplines that are normally separate phases.** Functional × stress × chaos,
   transport pathology × functional scenario, fault injection × the retry that follows. Every
   highest-value finding in both studies came from a crossing no single testing discipline owns.
5. **Keep the negatives.** Four campaigns came back clean, and they are worth as much as the
   findings: things now known rather than assumed. Record them.
6. **Freeze the system under test with a hash before you start**, and put the check in
   `RunMeFirstOnce` so a drifted build cannot silently invalidate a whole campaign.
7. **Write the analysis before the big run.** A campaign with thousands of failures is a pile until
   something reduces it to a minimal witness per invariant plus a per-axis enrichment table.

### If you are developing it

Ordered by what cost the most during two studies.

1. **Ship result triage.** Minimal-witness reduction and axis enrichment turn a campaign into a
   report. This is the largest single gap between instrument and product; `analyze_run.py` here is a
   crude 120-line sketch of what belongs in the box.
2. **Make bonds-as-hypotheses a documented, first-class loop.** It is the sharpest idea in the
   framework and currently an emergent use. "Mask what is explained, inspect the residue, and diff
   the residue between runs" deserves a command and a page, because saturation is the number one
   practical obstacle and this is the cure.
3. **Fix the concatenator default for `raw` code slots.** A verb emitting several values from one
   sheet joins them with an empty string; for code fragments that silently produces one long line.
   It cost a complete 2,048-candidate run here, and it was loud only by luck — a variant producing
   valid-but-wrong code would be silent. Either default to a newline when `raw=true`, or warn at
   authoring time when a multi-value verb's values do not end in one.
4. **Make an empty Analyzer corpus loud.** `✓ analyzer ran` printed over an empty `metrics.kv` with
   no `provenance.json` reads as success. The docs already warn about this; the tool should enforce
   what the docs advise.
5. **Give the brace and `FW_Group` a pre-count.** *(brace: done — see below; `FW_Group`: still open.)*
   They are the flagship operators and they were the two that tripped the budget gate, so the most
   powerful capability had the worst first-run experience.
6. **Fix the `pos` phrasing in the sidecar schema** and add a worked ordering-with-bonds example.
   *(done.)* Five minutes, and it prevents a whole class of silently-inert constraint.

### What was implemented from this list

- **#3 the concatenator trap** — `fwgen.check_raw_row_arity` flags a `raw` slot whose verb can place
  two or more values in one row when a value ends in neither a newline nor a statement terminator.
  Warns in compatibility mode, raises under `strict`, changes no generated workbook. 0 false
  positives across all 156 repo specs; catches the exact shape that broke 2,048 candidates.
- **#5 the brace pre-count** — `fwgen.brace_cardinality` now sizes a join from its operands' declared
  verbs, verified against the Core's `BraceOperationHandler`: `1:N`/`M:N`/`M:1` are `|A|·|B|`;
  `1:1`/`M:M` are the length-matched `Σ_L A_L·B_L` (`readWithCardinality`). EXACT on all three
  observed ground truths (6, 9, 18), and the brace campaign now runs with no `--allow-extreme` and
  no `--override-budget`.
- **#6 the `pos` wording** — corrected in `sidecar_schema.md` and `sieve.py`, with a new
  *Ordering and `pos`* subsection carrying the one-slot-per-step example.

**`FW_Group` remains unsized, deliberately.** The obvious model — the slot's verb applied twice, which
reproduces the canonical `README_CANONICAL_TRUTH.txt` example exactly (`FW_Subsets` over 2 values →
4 rows → 2⁴ = 16) — does **not** hold end to end. Measured through the full chain, a grouped brace
operand contributed **6** rows where the first-order count is 4 and the group formula predicts 16.
Since the observed value is neither, the first-order count is not even an upper bound, and no sound
static bound is available. `brace_cardinality` therefore returns UNKNOWN for a grouped operand rather
than guessing, and the budget gate keeps demanding an explicit decision — which is the correct
behaviour until someone traces `SheetWorker`'s group pass and its `curM` iteration to ground truth.

### On positioning

- **Lead with the thesis, not the verb table.** "More verbs than pairwise" invites the wrong
  comparison and undersells it. The actual claim is that *the unit of combination is an action, not
  a value* — and order, repetition, interleaving and chaos follow from that one decision.
- **Lead the evidence with the exhaustive control.** "We ran the entire classic model — 525,312
  cases — and it found the same two defects as 24 cases" is the argument that cannot be waved away
  as a sampling accident. It is stronger than any candidate count.
- **Do not fight pairwise; place it.** Pairwise finds value-shaped defects cheaply and did find real
  ones here. This finds shape-shaped defects. Saying so plainly is both true and more persuasive
  than a claim of replacement.
- **Do not soften the guardrails to make demos easier.** The origin refusal, the budget gate, the
  unenforceable-bond error and `README_CANONICAL_TRUTH.txt` are the strongest signals of seriousness
  in the repository. They are the reason this reads as an instrument rather than a prototype.

### Precomputation estimate — what changed

Every figure below was checked against a real chain run, not just reasoned about.

| scenario | before | after | ground truth |
|---|---|---|---|
| brace `1:N` / `M:N` / `M:1` | UNKNOWN | **EXACT** `\|A\|·\|B\|` | 6, 9, 18 ✓ |
| brace `1:1` / `M:M` | UNKNOWN | **EXACT** `Σ_L A_L·B_L` (length-matched) | derived from `readWithCardinality` |
| chained braces | counted twice (4×12=48) | **EXACT** 12 — an intermediate join is not also a factor | 12 ✓ |
| nested `FW_(…)` in an operand slot | sized from the declared verb (wrong) | resolved to the prior brace target, or UNKNOWN | — |
| `FW_Group` | "row-preserving", provably too low | **BOUNDED [1, emissions]** | 6 ∈ [1,16] ✓ |
| brace over a grouped operand | UNKNOWN | **BOUNDED [1, ceiling]** | 12 ≤ 32 ✓ |
| post-sieve | `[0, mandatory]` — unusable | **EXACT**, by running the sieve's own predicate in advance | 464, 364 ✓ |
| **optional slot, multi-row verb** | **wrong — hard-failed the run** | **EXACT** rows+1 | 5 ✓ |
| optional × 2, one multi-row | wrong | **EXACT** 20, decomposing as e₁=7, e₂=12 | 20 ✓ |
| optional, single-select | correct | unchanged | 8 ✓ |

Two of these were latent **bugs**, not just weak estimates:

- **Chained braces double-counted**, inflating the estimate by the intermediate join's size.
- **An optional slot with a multi-row verb was sized by its declared values instead of its result
  rows.** Core builds `fw_opt<size>` from the result table, so `FW_Subsets` over 2 values is 4 rows
  and 5 Reader branches, not 3. This did not merely mis-estimate — it tripped the reader's
  `emitted_eq_expected` invariant and **failed the run outright**, so a multi-select optional slot
  was effectively unusable. Fixed at the root (`optional_contract._optional_slot_rows`) and in both
  mirrors (`fwgen`, `seedbias`). No shipped spec changes: all 156 use single-select optional slots,
  where rows and values coincide.

`FW_Group` stays BOUNDED on purpose. Decoding the generated candidates showed the group *emits*
`verb-applied-twice` rows and then DISTINCTs them — `FW_Subsets` over 2 values: 4 first-order rows,
16 emissions, **6 distinct**. The collision rate is a property of the data (the canonical file
records the same 16 collapsing to 13 or 14 under two orderings), so the emission count is a provable
ceiling and nothing below 1 is provable. Note 6 > 4: the first-order count is not a bound either way.

The sieve pre-count fails soft by design — any bond it cannot evaluate (a `when` over params a value
does not declare, or one referencing an `FW_Optional` sheet, which the sieve *defers* rather than
enforcing on `fw_final`) falls back to the conservative range. An optimisation must never make the
estimate worse than not having it.

---

## Third study — the rest of the vocabulary, and what using it found

[../proof_authz](../proof_authz) exists because an audit of the first two studies was unflattering:
five of roughly fifteen verbs, and **none** of the sieve's five bond tiers. Not because those are
weak — because a billing account and a message bus offered them nothing to bite on. An
authorization engine does: seniority is ordinal, a role's actions are a dependent allowed-set, a
clause is built from clauses.

| campaign | predicted | delivered | capability shown working |
|---|---|---|---|
| `e1_bounded` | 648 | 648 | `FW_Subsets_EXACT/RANGE/BEFORE` |
| `e2_multiset` | 72 | 72 | `FW_CombiR` multisets, `FW_Permut` orderings |
| `e3_secondorder` | ≤6 | 6 | `FW_Group` + `FW_Separator` + brace |
| `e4_bonds` | 288→133 | 288→133 | `orders`, `assert/geSheet`, `mapping`, `condition`, `when` |

**`FW_Group` is demonstrated by content, not by count.** `FW_Combi(2)` over three predicates gives
three pairs; the assembled candidates carry *four* tokens each — those pairs recombined as atoms,
C(3,2)=3 groups — with `AND` woven between every element. The count 6 = 3×2 would have looked
identical with no grouping at all.

**`e4` is the sharpest single result in three studies.** The post-sieve figure 133 was predicted by
the pre-count, reproduced independently by a hand model of the four bonds, and confirmed by the
sieve removing 155 of 288. All 133 survivors pass — the bonds carve the space to the legally
reachable region of an authorization model, and inside it the engine holds. A negative result that
means something, because the space it covers is precisely defined.

### The defect this study found in the framework

**`FW_Permut(k)`'s argument is inert.** `PermutationsSimpleG` takes no size argument, so the slot
emits all n! orderings. `verb_output_count` returned `math.perm(n, k)` — *smaller*, and a budget
gate that under-states is wrong on the only side that matters, because it approves the run.

It hid because the two agree at n=3, k=2 (P(3,2) = 3! = 6), which is the shape every existing test
used. It surfaced only because a campaign printed its fragments: `FW_CombiR(2)` produced two,
`FW_Permut(2)` produced three.

It is live in shipped material. `10_third_order_brace` declares `FW_Permut(2)` over a 16-value
sheet; the plan reported **EXACT 530,841,600,000** while that slot alone emits 16! =
20,922,789,888,000 rows — confidently stated, and low by 39× for the spec. Corrected in the
estimator, with a spec-load warning; the engine semantics are left as the owner's call.

### And a defect in the triage stage this session added

`e3` failed on 100% of candidates, and triage returned **six findings from six failures** — no
reduction, exactly when a saturated run needs it most. With no passing candidates the
passing-set rule makes every key classifying. The fix uses **balance**: a combinatorial design
spreads an axis evenly by construction; an outcome is constant or lopsided. Both halves are
load-bearing — constancy alone would bury a rare finding among 399 of its dominant sibling.

### What this adds to the assessment

Nothing above changes the verdicts. Two are reinforced:

- **The framework's expressiveness is now demonstrated across its whole vocabulary**, not argued.
  Every verb and every bond tier has been run end to end against a frozen SUT with predicted counts.
- **Used seriously, it finds defects in itself.** Across three studies the framework's own
  guardrails caught four of my errors, and the campaigns found two defects in the framework and one
  in the tooling built for it. The `FW_Permut(k)` case is the strongest evidence for the study's
  central claim in miniature: the *count* agreed and the *content* did not, and only a method that
  generates real artifacts could tell the difference.
