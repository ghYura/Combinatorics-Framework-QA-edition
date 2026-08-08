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
// (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
// Ukraine
//
// See LICENSE and NOTICE.md for the binding terms.

package com.company;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

/**
 * End-to-end candidate-file smoke test for MainWatch's Janino-to-ECJ workflow.
 */
public final class MainWatchAdaptiveCompilerSmokeTest {
    private MainWatchAdaptiveCompilerSmokeTest() {}

    public static void main(String[] args) throws Exception {
        String previousCompiler = System.getProperty("fw.exec.compiler");
        boolean previousCustomMode = MainWatch.FW_CUSTOM_VARmode;
        boolean previousWriteFile = MainWatch.writeFile;
        boolean previousWriteToDb = MainWatch.writeToDB;
        File previousOut2 = MainWatch.out2;
        Path directory = Files.createTempDirectory("mainwatch-adaptive-compiler-");
        boolean ok;

        try {
            System.setProperty("fw.exec.compiler", "adaptive");
            MainWatch.FW_CUSTOM_VARmode = false;
            MainWatch.writeFile = false;
            MainWatch.writeToDB = false;
            MainWatch.out2 = directory.toFile();
            MainWatch.bq.clear();
            resetOutcomeCounts();

            Path candidate = directory.resolve("300000_0_0.java");
            Files.writeString(candidate,
                    "import java.util.List;"
                            + " public class IncomingModernCandidate {"
                            + " public static int FW_VAR = 1;"
                            + " public static void main(String[] args) {"
                            + " var values = List.of(1, 2, 3);"
                            + " FW_VAR = values.stream().mapToInt(value -> value).sum() == 6 ? 0 : 1;"
                            + " }"
                            + " }",
                    StandardCharsets.UTF_8);

            int processedBefore = MainWatch.atomicInteger.get();
            MainWatch.processCandidateFilePASSonly(candidate.toString());

            ok = MainWatch.atomicInteger.get() == processedBefore + 1
                    && MainWatch.outcomeCounts.get(MainWatch.Outcome.PASS).get() == 1
                    && MainWatch.outcomeCounts.get(MainWatch.Outcome.BROKEN).get() == 0
                    && MainWatch.bq.size() == 1;
            System.out.println(ok
                    ? "MainWatchAdaptiveCompilerSmokeTest: ALL OK"
                    : "MainWatchAdaptiveCompilerSmokeTest: FAIL -- modern candidate did not complete as PASS");
        } finally {
            if (previousCompiler == null) {
                System.clearProperty("fw.exec.compiler");
            } else {
                System.setProperty("fw.exec.compiler", previousCompiler);
            }
            MainWatch.FW_CUSTOM_VARmode = previousCustomMode;
            MainWatch.writeFile = previousWriteFile;
            MainWatch.writeToDB = previousWriteToDb;
            MainWatch.out2 = previousOut2;
            MainWatch.bq.clear();
            Files.deleteIfExists(directory.resolve("300000_0_0.java"));
            Files.deleteIfExists(directory);
        }
        System.exit(ok ? 0 : 1);
    }

    private static void resetOutcomeCounts() {
        for (MainWatch.Outcome outcome : MainWatch.Outcome.values()) {
            MainWatch.outcomeCounts.get(outcome).set(0);
        }
    }
}
