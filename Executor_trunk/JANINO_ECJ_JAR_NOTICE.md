# Janino, ECJ, and Dependency JAR Notice

> **Current boundary (2026-07-21):** the Bundle defaults to Python candidates and
> `trusted-local` execution. `--lang java` selects this Executor; secure-container and
> precompiled-container behavior are explicit modes, not defaults. Java repeat fan-out with K>1 is
> currently limited to trusted in-process execution, and the live gRPC path is Java/Handoff-v2/
> `trusted-local` only.

## Purpose

The Java Executor compiles and executes incoming `.java` candidate files at runtime. Its default compiler workflow combines:

- native Janino for the fast path;
- Eclipse Compiler for Java (ECJ) for modern or Janino-incompatible Java;
- the configured dependency-JAR directory for classes required by incoming candidates.

The implementation is designed so that compiler fallback changes only compilation. A candidate's `main` method is invoked once, after compilation succeeds.

## Compiler Dependencies

The Maven build uses these compatible, non-shaded dependencies:

```xml
<dependency>
    <groupId>org.codehaus.janino</groupId>
    <artifactId>janino</artifactId>
    <version>3.1.12</version>
</dependency>

<dependency>
    <groupId>org.eclipse.jdt</groupId>
    <artifactId>ecj</artifactId>
    <version>3.45.0</version>
</dependency>
```

Janino supplies its matching `commons-compiler` dependency transitively.

Do not add `janino-commons-compiler-ecj-1.1.jar` to the Executor classpath. That old bridge is a shaded 2016 artifact containing `commons-compiler 3.0.6` and ECJ 4.6.1. Combining it with Janino 3.1.12 and ECJ 3.45.0 would introduce duplicate compiler classes and version-dependent class-loading behavior.

## Compiler Modes

Select the runtime compiler with:

```text
-Dfw.exec.compiler=<mode>
```

Supported modes:

| Mode | Behavior |
| --- | --- |
| `adaptive` | Default. Routes clearly modern syntax to ECJ; otherwise tries Janino and falls back to ECJ on compilation failure. |
| `auto` | Alias for `adaptive`. |
| `simple` | Backward-compatible alias for `adaptive`. |
| `janino` | Forces native Janino. Unsupported Java constructs fail without ECJ fallback. |
| `ecj` | Forces ECJ. |
| `javac` | Forces the system JDK compiler. Requires a JDK, not a JRE. |

Adaptive routing recognizes constructs such as lambdas, method references, `var`, records, sealed classes, `permits`, and `yield`. The fallback still catches other Janino limitations, including generic return values that require casts under Janino.

## Compilation Lifecycle

For the normal trusted in-process workflow:

1. MainWatch reads and renames the incoming top-level Java type to the generated candidate class name.
2. The configured JAR directory is refreshed.
3. Adaptive mode chooses Janino or ECJ.
4. If Janino compilation fails, ECJ compiles the original source.
5. The generated class is loaded through an isolated per-compilation classloader.
6. MainWatch invokes `main` and reads `FW_VAR` or `FW_CUSTOM_VAR` exactly once.
7. Compiler and generated-class references are released after processing.

ECJ uses a short-lived UTF-8 source file because ECJ 3.45.0's JSR-199 implementation requires an existing source file. Generated class bytecode remains in memory. The temporary source is removed before candidate execution.

## Configured JAR Directory

MainWatch requires:

```text
-dirJars /path/to/jars
```

Every valid regular `.jar` file in that directory is treated as an explicit dependency available to incoming Java candidates.

The Executor now provides these guarantees:

- existing JARs are discovered synchronously before candidate watchers can process files;
- the directory is refreshed before every compilation;
- live `ENTRY_CREATE` and `ENTRY_MODIFY` events are handled;
- JAR central directories are validated before registration;
- partial or corrupt copies do not terminate the watcher;
- Janino receives dependencies through its parent classloader;
- ECJ receives dependencies through its compiler classpath and runtime parent classloader;
- explicit javac receives dependencies during compilation and runtime loading;
- secure-container execution mounts dependencies read-only under `/deps` and includes them in both compilation and runtime classpaths.

If `-dirJars` is missing or does not identify a readable directory, Executor startup fails rather than silently processing candidates with an incomplete classpath.

## Deploying Dependency JARs

Prefer atomic deployment:

1. Write or copy the JAR under a temporary filename outside `dirJars`, or under a non-`.jar` temporary name.
2. Complete and close the file.
3. Atomically rename it to its final `.jar` filename inside `dirJars`.

Directly copying a large JAR into the watched directory is tolerated. A create event may see an incomplete archive, which is logged and retried on a later modify event and before each candidate compilation. Atomic rename is still preferable because it avoids transient failures and log noise.

Use versioned filenames when updating a dependency, for example:

```text
rules-api-1.4.0.jar
rules-api-1.5.0.jar
```

Do not rely on overwriting an already-loaded JAR under the same filename. Java classloaders cannot redefine classes that have already been loaded. Restart the Executor when replacing a loaded dependency or when removing a dependency from the effective runtime classpath.

Avoid placing multiple JARs containing the same classes in `dirJars`. Resolution order for duplicate classes should not be treated as a compatibility contract.

## Secure Container Mode

When execution policy selects the container backend, candidate code is not compiled or run in the MainWatch JVM.

For each candidate:

- its source and the execution harness are mounted read-only under `/src`;
- registered dependency JARs are mounted individually and read-only under `/deps`;
- the compiler classpath contains `/sandbox` and the explicit `/deps` entries;
- the runtime URLClassLoader uses the platform classloader as its parent, ensuring the candidate and dependency JARs are loaded through the isolated candidate classpath;
- the ambient host/project classpath is not exposed;
- existing network, filesystem, process, memory, CPU, and wall-time restrictions remain active.

Dependency JARs are trusted configuration inputs. Mounting a JAR makes its code callable by the candidate inside the sandbox, but does not grant access to host secrets or an unrestricted host classpath.

## Bundle Routing

`generator_trunk/bundle_run.py` now routes verdict execution from the validated Handoff v2 language:

```text
--lang py      -> Executor_trunk/py_executor.py
--lang java    -> Executor_trunk/target/Executor-1.0-jar-with-dependencies.jar
```

For Java, the Bundle passes all normal handshake directories plus:

```text
-dirJars <java_jars_dir>
-failOnly false
-exitWhenComplete true
```

The default `java_jars_dir` is `Executor_trunk/lib`. Therefore every regular, valid `.jar` in that directory is included in the compile-time and runtime classpath of incoming Java candidates. The Java Executor synchronously registers existing JARs at startup and refreshes the directory before each compilation. A missing directory is a preflight error; it is never silently ignored.

The defaults can be overridden through the typed Bundle configuration:

```text
--java-executor-jar PATH
--java-jars-dir DIR
--executor-timeout SECONDS
```

Equivalent environment keys are `BUNDLE_JAVA_EXECUTOR_JAR`, `BUNDLE_JAVA_JARS_DIR`, and `BUNDLE_EXECUTOR_TIMEOUT_SECONDS`; the same field names are accepted in a Bundle JSON config file.

The manifest is authoritative. A requested language that disagrees with `manifest.json` fails before an Executor starts. Java verdict runs require Handoff v2 because its declared candidate count drives deterministic completion: after all candidates are classified, MainWatch exits normally, its shutdown hook flushes legacy/results_v2 writes, and `executor-summary.json` is evaluated by the same Bundle invariants used for Python.

## Source Locations

Primary implementation files:

- `src/main/java/com/company/MainWatch.java`
- `src/main/java/com/company/compiler/AdaptiveJavaCompiler.java`
- `src/main/java/com/company/compiler/JaninoCompilerBackend.java`
- `src/main/java/com/company/compiler/EcjCompilerBackend.java`
- `src/main/java/com/company/compiler/DynamicJavaCompiler.java`
- `src/main/java/com/company/compiler/CompiledJavaClass.java`
- `src/main/java/com/company/SandboxedJavaRunner.java`

Verification harnesses:

- `src/main/java/com/company/compiler/AdaptiveJavaCompilerSmokeTest.java`
- `src/main/java/com/company/MainWatchAdaptiveCompilerSmokeTest.java`
- `src/main/java/com/company/MainWatchJarClasspathSmokeTest.java`
- `src/main/java/com/company/MainWatchHandoffV2SmokeTest.java`
- `src/main/java/com/company/MainWatchOutcomeClassificationTest.java`
- `src/main/java/com/company/SandboxedJavaRunnerTest.java`

## Verification Performed

The packaged Executor has been tested for:

- legacy-style source compiled by native Janino;
- lambdas and `var` compiled by ECJ;
- Janino's generic no-cast limitation falling back to ECJ;
- compilation fallback without duplicate candidate execution;
- packaged top-level classes;
- full MainWatch file consumption, class renaming, compilation, invocation, verdict reading, and result queuing;
- an externally generated dependency JAR imported and invoked by an incoming candidate through adaptive Janino;
- the same dependency JAR through adaptive ECJ;
- the same dependency JAR through explicit javac;
- the same dependency JAR compiled, loaded, and executed in the real Docker sandbox;
- execution from `target/Executor-1.0-jar-with-dependencies.jar`;
- Bundle-style Java Handoff routing with full verdict mode, automatic manifest-corpus completion, shutdown flushing, and executor-summary emission;
- existing outcome, manifest, and secure-container regression suites.

The expected deployable artifact is:

```text
target/Executor-1.0-jar-with-dependencies.jar
```

The thin `Executor-1.0.jar` does not contain dependency libraries and must not be treated as a standalone distribution unless its full Maven runtime classpath is supplied separately.
