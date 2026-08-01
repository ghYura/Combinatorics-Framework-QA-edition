# 10 — Security and Sandboxing

> **Linux-specific.** Sandbox backends rely on Linux user namespaces (bubblewrap) and rootless
> Docker.

## Threat model

Generated/reconstructed candidate code is **untrusted**. The control plane (trusted) must never
execute it with its own privileges, must not expose host secrets/filesystem/classpath, and must
bound CPU/memory/processes/time/output and network. A secure run must **fail closed** if the sandbox
backend is unavailable — never silently fall back to local execution (high-level plan §4.11 / ADR-6;
cold-start Prohibition #10).

There is **no default profile**. A run that would execute candidate code refuses to start until
one is chosen; `bundle plan` is side-effect-free and needs none. `trusted-local` remains
available, but it is unsandboxed, inherits host access, and is suitable only when the candidate
source and all dependency JARs are trusted — so selecting it additionally requires an explicit
origin classification (`--candidate-origin`) and a recorded reason
(`--acknowledge-trusted-local`). Origins `generated`, `imported-untrusted` and `network-facing`
are refused it outright: the acknowledgement records a decision, it does not grant a permission.

## Trust boundary

```
control plane (trusted) ─▶ Executor ─┬─ secure profile ─▶ sandbox (untrusted code)
                                    └─ trusted-local ──▶ local/in-process execution (trusted code)
```

The Python control plane does not import candidate code. The Executor owns execution; under
trusted-local, Java candidates compile and run inside MainWatch and Python candidates run locally.

A candidate preprocessor is executable code and belongs inside the same trust decision. For Python,
secure profiles refuse an actual host-side Python `RunMeFirstOnce` preprocessor before candidate
execution. The Java `RunMeFirstOnce` stub emitted by the normal Reader is recognized as Java and
ignored rather than invoked with Python. Only `trusted-local` retains the legacy host Python
preprocessor behavior for reviewed code. Thus a secure candidate cannot be modified or preceded by
untrusted host code outside the recorded sandbox policy.

## Trusted-local vs secure modes (execution policy profiles)

`bundle/policy.py` defines three versioned profiles; the policy id/hash is recorded in the manifest
and every `results_v2` row:

| Profile | Backend | Network | Limits | Use |
|---|---|---|---|---|
| `trusted-local` | direct local execution (no SandboxBackend) | unrestricted | 600s timeout and 16MiB output ceilings; no CPU/memory/pid/fs isolation | reviewed code only; **never a default** — requires an origin classification and a recorded reason |
| `generated-default` | `container` | **disabled** | timeout 30s, cpu 15s, mem 512MB, pids 64, fs read/write `{scratch}` only, env allowlist (PATH/LANG/LC_ALL/TZ/HOME/TMPDIR), stdout/stderr 1MB | recommended secure profile for generated/untrusted candidates; not CLI default |
| `networked-api-probe` | `container` | **allowlist** (dedicated internal net) | as above + narrow allowlisted egress to a named target container | API/SUT probing, local-only |

Select `generated-default` or `networked-api-probe` explicitly for untrusted candidates. Those
secure profiles name `backend=container` and fail closed when it is unavailable.

## Sandbox backends (`Executor_trunk/sandbox.py`)

- **ContainerBackend** (rootless Docker): `--read-only` root, `--cap-drop ALL`,
  `--security-opt no-new-privileges`, `--pids-limit`, `--memory`/`--memory-swap`, `--ulimit cpu`,
  tmpfs `/sandbox` + `/tmp`, env allowlist only, **no published ports**, network `none` **or** a
  **dedicated per-sandbox `--internal` network**. Default image `python:3-slim`
  (`BUNDLE_SANDBOX_IMAGE` override). Verified live: the candidate ran with exactly these flags.
- **BubblewrapBackend** (daemonless userns): ro-binds only the system runtime (not `/home`,
  `/etc/shadow`, …), tmpfs scratch, `--unshare-net` when network disabled. A non-loopback allowlist
  can only be narrowed to loopback by bubblewrap alone (documented limitation; use `container` for
  real allowlists).
- **Trusted local**: a trusted `backend=local` policy returns no SandboxBackend and uses the direct
  legacy/local path. `LocalBackend` exists for a non-trusted custom local policy's resource knobs,
  but it is not a filesystem/network security boundary.

## Docker / internal networking (local-only)

For `networked-api-probe`, the backend creates a **dedicated `--internal` Docker network** per
sandbox and attaches **only** the allowlisted target container (`attach_target` refuses anything not
in the policy allowlist — it can never widen it). An `--internal` network has **no gateway**, so the
candidate has **no route off the host**. Verified live on the flagship:

```
sandbox net: internal=true   members=2 (candidate + secure-app)
secure-app: ports=map[]       # SUT publishes NO host ports — reachable only inside the internal net
```

This is the repository's canonical local-only, inter-container policy: bind any published port to
`127.0.0.1`, use internal networks, and never expose containers to the LAN/Internet. It preserves the
applicable restrictions from a historical Docker notice that is not shipped as a separate source
file. Build example SUT dependencies into a dedicated image (or install from a locked manifest).
Do not mount the host `/usr` into a candidate/SUT container: even read-only host runtime exposure is
broader than the documented isolation boundary and is host-version dependent.

## Live gRPC candidate transport is not a secure channel

The current Reader→Java-Executor gRPC path is **plaintext and unauthenticated**. It is
intentionally restricted by preflight to `trusted-local`, verdict mode, Handoff v2, and Java;
Reader targets `127.0.0.1:50061` by default.

**Loopback-only bind (audit F5, fixed).** The receiver previously used a port-only Netty bind
(`NettyServerBuilder.forPort`), which listens on every interface — a loopback Reader *target* never
constrained what the receiver *listened on*. `GrpcCandidateReceiver.start(host, port)` now binds an
explicit address and **refuses** a wildcard (`0.0.0.0`, `::`) or any non-loopback address, because
a channel with neither TLS nor peer identity has no correct off-host configuration today. The
launcher passes `-grpcBindHost` from `grpc_bind_host` (default `127.0.0.1`), validated at preflight
by `BundleConfig.validate_grpc_bind_host`, and the Java side fails closed on its own so a
standalone `MainWatch` invocation cannot bypass it. `generator_trunk/test_bundle_grpc_bind.py`
asserts the **real listening socket** is unreachable from this host's routable address.

This is an interface restriction, not a security upgrade: the channel is still unencrypted and
unauthenticated. Firewall it from other hosts/tenants and never treat it as an
encrypted/authenticated remote orchestration boundary. Secure profiles use file-based candidate
transport instead. Authenticated TLS with peer identity remains a future requirement, not a
partially-implemented mode.

## Fail-closed behavior

If a secure profile names `backend=container` but the sandbox module/daemon is unavailable, the
Executor prints `FATAL … refusing to run generated candidates unsandboxed`, runs **0** candidates,
and exits non-zero (verified in source `py_executor.py`). The launcher additionally requires the
executor-summary to record a non-`local` `sandbox_backend` for a secure run
(`_require_executor_summary`), so a secure run can never be reported green after a local fallback.

## Secret flow & redaction

- DB passwords come from env/config, never defaulted in source; preflight fails closed if missing.
- Manifests/reports/resolved-config redact `password`/`token`/`secret`/`api_key`/`credential`
  (verified `***REDACTED***`); the Handoff v2 `result_target` carries no password.
- Plaintext DB credentials exist only in run-private `core_cwd`/`reader_cwd/fw.properties` (JDBC
  necessity); `cleanup` flags them for deletion.
- Candidate-env passthrough (`--sandbox-candidate-env`) refuses credential-shaped names — a secure
  sandbox never receives secrets.

## Java/Python parity

The Java secure path (`SandboxedJavaRunner`, MainWatch container mode) mounts source/harness ro
under `/src`, dependency JARs ro under `/deps`, uses an isolated candidate classpath (no ambient
host classpath), and enforces the same network/fs/process/memory/cpu/time limits; the shared secure
profile permits `java`/`javac` (`SandboxedJavaRunner` refuses a Java candidate otherwise).

## Known residual risks

- Docker daemon trust (rootless reduces but does not eliminate).
- Dependency JARs are **trusted configuration inputs** (mounting one makes its code callable inside
  the sandbox).
- An operator who omits the profile now gets a refusal rather than unsandboxed execution, and an
  explicit `trusted-local` selection is recorded in the run manifest (profile, origin, reason,
  policy hash) and re-verified on resume. The residual risk is that a reviewed-origin
  classification is the operator's own assertion: the gate records who decided, not whether the
  code was genuinely reviewed.
- The gRPC candidate channel has neither TLS nor authentication and is trusted-host-only.
  It is now bound loopback-only and refuses any other interface, which limits exposure but
  does not make the channel secure.
- Bubblewrap allowlist narrows only to loopback (use `container` for named-target allowlists).
- An incorrect oracle/constraint can mislabel results (validate with known-pass/known-fail controls).
- The Java Executor is launcher-wired and **verified end-to-end in both** trusted-local (in-process
  Janino/ECJ) **and** the container/secure variant (`SandboxedJavaRunner`, `generated-default`,
  per-candidate `eclipse-temurin` container). Verified 2026-06-11: `janino_max` under
  `generated-default` gave the same 29 PASS / 19 DOMAIN_FAIL / 0 BROKEN as trusted-local, and the
  adversarial seam audit passed in real containers — corrupt/unknown policy → REFUSE (fail-closed),
  write-outside-scratch → BROKEN (read-only root), `--network none` blocks egress, cpu-limit →
  TIMEOUT, deps mounted ro at `/deps`. Residual: validate further against a multi-tenant threat model
  (microVM/Firecracker, SEV-SNP) before running untrusted third-party Java in a shared SaaS.
- A non-no-op resume of a networked run requires re-passing the candidate-env/allowlist flags.
