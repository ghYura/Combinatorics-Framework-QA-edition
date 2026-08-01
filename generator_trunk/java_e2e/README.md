# Java Executor end-to-end specs

Two **combinable** Java specs that drive the Bundle's Java Executor (MainWatch +
`com.company.compiler.AdaptiveJavaCompiler`), each exercising a different compiler backend
to its purpose, and both importing an **external dependency** from `-dirJars`
(`Executor_trunk/lib-src/target/rules-api-1.0.0.jar`, class
`com.example.rules.Scorer`) to verify the
dependency-JAR pass-through.

| Spec | Backend | What it exercises |
|---|---|---|
| `janino_max/janino_max.toml` | **Janino** (lightweight Java) | generics+explicit type args, enhanced-for, a nested interface + anonymous class, recursion, try/catch/finally, classic `switch`, `StringBuilder`, bitwise/ternary, `Math.*`, dep-jar call. Every one of the 48 combos compiles+runs on Janino. |
| `ecj_modern/ecj_modern.toml` | **ECJ** (full modern Java) | a nested `record`, `var`, the Stream API, lambdas (`->`), method refs (`::`), `Collectors`, a switch **expression** with `yield`, dep-jar call. Every combo *fails* on Janino and compiles+runs on ECJ; adaptive routes them all to ECJ. |

Both are 48-candidate spaces: `1(HEAD) × 2(BASE) × 6(OPS=3!) × 4(FLAGS=2²) × 1(TAIL)`.

## Combinability discipline

All shared state is declared in the invariant **HEAD** (static fields, and — in the ECJ spec
— `var` locals in the `main` opener that are in scope for every later chunk regardless of
order). Each `FW_Permut`/`FW_Subsets` chunk is a **self-contained statement** that only mutates
that state, so *any* order/subset concatenates into valid Java. Order changes the **result**
(order-sensitive verdict), never compilability.

## Automated test (no DB)

`generator_trunk/test_java_e2e_specs.py` assembles every combo and compiles+runs each through the
real backends (forced Janino / forced ECJ / adaptive) via `CompileProbe.java`, asserting the
routing and the dep-jar resolution. Build both prerequisites first:

```bash
mvn -q -f Executor_trunk/lib-src/pom.xml package
mvn -q -f Executor_trunk/pom.xml -DskipTests package
cd generator_trunk
python3 -m pytest test_java_e2e_specs.py -q
```

The test skips when the Executor fat JAR, dependency directory, or JDK is
unavailable; a skipped test is not verification.

## Full Generator→Core→Reader→Java-Executor→Results-DB run

```bash
cd generator_trunk
: "${BUNDLE_MAIN_DB_PASSWORD:?inject the main DB password}"
: "${BUNDLE_RESULTS_DB_PASSWORD:?inject the results DB password}"
# Janino-max:
python3 bundle_run.py java_e2e/janino_max --db jmax --lang java \
    --execution-policy-profile trusted-local \
    --candidate-origin reviewed-checked-in \
    --acknowledge-trusted-local 'reviewed checked-in java_e2e fixture' --run-id jmax-001
# ECJ-modern:
python3 bundle_run.py java_e2e/ecj_modern  --db ecjm --lang java \
    --execution-policy-profile trusted-local \
    --candidate-origin reviewed-checked-in \
    --acknowledge-trusted-local 'reviewed checked-in java_e2e fixture' --run-id ecjm-001
```

The following are historical recorded results from an earlier host-PostgreSQL,
trusted-local campaign:

- `janino_max`: Core 48 → Reader 48 `.java` → Java Executor 48 processed → **29 PASS / 19 DOMAIN_FAIL / 0 BROKEN**, `results_v2` 48 inserted.
- `ecj_modern`: Core 48 → Reader 48 `.java` → Java Executor 48 processed → **24 PASS / 24 DOMAIN_FAIL / 0 BROKEN**, `results_v2` 48 inserted.

The corresponding raw run directories are not part of this checkout. Re-run
the commands and retain the run journal, Executor summary, metrics, and DB
snapshot when current evidence is required.

> `trusted-local` runs the in-process Janino/ECJ compiler (the documented opt-in). For untrusted
> Java use `--execution-policy-profile generated-default` (the container backend +
> `SandboxedJavaRunner`); the dependency JARs are mounted read-only under `/deps`. Force a specific
> backend with `--executor-compiler {adaptive,janino,ecj,javac}`.
