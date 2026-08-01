package com.company;

import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.jar.JarEntry;
import java.util.jar.JarOutputStream;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

/**
 * Proves that configured dependency JARs are available to Janino, ECJ, runtime loading,
 * and the secure-container command used for incoming candidate files.
 */
public final class MainWatchJarClasspathSmokeTest {
    private MainWatchJarClasspathSmokeTest() {}

    public static void main(String[] args) throws Exception {
        String previousCompiler = System.getProperty("fw.exec.compiler");
        boolean previousCustomMode = MainWatch.FW_CUSTOM_VARmode;
        boolean previousWriteFile = MainWatch.writeFile;
        boolean previousWriteToDb = MainWatch.writeToDB;
        File previousOut2 = MainWatch.out2;
        File previousDirJars = MainWatch.dirJars;
        Path root = Files.createTempDirectory("mainwatch-jar-classpath-");
        boolean ok;

        try {
            Path jars = Files.createDirectories(root.resolve("jars"));
            Path dependencyJar = buildDependencyJar(root, jars);
            MainWatch.dirJars = jars.toFile();
            int registered = MainWatch.registerExistingDependencyJars(jars);

            MainWatch.FW_CUSTOM_VARmode = false;
            MainWatch.writeFile = false;
            MainWatch.writeToDB = false;
            MainWatch.out2 = root.toFile();

            boolean janino = runCandidate(root, "410000_0_0", "adaptive",
                    "import external.dep.Support;"
                            + " public class IncomingJaninoDependency {"
                            + " public static int FW_VAR = 1;"
                            + " public static void main(String[] args) {"
                            + " FW_VAR = Support.answer() == 42 ? 0 : 1;"
                            + " } } ");

            boolean ecj = runCandidate(root, "410001_0_0", "adaptive",
                    "import external.dep.Support; import java.util.List;"
                            + " public class IncomingEcjDependency {"
                            + " public static int FW_VAR = 1;"
                            + " public static void main(String[] args) {"
                            + " var values = List.of(Support.answer());"
                            + " FW_VAR = values.stream().mapToInt(v -> v).sum() == 42 ? 0 : 1;"
                            + " } } ");

            boolean javac = runCandidate(root, "410002_0_0", "javac",
                    "import external.dep.Support;"
                            + " public class IncomingJavacDependency {"
                            + " public static int FW_VAR = 1;"
                            + " public static void main(String[] args) {"
                            + " FW_VAR = Support.answer() == 42 ? 0 : 1;"
                            + " } } ");

            boolean sandbox = sandboxCommandContainsDependency(root, dependencyJar);
            ok = registered == 1 && janino && ecj && javac && sandbox;
            System.out.println(ok
                    ? "MainWatchJarClasspathSmokeTest: ALL OK"
                    : "MainWatchJarClasspathSmokeTest: FAIL -- registered=" + registered
                            + " janino=" + janino + " ecj=" + ecj + " javac=" + javac
                            + " sandbox=" + sandbox);
        } finally {
            if (previousCompiler == null) System.clearProperty("fw.exec.compiler");
            else System.setProperty("fw.exec.compiler", previousCompiler);
            MainWatch.FW_CUSTOM_VARmode = previousCustomMode;
            MainWatch.writeFile = previousWriteFile;
            MainWatch.writeToDB = previousWriteToDb;
            MainWatch.out2 = previousOut2;
            MainWatch.dirJars = previousDirJars;
            MainWatch.bq.clear();
            deleteRecursively(root);
        }
        System.exit(ok ? 0 : 1);
    }

    private static boolean runCandidate(Path root, String id, String compiler, String source) throws IOException {
        System.setProperty("fw.exec.compiler", compiler);
        MainWatch.bq.clear();
        resetOutcomeCounts();
        Path candidate = root.resolve(id + ".java");
        Files.writeString(candidate, source, StandardCharsets.UTF_8);
        int processedBefore = MainWatch.atomicInteger.get();
        MainWatch.processCandidateFilePASSonly(candidate.toString());
        return MainWatch.atomicInteger.get() == processedBefore + 1
                && MainWatch.outcomeCounts.get(MainWatch.Outcome.PASS).get() == 1
                && MainWatch.outcomeCounts.get(MainWatch.Outcome.BROKEN).get() == 0
                && MainWatch.bq.size() == 1;
    }

    private static Path buildDependencyJar(Path root, Path jars) throws IOException {
        Path source = root.resolve("dependency-src/external/dep/Support.java");
        Path classes = Files.createDirectories(root.resolve("dependency-classes"));
        Files.createDirectories(source.getParent());
        Files.writeString(source,
                "package external.dep; public final class Support {"
                        + " private Support() {} public static int answer() { return 42; } }",
                StandardCharsets.UTF_8);

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) throw new IOException("System Java compiler is unavailable");
        int rc = compiler.run(null, null, null, "-d", classes.toString(), source.toString());
        if (rc != 0) throw new IOException("Failed to compile external dependency fixture, rc=" + rc);

        Path jar = jars.resolve("external-support.jar");
        try (JarOutputStream output = new JarOutputStream(Files.newOutputStream(jar));
             java.util.stream.Stream<Path> files = Files.walk(classes)) {
            for (Path file : files.filter(Files::isRegularFile).sorted().toList()) {
                String entryName = classes.relativize(file).toString().replace(File.separatorChar, '/');
                output.putNextEntry(new JarEntry(entryName));
                Files.copy(file, output);
                output.closeEntry();
            }
        }
        return jar.toRealPath();
    }

    private static boolean sandboxCommandContainsDependency(Path root, Path dependencyJar) {
        SandboxedJavaRunner runner = new SandboxedJavaRunner(
                null, 30, null, 256L * 1024 * 1024, 16, List.of());
        List<String> argv = runner.buildArgv(
                root, "Candidate", new String[0], "test-container", List.of(dependencyJar.toFile()));
        String expectedMount = dependencyJar.toFile().getAbsolutePath()
                + ":/deps/0000-" + dependencyJar.getFileName() + ":ro";
        String expectedClassPath = "-Dfw.cp=/deps/0000-" + dependencyJar.getFileName();
        boolean commandWired = argv.contains(expectedMount) && argv.contains(expectedClassPath);
        if (!commandWired || !runner.isAvailable()) {
            return commandWired;
        }

        SandboxedJavaRunner.RunResult result = runner.run(
                "SandboxDependencyCandidate",
                "import external.dep.Support; public class SandboxDependencyCandidate {"
                        + " public static int FW_VAR = 1;"
                        + " public static void main(String[] args) {"
                        + " FW_VAR = Support.answer() == 42 ? 0 : 1; } }",
                new String[0], false, List.of(dependencyJar.toFile()));
        if (result.outcome != SandboxedJavaRunner.Outcome.PASS) {
            System.out.println("sandbox dependency failure: outcome=" + result.outcome
                    + " stdout=" + result.stdout.replace('\n', ' ')
                    + " stderr=" + result.stderr.replace('\n', ' '));
        }
        return result.outcome == SandboxedJavaRunner.Outcome.PASS;
    }

    private static void resetOutcomeCounts() {
        for (MainWatch.Outcome outcome : MainWatch.Outcome.values()) {
            MainWatch.outcomeCounts.get(outcome).set(0);
        }
    }

    private static void deleteRecursively(Path root) {
        if (root == null || !Files.exists(root)) return;
        try (java.util.stream.Stream<Path> paths = Files.walk(root)) {
            paths.sorted(java.util.Comparator.reverseOrder()).forEach(path -> {
                try { Files.deleteIfExists(path); } catch (IOException ignored) { }
            });
        } catch (IOException ignored) { }
    }
}
