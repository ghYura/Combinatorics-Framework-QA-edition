# 38 — Migration note: `158ab91` → Phases 01–05

> **Read this if a command that used to work has stopped working.** Two things changed behaviour on
> purpose. Everything else in Phases 01–05 is additive. This document says exactly what broke, the
> one-line fix for each, and — because a future reader deserves the option — exactly how to revert,
> together with what reverting costs.

Each break is also marked in the code with an unmissable comment at the enforcement point, so
somebody debugging at 2 a.m. does not have to find this file first:

| Break | Enforcement point |
|---|---|
| execution policy is no longer defaulted | `generator_trunk/bundle/policy.py::authorize_execution` |
| gRPC candidate intake is loopback-only | `Executor_trunk/.../GrpcCandidateReceiver.java::requireLoopback` |

---

## 1. `--execution-policy-profile` is required for any run

**Symptom**

```text
✗ no execution policy selected. This run would execute candidate code, so the
  policy must be an explicit decision -- there is deliberately no default.
```

**What changed.** On `158ab91` the flag defaulted to `trusted-local`. A run that omitted it executed
candidate code on the host with no sandbox, no recorded candidate origin and no stated reason —
silently. It now fails instead.

**Who is affected.** Every `bundle_run.py <spec>` invocation that did not pass the flag: shell
scripts, CI jobs, cron entries, and anything copied out of documentation written before Phase 02.
`bundle_run.py plan` is **not** affected — planning needs no policy and never has.

**The fix.** Add the profile that matches what you are actually running.

```bash
# generated, imported or otherwise untrusted candidates -> container sandbox
python3 generator_trunk/bundle_run.py <spec> --db <db> \
  --execution-policy-profile generated-default

# reviewed code you control, executed on THIS host with no sandbox
python3 generator_trunk/bundle_run.py <spec> --db <db> \
  --execution-policy-profile trusted-local \
  --candidate-origin reviewed-checked-in \
  --acknowledge-trusted-local 'reviewed checked-in scenario fragments in this repository'
```

`trusted-local` additionally requires an eligible `--candidate-origin` and a non-empty
acknowledgement. That is the same decision as before, made out loud and written into the run record.

**Why it was done.** Phase 02 audit item **F1**. A default that silently selects unsandboxed
execution is indistinguishable, at the call site, from a considered choice to use it. Making the
engine refuse is what turns "we run candidates in a sandbox" from a habit into a property.

### How to revert

1. In `generator_trunk/bundle/policy.py::authorize_execution`, delete the
   `if not (profile_name or "").strip():` guard.
2. In `generator_trunk/bundle/cli.py::_resolve_execution_policy`, pass `"trusted-local"` when the
   profile is unset instead of the empty string.

**What reverting costs.** Unsandboxed host execution becomes reachable by *default* again, on every
run that forgets the flag — which is precisely the condition F1 was raised to remove. The run record
will still show `trusted-local`, but it will no longer mean anyone chose it. Treat this as a security
decision, not a convenience one, and write down why.

A gentler middle path, if you need old commands to keep working during a transition: keep the guard
but default to `generated-default` (sandboxed) rather than `trusted-local`. Old commands then run,
and they run *inside* a container instead of on the host.

---

## 2. The gRPC candidate receiver binds to loopback only

**Symptom.** A Reader on another host can no longer reach the Java Executor's candidate channel; a
non-loopback or wildcard `--grpc-bind-host` is now an error rather than a warning.

**Who is affected.** Only setups that ran the Reader and the Executor on different machines over this
channel. Same-host runs — the documented and overwhelmingly common case — are unaffected.

**The fix.** Run the Reader and Executor on the same host, or use the file-based handoff.

**Why it was done.** The channel is plaintext and unauthenticated, and it accepts candidate code for
execution. Anything that can route to the port can run arbitrary code on the host.

### How to revert

Delete the two `throw new IOException(...)` statements in `requireLoopback`, or the call to it.
**What reverting costs:** an unauthenticated remote code-execution channel. If you genuinely need a
remote transport, add TLS and peer authentication — do not widen the bind.

---

## 3. Changed but almost certainly not affecting you

**`.fw.properties` optional-table lists.** The checked-in defaults moved
(`core.optional.includeOptionalCombiPairsToDBCSVList`: `4` → `1,2,3,4`, and similar for
`reader.core.isOptCSVList`). For `bundle_run.py` this is inert: `stage_core` and `stage_reader`
render both properties from the spec's optional-table contract at run time and override the file.
It matters only if you invoke Core or the Reader **directly** with the checked-in properties, in
which case the new values materialize every optional subset size rather than only the largest.

**SUT root discovery.** `sut_paths.sut_root()` now prefers a populated in-repository `suts/`, then a
sibling checkout (`../SUT`, `../SUT-main`) that actually contains a known project, then the old
default. Previously it always returned `<repo>/suts` whether or not anything was there, and
`bundle.stages` pinned that value into the environment *at import time* — so whether a SUT was found
depended on which module had been imported first. Setting `BUNDLE_SUT_ROOT` explicitly overrides all
of it, exactly as before.

---

## 4. What did not change

Planning is byte-identical: `bundle_run.py plan generator_trunk/brace_demo` produces FW_Seq graph
`sha256:3c1a093dedadb45b41bfe5378b8eb03257fc8f661e79049371f73dfa89c2b85f` on both `158ab91` and the
merged tip. Core, Reader, Executor and Analyzer semantics are untouched; Phases 01–05 added gates,
contracts, evidence and two demonstration SUTs around them.

Full suite at the merged tip: **1305 passed, 15 skipped, exit code 0.**
