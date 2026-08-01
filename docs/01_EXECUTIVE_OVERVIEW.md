# 01 — Executive Overview

## What the Bundle is

> **Bundle is an executable combinatorial design-space and evidence engine. AI response testing is a
> reference application.**

The Bundle (internally the *Combinatorics Framework*) is a **domain-neutral compiler and execution
pipeline for structured experiments**. The engine is `Core -> optional Sieve -> Reader -> Executor
-> Analyzer`; the control plane that plans, budgets, and journals a run is supporting engine
infrastructure. Everything else — the Face 1 UIs, the gateway, campaign launchers, the
`AI_combi_testing_platform` derivative, and every SUT adapter — is replaceable presentation or a
reference application. That boundary is declared as data and enforced by a test, not asserted here;
see [30_ENGINE_FIRST_ARCHITECTURE.md](30_ENGINE_FIRST_ARCHITECTURE.md).

It separates three concerns that most testing tools fuse together in code:

1. **Mechanics** — what variations can exist and how they compose (the combinatorial verbs).
2. **Bonds** — which combinations are forbidden/invalid/pointless (the constraint sieve).
3. **Meaning** — how an executed candidate is judged (the domain oracle / verdict).

Because these are separate stages with separate representations, the same machine applies far
beyond software testing: configuration testing, security/red-team interaction exploration,
resilience/chaos experiments, event-order testing, data-pipeline validation, performance and ML
design-space exploration, and fintech/business-rule verification.

It is **not** a flat Cartesian test-data generator. Its defining property is the preservation of
*meaning* across a long transformation:

```
domain choices → combinatorial relations → legal candidate identities →
executable artifacts → observed behavior → verdicts & metrics → selected outcomes
```

## Distinctive value

- **Freedom-shaped verbs.** You model the real shape of a degree of freedom (exactly-one, k-of-n,
  any-subset, an ordering, a sequence-with-repetition, a may-or-may-not "sudden action") and the
  count *falls out*. See [05_SPEC_V1_AUTHORING_GUIDE.md](05_SPEC_V1_AUTHORING_GUIDE.md).
- **Optional actions as a separate dimension.** `FW_Optional` bolts "what if this also happened?"
  (key rotation, cache poisoning, a retry, a fault) onto a base space without exploding the
  mandatory product: `final = pruned_mandatory × Π(nᵢ + 1)`.
- **Constraints before execution.** Invalid combinations are pruned at the relation level, before
  expensive reconstruction/execution — and the sieve is *explainable* (per-rule counts, overlaps,
  rejected/retained samples, dry-run).
- **Second-order combinatorics.** The brace (`FW_(…)`) joins two prior result tables and `FW_Group`
  re-combines + rewrites one — lifting `FW_Seq` into a combinatorial dataflow algebra, not just a
  product of value axes. Nested `FW_()`/`FW_()G` operands consume a prior brace result, so third
  order and beyond is ordinary engine usage. This is a property of the engine, independent of any
  application: `generator_trunk/engine_demo/` reaches fourth-order composition with nothing but the
  standard library on the path.
- **Relational materialization.** PostgreSQL makes large spaces durable, queryable, countable, and
  inspectable beyond process memory.
- **Quantitative honesty.** Every run is planned first (`bundle plan`): per-slot counts, exact vs
  bounded vs estimated classification, optional multiplier, resource/time/cost estimates, and a run
  class (S/B/L/X) gated by budgets.
- **A versioned, observable run contract.** Each run has a stable identity, a `run.json` manifest,
  per-stage JSON results, machine-enforced cross-stage invariants, atomic writes, resume,
  cancel, and scoped cleanup.
- **Explicit, fail-closed security profiles.** A run using `generated-default` or
  `networked-api-probe` never silently falls back to local execution. There is **no default
  profile**: a run refuses to execute until one is chosen (planning needs none). `trusted-local`
  remains available for reviewed code, but selecting it requires an explicit origin classification
  and a recorded reason, and is refused outright for generated, imported or network-facing origins.
- **Repeat-aware experimentation and feedback.** Local Python/Java execution can retain raw
  repeat samples with stable repeat/environment identity; Analyzer can aggregate noise-aware
  fronts and emit a `BundleSeed` consumed by `bundle iterate` or `--seed-from`.
- **Explainable analysis.** A *formal* Analyzer mode uses only declared objectives, requires a
  corpus count, and ties every selected (Pareto) candidate back to its source and verdict; an
  *exploratory* mode keeps auto-discovery, clearly labelled.

## Areas of application

Software/backend configuration testing; API & integration testing; **security testing & red
teaming** (the strongest narrative — interactions, order, and sudden state-changes matter);
resilience/chaos engineering; distributed workflow & event-order testing; data-pipeline/ETL
validation; database/query-plan experimentation; performance & systems optimization; ML/LLM
evaluation (discrete outer structure); fintech & business-rule verification; protocol/compatibility
testing; deployment/infrastructure design; scientific design-space exploration; education/research.

The Bundle fits problems where (1) behavior depends on interactions among several dimensions, (2)
the dimensions have meaningful combinatorial structure, (3) invalid combinations can be described,
and (4) each candidate can be judged by an executable oracle or metric.

It is **not** the right tool when there are only one or two parameters, the space is primarily
continuous, there is no reliable oracle, system state cannot be reset/isolated, or random mutation
beats structured enumeration. It complements — does not replace — unit/property-based testing,
fuzzing, covering-array tools, constraint solvers, hyperparameter optimizers, and chaos platforms.

## Intended audiences

Senior test-automation/quality engineers; reliability & distributed-systems engineers;
application-security/red-team tool builders; performance/optimization engineers; developer-tool
architects & research engineers; and a technical sponsor who can evaluate platform potential after
the engineers validate the mechanics. The first audience should be a small, technically senior
group that can challenge the semantics — not a broad nontechnical or junior-manual-testing room.

## Strengths, limitations, maturity, honest positioning

**Strengths (verified this release):** expressive Core (first/second-order verbs, optional
actions); exact cardinality planning with budgets; a versioned run contract with machine-enforced
invariants; canonical outcome model (PASS/DOMAIN_FAIL/BROKEN/TIMEOUT/INFRA_FAIL/SKIPPED/CANCELLED);
additive, idempotent results schema; resume/cancel/cleanup lifecycle; fail-closed rootless-Docker
sandbox when a secure profile is selected; formal vs exploratory Analyzer with provenance;
repeat-aware results and seed feedback; reproducible
offline builds with artifact hashes; a one-command local DB deploy profile.

**Limitations (honest):**
- Onboarding requires understanding the verb vocabulary (aliases help, but advanced specs need Core
  knowledge).
- Brace / `FW_Group` cardinality is **not** exact ahead of a run (planner marks them UNKNOWN).
- Both the **Python** and **Java** Executor chains are launcher-wired (`--lang py`/`--lang java`).
  Dated 2026-06-11 evidence covers both trusted-local and the container/secure Java variant
  (`SandboxedJavaRunner`); Java + `--analyzer` remains refused (no in-sandbox metrics harvest yet).
- Candidate transport is loose files, shards, or live gRPC. gRPC is currently Java/verdict/v2/
  trusted-local only and is plaintext/unauthenticated; it is not a remote-security boundary.
- `--repeat K` is live for Python and Java with local `metrics`/`all` scope. The launcher still
  refuses disperse/nested runtime policies, even though the standalone Java control-plane seam can
  plan and execute them. Java executor pooling is incompatible with K>1.
- Scale: **bounded (288) end-to-end and a 10K stage benchmark are measured here**; multi-million
  Core counts are source-confirmed fixtures (not re-run this session); **billion-scale end-to-end is
  not claimed**.
- A networked secure run requires re-passing the candidate-env/allowlist flags on a *non-no-op*
  resume (a clean no-op resume reuses all stages and needs nothing).
- External/LLM/live-financial scenarios are **blocked by default** and require local
  mocks/surrogates + explicit operator opt-in.

**Maturity / positioning:** An advanced, controlled, explainable, observable platform — suitable
today for expert users who control their environment. Lead with a bounded defect-discovery story
(exact count planning, constraint pruning, optional sudden actions, an independent oracle, traceable
failures), then show the architecture scales. Positioning line: **"a compiler for structured
experiments."**

See [18_VERIFICATION_AND_RELEASE_REPORT.md](18_VERIFICATION_AND_RELEASE_REPORT.md) for the gate
results and the two release-blocking bugs found and fixed during this gate.
