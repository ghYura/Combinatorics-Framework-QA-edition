# Executor Concurrency and Precompiled Container Dispatch

Date: 2026-07-02

> **Historical implementation snapshot.** A live Reader → Java Executor gRPC ingestion path was
> added after this document was written. It is not a gRPC implementation of the precompiled-Docker
> dispatcher proposed below: it currently carries Handoff-v2 Java candidates/verdicts, stores no
> on-disk corpus, is plaintext/unauthenticated, and the Bundle launcher restricts it to
> `trusted-local`. See the [current code audit](CURRENT_CODE_AUDIT_2026-07-21.md).

Scope: Java Executor implementation in `Executor_trunk`, primarily `com.company.MainWatch`, with a new precompiled Docker runner and smoke coverage.

## Summary

Today the Java Executor was extended in two directions:

1. Incoming Java candidate files are no longer processed serially by the watch thread. Candidate discovery now feeds a bounded worker pool, allowing multiple incoming files to compile and execute at the same time.
2. A new execution mode was added for host-side precompilation followed by actual execution in a Docker-backed execution node. This is separate from the existing secure container mode, which compiles and runs inside the container.

The implementation keeps the existing trusted-local and secure-container semantics intact. The new precompiled path is explicit and fail-closed: it is selected by policy backend `precompiled-container` or by `-dispatchMode precompiled-container` / `-Dfw.exec.dispatch=precompiled-container`.

No gRPC client was added today because the repository does not yet contain a dispatcher proto, generated stubs, service contract, or orchestration node API. Adding a pretend gRPC protocol would create an integration surface that cannot interoperate with anything in the current tree. The implementation instead provides the concrete Docker dispatch behavior now and leaves a clean place to add a real gRPC dispatcher once the protocol exists.

## Files Touched

New files:

- `Executor_trunk/src/main/java/com/company/PrecompiledDockerJavaRunner.java`
- `Executor_trunk/src/main/java/com/company/PrecompiledDockerJavaRunnerTest.java`
- `Executor_trunk/src/main/java/com/company/MainWatchConcurrencySmokeTest.java`

Updated files:

- `Executor_trunk/src/main/java/com/company/MainWatch.java`
- `Executor_trunk/src/main/java/com/company/SandboxedJavaRunner.java`
- `Executor_trunk/src/main/java/com/company/SandboxedJavaRunnerTest.java`

## Existing Execution Modes Before This Change

Before today's work, MainWatch had these relevant execution paths:

- Trusted local in-process execution.
  - Candidates compile in the Executor JVM using the adaptive compiler path, Janino, ECJ, or JDK `javac` depending on configuration.
  - Candidate `main()` runs inside the Executor JVM.
  - This mode remains the explicit trusted-local opt-in.

- Secure container execution via `SandboxedJavaRunner`.
  - The Executor sends source into a rootless Docker container.
  - The container compiles and runs the candidate using an in-container harness.
  - The Executor receives stdout, stderr, and the canonical verdict marker.
  - This remains the secure untrusted Java path for backend `container`.

The new mode is deliberately not a replacement for either of these. It is a third mode.

## New Candidate Worker Pool

### Goal

Allow MainWatch to process several incoming Java candidate files at the same time, including files arriving from multiple watched directories.

### Implementation

MainWatch now owns a bounded `ExecutorService` for candidate work:

- `candidateWorkerCount`
- `candidateExecutor`
- `candidateWorkerThreadIds`
- `scheduledCandidateFiles`

Watch threads and cold-start scans submit candidate paths to this pool instead of compiling/executing directly in the watch callback.

The worker count is configured by either:

```bash
-Dfw.exec.threads=N
```

or MainWatch CLI options:

```bash
-executorThreads N
```

Aliases accepted by the parser:

```bash
-threads N
--executorThreads N
--threads N
```

Because MainWatch's argument parser strips one leading dash from option names, both single-dash and double-dash forms can appear in `mainArgs` depending on how the launcher invokes it.

Default worker count:

```text
max(1, min(Runtime.availableProcessors(), 8))
```

This avoids unbounded compilation fan-out on large hosts while still allowing real parallelism.

### Duplicate Suppression

`scheduledCandidateFiles` tracks absolute normalized candidate paths currently in-flight. If multiple create/modify events arrive for the same file while it is already queued or running, the duplicate event is ignored.

This matters because file-watch implementations often emit multiple events for one write.

### File Stability Wait

Before a worker reads a candidate file, it waits briefly for the file to become stable:

- sample file size and last-modified time
- require two consecutive stable observations
- sleep 100 ms between observations
- retry up to 50 times

This reduces the risk of compiling a partially-written candidate after an `ENTRY_CREATE` or early `ENTRY_MODIFY` event.

### Processing Dispatch

All worker submissions flow through a single mode-aware dispatch helper:

```text
submitCandidateFile(Path candidatePath, CandidateMode mode)
processCandidateFileByMode(String path, CandidateMode mode)
```

The dispatch decision is:

1. If `precompiledDispatch` is enabled, run `processCandidateFilePrecompiledDispatched`.
2. Else if `secureSandbox` is enabled, run `processCandidateFileSandboxed`.
3. Else if pass-only mode is active, run `processCandidateFilePASSonly`.
4. Else if fail-only mode is active, run `processCandidateFileFAILonly`.
5. Else if `repeatK > 1`, run `processCandidateFileRepeated`.
6. Else run the normal `processCandidateFile` path.

This preserves existing result accounting and outcome mapping because the old candidate-processing methods remain the core implementation.

### Metrics Serialization Caveat

The in-process metrics path uses a JVM system property, `fw.metrics.out`, to pass a per-candidate metrics sink to candidate code. JVM system properties are process-global, not thread-local.

To avoid cross-candidate metrics sink races, MainWatch serializes in-process candidate invocation only when all of these are true:

- `-metricsFile` is enabled
- secure sandbox is not enabled
- precompiled dispatch is not enabled

In that case, workers still handle discovery and scheduling, but actual in-process candidate invocation is guarded by `inProcessMetricsLock`.

Container-backed modes harvest metrics from captured stdout and do not need this lock.

## Watch Directory Behavior

### Previous Behavior

The prior live watch path only acted on `ENTRY_MODIFY`, and it depended on a duplicate-offer pattern through `ConcurrentSetBlockingQueue`. In practice, candidate execution could require a second modify event for the same file.

### New Behavior

MainWatch now watches candidate directories for both:

- `ENTRY_CREATE`
- `ENTRY_MODIFY`

The watch callback resolves the event context against the watched path and submits it directly to the worker pool.

The changed methods are:

- `dirWatchExampleCopy`
- `dirWatchExampleCopyFAILonly`
- `dirWatchExampleCopyPASSonly`

Each method still runs the cold-start scan before entering the live watch loop.

## Cold-Start Scan Behavior

Cold-start scanning now submits every regular Java file to the worker pool instead of processing candidates in a serial loop.

For loose-file sources:

```text
coldStartScanSrcDir(path, failOnly)
```

now enqueues every existing candidate into the bounded worker pool.

For sharded sources:

```text
coldStartScanShards(shardDir, failOnly)
```

still streams shard records one at a time through a scratch file. That path intentionally remains sequential because the shard streaming contract avoids expanding the whole corpus to loose files.

## Multiple Watch Directories

### Legacy CLI Mode

MainWatch already accepted repeated `-srcDirList` values into `srcDirList`. With the new worker pool, candidates from all watched directories can now run concurrently, bounded by `candidateWorkerCount`.

Once the DB URL handshake arrives, MainWatch starts one watch thread per source directory. Those watch threads all submit into the same candidate worker pool.

### Handoff v2 Manifest Mode

Before this change, Java MainWatch required exactly one manifest source for both `loose-files` and `sharded` transports.

Now:

- `candidate_transport = "sharded"` still requires exactly one source directory.
- `candidate_transport = "loose-files"` may declare multiple source directories.

For loose-file manifests, MainWatch now:

1. Clears any legacy `-srcDirList` entries because the manifest is the source of truth.
2. Validates every declared source path exists and is a directory.
3. Adds every declared source to `srcDirList`.
4. Counts `*.java` files in each source directory.
5. Verifies each source checksum independently when `sha256` is present.
6. Reconciles the sum of all Java files across sources against `candidate_count`.

This gives a manifest-level multi-watch contract without weakening the existing checksum and candidate-count checks.

## New Precompiled Container Dispatch Mode

### Purpose

The new mode supports this execution shape:

```text
incoming .java file
  -> MainWatch reads and normalizes source
  -> MainWatch renames the top-level type as usual
  -> host-side javac precompiles the source
  -> compiled classes are mounted read-only into a Docker container
  -> container runs the already-compiled candidate
  -> MainWatch records canonical outcome and verdict
```

This addresses the requested mode where the Executor may precompile incoming files but send actual execution to a configured Docker/orchestration execution node.

### Selection

Policy-based selection:

```json
{
  "policy": {
    "backend": "precompiled-container",
    "allowed_interpreters": ["java", "javac"],
    "timeout_seconds": 30,
    "cpu_seconds": 10,
    "memory_bytes": 268435456,
    "max_processes": 64
  }
}
```

CLI/system-property selection:

```bash
-dispatchMode precompiled-container
```

or:

```bash
-Dfw.exec.dispatch=precompiled-container
```

Accepted aliases in the implementation:

- `precompiled-container`
- `container-precompiled`
- `precompiled-docker`

The shared execution-mode enum now includes:

```text
PRECOMPILED_CONTAINER
```

### Fail-Closed Rules

The precompiled dispatch path refuses to start unless Java execution is explicitly allowed.

With an execution policy, the policy must permit both:

- `java`
- `javac`

Without an execution policy, this mode requires:

```bash
-Dfw.exec.trusted=true
```

Reason: host-side precompilation parses and compiles untrusted source in the Executor JVM process. That is a different trust profile from the existing fully containerized `container` backend where compilation happens inside the sandbox.

### PrecompiledDockerJavaRunner

`PrecompiledDockerJavaRunner` is the new implementation class.

Responsibilities:

1. Discover Docker using the same rootless Docker discovery helper used by `SandboxedJavaRunner`.
2. Compile the renamed candidate source on the host with system `javac`.
3. Use `-proc:none` so annotation processors from candidate code are not executed during precompilation.
4. Build a restricted Docker command that mounts:
   - compiled class output at `/classes:ro`
   - a tiny execution harness at `/runner/FwPrecompiledRunner.java:ro`
   - configured dependency JARs under `/deps/*.jar:ro`
5. Run the harness using JDK single-file source mode inside the container.
6. Parse the verdict marker from container stdout.
7. Map execution results to the existing canonical outcome model.
8. Force-remove the container and delete temp build output in `finally`.

### Host Compile Command Shape

The host compile path uses JDK `javac` through `ToolProvider.getSystemJavaCompiler()`.

Core options:

```text
-proc:none
-encoding UTF-8
--release <current Java feature version, minimum 8>
-classpath <configured dependency jars, if any>
-d <temp classes dir>
<renamed candidate source>
```

A compile failure maps to `BROKEN` because the candidate did not produce a runnable verdict.

A missing host JDK compiler maps to `INFRA_FAIL` because the execution environment cannot perform the requested dispatch mode.

### Container Run Shape

The Docker container is configured similarly to the secure sandbox path:

- `--network none`
- `--read-only`
- `--cap-drop ALL`
- `--security-opt no-new-privileges`
- `--pids-limit <policy max_processes or 64>`
- `--memory <policy memory_bytes>` when configured
- `--memory-swap` equal to memory when configured
- `--ulimit cpu=<cpu_seconds>:<cpu_seconds>` when configured
- writable `tmpfs` at `/sandbox`
- writable `tmpfs` at `/tmp`
- no host project classpath mounted by default

The candidate runs from compiled classes mounted at `/classes`, not from source.

Dependency JARs registered through `dirJars` are mounted read-only under `/deps` and passed to the harness through `-Dfw.cp=...`.

### Harness Behavior

The in-container harness:

1. Builds a classloader over `/classes` plus optional `/deps` entries.
2. Loads the candidate binary class name.
3. Invokes `public static void main(String[] args)`.
4. Reflectively reads `FW_VAR` and `FW_CUSTOM_VAR`.
5. Prints:

```text
__FWV__ <FW_VAR> <FW_CUSTOM_VAR>
```

MainWatch parses that marker exactly like the existing sandbox path parses its marker.

### Outcome Mapping

The precompiled path maps results to the existing MainWatch outcome model:

- verdict 0 -> `PASS`
- verdict non-zero -> `DOMAIN_FAIL`
- host compile failure -> `BROKEN`
- no verdict marker -> `BROKEN`
- candidate `main()` throws -> no marker -> `BROKEN`
- wall timeout or CPU timeout -> `TIMEOUT`
- Docker cannot start or host compiler unavailable -> `INFRA_FAIL`

`processCandidateFilePrecompiledDispatched` then records:

- legacy `SqlRecord` queue entries for domain verdicts
- `results_v2` canonical result rows when `runId` is available
- outcome counters
- processed counters
- metrics line harvested from stdout when `-metricsFile` is enabled

## Interaction With Existing Modes

### Trusted Local

No intentional behavior change.

Trusted local still uses:

- `processCandidateFile`
- `processCandidateFileFAILonly`
- `processCandidateFilePASSonly`
- `processCandidateFileRepeated`

The only difference is that those methods can now be invoked by candidate worker threads instead of directly by the watch thread.

### Secure Container

No intentional behavior change.

Backend `container` still uses `SandboxedJavaRunner`, where both compilation and execution happen inside the Docker sandbox.

### Precompiled Container

New behavior.

Backend `precompiled-container` uses host `javac` for precompilation and Docker for actual execution.

### Repeat K > 1

Repeat fan-out remains trusted-local only.

If `repeatK > 1` and either secure container or precompiled-container dispatch is active, MainWatch fails closed.

Reason: container-backed K > 1 needs explicit K-subprocess dispatch and raw sample accounting. Silently running one sample would violate the repeat contract.

## Configuration Reference

### Worker Count

System property:

```bash
-Dfw.exec.threads=4
```

MainWatch CLI:

```bash
-executorThreads 4
```

### Existing Secure Container Mode

Policy backend:

```json
"backend": "container"
```

Semantics:

```text
compile in container, run in container
```

### New Precompiled Container Mode

Policy backend:

```json
"backend": "precompiled-container"
```

or CLI:

```bash
-dispatchMode precompiled-container
```

or JVM property:

```bash
-Dfw.exec.dispatch=precompiled-container
```

Semantics:

```text
compile in Executor JVM with host javac, run compiled classes in container
```

### Trusted Legacy Override

Only for explicitly trusted/no-policy operation:

```bash
-Dfw.exec.trusted=true
```

Required if precompiled dispatch is requested without an execution policy.

## Example Invocation

Example with explicit worker count and precompiled dispatch:

```bash
java   -Dfw.exec.threads=4   -cp target/Executor-1.0-jar-with-dependencies.jar   com.company.MainWatch   -manifest /path/to/manifest.json   -dirJars /path/to/jars   -dirSqlTemplate /path/to/sqlTemplate   -dirResultsDbURL /path/to/resultsDbURL   -out2 /path/to/out2   -dispatchMode precompiled-container   -exitWhenComplete true
```

Prefer policy-driven selection for production runs:

```json
{
  "id": "precompiled-container-java",
  "sha256": "...",
  "policy": {
    "backend": "precompiled-container",
    "allowed_interpreters": ["java", "javac"],
    "timeout_seconds": 30,
    "cpu_seconds": 10,
    "memory_bytes": 536870912,
    "max_processes": 64
  }
}
```

## Verification Performed

The following commands were run successfully from `Executor_trunk`:

```bash
mvn -q -DskipTests compile
mvn -q -DskipTests package
java -cp target/Executor-1.0-jar-with-dependencies.jar com.company.SandboxedJavaRunnerTest
java -cp target/Executor-1.0-jar-with-dependencies.jar com.company.PrecompiledDockerJavaRunnerTest
java -cp target/Executor-1.0-jar-with-dependencies.jar com.company.MainWatchConcurrencySmokeTest
java -cp target/Executor-1.0-jar-with-dependencies.jar com.company.MainWatchAdaptiveCompilerSmokeTest
java -cp target/Executor-1.0-jar-with-dependencies.jar com.company.MainWatchOutcomeClassificationTest
java -cp target/Executor-1.0-jar-with-dependencies.jar com.company.MainWatchJarClasspathSmokeTest
```

Observed test coverage:

- `SandboxedJavaRunnerTest`
  - existing secure container behavior still passes
  - policy decision now recognizes `precompiled-container`

- `PrecompiledDockerJavaRunnerTest`
  - validates policy limit parsing
  - validates Docker command wiring for `/classes`, `/runner`, and `/deps`
  - validates dependency classpath handoff
  - executed a real precompiled-container PASS candidate on the host where Docker/image were available

- `MainWatchConcurrencySmokeTest`
  - submits two candidates into a two-worker pool
  - candidates rendezvous inside `main()`
  - both pass only if they execute concurrently

- `MainWatchAdaptiveCompilerSmokeTest`
  - confirms the existing adaptive compiler path still works

- `MainWatchOutcomeClassificationTest`
  - confirms canonical outcome accounting still works

- `MainWatchJarClasspathSmokeTest`
  - confirms dependency JAR registration and classpath behavior still works for local and container paths

## Known Limitations and Follow-Up Work

### gRPC Dispatcher Not Implemented Yet

The user request mentioned Docker/orchestration dispatcher nodes through gRPC. The current repository does not yet define:

- `.proto` files
- generated gRPC stubs
- dispatcher service name
- request/response schema
- artifact upload format
- authentication/TLS contract
- retry semantics
- result streaming semantics

Because that contract does not exist, today's implementation stops at a concrete Docker-backed precompiled execution node. A future gRPC implementation should be added behind a small dispatcher interface rather than embedded directly into `MainWatch`.

Suggested future interface:

```java
interface JavaExecutionDispatcher {
    SandboxedJavaRunner.RunResult run(
        String binaryClassName,
        Path compiledClasses,
        List<File> dependencyJars,
        String[] args,
        boolean customMode,
        ExecutionLimits limits);
}
```

Then implementations can be:

- `PrecompiledDockerJavaRunner`
- `GrpcJavaExecutionDispatcher`
- future container-orchestration/job-queue dispatcher

### Host Precompile Trust Boundary

`precompiled-container` compiles source on the host. The implementation uses `-proc:none`, but Java compilation is still more trusted than fully containerized compilation.

For untrusted candidate code, backend `container` remains the stricter isolation model because both compilation and execution happen inside Docker.

### In-Process Metrics Serialization

When trusted-local in-process execution and `-metricsFile` are both enabled, candidate invocation is serialized to protect the process-global `fw.metrics.out` system property. If full parallel trusted-local metrics are needed, replace the system property transport with a per-thread or per-invocation API that does not rely on global JVM state.

### Sharded Sources

Sharded source streaming remains sequential by design. Parallel shard streaming would require a different scratch-file strategy or a candidate body API that avoids writing one temporary loose Java file at a time.

### DB Writer Concurrency

This change parallelizes candidate compile/run work, not legacy DB flush internals. Existing async DB batching remains in place. Because candidate processing can now enqueue verdicts faster, production worker counts should be selected with DB capacity in mind.

## Operational Notes

Use conservative worker counts first:

```bash
-executorThreads 2
```

Increase gradually after observing:

- CPU saturation
- Docker container startup rate
- Results DB insert latency
- memory pressure
- candidate timeout rate

For precompiled-container runs, ensure the Docker image contains a JRE/JDK capable of running JDK single-file source mode for the harness. The default image remains:

```text
eclipse-temurin:21-jdk-alpine
```

The image can still be overridden by the existing environment mechanism used by the Java sandbox runner.

## End State

After today's work, the Java Executor can:

- watch and process multiple incoming Java files concurrently
- accept multiple loose-file source directories in manifest mode
- continue to process repeated legacy `-srcDirList` watch directories
- run existing trusted-local and secure-container modes unchanged
- precompile candidates on the Executor host and run compiled artifacts inside Docker
- report the selected container backend in `executor-summary.json`
- verify the new behavior through focused smoke tests
