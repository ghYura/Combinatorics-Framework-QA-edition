package com.company;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

/**
 * STEP 29: the out-of-process secure backend for Java candidates -- the Java
 * analog of the Python Executor's {@code sandbox.ContainerBackend}.
 *
 * <p>In secure mode an untrusted candidate is NOT compiled or run inside the
 * MainWatch JVM (the in-process Janino/JDK path stays as the explicit
 * {@code trusted-local} opt-in). Instead it is compiled AND run inside a
 * throwaway rootless-Docker container with the same security boundary the Python
 * path enforces:
 * <ul>
 *   <li>{@code --read-only} root + an isolated writable {@code --tmpfs} scratch;</li>
 *   <li>{@code --pids-limit} / {@code --memory} / CPU-time {@code --ulimit cpu}
 *       (the policy's {@code cpu_seconds}) + a wall-clock timeout;</li>
 *   <li>{@code --cap-drop ALL} + {@code --security-opt no-new-privileges};</li>
 *   <li>{@code --network none} (a generated Java candidate gets no network);</li>
 *   <li>NO host environment -- Docker starts from the image env, so host secrets
 *       cannot leak (action 6);</li>
 *   <li>a classpath restricted to the in-sandbox scratch, explicit allowlist,
 *       and MainWatch's configured dependency JARs mounted read-only under
 *       {@code /deps} -- never the ambient host/project classpath (action 5).</li>
 * </ul>
 *
 * <p>The candidate's {@code FW_VAR}/{@code FW_CUSTOM_VAR} verdict is extracted by
 * an embedded harness ({@link #HARNESS_SOURCE}, run via JDK single-file source
 * mode so there is no shell to inject into) and mapped onto the SAME canonical
 * {@link Outcome} model py_executor and MainWatch use -- aligning the Java
 * mapping with Python (action 4): compile failure / no verdict marker / a
 * throwing {@code main} -&gt; BROKEN, the CPU/wall limit -&gt; TIMEOUT, a sandbox
 * that cannot start -&gt; INFRA_FAIL, verdict 0 -&gt; PASS, else DOMAIN_FAIL.
 *
 * <p>Standalone (no project deps) and side-effect free apart from a per-candidate
 * temp build dir + container, both removed in {@link #run}'s finally (guaranteed
 * cleanup).
 */
public final class SandboxedJavaRunner {

    /** Canonical outcome model (mirrors {@code MainWatch.Outcome} / py_executor.Outcome). */
    public enum Outcome { PASS, DOMAIN_FAIL, BROKEN, TIMEOUT, INFRA_FAIL, SKIPPED, CANCELLED }

    /** STEP 29 fail-closed decision: how the Java Executor is allowed to run a
     *  candidate, derived from the resolved execution policy. {@code REFUSE} is
     *  the safe default -- the in-process (trusted) path is opt-in ONLY. */
    public enum ExecMode {
        /** policy backend="container" + java/javac allowed -> compile+run out-of-process sandbox. */
        SECURE_SANDBOX,
        /** policy backend="precompiled-container" + java/javac allowed -> host compile, container run. */
        PRECOMPILED_CONTAINER,
        /** policy backend="local" + trusted=true + java/javac allowed -> in-process Janino/JDK. */
        TRUSTED_INPROCESS,
        /** anything else -- missing/corrupt policy, unknown backend, local+untrusted,
         *  or a policy that does not permit java/javac -- run NOTHING (fail closed). */
        REFUSE
    }

    /**
     * Decide how (or whether) the Java Executor may run a candidate, fail-closed.
     *
     * <p>The in-process path is never a silent fallback: it runs only for an
     * explicit {@code trusted-local} policy (or, with no policy, an explicit
     * {@code trustedOverride} = {@code -Dfw.exec.trusted=true} legacy opt-in).
     * A secure policy uses the sandbox. Everything else -- a missing/corrupt
     * policy, an unknown backend, a non-trusted {@code local} policy, or a policy
     * whose {@code allowed_interpreters} does not name {@code java}+{@code javac}
     * -- returns {@link ExecMode#REFUSE} so the caller exits without running
     * untrusted Java anywhere.
     *
     * @param policy          the execution_policy.json {@code "policy"} map, or {@code null}
     *                        when it is absent/corrupt
     * @param trustedOverride explicit legacy opt-in for the no-policy case
     */
    public static ExecMode decideExecMode(Map<String, Object> policy, boolean trustedOverride) {
        if (policy == null) {
            return trustedOverride ? ExecMode.TRUSTED_INPROCESS : ExecMode.REFUSE;
        }
        Object backend = policy.get("backend");
        boolean trusted = Boolean.TRUE.equals(policy.get("trusted"));
        boolean javaOk = interpretersAllowJava(policy);
        if ("container".equals(backend)) {
            return javaOk ? ExecMode.SECURE_SANDBOX : ExecMode.REFUSE;
        }
        if ("precompiled-container".equals(backend) || "container-precompiled".equals(backend)) {
            return javaOk ? ExecMode.PRECOMPILED_CONTAINER : ExecMode.REFUSE;
        }
        if ("local".equals(backend) && trusted) {
            return javaOk ? ExecMode.TRUSTED_INPROCESS : ExecMode.REFUSE;
        }
        // local+untrusted, unknown/missing backend, etc. -> never in-process.
        return ExecMode.REFUSE;
    }

    /** True only when the policy's {@code allowed_interpreters} explicitly permits
     *  BOTH {@code java} and {@code javac} (action: "явно разрешать Java/Javac в
     *  secure policy"). A python-only policy returns false -> the caller refuses. */
    public static boolean interpretersAllowJava(Map<String, Object> policy) {
        Object ai = policy == null ? null : policy.get("allowed_interpreters");
        if (!(ai instanceof List<?> list)) return false;
        boolean java = false, javac = false;
        for (Object o : list) {
            String s = String.valueOf(o);
            if ("java".equals(s)) java = true;
            else if ("javac".equals(s)) javac = true;
        }
        return java && javac;
    }

    /** Default JDK sandbox image (needs {@code javac}+{@code java}); override with
     *  {@code BUNDLE_SANDBOX_JAVA_IMAGE}. */
    public static final String DEFAULT_IMAGE =
            envOr("BUNDLE_SANDBOX_JAVA_IMAGE", "eclipse-temurin:21-jdk-alpine");

    private static final String MARKER = "__FWV__";
    private static final int SIGKILL_RC = 137, SIGXCPU_RC = 152;   // docker exit = 128 + signal
    private static final String CANDIDATE_DIR = "/src";
    private static final String DEPENDENCY_DIR = "/deps";
    private static final String SCRATCH = "/sandbox";
    private static final int OUTPUT_CAP = 1 << 20;                 // 1 MiB captured per stream

    /** Structured result -- the same shape the in-process path produces a verdict in. */
    public static final class RunResult {
        public final Outcome outcome;
        public final int fwVar, fwCustomVar;
        public final String stdout, stderr;
        RunResult(Outcome o, int fw, int fwc, String out, String err) {
            this.outcome = o; this.fwVar = fw; this.fwCustomVar = fwc; this.stdout = out; this.stderr = err;
        }
    }

    private final String image;
    private final String dockerCmd;
    private final Map<String, String> dockerEnv;
    private final double timeoutSeconds;
    private final Integer cpuSeconds;
    private final Long memoryBytes;
    private final Integer maxProcesses;
    private final List<String> classpathAllowlist;   // extra in-sandbox classpath entries (default none)

    public SandboxedJavaRunner(String image, double timeoutSeconds, Integer cpuSeconds, Long memoryBytes,
                               Integer maxProcesses, List<String> classpathAllowlist) {
        this.image = (image == null || image.isBlank()) ? DEFAULT_IMAGE : image;
        String[] disc = discoverDocker();
        this.dockerCmd = disc[0];
        this.dockerEnv = dockerEnv(disc[1]);
        this.timeoutSeconds = timeoutSeconds > 0 ? timeoutSeconds : 30.0;
        this.cpuSeconds = cpuSeconds;
        this.memoryBytes = memoryBytes;
        this.maxProcesses = maxProcesses;
        this.classpathAllowlist = classpathAllowlist == null ? List.of() : classpathAllowlist;
    }

    /** Build from the plain {@code execution_policy.json}'s {@code "policy"} map
     *  (the same dict py_executor's sandbox consumes). */
    public static SandboxedJavaRunner fromPolicy(Map<String, Object> policy, String imageOverride) {
        double t = num(policy.get("timeout_seconds"), 30.0);
        Integer cpu = policy.get("cpu_seconds") == null ? null : (int) num(policy.get("cpu_seconds"), 0);
        Long mem = policy.get("memory_bytes") == null ? null : (long) num(policy.get("memory_bytes"), 0);
        Integer pids = policy.get("max_processes") == null ? null : (int) num(policy.get("max_processes"), 0);
        return new SandboxedJavaRunner(imageOverride, t, cpu, mem, pids, List.of());
    }

    public String image() { return image; }

    /** Functional self-test: the JDK image is present (which also proves the
     *  daemon is reachable). Secure runs fail closed when this is false. */
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

    public String describe() {
        return "container-java (rootless docker, image=" + image + ", read-only root, tmpfs scratch, "
                + "pids<=" + maxProcesses + ", mem=" + memoryBytes + ", cpu_s=" + cpuSeconds
                + ", net=none, classpath=scratch" + (classpathAllowlist.isEmpty() ? "" : "+allowlist")
                + ", no published ports)";
    }

    /**
     * Compile + run one candidate inside the sandbox and classify it.
     *
     * @param className  the (already renamed) top-level class, e.g. {@code C1_0_0}
     * @param source     the candidate source declaring {@code className}
     * @param args       argv for the candidate's {@code main}
     * @param customMode  true -&gt; the verdict is {@code FW_CUSTOM_VAR}, else {@code FW_VAR}
     */
    public RunResult run(String className, String source, String[] args, boolean customMode) {
        return run(className, source, args, customMode, List.of());
    }

    public RunResult run(
            String className,
            String source,
            String[] args,
            boolean customMode,
            List<java.io.File> dependencyJars) {
        if (dockerCmd == null) return new RunResult(Outcome.INFRA_FAIL, -999, -999, "", "docker CLI not found");
        Path build;
        try {
            build = Files.createTempDirectory("fw-sbx-java-");
        } catch (IOException e) {
            return new RunResult(Outcome.INFRA_FAIL, -999, -999, "", "mkdtemp failed: " + e);
        }
        String name = "bundle-sbx-j-" + Long.toHexString(System.nanoTime());
        try {
            Files.writeString(build.resolve(className + ".java"), source, StandardCharsets.UTF_8);
            Files.writeString(build.resolve("FwRunner.java"), HARNESS_SOURCE, StandardCharsets.UTF_8);

            List<String> cmd = buildArgv(build, className, args, name, dependencyJars);
            long startNanos = System.nanoTime();
            Proc pr = exec(cmd, timeoutSeconds, name);
            double elapsed = (System.nanoTime() - startNanos) / 1e9;

            if (pr.spawnError != null) return new RunResult(Outcome.INFRA_FAIL, -999, -999, pr.out, pr.spawnError);

            boolean timedOut = pr.timedOut;
            // A non-wall signal-kill (137/152) at ~the CPU budget, and NOT an OOM
            // kill, is the cpu_seconds ulimit -> a *time* limit -> TIMEOUT (the
            // exact discrimination sandbox.py makes; OOM/crash stay BROKEN).
            if (!timedOut && cpuSeconds != null && (pr.rc == SIGKILL_RC || pr.rc == SIGXCPU_RC)
                    && elapsed >= cpuSeconds * 0.5 && !oomKilled(name)) {
                timedOut = true;
            }
            if (timedOut) return new RunResult(Outcome.TIMEOUT, -999, -999, pr.out, pr.err);

            int[] v = parseMarker(pr.out);
            if (v == null) {
                // compile failure / no verdict marker / a throwing main -> BROKEN (aligned with Python)
                return new RunResult(Outcome.BROKEN, -999, -999, pr.out, pr.err);
            }
            int verdict = customMode ? v[1] : v[0];
            return new RunResult(verdict == 0 ? Outcome.PASS : Outcome.DOMAIN_FAIL, v[0], v[1], pr.out, pr.err);
        } catch (IOException e) {
            return new RunResult(Outcome.INFRA_FAIL, -999, -999, "", "sandbox setup failed: " + e);
        } finally {
            rm(name);                 // guaranteed teardown (action 7)
            deleteQuiet(build);
        }
    }

    // ------------------------------- docker argv ------------------------------ //
    List<String> buildArgv(Path build, String className, String[] args, String name) {
        return buildArgv(build, className, args, name, List.of());
    }

    List<String> buildArgv(
            Path build,
            String className,
            String[] args,
            String name,
            List<java.io.File> dependencyJars) {
        long scratchBytes = Math.max(memoryBytes == null ? 0 : memoryBytes, 128L * 1024 * 1024);
        List<String> c = new ArrayList<>(List.of(
                dockerCmd, "run", "--name", name,
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
            c.add("--memory"); c.add(Long.toString(memoryBytes));
            c.add("--memory-swap"); c.add(Long.toString(memoryBytes));   // ==memory -> no swap headroom
        }
        if (cpuSeconds != null) {
            c.add("--ulimit"); c.add("cpu=" + cpuSeconds + ":" + cpuSeconds);
        }
        // Candidate, harness, and explicitly configured dependency JARs are mounted
        // read-only; the ambient host/project classpath is never exposed.
        c.add("--volume"); c.add(build.resolve(className + ".java").toAbsolutePath() + ":"
                + CANDIDATE_DIR + "/" + className + ".java:ro");
        c.add("--volume"); c.add(build.resolve("FwRunner.java").toAbsolutePath() + ":"
                + CANDIDATE_DIR + "/FwRunner.java:ro");
        List<String> candidateClassPath = new ArrayList<>(classpathAllowlist);
        int dependencyIndex = 0;
        for (java.io.File dependency : dependencyJars == null ? List.<java.io.File>of() : dependencyJars) {
            if (dependency == null || !dependency.isFile()) continue;
            String containerPath = DEPENDENCY_DIR + "/"
                    + String.format(java.util.Locale.ROOT, "%04d-", dependencyIndex++)
                    + dependency.getName();
            c.add("--volume");
            c.add(dependency.getAbsolutePath() + ":" + containerPath + ":ro");
            candidateClassPath.add(containerPath);
        }
        c.add(image);
        // Run the harness via JDK single-file source mode -- compiles+loads the
        // candidate inside the sandbox and prints the verdict marker. No shell:
        // className/args are clean argv, not interpolated into a `sh -c` string.
        c.add("java");
        if (!candidateClassPath.isEmpty()) {
            c.add("-Dfw.cp=" + String.join(java.io.File.pathSeparator, candidateClassPath));
        }
        c.add(CANDIDATE_DIR + "/FwRunner.java");
        c.add(className);
        if (args != null) for (String a : args) c.add(a);
        return c;
    }

    // ------------------------------- subprocess ------------------------------- //
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
        ByteArrayOutputStream outBuf = new ByteArrayOutputStream();
        ByteArrayOutputStream errBuf = new ByteArrayOutputStream();
        Thread to = gobble(p.getInputStream(), outBuf);
        Thread te = gobble(p.getErrorStream(), errBuf);
        try {
            if (!p.waitFor((long) (timeoutSeconds * 1000), TimeUnit.MILLISECONDS)) {
                pr.timedOut = true;
                rm(name);                       // kill the container the daemon still runs
                p.destroyForcibly();
                p.waitFor(10, TimeUnit.SECONDS);
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            p.destroyForcibly();
        }
        join(to); join(te);
        pr.rc = p.exitValue();
        pr.out = outBuf.toString(StandardCharsets.UTF_8);
        pr.err = errBuf.toString(StandardCharsets.UTF_8);
        return pr;
    }

    private static Thread gobble(InputStream in, ByteArrayOutputStream out) {
        Thread t = new Thread(() -> {
            byte[] buf = new byte[8192];
            int n;
            try {
                while ((n = in.read(buf)) != -1) {
                    if (out.size() < OUTPUT_CAP) out.write(buf, 0, Math.min(n, OUTPUT_CAP - out.size()));
                    // keep draining past the cap so the child never blocks on a full pipe
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

    // ------------------------------- helpers ---------------------------------- //
    static int[] parseMarker(String stdout) {
        if (stdout == null) return null;
        for (String line : stdout.split("\n", -1)) {
            String s = line.trim();
            if (s.startsWith(MARKER)) {
                String[] p = s.split("\\s+");
                if (p.length >= 3) {
                    try { return new int[]{ Integer.parseInt(p[1]), Integer.parseInt(p[2]) }; }
                    catch (NumberFormatException ignored) { }
                }
            }
        }
        return null;
    }

    private static double num(Object o, double dflt) {
        if (o instanceof Number n) return n.doubleValue();
        if (o instanceof String s) { try { return Double.parseDouble(s.trim()); } catch (NumberFormatException ignored) { } }
        return dflt;
    }

    private static String envOr(String key, String dflt) {
        String v = System.getenv(key);
        return (v == null || v.isBlank()) ? dflt : v;
    }

    /** Locate the docker CLI + rootless socket without assuming the launcher's
     *  env was set up (mirrors sandbox.py {@code _discover_docker}). Returns
     *  {@code [dockerCmd-or-null, dockerHost-or-null]}. */
    static String[] discoverDocker() {
        String cmd = which("docker");
        if (cmd == null) {
            for (String cand : new String[]{ System.getProperty("user.home") + "/bin/docker",
                    "/usr/bin/docker", "/usr/local/bin/docker" }) {
                if (Files.isExecutable(Paths.get(cand))) { cmd = cand; break; }
            }
        }
        String host = System.getenv("DOCKER_HOST");
        if (host == null || host.isBlank()) {
            String runtime = System.getenv("XDG_RUNTIME_DIR");
            if (runtime == null || runtime.isBlank()) {
                long uid = uid();
                if (uid >= 0) runtime = "/run/user/" + uid;
            }
            if (runtime != null) {
                Path sock = Paths.get(runtime, "docker.sock");
                if (Files.exists(sock)) host = "unix://" + sock;
            }
        }
        return new String[]{ cmd, host };
    }

    private static Map<String, String> dockerEnv(String host) {
        java.util.HashMap<String, String> env = new java.util.HashMap<>();
        if (host != null) env.put("DOCKER_HOST", host);
        String home = System.getProperty("user.home");
        String path = System.getenv().getOrDefault("PATH", "/usr/bin:/bin");
        env.put("PATH", home + "/bin" + java.io.File.pathSeparator + path);
        return env;
    }

    private static String which(String exe) {
        String path = System.getenv("PATH");
        if (path == null) return null;
        for (String dir : path.split(java.io.File.pathSeparator)) {
            Path p = Paths.get(dir, exe);
            if (Files.isExecutable(p)) return p.toString();
        }
        return null;
    }

    private static long uid() {
        try {
            Process p = new ProcessBuilder("id", "-u").redirectErrorStream(true).start();
            String s = new String(p.getInputStream().readAllBytes(), StandardCharsets.UTF_8).trim();
            p.waitFor(5, TimeUnit.SECONDS);
            return Long.parseLong(s);
        } catch (Exception e) {
            return -1;
        }
    }

    private static void deleteQuiet(Path root) {
        try (java.util.stream.Stream<Path> w = Files.walk(root)) {
            w.sorted(Comparator.reverseOrder()).forEach(p -> {
                try { Files.deleteIfExists(p); } catch (IOException ignored) { }
            });
        } catch (IOException ignored) { }
    }

    /** The in-sandbox harness, compiled+run via JDK single-file source mode. It
     *  compiles the candidate with the system Java compiler into the writable
     *  scratch (classpath = scratch + optional read-only {@code -Dfw.cp}
     *  dependencies, never the ambient host classpath), loads it through an
     *  isolated child class loader, invokes
     *  {@code main}, then prints {@code __FWV__ <FW_VAR> <FW_CUSTOM_VAR>}. A
     *  compile failure or a throwing {@code main} prints NO marker -&gt; the
     *  caller classifies it BROKEN, exactly as the Python path does. */
    static final String HARNESS_SOURCE = """
            import javax.tools.JavaCompiler;
            import javax.tools.ToolProvider;
            import java.io.ByteArrayOutputStream;
            import java.io.PrintStream;
            import java.net.URL;
            import java.net.URLClassLoader;
            import java.nio.charset.StandardCharsets;
            import java.nio.file.Files;
            import java.nio.file.Path;
            import java.nio.file.Paths;
            import java.util.ArrayList;
            import java.util.Arrays;
            import java.util.List;

            public class FwRunner {
                public static void main(String[] a) throws Exception {
                    String cls = a[0];
                    String[] rest = Arrays.copyOfRange(a, 1, a.length);
                    Path src = Paths.get("/src", cls + ".java");
                    Path out = Paths.get("/sandbox");
                    Files.createDirectories(out);

                    List<String> cp = new ArrayList<>();
                    cp.add(out.toString());
                    String extra = System.getProperty("fw.cp", "");
                    if (!extra.isBlank()) for (String e : extra.split(java.io.File.pathSeparator)) cp.add(e);
                    String cpStr = String.join(java.io.File.pathSeparator, cp);

                    JavaCompiler jc = ToolProvider.getSystemJavaCompiler();
                    if (jc == null) { System.err.println("no system Java compiler in sandbox image"); System.exit(3); }
                    ByteArrayOutputStream diag = new ByteArrayOutputStream();
                    int rc = jc.run(null, null, new PrintStream(diag, true, "UTF-8"),
                                    "-classpath", cpStr, "-d", out.toString(), src.toString());
                    if (rc != 0) {
                        System.err.println("COMPILE_FAILED\\n" + diag.toString("UTF-8"));
                        System.exit(2);                       // no marker -> BROKEN
                    }
                    List<URL> urls = new ArrayList<>();
                    for (String e : cp) urls.add(Paths.get(e).toUri().toURL());
                    try (URLClassLoader cl = new URLClassLoader(urls.toArray(new URL[0]),
                            ClassLoader.getPlatformClassLoader())) {
                        Class<?> c = Class.forName(cls, true, cl);
                        c.getMethod("main", String[].class).invoke(null, (Object) rest);  // throws -> no marker -> BROKEN
                        System.out.println("__FWV__ " + readInt(c, "FW_VAR") + " " + readInt(c, "FW_CUSTOM_VAR"));
                    }
                }
                static int readInt(Class<?> c, String f) {
                    try { return c.getDeclaredField(f).getInt(null); } catch (Throwable t) { return -999; }
                }
            }
            """;
}
