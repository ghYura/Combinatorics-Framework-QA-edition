<!-- SPDX-License-Identifier: BUSL-1.1 -->
# The AI implementer implementation instructions — D1

Implement [contract v1](CONTRACT.md) and follow
[the shared protocol](../README.md). The architecture is ready; begin
this example on receipt of the the AI architect IMPLEMENT message. Routine implementation,
small tests and this bounded local campaign are within the requested work.
Report genuine blockers in a file here and continue unaffected work.

**Author update, 2026-09-27:** necessary Framework code changes are authorized
for both AIs. Implement the XLSX constraint-sidecar fix specified by the AI architect's
reply to `an AI handoff note`, then run the XLSX campaign.
This supersedes the original no-Framework-edits restriction; see
AUTHOR_DECISIONS.md. The domain contract and run
budgets are unchanged. Preserve the existing changes as well as the new fix,
and update provenance guards to recognize the authorized working-tree state.

## Deliverable layout

```text
01-d1-idempotency/
  ARCHITECTURE.md, CONTRACT.md, IMPLEMENTATION.md, REVIEW.md   # The AI architect-owned
  README.md                         # add reproduction and walkthrough links
  sut.py                            # concrete service strategies
  oracle.py                         # normative contract, unaware of selector
  runtime.py                        # one isolated case and observation emission
  build_spec.py                     # compositional spec/workbook builder
  run_demo.py                       # guarded Bundle launcher
  verify.py                         # independent artifact verifier
  tests/                            # meaningful service/oracle checks
  spec/
    spec.toml
    demo.xlsx
    <actual constraint sidecar and mapping>
  evidence/<run-id>/
    manifest.json, commands.json, plan-*.json
    stage-counts.json, observations.jsonl, verification.json
    witnesses.json, results.md, logs/
  architect-to-implementer-*.md, implementer-to-architect-*.md
```

Equivalent compact file organization is fine if responsibilities remain clear.
No new package is needed for the service or verifier: standard-library Python
is sufficient. Use the existing Framework environment for workbook generation.
Apply the repository's BUSL-1.1 header convention to new source and docs.

## 1. Implement and validate the fixture

Implement the five policies exactly as specified. Keep the durable ledger
separate from the cache, so a volatile-cache reset cannot accidentally erase
the evidence of a duplicate effect. Restart by replacing the process object
while retaining its declared backing state. Reset everything between cases.

Test the normative behaviours directly: equal-payload replay, conflicting
retry, two operations in one order, equal-payload operations in different
orders, restart persistence and isolation between consecutive cases. Check
that the runtime oracle rejects the four defective policies on the declared
witnesses. Tests must inspect real ledger/receipt behaviour, not reproduce an
implementation-name-to-verdict lookup table.

The runtime oracle must judge observations without knowing the selected policy.
The separate verifier may use the policy to predict the faulty implementation's
signature, but it must derive that prediction independently from the contract.

## 2. Build the declarative input

Follow the sheet order and two bonds in CONTRACT.md. `FW_Combi(1)` catalogue
values must be syntactically complete Python statements with newlines. Keep
case identity assignments visible to AST inspection. Define the HEAD once and
let Core/Reader choose and assemble the factors; do not create a catalogue of
120 complete programs in Python.

Produce a readable workbook using the supported generator interface and retain
its TOML authoring source. Include all needed control sheets, custom verdict
messages and the constraint sidecar. Resolve the current XLSX sidecar discovery
convention explicitly; record its exact path/hash and show that it is loaded.
Any XLSX-specific limitation needs a minimal reproducer and a message to the AI architect.

Make each generated program self-contained and compatible with
`--execution-policy-profile generated-default`: inline the audited local
definitions into HEAD if necessary, and use no absolute host imports or new
network dependency. This is approximately 120 small programs, not a large
fixture. Preserve separately reviewable source modules and source hashes.

Emit a full structured observation record per program through the supported
Executor capture mechanism and export it to JSONL. If a compact stdout marker
is used, make it unambiguous and verify it survives Executor capture. Use the
existing metrics/verdict conventions as well. With HEAD followed by IMPL,
the legacy nonzero carrier can use the IMPL position (2), with a custom message
that directs the reader to observations; confirm the actual mapping. PASS is
0. Start TAIL with an ordinary assignment/call (for example `_verdict = ...`),
then assign `FW_VAR` and `FW_CUSTOM_VAR`; a leading `FW_VAR` has historically
been parsed as a data-cell directive. Do not use Python crashes for domain
verdicts. Do not describe the carrier position as the failure's cause.

## 3. Plan before connecting a run

From the Framework repository:

```bash
source bundle_env.sh
python generator_trunk/bundle_run.py plan 01-d1-idempotency/spec/spec.toml --out 01-d1-idempotency/evidence/plan-toml
python generator_trunk/bundle_run.py plan 01-d1-idempotency/spec/demo.xlsx --out 01-d1-idempotency/evidence/plan-xlsx
```

Save both plans and compare sheet support, flags, effective program and loaded
constraints. Expect raw support 600 and post-sieve target 120. If a planner
legitimately returns a bound, retain that label and provide the independent
enumeration; never edit a plan to make it EXACT. No mandatory sheet may drop.
Use constraint explanation or an equivalent explicit truth-table check to
verify the 600 → 500 → 120 restriction and retain accepted/rejected controls.

## 4. Run one bounded campaign through the actual Framework

Provide a wrapper interface `python run_demo.py --input xlsx` that builds or
checks the inputs, makes fresh run/DB names, runs the Bundle and saves evidence.
Use `as0927_d1_<unique timestamp>` on **both** ports, checking absence before
creation. A collision must fail without dropping anything. Record every
database this run creates; do not use `cl*`, `cx*` or unprefixed DB names.

The wrapper's Bundle invocation uses the workbook and its real sidecar, `--sieve`,
`--lang py`, K=1, one executor worker, a unique run ID, and these limits:

```text
--budget-mandatory-rows 1000
--budget-final-candidates 1000
--budget-disk-bytes 200000000
--budget-wall-time-seconds 600
--execution-policy-profile generated-default
```

The limits provide modest headroom for a conservative plan; the accepted case
count remains exactly 120. Confirm current disk space and use at most 2 GB heap
per spawned JVM for this demonstration (the workspace ceiling is 4 GB). Record
the effective JVM settings. Do not override budget gates or tolerate unexpected
BROKEN/INFRA_FAIL/TIMEOUT outcomes. No Analyzer is needed for this comparison.

The main campaign uses XLSX. TOML needs a successful, equivalent plan; repeat
the full campaign through TOML only if an unresolved format discrepancy makes
that second run useful. Record additional witness replays separately from the
120 K=1 campaign attempts. Avoid modifying the author's PostgreSQL services
because a restricted process cannot reach localhost.

## 5. Verify and explain the outcome

Implement `python verify.py --run <evidence-directory>` as an offline verifier.
It must fail on missing/duplicate case IDs, mismatched rendered assignments,
incorrect prefix effects, receipt identity/payload mistakes, wrong verdicts,
missing stages or unexpected infrastructure results. It must not import the
SUT, runtime or runtime oracle, connect to a DB or execute candidate programs.
The exported evidence must be sufficient for those checks.

Include every observed field needed by CONTRACT.md, the actual case-set equality
result, and a per-policy/per-population verdict table. The expected 77 PASS /
43 DOMAIN_FAIL is a check, not the definition of correctness. Explain any
disagreement before claiming success. Record at least four defective-policy
witnesses and a passing operation-key control with replay commands.

Write a brief `results.md` explaining the real problem, the structural model,
Framework's part in constructing/executing the space, the four walkthrough
contrasts, measured counts, named sensors and finite-domain limitations.
Do not describe expected failures as defects found in the Framework or stdlib.

## 6. Deliver for independent review

Send `implementer-to-architect-<EEST timestamp>.md` inside this folder. Include the frozen
contract hash, exact commands, file list, run/DB IDs, all gate evidence links,
the measured versus predicted table and any remaining limitation. Keep complete
compact evidence and leave owned run state available until the AI architect's review.
Do not start D2 or mark this example accepted yourself.

Read-only methodological references, if useful:

- `<external>/experiments/r3/dedup/specs/spec.toml`
- `<external>/experiments/r3/dedup/notes.md`

They describe a different 44-case fixture. Reuse ideas and supported integration
patterns, with attribution; do not copy its outputs into this new run.
