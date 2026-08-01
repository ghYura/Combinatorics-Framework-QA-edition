package com.company;

import java.io.File;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;

/**
 * Smoke test for MainWatch's bounded multi-candidate worker pool. The two candidates
 * rendezvous inside main(); with only serial execution one candidate times out and
 * records a DOMAIN_FAIL, while a two-worker pool lets both pass.
 */
public final class MainWatchConcurrencySmokeTest {
    private MainWatchConcurrencySmokeTest() {}

    private static volatile CountDownLatch entered;

    public static boolean enterAndAwait() throws InterruptedException {
        entered.countDown();
        return entered.await(5, TimeUnit.SECONDS);
    }

    public static void main(String[] args) throws Exception {
        boolean previousCustomMode = MainWatch.FW_CUSTOM_VARmode;
        boolean previousWriteFile = MainWatch.writeFile;
        boolean previousWriteToDb = MainWatch.writeToDB;
        boolean previousSecure = MainWatch.secureSandbox;
        boolean previousPrecompiled = MainWatch.precompiledDispatch;
        File previousOut2 = MainWatch.out2;
        int previousWorkers = MainWatch.candidateWorkerCount;
        Path root = Files.createTempDirectory("mainwatch-concurrency-");
        boolean ok = false;

        try {
            MainWatch.FW_CUSTOM_VARmode = false;
            MainWatch.writeFile = false;
            MainWatch.writeToDB = false;
            MainWatch.secureSandbox = false;
            MainWatch.precompiledDispatch = false;
            MainWatch.out2 = root.toFile();
            MainWatch.metricsCorpusFile = null;
            MainWatch.candidateWorkerCount = 2;
            MainWatch.bq.clear();
            resetOutcomeCounts();
            shutdownCandidateExecutor();
            invokeEnsureCandidateExecutor();

            entered = new CountDownLatch(2);
            Path first = writeCandidate(root, "700000_0_0");
            Path second = writeCandidate(root, "700001_0_0");
            int processedBefore = MainWatch.atomicInteger.get();

            Object passOnlyMode = enumValue("com.company.MainWatch$CandidateMode", "PASS_ONLY");
            Method submit = MainWatch.class.getDeclaredMethod("submitCandidateFile", Path.class, passOnlyMode.getClass());
            submit.setAccessible(true);
            submit.invoke(null, first, passOnlyMode);
            submit.invoke(null, second, passOnlyMode);

            long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(15);
            while (System.nanoTime() < deadline && MainWatch.atomicInteger.get() < processedBefore + 2) {
                Thread.sleep(50);
            }

            int processedDelta = MainWatch.atomicInteger.get() - processedBefore;
            int pass = MainWatch.outcomeCounts.get(MainWatch.Outcome.PASS).get();
            int fail = MainWatch.outcomeCounts.get(MainWatch.Outcome.DOMAIN_FAIL).get();
            ok = processedDelta == 2 && pass == 2 && fail == 0 && MainWatch.bq.size() == 2;
            System.out.println(ok
                    ? "MainWatchConcurrencySmokeTest: ALL OK"
                    : "MainWatchConcurrencySmokeTest: FAIL -- processedDelta=" + processedDelta
                            + " pass=" + pass + " domain_fail=" + fail + " queued=" + MainWatch.bq.size());
        } finally {
            shutdownCandidateExecutor();
            MainWatch.candidateWorkerCount = previousWorkers;
            MainWatch.FW_CUSTOM_VARmode = previousCustomMode;
            MainWatch.writeFile = previousWriteFile;
            MainWatch.writeToDB = previousWriteToDb;
            MainWatch.secureSandbox = previousSecure;
            MainWatch.precompiledDispatch = previousPrecompiled;
            MainWatch.out2 = previousOut2;
            MainWatch.bq.clear();
            deleteRecursively(root);
        }
        System.exit(ok ? 0 : 1);
    }

    private static Path writeCandidate(Path root, String id) throws Exception {
        Path file = root.resolve(id + ".java");
        Files.writeString(file,
                "import com.company.MainWatchConcurrencySmokeTest;"
                        + " public class IncomingConcurrentCandidate {"
                        + " public static int FW_VAR = 1;"
                        + " public static void main(String[] args) throws Exception {"
                        + " FW_VAR = MainWatchConcurrencySmokeTest.enterAndAwait() ? 0 : 1;"
                        + " } }",
                StandardCharsets.UTF_8);
        return file;
    }

    @SuppressWarnings({"unchecked", "rawtypes"})
    private static Object enumValue(String className, String name) throws Exception {
        return Enum.valueOf((Class<Enum>) Class.forName(className), name);
    }

    private static void invokeEnsureCandidateExecutor() throws Exception {
        Method ensure = MainWatch.class.getDeclaredMethod("ensureCandidateExecutor");
        ensure.setAccessible(true);
        ensure.invoke(null);
    }

    private static void shutdownCandidateExecutor() throws Exception {
        Field field = MainWatch.class.getDeclaredField("candidateExecutor");
        field.setAccessible(true);
        ExecutorService executor = (ExecutorService) field.get(null);
        if (executor != null) {
            executor.shutdownNow();
            executor.awaitTermination(5, TimeUnit.SECONDS);
            field.set(null, null);
        }
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
                try { Files.deleteIfExists(path); } catch (Exception ignored) { }
            });
        } catch (Exception ignored) { }
    }
}
