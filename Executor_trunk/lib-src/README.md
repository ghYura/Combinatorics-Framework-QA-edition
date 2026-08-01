# Dependency-JAR test fixture source

`com/example/rules/Scorer.java` is the source for `../lib/rules-api-1.0.0.jar`, the external
dependency the Java E2E specs (`generator_trunk/java_e2e/{janino_max,ecj_modern}`) import and
invoke to verify the `-dirJars` dependency pass-through (resolved through Janino's parent
classloader and ECJ's compile classpath + runtime parent).

Rebuild the jar:

```bash
javac --release 17 -d /tmp/scorer com/example/rules/Scorer.java
jar --create --file ../lib/rules-api-1.0.0.jar \
  -C /tmp/scorer com/example/rules/Scorer.class
```

This JAR is a repository test fixture, not a production dependency bundle.
