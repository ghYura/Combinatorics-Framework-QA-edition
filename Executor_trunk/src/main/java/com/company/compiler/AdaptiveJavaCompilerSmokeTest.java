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

package com.company.compiler;

import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Standalone smoke coverage for the dynamic compiler path used by MainWatch.
 */
public final class AdaptiveJavaCompilerSmokeTest {
    private AdaptiveJavaCompilerSmokeTest() {}

    public static void main(String[] args) throws Exception {
        int failures = 0;
        failures += testJaninoFastPath();
        failures += testModernJavaUsesEcj();
        failures += testGenericNoCastFallsBackToEcj();
        failures += testCompileFailureFallsBackToEcj();
        failures += testPackagedClass();
        failures += testCandidateInvokedOnce();

        System.out.println(failures == 0
                ? "AdaptiveJavaCompilerSmokeTest: ALL OK"
                : "AdaptiveJavaCompilerSmokeTest: " + failures + " FAILURE(S)");
        System.exit(failures == 0 ? 0 : 1);
    }

    private static int testJaninoFastPath() throws Exception {
        String source = "public class LegacyCandidate {"
                + " public static int value() { int total = 0; for (int i = 1; i <= 4; i++) total += i; return total; }"
                + "}";
        try (CompiledJavaClass compiled = new AdaptiveJavaCompiler().compile(
                request("LegacyCandidate", source), AdaptiveJavaCompiler.Mode.ADAPTIVE)) {
            int value = (Integer) compiled.type().getMethod("value").invoke(null);
            return check("legacy source uses native Janino", "janino".equals(compiled.backend()) && value == 10);
        }
    }

    private static int testModernJavaUsesEcj() throws Exception {
        String source = "import java.util.List; public class ModernCandidate {"
                + " public static int value() { var values = List.of(1, 2, 3);"
                + " return values.stream().mapToInt(v -> v).sum(); }"
                + "}";
        try (CompiledJavaClass compiled = new AdaptiveJavaCompiler().compile(
                request("ModernCandidate", source), AdaptiveJavaCompiler.Mode.ADAPTIVE)) {
            int value = (Integer) compiled.type().getMethod("value").invoke(null);
            return check("lambda/var source routes directly to ECJ", "ecj".equals(compiled.backend()) && value == 6);
        }
    }

    private static int testCompileFailureFallsBackToEcj() throws Exception {
        AtomicInteger fastAttempts = new AtomicInteger();
        DynamicJavaCompiler forcedFailure = new DynamicJavaCompiler() {
            @Override
            public String name() {
                return "forced-fast-failure";
            }

            @Override
            public CompiledJavaClass compile(CompilationRequest request) throws Exception {
                fastAttempts.incrementAndGet();
                throw new Exception("forced fast-path compile failure");
            }
        };
        AdaptiveJavaCompiler compiler = new AdaptiveJavaCompiler(forcedFailure, new EcjCompilerBackend());
        String source = "public class FallbackCandidate { public static int value() { return 42; } }";
        try (CompiledJavaClass compiled = compiler.compile(
                request("FallbackCandidate", source), AdaptiveJavaCompiler.Mode.ADAPTIVE)) {
            int value = (Integer) compiled.type().getMethod("value").invoke(null);
            return check("a fast-path compile failure retries once with ECJ",
                    fastAttempts.get() == 1 && "ecj".equals(compiled.backend()) && value == 42);
        }
    }

    private static int testGenericNoCastFallsBackToEcj() throws Exception {
        String source = "import java.util.ArrayList; import java.util.List;"
                + " public class GenericCandidate {"
                + " public static int value() { List<String> values = new ArrayList<String>();"
                + " values.add(\"fallback\"); String value = values.get(0); return value.length(); }"
                + "}";
        try (CompiledJavaClass compiled = new AdaptiveJavaCompiler().compile(
                request("GenericCandidate", source), AdaptiveJavaCompiler.Mode.ADAPTIVE)) {
            int value = (Integer) compiled.type().getMethod("value").invoke(null);
            return check("Janino generic no-cast limitation falls back to ECJ",
                    "ecj".equals(compiled.backend()) && value == 8);
        }
    }

    private static int testPackagedClass() throws Exception {
        String source = "package example.dynamic; public class PackagedCandidate {"
                + " public static String value() { return \"package-ok\"; }"
                + "}";
        try (CompiledJavaClass compiled = new AdaptiveJavaCompiler().compile(
                request("PackagedCandidate", source), AdaptiveJavaCompiler.Mode.ADAPTIVE)) {
            String value = (String) compiled.type().getMethod("value").invoke(null);
            return check("package declaration is reflected in the loaded binary name",
                    "example.dynamic.PackagedCandidate".equals(compiled.type().getName())
                            && "package-ok".equals(value));
        }
    }

    private static int testCandidateInvokedOnce() throws Exception {
        String source = "public class SingleInvocationCandidate {"
                + " public static int calls = 0;"
                + " public static void main(String[] args) { calls++; }"
                + "}";
        try (CompiledJavaClass compiled = new AdaptiveJavaCompiler().compile(
                request("SingleInvocationCandidate", source), AdaptiveJavaCompiler.Mode.ADAPTIVE)) {
            compiled.type().getMethod("main", String[].class).invoke(null, (Object) new String[0]);
            int calls = compiled.type().getField("calls").getInt(null);
            return check("candidate execution remains outside fallback and occurs once", calls == 1);
        }
    }

    private static DynamicJavaCompiler.CompilationRequest request(String className, String source) {
        return DynamicJavaCompiler.CompilationRequest.forSource(
                className,
                source,
                AdaptiveJavaCompilerSmokeTest.class.getClassLoader(),
                List.of(),
                Runtime.version().feature());
    }

    private static int check(String label, boolean condition) {
        System.out.println((condition ? "  ok  " : "FAIL  ") + label);
        return condition ? 0 : 1;
    }
}
