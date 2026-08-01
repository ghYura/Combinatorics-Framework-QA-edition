package com.company;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/** Smoke checks for the precompiled-container Java dispatcher. */
public final class PrecompiledDockerJavaRunnerTest {
    private PrecompiledDockerJavaRunnerTest() {}

    public static void main(String[] args) throws Exception {
        int failures = 0;
        Map<String, Object> policy = new HashMap<>();
        policy.put("backend", "precompiled-container");
        policy.put("timeout_seconds", 12);
        policy.put("cpu_seconds", 5);
        policy.put("memory_bytes", 134217728L);
        policy.put("max_processes", 8);

        PrecompiledDockerJavaRunner runner = PrecompiledDockerJavaRunner.fromPolicy(policy, "img:tag");
        String description = runner.describe();
        failures += check("describe includes parsed limits",
                description.contains("precompiled-container-java")
                        && description.contains("image=img:tag")
                        && description.contains("pids<=8")
                        && description.contains("cpu_s=5")
                        && description.contains("mem=134217728"));

        Path root = Files.createTempDirectory("precompiled-runner-test-");
        try {
            Path classes = Files.createDirectories(root.resolve("classes"));
            Path harness = root.resolve("FwPrecompiledRunner.java");
            Path dep = root.resolve("dep.jar");
            Files.writeString(harness, PrecompiledDockerJavaRunner.HARNESS_SOURCE, StandardCharsets.UTF_8);
            Files.writeString(dep, "not-a-real-jar", StandardCharsets.UTF_8);

            List<String> argv = runner.buildArgv(classes, harness, "Candidate", new String[]{"x"},
                    "test-container", List.of(dep.toFile()));
            failures += check("docker argv mounts compiled classes",
                    argv.contains(classes.toAbsolutePath() + ":/classes:ro"));
            failures += check("docker argv mounts harness",
                    argv.contains(harness.toAbsolutePath() + ":/runner/FwPrecompiledRunner.java:ro"));
            failures += check("docker argv mounts dependency jar",
                    argv.contains(dep.toAbsolutePath() + ":/deps/0000-dep.jar:ro"));
            failures += check("docker argv passes dependency classpath",
                    argv.contains("-Dfw.cp=/deps/0000-dep.jar"));
            failures += check("docker argv passes binary name and args",
                    argv.contains("Candidate") && argv.contains("x"));
        } finally {
            deleteRecursively(root);
        }

        Map<String, Object> runtimePolicy = new HashMap<>(policy);
        runtimePolicy.put("max_processes", 64);
        PrecompiledDockerJavaRunner realRunner = PrecompiledDockerJavaRunner.fromPolicy(runtimePolicy, null);
        if (!realRunner.isAvailable()) {
            System.out.println("SKIP: rootless Docker / image " + realRunner.image()
                    + " unavailable -- precompiled-container execution not exercised here");
        } else {
            SandboxedJavaRunner.RunResult result = realRunner.run(
                    "PrecompiledPassCandidate",
                    "public class PrecompiledPassCandidate { public static int FW_VAR = 1; "
                            + "public static void main(String[] args) { FW_VAR = 0; } }",
                    new String[0], false, List.of(), Runtime.version().feature());
            failures += check("real precompiled-container run -> PASS",
                    result.outcome == SandboxedJavaRunner.Outcome.PASS);
            if (result.outcome != SandboxedJavaRunner.Outcome.PASS) {
                System.out.println("  outcome=" + result.outcome + " stdout="
                        + result.stdout.replace('\n', ' ') + " stderr=" + result.stderr.replace('\n', ' '));
            }
        }

        System.out.println(failures == 0 ? "PrecompiledDockerJavaRunnerTest: ALL OK"
                : "PrecompiledDockerJavaRunnerTest: " + failures + " FAILURE(S)");
        System.exit(failures == 0 ? 0 : 1);
    }

    private static int check(String label, boolean ok) {
        System.out.println((ok ? "  ok  " : "  FAIL ") + label);
        return ok ? 0 : 1;
    }

    private static void deleteRecursively(Path root) {
        if (root == null || !Files.exists(root)) return;
        try (java.util.stream.Stream<Path> paths = Files.walk(root)) {
            paths.sorted(java.util.Comparator.reverseOrder()).forEach(path -> {
                try { Files.deleteIfExists(path); } catch (Exception ignored) { }
            });
        } catch (Exception ignored) { }
    }
}
