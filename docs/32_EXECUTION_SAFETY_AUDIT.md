# 32 — Execution-safety and contract audit (2026-07-31)

The required audit that precedes the safe-by-default work. Every finding below was verified against
current source at `main` `158ab91`; each cites the file and line so it can be re-checked rather than
believed. **This document is an audit, not a fix**: nothing here has been remediated yet, and the
findings are ordered by severity so the implementation can be sequenced.

Scope: execution-policy defaults and implicit fallbacks, the Core/Reader optional-table contract,
and the direct Reader→Executor candidate gRPC boundary.

## Execution-origin classification

The origin of candidate code determines which policy is defensible. The classification must come
from the **operator**, not from the scenario — an untrusted scenario declaring itself trusted is
precisely the case the gate exists to stop.

| Origin | Description | Defensible policy |
|---|---|---|
| `reviewed-checked-in` | candidate fragments committed in this repository and reviewed | `trusted-local` acceptable |
| `locally-authored` | written by the operator in this checkout, not yet reviewed by anyone else | `trusted-local` acceptable with an explicit decision |
| `generated` | produced by a generator, model, or transformation | secure profile required |
| `imported-untrusted` | obtained from outside this checkout | secure profile required |
| `network-facing` | reaches a network target during execution | `networked-api-probe` with an explicit allowlist |

Today **no such classification exists in the code at all**: nothing records why a given run was
entitled to the policy it used.

## Findings

### F1 — `trusted-local` is the default everywhere, and it is unsandboxed  (severity: high)

`BundleConfig.execution_policy_profile` defaults to `"trusted-local"`
(`generator_trunk/bundle/config.py:190`). The profile is `backend="local"`, `network=UNRESTRICTED`,
`fs_read=("/",)`, `fs_write=("/",)`, `env_allowlist=("*",)`, `trusted=True`
(`generator_trunk/bundle/policy.py:207-216`) — full host access, the complete environment including
secrets, and no isolation.

Every entry point inherits that default rather than deciding:

| Surface | Evidence |
|---|---|
| CLI / typed config | `bundle/config.py:190` |
| Face 1 Old backend | `intake/serve_face1.py:399`, `:600` |
| Face 1 Old browser state | `intake/face1.html:916`, `:923` |
| Face 1 New runtime model | `face1_new/runtime_model.py:97` |
| Face 1 New E2E orchestrator | `face1_new/e2e/orchestrator.py:284` |
| Evaluation gateway | `bundle/gateway/engine.py:376`, `:549` |

Consequence: an operator who omits the flag has not requested isolation and does not know it. A
generated or imported candidate then executes on the host with the launcher's own privileges.

### F2 — Face 1 New offers two execution profiles that do not exist  (severity: high)

`face1_new/run_ui.py:174` renders the execution-policy selector as:

```python
ui.select({"trusted-local": "Trusted local", "balanced": "Balanced sandbox",
           "strict": "Strict sandbox", "networked-api-probe": "Networked API probe"}, ...)
```

`balanced` and `strict` are **not** in the canonical registry — `policy.PROFILES` contains exactly
`trusted-local`, `generated-default`, `networked-api-probe` (`bundle/policy.py:248-250`), and
`resolve_policy` fails closed on anything else (`:298-309`). There is no alias mapping anywhere in
the tree.

Two distinct problems, and the second is worse than the first:

1. A user choosing "Balanced sandbox" or "Strict sandbox" gets a `PolicyError`, not a sandbox.
2. The **only secure profile that actually exists** — `generated-default` — is *absent from the
   list*. The one UI control whose purpose is to select isolation cannot select it. Face 1 Old's
   list is correct (`intake/face1.html:1396`), so the two UIs disagree.

### F3 — Resume cannot detect a policy downgrade and does not re-establish the policy stamp  (severity: high)

Three gaps compound on the resume path:

1. `_resolve_execution_policy` is called only in `_run` (`bundle/cli.py:625`). `_resume_run`
   (`:904-1257`) never resolves or validates a policy.
2. When the reader stage must re-run during resume, `stage_reader` is invoked **without**
   `policy_ref` (`bundle/cli.py:1118-1120`), and `_persist_handoff_policy` — which stamps
   `execution_policy_ref` into the manifest and writes `execution_policy.json` — is never called on
   the resume path.
3. `_run` verifies that a secure run actually recorded a non-local sandbox backend via
   `_require_executor_summary(..., required_backend=required_backend)` (`:811`). Both resume call
   sites pass **no** `required_backend` (`:1179`, `:1215`).

The Executor's own behaviour closes the loop the wrong way: `_load_execution_policy` returns
`(None, None, None)` when no policy document is found and, in its own words, "runs the legacy
unsandboxed path rather than failing" (`Executor_trunk/py_executor.py:593-603`).

So resume neither carries the original policy identity forward by construction nor checks that the
executor honoured it. This is the concrete mechanism by which a secure run could resume into an
unsandboxed one; it needs a regression test that reproduces it before the fix.

### F4 — The optional-table property templates contradict each other  (severity: medium)

`R ⊆ P` must hold, where `P` = optional sizes Core materializes
(`core.optional.includeOptionalCombiPairsToDBCSVList`) and `R` = sizes Reader consumes
(`reader.core.isOptCSVList`). In the standalone/template property files it does not:

| File | `P` (Core produces) | `R` (Reader consumes) | Holds? |
|---|---|---|---|
| `Core_trunk/fw.properties` | `4` (:166) | `1,2,3,4` (:342) | **no** — R ⊄ P |
| `Reader_trunk/fw.properties` | `1,2,3` (:89) | `4` (:215) | **no** — disjoint |
| `generator_trunk/config/core.fw.properties` | `1,2` (:159) | `1,2,3` (:329) | **no** — R ⊄ P |
| `generator_trunk/config/reader.fw.properties` | `1,2,3` (:85) | commented out (:200) | undetermined |

The **Bundle launcher path is currently correct**: `stages.stage_core` renders `1..N`
(`bundle/stages.py:324`) and `stages.stage_reader` renders the same `1..N`
(`bundle/stages.py:777`), both derived from one `n_opt` computed in `cli.py:676`. The live
`event_order` run confirms it (Core 6 × optional ×4 = 24 = Reader = Executor).

So this is a **latent** defect, not an active one: it bites a standalone component launch, and there
is no preflight that would catch the mismatch before Core and Reader do expensive work. The fix is
not to make the four text files equal — it is to derive both from one recorded contract and validate
`R ⊆ P` during side-effect-free planning.

### F5 — The direct candidate gRPC receiver binds by port, not by interface  (severity: medium)

The Reader targets `127.0.0.1:50061` by default (`bundle/config.py:164-165`), but the Java receiver
in `MainWatch` is constructed from a **port only**, so a loopback Reader target does not constrain
which interfaces the receiver listens on. The repository already documents this accurately
(`docs/10_SECURITY_AND_SANDBOXING.md:83-91`, `docs/09_READER_EXECUTOR_AND_RESULTS.md:20-23`,
`README.md`), and preflight restricts the channel to Java + verdict + Handoff v2 + `trusted-local`
(`bundle/cli.py:632-638`, `bundle/stages.py:156-205`).

The channel is plaintext and unauthenticated. What is missing is an **explicit bind host** that is
loopback by default and refuses a wildcard or non-loopback address while the channel remains
unauthenticated, plus a test asserting the actual listening socket.

### F6 — Documentation states both "safe by default" and "trusted-local is the default"  (severity: low, but it is the reason F1 persists)

`docs/01_EXECUTIVE_OVERVIEW.md` lists "Explicit, fail-closed security profiles" as a strength and,
in the same bullet, notes the default is the unsandboxed one. `docs/10_SECURITY_AND_SANDBOXING.md`
is accurate and unambiguous, and `docs/21_ARCHITECTURE_DECISIONS.md` ADR-6 states the tension
plainly. The overview's framing is the one that misleads: fail-closed behaviour is real, but only
for a profile the operator must know to ask for.

## What the fix must establish

1. **No implicit policy.** Either `generated-default` becomes the default, or a run refuses to
   execute until a policy is chosen. Planning must remain available without one.
   *Recommendation: refuse.* `generated-default` requires a working rootless container runtime and a
   local image; making it the default would make the common case fail on hosts that have neither,
   and an operator who then reaches for `trusted-local` to get moving has been trained to disable
   the safety control. Refusing has no fallback to downgrade to, and it puts the trust decision at
   the moment the operator is actually thinking about it.
2. **`trusted-local` requires a conspicuous, auditable decision**: a non-empty reason, the operator's
   origin classification, and both persisted in the run manifest alongside the resolved policy hash.
   Origins `generated`, `imported-untrusted` and `network-facing` must be refused `trusted-local`
   outright — an explicit acknowledgement should not be able to authorize what the threat model
   forbids.
3. **`generated-default` stays fail-closed** when its backend or image is unavailable. Never a host
   fallback.
4. **Resume verifies policy identity** and re-establishes the stamp, and applies the same
   `required_backend` check as a fresh run.
5. **One profile registry** feeds the CLI and both UIs, so a phantom profile cannot be offered and a
   real one cannot be omitted.
6. **One optional-table contract** renders both properties, validated at planning time and re-checked
   after Core before the Reader starts.
7. **An explicit loopback-only gRPC bind host**, with a test on the real listening socket.
8. **Checked-in launchers and tests that intentionally use trusted-local pass the acknowledgement
   explicitly** — no global environment escape hatch, because one would immediately become the
   default in every CI file that found it inconvenient.

No claim of multi-tenant readiness follows from any of this. The current qualification —
single-tenant, trusted-host — must be preserved.

## Status

Audited 2026-07-31; remediated 2026-07-31 (same session). The findings above are preserved as
written at audit time — the "what the fix must establish" list is what was implemented, not a
rewrite of history.

| Finding | Status | Where |
|---|---|---|
| F1 default is unsandboxed | **FIXED** | `config.execution_policy_profile = ""`; `policy.authorize_execution` refuses an unset profile and refuses `trusted-local` without an eligible origin + non-empty reason; recorded in `run.json` `settings.execution_authorization` |
| F2 phantom profiles in Face 1 New, secure profile missing | **FIXED** | `policy.profile_choices()` is the one registry; Face 1 New renders it; Face 1 Old offers `generated-default` first and pre-selects nothing |
| F3 resume policy gaps | **FIXED** | `_resume_run` re-resolves, `policy.verify_same_policy` refuses any change (naming a downgrade), the reader stage re-stamps the policy, and `_require_executor_summary(path, policy)` derives the backend requirement so no call site can omit it |
| F4 optional-table template drift | **FIXED** | `bundle/optional_contract.py` is the single contract; both properties are rendered from it; validated at plan time; `fw_opt<size>` materialization verified after Core; all four templates reconciled and labelled |
| F5 gRPC receiver bind host | **FIXED** | `GrpcCandidateReceiver.start(host, port)` binds explicitly and refuses wildcard/non-loopback; `-grpcBindHost` wired from `grpc_bind_host`; validated at preflight; real listening socket asserted unreachable off-loopback |
| F6 contradictory documentation | **FIXED** | README, `01_EXECUTIVE_OVERVIEW`, `10_SECURITY_AND_SANDBOXING`, `docs/README` corrected; a test asserts no document calls `trusted-local` the default |

### Tests

| Suite | Covers |
|---|---|
| `test_bundle_execution_safety.py` | F1, F2, F3, F6 — refusal without a policy, origin eligibility, resume policy identity, one registry, documentation consistency |
| `test_bundle_optional_contract.py` | F4 — `R ⊆ P`, exact multiplier, malformed lists, materialization, template audit |
| `test_bundle_grpc_bind.py` | F5 — config gate plus a real JVM bind probe and an off-loopback reachability check |
| `test_bundle_resume.py` | F3 at run level — unauthorized run refused, downgrade refused |

### What was deliberately not done

- **No TLS or peer authentication for the gRPC candidate channel.** F5 restricts the interface; it
  does not make the channel secure. A partial TLS mode would be worse than none, because it would
  read as a remote-security boundary. The requirement is recorded, not half-built.
- **No multi-tenant claim.** Everything here remains single-tenant, trusted-host.
- **No global environment escape hatch** for the trusted-local gate. Checked-in launchers pass the
  acknowledgement explicitly; a `BUNDLE_SKIP_*` variable would have become the default in every CI
  file that found the gate inconvenient.
- **The origin classification is the operator's assertion.** The gate records who decided that code
  was reviewed; it cannot verify that it was.

See [10_SECURITY_AND_SANDBOXING.md](10_SECURITY_AND_SANDBOXING.md) for the current threat model and
[27_TABLE_ARCHITECTURE_AND_READER_ASSEMBLY.md](27_TABLE_ARCHITECTURE_AND_READER_ASSEMBLY.md) for the
optional-table semantics this contract must preserve.

## Independent post-completion verification

The first completion report was independently re-checked on 2026-07-31 against source rather than
accepted from its green test count. That review found that several acceptance tests proved only the
intended call sites, not the fail-closed structure. The following corrections are part of the same
uncommitted Phase 02 worktree:

- `_require_executor_summary` no longer has a default policy argument, and `required_backend(None)`
  is an error. Resume now requires and records the summary after an Executor rerun and includes it
  in the reuse artifact set; a reused secure result is re-checked against its required backend.
- `verify_same_policy` compares the complete recorded `ExecutionAuthorization`, not only the policy
  hash. Changing origin, acknowledgement, sandboxed state, policy id, or hash is therefore a new
  decision and is refused on resume. Manifest booleans are type-checked instead of coerced.
- Resume constructs the same `OptionalTableContract` used by a fresh run, passes that one object to
  Core and Reader, uses its exact multiplier, and checks required `fw_opt<size>` tables before
  reusing Core. Changed-spec resume records the newly derived contract before stages run; unchanged
  resume refuses drift between the specification and recorded contract. `RunJournal` is created
  only after that reconciliation so its cached manifest cannot overwrite the new evidence. A
  duplicate active `reader.core.isOptCSVList` introduced in the standalone Reader template was
  removed and uniqueness is now tested.
- Face 1 Old receives `policy.profile_choices()` through `/api/ping` instead of maintaining a
  second JavaScript profile list. Face 1 New now exposes and validates the origin/reason controls
  required by `trusted-local`. Repository scenario profiles preserve those operator fields rather
  than discarding them. Their effective profile is authorized before the confirmation UI or
  programmatic launcher creates a temporary run directory.
- Direct benchmark declarations and `llm_arch_search` launchers now pass the required reviewed
  origin and acknowledgement. Generated training/cold-start guidance uses `generated-default`.
  User-facing trusted-local examples were repaired, and stale pre-F5 port-only bind descriptions
  were removed from current documentation.

The strengthened focused regression completed with **176 passed, 1 expected live-E2E skip**. The
final repository-wide run, configured with the prepared sibling SUT, completed with **1019 passed,
13 expected optional skips** in 854.07 seconds. The skips are the live Face 1 E2E opt-in, tests that
require an Analyzer build absent from this publish-clean checkout, and the deploy test's deliberate
refusal to delete a real `deploy/.env`. Both `bundle_run.py architecture` and `coverage` exited zero;
their generated JSON remains under `/tmp`, not in source control. The Phase 03 handoff records the
commands and repository state.

One modelling issue remains for later design rather than a silent Phase 02 patch: the single
`candidate-origin` enum mixes source provenance (`generated`, `reviewed-checked-in`) with runtime
capability (`network-facing`). A candidate can be both. The current gate is fail-closed for any
origin actually declared, but a future schema should represent provenance and network intent as
orthogonal fields so the audit record does not force a lossy classification.
