# RunMeFirstOnce — the run-scoped logical prologue

## Definition

`RunMeFirstOnce` is the Bundle's programmable **zero-th layer**: a run-scoped prologue executed at
the Reader→Executor handoff before the combinatorial candidate family is evaluated. It establishes
the invariant world shared by that family; it is not another combinatorial axis.

```text
shared_context = RunMeFirstOnce(environment, authored_arguments)

for each Reader-assembled candidate:
    execute(HEAD + selected combinatorial bodies + TAIL, shared_context)
    record the per-candidate verdict and metrics
```

The key modeling boundary is therefore:

- `RunMeFirstOnce`: what must be observed, prepared, or fixed for the run;
- HEAD/combinatorial bodies/TAIL: what is instantiated and evaluated for every candidate.

This is stronger than an ordinary setup callback because it may inspect the actual execution
environment, preprocess the assembled corpus, and compute the arguments supplied to all candidates.
It lets a statically constructed search space adapt to runtime facts without turning those facts
into accidental combinatorial dimensions.

## Scope and ordering

“First” means before candidate evaluation at one Executor handoff. “Once” means shared across that
handoff's candidate family—not once per repository, installation, or machine lifetime. An Executor
pool has one such scope per Executor instance. A later independent Bundle run gets a new scope.

`RunMeFirstOnce` is distinct from:

| Construct | Scope and role |
|---|---|
| `FW_Arguments` | static authored candidate arguments |
| `RunMeFirstOnce` | run-scoped setup/observation and dynamic argument production |
| HEAD | per-candidate common prefix |
| combinatorial bodies | per-candidate selected variation |
| TAIL / `FW_VAR` / `FW_CUSTOM_VAR` | per-candidate oracle and verdict |
| Analyzer | post-run aggregation and selection |

Fresh per-candidate setup is not logically `RunMeFirstOnce`. If behavior must vary by candidate, it
belongs in a modeled slot, HEAD/TAIL, or an explicitly named per-candidate adapter/preprocessor.

## Canonical Core → Reader → Java Executor contract

1. The `FW_RunMeFirstOnce` control sheet supplies source code. The canonical Java shape contains
   `class RunMeFirstOnce`, `public static String FW_ARGS`, a `main(String[] args)`, and an
   `FW_ARGS` assignment.
2. Core preserves that source in `public.runmefirstonce`; it does not combine the source into
   `fw_final` or the optional tables.
3. Reader substitutes the run-specific `FW_PATH_FILES_TO` value when present, then exports the
   source through the legacy `runFirstOnce/runmefirstonce.first` handshake and the Handoff v2
   `preprocess` reference.
4. Java `MainWatch` compiles and invokes the prologue for the handoff. A compile or invocation
   failure blocks execution.
5. `MainWatch` reads the resulting static `FW_ARGS`, splits it into the shared argument vector, and
   uses that vector instead of the ordinary `FW_Arguments` vector for candidate invocations.
6. The candidate body and its oracle still run separately for every assembled candidate.

This contract supports both ordinary initialization and corpus-level preprocessing. A prologue can,
for example, observe hardware/toolchain facts, compile a shared kernel, seed and smoke-test a
fixture, provision a reviewed local dependency, or deterministically rewrite materialized candidate
files under `FW_PATH_FILES_TO` before evaluation.

## Good uses and anti-patterns

Good uses preserve one experimental context for all candidates:

- prerequisite checks that abort an invalid run early;
- runtime observation or calibration unavailable to Core;
- expensive immutable setup reused by the candidate family;
- deterministic corpus-wide preprocessing;
- calculation of shared `FW_ARGS`;
- creation of a run-scoped fixture or endpoint used identically by every candidate.

Avoid these anti-patterns:

- hiding a candidate-dependent choice in the prologue, because that removes the choice from the
  combinatorial design and its provenance;
- scoring individual candidates there—the oracle belongs in TAIL/candidate evaluation;
- mutable shared state that makes later candidates depend on execution order;
- unrecorded environment detection that prevents reproduction;
- non-idempotent side effects whose result changes when a run is resumed or the prologue is
  retried;
- treating the filename as proof of once-only behavior without checking the selected Executor path.

Prefer an idempotent prologue, immutable shared outputs, explicit failure, and recorded hashes or
environment identifiers. If shared mutable state is unavoidable, reset it between candidates or
model the state transition explicitly.

## Language and security boundaries

The canonical once-per-handoff behavior is the Java `MainWatch` contract. Python compatibility is
different:

- the normal Java-shaped stub is recognized and ignored for Python candidates;
- an actual Python preprocessor is a reviewed `trusted-local` compatibility feature and is
  currently invoked before each candidate, so it is a **per-candidate preprocessor**, not the
  canonical run-once prologue;
- secure Python profiles reject host-side Python preprocessing before candidate provisioning, since
  it would execute outside the candidate sandbox.

Consequently, a spec author must not assume identical `RunMeFirstOnce` semantics across languages.
Executable prologue code belongs inside the same trust decision as candidate code. See
[09_READER_EXECUTOR_AND_RESULTS.md](09_READER_EXECUTOR_AND_RESULTS.md) and
[10_SECURITY_AND_SANDBOXING.md](10_SECURITY_AND_SANDBOXING.md).

## Mapping to AI prompt-response testing

For one target/configuration/effort test cell, the logical mapping is:

```text
RunMeFirstOnce:
    validate task/oracle/manifest hashes
    freeze target identity, session policy, budgets, and adapter readiness

per prompt candidate:
    create the required fresh session
    submit the assembled prompt
    capture the response

TAIL/oracle/reporting:
    parse and score the response
    aggregate the breakpoint evidence
```

Fresh-chat creation is per candidate, not run-once behavior. Response scoring happens after a
response and therefore belongs to the oracle/reporting side, not to the canonical prologue.

The AI platform's top-level `RunMeFirstOnce.py` is a manual, cost-free readiness preflight and is a
useful package-level analogue; it is not automatically the Java runtime hook. The release-gate
exchange also exports a file with that historical/convenience name, but that script both validates
the package and scores completed response files. It must be understood as an exchange bootstrap and
scoring driver, not as evidence that post-response scoring is canonical `RunMeFirstOnce` behavior.
