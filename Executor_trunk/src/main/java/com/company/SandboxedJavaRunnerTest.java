package com.company;

import java.util.List;

/**
 * STEP 29 targeted smoke test for {@link SandboxedJavaRunner} (the out-of-process
 * secure Java backend). Main-based, like {@code MainWatchOutcomeClassificationTest}
 * -- no JUnit dependency. Exercises the four required behaviors against the real
 * rootless-Docker sandbox plus a couple of extras:
 *
 *   normal candidate            -> PASS         (verdict 0, out-of-process)
 *   domain-fail candidate       -> DOMAIN_FAIL  (verdict != 0)
 *   compile failure             -> BROKEN       (no verdict marker)
 *   timeout candidate           -> TIMEOUT      (wall clock)
 *   cpu_seconds enforcement     -> TIMEOUT      (CPU-time budget, before the wall)
 *   prohibited filesystem write -> BROKEN       (read-only root: main throws)
 *   network disabled            -> PASS         (--network none blocks egress)
 *
 * Run after `mvn -q -o compile`:
 *   java -cp target/classes com.company.SandboxedJavaRunnerTest
 * SKIPs cleanly (exit 0) when rootless Docker / the JDK image is unavailable.
 */
public final class SandboxedJavaRunnerTest {

    private static int failures = 0;

    public static void main(String[] args) {
        // STEP 29 fail-closed decision (no Docker needed, always runs): the
        // in-process path is the trusted-local opt-in ONLY; everything else
        // (missing/corrupt policy, unknown backend, local+untrusted, or a policy
        // that does not allow java/javac) REFUSES.
        eq("container + java/javac -> SECURE_SANDBOX", SandboxedJavaRunner.ExecMode.SECURE_SANDBOX,
                SandboxedJavaRunner.decideExecMode(pol("container", false, "python", "java", "javac"), false));
        eq("container + python-only -> REFUSE (interpreter)", SandboxedJavaRunner.ExecMode.REFUSE,
                SandboxedJavaRunner.decideExecMode(pol("container", false, "python"), false));
        eq("precompiled-container + java/javac -> PRECOMPILED_CONTAINER", SandboxedJavaRunner.ExecMode.PRECOMPILED_CONTAINER,
                SandboxedJavaRunner.decideExecMode(pol("precompiled-container", false, "java", "javac"), false));
        eq("local + trusted + java/javac -> TRUSTED_INPROCESS", SandboxedJavaRunner.ExecMode.TRUSTED_INPROCESS,
                SandboxedJavaRunner.decideExecMode(pol("local", true, "python", "java", "javac"), false));
        eq("local + trusted=false -> REFUSE", SandboxedJavaRunner.ExecMode.REFUSE,
                SandboxedJavaRunner.decideExecMode(pol("local", false, "python", "java", "javac"), false));
        eq("unknown backend -> REFUSE", SandboxedJavaRunner.ExecMode.REFUSE,
                SandboxedJavaRunner.decideExecMode(pol("wormhole", true, "java", "javac"), false));
        eq("missing/corrupt policy, no override -> REFUSE", SandboxedJavaRunner.ExecMode.REFUSE,
                SandboxedJavaRunner.decideExecMode(null, false));
        eq("missing policy + -Dfw.exec.trusted -> TRUSTED_INPROCESS", SandboxedJavaRunner.ExecMode.TRUSTED_INPROCESS,
                SandboxedJavaRunner.decideExecMode(null, true));

        // policy -> runner resolution (the parse MainWatch performs from
        // execution_policy.json's "policy" map); no Docker needed, always runs.
        java.util.Map<String, Object> pol = new java.util.HashMap<>();
        pol.put("backend", "container"); pol.put("timeout_seconds", 12);
        pol.put("cpu_seconds", 5); pol.put("memory_bytes", 134217728L); pol.put("max_processes", 8);
        String d = SandboxedJavaRunner.fromPolicy(pol, "img:tag").describe();
        if (d.contains("image=img:tag") && d.contains("pids<=8") && d.contains("cpu_s=5") && d.contains("mem=134217728")) {
            System.out.println("  ok  fromPolicy parses limits: " + d);
        } else {
            System.out.println("  FAIL fromPolicy parse: " + d); failures++;
        }

        SandboxedJavaRunner probe = new SandboxedJavaRunner(null, 30, null, 256L * 1024 * 1024, 16, List.of());
        if (!probe.isAvailable()) {
            System.out.println("SKIP: rootless Docker / image " + SandboxedJavaRunner.DEFAULT_IMAGE
                    + " unavailable -- secure Java sandbox not exercisable here");
            if (failures > 0) System.exit(1);
            return;
        }
        System.out.println("sandbox: " + probe.describe());

        // 1) normal candidate -> PASS
        check("normal -> PASS", SandboxedJavaRunner.Outcome.PASS,
                run(probe, "CnormalT",
                        "public class CnormalT { public static int FW_VAR; "
                        + "public static void main(String[] a){ FW_VAR = 0; } }", false));

        // 2) domain-fail candidate -> DOMAIN_FAIL
        check("domain-fail -> DOMAIN_FAIL", SandboxedJavaRunner.Outcome.DOMAIN_FAIL,
                run(probe, "CdomainT",
                        "public class CdomainT { public static int FW_VAR; "
                        + "public static void main(String[] a){ FW_VAR = 7; } }", false));

        // 3) compile failure -> BROKEN (no verdict marker emitted)
        check("compile-failure -> BROKEN", SandboxedJavaRunner.Outcome.BROKEN,
                run(probe, "CbadT",
                        "public class CbadT { public static void main(String[] a){ this is not java } }", false));

        // 4) infinite loop -> TIMEOUT (wall clock); short timeout, no cpu limit
        SandboxedJavaRunner wall = new SandboxedJavaRunner(null, 6, null, 256L * 1024 * 1024, 16, List.of());
        long t0 = System.currentTimeMillis();
        SandboxedJavaRunner.RunResult loop = run(wall, "CloopT",
                "public class CloopT { public static int FW_VAR; "
                + "public static void main(String[] a){ while(true){} } }", false);
        check("infinite-loop -> TIMEOUT (" + (System.currentTimeMillis() - t0) + "ms)",
                SandboxedJavaRunner.Outcome.TIMEOUT, loop);

        // 5) cpu_seconds enforced -> TIMEOUT well before the (much larger) wall timeout
        SandboxedJavaRunner cpu = new SandboxedJavaRunner(null, 30, 2, 256L * 1024 * 1024, 16, List.of());
        long t1 = System.currentTimeMillis();
        SandboxedJavaRunner.RunResult burn = run(cpu, "CburnT",
                "public class CburnT { public static int FW_VAR; "
                + "public static void main(String[] a){ long x=0; while(true){ x++; } } }", false);
        long burnMs = System.currentTimeMillis() - t1;
        check("cpu_seconds enforced -> TIMEOUT (" + burnMs + "ms, < wall 30s)",
                SandboxedJavaRunner.Outcome.TIMEOUT, burn);
        if (burnMs >= 15000) { System.out.println("  FAIL: cpu kill took too long (" + burnMs + "ms)"); failures++; }

        // 6) prohibited filesystem write (read-only root) -> main throws -> BROKEN
        check("write outside scratch -> BROKEN", SandboxedJavaRunner.Outcome.BROKEN,
                run(probe, "CwriteT",
                        "import java.nio.file.*; public class CwriteT { public static int FW_VAR; "
                        + "public static void main(String[] a) throws Exception { "
                        + "Files.writeString(Paths.get(\"/etc/evil\"), \"x\"); FW_VAR = 0; } }", false));
        // control: writing INTO the scratch works -> PASS
        check("write into scratch -> PASS", SandboxedJavaRunner.Outcome.PASS,
                run(probe, "CokwriteT",
                        "import java.nio.file.*; public class CokwriteT { public static int FW_VAR; "
                        + "public static void main(String[] a) throws Exception { "
                        + "Files.writeString(Paths.get(\"/sandbox/ok\"), \"x\"); FW_VAR = 0; } }", false));

        // 7) network disabled: connect attempt fails -> candidate sets FW_VAR=0 -> PASS
        check("network none blocks egress -> PASS", SandboxedJavaRunner.Outcome.PASS,
                run(probe, "CnetT",
                        "import java.net.*; public class CnetT { public static int FW_VAR; "
                        + "public static void main(String[] a){ try { "
                        + "Socket s = new Socket(); s.connect(new InetSocketAddress(\"1.1.1.1\", 53), 3000); "
                        + "FW_VAR = 1; } catch (Exception e) { FW_VAR = 0; } } }", false));

        System.out.println(failures == 0 ? "\nALL SANDBOX-JAVA CHECKS PASSED"
                : "\n" + failures + " CHECK(S) FAILED");
        if (failures > 0) System.exit(1);
    }

    private static java.util.Map<String, Object> pol(String backend, boolean trusted, String... interps) {
        java.util.Map<String, Object> m = new java.util.HashMap<>();
        m.put("backend", backend);
        m.put("trusted", trusted);
        m.put("allowed_interpreters", java.util.Arrays.asList(interps));
        return m;
    }

    private static void eq(String label, Object expected, Object got) {
        boolean ok = java.util.Objects.equals(expected, got);
        System.out.println((ok ? "  ok  " : "  FAIL ") + label + " (got " + got + ")");
        if (!ok) failures++;
    }

    private static SandboxedJavaRunner.RunResult run(SandboxedJavaRunner r, String cls, String src, boolean custom) {
        return r.run(cls, src, new String[0], custom);
    }

    private static void check(String label, SandboxedJavaRunner.Outcome expected, SandboxedJavaRunner.RunResult got) {
        boolean ok = got.outcome == expected;
        System.out.println((ok ? "  ok  " : "  FAIL ") + label + "  (got " + got.outcome
                + (ok ? "" : ", fw=" + got.fwVar + " fwc=" + got.fwCustomVar
                       + " err=" + oneLine(got.stderr)) + ")");
        if (!ok) failures++;
    }

    private static String oneLine(String s) {
        if (s == null) return "";
        s = s.strip().replace('\n', ' ');
        return s.length() > 160 ? s.substring(0, 160) + "..." : s;
    }
}
