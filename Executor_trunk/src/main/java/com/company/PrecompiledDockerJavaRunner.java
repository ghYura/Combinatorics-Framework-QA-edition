package com.company;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.regex.Matcher;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

import com.company.compiler.DynamicJavaCompiler;

/**
 * Host-precompile/container-run Java dispatcher. Unlike {@link SandboxedJavaRunner},
 * this mode compiles the renamed incoming source in the Executor JVM, then sends only
 * the compiled class directory plus configured dependency JARs into a locked-down
 * Docker container for actual execution.
 */
public final class PrecompiledDockerJavaRunner {
    private static final String MARKER = "__FWV__";
    private static final int SIGKILL_RC = 137, SIGXCPU_RC = 152;
    private static final String CLASSES_DIR = "/classes";
    private static final String RUNNER_DIR = "/runner";
    private static final String DEPENDENCY_DIR = "/deps";
    private static final String SCRATCH = "/sandbox";
    private static final int OUTPUT_CAP = 1 << 20;

    private final String image;
    private final String dockerCmd;
    private final Map<String, String> dockerEnv;
    private final double timeoutSeconds;
    private final Integer cpuSeconds;
    private final Long memoryBytes;
    private final Integer maxProcesses;

    public PrecompiledDockerJavaRunner(String image, double timeoutSeconds, Integer cpuSeconds,
                                       Long memoryBytes, Integer maxProcesses) {
        this.image = (image == null || image.isBlank()) ? SandboxedJavaRunner.DEFAULT_IMAGE : image;
        String[] discovered = SandboxedJavaRunner.discoverDocker();
        this.dockerCmd = discovered[0];
        this.dockerEnv = dockerEnv(discovered[1]);
        this.timeoutSeconds = timeoutSeconds > 0 ? timeoutSeconds : 30.0;
        this.cpuSeconds = cpuSeconds;
        this.memoryBytes = memoryBytes;
        this.maxProcesses = maxProcesses;
    }

    public static PrecompiledDockerJavaRunner fromPolicy(Map<String, Object> policy, String imageOverride) {
        double timeout = num(policy == null ? null : policy.get("timeout_seconds"), 30.0);
        Integer cpu = policy == null || policy.get("cpu_seconds") == null
                ? null : (int) num(policy.get("cpu_seconds"), 0);
        Long memory = policy == null || policy.get("memory_bytes") == null
                ? null : (long) num(policy.get("memory_bytes"), 0);
        Integer pids = policy == null || policy.get("max_processes") == null
                ? null : (int) num(policy.get("max_processes"), 0);
        return new PrecompiledDockerJavaRunner(imageOverride, timeout, cpu, memory, pids);
    }

    public String image() { return image; }

    public String describe() {
        return "precompiled-container-java (host javac -proc:none, docker image=" + image
                + ", read-only root, tmpfs scratch, pids<=" + maxProcesses
                + ", mem=" + memoryBytes + ", cpu_s=" + cpuSeconds
                + ", net=none, classpath=compiled-classes+deps)";
    }

    public boolean isAvailable() {
        if (dockerCmd == null) return false;
        try {
            Process p = process(List.of(dockerCmd, "image", "inspect", image));
            if (!p.waitFor(30, TimeUnit.SECONDS)) { p.destroyForcibly(); return false; }
            return p.exitValue() == 0;
        } catch (IOException | InterruptedException e) {
            if (e instanceof InterruptedException) Thread.currentThread().interrupt();
            return false;
        }
    }

    public SandboxedJavaRunner.RunResult run(String simpleClassName, String source, String[] args,
                                             boolean customMode, List<File> dependencyJars,
                                             int javaRelease) {
        if (dockerCmd == null) {
            return new SandboxedJavaRunner.RunResult(
                    SandboxedJavaRunner.Outcome.INFRA_FAIL, -999, -999, "", "docker CLI not found");
        }
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            return new SandboxedJavaRunner.RunResult(
                    SandboxedJavaRunner.Outcome.INFRA_FAIL, -999, -999, "", "No system Java compiler; run on a JDK");
        }

        Path build = null;
        String name = "bundle-precompiled-j-" + Long.toHexString(System.nanoTime());
        try {
            build = Files.createTempDirectory("fw-precompiled-java-");
            Path classes = Files.createDirectories(build.resolve("classes"));
            Path sourceFile = build.resolve(simpleClassName + ".java");
            Path runnerSource = build.resolve("FwPrecompiledRunner.java");
            Files.writeString(sourceFile, source, StandardCharsets.UTF_8);
            Files.writeString(runnerSource, HARNESS_SOURCE, StandardCharsets.UTF_8);

            String binaryName = binaryClassName(simpleClassName, source);
            String compileDiagnostics = compileHost(
                    compiler, sourceFile, classes, dependencyJars, Math.max(8, javaRelease));
            if (compileDiagnostics != null) {
                return new SandboxedJavaRunner.RunResult(
                        SandboxedJavaRunner.Outcome.BROKEN, -999, -999, "", compileDiagnostics);
            }

            List<String> cmd = buildArgv(classes, runnerSource, binaryName, args, name, dependencyJars);
            long startNanos = System.nanoTime();
            Proc pr = exec(cmd, timeoutSeconds, name);
            double elapsed = (System.nanoTime() - startNanos) / 1e9;

            if (pr.spawnError != null) {
                return new SandboxedJavaRunner.RunResult(
                        SandboxedJavaRunner.Outcome.INFRA_FAIL, -999, -999, pr.out, pr.spawnError);
            }

            boolean timedOut = pr.timedOut;
            if (!timedOut && cpuSeconds != null && (pr.rc == SIGKILL_RC || pr.rc == SIGXCPU_RC)
                    && elapsed >= cpuSeconds * 0.5 && !oomKilled(name)) {
                timedOut = true;
            }
            if (timedOut) {
                return new SandboxedJavaRunner.RunResult(
                        SandboxedJavaRunner.Outcome.TIMEOUT, -999, -999, pr.out, pr.err);
            }

            int[] verdicts = parseMarker(pr.out);
            if (verdicts == null) {
                return new SandboxedJavaRunner.RunResult(
                        SandboxedJavaRunner.Outcome.BROKEN, -999, -999, pr.out, pr.err);
            }
            int verdict = customMode ? verdicts[1] : verdicts[0];
            return new SandboxedJavaRunner.RunResult(
                    verdict == 0 ? SandboxedJavaRunner.Outcome.PASS : SandboxedJavaRunner.Outcome.DOMAIN_FAIL,
                    verdicts[0], verdicts[1], pr.out, pr.err);
        } catch (IOException e) {
            return new SandboxedJavaRunner.RunResult(
                    SandboxedJavaRunner.Outcome.INFRA_FAIL, -999, -999, "", "precompiled dispatch setup failed: " + e);
        } finally {
            rm(name);
            if (build != null) deleteQuiet(build);
        }
    }

    List<String> buildArgv(Path classes, Path runnerSource, String binaryClassName, String[] args,
                           String name, List<File> dependencyJars) {
        long scratchBytes = Math.max(memoryBytes == null ? 0 : memoryBytes, 128L * 1024 * 1024);
        List<String> cmd = new ArrayList<>(List.of(
                dockerCmd == null ? "docker" : dockerCmd, "run", "--name", name,
                "--network", "none",
                "--read-only",
                "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges",
                "--pids-limit", Integer.toString(maxProcesses == null ? 64 : maxProcesses),
                "--tmpfs", SCRATCH + ":rw,size=" + scratchBytes + ",mode=1777",
                "--tmpfs", "/tmp:rw,size=" + scratchBytes + ",mode=1777",
                "--workdir", SCRATCH,
                "--env", "HOME=" + SCRATCH,
                "--env", "TMPDIR=" + SCRATCH));
        if (memoryBytes != null) {
            cmd.add("--memory"); cmd.add(Long.toString(memoryBytes));
            cmd.add("--memory-swap"); cmd.add(Long.toString(memoryBytes));
        }
        if (cpuSeconds != null) {
            cmd.add("--ulimit"); cmd.add("cpu=" + cpuSeconds + ":" + cpuSeconds);
        }
        cmd.add("--volume"); cmd.add(classes.toAbsolutePath() + ":" + CLASSES_DIR + ":ro");
        cmd.add("--volume"); cmd.add(runnerSource.toAbsolutePath() + ":" + RUNNER_DIR + "/FwPrecompiledRunner.java:ro");

        List<String> dependencyClassPath = new ArrayList<>();
        int dependencyIndex = 0;
        for (File dependency : dependencyJars == null ? List.<File>of() : dependencyJars) {
            if (dependency == null || !dependency.isFile()) continue;
            String containerPath = DEPENDENCY_DIR + "/"
                    + String.format(java.util.Locale.ROOT, "%04d-", dependencyIndex++)
                    + dependency.getName();
            cmd.add("--volume");
            cmd.add(dependency.getAbsolutePath() + ":" + containerPath + ":ro");
            dependencyClassPath.add(containerPath);
        }

        cmd.add(image);
        cmd.add("java");
        if (!dependencyClassPath.isEmpty()) {
            cmd.add("-Dfw.cp=" + String.join(File.pathSeparator, dependencyClassPath));
        }
        cmd.add(RUNNER_DIR + "/FwPrecompiledRunner.java");
        cmd.add(binaryClassName);
        if (args != null) for (String arg : args) cmd.add(arg);
        return cmd;
    }

    private static String compileHost(JavaCompiler compiler, Path sourceFile, Path classes,
                                      List<File> dependencyJars, int javaRelease) {
        List<String> argv = new ArrayList<>();
        argv.add("-proc:none");
        argv.add("-encoding"); argv.add(StandardCharsets.UTF_8.name());
        argv.add("--release"); argv.add(Integer.toString(javaRelease));
        String classPath = hostClassPath(dependencyJars);
        if (!classPath.isBlank()) {
            argv.add("-classpath"); argv.add(classPath);
        }
        argv.add("-d"); argv.add(classes.toString());
        argv.add(sourceFile.toString());

        ByteArrayOutputStream diagnostics = new ByteArrayOutputStream();
        try (PrintStream ps = new PrintStream(diagnostics, true, StandardCharsets.UTF_8)) {
            int rc = compiler.run(null, null, ps, argv.toArray(new String[0]));
            return rc == 0 ? null : "host javac failed for " + sourceFile.getFileName() + ":\n"
                    + diagnostics.toString(StandardCharsets.UTF_8);
        }
    }

    private static String hostClassPath(List<File> dependencyJars) {
        List<String> entries = new ArrayList<>();
        for (File dependency : dependencyJars == null ? List.<File>of() : dependencyJars) {
            if (dependency != null && dependency.isFile()) entries.add(dependency.getAbsolutePath());
        }
        return String.join(File.pathSeparator, entries);
    }

    private static String binaryClassName(String simpleClassName, String source) {
        Matcher packageMatcher = DynamicJavaCompiler.PACKAGE_DECLARATION.matcher(source);
        return packageMatcher.find() ? packageMatcher.group(1) + "." + simpleClassName : simpleClassName;
    }

    private static int[] parseMarker(String stdout) {
        if (stdout == null) return null;
        for (String line : stdout.split("\n", -1)) {
            String s = line.trim();
            if (!s.startsWith(MARKER)) continue;
            String[] parts = s.split("\\s+");
            if (parts.length >= 3) {
                try { return new int[]{ Integer.parseInt(parts[1]), Integer.parseInt(parts[2]) }; }
                catch (NumberFormatException ignored) { }
            }
        }
        return null;
    }

    private static final class Proc {
        int rc; String out = "", err = ""; boolean timedOut; String spawnError;
    }

    private Proc exec(List<String> cmd, double timeoutSeconds, String name) {
        Proc pr = new Proc();
        Process p;
        try {
            p = process(cmd);
        } catch (IOException e) {
            pr.spawnError = e.getClass().getSimpleName() + ": " + e.getMessage();
            return pr;
        }
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        ByteArrayOutputStream err = new ByteArrayOutputStream();
        Thread outThread = gobble(p.getInputStream(), out);
        Thread errThread = gobble(p.getErrorStream(), err);
        try {
            if (!p.waitFor((long) (timeoutSeconds * 1000), TimeUnit.MILLISECONDS)) {
                pr.timedOut = true;
                rm(name);
                p.destroyForcibly();
                p.waitFor(10, TimeUnit.SECONDS);
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            p.destroyForcibly();
        }
        join(outThread); join(errThread);
        pr.rc = p.exitValue();
        pr.out = out.toString(StandardCharsets.UTF_8);
        pr.err = err.toString(StandardCharsets.UTF_8);
        return pr;
    }

    private static Thread gobble(InputStream in, ByteArrayOutputStream out) {
        Thread t = new Thread(() -> {
            byte[] buf = new byte[8192];
            int n;
            try {
                while ((n = in.read(buf)) != -1) {
                    if (out.size() < OUTPUT_CAP) out.write(buf, 0, Math.min(n, OUTPUT_CAP - out.size()));
                }
            } catch (IOException ignored) { }
        });
        t.setDaemon(true);
        t.start();
        return t;
    }

    private static void join(Thread t) {
        try { t.join(5000); } catch (InterruptedException e) { Thread.currentThread().interrupt(); }
    }

    private boolean oomKilled(String name) {
        try {
            Process p = process(List.of(dockerCmd, "inspect", "-f", "{{.State.OOMKilled}}", name));
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            Thread g = gobble(p.getInputStream(), out);
            if (!p.waitFor(15, TimeUnit.SECONDS)) { p.destroyForcibly(); return false; }
            join(g);
            return p.exitValue() == 0 && out.toString(StandardCharsets.UTF_8).trim().equals("true");
        } catch (IOException | InterruptedException e) {
            if (e instanceof InterruptedException) Thread.currentThread().interrupt();
            return false;
        }
    }

    private void rm(String name) {
        try {
            Process p = process(List.of(dockerCmd, "rm", "-f", name));
            if (!p.waitFor(30, TimeUnit.SECONDS)) p.destroyForcibly();
        } catch (IOException | InterruptedException e) {
            if (e instanceof InterruptedException) Thread.currentThread().interrupt();
        }
    }

    private Process process(List<String> cmd) throws IOException {
        ProcessBuilder pb = new ProcessBuilder(cmd);
        pb.environment().putAll(dockerEnv);
        return pb.start();
    }

    private static Map<String, String> dockerEnv(String host) {
        Map<String, String> env = new HashMap<>();
        if (host != null) env.put("DOCKER_HOST", host);
        String home = System.getProperty("user.home");
        String path = System.getenv().getOrDefault("PATH", "/usr/bin:/bin");
        env.put("PATH", home + "/bin" + File.pathSeparator + path);
        return env;
    }

    private static double num(Object o, double dflt) {
        if (o instanceof Number n) return n.doubleValue();
        if (o instanceof String s) {
            try { return Double.parseDouble(s.trim()); } catch (NumberFormatException ignored) { }
        }
        return dflt;
    }

    private static void deleteQuiet(Path root) {
        try (java.util.stream.Stream<Path> walk = Files.walk(root)) {
            walk.sorted(Comparator.reverseOrder()).forEach(path -> {
                try { Files.deleteIfExists(path); } catch (IOException ignored) { }
            });
        } catch (IOException ignored) { }
    }

    static final String HARNESS_SOURCE = """
            import java.net.URL;
            import java.net.URLClassLoader;
            import java.nio.file.Paths;
            import java.util.ArrayList;
            import java.util.Arrays;
            import java.util.List;

            public class FwPrecompiledRunner {
                public static void main(String[] a) throws Exception {
                    String cls = a[0];
                    String[] rest = Arrays.copyOfRange(a, 1, a.length);
                    List<URL> urls = new ArrayList<>();
                    urls.add(Paths.get(\"/classes\").toUri().toURL());
                    String extra = System.getProperty(\"fw.cp\", \"\");
                    if (!extra.isBlank()) {
                        for (String e : extra.split(java.io.File.pathSeparator)) {
                            if (!e.isBlank()) urls.add(Paths.get(e).toUri().toURL());
                        }
                    }
                    try (URLClassLoader cl = new URLClassLoader(urls.toArray(new URL[0]),
                            ClassLoader.getPlatformClassLoader())) {
                        Class<?> c = Class.forName(cls, true, cl);
                        c.getMethod(\"main\", String[].class).invoke(null, (Object) rest);
                        System.out.println(\"__FWV__ \" + readInt(c, \"FW_VAR\") + \" \" + readInt(c, \"FW_CUSTOM_VAR\"));
                    }
                }
                static int readInt(Class<?> c, String f) {
                    try { return c.getDeclaredField(f).getInt(null); } catch (Throwable t) { return -999; }
                }
            }
            """;
}
