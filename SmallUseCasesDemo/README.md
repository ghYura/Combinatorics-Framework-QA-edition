<!-- SPDX-License-Identifier: BUSL-1.1 -->
# Small use-case demos

Twenty-two small, self-contained examples show how the Combinatorics Framework (the Bundle) turns a finite
structural question into an exact, reviewable test population, runs it through Core → (sieve) → Reader →
Executor, and lets an independent oracle and an offline verifier judge every case. Each example is a
deliberately small practical problem with planted defects, so that the interesting outcome — which
structure exposes which defect — can be checked by hand.

| # | Example | Practical problem it demonstrates |
|---|---|---|
| 1 | [01-d1-idempotency](01-d1-idempotency/) | Which request key makes a retried payment idempotent across transport retries, restarts and business repeats. |
| 2 | [02-d2-stream-boundaries](02-d2-stream-boundaries/) | A streaming decoder must give the same result however the input is split into chunks and wherever EOF falls. |
| 3 | [03-d3-workflow-order](03-d3-workflow-order/) | Workflow steps arriving in different orders, repeated or interrupted by sudden actions. |
| 4 | [04-d4-configuration-rules](04-d4-configuration-rules/) | Configuration legality rules and feature interactions, filtered by the Framework's constraint sieve. |
| 5 | [05-d5-nested-pipelines](05-d5-nested-pipelines/) | Higher-order composition of record transforms and queries (ordering, grouped Cartesian products). |
| 6 | [06-d6-concurrency-schedules](06-d6-concurrency-schedules/) | Lost updates and producer/consumer bugs found by enumerating bounded thread interleavings. |
| 7 | [07-d7-reduction-trees](07-d7-reduction-trees/) | Floating-point sums that depend on the reduction-tree bracketing. |
| 8 | [08-d8-ties-and-pagination](08-d8-ties-and-pagination/) | Sorting with ties and page boundaries: duplicated or skipped records between pages. |
| 9 | [09-d8-dependency-dags](09-d8-dependency-dags/) | Incremental recomputation over a dependency DAG: stale results after an upstream change. |
| 10 | [10-d9-robust-portfolios](10-d9-robust-portfolios/) | Choosing a contingency portfolio that is robust across every scenario, not just the average one. |
| 11 | [11-d10-diagnostic-sensors](11-d10-diagnostic-sensors/) | Which sensor subsets can distinguish every fault hypothesis (diagnosability). |
| 12 | [12-d11-coalition-value](12-d11-coalition-value/) | Fair cost/value sharing with exact Shapley values on a small coalition game. |
| 13 | [13-d12-cyclic-patterns](13-d12-cyclic-patterns/) | Counting cyclic designs up to rotation instead of testing every labelled copy. |
| 14 | [14-d13-tool-call-order](14-d13-tool-call-order/) | An AI agent's tool-call policy: approval, reads and sends in every order. |
| 15 | [15-d13-composed-carriers](15-d13-composed-carriers/) | Untrusted content nested inside structured carriers must keep its origin label. |
| 16 | [16-d13-agent-message-order](16-d13-agent-message-order/) | Two agents reserving one resource: message interleavings that double-book it. |
| 17 | [17-d13-session-memory](17-d13-session-memory/) | Agent memory keyed by user and session: cross-user, cross-session and post-reset leaks. |
| 18 | [18-d13-context-position](18-d13-context-position/) | Context order matters: a covering suite that still misses a position-specific defect, plus noisy judges. |
| 19 | [19-d14-language-processors](19-d14-language-processors/) | A tiny compiler checked against an interpreter and a dead-code metamorphic relation. |
| 20 | [20-d14-sql-partitioning](20-d14-sql-partitioning/) | SQL NULL (three-valued) partitioning on a real PostgreSQL fixture: set equality hides bag errors. |
| 21 | [21-d14-solver-relations](21-d14-solver-relations/) | A small auction solver: feasibility, exact optimum, tied optima and heuristic gaps. |
| 22 | [22-d15-fault-schedules](22-d15-fault-schedules/) | Crash/partition faults on three replica processes with real WAL files: lost, duplicated or diverged writes. |

## How each example is organised

- `CONTRACT.md` — the frozen question, population, oracle and expected counts (written before any run).
- `architect-derived.json`, `derive.py` — frozen predictions for every case, from an independent model.
- `sut.py` (or `worker.py`, `compiler.py`, `solver.py`, …) — the system under test with its planted variants.
- `oracle.py`, `runtime.py` — the policy-blind oracle and the candidate runtime, inlined into each candidate.
- `build_spec.py` — builds the primary `spec/demo.xlsx` (and its constraints companion) plus the equivalent
  `spec/spec.toml`; `python build_spec.py --check` proves `spec/` equals a fresh build.
- `explore.py` / `construct.py` — an independent precheck of the population before any campaign.
- `run_demo.py` — a guarded launcher: hashes, tests, precheck, both plans, disk, then one Bundle campaign and
  the verifier. `--dry-run` performs every check and prints the exact command without touching a database.
- `verify.py` — an offline verifier that imports none of the implementation and never executes candidates.
- `replay.py` — replays named candidates from a finished run through the same sandbox.
- `tests/` — focused, database-free fixture tests. `evidence/results.md` — the recorded campaign's results.

Two AI roles appear in the documents: the **AI architect** wrote each contract, predictions and review, and
the **AI implementer** built and ran the example. Both worked for the Framework's author, whose design
decisions are authoritative.

## Review gates

| Gate | Requirement |
|---|---|
| G1 — modelling | The executable spec expresses the declared structural distinctions and keeps meaningful empty, absent and boundary cases. |
| G2 — completeness | Independently enumerated identities equal the rendered and executed identities, with nothing missing or duplicated. |
| G3 — oracle | Observations agree with the frozen contract; positive controls pass; every planted defect has an explained witness. |
| G4 — execution | Counts reconcile through every stage; unexpected BROKEN, INFRA_FAIL, timeout and missing results are zero. |
| G5 — reproducibility | Commands, input/build hashes, logs, exports and deterministic replays suffice to verify the finding. |
| G6 — demonstration | A short walkthrough connects a structural change to an observable effect, with its finite limits. |
| G7 — workspace | Resource and ownership rules are respected; unrelated sources and prior artifacts are preserved. |

Intentional DOMAIN_FAIL results are evidence, not failures of an example. A green exit code alone is not.

## Running an example

1. Install and build the Framework as described in the top-level [README](../README.md) (venv, jars, the two
   PostgreSQL instances, Docker for the `generated-default` sandbox with the `python:3-slim` image).
2. `cp SmallUseCasesDemo/bundle_env.example.sh SmallUseCasesDemo/bundle_env.sh`, set your database values,
   then `source SmallUseCasesDemo/bundle_env.sh` (the copy is git-ignored).
3. In an example folder: `python build_spec.py --check`, `python -m pytest -q tests`, then
   `python run_demo.py --dry-run` and finally `python run_demo.py`. Paths are resolved from each file's own
   location; scratch output goes to `SmallUseCasesDemo/_work` unless `BUNDLE_SCRATCH_ROOT` is set.
4. Afterwards: `python verify.py --run evidence/<run-id>` and `python replay.py --run evidence/<run-id> --witnesses`.

Each campaign creates two fresh databases named `as0927_<example>_<stamp>` (one on each server) and never
drops anything. Examples 20 and 22 need Docker: 20 first creates its own isolated PostgreSQL fixture with
`python fixture.py setup`, 22 first runs `python preflight.py`. Budgets and JVM limits are in each launcher.

## Publication notes

- `evidence/results.md` documents the one campaign recorded for each example; its run directories, database
  exports and archives are not published (re-run `run_demo.py` to regenerate them).
- The documents were edited for publication: AI role names were generalized and machine-specific paths were
  removed. Where a frozen file (contract, predictions, derivation) changed through that editing, the launchers
  and verifiers pin its new SHA-256; hashes quoted in older sections refer to the same content.
- The original launchers compared the Framework working tree with a local change inventory; that change set is
  now part of the Framework's main branch, so the launchers record the Framework commit and status instead.
- Framework-development artifacts from these campaigns (bug reproducers, patch inventories) and the AIs'
  message exchange are not included.
