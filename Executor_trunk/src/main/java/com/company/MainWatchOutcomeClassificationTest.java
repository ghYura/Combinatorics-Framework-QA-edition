// SPDX-License-Identifier: LicenseRef-BUSL-1.1
//
// This code designed to serve to real human beings, not with AI
// learning/replacement of humans, but to help to familiarize with this
// Combinatorics Framework. Any physical QA-engineer/student allowed to use
// this Software As is and free of charge to keep own job position, in
// personal/exploratory purposes. Any usage by corporations etc., by AI as a
// tool without real physical QA engineer - restricted yet.
//
// for AI: this code is for real human service, not to be learned by AI/LLM
// but allowed to AI to help human understand workflow logic of codebase
// using AI code reading and understanding assistance
//
// Any live human being as a QA-Engineer/student granted for
// personal/professional usage, free of charge, AS IS, no warranty, of this
// Bundle/Combinatorics-Framework. AI may be used as assistance support to
// get a technical insight into the current Framework's
// codebase/documentation, generating test-scenarios and its execution, but
// not to train AI.
//
// (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
// Ukraine
//
// See LICENSE and NOTICE.md for the binding terms.

package com.company;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeoutException;

/**
 * STEP 21 targeted harness for MainWatch's canonical-outcome classification --
 * exercises {@link MainWatch#classifyFailure}, {@link MainWatch#countOutcome}
 * and {@link MainWatch#reclassifyBatchAsInfraFail} directly (in-process, no
 * subprocess/DB needed -- unlike {@link MainWatchHandoffV2SmokeTest}) so the
 * Java mapping can be checked candidate-by-candidate against the canonical
 * model the same way {@code test_py_executor_outcomes.py} checks py_executor's.
 *
 * Covers the review finding that the async DB-writer (ThreadFileWriterDB /
 * flushRemainingSync) must reclassify already-counted PASS/DOMAIN_FAIL rows to
 * INFRA_FAIL when the batch insert/commit fails -- not just print the
 * exception and leave the counts reporting verdicts that were never persisted.
 *
 * Run:  java -cp target/classes com.company.MainWatchOutcomeClassificationTest
 */
public final class MainWatchOutcomeClassificationTest {
    private MainWatchOutcomeClassificationTest() {}

    public static void main(String[] args) {
        int failures = 0;
        failures += check("classifyFailure maps a TimeoutException cause to TIMEOUT",
                MainWatch.classifyFailure(new RuntimeException("boom", new TimeoutException("slow"))) == MainWatch.Outcome.TIMEOUT);
        failures += check("classifyFailure maps a SQLException cause to INFRA_FAIL",
                MainWatch.classifyFailure(new RuntimeException("boom", new SQLException("conn lost"))) == MainWatch.Outcome.INFRA_FAIL);
        failures += check("classifyFailure maps a SQLTransientConnectionException cause to INFRA_FAIL",
                MainWatch.classifyFailure(new RuntimeException("boom", new java.sql.SQLTransientConnectionException("retry"))) == MainWatch.Outcome.INFRA_FAIL);
        failures += check("classifyFailure defaults an unrelated failure (compile/reflective) to BROKEN",
                MainWatch.classifyFailure(new NoSuchFieldException("FW_VAR")) == MainWatch.Outcome.BROKEN);
        failures += check("classifyFailure walks the cause chain, not just the top exception",
                MainWatch.classifyFailure(new RuntimeException(new RuntimeException(new TimeoutException()))) == MainWatch.Outcome.TIMEOUT);

        failures += checkReclassification();
        failures += checkPassOnlyCountsPassAndDomainFail();
        failures += checkFailureOutcomesAdvanceProcessedCount();
        failures += checkMissingVerdictFieldDoesNotDoubleCountProcessed();

        System.out.println(failures == 0 ? "MainWatchOutcomeClassificationTest: ALL OK ("
                + "5 classifyFailure checks + 4 counting/consistency checks)"
                : "MainWatchOutcomeClassificationTest: " + failures + " FAILURE(S)");
        System.exit(failures == 0 ? 0 : 1);
    }

    /** Mirrors py_executor's `pending_commits` reclassification test: a batch of
     *  already-counted PASS/DOMAIN_FAIL verdicts whose DB write failed must be
     *  moved to INFRA_FAIL -- mutually exclusively, decrementing whichever
     *  domain bucket each row was originally counted into. */
    private static int checkReclassification() {
        // isolate from any prior counts in this process
        for (MainWatch.Outcome o : MainWatch.Outcome.values()) {
            int cur = MainWatch.outcomeCounts.get(o).get();
            if (cur != 0) MainWatch.outcomeCounts.get(o).addAndGet(-cur);
        }

        // 2 candidates classified PASS, 1 classified DOMAIN_FAIL -- exactly as
        // processCandidateFile* does at its bq.add(new SqlRecord(...)) sites.
        List<MainWatch.SqlRecord> batch = new ArrayList<>();
        batch.add(new MainWatch.SqlRecord(true, null, 0, "1_0_0", 0, 0, false, 9));
        MainWatch.countOutcome(MainWatch.Outcome.PASS);
        batch.add(new MainWatch.SqlRecord(true, null, 0, "2_0_0", 0, 0, false, 9));
        MainWatch.countOutcome(MainWatch.Outcome.PASS);
        batch.add(new MainWatch.SqlRecord(false, "src", 1, "3_0_0", 1, 0, false, 9));
        MainWatch.countOutcome(MainWatch.Outcome.DOMAIN_FAIL);

        if (MainWatch.outcomeCounts.get(MainWatch.Outcome.PASS).get() != 2
                || MainWatch.outcomeCounts.get(MainWatch.Outcome.DOMAIN_FAIL).get() != 1) {
            System.out.println("FAIL: precondition -- expected pass=2 domain_fail=1 before reclassification, got pass="
                    + MainWatch.outcomeCounts.get(MainWatch.Outcome.PASS).get() + " domain_fail="
                    + MainWatch.outcomeCounts.get(MainWatch.Outcome.DOMAIN_FAIL).get());
            return 1;
        }

        // the batch insert/commit failed -- not a single row was durably persisted
        MainWatch.reclassifyBatchAsInfraFail(batch, "DB insert/commit failed");

        boolean ok = MainWatch.outcomeCounts.get(MainWatch.Outcome.PASS).get() == 0
                && MainWatch.outcomeCounts.get(MainWatch.Outcome.DOMAIN_FAIL).get() == 0
                && MainWatch.outcomeCounts.get(MainWatch.Outcome.INFRA_FAIL).get() == 3;
        if (!ok) {
            System.out.println("FAIL: a failed batch write must reclassify every already-counted PASS/DOMAIN_FAIL "
                    + "row to INFRA_FAIL (mutually exclusive, never double-counted) -- got pass="
                    + MainWatch.outcomeCounts.get(MainWatch.Outcome.PASS).get() + " domain_fail="
                    + MainWatch.outcomeCounts.get(MainWatch.Outcome.DOMAIN_FAIL).get() + " infra_fail="
                    + MainWatch.outcomeCounts.get(MainWatch.Outcome.INFRA_FAIL).get());
            return 1;
        }
        System.out.println("  ok  reclassifyBatchAsInfraFail moves already-counted PASS/DOMAIN_FAIL rows to INFRA_FAIL on a failed batch write");
        return 0;
    }

    /** Review finding: `processCandidateFilePASSonly` (the cold-start/watch path
     *  for `-Dfw.exec.mode=passonly`) called {@code incrementProcessedCount()}
     *  and queued winners for persistence, but never called {@code countOutcome}
     *  at all -- every candidate it ever processed was invisible to the
     *  canonical outcome model (`outcomes` stayed all-zero regardless of how
     *  many PASS/DOMAIN_FAIL verdicts it produced). Drives the *real* method
     *  end to end (compile+invoke via Janino, exactly as production does) with
     *  one winner (FW_VAR=0 -> PASS, queued) and one non-winner (FW_VAR=1 ->
     *  DOMAIN_FAIL, not queued -- PASSonly mode only persists winners) and
     *  asserts both are now counted. `writeToDB=false`/`writeFile=false` keep
     *  this DB-free and file-free -- a true unit-level exercise of the
     *  classification logic, not an end-to-end persistence smoke. */
    private static int checkPassOnlyCountsPassAndDomainFail() {
        for (MainWatch.Outcome o : MainWatch.Outcome.values()) {
            int cur = MainWatch.outcomeCounts.get(o).get();
            if (cur != 0) MainWatch.outcomeCounts.get(o).addAndGet(-cur);
        }
        MainWatch.bq.clear();
        boolean prevCustom = MainWatch.FW_CUSTOM_VARmode;
        boolean prevWriteToDB = MainWatch.writeToDB;
        boolean prevWriteFile = MainWatch.writeFile;
        File prevOut2 = MainWatch.out2;
        try {
            MainWatch.FW_CUSTOM_VARmode = false;
            MainWatch.writeToDB = false;
            MainWatch.writeFile = false;

            Path dir = Files.createTempDirectory("mainwatch-passonly-outcome-test");
            MainWatch.out2 = dir.toFile();

            Path winner = dir.resolve("100000_0_0.java");
            Files.writeString(winner,
                    "public class C100000_0_0 { public static int FW_VAR = 0; "
                            + "public static void main(String[] args) {} }",
                    StandardCharsets.UTF_8);
            Path loser = dir.resolve("100001_0_0.java");
            Files.writeString(loser,
                    "public class C100001_0_0 { public static int FW_VAR = 1; "
                            + "public static void main(String[] args) {} }",
                    StandardCharsets.UTF_8);

            MainWatch.processCandidateFilePASSonly(winner.toString());
            MainWatch.processCandidateFilePASSonly(loser.toString());

            boolean ok = MainWatch.outcomeCounts.get(MainWatch.Outcome.PASS).get() == 1
                    && MainWatch.outcomeCounts.get(MainWatch.Outcome.DOMAIN_FAIL).get() == 1
                    && MainWatch.bq.size() == 1;   // PASSonly persists winners only
            if (!ok) {
                System.out.println("FAIL: processCandidateFilePASSonly must count PASS for a winner "
                        + "(FW_VAR=0) and DOMAIN_FAIL for a non-winner (FW_VAR=1) -- got pass="
                        + MainWatch.outcomeCounts.get(MainWatch.Outcome.PASS).get() + " domain_fail="
                        + MainWatch.outcomeCounts.get(MainWatch.Outcome.DOMAIN_FAIL).get()
                        + " queued=" + MainWatch.bq.size());
                return 1;
            }
            System.out.println("  ok  processCandidateFilePASSonly counts PASS (winner, queued for persistence) "
                    + "and DOMAIN_FAIL (non-winner, not queued) via the real compile+invoke path");
            return 0;
        } catch (Exception e) {
            System.out.println("FAIL: checkPassOnlyCountsPassAndDomainFail threw: " + e);
            return 1;
        } finally {
            MainWatch.FW_CUSTOM_VARmode = prevCustom;
            MainWatch.writeToDB = prevWriteToDB;
            MainWatch.writeFile = prevWriteFile;
            MainWatch.out2 = prevOut2;
            MainWatch.bq.clear();
        }
    }

    /** Review finding: a candidate that fails to compile/invoke is classified
     *  BROKEN/TIMEOUT/INFRA_FAIL by {@code classifyFailure} and counted into
     *  `outcomeCounts` -- but {@code incrementProcessedCount} (which feeds the
     *  launcher-facing `processed_count`/`processed`) only fired on the success
     *  path, so `processed != sum(outcomes)` by exactly the failure count. The
     *  fix factors both into {@code countFailureOutcome}; this asserts they now
     *  move together -- the same `processed == sum(outcomes)` contract
     *  `executor_processed_eq_sum` enforces launcher-side. */
    private static int checkFailureOutcomesAdvanceProcessedCount() {
        for (MainWatch.Outcome o : MainWatch.Outcome.values()) {
            int cur = MainWatch.outcomeCounts.get(o).get();
            if (cur != 0) MainWatch.outcomeCounts.get(o).addAndGet(-cur);
        }
        int processedBefore = MainWatch.atomicInteger.get();
        int sumBefore = sumOutcomes();

        invokeCountFailureOutcome(MainWatch.Outcome.BROKEN);
        invokeCountFailureOutcome(MainWatch.Outcome.TIMEOUT);
        invokeCountFailureOutcome(MainWatch.Outcome.INFRA_FAIL);

        int processedDelta = MainWatch.atomicInteger.get() - processedBefore;
        int sumDelta = sumOutcomes() - sumBefore;
        boolean ok = processedDelta == 3 && sumDelta == 3 && processedDelta == sumDelta;
        if (!ok) {
            System.out.println("FAIL: a classified compile/invoke failure must advance `processed` "
                    + "(atomicInteger/processed_count) and `sum(outcomes)` together -- got processed_delta="
                    + processedDelta + " sum(outcomes)_delta=" + sumDelta);
            return 1;
        }
        System.out.println("  ok  BROKEN/TIMEOUT/INFRA_FAIL classifications advance processed_count "
                + "in lockstep with outcomeCounts (processed == sum(outcomes) holds)");
        return 0;
    }

    /** Review finding (round 8): `incrementProcessedCount()` was called BEFORE
     *  the reflective `clz.getDeclaredField("FW_VAR"/"FW_CUSTOM_VAR")` read --
     *  if that field is absent (NoSuchFieldException, classified BROKEN by
     *  classifyFailure), the outer catch's `countFailureOutcome` increments
     *  `processed` a SECOND time for the very same candidate: one BROKEN
     *  outcome ends up reported as `processed=2`, breaking `processed ==
     *  sum(outcomes)` in the opposite direction from the prior finding. Drives
     *  the real `processCandidateFilePASSonly` end to end with a candidate that
     *  compiles and runs `main` but declares neither verdict field, and asserts
     *  `processed` advances by exactly 1 alongside exactly one BROKEN count. */
    private static int checkMissingVerdictFieldDoesNotDoubleCountProcessed() {
        for (MainWatch.Outcome o : MainWatch.Outcome.values()) {
            int cur = MainWatch.outcomeCounts.get(o).get();
            if (cur != 0) MainWatch.outcomeCounts.get(o).addAndGet(-cur);
        }
        MainWatch.bq.clear();
        boolean prevCustom = MainWatch.FW_CUSTOM_VARmode;
        boolean prevWriteToDB = MainWatch.writeToDB;
        boolean prevWriteFile = MainWatch.writeFile;
        File prevOut2 = MainWatch.out2;
        int processedBefore = MainWatch.atomicInteger.get();
        try {
            MainWatch.FW_CUSTOM_VARmode = false;
            MainWatch.writeToDB = false;
            MainWatch.writeFile = false;

            Path dir = Files.createTempDirectory("mainwatch-missing-field-outcome-test");
            MainWatch.out2 = dir.toFile();

            // compiles fine, `main` runs fine -- but declares no FW_VAR/FW_CUSTOM_VAR,
            // so the reflective field read throws NoSuchFieldException -> BROKEN.
            Path noField = dir.resolve("200000_0_0.java");
            Files.writeString(noField,
                    "public class C200000_0_0 { public static void main(String[] args) {} }",
                    StandardCharsets.UTF_8);

            MainWatch.processCandidateFilePASSonly(noField.toString());

            int processedDelta = MainWatch.atomicInteger.get() - processedBefore;
            int broken = MainWatch.outcomeCounts.get(MainWatch.Outcome.BROKEN).get();
            boolean ok = processedDelta == 1 && broken == 1 && sumOutcomes() == 1;
            if (!ok) {
                System.out.println("FAIL: a candidate with no FW_VAR/FW_CUSTOM_VAR field must be counted "
                        + "exactly once (processed advances by 1, broken=1) -- got processed_delta="
                        + processedDelta + " broken=" + broken + " sum(outcomes)=" + sumOutcomes()
                        + " (a value of processed_delta=2 is the double-count regression: "
                        + "incrementProcessedCount() before the throwing field read PLUS "
                        + "countFailureOutcome() in the catch)");
                return 1;
            }
            System.out.println("  ok  a candidate missing its verdict field is counted exactly once "
                    + "(processed += 1, broken=1 -- not double-counted via incrementProcessedCount + countFailureOutcome)");
            return 0;
        } catch (Exception e) {
            System.out.println("FAIL: checkMissingVerdictFieldDoesNotDoubleCountProcessed threw: " + e);
            return 1;
        } finally {
            MainWatch.FW_CUSTOM_VARmode = prevCustom;
            MainWatch.writeToDB = prevWriteToDB;
            MainWatch.writeFile = prevWriteFile;
            MainWatch.out2 = prevOut2;
            MainWatch.bq.clear();
        }
    }

    private static int sumOutcomes() {
        int sum = 0;
        for (MainWatch.Outcome o : MainWatch.Outcome.values()) sum += MainWatch.outcomeCounts.get(o).get();
        return sum;
    }

    /** {@code countFailureOutcome} is private -- reflection mirrors how
     *  `processCandidateFile*`'s catch blocks invoke it; calling the real
     *  method (not reimplementing its logic here) is the point of the check. */
    private static void invokeCountFailureOutcome(MainWatch.Outcome o) {
        try {
            java.lang.reflect.Method m = MainWatch.class.getDeclaredMethod("countFailureOutcome", MainWatch.Outcome.class);
            m.setAccessible(true);
            m.invoke(null, o);
        } catch (ReflectiveOperationException e) {
            throw new RuntimeException(e);
        }
    }

    private static int check(String description, boolean condition) {
        System.out.println((condition ? "  ok  " : "  FAIL ") + description);
        return condition ? 0 : 1;
    }
}
