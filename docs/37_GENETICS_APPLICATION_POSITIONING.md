# 37 — Positioning a genetics-model-testing application in the Bundle line

> **Status update, 2026-08-01.** The Phase 01–05 consolidation is merged (`main`, local only). D1 and
> D6 are decided and implemented. **D3 is authorized at narrow scope and Stage 2 is done**:
> the model and its exact oracle are integrated into local `main`. Stages 3–9 — mutants, a factor
> space, baselines and any engine run — are **not** started. **D7 is postponed and present as a guarded
> stub** (`expert_model.py`).
>
> **Original status: planning only.** This
> document is deliverables 1–5 of that authorization request, plus the Part A worktree audit that
> must complete first.

---

## 1. Confirmation of the architectural interpretation

The interpretation is **correct, and I would add one qualification.**

Confirmed as stated:

| Proposition | Verdict |
|---|---|
| Core + Reader + Executor remain the fundamental combinatorial engine | ✅ correct — nothing in Phase 01–05 changed them; Phase 01 exists precisely to make that boundary machine-checkable |
| The genetics application is a **new vertical application** of the original engine | ✅ correct |
| It is **not** an extension of `AI_combi_testing_platform` | ✅ correct, and architecturally enforceable — see §2 |
| It is **not** a fork, and **not** a replacement of any engine component | ✅ correct |
| It **cannot** establish biological truth | ✅ correct — see §5, risk R1 |
| It is **not** another artificial SUT built to improve an evidence report | ✅ correct, and this must stay true under pressure — see §5, risk R2 |
| Genetics code models **textual/mathematical representations**, never real human DNA or clinical decisions | ✅ correct |

> **Update, same day: the qualification below has been addressed.** The harness now lives in
> `generator_trunk/bundle/study.py` — the control plane, which every layer above it may import, so a
> genetics application needs no cross-layer exception to use it. `store_flagship.py` no longer
> imports `pipeline_flagship` at all, and `reconcile.py` imports no SUT at module scope. Exit
> criterion met: both existing SUTs still reconcile (`--level l2`, `--level s2`, `--level l3` all
> RECONCILED) and the architecture gate reports no dependency-direction violations. §4 Stage 1 is
> **done**; the paragraph below is kept because it is the reasoning that justified doing it.

**The qualification (resolved).** The reusable Phase 05 assets were **not in a reusable shape.** The
baseline-comparison harness (`evaluate_suite`, `compare`, `format_comparison`, and the OFAT /
pairwise / Cartesian generators) currently lives inside `flagship/pipeline_flagship.py` — a module
that also contains the record-pipeline mutants and factor space. The second SUT already demonstrates
the consequence: `store_flagship.py` opens with `from generator_trunk.flagship import
pipeline_flagship as F` and therefore drags in a pipeline SUT it has no use for. `reconcile.py` is
worse: it imports *both* SUT modules at module scope to populate its `TWINS` registry.

A genetics application built on top of that would import two irrelevant SUTs to obtain a comparison
function. That is a coupling defect introduced by my own Phase 05 work, it is my responsibility, and
it must be fixed **before** the genetics branch rather than inherited by it. It is Stage 1 of §4.

---

## 2. Proposed branch and directory structure

**Implementation branch (now locally integrated):** `feature/genetics-model-testing`, cut from
`main` *after* the Phase 01–05 consolidation was accepted. The ordering mattered: an earlier branch
would have missed the evidence layer it was supposed to reuse.

```text
generator_trunk/genetics_model_testing/
├── README.md                     what this is, and the scientific boundary, stated first
├── __init__.py
├── model/                        the DOMAIN — mathematically closed, no engine imports
│   ├── genome.py                 loci, alleles, haplotypes, genotypes as immutable values
│   ├── operations.py             point mutation, insertion, deletion, recombination
│   ├── environment.py            environment variables and their interaction terms
│   └── oracle.py                 the exact oracle: independent recomputation + invariants
├── study/                        the EXPERIMENT — mutants, factor spaces, baselines
│   ├── mutants.py                versioned known faults (one single-locus, one epistatic)
│   ├── factors.py                factor spaces at two widths
│   └── build.py                  assignment -> model instance (the in-process twin)
├── scenarios/                    the ENGINE's half — spec only, no Python logic
│   ├── g1_smoke/scenario.toml
│   ├── g2_narrow/scenario.toml
│   └── g3_wide/scenario.toml
├── run_genetics.py               thin launcher over bundle_run.py (no second orchestrator)
└── manifest.json                 bundle.sut-manifest/v1 entry
```

Plus, outside the application:

```text
generator_trunk/genetics_model_testing/test_genetics_model.py   domain + oracle
generator_trunk/test_bundle_genetics_study.py                    study + baselines (repo convention)
docs/41_GENETICS_MODEL_TESTING.md                                future evidence and boundary
```

**Layer classification.** `generator_trunk/bundle/architecture.py` will refuse to run until the new
root is classified — that gate has already caught three of my own new directories, so this is not a
theoretical step. Two options, an owner decision (§5, D6):

> **Decided and implemented (owner authorization, 2026-08-01): the new `domain-application` layer.**
> `may_import` = engine layers + itself. It may import neither `reference-application` nor
> `engine-demonstration`, so the gate — not a convention — keeps genetics out of the AI platform and
> stops it borrowing the flagship SUTs. Proven by introducing both illegal imports deliberately: four
> violations reported with file and line, gate exit code 1. The root
> `generator_trunk/genetics_model_testing` is declared *before the directory exists*, so the boundary
> applies to the application's first commit. See [docs/30](30_ENGINE_FIRST_ARCHITECTURE.md).

**What the directory must never contain:** an import of `AI_combi_testing_platform`, `llm_*`,
`face1_new`, `intake`, or either Phase 05 SUT. The architecture gate can enforce this as a declared
forbidden edge rather than a convention.

---

## 3. Dependency map — what is genuinely domain-neutral

### 3.1 Reusable as-is

| Component | Why it is neutral | Genetics use |
|---|---|---|
| `bundle/architecture.py` | layer model + AST dependency-direction gate; knows nothing about any domain | classify the new root; declare forbidden edges |
| `bundle/coverage.py` + `bundle-reference-coverage-v1.schema.json` | coverage targets over declared layers | coverage target for the new layer |
| `bundle/policy.py` | `ExecutionAuthorization`, candidate origins, execution profiles | genetics candidates start as `reviewed-checked-in` / `trusted-local` |
| `bundle/optional_contract.py` | the P ⊇ R invariant over `FW_Optional` sizes | **directly load-bearing** — environment factors and conditional variants are `FW_Optional` |
| `bundle/capabilities.py` | dimension/rule registry | add genetics values; no machinery change |
| `bundle/release.py` | skip classification, release manifest, SBOM, dependency pins | unchanged |
| `bundle/provenance.py` | licence/provenance inventory and blockers | **needed** — the origin of any model parameters is provenance |
| `bundle/sut_manifests.py` + schema | canonical SUT inventory, CI wiring check, drift detection | the genetics model becomes a canonical SUT |
| `constraints/sieve.py` | binary bonds over `fw_final` columns, **including the FW_Exclude fix from Phase 05** | removes mathematically impossible genotypes |
| Scenario **idioms** (not code) | top-level `seq_extra`; `FW_Exclude` on every brace operand; `FW_()` in both operand positions; helper-sheet debris tolerance; the `*_DONE` guard for optional splices | the genetics scenarios reuse the pattern verbatim |

### 3.2 Reusable **after** the Stage 1 extraction

| Component | Current home | Problem | Required change |
|---|---|---|---|
| `Verdict`, outcome taxonomy (`PASS`/`DOMAIN_FAIL`/`BROKEN`/`TIMEOUT`/`INFRA_FAIL`) | `flagship/pipeline_flagship.py` | inside a SUT module | move to a neutral module |
| `evaluate_suite`, `compare`, `format_comparison` | same | same; already parameterised by `factors` / `builder` / `judge_fn` / `baselines`, so the work is a move, not a redesign | move |
| `cartesian_suite`, `pairwise_suite`, `ofat_structural_suite` | same | same | move; **add `twise_suite(t)` and `random_suite(budget, seed)`** — see §4 Stage 4 |
| `reconcile.py` — stage-artifact counts, optional-contract check, metric-multiset comparison | `flagship/` | imports both SUT modules at module scope for `TWINS` | invert: each SUT *registers* its twin, the reconciler imports none |
| `run_flagship.py` `Level` (declared expected count, budget gate, derivation string) | `flagship/` | named for one study | generalise and rename |
| `METRIC_KEYS` / `metrics_line()` contract | `engine_demo/record_pipeline.py`, duplicated in `txn_store.py` | duplicated per SUT | one declaration; genetics reuses the same keys so one Analyzer config serves all |

**Acceptance test for Stage 1:** both existing SUTs' reconciliations must still produce
byte-identical results (10 runs, 17 088 candidates). If the extraction changes a single metric tuple,
it changed behaviour and must be reverted.

### 3.3 Explicitly **not** reusable — do not copy

`engine_demo/record_pipeline.py`, `engine_demo/txn_store.py`, `flagship/pipeline_flagship.py`
(mutants/factors/build), `flagship/store_flagship.py`, `flagship/levels.py`, every
`bundle_native_*/scenario.toml`; and all of `AI_combi_testing_platform/`, `llm_arch_search/`,
`llm_loop/`, `llm_transformer_campaign/`, `llm_selfposed_bundle_tasks/`, `face1_new/`, `intake/`,
`invitation_wizard/`, `landing/`.

The two Phase 05 SUTs are **worked examples of the method**, not a framework. Copying either one's
shape into genetics would reproduce its assumptions along with its structure — which is exactly the
common-authorship confound §5 R2 is trying to avoid.

---

## 4. Staged implementation and validation plan

Each stage has an exit criterion that is checkable, not a feeling.

| Stage | Work | Exit criterion |
|---|---|---|
| **0** | Consolidate Phase 01–05 into `main` (Part A below) | owner accepts the commit plan; full suite green; commits made only on explicit instruction |
| **1** | ~~Extract the neutral study harness; invert the twin registry~~ **done** — `bundle/study.py`; both SUTs reconcile; the `domain-application` layer role is declared and enforced | ✅ met |
| **2** | ~~Genetics **model** and **exact oracle**~~ **done** — 12 loci, closed integer arithmetic, immutable values, no I/O | ✅ four distinct layers: the observed reciprocal products are checked by direct tuple construction; the reference trait evaluator bypasses executable-path helpers; both length bounds are computed without executing; and the viability contract remains a domain verdict. Each check is reachable by test, including witnesses for both viability bounds |
| **3** | Two versioned faults: one single-locus, one **epistatic / interaction-only** | **not started.** The model already carries the structure a fault would exploit: loci 1+3 predict +6 additively and deliver **+18**, and locus 2 contributes 0 at baseline but +7 when hot. Both proven by test |
| **4** | In-process baseline comparison at two widths: **OFAT, pairwise, t-wise (t=3), random under equal budget, exhaustive** — all five now exist in `bundle/study.py` and are back-ported to both existing SUTs | zero false positives on the control; costs reported alongside detections. **Note the result on the existing SUTs: t=3 and random both find the interaction defects, so a genetics study must not repeat the withdrawn claim** (docs/35 §3.3) |
| **5** | Bundle-native scenario through the real Core → Reader → Executor → Analyzer: `FW_Group` for linked regions, `FW_Optional` for environment, `FW_Exclude` for impossible states, nested braces for haplotype → genotype → environment → operation | engine detection counts equal the in-process counts exactly |
| **6** | Sieve constraints removing mathematically/biologically invalid instances | proven that **only** invalid instances were removed: every removed assignment fails construction, no kept assignment does, detections unchanged |
| **7** | Full-chain reconciliation + scaling ladder + declared budget breakpoint | every stage count agrees; metric multisets equal the twin; the breakpoint is measured against a budget declared *before* the runs |
| **8** | SUT manifest, capability-matrix entries, provenance, release/honesty gates | `provenance --fail-on-blockers` reports no *new* blockers; SUT manifest passes drift detection |
| **9** | Written evidence with the scientific boundary stated in the first paragraph | an independent reader can falsify each claim from a named command |

**Note on Stage 4.** At planning time, Phase 05 lacked two baselines: **t-wise (t=3)** and **random
under equal budget**. They have since been implemented in the neutral harness and back-ported to both
existing SUTs. Random-under-equal-budget remains the strongest and least flattering baseline
available — a method that cannot beat random sampling at the same candidate count has not earned its
complexity. A genetics study must reuse both baselines rather than reopen that completed framework
work.

---

## 5. Risks and owner decisions

### Risks

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| **R1** | **Scientific overclaim** — a reader takes "validated the model" as "validated the biology" | **highest** | The boundary sentence appears in the module docstring, the README, the future evidence document, and at least one test name. Not in a footnote. Bundle validates *models, simulators, transformation pipelines and their implementations*; it says nothing about biological causality |
| **R2** | **Common authorship, third instance.** Both Phase 05 SUTs were designed by me from one idea of what an interaction defect is. A genetics model *also* designed by me — in a domain where I am not an expert — would be the third instance of one intuition, dressed as independent replication | **high** | State it up front. Treat the genetics study as an *engineering* demonstration until a genetics/domain expert independently selects the model and the faults. Do not present it as external validation before then |
| **R3** | **Oracle credibility.** An "exact oracle" is exact *for the model*. It cannot certify that the model is right | high | Two independent oracle layers, and explicit wording that both judge the model, not nature |
| **R4** | **Ethical / regulatory perception.** Even synthetic genetic modelling attracts scrutiny | medium-high | No real DNA, no clinical framing, no identifiable data, no external data sources. Enforce with a test asserting the model module has no network or file I/O |
| **R5** | **Scope creep into a genetics simulator.** Bundle is a construction and evidence engine | medium | The model stays small and closed. If it needs a simulator, the simulator is the SUT — chosen by a domain expert — not something we write |
| **R6** | **Stage 1 refactor destabilises Phase 05 evidence** | medium | Byte-identical reconciliation of all 10 existing runs is the exit criterion, not "tests pass" |
| **R7** | **Combinatorial ceiling.** 20 loci is astronomically larger than anything executed so far; the measured ceiling is ~6 800 candidates per version per 10-minute gate on this host | medium | Bound the model before writing it; declare the budget first; state the breakpoint in the plan rather than discovering it |
| **R8** | **Reviewers conflate the genetics app with the AI platform** | low-medium | Separate layer, declared forbidden import edges, enforced by the architecture gate |

### Owner decisions required

| # | Decision | Blocks |
|---|---|---|
| ~~**D1**~~ | ~~Accept or amend the Phase 01–05 commit plan below~~ — **accepted and locally merged** | resolved |
| ~~**D2**~~ | ~~Explicit instruction to commit~~ — **granted; the bounded commits were created locally, with no push** | resolved |
| ~~**D3**~~ | ~~Authorize the branch~~ — **granted at narrow scope; Stage 2 delivered, Stages 3–9 not started** | resolved |
| ~~**D4**~~ | ~~Confirm directory `generator_trunk/genetics_model_testing/`~~ — **confirmed by the Stage 2 implementation** | resolved |
| **D5** | ~~Where the Stage 1 extraction lands~~ — done on the consolidation branch | resolved |
| ~~**D6**~~ | ~~Layer role~~ — **decided: new `domain-application` layer, implemented and enforced** | resolved |
| **D7** | Whether and when a domain expert selects the model and the faults | **postponed by owner instruction**; present as a guarded stub in `expert_model.py` carrying the notice *"for special user's request, separately against of any future fixes"*. Until decided, anything built on this model is an **engineering demonstration**, never external validation |
| **D8** | Approve the scientific-boundary wording for any external publication claim | publication |
| ~~**D9**~~ | ~~Whether to back-port the t-wise and random-under-equal-budget baselines to the two existing SUTs~~ — **done in `0fcfd17`** | resolved |

Still open and **not closed** by genetics work: one owner decision about the Python release surface,
the environment-qualified non-zero provenance gate in
[34_RELEASE_REPRODUCIBILITY.md](34_RELEASE_REPRODUCIBILITY.md) §5. The historical
publication-specific owner-gate checklist is intentionally omitted from this private QA edition.
The former Action/image pin gaps were closed locally on 2026-08-01; both Maven and Python evidence
can change blocker IDs,
so no fixed provenance count may be quoted without its metadata root and interpreter.

---

## A. Historical Part A — pre-consolidation worktree audit and commit plan

The figures and branch state below are the preserved pre-consolidation snapshot at `158ab91`, not a
description of the current local `main`.

`main` is at `158ab91`, clean against `origin/main`. The worktree holds **99 changed paths**:
66 modified tracked files (+2 723 / −276 lines) and 33 untracked paths. `git diff --check` is clean;
no credential appears in any added file; no generated artifact (`__pycache__`, run output, database
dump, SBOM instance) is staged for inclusion — run artifacts live under `/tmp/fw_work/`.

### A.1 The commit series, created and verified

Ten commits on the local branch **`chore/phase-01-05-consolidation`**, cut from `158ab91`. Local
only: nothing pushed, tagged, or published. A branch rather than `main` directly so the owner can
review before fast-forwarding.

| Commit | Subject |
|---|---|
| `c015074` | fix(sut-paths): resolve the SUT root without depending on import order |
| `d9c55a6` | feat(bundle): machine-readable layer model, coverage gate and direct engine demonstration |
| `71c963c` | feat(bundle): capability matrix, execution authorization by candidate origin, the optional-table contract, and a loopback gRPC bind |
| `75be8ff` | fix(tests): classify every skip and replace collection errors with classified skips |
| `9a10952` | feat(bundle): release manifest, SBOM, dependency pins, CI tiers and canonical SUT manifests |
| `21a5471` | docs(publication): non-operative governance, licensing and IP-provenance drafts |
| `7efff19` | fix(sieve): decode only materialized sheets and reject unenforceable bonds |
| `4b81f12` | feat(flagship): record-pipeline SUT, mutants, baselines, executed ladder and full-chain reconciliation |
| `5bb5596` | feat(flagship): second SUT -- transactional store with an independent oracle family |
| `93fb88b` | docs: position a genetics-model-testing application in the Bundle line |

Every commit was checked out in a detached worktree, imported (`import bundle.cli`) and run against
its own targeted tests. **All ten are green**, which is what makes the series reviewable commit by
commit rather than only at its tip:

```text
C0  12 passed    C4   25 passed, 2 skipped    C8   19 passed
C1  78 passed    C5  122 passed               C9   26 passed
C3 154 passed    C6   85 passed               C10  24 passed
    3 skipped    C7   19 passed, 6 skipped
```

Only `cli.py` needed hunk-level splitting (31 hunks: 25 to the policy commit, the rest to
architecture, capabilities and release, with the two subcommand blocks split by function). Four more
files needed a single intermediate slice each: `stages.py`, `reconcile.py`, `run_flagship.py` and
`docs/14_SCENARIO_CATALOG.md`. `ci.yml` needed none — all the subcommands it invokes exist by the
commit that carries it.

### A.2 What the split revealed

Three couplings only surfaced because each commit was actually built and run. All three are now
either fixed or documented as intrinsic.

**1. A pre-existing test-order bug (fixed, commit C0).** `bundle.stages` pinned `BUNDLE_SUT_ROOT` to
the in-repository `suts/` at *import time*. Several test modules discover a sibling checkout for
themselves, but only when that variable is unset — so whether a SUT was found depended on whether
anything had imported `bundle.stages` first. Two automation-studio tests passed alone and failed in a
full run. It reproduces on clean `158ab91`, so it is not a Phase 01–05 regression; the new test
modules merely changed collection order enough to expose it. Resolution now lives in
`sut_paths.discovered_sut_root()` and is a pure function of the environment and the filesystem.

**2. The capability matrix and the execution-policy work cannot be separated (merged into C3).**
`capabilities.py` imports `policy.PROFILES`; `stages.capability_gate` imports `capabilities`; and the
capability registry cites `test_bundle_execution_safety.py` as the evidence for its runnable rows.
Any ordering of two commits leaves one of them red. They are one change and are now committed as one.
This is a finding about the code, not about the split: a genuinely separable capability registry
would not cite another phase's test as its evidence.

**3. `reconcile.py` imported every SUT at module scope (fixed).** The `TWINS` registry held
`store_flagship` eagerly, so the record-pipeline commit could not stand without the transactional
store that arrives a commit later. The registry now holds thunks and imports a SUT only when that
level is reconciled. This is the first slice of §4 Stage 1 — the same coupling §1 flags as a blocker
for the genetics application — done early because the commit split forced it. Both SUTs still
reconcile: `--level s2` re-verified end to end after the change.

### A.3 Blockers

| # | Blocker | Status |
|---|---|---|
| **B1** | Full test-suite verification | **resolved** — see §A.4 |
| **B2** | Cross-cutting files needed per-hunk splitting and per-commit verification | **resolved** — series built, all ten commits green |
| **B3** | Commit authorization | **granted for local commits**; push, tag, licence activation and publication remain withheld and none were performed |
| **B4** | Historical snapshot: 3 reproducibility gaps, **9** provenance blockers, 8 owner gates | superseded for current counts by the note above; publication remains blocked, private-source commits do not |
| **B5** | Harness coupling (§1) blocks the genetics branch | **resolved** — `bundle/study.py` extracted, both SUTs decoupled, reconciliations re-verified |

### A.4 Full-suite result

Recorded verbatim from the run's own exit code, not from a reading of the summary line.

```text
1298 passed, 15 skipped in 984.48s (0:16:24)
BUNDLE_PYTEST_EXIT_CODE=0
```

`python3 -m pytest generator_trunk Executor_trunk -q` at `93fb88b`, hermetic (no database
credentials, so DB-gated suites skip and are classified). Transcript
`sha256:f9f268ca182516bd06be5f1836351931782ae905fe8e6e8d838cd8df2217bad7`; not committed, per the
standing rule on runtime logs.

The comparison against the pre-consolidation worktree is the useful number:

| | before C0 | after |
|---|---:|---:|
| passed | 1 229 | **1 298** |
| skipped | 56 | **15** |
| failed | **2** | **0** |
| exit code | 1 | **0** |

Fixing the import-order bug did not merely turn two failures green — it unlocked roughly forty
SUT-dependent tests that had been silently skipping because `BUNDLE_SUT_ROOT` was pinned to a
directory that does not exist. They all pass. Every remaining skip carries a class
(`EXPECTED_OPTIONAL`, `MISSING_AUTHORIZED_BACKEND`) or names an absent optional component; none is
`BLOCKING_UNEXPECTED`.

The three flagship reconciliations (`--level l2`, `--level s2`, `--level l3`) were re-run against the
live database pair after the `reconcile.py` change and still report RECONCILED.
